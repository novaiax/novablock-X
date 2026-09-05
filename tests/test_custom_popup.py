import unittest
from unittest.mock import patch

from novablock.monitor import WindowMonitor


class CustomPopupTriggerTests(unittest.TestCase):
    def make_monitor(self, domains=None, urls=None):
        m = WindowMonitor(lambda *_: None, poll_interval=1.0)
        cfg = {
            "custom_blocked_domains": domains or [],
            "custom_blocked_urls": urls or [],
        }
        with patch("novablock.config.load", return_value=cfg):
            m._custom_cache_until = 0
            m._reload_custom_tokens()
        return m

    def test_poll_interval_is_capped_at_100ms(self):
        self.assertLessEqual(WindowMonitor(lambda *_: None, poll_interval=1.0).poll_interval, 0.10)

    def test_custom_domain_brand_in_title_triggers(self):
        m = self.make_monitor(domains=["instagram.com"])
        self.assertEqual(m._check_title("Instagram • Photos et vidéos"), "instagram")

    def test_custom_url_host_triggers(self):
        m = self.make_monitor(urls=["https://tiktok.com/@foo/video/123"])
        self.assertEqual(m._check_title("TikTok - Make Your Day"), "tiktok")

    def test_unrelated_title_does_not_trigger_custom_site(self):
        m = self.make_monitor(domains=["instagram.com"])
        self.assertIsNone(m._check_title("Documentation Python"))

    def test_x_dot_com_special_case(self):
        m = self.make_monitor(domains=["x.com"])
        self.assertEqual(m._check_title("Home / X"), "x.com")

    def test_config_can_be_reloaded_without_restart(self):
        m = WindowMonitor(lambda *_: None, poll_interval=1.0)
        with patch("novablock.config.load", return_value={"custom_blocked_domains": ["reddit.com"], "custom_blocked_urls": []}):
            m._custom_cache_until = 0
            self.assertEqual(m._check_title("Reddit - Dive into anything"), "reddit")


if __name__ == "__main__":
    unittest.main()
