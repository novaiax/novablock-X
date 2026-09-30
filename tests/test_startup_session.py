"""Regression tests for session-aware startup. No live app is launched."""

import sys
import unittest
from contextlib import ExitStack
from unittest.mock import patch

from novablock import main as app_main


class StartupSessionTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(app_main, "setup_logging"))
        self.stack.enter_context(patch.object(app_main, "secure_program_data", return_value=0))

    def mock(self, obj, name, **kwargs):
        return self.stack.enter_context(patch.object(obj, name, **kwargs))

    def test_legacy_service_mode_only_runs_headless_repair(self):
        self.mock(sys, "argv", new=["NovaBlock.exe", "--service-run"])
        self.mock(app_main, "is_admin", return_value=True)
        headless = self.mock(app_main, "run_watchdog_headless")
        session = self.mock(app_main, "current_session_id")
        self.assertEqual(app_main.main(), 0)
        headless.assert_called_once_with()
        session.assert_not_called()

    def test_plain_launch_in_session_zero_never_starts_ui(self):
        self.mock(sys, "argv", new=["NovaBlock.exe"])
        self.mock(app_main, "current_session_id", return_value=0)
        self.mock(app_main, "is_admin", return_value=True)
        headless = self.mock(app_main, "run_watchdog_headless")
        ui = self.mock(app_main, "run_app")
        self.assertEqual(app_main.main(), 0)
        headless.assert_called_once_with()
        ui.assert_not_called()

    def test_plain_launch_in_interactive_session_starts_ui(self):
        self.mock(sys, "argv", new=["NovaBlock.exe"])
        self.mock(app_main, "current_session_id", return_value=1)
        self.mock(app_main, "is_admin", return_value=True)
        self.mock(app_main.config, "is_installed", return_value=True)
        self.mock(app_main.config, "ensure_default_popup_sites", return_value=0)
        self.mock(app_main.recovery, "shutdown_requested", return_value=False)
        self.mock(app_main.single_instance, "acquire", return_value=True)
        release = self.mock(app_main.single_instance, "release")
        ui = self.mock(app_main, "run_app")
        self.assertEqual(app_main.main(), 0)
        ui.assert_called_once_with()
        release.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
