//go:build windows

package main

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestSamePathUsesWindowsCaseAndExtendedPrefix(t *testing.T) {
	if !samePath(`\\?\C:\Program Files\Example\Main.exe`, `c:\program files\example\main.exe`) {
		t.Fatal("same Windows path was rejected")
	}
	if samePath(`C:\Other\Main.exe`, `C:\Example\Main.exe`) {
		t.Fatal("different binary was accepted")
	}
}

func TestBrowserWindowClassifiesUCVariantsAndCommonBrowsers(t *testing.T) {
	for _, item := range []struct {
		image, title string
		want         bool
	}{
		{`C:\Program Files\UC\UCBrowser\browser.exe`, "Page", true},
		{`C:\Tools\browser.exe`, "Page - UC Browser", true},
		{`C:\Program Files\Chrome\chrome.exe`, "Page", true},
		{`C:\Tools\editor.exe`, "Document", false},
	} {
		if got := browserWindow(item.image, item.title); got != item.want {
			t.Errorf("browserWindow(%q, %q) = %v, want %v", item.image, item.title, got, item.want)
		}
	}
}

func TestMaintenanceMarkerExpires(t *testing.T) {
	t.Setenv("ProgramData", t.TempDir())
	if err := os.MkdirAll(dataDir(), 0o700); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(dataDir(), "update.lock")
	if err := os.WriteFile(path, []byte("test"), 0o600); err != nil {
		t.Fatal(err)
	}
	if !paused() {
		t.Fatal("current maintenance was ignored")
	}
	old := time.Now().Add(-maintenanceAge - time.Second)
	if err := os.Chtimes(path, old, old); err != nil {
		t.Fatal(err)
	}
	if paused() {
		t.Fatal("expired maintenance kept relay stopped")
	}
}
