import unittest
from unittest.mock import patch

from novablock import config
from novablock.custom_status import StatusWindow


class CustomPopupConfigTests(unittest.TestCase):
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
