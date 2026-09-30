//go:build windows

package main

import (
	"fmt"
	"testing"
)

func interactiveTaskXML(command, args, enabled, logonType string) string {
	return fmt.Sprintf(`<Task><Principals><Principal><UserId>S-1-5-21-123</UserId>`+
		`<LogonType>%s</LogonType></Principal></Principals><Settings><Enabled>%s</Enabled></Settings>`+
		`<Actions><Exec><Command>%s</Command><Arguments>%s</Arguments></Exec></Actions></Task>`,
		logonType, enabled, command, args)
}

func TestInteractiveTaskRequiresRegisteredExecutable(t *testing.T) {
	expected := `C:\Program Files\NovaBlock\NovaBlock.exe`
	valid := interactiveTaskXML(expected, "", "true", "InteractiveToken")
	if err := validateInteractiveTaskXML(valid, expected); err != nil {
		t.Fatalf("valid task rejected: %v", err)
	}
	for _, value := range []string{
		interactiveTaskXML(`C:\Temp\NovaBlock.exe`, "", "true", "InteractiveToken"),
		interactiveTaskXML(expected, "--service-run", "true", "InteractiveToken"),
		interactiveTaskXML(expected, "", "false", "InteractiveToken"),
		interactiveTaskXML(expected, "", "true", "Password"),
	} {
		if err := validateInteractiveTaskXML(value, expected); err == nil {
			t.Fatalf("unsafe task accepted: %s", value)
		}
	}
}

func TestTaskValueDecodesXmlPath(t *testing.T) {
	path := `C:\A & B\NovaBlock.exe`
	xml := interactiveTaskXML(`C:\A &amp; B\NovaBlock.exe`, "", "true", "InteractiveToken")
	if err := validateInteractiveTaskXML(xml, path); err != nil {
		t.Fatalf("escaped registered path rejected: %v", err)
	}
}

func TestRegisteredAppPathParsing(t *testing.T) {
	output := "HKEY_LOCAL_MACHINE\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\n" +
		"    NovaBlock    REG_SZ    \"C:\\Program Files\\NovaBlock\\NovaBlock.exe\"\n"
	path, err := parseRegisteredAppPath(output)
	if err != nil || path != `C:\Program Files\NovaBlock\NovaBlock.exe` {
		t.Fatalf("registered path parse failed: %q %v", path, err)
	}
	if _, err := parseRegisteredAppPath("no value"); err == nil {
		t.Fatal("missing registered path accepted")
	}
}

func TestProcessIdentityRequiresSameRegisteredExecutable(t *testing.T) {
	if !sameExecutablePath(`\\?\C:\Apps\NovaBlock.exe`, `c:\apps\novablock.exe`) {
		t.Fatal("same installed executable not recognized")
	}
	if sameExecutablePath(`C:\Temp\NovaBlock.exe`, `C:\Apps\NovaBlock.exe`) {
		t.Fatal("renamed executable in another directory accepted")
	}
	if sameExecutablePath("", `C:\Apps\NovaBlock.exe`) {
		t.Fatal("missing executable path accepted")
	}
}
