"""Extended main status window with explicit custom-site visibility.

This is intentionally separate from gui.py so the long-standing setup/unlock
UI remains untouched. The panel reads config.dat directly on every refresh,
which makes it a simple truth display for what NovaBlock will monitor.
"""
import tkinter as tk

from . import config
from .gui import StatusWindow as BaseStatusWindow, BG, ACCENT, MUTED, FONT_MD, FONT_SM, _center
from .monitor import HAS_UIA


class StatusWindow(BaseStatusWindow):
    """Main window plus a live list of user-configured popup triggers."""

    def _build(self) -> None:
        super()._build()

        # Give the explicit monitored-sites panel enough space without
        # redesigning the stable controls above it.
        _center(self.root, 620, 720)

        panel = tk.Frame(self.root, bg="white", padx=14, pady=12,
                         highlightbackground="#dfe6e9", highlightthickness=1)
        panel.pack(fill="both", expand=False, padx=24, pady=(0, 18))

        head = tk.Frame(panel, bg="white")
        head.pack(fill="x")
        tk.Label(head, text="Sites personnels surveillés pour popup",
                 font=FONT_MD, fg=ACCENT, bg="white").pack(side="left")
        self.custom_count_lbl = tk.Label(head, text="", font=FONT_SM,
                                         fg=MUTED, bg="white")
        self.custom_count_lbl.pack(side="right")

        detection = "URL réelle + titre" if HAS_UIA else "titre uniquement (URL réelle indisponible)"
        self.custom_engine_lbl = tk.Label(
            panel,
            text=f"Détection : {detection} • contrôle ~100 ms • lu depuis config.dat",
            font=("Segoe UI", 9), fg=MUTED, bg="white", justify="left",
        )
        self.custom_engine_lbl.pack(anchor="w", pady=(2, 8))

        list_wrap = tk.Frame(panel, bg="white")
        list_wrap.pack(fill="both", expand=True)
        self.custom_sites_list = tk.Listbox(
            list_wrap, height=6, font=("Consolas", 10),
            relief="solid", bd=1, activestyle="none",
            selectmode="browse", exportselection=False,
        )
        scrollbar = tk.Scrollbar(list_wrap, orient="vertical",
                                 command=self.custom_sites_list.yview)
        self.custom_sites_list.configure(yscrollcommand=scrollbar.set)
        self.custom_sites_list.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        tk.Label(
            panel,
            text="Si un site apparaît ici, il est bien enregistré et le monitor le recharge automatiquement.",
            font=("Segoe UI", 9), fg=MUTED, bg="white", justify="left",
        ).pack(anchor="w", pady=(8, 0))

    def _refresh_custom_sites_panel(self) -> None:
        if not hasattr(self, "custom_sites_list"):
            return
        cfg = config.load()
        domains = [str(v).strip() for v in cfg.get("custom_blocked_domains", []) or [] if str(v).strip()]
        urls = [str(v).strip() for v in cfg.get("custom_blocked_urls", []) or [] if str(v).strip()]

        self.custom_sites_list.delete(0, "end")
        for value in domains:
            self.custom_sites_list.insert("end", f"SITE  {value}")
        for value in urls:
            self.custom_sites_list.insert("end", f"URL   {value}")

        total = len(domains) + len(urls)
        self.custom_count_lbl.config(text=f"{total} actif{'s' if total != 1 else ''}")
        if not total:
            self.custom_sites_list.insert("end", "(aucun site personnel enregistré)")

    def _refresh(self) -> None:
        super()._refresh()
        self._refresh_custom_sites_panel()
