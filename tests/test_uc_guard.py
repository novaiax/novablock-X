"""UC Browser cannot be used as an unmonitored browser."""

import unittest
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


if __name__ == "__main__":
    unittest.main()
