import unittest
from unittest.mock import patch

from novablock import config
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

    def test_every_default_popup_domain_matches_a_committed_navigation(self):
        self.assertEqual(len(config.DEFAULT_POPUP_DOMAINS), 17)
        m = self.make_monitor(domains=list(config.DEFAULT_POPUP_DOMAINS))
        for domain in config.DEFAULT_POPUP_DOMAINS:
            with self.subTest(domain=domain):
                self.assertEqual(m._match_custom_url(f"https://{domain}/page"), domain)
        self.assertIsNone(m._match_custom_url("https://www.reddit.com/r/example"))

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

    def test_unknown_browser_with_labelled_address_bar_is_monitored(self):
        m = self.make_monitor(domains=["duckduckgo.com"])
        detections = []
        m.on_detect = lambda title, hit, hwnd: (detections.append((hit, hwnd)), m.stop())
        with patch("novablock.monitor.win32gui.GetForegroundWindow", return_value=321), \
             patch("novablock.monitor.win32gui.GetWindowText", return_value="Search"), \
             patch("novablock.monitor.win32process.GetWindowThreadProcessId", return_value=(0, 42)), \
             patch.object(m, "_is_uc_browser", return_value=False), \
             patch.object(m, "_is_browser", return_value=False), \
             patch.object(m, "_read_address_bar", return_value=("https://duckduckgo.com", False)) as read:
            m._loop()
        self.assertEqual(detections, [("duckduckgo.com", 321)])
        read.assert_called_once_with(321, require_hint=True)

    def test_unknown_app_without_labelled_address_does_not_trigger(self):
        m = self.make_monitor(domains=["duckduckgo.com"])
        detections = []
        m.on_detect = lambda *_args: detections.append(True)
        def stop_after_one_tick(_seconds):
            m._stop.set()
            return True
        with patch("novablock.monitor.win32gui.GetForegroundWindow", return_value=321), \
             patch("novablock.monitor.win32gui.GetWindowText", return_value="duckduckgo.com mentioned"), \
             patch("novablock.monitor.win32process.GetWindowThreadProcessId", return_value=(0, 42)), \
             patch.object(m, "_is_uc_browser", return_value=False), \
             patch.object(m, "_is_browser", return_value=False), \
             patch.object(m, "_read_address_bar", return_value=("", False)), \
             patch.object(m._stop, "wait", side_effect=stop_after_one_tick):
            m._loop()
        self.assertEqual(detections, [])

    def test_one_popup_does_not_create_a_global_gap_for_another_window(self):
        m = self.make_monitor(domains=["duckduckgo.com"])
        detections = []
        m.on_detect = lambda _title, hit, hwnd: detections.append((hit, hwnd))
        windows = iter((101, 202, 0))
        with patch("novablock.monitor.win32gui.GetForegroundWindow",
                   side_effect=lambda: next(windows, 0)), \
             patch("novablock.monitor.win32gui.GetWindowText", return_value="Search"), \
             patch("novablock.monitor.win32process.GetWindowThreadProcessId", return_value=(0, 42)), \
             patch.object(m, "_is_uc_browser", return_value=False), \
             patch.object(m, "_is_browser", return_value=True), \
             patch.object(m, "_match_committed_custom_navigation",
                          return_value="duckduckgo.com"):
            ticks = 0
            def stop_after_two(_seconds):
                nonlocal ticks
                ticks += 1
                if ticks >= 2:
                    m._stop.set()
                return m._stop.is_set()
            with patch.object(m._stop, "wait", side_effect=stop_after_two):
                m._loop()
        self.assertEqual(detections, [
            ("duckduckgo.com", 101), ("duckduckgo.com", 202),
        ])

    def test_long_running_monitor_drops_expired_window_and_process_cache(self):
        m = self.make_monitor(domains=["duckduckgo.com"])
        m._browser_cache = {1: (9.0, False), 2: (11.0, True)}
        m._address_cache = {(1, False): (9.0, "", False),
                            (2, True): (11.0, "https://duckduckgo.com", False)}
        m._unknown_probe = {1: (-60.0, "old"), 2: (11.0, "new")}
        m._prune_caches(10.0)
        self.assertEqual(set(m._browser_cache), {2})
        self.assertEqual(set(m._address_cache), {(2, True)})
        self.assertEqual(set(m._unknown_probe), {2})


if __name__ == "__main__":
    unittest.main()
