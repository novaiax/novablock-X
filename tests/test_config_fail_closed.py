"""A damaged installed config must never become a fresh setup."""

import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from novablock import config, crypto


class _ExistingConfig:
    def exists(self):
        return True

    def read_bytes(self):
        return b"damaged encrypted data"


class _MissingConfig:
    def exists(self):
        return False


class ConfigFailClosedTests(unittest.TestCase):
    def test_corruption_keeps_filter_installed_and_rejects_changes(self):
        with patch.object(config, "CONFIG_FILE", _ExistingConfig()), \
             patch.object(config, "decrypt_machine", side_effect=ValueError("corrupt")):
            fallback = config.load()
            self.assertTrue(config.is_installed())
            self.assertTrue(fallback["_config_unreadable"])
            self.assertEqual(len(config.get_popup_domains()), 17)
            self.assertFalse(crypto.verify_code("ANY CODE", fallback["code_hash"]))
            self.assertFalse(config.needs_code_rotation())
            with self.assertRaises(RuntimeError):
                config.save(fallback)

    def test_missing_config_with_persistence_is_not_new_install(self):
        with patch.object(config, "CONFIG_FILE", _MissingConfig()), \
             patch.object(config, "_prior_install_present", return_value=True):
            self.assertTrue(config.is_installed())
            self.assertTrue(config.load()["_config_unreadable"])

    def test_missing_config_without_persistence_is_fresh_install(self):
        with patch.object(config, "CONFIG_FILE", _MissingConfig()), \
             patch.object(config, "_prior_install_present", return_value=False):
            self.assertFalse(config.is_installed())
            self.assertEqual(len(config.load()["custom_popup_domains"]), 17)

    def test_existing_blocklist_survives_deleted_config_and_quarantined_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "blocklist.txt").write_text("existing blocklist", encoding="utf-8")
            with patch.object(config, "PROGRAM_DATA", root), \
                 patch.object(config, "CONFIG_FILE", _MissingConfig()):
                self.assertTrue(config._prior_install_present())
                self.assertTrue(config.load()["_config_unreadable"])

    def test_hosts_marker_identifies_prior_install_if_other_files_are_gone(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            hosts = root / "hosts"
            hosts.write_text(config.BLOCK_MARKER_START, encoding="utf-8")
            with patch.object(config, "PROGRAM_DATA", root), \
                 patch.object(config, "WINDOWS_HOSTS", hosts), \
                 patch("winreg.OpenKey", side_effect=FileNotFoundError()), \
                 patch.object(config.subprocess, "run", return_value=SimpleNamespace(returncode=1)):
                self.assertTrue(config._prior_install_present())


if __name__ == "__main__":
    unittest.main()
