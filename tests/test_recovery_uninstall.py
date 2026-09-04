"""Ensure recovery changes do not bypass the existing uninstall gate."""
import unittest
from unittest.mock import Mock, patch

from novablock import main, gui


class UninstallGuardTests(unittest.TestCase):
    def test_no_cooldown_refuses_uninstall_without_side_effects(self):
        with patch.object(main.config, "is_installed", return_value=True), \
             patch.object(main.config, "uninstall_cooldown_remaining", return_value=-1), \
             patch.object(main.ctypes.windll.user32, "MessageBoxW"), \
             patch.object(main.blocker, "remove_full_block") as remove, \
             patch("requests.post", side_effect=AssertionError("Unexpected email")):
            self.assertEqual(main.run_uninstall_check(), 1)
            remove.assert_not_called()

    def test_active_cooldown_refuses_uninstall(self):
        with patch.object(main.config, "is_installed", return_value=True), \
             patch.object(main.config, "uninstall_cooldown_remaining", return_value=3600), \
             patch.object(main.ctypes.windll.user32, "MessageBoxW"), \
             patch.object(main.blocker, "remove_full_block") as remove:
            self.assertEqual(main.run_uninstall_check(), 1)
            remove.assert_not_called()

    def test_expired_cooldown_still_requires_valid_code(self):
        root = Mock()
        dialog = Mock(result="wrong-code")
        with patch.object(main.config, "is_installed", return_value=True), \
             patch.object(main.config, "uninstall_cooldown_remaining", return_value=0), \
             patch.object(main.config, "load", return_value={"code_hash": "stored"}), \
             patch("tkinter.Tk", return_value=root), \
             patch.object(gui, "CodeDialog", return_value=dialog), \
             patch("novablock.crypto.verify_code", return_value=False), \
             patch.object(main.ctypes.windll.user32, "MessageBoxW"), \
             patch.object(main.blocker, "remove_full_block") as remove, \
             patch.object(main.persistence, "remove_scheduled_task") as remove_task:
            self.assertEqual(main.run_uninstall_check(), 1)
            remove.assert_not_called()
            remove_task.assert_not_called()


if __name__ == "__main__":
    unittest.main()
