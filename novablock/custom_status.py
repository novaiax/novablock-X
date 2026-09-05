"""Compact NovaBlock main window with explicit popup-only custom sites."""
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from . import config, crypto
from .gui import (
    StatusWindow as BaseStatusWindow,
    CodeDialog,
    BG, ACCENT, MUTED, PRIMARY, FONT_LG, FONT_MD, FONT_SM, _center,
)
from .monitor import HAS_UIA


class StatusWindow(BaseStatusWindow):
    """Stable fixed-size main window; no cumulative resizing on refresh."""

    WIDTH = 620
    HEIGHT = 700

    def _build(self) -> None:
        # Move <=1.0.31 custom entries to popup-only storage before anything
        # displays them. If this was the first migration, rebuild the adult
        # network layers once in background so stale custom hosts/policies are
        # removed without freezing the UI.
        migrated = False
        try:
            migrated = config.migrate_custom_sites_to_popup_only()
        except Exception:
            migrated = False
        if migrated:
            threading.Thread(
                target=self._cleanup_legacy_network_custom_blocks,
                name="NovaBlockCustomPopupMigration",
                daemon=True,
            ).start()

        # BaseStatusWindow.__init__ initially centers the legacy 520x480 size.
        # Override it once here and never resize again during refresh.
        _center(self.root, self.WIDTH, self.HEIGHT)
        self.root.resizable(False, False)

        outer = tk.Frame(self.root, bg=BG, padx=22, pady=18)
        outer.pack(fill="both", expand=True)

        top = tk.Frame(outer, bg=BG)
        top.pack(fill="x")
        tk.Label(top, text="NovaBlock", font=FONT_LG,
                 fg=PRIMARY, bg=BG).pack(side="left")
        self.status_lbl = tk.Label(top, text="", font=FONT_MD,
                                   fg=ACCENT, bg=BG)
        self.status_lbl.pack(side="right")

        self.stats_lbl = tk.Label(
            outer, text="", font=("Segoe UI", 9), fg=MUTED, bg=BG,
            justify="left", anchor="w",
        )
        self.stats_lbl.pack(fill="x", pady=(5, 10))

        unlock_row = tk.Frame(outer, bg=BG)
        unlock_row.pack(fill="x", pady=(0, 5))
        self.unlock_btn = tk.Button(
            unlock_row, text="Demander le code à mon ami",
            font=FONT_SM, bg=PRIMARY, fg="white", relief="flat",
            padx=10, pady=7, command=self._request_unlock,
        )
        self.unlock_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.enter_btn = tk.Button(
            unlock_row, text="J'ai le code — débloquer 24h",
            font=FONT_SM, bg="#fdcb6e", fg=ACCENT, relief="flat",
            padx=10, pady=7, command=self._enter_code,
        )
        self.enter_btn.pack(side="left", fill="x", expand=True, padx=(4, 0))

        self.settings_btn = tk.Button(
            outer, text="⚙  Modifier mes infos",
            font=FONT_SM, bg="#dfe6e9", fg=ACCENT, relief="flat",
            padx=10, pady=5, command=self._open_settings,
        )
        self.settings_btn.pack(fill="x", pady=(0, 9))

        ttk.Separator(outer).pack(fill="x", pady=(2, 9))

        panel = tk.Frame(
            outer, bg="white", padx=13, pady=11,
            highlightbackground="#dfe6e9", highlightthickness=1,
        )
        panel.pack(fill="x")

        head = tk.Frame(panel, bg="white")
        head.pack(fill="x")
        tk.Label(head, text="Sites personnels surveillés pour popup",
                 font=("Segoe UI", 11, "bold"), fg=ACCENT,
                 bg="white").pack(side="left")
        self.custom_count_lbl = tk.Label(head, text="", font=FONT_SM,
                                         fg=MUTED, bg="white")
        self.custom_count_lbl.pack(side="right")

        engine_text = (
            "Navigation réelle uniquement • saisie/texte ignorés • contrôle ~100 ms"
            if HAS_UIA else
            "Détection URL réelle indisponible sur ce PC"
        )
        self.custom_engine_lbl = tk.Label(
            panel, text=engine_text, font=("Segoe UI", 9),
            fg=MUTED, bg="white", justify="left",
        )
        self.custom_engine_lbl.pack(anchor="w", pady=(2, 7))

        list_wrap = tk.Frame(panel, bg="white")
        list_wrap.pack(fill="x")
        self.custom_sites_list = tk.Listbox(
            list_wrap, height=5, font=("Consolas", 9),
            relief="solid", bd=1, activestyle="none",
            selectmode="browse", exportselection=False,
        )
        scrollbar = tk.Scrollbar(list_wrap, orient="vertical",
                                 command=self.custom_sites_list.yview)
        self.custom_sites_list.configure(yscrollcommand=scrollbar.set)
        self.custom_sites_list.pack(side="left", fill="x", expand=True)
        scrollbar.pack(side="right", fill="y")

        site_actions = tk.Frame(panel, bg="white")
        site_actions.pack(fill="x", pady=(8, 0))
        self.add_site_btn = tk.Button(
            site_actions, text="+ Ajouter un site popup",
            font=FONT_SM, bg="#74b9ff", fg="white", relief="flat",
            padx=10, pady=5, command=self._add_custom_site,
        )
        self.add_site_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.remove_site_btn = tk.Button(
            site_actions, text="− Retirer (code requis)",
            font=FONT_SM, bg="#dfe6e9", fg=ACCENT, relief="flat",
            padx=10, pady=5, command=self._remove_custom_site,
        )
        self.remove_site_btn.pack(side="left", fill="x", expand=True, padx=(4, 0))

        tk.Label(
            panel,
            text="Le popup apparaît seulement quand tu engages réellement la navigation vers un site listé.",
            font=("Segoe UI", 8), fg=MUTED, bg="white", justify="left",
        ).pack(anchor="w", pady=(7, 0))

        ttk.Separator(outer).pack(fill="x", pady=(11, 8))

        self.uninstall_btn = tk.Button(
            outer, text="Désinstaller NovaBlock (cooldown 7 jours)",
            font=FONT_SM, bg="#dfe6e9", fg=ACCENT, relief="flat",
            padx=10, pady=5, command=self._request_uninstall,
        )
        self.uninstall_btn.pack(fill="x")

        self.cancel_uninstall_btn = tk.Button(
            outer, text="Annuler la désinstallation",
            font=FONT_SM, bg="#dfe6e9", fg=ACCENT, relief="flat",
            padx=10, pady=5, command=self._cancel_uninstall,
        )

        self.feedback_lbl = tk.Label(
            outer, text="", font=("Segoe UI", 9), fg=MUTED, bg=BG,
            wraplength=560, justify="left",
        )
        self.feedback_lbl.pack(fill="x", pady=(7, 0))

        self._refresh_job = None

    @staticmethod
    def _cleanup_legacy_network_custom_blocks() -> None:
        """One-time cleanup; never sends mail and never kills browsers."""
        try:
            from . import blocker
            blocker.apply_full_block(kill_browsers=False)
        except Exception:
            # The watchdog can repair again later; migration itself is already
            # safe because network getters now always return empty custom lists.
            pass

    def _refresh_custom_sites_panel(self) -> None:
        domains = config.get_popup_domains()
        urls = config.get_popup_urls()
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
        if getattr(self, "_refresh_job", None):
            try:
                self.root.after_cancel(self._refresh_job)
            except Exception:
                pass
            self._refresh_job = None

        cfg = config.load()
        if not cfg.get("install_ts"):
            self.status_lbl.config(text="Non installé", fg=PRIMARY)
            return

        if config.is_temp_unlocked():
            remain = max(0, int(cfg.get("temp_unlock_until", 0) - time.time()))
            h = remain // 3600
            m = (remain % 3600) // 60
            self.status_lbl.config(text=f"⚠ Débloqué {h}h{m:02d}", fg=PRIMARY)
        else:
            self.status_lbl.config(text="🛡 Filtre actif", fg="#00b894")

        days_active = int((time.time() - cfg["install_ts"]) // 86400)
        last_rot = cfg.get("code_rotation_ts") or cfg["install_ts"]
        next_rot = max(0, int((last_rot + 7 * 86400 - time.time()) // 86400))
        wk = config.count_requests_last_week(cfg)
        total = config.count_requests_total(cfg)
        cooldown = config.uninstall_cooldown_remaining()
        cooldown_txt = ""
        if cooldown >= 0:
            d = cooldown // 86400
            h = (cooldown % 86400) // 3600
            cooldown_txt = f"  •  Désinstallation : {d}j {h}h"
            if not self.cancel_uninstall_btn.winfo_manager():
                self.cancel_uninstall_btn.pack(fill="x", pady=(5, 0))
        else:
            self.cancel_uninstall_btn.pack_forget()

        self.stats_lbl.config(text=(
            f"Actif depuis {days_active}j  •  Demandes semaine : {wk}  •  Total : {total}  •  "
            f"Rotation code : {next_rot}j{cooldown_txt}"
        ))
        self._refresh_custom_sites_panel()
        self._refresh_job = self.root.after(5000, self._refresh)

    def _add_custom_site(self) -> None:
        dlg = tk.Toplevel(self.root)
        dlg.title("Ajouter un site popup")
        dlg.configure(bg=BG)
        _center(dlg, 500, 300)
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        tk.Label(dlg, text="Déclencher un popup quand je navigue vers…",
                 font=FONT_MD, fg=ACCENT, bg=BG).pack(anchor="w", padx=20, pady=(18, 5))

        scope = tk.StringVar(value="domain")
        radios = tk.Frame(dlg, bg=BG)
        radios.pack(fill="x", padx=20)
        tk.Radiobutton(radios, text="Tout le site (ex. instagram.com)",
                       variable=scope, value="domain", font=FONT_SM,
                       bg=BG, selectcolor=BG).pack(anchor="w")
        tk.Radiobutton(radios, text="Une URL précise",
                       variable=scope, value="url", font=FONT_SM,
                       bg=BG, selectcolor=BG).pack(anchor="w")

        entry = tk.Entry(dlg, font=FONT_MD, relief="solid", bd=1)
        entry.pack(fill="x", padx=20, pady=(10, 5), ipady=4)
        entry.focus_set()
        tk.Label(
            dlg,
            text="Aucun blocage DNS/hosts : le site commence à charger puis le popup apparaît.",
            font=("Segoe UI", 9), fg=MUTED, bg=BG, wraplength=455, justify="left",
        ).pack(anchor="w", padx=20)

        def _add():
            raw = entry.get().strip()
            added = (config.add_custom_domain(raw)
                     if scope.get() == "domain" else config.add_custom_url(raw))
            if not added:
                msg = (
                    "movix.cash est explicitement autorisé et ne peut pas être ajouté à cette liste."
                    if "movix.cash" in raw.lower() else f"Entrée invalide : {raw}"
                )
                messagebox.showerror("Impossible d'ajouter", msg, parent=dlg)
                return
            dlg.destroy()
            self.feedback_lbl.config(
                text=f"✓ {added} ajouté. Popup actif dès la prochaine navigation.",
                fg="#00b894",
            )
            self._refresh()

        buttons = tk.Frame(dlg, bg=BG)
        buttons.pack(fill="x", padx=20, pady=14)
        tk.Button(buttons, text="Annuler", font=FONT_SM, bg="#ddd", fg=ACCENT,
                  relief="flat", padx=12, pady=6, command=dlg.destroy).pack(side="right", padx=(8, 0))
        tk.Button(buttons, text="Ajouter", font=FONT_SM, bg=PRIMARY, fg="white",
                  relief="flat", padx=12, pady=6, command=_add).pack(side="right")
        entry.bind("<Return>", lambda _e: _add())

    def _remove_custom_site(self) -> None:
        domains = config.get_popup_domains()
        urls = config.get_popup_urls()
        if not domains and not urls:
            messagebox.showinfo("Aucun site", "Aucun site personnel n'est enregistré.")
            return

        code_dlg = CodeDialog(self.root)
        self.root.wait_window(code_dlg.top)
        if not code_dlg.result:
            return
        cfg = config.load()
        if not crypto.verify_code(code_dlg.result, cfg.get("code_hash", "")):
            self.feedback_lbl.config(text="✗ Code incorrect.", fg=PRIMARY)
            return

        dlg = tk.Toplevel(self.root)
        dlg.title("Retirer un site popup")
        dlg.configure(bg=BG)
        _center(dlg, 520, 390)
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        tk.Label(dlg, text="Sélectionne les règles à retirer",
                 font=FONT_MD, fg=ACCENT, bg=BG).pack(anchor="w", padx=20, pady=(18, 8))
        box = tk.Frame(dlg, bg="white", padx=8, pady=6)
        box.pack(fill="both", expand=True, padx=20)

        vars_: dict[tuple[str, str], tk.BooleanVar] = {}
        for value in domains:
            var = tk.BooleanVar(value=False)
            vars_[("domain", value)] = var
            tk.Checkbutton(box, text=f"SITE  {value}", variable=var,
                           font=FONT_SM, bg="white", fg=ACCENT,
                           anchor="w").pack(fill="x", anchor="w")
        for value in urls:
            var = tk.BooleanVar(value=False)
            vars_[("url", value)] = var
            tk.Checkbutton(box, text=f"URL   {value}", variable=var,
                           font=FONT_SM, bg="white", fg=ACCENT,
                           anchor="w").pack(fill="x", anchor="w")

        def _remove():
            removed: list[str] = []
            for (kind, value), var in vars_.items():
                if not var.get():
                    continue
                ok = (config.remove_custom_domain(value)
                      if kind == "domain" else config.remove_custom_url(value))
                if ok:
                    removed.append(value)
            dlg.destroy()
            if removed:
                self.feedback_lbl.config(text=f"✓ Retirés : {', '.join(removed)}", fg="#00b894")
            else:
                self.feedback_lbl.config(text="Aucune règle sélectionnée.", fg=MUTED)
            self._refresh()

        buttons = tk.Frame(dlg, bg=BG)
        buttons.pack(fill="x", padx=20, pady=14)
        tk.Button(buttons, text="Annuler", font=FONT_SM, bg="#ddd", fg=ACCENT,
                  relief="flat", padx=12, pady=6, command=dlg.destroy).pack(side="right", padx=(8, 0))
        tk.Button(buttons, text="Retirer", font=FONT_SM, bg=PRIMARY, fg="white",
                  relief="flat", padx=12, pady=6, command=_remove).pack(side="right")
