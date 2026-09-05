import unittest
from unittest.mock import patch

from novablock.monitor import WindowMonitor


class CustomPopupTriggerTests(unittest.TestCase):
    def make_monitor(self, domains=None, urls=None):
        m = WindowMonitor(lambda *_: None, poll_interval=1.0)
        with patch("novablock.config.get_popup_domains", return_value=domains or []), \
             patch("novablock.config.get_popup_urls", return_value=urls or []):
            m._custom_cache_until = 0
            m._reload_custom_config()
        return m

    def test_poll_interval_is_capped_at_100ms(self):
        self.assertLessEqual(WindowMonitor(lambda *_: None, poll_interval=1.0).poll_interval, 0.10)

    def test_custom_domain_name_in_title_does_not_trigger(self):
        m = self.make_monitor(domains=["instagram.com"])
        self.assertIsNone(m._check_title("Instagram • Photos et vidéos"))
        self.assertIsNone(m._check_title("instagram.com - résultat de recherche"))

    def test_custom_precise_url_name_in_title_does_not_trigger(self):
        m = self.make_monitor(urls=["https://tiktok.com/@foo/video/123"])
        self.assertIsNone(m._check_title("TikTok - Make Your Day"))

    def test_generic_pro_word_never_triggers(self):
        m = self.make_monitor(domains=["example.pro"])
        self.assertIsNone(m._check_title("Version Pro - Documentation"))
        self.assertIsNone(m._check_title("pro - Recherche Google"))

    def test_custom_x_name_in_title_does_not_trigger(self):
        m = self.make_monitor(domains=["x.com"])
        self.assertIsNone(m._check_title("Home / X"))

    def test_real_adult_title_detection_is_unchanged(self):
        m = self.make_monitor(domains=["instagram.com"])
        self.assertEqual(m._check_title("Pornhub - Videos"), "porn")
        self.assertEqual(m._check_title("NSFW discussion"), "nsfw")


if __name__ == "__main__":
    unittest.main()
