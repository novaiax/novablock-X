"""NovaBlock popup variant with safe, explicit one-tab dismissal."""
import threading
import tkinter as tk

from .gui import (
    BlockedPopup as BaseBlockedPopup,
    PRIMARY, ACCENT, MUTED, FONT_MD, FONT_SM,
)
from . import tab_close


class BlockedPopup(BaseBlockedPopup):
    """Popup that closes only the triggering tab when the user dismisses it.

    Unlike the legacy popup, this class does not send Ctrl+W at popup creation
    and never kills the whole browser as a fallback.
    """

    @classmethod
    def set_parent_root(cls, root: tk.Tk) -> None:
        cls._parent_root = root

    def _auto_close_browser_tab(self) -> None:
        # Intentionally disabled. The user asked for the tab to close only
        # after clicking the explicit Fermer button.
        return

    def _followup_kill(self) -> None:
        # Never terminate the browser process. A failure to close one tab must
        # not destroy all Chrome/Edge/Firefox windows and tabs.
        return

    def _on_destroy(self, event=None) -> None:
        if event is not None and event.widget is not self.root:
            return
        type(self)._active = None

    def _close_triggering_tab_and_popup(self) -> None:
        """Close exactly the tab active in the browser HWND that triggered us."""
        # Hide the topmost popup first so Windows can make the browser the
        # foreground keyboard target. Keep the Tk object alive until Ctrl+W
        # has been sent.
        try:
            self.root.withdraw()
            self.root.update_idletasks()
        except Exception:
            pass
        try:
            tab_close.close_one_tab(self.target_hwnd)
        finally:
            try:
                self.root.destroy()
            except Exception:
                pass

    def _build(self) -> None:
        wrap = tk.Frame(self.root, bg=PRIMARY)
        wrap.pack(expand=True)
        card = tk.Frame(wrap, bg="white", padx=48, pady=40)
        card.pack(padx=40, pady=40)
        tk.Label(card, text="🚫", font=("Segoe UI", 72), bg="white", fg=PRIMARY).pack()
        tk.Label(card, text="Contenu bloqué", font=("Segoe UI", 28, "bold"),
                 fg=PRIMARY, bg="white").pack(pady=(0, 8))
        tk.Label(card,
                 text=f"Détection : « {self.keyword} »",
                 font=FONT_SM, fg=MUTED, bg="white").pack(pady=(0, 16))
        tk.Label(card,
                 text=("Pour débloquer, demande à ton ami le code de 25 caractères\n"
                       "qu'il a reçu par email."),
                 font=FONT_MD, fg=ACCENT, bg="white", justify="center").pack(pady=(0, 24))

        btns = tk.Frame(card, bg="white")
        btns.pack(pady=(8, 0))
        tk.Button(btns, text="Demander le code à mon ami", font=FONT_MD,
                  bg=PRIMARY, fg="white", relief="flat", padx=20, pady=10,
                  command=self._request_email).grid(row=0, column=0, padx=4)
        tk.Button(btns, text="J'ai le code", font=FONT_MD,
                  bg="#fdcb6e", fg=ACCENT, relief="flat", padx=20, pady=10,
                  command=self._enter_code).grid(row=0, column=1, padx=4)
        tk.Button(btns, text="Fermer l'onglet", font=FONT_SM,
                  bg="#dfe6e9", fg=ACCENT, relief="flat", padx=14, pady=8,
                  command=self._close_triggering_tab_and_popup).grid(row=0, column=2, padx=4)

        self.feedback = tk.Label(card, text="", font=FONT_SM, fg=MUTED,
                                 bg="white", wraplength=480)
        self.feedback.pack(pady=(20, 0))
