//go:build windows

package main

import (
	"bytes"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"time"
	"unsafe"
)

const (
	releaseVersion = "v1.0.34"

	// Internal identifiers are intentionally kept out of user-facing docs.
	serviceName   = "AegisRecovery_7C31"
	displayName   = "Aegis Recovery Runtime"
	installedFile = "runtime_7c31.exe"
	gateRuleName  = "AegisRecoveryGate_7C31"

	appTaskName   = "NovaBlockApp"
	mainMutexName = `Global\NovaBlock_SingleInstance_Mutex`

	pollInterval         = 5 * time.Millisecond
	browserSweepInterval = 12 * time.Millisecond
	stableWindow         = 120 * time.Millisecond
	restartRetry         = 350 * time.Millisecond
	heartbeatInterval    = 250 * time.Millisecond
	maintenanceMaxAge    = 30 * time.Minute
)

var defaultAction = "install"

var (
	kernel32 = syscall.NewLazyDLL("kernel32.dll")
	advapi32 = syscall.NewLazyDLL("advapi32.dll")
	shell32  = syscall.NewLazyDLL("shell32.dll")

	procOpenMutexW               = kernel32.NewProc("OpenMutexW")
	procCloseHandle              = kernel32.NewProc("CloseHandle")
	procCreateToolhelp32Snapshot = kernel32.NewProc("CreateToolhelp32Snapshot")
	procProcess32FirstW          = kernel32.NewProc("Process32FirstW")
	procProcess32NextW           = kernel32.NewProc("Process32NextW")
	procOpenProcess              = kernel32.NewProc("OpenProcess")
	procTerminateProcess         = kernel32.NewProc("TerminateProcess")

	procStartServiceCtrlDispatcherW   = advapi32.NewProc("StartServiceCtrlDispatcherW")
	procRegisterServiceCtrlHandlerExW = advapi32.NewProc("RegisterServiceCtrlHandlerExW")
	procSetServiceStatus              = advapi32.NewProc("SetServiceStatus")

	procIsUserAnAdmin = shell32.NewProc("IsUserAnAdmin")
)

const (
	synchronize       = 0x00100000
	errorAccessDenied = 5
	errorFileNotFound = 2

	th32csSnapProcess = 0x00000002
	processTerminate  = 0x0001

	serviceWin32OwnProcess = 0x00000010
	serviceStop            = 0x00000001
	serviceShutdown        = 0x00000005
	serviceControlStop     = 0x00000001
	serviceControlShutdown = 0x00000005
	serviceStartPending    = 0x00000002
	serviceStopPending     = 0x00000003
	serviceRunning         = 0x00000004
	serviceStopped         = 0x00000001
	serviceAcceptStop      = 0x00000001
	serviceAcceptShutdown  = 0x00000004
)

type serviceTableEntry struct {
	name *uint16
	proc uintptr
}

type serviceStatus struct {
	serviceType             uint32
	currentState            uint32
	controlsAccepted        uint32
	win32ExitCode           uint32
	serviceSpecificExitCode uint32
	checkPoint              uint32
	waitHint                uint32
}

type processEntry32 struct {
	size            uint32
	cntUsage        uint32
	processID       uint32
	defaultHeapID   uintptr
	moduleID        uint32
	cntThreads      uint32
	parentProcessID uint32
	priClassBase    int32
	flags           uint32
	exeFile         [260]uint16
}

var (
	stopOnce            sync.Once
	stopCh              = make(chan struct{})
	serviceStatusHandle uintptr
)

var browserNames = map[string]struct{}{
	"chrome.exe":    {},
	"msedge.exe":    {},
	"brave.exe":     {},
	"firefox.exe":   {},
	"opera.exe":     {},
	"vivaldi.exe":   {},
	"ucbrowser.exe": {},
}

func main() {
	action := defaultAction
	if len(os.Args) > 1 {
		action = strings.ToLower(strings.TrimSpace(os.Args[1]))
	}

	var err error
	switch action {
	case "--service", "service":
		err = runAsService()
	case "--probe", "probe":
		err = probe()
	case "--status", "status":
		err = statusCheck()
	case "--repair", "--reactivate", "repair", "reactivate", "install":
		err = installOrRepair()
	case "--repair-network", "repair-network":
		err = repairNetworkState()
	case "--maintenance-pause", "maintenance-pause":
		err = maintenancePause()
	case "--rollback", "rollback":
		err = rollback()
	case "--version", "version":
		fmt.Println(releaseVersion)
		return
	default:
		err = fmt.Errorf("unknown action: %s", action)
	}
	if err != nil {
		logLine("ERROR: %v", err)
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func programDataDir() string {
	base := os.Getenv("ProgramData")
	if base == "" {
		base = `C:\ProgramData`
	}
	return filepath.Join(base, "NovaBlock")
}

func installedPath() string { return filepath.Join(programDataDir(), installedFile) }
func heartbeatPath() string { return filepath.Join(programDataDir(), "recovery_v134.heartbeat") }
func logPath() string       { return filepath.Join(programDataDir(), "update_v134.log") }

func logLine(format string, args ...any) {
	_ = os.MkdirAll(programDataDir(), 0o755)
	f, err := os.OpenFile(logPath(), os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	if err != nil {
		return
	}
	defer f.Close()
	_, _ = fmt.Fprintf(f, "%s "+format+"\r\n", append([]any{time.Now().Format("2006-01-02 15:04:05.000")}, args...)...)
}

func probe() error {
	if runtimeUnsupported() {
		return errors.New("Windows APIs required by the recovery layer are unavailable")
	}
	_ = os.MkdirAll(programDataDir(), 0o755)
	logLine("probe ok (%s)", releaseVersion)
	return nil
}

func runtimeUnsupported() bool {
	return procOpenMutexW.Find() != nil || procStartServiceCtrlDispatcherW.Find() != nil || procSetServiceStatus.Find() != nil
}

func isAdmin() bool {
	r, _, _ := procIsUserAnAdmin.Call()
	return r != 0
}

func requireAdmin() error {
	if !isAdmin() {
		return errors.New("administrator privileges are required")
	}
	return nil
}

func command(name string, args ...string) *exec.Cmd {
	cmd := exec.Command(name, args...)
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	return cmd
}

func runCommand(name string, args ...string) (string, error) {
	cmd := command(name, args...)
	var buf bytes.Buffer
	cmd.Stdout = &buf
	cmd.Stderr = &buf
	err := cmd.Run()
	if err != nil {
		return buf.String(), fmt.Errorf("%s %s: %w (%s)", name, strings.Join(args, " "), err, strings.TrimSpace(buf.String()))
	}
	return buf.String(), nil
}

func runBestEffort(name string, args ...string) {
	_, _ = runCommand(name, args...)
}

func installOrRepair() error {
	if err := requireAdmin(); err != nil {
		return err
	}
	if err := probe(); err != nil {
		return err
	}
	logLine("install/repair start")
	if err := os.MkdirAll(programDataDir(), 0o755); err != nil {
		return err
	}

	cleanupExperimentalServices()
	loosenServiceACL()
	runBestEffort("sc.exe", "stop", serviceName)
	waitForServiceStop(4 * time.Second)
	_ = os.Remove(heartbeatPath())

	if err := installSelfCopy(); err != nil {
		return fmt.Errorf("install recovery runtime: %w", err)
	}
	if err := ensureGateRule(); err != nil {
		return fmt.Errorf("prepare fail-closed gate: %w", err)
	}
	if err := ensureService(); err != nil {
		return fmt.Errorf("register recovery service: %w", err)
	}
	tightenServiceACL()

	runBestEffort("sc.exe", "start", serviceName)
	if err := waitFreshHeartbeat(8 * time.Second); err != nil {
		loosenServiceACL()
		runBestEffort("sc.exe", "stop", serviceName)
		setGate(false)
		return fmt.Errorf("recovery component did not become healthy: %w", err)
	}

	if mainRunning() {
		setGate(false)
	}
	logLine("install/repair complete")
	fmt.Println("NovaBlock v1.0.34 recovery layer: OK")
	return nil
}

func installSelfCopy() error {
	self, err := os.Executable()
	if err != nil {
		return err
	}
	self, _ = filepath.Abs(self)
	dst := installedPath()
	dstAbs, _ := filepath.Abs(dst)
	if strings.EqualFold(self, dstAbs) {
		return nil
	}
	in, err := os.Open(self)
	if err != nil {
		return err
	}
	defer in.Close()
	tmp := dst + ".new"
	out, err := os.Create(tmp)
	if err != nil {
		return err
	}
	_, copyErr := io.Copy(out, in)
	closeErr := out.Close()
	if copyErr != nil {
		return copyErr
	}
	if closeErr != nil {
		return closeErr
	}

	deadline := time.Now().Add(5 * time.Second)
	for {
		_ = os.Remove(dst)
		if err := os.Rename(tmp, dst); err == nil {
			return nil
		}
		if time.Now().After(deadline) {
			return fmt.Errorf("could not replace %s", dst)
		}
		time.Sleep(50 * time.Millisecond)
	}
}

func ensureGateRule() error {
	runBestEffort("netsh", "advfirewall", "firewall", "delete", "rule", "name="+gateRuleName)
	_, err := runCommand("netsh", "advfirewall", "firewall", "add", "rule",
		"name="+gateRuleName, "dir=out", "action=block", "enable=no", "profile=any")
	return err
}

func setGate(enable bool) {
	state := "no"
	if enable {
		state = "yes"
	}
	_, err := runCommand("netsh", "advfirewall", "firewall", "set", "rule", "name="+gateRuleName, "new", "enable="+state)
	if err != nil {
		logLine("gate enable=%s failed: %v", state, err)
	}
}

func ensureService() error {
	bin := fmt.Sprintf(`"%s" --service`, installedPath())
	if _, err := runCommand("sc.exe", "query", serviceName); err == nil {
		if _, err = runCommand("sc.exe", "config", serviceName, "binPath=", bin, "start=", "auto"); err != nil {
			return err
		}
	} else {
		if _, err = runCommand("sc.exe", "create", serviceName,
			"binPath=", bin, "start=", "auto", "type=", "own", "error=", "normal", "DisplayName=", displayName); err != nil {
			return err
		}
	}
	runBestEffort("sc.exe", "description", serviceName, "Application recovery runtime")
	runBestEffort("sc.exe", "failure", serviceName, "reset=", "86400", "actions=", "restart/1000/restart/1000/restart/5000")
	runBestEffort("sc.exe", "failureflag", serviceName, "1")
	return nil
}

func loosenServiceACL() {
	runBestEffort("sc.exe", "sdset", serviceName,
		"D:(A;;CCLCSWRPWPDTLOCRRC;;;SY)(A;;CCLCSWRPWPDTLOCRRC;;;BA)")
}

func tightenServiceACL() {
	runBestEffort("sc.exe", "sdset", serviceName,
		"D:(A;;CCLCSWRPWPDTLOCRRC;;;SY)(A;;CCLCSWLORC;;;BA)(A;;CCLCSWLORC;;;IU)(A;;CCLCSWLORC;;;SU)")
}

func waitForServiceStop(max time.Duration) {
	deadline := time.Now().Add(max)
	for time.Now().Before(deadline) {
		out, _ := runCommand("sc.exe", "query", serviceName)
		if !strings.Contains(out, ": 4") && !strings.Contains(out, ": 2") && !strings.Contains(out, ": 3") {
			return
		}
		time.Sleep(100 * time.Millisecond)
	}
}

func cleanupExperimentalServices() {
	for _, name := range []string{"NovaBlockService", "NovaBlockGuardian"} {
		runBestEffort("sc.exe", "sdset", name, "D:(A;;CCLCSWRPWPDTLOCRRC;;;SY)(A;;CCLCSWRPWPDTLOCRRC;;;BA)")
		runBestEffort("sc.exe", "stop", name)
		runBestEffort("sc.exe", "delete", name)
	}
}

func maintenancePause() error {
	if err := requireAdmin(); err != nil {
		return err
	}
	logLine("maintenance pause requested")
	loosenServiceACL()
	runBestEffort("sc.exe", "stop", serviceName)
	waitForServiceStop(4 * time.Second)
	runBestEffort("sc.exe", "config", serviceName, "start=", "disabled")
	setGate(false)
	return nil
}

func rollback() error {
	if err := requireAdmin(); err != nil {
		return err
	}
	logLine("rollback to v1.0.33 base start")
	loosenServiceACL()
	runBestEffort("sc.exe", "stop", serviceName)
	waitForServiceStop(4 * time.Second)
	runBestEffort("sc.exe", "delete", serviceName)
	setGate(false)
	runBestEffort("netsh", "advfirewall", "firewall", "delete", "rule", "name="+gateRuleName)
	cleanupExperimentalServices()
	_ = os.Remove(heartbeatPath())
	_ = os.Remove(installedPath())
	runBestEffort("schtasks", "/Run", "/TN", appTaskName)
	logLine("rollback complete")
	fmt.Println("Retour au socle NovaBlock v1.0.33: OK")
	return nil
}

func repairNetworkState() error {
	if err := requireAdmin(); err != nil {
		return err
	}
	if !mainRunning() {
		runBestEffort("schtasks", "/Run", "/TN", appTaskName)
		deadline := time.Now().Add(10 * time.Second)
		for time.Now().Before(deadline) && !mainRunning() {
			time.Sleep(50 * time.Millisecond)
		}
	}
	if mainRunning() {
		setGate(false)
		return nil
	}
	return errors.New("NovaBlock principal absent; le mode fail-closed reste actif")
}

func statusCheck() error {
	if !serviceIsRunning() {
		return errors.New("recovery service is not running")
	}
	if !freshHeartbeat(2 * time.Second) {
		return errors.New("recovery heartbeat is not fresh")
	}
	fmt.Println("NovaBlock v1.0.34 recovery layer: healthy")
	return nil
}

func serviceIsRunning() bool {
	out, err := runCommand("sc.exe", "query", serviceName)
	if err != nil {
		return false
	}
	return strings.Contains(out, ": 4")
}

func waitFreshHeartbeat(max time.Duration) error {
	deadline := time.Now().Add(max)
	for time.Now().Before(deadline) {
		if freshHeartbeat(1500 * time.Millisecond) {
			return nil
		}
		time.Sleep(100 * time.Millisecond)
	}
	return errors.New("heartbeat timeout")
}

func freshHeartbeat(maxAge time.Duration) bool {
	st, err := os.Stat(heartbeatPath())
	if err != nil {
		return false
	}
	age := time.Since(st.ModTime())
	return age >= 0 && age <= maxAge
}

func markerRecent(name string) bool {
	st, err := os.Stat(filepath.Join(programDataDir(), name))
	if err != nil {
		return false
	}
	age := time.Since(st.ModTime())
	return age >= -5*time.Second && age <= maintenanceMaxAge
}

func maintenanceActive() bool {
	return markerRecent("shutdown.sentinel") || markerRecent("update.lock")
}

func mainRunning() bool {
	name, _ := syscall.UTF16PtrFromString(mainMutexName)
	r, _, e := procOpenMutexW.Call(synchronize, 0, uintptr(unsafe.Pointer(name)))
	if r != 0 {
		procCloseHandle.Call(r)
		return true
	}
	errno, ok := e.(syscall.Errno)
	if ok && uint32(errno) == errorAccessDenied {
		return true
	}
	if ok && uint32(errno) == errorFileNotFound {
		return false
	}
	return false
}

func requestAppRestart() {
	if out, err := runCommand("schtasks", "/Run", "/TN", appTaskName); err != nil {
		logLine("restart request failed: %v output=%s", err, strings.TrimSpace(out))
	}
}

func closeBrowsersNative() int {
	snap, _, _ := procCreateToolhelp32Snapshot.Call(th32csSnapProcess, 0)
	invalid := ^uintptr(0)
	if snap == 0 || snap == invalid {
		return 0
	}
	defer procCloseHandle.Call(snap)

	var pe processEntry32
	pe.size = uint32(unsafe.Sizeof(pe))
	ok, _, _ := procProcess32FirstW.Call(snap, uintptr(unsafe.Pointer(&pe)))
	killed := 0
	for ok != 0 {
		exe := strings.ToLower(syscall.UTF16ToString(pe.exeFile[:]))
		if _, match := browserNames[exe]; match {
			h, _, _ := procOpenProcess.Call(processTerminate, 0, uintptr(pe.processID))
			if h != 0 {
				r, _, _ := procTerminateProcess.Call(h, 1)
				procCloseHandle.Call(h)
				if r != 0 {
					killed++
				}
			}
		}
		pe.size = uint32(unsafe.Sizeof(pe))
		ok, _, _ = procProcess32NextW.Call(snap, uintptr(unsafe.Pointer(&pe)))
	}
	return killed
}

func recoverMain() {
	// The first browser sweep is synchronous and happens before spawning any
	// slower command. This is the core v5 behavior that removes the download gap.
	killed := closeBrowsersNative()
	if killed > 0 {
		logLine("fast browser sweep closed %d process(es)", killed)
	}

	gateDone := make(chan struct{})
	go func() { setGate(true); close(gateDone) }()
	go requestAppRestart()

	lastRestart := time.Now()
	nextSweep := time.Now().Add(browserSweepInterval)
	var stableSince time.Time

	for {
		select {
		case <-stopCh:
			return
		default:
		}

		if maintenanceActive() {
			setGate(false)
			return
		}

		now := time.Now()
		if now.After(nextSweep) {
			closeBrowsersNative()
			nextSweep = now.Add(browserSweepInterval)
		}

		if mainRunning() {
			if stableSince.IsZero() {
				stableSince = now
			}
			if now.Sub(stableSince) >= stableWindow {
				// Prefer finishing gate activation before turning it back off,
				// avoiding an inverted race where a late enable lands after recovery.
				select {
				case <-gateDone:
				case <-time.After(2 * time.Second):
				}
				setGate(false)
				logLine("main recovered and stable after %s", now.Sub(stableSince))
				return
			}
		} else {
			stableSince = time.Time{}
			if now.Sub(lastRestart) >= restartRetry {
				go requestAppRestart()
				lastRestart = now
			}
		}
		time.Sleep(pollInterval)
	}
}

func writeHeartbeat() {
	_ = os.MkdirAll(programDataDir(), 0o755)
	_ = os.WriteFile(heartbeatPath(), []byte(fmt.Sprintf("%d\r\n", time.Now().UnixMilli())), 0o644)
}

func serviceLoop() {
	logLine("recovery service loop start (%s)", releaseVersion)
	nextHB := time.Time{}
	nextMaintenanceCheck := time.Time{}
	maintenance := false
	gateKnownOff := false

	for {
		select {
		case <-stopCh:
			logLine("service stop requested")
			return
		default:
		}
		now := time.Now()
		if now.After(nextHB) {
			writeHeartbeat()
			nextHB = now.Add(heartbeatInterval)
		}
		if now.After(nextMaintenanceCheck) {
			maintenance = maintenanceActive()
			nextMaintenanceCheck = now.Add(100 * time.Millisecond)
			if maintenance && !gateKnownOff {
				setGate(false)
				gateKnownOff = true
			}
		}
		if maintenance {
			time.Sleep(25 * time.Millisecond)
			continue
		}
		gateKnownOff = false
		if !mainRunning() {
			logLine("main absence detected")
			recoverMain()
			continue
		}
		time.Sleep(pollInterval)
	}
}

func runAsService() error {
	if runtimeUnsupported() {
		return errors.New("required Windows service APIs unavailable")
	}
	name, _ := syscall.UTF16PtrFromString(serviceName)
	table := []serviceTableEntry{
		{name: name, proc: syscall.NewCallback(serviceMain)},
		{},
	}
	r, _, e := procStartServiceCtrlDispatcherW.Call(uintptr(unsafe.Pointer(&table[0])))
	if r == 0 {
		return fmt.Errorf("StartServiceCtrlDispatcherW: %v", e)
	}
	return nil
}

func serviceMain(argc uintptr, argv uintptr) uintptr {
	name, _ := syscall.UTF16PtrFromString(serviceName)
	handler := syscall.NewCallback(serviceControlHandler)
	h, _, _ := procRegisterServiceCtrlHandlerExW.Call(uintptr(unsafe.Pointer(name)), handler, 0)
	if h == 0 {
		return 0
	}
	serviceStatusHandle = h
	reportServiceStatus(serviceStartPending, 0, 2000)
	reportServiceStatus(serviceRunning, serviceAcceptStop|serviceAcceptShutdown, 0)
	serviceLoop()
	reportServiceStatus(serviceStopPending, 0, 500)
	reportServiceStatus(serviceStopped, 0, 0)
	return 0
}

func serviceControlHandler(control uintptr, eventType uintptr, eventData uintptr, context uintptr) uintptr {
	if uint32(control) == serviceControlStop || uint32(control) == serviceControlShutdown || uint32(control) == serviceStop || uint32(control) == serviceShutdown {
		stopOnce.Do(func() { close(stopCh) })
	}
	return 0
}

func reportServiceStatus(state uint32, accepted uint32, waitHint uint32) {
	if serviceStatusHandle == 0 {
		return
	}
	st := serviceStatus{
		serviceType:      serviceWin32OwnProcess,
		currentState:     state,
		controlsAccepted: accepted,
		waitHint:         waitHint,
	}
	procSetServiceStatus.Call(serviceStatusHandle, uintptr(unsafe.Pointer(&st)))
}
