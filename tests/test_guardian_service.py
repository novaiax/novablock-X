"""Regression tests for the v1.0.35 LocalSystem guardian.

The guardian is intentionally process-recovery only. If network filtering ever
creeps into this module, these tests must fail before a Windows release builds.
"""
import ast
import inspect
import unittest
from unittest.mock import patch

from novablock import config, persistence, process_protect, recovery, service


class GuardianIsolationTests(unittest.TestCase):
    def test_guardian_has_no_network_filter_imports_or_calls(self):
        source = inspect.getsource(service)
        tree = ast.parse(source)

        forbidden_modules = {"blocker", "firewall", "browser_policies"}
        forbidden_calls = {
            "apply_full_block",
            "set_family_dns",
            "reset_dns",
            "block_doh_endpoints",
            "apply_all_browser_policies",
        }

        imported = set()
        called = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[-1] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.add(node.module.split(".")[-1])
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    called.add(func.id)
                elif isinstance(func, ast.Attribute):
                    called.add(func.attr)

        self.assertTrue(forbidden_modules.isdisjoint(imported), imported)
        self.assertTrue(forbidden_calls.isdisjoint(called), called)

    def test_guardian_name_is_distinct_from_retired_v134_service(self):
        self.assertEqual(service.SERVICE_NAME, "NovaBlockGuardian")
        self.assertEqual(persistence._LEGACY_SERVICE_NAME, "NovaBlockService")
        self.assertNotEqual(service.SERVICE_NAME, persistence._LEGACY_SERVICE_NAME)


class GuardianLoopTests(unittest.TestCase):
    def test_missing_main_requests_interactive_relaunch(self):
        with patch.object(service, "HAS_WIN32_SERVICE", False), \
             patch.object(service, "_read_pid", return_value=0), \
             patch.object(service, "_main_alive", return_value=False), \
             patch.object(service, "_request_main_restart", return_value=True) as restart, \
             patch.object(service.time, "monotonic", return_value=10.0), \
             patch.object(service.time, "sleep"), \
             patch.object(config, "is_installed", return_value=True), \
             patch.object(recovery, "update_in_progress", return_value=False), \
             patch.object(recovery, "shutdown_requested", side_effect=[False, True]), \
             patch.object(process_protect, "harden_current_process", return_value=True):
            service._service_loop(None)

        restart.assert_called_once_with()

    def test_update_pauses_relaunch(self):
        with patch.object(service, "HAS_WIN32_SERVICE", False), \
             patch.object(service, "_request_main_restart") as restart, \
             patch.object(service.time, "sleep"), \
             patch.object(config, "is_installed", return_value=True), \
             patch.object(recovery, "update_in_progress", return_value=True), \
             patch.object(recovery, "shutdown_requested", side_effect=[False, True]), \
             patch.object(process_protect, "harden_current_process", return_value=True):
            service._service_loop(None)

        restart.assert_not_called()


class GuardianMigrationTests(unittest.TestCase):
    def test_remove_service_cleans_guardian_and_legacy_v134(self):
        with patch.object(persistence, "_remove_service_name", return_value=True) as remove:
            self.assertTrue(persistence.remove_service())

        self.assertEqual(
            [call.args[0] for call in remove.call_args_list],
            ["NovaBlockGuardian", "NovaBlockService"],
        )

    def test_install_attempts_legacy_cleanup_before_guardian_setup(self):
        events = []

        def legacy_cleanup():
            events.append("legacy")
            return True

        def exists(name):
            events.append(f"exists:{name}")
            return False

        def run(cmd, timeout=30):
            events.append("run:" + " ".join(cmd[:3]))
            return 0, "", ""

        with patch.object(persistence, "remove_legacy_service", side_effect=legacy_cleanup), \
             patch.object(persistence, "_service_exists_name", side_effect=exists), \
             patch.object(persistence, "_run", side_effect=run), \
             patch.object(persistence, "_apply_service_dacl", return_value=True):
            self.assertTrue(persistence.install_service())

        self.assertEqual(events[0], "legacy")
        self.assertIn("exists:NovaBlockGuardian", events)


if __name__ == "__main__":
    unittest.main()
