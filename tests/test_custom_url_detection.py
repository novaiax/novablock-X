import unittest
from unittest.mock import patch

from novablock.monitor import WindowMonitor


class CustomUrlDetectionTests(unittest.TestCase):
    def make_monitor(self, domains=None, urls=None):
        monitor = WindowMonitor(lambda *_: None, poll_interval=1.0)
        with patch("novablock.config.get_popup_domains", return_value=domains or []), \
             patch("novablock.config.get_popup_urls", return_value=urls or []):
            monitor._custom_cache_until = 0
            monitor._reload_custom_config()
        return monitor

    def test_domain_matches_real_url_even_when_title_is_unrelated(self):
        m = self.make_monitor(domains=["instagram.com"])
        self.assertEqual(m._match_custom_url("https://www.instagram.com/reels/abc"), "instagram.com")
        self.assertIsNone(m._check_title("Photos de vacances"))

    def test_subdomain_matches_configured_domain(self):
        m = self.make_monitor(domains=["example.com"])
        self.assertEqual(m._match_custom_url("https://sub.example.com/path"), "example.com")

    def test_precise_url_matches_page_and_descendant(self):
        m = self.make_monitor(urls=["https://example.com/private/page"])
        self.assertEqual(m._match_custom_url("https://example.com/private/page"), "example.com/private/page")
        self.assertEqual(m._match_custom_url("https://example.com/private/page/child"), "example.com/private/page")
        self.assertIsNone(m._match_custom_url("https://example.com/other"))

    def test_unrelated_domain_does_not_match(self):
        m = self.make_monitor(domains=["instagram.com"])
        self.assertIsNone(m._match_custom_url("https://example.com/instagram-guide"))

    def test_typing_in_address_bar_is_not_navigation(self):
        m = self.make_monitor(domains=["instagram.com"])
        with patch.object(m, "_read_address_bar", return_value=("https://instagram.com", True)):
            self.assertIsNone(m._match_committed_custom_navigation(123))

    def test_committed_navigation_triggers_immediately(self):
        m = self.make_monitor(domains=["instagram.com"])
        with patch.object(m, "_read_address_bar", return_value=("https://instagram.com", False)):
            self.assertEqual(m._match_committed_custom_navigation(123), "instagram.com")

    def test_poll_interval_stays_near_instant(self):
        self.assertLessEqual(WindowMonitor(lambda *_: None, poll_interval=1.0).poll_interval, 0.10)


if __name__ == "__main__":
    unittest.main()
