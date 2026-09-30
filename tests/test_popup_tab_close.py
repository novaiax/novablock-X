import unittest
from unittest.mock import patch

from novablock import tab_close
from novablock.popup import BlockedPopup


class _FakeRoot:
    def __init__(self):
        self.withdrawn = False
        self.destroyed = False
        self.updated = False
        self.visible = False
        self.scheduled = []

    def withdraw(self):
        self.withdrawn = True

    def update_idletasks(self):
        self.updated = True

    def destroy(self):
        self.destroyed = True

    def deiconify(self):
        self.visible = True

    def lift(self):
        pass

    def attributes(self, *_args):
        pass

    def after(self, _delay, callback):
        self.scheduled.append(callback)


class _FakeFeedback:
    def __init__(self):
        self.text = ""

    def config(self, *, text):
        self.text = text


class PopupTabCloseTests(unittest.TestCase):
    def test_popup_appearance_does_not_close_any_tab(self):
        popup = BlockedPopup.__new__(BlockedPopup)
        with patch("novablock.popup.tab_close.close_one_tab") as close_one:
            popup._auto_close_browser_tab()
        close_one.assert_not_called()

    def test_close_button_targets_triggering_window_once(self):
        popup = BlockedPopup.__new__(BlockedPopup)
        popup.target_hwnd = 424242
        popup.detected_title = "Blocked page"
        popup.root = _FakeRoot()
        popup.feedback = _FakeFeedback()

        with patch("novablock.popup.tab_close.close_one_tab", return_value=True) as close_one, \
             patch("win32gui.IsWindow", return_value=False):
            popup._close_triggering_tab_and_popup()
            self.assertFalse(popup.root.destroyed)
            popup.root.scheduled.pop(0)()

        close_one.assert_called_once_with(424242)
        self.assertTrue(popup.root.withdrawn)
        self.assertTrue(popup.root.updated)
        self.assertTrue(popup.root.visible)
        self.assertTrue(popup.root.destroyed)

    def test_failed_close_keeps_the_blocking_popup(self):
        popup = BlockedPopup.__new__(BlockedPopup)
        popup.target_hwnd = 424242
        popup.detected_title = "Blocked page"
        popup.root = _FakeRoot()
        popup.feedback = _FakeFeedback()
        with patch("novablock.popup.tab_close.close_one_tab", return_value=False):
            popup._close_triggering_tab_and_popup()
        self.assertTrue(popup.root.visible)
        self.assertFalse(popup.root.destroyed)
        self.assertIn("Réessaie", popup.feedback.text)

    def test_unchanged_browser_title_keeps_the_popup(self):
        popup = BlockedPopup.__new__(BlockedPopup)
        popup.target_hwnd = 424242
        popup.detected_title = "Blocked page"
        popup.root = _FakeRoot()
        popup.feedback = _FakeFeedback()
        with patch("win32gui.IsWindow", return_value=True), \
             patch("win32gui.GetWindowText", return_value="Blocked page"):
            popup._confirm_tab_closed(12)
        self.assertFalse(popup.root.destroyed)
        self.assertIn("encore ouvert", popup.feedback.text)

    def test_followup_never_kills_browser(self):
        popup = BlockedPopup.__new__(BlockedPopup)
        self.assertIsNone(popup._followup_kill())

if __name__ == "__main__":
    unittest.main()
