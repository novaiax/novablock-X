import unittest
import json
from unittest.mock import patch

from novablock import config
from novablock.custom_status import StatusWindow


class CustomPopupConfigTests(unittest.TestCase):
    def test_fresh_install_starts_with_requested_popup_sites_without_reddit(self):
        expected = {
            "botinok.porn", "domporno.me", "seksvideo.tv", "top-xxx.pro",
            "sexm.xxx", "nudevista.tv", "pornoopa.com", "ru.mylust.com",
            "ru.anysex.com", "myhomemadesex.com", "pornorussia.mobi",
            "vk.ru", "hqfukc.com", "xxxfilm.pro", "porn4e.com",
            "duckduckgo.com", "ucweb.com",
        }
        class MissingConfig:
            def exists(self):
                return False

        with patch.object(config, "CONFIG_FILE", MissingConfig()), \
             patch.object(config, "_prior_install_present", return_value=False):
            fresh = config.load()
            self.assertEqual(set(fresh["custom_popup_domains"]), expected)
            self.assertEqual(len(fresh["custom_popup_domains"]), 17)
            self.assertNotIn("reddit.com", fresh["custom_popup_domains"])
            self.assertTrue(fresh["default_popup_sites_seeded"])
            fresh["custom_popup_domains"].append("example.com")
            self.assertEqual(set(config.load()["custom_popup_domains"]), expected)

    def test_existing_install_does_not_gain_new_defaults(self):
        class ExistingConfig:
            def exists(self):
                return True

            def read_bytes(self):
                return b"encrypted"

        stored = {"custom_popup_domains": [], "code_hash": "existing", "install_ts": 1}
        with patch.object(config, "CONFIG_FILE", ExistingConfig()), \
             patch.object(config, "decrypt_machine", return_value=json.dumps(stored).encode()):
            self.assertEqual(config.load()["custom_popup_domains"], [])

    def test_update_adds_missing_defaults_once_and_keeps_existing_sites(self):
        existing = {
            "code_hash": "installed", "install_ts": 1,
            "custom_popup_domains": ["example.org", config.DEFAULT_POPUP_DOMAINS[0]],
            "custom_popup_urls": ["https://example.org/path"],
            "default_popup_sites_seeded": False,
        }
        with patch.object(config, "load", return_value=existing), \
             patch.object(config, "save") as save:
            self.assertEqual(config.ensure_default_popup_sites(), 16)
            self.assertEqual(config.ensure_default_popup_sites(), 0)
            save.assert_called_once_with(existing)
        self.assertEqual(len(existing["custom_popup_domains"]), 18)
        self.assertIn("example.org", existing["custom_popup_domains"])
        self.assertEqual(existing["custom_popup_urls"], ["https://example.org/path"])
        self.assertTrue(existing["default_popup_sites_seeded"])
        existing["custom_popup_domains"].remove(config.DEFAULT_POPUP_DOMAINS[0])
        with patch.object(config, "load", return_value=existing), patch.object(config, "save") as save:
            self.assertEqual(config.ensure_default_popup_sites(), 0)
            save.assert_not_called()

    def test_movix_cash_cannot_be_added(self):
        self.assertEqual(config.add_custom_domain("movix.cash"), "")
        self.assertEqual(config.add_custom_domain("www.movix.cash"), "")
        self.assertEqual(config.add_custom_url("https://movix.cash/movie/test"), "")

    def test_migration_removes_movix_and_clears_legacy_network_lists(self):
        legacy = {
            "custom_blocked_domains": ["instagram.com", "movix.cash"],
            "custom_blocked_urls": [
                "https://tiktok.com/@foo",
                "https://movix.cash/movie/abc",
            ],
            "custom_popup_domains": [],
            "custom_popup_urls": [],
            "custom_popup_only_migrated": False,
        }
        with patch.object(config, "load", return_value=legacy), \
             patch.object(config, "save") as save:
            self.assertTrue(config.migrate_custom_sites_to_popup_only())
            written = save.call_args.args[0]
        self.assertEqual(written["custom_popup_domains"], ["instagram.com"])
        self.assertEqual(written["custom_popup_urls"], ["https://tiktok.com/@foo"])
        self.assertEqual(written["custom_blocked_domains"], [])
        self.assertEqual(written["custom_blocked_urls"], [])
        self.assertTrue(written["custom_popup_only_migrated"])

    def test_network_layers_never_receive_popup_sites(self):
        self.assertEqual(config.get_custom_domains(), [])
        self.assertEqual(config.get_custom_urls(), [])

    def test_popup_getters_filter_movix_even_before_migration(self):
        legacy = {
            "custom_blocked_domains": ["movix.cash", "instagram.com"],
            "custom_blocked_urls": ["https://movix.cash/a", "https://example.com/private"],
            "custom_popup_domains": [],
            "custom_popup_urls": [],
        }
        with patch.object(config, "load", return_value=legacy):
            self.assertEqual(config.get_popup_domains(), ["instagram.com"])
            self.assertEqual(config.get_popup_urls(), ["https://example.com/private"])

    def test_main_window_has_one_fixed_compact_size(self):
        self.assertEqual(StatusWindow.WIDTH, 620)
        self.assertEqual(StatusWindow.HEIGHT, 700)


if __name__ == "__main__":
    unittest.main()
