"""UC Browser cannot be used as an unmonitored browser."""

import unittest
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from novablock import browser_kill, monitor


class UcBrowserGuardTests(unittest.TestCase):
    def test_uc_process_names_and_install_paths_are_recognized(self):
        self.assertTrue(browser_kill.is_uc_browser_process("UCBrowser.exe"))
        self.assertTrue(browser_kill.is_uc_browser_process(
            "browser.exe", r"C:\Program Files\UC Browser\browser.exe"))
        self.assertFalse(browser_kill.is_uc_browser_process("NovaBlock.exe"))
        self.assertFalse(browser_kill.is_uc_browser_process("chrome.exe"))

    def test_only_uc_processes_are_closed(self):
        uc = SimpleNamespace(info={"name": "UCBrowser.exe", "exe": ""}, kill=Mock())
        chrome = SimpleNamespace(info={"name": "chrome.exe", "exe": ""}, kill=Mock())
        with patch.object(browser_kill.psutil, "process_iter", return_value=[uc, chrome]):
            self.assertEqual(browser_kill.close_uc_browser_processes(), 1)
        uc.kill.assert_called_once_with()
        chrome.kill.assert_not_called()

    def test_foreground_uc_triggers_popup_and_closure(self):
        detected = []
        guard = monitor.WindowMonitor(
            on_detect=lambda title, keyword, hwnd: (detected.append((title, keyword, hwnd)), guard.stop()),
        )
        with patch.object(monitor.win32gui, "GetForegroundWindow", return_value=99), \
             patch.object(monitor.win32gui, "GetWindowText", return_value="UC Browser"), \
             patch.object(monitor.win32process, "GetWindowThreadProcessId", return_value=(0, 42)), \
             patch.object(guard, "_is_uc_browser", return_value=True), \
             patch("novablock.config.is_temp_unlocked", return_value=False), \
             patch.object(browser_kill, "close_uc_browser_processes", return_value=1) as close:
            guard._loop()
        self.assertEqual(detected, [("UC Browser", "UC Browser non contrôlé", 99)])
        close.assert_called_once_with()

    def test_renamed_uc_window_is_still_closed(self):
        detected = []
        guard = monitor.WindowMonitor(
            on_detect=lambda title, keyword, hwnd: (detected.append(keyword), guard.stop()),
        )
        proc = SimpleNamespace(name=Mock(return_value="browser.exe"), kill=Mock())
        with patch.object(monitor.win32gui, "GetForegroundWindow", return_value=99), \
             patch.object(monitor.win32gui, "GetWindowText", return_value="Page - UC Browser"), \
             patch.object(monitor.win32process, "GetWindowThreadProcessId", return_value=(0, 42)), \
             patch.object(guard, "_is_uc_browser", return_value=False), \
             patch.object(guard, "_is_browser", return_value=False), \
             patch.object(monitor.psutil, "Process", return_value=proc), \
             patch("novablock.config.is_temp_unlocked", return_value=False):
            guard._loop()
        self.assertEqual(detected, ["UC Browser non contrôlé"])
        proc.kill.assert_called_once_with()

    def test_browser_process_lists_do_not_drift(self):
        source = (Path(__file__).resolve().parents[1] / "recovery_v134" /
                  "cmd" / "recovery" / "main_windows.go").read_text(encoding="utf-8")
        names = set(re.findall(r'"([a-z]+\.exe)":\s*\{\}', source))
        self.assertTrue(monitor.BROWSER_PROCS.issubset(names))
        self.assertTrue(set(browser_kill.BROWSERS).issubset(names))


if __name__ == "__main__":
    unittest.main()
