"""Recovery regression tests. No real filtering, configuration writes or email.

Run on Windows: python -m unittest discover -s tests -p 'test_recovery*.py' -v
"""
import ctypes
import os
import sys
import tempfile
import time
import unittest
import uuid
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from novablock import main, recovery, companion, single_instance, process_protect


class IsolatedTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch("requests.post", side_effect=AssertionError("Unexpected network/email")))
        self.stack.enter_context(patch.object(main.config, "save", side_effect=AssertionError("Unexpected config write")))

    def mock(self, obj, name, **kwargs):
        return self.stack.enter_context(patch.object(obj, name, **kwargs))


class HeadlessRecoveryTests(IsolatedTest):
    def setUp(self):
        super().setUp()
        self.installed = self.mock(main.config, "is_installed", return_value=True)
        self.unlocked = self.mock(main.config, "is_temp_unlocked", return_value=False)
        self.alive = self.mock(main.single_instance, "is_running", return_value=False)
        self.paused = self.mock(recovery, "recovery_paused", return_value=False)
        self.restart = self.mock(recovery, "request_app_restart", return_value=True)
        self.hosts = self.mock(main.blocker, "hosts_block_present", return_value=True)
        self.dns = self.mock(main.blocker, "dns_is_locked", return_value=True)
        self.repair = self.mock(main.blocker, "apply_full_block")
        self.mock(main.persistence, "add_startup_registry", return_value=True)
        self.mock(main.persistence, "startup_shortcut_present", return_value=True)
        self.mock(main.persistence, "add_startup_shortcut", return_value=True)
        self.mock(main.persistence, "logon_task_exists", return_value=True)
        self.heartbeat = Mock()
        self.heartbeat.exists.return_value = True
        self.heartbeat.read_text.return_value = str(int(time.time()))
        self.mock(main, "HEARTBEAT_FILE", new=self.heartbeat)

    def test_dead_app_recovers_even_when_filters_intact(self):
        main.run_watchdog_headless()
        self.restart.assert_called_once_with()
        self.repair.assert_not_called()

    def test_temp_unlock_does_not_disable_app_recovery(self):
        self.unlocked.return_value = True
        main.run_watchdog_headless()
        self.restart.assert_called_once_with()
        self.repair.assert_not_called()

    def test_filter_failure_still_attempts_recovery(self):
        self.hosts.return_value = False
        self.repair.side_effect = RuntimeError("simulated filter failure")
        with self.assertRaises(RuntimeError):
            main.run_watchdog_headless()
        self.restart.assert_called_once_with()
        self.repair.assert_called_once_with(kill_browsers=False)

    def test_missing_filters_repaired_without_killing_browsers(self):
        self.dns.return_value = False
        main.run_watchdog_headless()
        self.repair.assert_called_once_with(kill_browsers=False)
        self.restart.assert_called_once_with()

    def test_running_healthy_app_is_not_duplicated(self):
        self.alive.return_value = True
        main.run_watchdog_headless()
        self.restart.assert_not_called()
        self.repair.assert_not_called()

    def test_running_stale_app_can_get_filter_repair_but_not_duplicate(self):
        self.alive.return_value = True
        self.heartbeat.read_text.return_value = "1"
        self.hosts.return_value = False
        main.run_watchdog_headless()
        self.repair.assert_called_once_with(kill_browsers=False)
        self.restart.assert_not_called()

    def test_update_or_verified_shutdown_is_respected(self):
        self.paused.return_value = True
        main.run_watchdog_headless()
        self.restart.assert_not_called()
        self.repair.assert_not_called()

    def test_uninstalled_app_is_not_restarted(self):
        self.installed.return_value = False
        main.run_watchdog_headless()
        self.restart.assert_not_called()
        self.repair.assert_not_called()


class InteractiveTaskTests(IsolatedTest):
    def setUp(self):
        super().setUp()
        self.paused = self.mock(recovery, "recovery_paused", return_value=False)
        self.installed = self.mock(main.config, "is_installed", return_value=True)
        self.alive = self.mock(single_instance, "is_running", return_value=False)
        self.exists = self.mock(main.persistence, "logon_task_exists", return_value=True)
        self.run = self.mock(main.persistence, "_run", return_value=(0, "OK", ""))

    def test_uses_interactive_task_not_system_gui_child(self):
        self.assertTrue(recovery.request_app_restart())
        self.run.assert_called_once_with(["schtasks", "/Run", "/TN", "NovaBlockApp"], timeout=15)

    def test_race_companion_already_restarted_app(self):
        self.alive.return_value = True
        self.assertFalse(recovery.request_app_restart())
        self.run.assert_not_called()

    def test_maintenance_rechecked_before_launch(self):
        self.paused.return_value = True
        self.assertFalse(recovery.request_app_restart())
        self.run.assert_not_called()

    def test_uninstall_rechecked_before_launch(self):
        self.installed.return_value = False
        self.assertFalse(recovery.request_app_restart())
        self.run.assert_not_called()

    def test_missing_task_is_not_created_as_wrong_user(self):
        self.exists.return_value = False
        self.assertFalse(recovery.request_app_restart())
        self.run.assert_not_called()

    def test_failed_task_run_is_reported(self):
        self.run.return_value = (1, "", "failed")
        self.assertFalse(recovery.request_app_restart())


class MaintenanceTests(IsolatedTest):
    def setUp(self):
        super().setUp()
        directory = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.sentinel = Path(directory) / "shutdown.sentinel"
        self.lock = Path(directory) / "update.lock"
        self.mock(recovery, "SHUTDOWN_SENTINEL", new=self.sentinel)
        self.mock(recovery, "UPDATE_LOCK", new=self.lock)
        self.now = 100000
        self.mock(recovery.time, "time", return_value=self.now)

    def marker(self, path, text="", age=0):
        path.write_text(text, encoding="utf-8")
        os.utime(path, (self.now - age, self.now - age))

    def test_no_markers_no_pause(self):
        self.assertFalse(recovery.recovery_paused())

    def test_active_update_pauses_recovery(self):
        self.marker(self.lock, str(self.now))
        self.assertTrue(recovery.recovery_paused())
        self.assertFalse(recovery.shutdown_requested())

    def test_verified_uninstall_sentinel_pauses_recovery(self):
        self.marker(self.sentinel, str(self.now))
        self.assertTrue(recovery.shutdown_requested())

    def test_crashed_updater_lock_expires(self):
        self.marker(self.lock, str(self.now - 1801), age=1801)
        self.assertFalse(recovery.recovery_paused())
        self.assertTrue(self.lock.exists())

    def test_stale_shutdown_does_not_disable_recovery_forever(self):
        self.marker(self.sentinel, "update.bat", age=1801)
        self.assertFalse(recovery.shutdown_requested())
        self.assertTrue(self.sentinel.exists())

    def test_partial_lock_write_uses_mtime(self):
        self.marker(self.lock, "")
        self.assertTrue(recovery.update_in_progress())


class CompanionTests(IsolatedTest):
    def test_spawn_sets_independent_pyinstaller_environment(self):
        popen = self.mock(companion.subprocess, "Popen", return_value=SimpleNamespace(pid=123))
        previous = os.environ.get("PYINSTALLER_RESET_ENVIRONMENT")
        self.assertEqual(companion._spawn(["NovaBlock.exe", "--companion"]), 123)
        kwargs = popen.call_args.kwargs
        self.assertEqual(kwargs["env"]["PYINSTALLER_RESET_ENVIRONMENT"], "1")
        self.assertEqual(os.environ.get("PYINSTALLER_RESET_ENVIRONMENT"), previous)
        self.assertTrue(kwargs["close_fds"])

    def test_spawn_failure_returns_zero(self):
        self.mock(companion.subprocess, "Popen", side_effect=OSError("simulated"))
        self.assertEqual(companion._spawn(["missing.exe"]), 0)

    def test_update_prevents_companion_spawn(self):
        self.mock(recovery, "recovery_paused", return_value=True)
        spawn = self.mock(companion, "_spawn")
        self.assertEqual(companion.spawn_companion(), 0)
        spawn.assert_not_called()

    def test_pending_bootloader_prevents_spawn_storm(self):
        self.mock(recovery, "recovery_paused", return_value=False)
        self.mock(companion, "_read_pid", return_value=0)
        self.mock(companion, "_pending_companion_pid", new=321)
        self.mock(companion, "_pid_alive", side_effect=lambda pid, role="": pid == 321)
        spawn = self.mock(companion, "_spawn")
        self.assertEqual(companion.spawn_companion(), 321)
        spawn.assert_not_called()

    def test_pid_zero_is_not_alive(self):
        self.assertFalse(companion._pid_alive(0, "main"))

    def test_recycled_pid_with_wrong_executable_is_not_alive(self):
        import psutil
        proc = Mock()
        proc.is_running.return_value = True
        proc.exe.return_value = "C:\\unrelated\\other.exe"
        self.mock(psutil, "Process", return_value=proc)
        self.assertFalse(companion._pid_alive(123, "main"))


class Win32MutexTests(IsolatedTest):
    def test_native_mutex_probe_closes_all_handles(self):
        import psutil
        with patch.object(single_instance, "MUTEX_NAME", "Local\\NovaBlockTest_" + uuid.uuid4().hex):
            self.assertFalse(single_instance.is_running())
            self.assertTrue(single_instance.acquire())
            try:
                before = psutil.Process().num_handles()
                for _ in range(128):
                    self.assertTrue(single_instance.is_running())
                after = psutil.Process().num_handles()
                self.assertLessEqual(after - before, 1)
            finally:
                single_instance.release()
            self.assertFalse(single_instance.is_running())

    def test_handle_return_and_argument_signatures(self):
        from ctypes import wintypes
        kernel = single_instance._kernel32
        self.assertIs(kernel.OpenMutexW.restype, wintypes.HANDLE)
        self.assertIs(kernel.CreateMutexW.restype, wintypes.HANDLE)
        self.assertEqual(kernel.CloseHandle.argtypes, [wintypes.HANDLE])
        self.assertEqual(kernel.ReleaseMutex.argtypes, [wintypes.HANDLE])


class ProcessProtectionTests(IsolatedTest):
    def test_deny_is_first_and_original_allow_is_preserved(self):
        import win32api
        import win32security
        everyone = win32security.ConvertStringSidToSid("S-1-1-0")
        old = win32security.ACL()
        old.AddAccessAllowedAce(win32security.ACL_REVISION, 0x1FFFFF, everyone)
        sd = SimpleNamespace(GetSecurityDescriptorDacl=lambda: old)
        self.mock(win32api, "GetCurrentProcess", return_value=123)
        self.mock(win32security, "GetSecurityInfo", return_value=sd)
        setter = self.mock(win32security, "SetSecurityInfo")
        self.assertTrue(process_protect.harden_current_process())
        dacl = setter.call_args.args[5]
        self.assertEqual(dacl.GetAceCount(), 2)
        self.assertEqual(dacl.GetAce(0)[0][0], win32security.ACCESS_DENIED_ACE_TYPE)
        self.assertEqual(dacl.GetAce(0)[1], 0x0801)
        self.assertEqual(dacl.GetAce(1), old.GetAce(0))


class RegistrationTests(IsolatedTest):
    def test_tasks_are_replaced_without_delete_gap(self):
        self.mock(main, "_migrate_hosts_if_youtube_present")
        installers = [self.mock(main.persistence, name, return_value=True) for name in
                      ("install_scheduled_task", "install_logon_task", "add_startup_registry", "add_startup_shortcut")]
        delete_watchdog = self.mock(main.persistence, "remove_scheduled_task")
        delete_app = self.mock(main.persistence, "remove_logon_task")
        main.ensure_persistence()
        for installer in installers:
            installer.assert_called_once_with()
        delete_watchdog.assert_not_called()
        delete_app.assert_not_called()


if __name__ == "__main__":
    unittest.main()
