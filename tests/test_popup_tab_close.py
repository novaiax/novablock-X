import unittest
from unittest.mock import patch

from novablock.popup import BlockedPopup


class _FakeRoot:
    def __init__(self):
        self.withdrawn = False
        self.destroyed = False
        self.updated = False

    def withdraw(self):
        self.withdrawn = True

    def update_idletasks(self):
        self.updated = True

    def destroy(self):
        self.destroyed = True


class PopupTabCloseTests(unittest.TestCase):
    def test_popup_appearance_does_not_close_any_tab(self):
        popup = BlockedPopup.__new__(BlockedPopup)
        with patch("novablock.popup.tab_close.close_one_tab") as close_one:
            popup._auto_close_browser_tab()
        close_one.assert_not_called()

    def test_close_button_targets_triggering_window_once(self):
        popup = BlockedPopup.__new__(BlockedPopup)
        popup.target_hwnd = 424242
        popup.root = _FakeRoot()

        with patch("novablock.popup.tab_close.close_one_tab", return_value=True) as close_one:
            popup._close_triggering_tab_and_popup()

        close_one.assert_called_once_with(424242)
        self.assertTrue(popup.root.withdrawn)
        self.assertTrue(popup.root.updated)
        self.assertTrue(popup.root.destroyed)

    def test_followup_never_kills_browser(self):
        popup = BlockedPopup.__new__(BlockedPopup)
        self.assertIsNone(popup._followup_kill())


if __name__ == "__main__":
    unittest.main()
