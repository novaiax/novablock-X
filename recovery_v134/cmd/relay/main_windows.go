//go:build windows

// A small interactive-session relay. It never changes networking, installs
// services, or terminates browsers. The main application starts it with its
// existing elevated token; it only restarts the registered application.
package main

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"time"
	"unsafe"
)

const (
	pollInterval    = 25 * time.Millisecond
	launchGrace     = 5 * time.Second
	maintenanceAge  = 30 * time.Minute
	processQuery    = 0x1000
	synchronize     = 0x00100000
	waitTimeout     = 0x00000102
	detachedProcess = 0x00000008
	mainMutexName   = `Global\NovaBlock_SingleInstance_Mutex`
)

var (
	kernel32             = syscall.NewLazyDLL("kernel32.dll")
	shell32              = syscall.NewLazyDLL("shell32.dll")
	user32               = syscall.NewLazyDLL("user32.dll")
	openProcess          = kernel32.NewProc("OpenProcess")
	openMutex            = kernel32.NewProc("OpenMutexW")
	closeHandle          = kernel32.NewProc("CloseHandle")
	waitForSingleObject  = kernel32.NewProc("WaitForSingleObject")
	queryFullProcessName = kernel32.NewProc("QueryFullProcessImageNameW")
	isUserAnAdmin        = shell32.NewProc("IsUserAnAdmin")
	enumWindows          = user32.NewProc("EnumWindows")
	isWindowVisible      = user32.NewProc("IsWindowVisible")
	getWindowProcessID   = user32.NewProc("GetWindowThreadProcessId")
	getWindowText        = user32.NewProc("GetWindowTextW")
	postMessage          = user32.NewProc("PostMessageW")
)

var browserImages = map[string]bool{
	"chrome.exe": true, "msedge.exe": true, "brave.exe": true,
	"firefox.exe": true, "opera.exe": true, "vivaldi.exe": true,
	"iexplore.exe": true, "tor.exe": true, "ucbrowser.exe": true,
	"ucbrowserlauncher.exe": true,
}

func dataDir() string {
	base := os.Getenv("ProgramData")
	if base == "" {
		base = `C:\ProgramData`
	}
	return filepath.Join(base, "NovaBlock")
}

func logLine(format string, args ...any) {
	file, err := os.OpenFile(filepath.Join(dataDir(), "continuity.log"), os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o600)
	if err != nil {
		return
	}
	defer file.Close()
	_, _ = fmt.Fprintf(file, "%s "+format+"\r\n", append([]any{time.Now().Format("2006-01-02 15:04:05.000")}, args...)...)
}

func recentMarker(name string) bool {
	st, err := os.Stat(filepath.Join(dataDir(), name))
	if err != nil {
		return false
	}
	age := time.Since(st.ModTime())
	return age >= -5*time.Second && age < maintenanceAge
}

func paused() bool { return recentMarker("shutdown.sentinel") || recentMarker("update.lock") }

func registeredAppPath() (string, error) {
	cmd := exec.Command("reg.exe", "query", `HKLM\Software\Microsoft\Windows\CurrentVersion\Run`, "/v", "NovaBlock")
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	out, err := cmd.Output()
	if err != nil {
		return "", err
	}
	for _, line := range strings.Split(string(out), "\n") {
		upper := strings.ToUpper(line)
		index := strings.Index(upper, "REG_SZ")
		if index >= 0 && strings.Contains(upper[:index], "NOVABLOCK") {
			value := strings.Trim(strings.TrimSpace(line[index+len("REG_SZ"):]), `"`)
			if strings.EqualFold(filepath.Ext(value), ".exe") {
				if info, statErr := os.Stat(value); statErr == nil && !info.IsDir() {
					return value, nil
				}
			}
		}
	}
	return "", errors.New("registered application executable unavailable")
}

func samePath(actual, expected string) bool {
	actual = strings.TrimPrefix(actual, `\\?\`)
	expected = strings.TrimPrefix(expected, `\\?\`)
	return actual != "" && expected != "" && strings.EqualFold(filepath.Clean(actual), filepath.Clean(expected))
}

func processMatches(pid uint64, expected string) bool {
	if pid == 0 || pid > 0xffffffff {
		return false
	}
	handle, _, _ := openProcess.Call(processQuery|synchronize, 0, uintptr(pid))
	if handle == 0 {
		return false
	}
	defer closeHandle.Call(handle)
	state, _, _ := waitForSingleObject.Call(handle, 0)
	if state != waitTimeout {
		return false
	}
	var buf [32768]uint16
	length := uint32(len(buf))
	ok, _, _ := queryFullProcessName.Call(handle, 0, uintptr(unsafe.Pointer(&buf[0])), uintptr(unsafe.Pointer(&length)))
	return ok != 0 && length > 0 && samePath(syscall.UTF16ToString(buf[:int(length)]), expected)
}

func processImage(pid uint32) string {
	handle, _, _ := openProcess.Call(processQuery, 0, uintptr(pid))
	if handle == 0 {
		return ""
	}
	defer closeHandle.Call(handle)
	var buf [32768]uint16
	length := uint32(len(buf))
	ok, _, _ := queryFullProcessName.Call(handle, 0,
		uintptr(unsafe.Pointer(&buf[0])), uintptr(unsafe.Pointer(&length)))
	if ok == 0 || length == 0 {
		return ""
	}
	return syscall.UTF16ToString(buf[:int(length)])
}

func browserWindow(image, title string) bool {
	lowerPath := strings.ToLower(strings.ReplaceAll(image, "/", `\`))
	if browserImages[strings.ToLower(filepath.Base(image))] ||
		strings.Contains(lowerPath, `\ucbrowser\`) ||
		strings.Contains(lowerPath, `\uc browser\`) ||
		strings.Contains(lowerPath, `\ucweb\`) {
		return true
	}
	title = strings.ToLower(strings.TrimSpace(title))
	return title == "uc browser" || strings.HasSuffix(title, " - uc browser") ||
		strings.HasSuffix(title, " | uc browser") || strings.HasSuffix(title, " — uc browser")
}

func closeBrowserWindows() int {
	closed := 0
	callback := syscall.NewCallback(func(hwnd, _ uintptr) uintptr {
		visible, _, _ := isWindowVisible.Call(hwnd)
		if visible == 0 {
			return 1
		}
		var pid uint32
		getWindowProcessID.Call(hwnd, uintptr(unsafe.Pointer(&pid)))
		if pid == 0 {
			return 1
		}
		var title [512]uint16
		getWindowText.Call(hwnd, uintptr(unsafe.Pointer(&title[0])), uintptr(len(title)))
		if browserWindow(processImage(pid), syscall.UTF16ToString(title[:])) {
			if ok, _, _ := postMessage.Call(hwnd, 0x0010, 0, 0); ok != 0 { // WM_CLOSE
				closed++
			}
		}
		return 1
	})
	enumWindows.Call(callback, 0)
	return closed
}

func mainMutexPresent() bool {
	name, _ := syscall.UTF16PtrFromString(mainMutexName)
	handle, _, callErr := openMutex.Call(synchronize, 0, uintptr(unsafe.Pointer(name)))
	if handle != 0 {
		closeHandle.Call(handle)
		return true
	}
	errno, ok := callErr.(syscall.Errno)
	return ok && errno == 5 // An existing protected mutex can deny a query.
}

func mainRunning(expected string) bool {
	if !mainMutexPresent() {
		return false
	}
	data, err := os.ReadFile(filepath.Join(dataDir(), "main.pid"))
	if err != nil {
		return false
	}
	pid, err := strconv.ParseUint(strings.TrimSpace(string(data)), 10, 32)
	return err == nil && processMatches(pid, expected)
}

func launch(expected string) (uint64, error) {
	cmd := exec.Command(expected)
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: syscall.CREATE_NEW_PROCESS_GROUP | detachedProcess}
	if err := cmd.Start(); err != nil {
		return 0, err
	}
	pid := uint64(cmd.Process.Pid)
	if err := cmd.Process.Release(); err != nil {
		return pid, err
	}
	return pid, nil
}

func supervise() error {
	admin, _, _ := isUserAnAdmin.Call()
	if admin == 0 {
		return errors.New("interactive relay requires an elevated launch")
	}
	path, err := registeredAppPath()
	if err != nil {
		return err
	}
	if err := os.WriteFile(filepath.Join(dataDir(), "companion.pid"), []byte(strconv.Itoa(os.Getpid())), 0o600); err != nil {
		return err
	}
	defer func() {
		data, err := os.ReadFile(filepath.Join(dataDir(), "companion.pid"))
		if err == nil && strings.TrimSpace(string(data)) == strconv.Itoa(os.Getpid()) {
			_ = os.Remove(filepath.Join(dataDir(), "companion.pid"))
		}
	}()
	logLine("interactive relay active")
	var pending uint64
	var launched time.Time
	var absentSince time.Time
	for {
		if paused() {
			logLine("maintenance marker observed; relay exits")
			return nil
		}
		if mainRunning(path) {
			if !absentSince.IsZero() {
				logLine("main process restored after %s", time.Since(absentSince))
				absentSince = time.Time{}
			}
			pending = 0
		} else if pending == 0 || (!processMatches(pending, path) && time.Since(launched) >= launchGrace) {
			if absentSince.IsZero() {
				absentSince = time.Now()
				logLine("main absence detected")
			}
			go func() {
				if count := closeBrowserWindows(); count > 0 {
					logLine("closed %d browser window(s) while restarting protection", count)
				}
			}()
			start := time.Now()
			pending, err = launch(path)
			launched = time.Now()
			if err != nil {
				logLine("interactive restart failed: %v", err)
			} else {
				logLine("interactive restart requested in %s", time.Since(start))
			}
		}
		time.Sleep(pollInterval)
	}
}

func main() {
	if len(os.Args) == 2 && os.Args[1] == "--probe" {
		fmt.Println("interactive relay available")
		return
	}
	if len(os.Args) != 2 || os.Args[1] != "--supervise" {
		os.Exit(2)
	}
	if err := supervise(); err != nil {
		logLine("interactive relay stopped: %v", err)
		os.Exit(1)
	}
}
