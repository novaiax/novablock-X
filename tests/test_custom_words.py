import unittest
from unittest.mock import patch

from novablock import config
from novablock.monitor import WindowMonitor


class CustomWordDetectionTests(unittest.TestCase):
    def make_monitor(self, words=None):
        monitor = WindowMonitor(lambda *_: None, poll_interval=1.0)
        with patch("novablock.config.get_popup_domains", return_value=[]), \
             patch("novablock.config.get_popup_urls", return_value=[]), \
             patch("novablock.config.get_popup_words", return_value=words or []):
            monitor._custom_cache_until = 0
            monitor._reload_custom_config()
        return monitor

    def test_exact_word_matches_standalone_only(self):
        m = self.make_monitor(["pro"])
        self.assertEqual(m._match_custom_word("version PRO disponible"), "pro")
        self.assertIsNone(m._match_custom_word("professional"))
        self.assertIsNone(m._match_custom_word("programme"))
        self.assertIsNone(m._match_custom_word("approche"))

    def test_phrase_is_case_insensitive_and_whitespace_tolerant(self):
        m = self.make_monitor(["social media"])
        self.assertEqual(m._match_custom_word("SOCIAL   MEDIA aujourd'hui"), "social media")
        self.assertIsNone(m._match_custom_word("social mediabox"))

    def test_title_can_trigger_custom_word(self):
        m = self.make_monitor(["casino"])
        with patch.object(m, "_read_focused_edit_texts", return_value=()), \
             patch.object(m, "_read_address_bar", return_value=("https://example.com", False)):
            self.assertEqual(m._match_custom_word_sources(123, "Casino - résultat"), "casino")

    def test_focused_browser_input_triggers_while_typing(self):
        m = self.make_monitor(["casino"])
        with patch.object(m, "_read_focused_edit_texts", return_value=("je cherche casino",)), \
             patch.object(m, "_read_address_bar", return_value=("", True)):
            self.assertEqual(m._match_custom_word_sources(123, "Nouvel onglet"), "casino")

    def test_active_url_can_trigger_custom_word(self):
        m = self.make_monitor(["casino"])
        with patch.object(m, "_read_focused_edit_texts", return_value=()), \
             patch.object(m, "_read_address_bar", return_value=("https://example.com/casino/offres", False)):
            self.assertEqual(m._match_custom_word_sources(123, "Example"), "casino")

    def test_config_normalizes_and_deduplicates_words(self):
        cfg = {"custom_popup_words": ["Pro"]}
        with patch("novablock.config.load", return_value=cfg), \
             patch("novablock.config.save") as save:
            self.assertEqual(config.add_custom_word("  PRO  "), "pro")
            self.assertEqual(cfg["custom_popup_words"], ["pro"])
            save.assert_called_once()

    def test_config_removal_is_supported(self):
        cfg = {"custom_popup_words": ["pro", "casino"]}
        with patch("novablock.config.load", return_value=cfg), \
             patch("novablock.config.save") as save:
            self.assertTrue(config.remove_custom_word("CASINO"))
            self.assertEqual(cfg["custom_popup_words"], ["pro"])
            save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
