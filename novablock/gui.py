"""Tkinter GUI: setup wizard, status window, blocked-site popup, unlock dialog."""
import logging
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk
from typing import Optional

import requests

from . import config, crypto, mailer, blocker, persistence

log = logging.getLogger("novablock.gui")

PRIMARY = "#d63031"
ACCENT = "#2d3436"
BG = "#fafafa"
MUTED = "#636e72"

FONT_LG = ("Segoe UI", 18, "bold")
FONT_MD = ("Segoe UI", 12)
FONT_SM = ("Segoe UI", 10)
FONT_MONO = ("Consolas", 14)


def _center(win: tk.Misc, w: int, h: int) -> None:
    win.update_idletasks()
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    win.geometry(f"{w}x{h}+{x}+{y}")


def _link(parent, text: str, url: str, font=None) -> tk.Label:
    """A clickable hyperlink label."""
    lbl = tk.Label(parent, text=text, fg="#0984e3", bg=BG, cursor="hand2",
                   font=font or FONT_SM)
    lbl.bind("<Button-1>", lambda _e: webbrowser.open(url))
    f = lbl.cget("font")
    lbl.configure(font=(f if isinstance(f, str) else f[0], 10, "underline"))
    return lbl


class SetupWizard:
    """Multi-step setup wizard. Self-contained — explains everything.

    Steps:
      1. Welcome / what NovaBlock does
      2. Resend account setup (with clickable links)
      3. Personal info (you + your friend)
      4. Final review & install
      5. Done
    """

    def __init__(self, resend_api_key: str = "",
                 from_email: str = "NovaBlock <onboarding@resend.dev>"):
        self.prefill_api_key = resend_api_key
        self.prefill_from_email = from_email
        self.root = tk.Tk()
        self.root.title("NovaBlock — Installation")
        self.root.configure(bg=BG)
        _center(self.root, 720, 720)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.completed = False
        self.step = 1

        self.data = {
            "api_key": resend_api_key,
            "from_email": from_email,
            "user_name": "",
            "friend_name": "",
            "friend_email": "",
        }

        self.container = tk.Frame(self.root, bg=BG)
        self.container.pack(fill="both", expand=True, padx=32, pady=20)
        self._render()

    # ---------- step rendering ----------

    def _clear(self) -> None:
        for w in self.container.winfo_children():
            w.destroy()

    def _render(self) -> None:
        self._clear()
        if self.step == 1:
            self._step_welcome()
        elif self.step == 2:
            self._step_resend()
        elif self.step == 3:
            self._step_personal()
        elif self.step == 4:
            self._step_review()
        elif self.step == 5:
            self._step_done()

    def _header(self, title: str, subtitle: str = "") -> None:
        tk.Label(self.container, text="NovaBlock", font=FONT_LG, fg=PRIMARY, bg=BG).pack(anchor="w")
        tk.Label(self.container, text=f"Étape {self.step}/4 — {title}",
                 font=FONT_MD, fg=ACCENT, bg=BG).pack(anchor="w", pady=(2, 0))
        if subtitle:
            tk.Label(self.container, text=subtitle, font=FONT_SM, fg=MUTED, bg=BG,
                     justify="left", wraplength=640).pack(anchor="w", pady=(2, 14))
        else:
            tk.Frame(self.container, bg=BG, height=10).pack()

    def _nav(self, on_next, next_label: str = "Suivant",
             show_back: bool = True, next_enabled: bool = True) -> None:
        bar = tk.Frame(self.container, bg=BG)
        bar.pack(fill="x", side="bottom", pady=(20, 0))
        nb = tk.Button(bar, text=next_label, font=FONT_MD,
                       bg=PRIMARY if next_enabled else "#aaa", fg="white",
                       relief="flat", padx=18, pady=8,
                       command=on_next,
                       state="normal" if next_enabled else "disabled")
        nb.pack(side="right")
        if show_back:
            tk.Button(bar, text="Précédent", font=FONT_MD, bg="#ddd", fg=ACCENT,
                      relief="flat", padx=14, pady=8,
                      command=self._back).pack(side="right", padx=(0, 8))
        tk.Button(bar, text="Annuler", font=FONT_SM, bg=BG, fg=MUTED,
                  relief="flat", command=self._on_close).pack(side="left")

    def _back(self) -> None:
        if self.step > 1:
            self.step -= 1
            self._render()

    def _next(self) -> None:
        self.step += 1
        self._render()

    # ---------- step 1: welcome ----------

    def _step_welcome(self) -> None:
        self._header(
            "Bienvenue",
            "NovaBlock est un bloqueur de contenu adulte avec accountability partner. "
            "Très chiant à contourner — c'est volontaire.",
        )

        tk.Label(self.container, text="Comment ça marche", font=FONT_MD, fg=ACCENT, bg=BG).pack(anchor="w", pady=(8, 4))
        tk.Label(self.container, justify="left", wraplength=640, fg=ACCENT, bg=BG, font=FONT_SM, text=(
            "  • L'app génère un code de 25 caractères. Tu ne le vois jamais.\n"
            "  • Le code est envoyé par email à un ami de confiance que tu désignes.\n"
            "  • L'app bloque les domaines adultes (DNS Cloudflare Family + hosts file ~50 000 domaines).\n"
            "  • Si tu essayes d'accéder à un site adulte, l'app affiche un popup plein écran qui bloque.\n"
            "  • Pour débloquer 24h : ton ami doit te donner le code (un email lui est envoyé).\n"
            "  • Le code change automatiquement tous les 7 jours.\n"
            "  • Pour désinstaller : cooldown obligatoire de 7 jours, puis code requis."
        )).pack(anchor="w")

        tk.Label(self.container, text="Limites honnêtes", font=FONT_MD, fg=ACCENT, bg=BG).pack(anchor="w", pady=(14, 4))
        tk.Label(self.container, justify="left", wraplength=640, fg=MUTED, bg=BG, font=FONT_SM, text=(
            "Un user admin déterminé peut booter en Safe Mode et désactiver le service. "
            "Aucun bloqueur userland ne peut empêcher ça. L'objectif est de rendre le contournement "
            "assez chiant pour qu'un moment de faiblesse abandonne — pas de bloquer un attaquant motivé."
        )).pack(anchor="w")

        warn = tk.Label(
            self.container, font=FONT_SM, fg=PRIMARY, bg=BG, justify="left", wraplength=640,
            text="⚠️  Une fois installé, désinstaller prend 7 jours minimum. C'est volontaire."
        )
        warn.pack(anchor="w", pady=(20, 0))

        self._nav(on_next=self._next, next_label="Commencer", show_back=False)

    # ---------- step 2: Resend ----------

    def _step_resend(self) -> None:
        self._header(
            "Configuration Resend (envoi des emails)",
            "NovaBlock utilise Resend pour envoyer le code et les notifications. "
            "Tu as besoin d'un compte Resend gratuit (3000 emails/mois)."
        )

        steps = tk.Frame(self.container, bg=BG)
        steps.pack(fill="x", anchor="w")

        tk.Label(steps, text="1.", font=FONT_MD, fg=ACCENT, bg=BG).grid(row=0, column=0, sticky="nw")
        s1 = tk.Frame(steps, bg=BG); s1.grid(row=0, column=1, sticky="w", padx=(6, 0))
        tk.Label(s1, text="Crée un compte Resend gratuit :", font=FONT_SM, fg=ACCENT, bg=BG).pack(anchor="w")
        _link(s1, "→ resend.com/signup", "https://resend.com/signup").pack(anchor="w")

        tk.Label(steps, text="2.", font=FONT_MD, fg=ACCENT, bg=BG).grid(row=1, column=0, sticky="nw", pady=(10, 0))
        s2 = tk.Frame(steps, bg=BG); s2.grid(row=1, column=1, sticky="w", padx=(6, 0), pady=(10, 0))
        tk.Label(s2, text="Crée une clé API (permission \"Sending access\") :",
                 font=FONT_SM, fg=ACCENT, bg=BG).pack(anchor="w")
        _link(s2, "→ resend.com/api-keys", "https://resend.com/api-keys").pack(anchor="w")

        tk.Label(steps, text="3.", font=FONT_MD, fg=ACCENT, bg=BG).grid(row=2, column=0, sticky="nw", pady=(10, 0))
        s3 = tk.Frame(steps, bg=BG); s3.grid(row=2, column=1, sticky="w", padx=(6, 0), pady=(10, 0))
        tk.Label(s3, text="Vérifie un domaine pour pouvoir envoyer à n'importe quel email :",
                 font=FONT_SM, fg=ACCENT, bg=BG).pack(anchor="w")
        _link(s3, "→ resend.com/domains", "https://resend.com/domains").pack(anchor="w")
        tk.Label(s3, text="(Sans domaine vérifié, tu ne peux envoyer qu'à l'email de ton compte Resend)",
                 font=("Segoe UI", 9), fg=MUTED, bg=BG).pack(anchor="w")

        # Form
        form = tk.Frame(self.container, bg=BG)
        form.pack(fill="x", pady=(20, 0))

        tk.Label(form, text="Clé API Resend :", font=FONT_SM, fg=ACCENT, bg=BG).pack(anchor="w")
        self.api_entry = tk.Entry(form, font=FONT_MD, relief="solid", bd=1, show="•")
        self.api_entry.insert(0, self.data["api_key"])
        self.api_entry.pack(fill="x", ipady=4)
        tk.Label(form, text="(commence par re_… ; cachée pour la sécurité)",
                 font=("Segoe UI", 9), fg=MUTED, bg=BG).pack(anchor="w")

        tk.Label(form, text="Email expéditeur :", font=FONT_SM, fg=ACCENT, bg=BG).pack(anchor="w", pady=(10, 0))
        self.from_entry = tk.Entry(form, font=FONT_MD, relief="solid", bd=1)
        self.from_entry.insert(0, self.data["from_email"])
        self.from_entry.pack(fill="x", ipady=4)
        tk.Label(form,
                 text="(format : NovaBlock <noreply@ton-domaine.com>. "
                      "Si pas de domaine vérifié : NovaBlock <onboarding@resend.dev>)",
                 font=("Segoe UI", 9), fg=MUTED, bg=BG, wraplength=640, justify="left").pack(anchor="w")

        # Test connection button
        action = tk.Frame(self.container, bg=BG)
        action.pack(fill="x", pady=(12, 0))
        self.test_btn = tk.Button(action, text="Tester la clé API", font=FONT_SM,
                                  bg="#dfe6e9", fg=ACCENT, relief="flat", padx=12, pady=6,
                                  command=self._test_api)
        self.test_btn.pack(side="left")
        self.test_lbl = tk.Label(action, text="", font=FONT_SM, bg=BG)
        self.test_lbl.pack(side="left", padx=(10, 0))

        self._nav(on_next=self._validate_resend, next_label="Suivant")

    def _test_api(self) -> None:
        key = self.api_entry.get().strip()
        if not key.startswith("re_"):
            self.test_lbl.config(text="✗ Clé invalide (doit commencer par re_)", fg=PRIMARY)
            return
        self.test_lbl.config(text="Test en cours…", fg=MUTED)
        self.root.update()
        threading.Thread(target=self._do_test_api, args=(key,), daemon=True).start()

    def _do_test_api(self, key: str) -> None:
        try:
            r = requests.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={}, timeout=10,
            )
            body = r.text.lower()
            if r.status_code == 401 and "invalid_api_key" in body:
                self.root.after(0, lambda: self.test_lbl.config(
                    text="✗ Clé invalide", fg=PRIMARY))
            elif r.status_code in (200, 401, 422):
                self.root.after(0, lambda: self.test_lbl.config(
                    text="✓ Clé valide", fg="#00b894"))
            else:
                self.root.after(0, lambda: self.test_lbl.config(
                    text=f"? Réponse inattendue ({r.status_code})", fg=MUTED))
        except Exception as e:
            self.root.after(0, lambda: self.test_lbl.config(text=f"✗ {e}", fg=PRIMARY))

    def _validate_resend(self) -> None:
        api = self.api_entry.get().strip()
        frm = self.from_entry.get().strip()
        if not api.startswith("re_"):
            messagebox.showerror("Erreur", "Clé API invalide (doit commencer par 're_').")
            return
        if "@" not in frm:
            messagebox.showerror("Erreur", "Email expéditeur invalide (doit contenir un @).")
            return
        self.data["api_key"] = api
        self.data["from_email"] = frm
        self._next()

    # ---------- step 3: personal ----------

    def _step_personal(self) -> None:
        self._header(
            "Toi & ton accountability partner",
            "Choisis bien la personne — elle aura le code et tu devras lui demander pour débloquer. "
            "Idéal : un proche qui te connaît et qui n'a pas peur de te dire non."
        )

        form = tk.Frame(self.container, bg=BG)
        form.pack(fill="x")

        tk.Label(form, text="Ton prénom :", font=FONT_SM, fg=ACCENT, bg=BG).pack(anchor="w", pady=(8, 2))
        self.user_name_e = tk.Entry(form, font=FONT_MD, relief="solid", bd=1)
        self.user_name_e.insert(0, self.data["user_name"])
        self.user_name_e.pack(fill="x", ipady=4)

        tk.Label(form, text="Prénom de ton ami :", font=FONT_SM, fg=ACCENT, bg=BG).pack(anchor="w", pady=(12, 2))
        self.friend_name_e = tk.Entry(form, font=FONT_MD, relief="solid", bd=1)
        self.friend_name_e.insert(0, self.data["friend_name"])
        self.friend_name_e.pack(fill="x", ipady=4)

        tk.Label(form, text="Email de ton ami :", font=FONT_SM, fg=ACCENT, bg=BG).pack(anchor="w", pady=(12, 2))
        self.friend_email_e = tk.Entry(form, font=FONT_MD, relief="solid", bd=1)
        self.friend_email_e.insert(0, self.data["friend_email"])
        self.friend_email_e.pack(fill="x", ipady=4)
        tk.Label(form,
                 text="(L'app enverra le code à cet email. Préviens ton ami avant.)",
                 font=("Segoe UI", 9), fg=MUTED, bg=BG).pack(anchor="w")

        # Send test email
        action = tk.Frame(self.container, bg=BG)
        action.pack(fill="x", pady=(14, 0))
        self.test_email_btn = tk.Button(action, text="Envoyer un email de test à mon ami",
                                        font=FONT_SM, bg="#dfe6e9", fg=ACCENT,
                                        relief="flat", padx=12, pady=6,
                                        command=self._test_email)
        self.test_email_btn.pack(side="left")
        self.test_email_lbl = tk.Label(action, text="", font=FONT_SM, bg=BG, wraplength=400, justify="left")
        self.test_email_lbl.pack(side="left", padx=(10, 0))

        tk.Label(self.container,
                 text="Ce test n'envoie PAS le vrai code — c'est juste pour vérifier "
                      "que l'email arrive bien chez ton ami.",
                 font=("Segoe UI", 9), fg=MUTED, bg=BG, wraplength=640, justify="left").pack(anchor="w", pady=(4, 0))

        self._nav(on_next=self._validate_personal, next_label="Suivant")

    def _test_email(self) -> None:
        friend_email = self.friend_email_e.get().strip()
        friend_name = self.friend_name_e.get().strip() or "ami"
        user_name = self.user_name_e.get().strip() or "quelqu'un"
        if "@" not in friend_email:
            self.test_email_lbl.config(text="✗ Email invalide", fg=PRIMARY)
            return
        self.test_email_lbl.config(text="Envoi en cours…", fg=MUTED)
        self.root.update()
        threading.Thread(target=self._do_test_email,
                         args=(friend_email, friend_name, user_name), daemon=True).start()

    def _do_test_email(self, to: str, friend_name: str, user_name: str) -> None:
        html = (f"<p>Salut {friend_name},</p>"
                f"<p>Ceci est un email de test envoyé par <strong>{user_name}</strong> "
                f"depuis l'installation de NovaBlock.</p>"
                f"<p>Si tu vois cet email, ça veut dire que la livraison fonctionne. "
                f"Tu recevras bientôt un autre email contenant le vrai code à 25 caractères.</p>"
                f"<p style='color:#888;font-size:12px'>NovaBlock — bloqueur de contenu adulte avec accountability partner.</p>")
        ok = mailer._send(self.data["api_key"], self.data["from_email"], to,
                          "NovaBlock — Email de test", html)
        if ok:
            self.root.after(0, lambda: self.test_email_lbl.config(
                text=f"✓ Email envoyé à {to}", fg="#00b894"))
        else:
            err = mailer.get_last_error()
            hint = ""
            if "validation_error" in err.lower() or "you can only send" in err.lower() \
               or "testing emails" in err.lower() or "verify a domain" in err.lower():
                hint = ("\n→ Domaine non vérifié sur Resend. Tu ne peux envoyer qu'à "
                        "l'email de ton compte Resend, sauf si tu vérifies un domaine.")
            self.root.after(0, lambda: self.test_email_lbl.config(
                text=f"✗ {err}{hint}", fg=PRIMARY))

    def _validate_personal(self) -> None:
        un = self.user_name_e.get().strip()
        fn = self.friend_name_e.get().strip()
        fe = self.friend_email_e.get().strip()
        if not un or not fn:
            messagebox.showerror("Erreur", "Prénoms requis.")
            return
        if "@" not in fe:
            messagebox.showerror("Erreur", "Email de ton ami invalide.")
            return
        self.data["user_name"] = un
        self.data["friend_name"] = fn
        self.data["friend_email"] = fe
        self._next()

    # ---------- step 4: review ----------

    def _step_review(self) -> None:
        self._header(
            "Vérification & installation",
            "Dernière étape avant d'installer."
        )
        recap = tk.Frame(self.container, bg="white", padx=16, pady=14, highlightbackground="#ddd",
                         highlightthickness=1)
        recap.pack(fill="x", pady=(4, 16))

        rows = [
            ("Toi", self.data["user_name"]),
            ("Accountability partner", f"{self.data['friend_name']} ({self.data['friend_email']})"),
            ("Email expéditeur", self.data["from_email"]),
            ("Clé Resend", self.data["api_key"][:8] + "…" + self.data["api_key"][-4:]),
        ]
        for k, v in rows:
            row = tk.Frame(recap, bg="white")
            row.pack(fill="x", pady=2)
            tk.Label(row, text=k, font=FONT_SM, fg=MUTED, bg="white", width=22, anchor="w").pack(side="left")
            tk.Label(row, text=v, font=FONT_SM, fg=ACCENT, bg="white", anchor="w").pack(side="left")

        tk.Label(self.container, text="Ce qui va se passer", font=FONT_MD, fg=ACCENT, bg=BG).pack(anchor="w", pady=(8, 4))
        tk.Label(self.container, justify="left", wraplength=640, fg=ACCENT, bg=BG, font=FONT_SM, text=(
            "  1. Génération d'un code aléatoire de 25 caractères\n"
            "  2. Envoi du code par email à ton ami\n"
            "  3. Téléchargement de la liste de blocage (~50 000 domaines)\n"
            "  4. Modification du fichier hosts Windows + ACL durci\n"
            "  5. DNS forcé sur Cloudflare Family (1.1.1.3)\n"
            "  6. Installation d'une tâche planifiée SYSTEM (relance auto)\n"
            "  7. NovaBlock se met dans le tray et reste actif"
        )).pack(anchor="w")

        tk.Label(self.container,
                 text="⚠️  Une fois cette étape lancée, tu ne pourras plus revenir en arrière "
                      "sans le code de ton ami + 7 jours d'attente.",
                 font=FONT_SM, fg=PRIMARY, bg=BG, wraplength=640, justify="left").pack(anchor="w", pady=(10, 0))

        self.install_status = tk.Label(self.container, text="", font=FONT_SM, fg=MUTED,
                                       bg=BG, wraplength=640, justify="left")
        self.install_status.pack(anchor="w", pady=(8, 0))

        bar = tk.Frame(self.container, bg=BG)
        bar.pack(fill="x", side="bottom", pady=(20, 0))
        self.install_btn = tk.Button(bar, text="Installer NovaBlock", font=FONT_MD,
                                     bg=PRIMARY, fg="white", relief="flat", padx=18, pady=8,
                                     command=self._install)
        self.install_btn.pack(side="right")
        tk.Button(bar, text="Précédent", font=FONT_MD, bg="#ddd", fg=ACCENT,
                  relief="flat", padx=14, pady=8,
                  command=self._back).pack(side="right", padx=(0, 8))
        tk.Button(bar, text="Annuler", font=FONT_SM, bg=BG, fg=MUTED,
                  relief="flat", command=self._on_close).pack(side="left")

    def _install(self) -> None:
        self.install_btn.config(state="disabled")
        self.install_status.config(text="Installation en cours… (ça peut prendre 1 min)", fg=MUTED)
        self.root.update()
        threading.Thread(target=self._do_install, daemon=True).start()

    def _do_install(self) -> None:
        try:
            self.root.after(0, lambda: self.install_status.config(text="Génération du code…"))
            code = crypto.generate_unlock_code()
            code_hash = crypto.hash_code(code)

            self.root.after(0, lambda: self.install_status.config(text="Envoi du code à ton ami…"))
            sent = mailer.send_setup_email(
                self.data["api_key"], self.data["from_email"],
                self.data["friend_email"], self.data["friend_name"],
                self.data["user_name"], code,
            )
            if not sent:
                err = mailer.get_last_error()
                self.root.after(0, lambda: messagebox.showerror(
                    "Erreur d'envoi", f"{err}\n\nReviens à l'étape 2 ou 3 pour corriger."))
                self.root.after(0, lambda: self.install_btn.config(state="normal"))
                return

            self.root.after(0, lambda: self.install_status.config(text="Téléchargement de la blocklist…"))
            self.root.after(0, lambda: self.install_status.config(text="Application du blocage (DNS + hosts)…"))

            cfg = config.load()
            cfg.update({
                "user_name": self.data["user_name"],
                "user_email": "",
                "friend_name": self.data["friend_name"],
                "friend_email": self.data["friend_email"],
                "code_hash": code_hash,
                "install_ts": int(time.time()),
                "code_rotation_ts": int(time.time()),
                "resend_api_key": self.data["api_key"],
                "from_email": self.data["from_email"],
            })
            config.save(cfg)

            blocker.apply_full_block()

            self.root.after(0, lambda: self.install_status.config(text="Installation de la persistance…"))
            persistence.install_scheduled_task()
            persistence.add_startup_registry()

            self.completed = True
            self.step = 5
            self.root.after(0, self._render)
        except Exception as e:
            log.exception("install failed")
            self.root.after(0, lambda: messagebox.showerror("Erreur", f"Échec : {e}"))
            self.root.after(0, lambda: self.install_btn.config(state="normal"))

    # ---------- step 5: done ----------

    def _step_done(self) -> None:
        self._clear()
        tk.Label(self.container, text="✓ Installation terminée",
                 font=FONT_LG, fg="#00b894", bg=BG).pack(anchor="w", pady=(20, 8))
        tk.Label(self.container, justify="left", wraplength=640, fg=ACCENT, bg=BG, font=FONT_SM, text=(
            f"Le code à 25 caractères a été envoyé à {self.data['friend_email']}.\n"
            "Demande à ton ami de confirmer la réception AVANT de fermer cette fenêtre.\n\n"
            "À partir de maintenant :\n"
            "  • Le filtre est actif sur tous les navigateurs\n"
            "  • Si tu essayes d'accéder à un site adulte, l'app affiche un popup plein écran\n"
            "  • Pour débloquer 24h : 'Demander le code à mon ami' depuis le tray\n"
            "  • Pour désinstaller : 7 jours de cooldown, puis code requis\n"
            "  • Le code change automatiquement tous les 7 jours\n\n"
            "⚠️  Cliquer sur \"Terminer\" ferme automatiquement tous tes navigateurs\n"
            "(Chrome, Edge, Firefox, etc.) pour que les politiques DoH s'appliquent.\n"
            "Tu pourras les rouvrir tout de suite après — tes onglets seront perdus."
        )).pack(anchor="w")

        bar = tk.Frame(self.container, bg=BG)
        bar.pack(fill="x", side="bottom", pady=(20, 0))
        tk.Button(bar, text="Terminer (ferme les navigateurs)", font=FONT_MD,
                  bg=PRIMARY, fg="white", relief="flat", padx=18, pady=8,
                  command=self._finish).pack(side="right")

    def _finish(self) -> None:
        from . import browser_kill
        try:
            n = browser_kill.kill_all_browsers()
            log.info("Wizard finish: killed %d browsers", n)
        except Exception as e:
            log.warning("browser kill on finish failed: %s", e)
        self.root.destroy()

    # ---------- close handling ----------

    def _on_close(self) -> None:
        if not self.completed:
            if messagebox.askyesno("Quitter ?", "Installation non terminée. Quitter quand même ?"):
                self.root.destroy()
        else:
            self.root.destroy()

    def run(self) -> bool:
        self.root.mainloop()
        return self.completed


class StatusWindow:
    """Main window: shows status, request unlock, request uninstall."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("NovaBlock")
        self.root.configure(bg=BG)
        _center(self.root, 520, 480)
        self.root.protocol("WM_DELETE_WINDOW", self.root.withdraw)
        self._build()
        self._refresh()

    def _build(self) -> None:
        frm = tk.Frame(self.root, bg=BG, padx=24, pady=20)
        frm.pack(fill="both", expand=True)

        tk.Label(frm, text="NovaBlock", font=FONT_LG, fg=PRIMARY, bg=BG).pack(anchor="w")
        self.status_lbl = tk.Label(frm, text="", font=FONT_MD, fg=ACCENT, bg=BG, justify="left")
        self.status_lbl.pack(anchor="w", pady=(8, 16))

        self.stats_lbl = tk.Label(frm, text="", font=FONT_SM, fg=MUTED, bg=BG, justify="left")
        self.stats_lbl.pack(anchor="w", pady=(0, 16))

        ttk.Separator(frm).pack(fill="x", pady=8)

        self.unlock_btn = tk.Button(
            frm, text="Demander le code à mon ami (24h de déblocage)",
            font=FONT_MD, bg=PRIMARY, fg="white", relief="flat", padx=12, pady=8,
            command=self._request_unlock,
        )
        self.unlock_btn.pack(fill="x", pady=4)

        self.enter_btn = tk.Button(
            frm, text="J'ai le code — débloquer 24h",
            font=FONT_MD, bg="#fdcb6e", fg=ACCENT, relief="flat", padx=12, pady=8,
            command=self._enter_code,
        )
        self.enter_btn.pack(fill="x", pady=4)

        ttk.Separator(frm).pack(fill="x", pady=(12, 8))
        tk.Label(frm, text="Sites bloqués manuellement",
                 font=FONT_SM, fg=ACCENT, bg=BG).pack(anchor="w")

        self.add_site_btn = tk.Button(
            frm, text="+ Bloquer un site (libre)",
            font=FONT_SM, bg="#74b9ff", fg="white", relief="flat", padx=12, pady=6,
            command=self._add_custom_site,
        )
        self.add_site_btn.pack(fill="x", pady=2)

        self.remove_site_btn = tk.Button(
            frm, text="− Retirer un site bloqué (code requis)",
            font=FONT_SM, bg="#dfe6e9", fg=ACCENT, relief="flat", padx=12, pady=6,
            command=self._remove_custom_site,
        )
        self.remove_site_btn.pack(fill="x", pady=2)

        self.uninstall_btn = tk.Button(
            frm, text="Désinstaller NovaBlock (cooldown 7 jours)",
            font=FONT_SM, bg="#dfe6e9", fg=ACCENT, relief="flat", padx=12, pady=6,
            command=self._request_uninstall,
        )
        self.uninstall_btn.pack(fill="x", pady=(16, 4))

        self.cancel_uninstall_btn = tk.Button(
            frm, text="Annuler la désinstallation",
            font=FONT_SM, bg="#dfe6e9", fg=ACCENT, relief="flat", padx=12, pady=6,
            command=self._cancel_uninstall,
        )

        self.feedback_lbl = tk.Label(frm, text="", font=FONT_SM, fg=MUTED, bg=BG, wraplength=460, justify="left")
        self.feedback_lbl.pack(anchor="w", pady=(8, 0))

    def _refresh(self) -> None:
        cfg = config.load()
        if not cfg.get("install_ts"):
            self.status_lbl.config(text="Non installé.", fg=PRIMARY)
            return
        if config.is_temp_unlocked():
            remain = int(cfg["temp_unlock_until"] - time.time())
            h = remain // 3600
            m = (remain % 3600) // 60
            self.status_lbl.config(
                text=f"⚠️  Déblocage temporaire actif — {h}h{m:02d}m restantes",
                fg=PRIMARY,
            )
        else:
            self.status_lbl.config(text="🛡️  Filtre actif", fg="#00b894")

        days_active = (time.time() - cfg["install_ts"]) // 86400
        last_rot = cfg.get("code_rotation_ts") or cfg["install_ts"]
        next_rot = max(0, int((last_rot + 7 * 86400 - time.time()) // 86400))
        wk = config.count_requests_last_week(cfg)
        total = config.count_requests_total(cfg)
        cooldown = config.uninstall_cooldown_remaining()
        cooldown_txt = ""
        if cooldown >= 0:
            d = cooldown // 86400
            h = (cooldown % 86400) // 3600
            cooldown_txt = f"\nDésinstallation : {d}j {h}h restantes"
            self.cancel_uninstall_btn.pack(fill="x", pady=4)
        else:
            self.cancel_uninstall_btn.pack_forget()

        self.stats_lbl.config(text=(
            f"Actif depuis : {int(days_active)} jours\n"
            f"Demandes de déblocage cette semaine : {wk}\n"
            f"Demandes de déblocage au total : {total}\n"
            f"Prochaine rotation du code : dans {next_rot}j"
            f"{cooldown_txt}"
        ))
        self.root.after(5000, self._refresh)

    def _request_unlock(self) -> None:
        if not messagebox.askyesno(
            "Demander le code ?",
            "Cliquer ici va envoyer un email à ton ami avec le détail de ta demande.\n\n"
            "Continuer ?",
        ):
            return
        self.feedback_lbl.config(text="Envoi en cours…", fg=MUTED)
        self.root.update()
        threading.Thread(target=self._do_request_unlock, daemon=True).start()

    def _do_request_unlock(self) -> None:
        cfg = config.load()
        # Generate a FRESH code, replace the hash, then email the new code to the friend.
        new_code = crypto.generate_unlock_code()
        new_hash = crypto.hash_code(new_code)
        wk = config.record_unlock_request()
        total = config.count_requests_total()
        ok = mailer.send_unlock_request(
            cfg.get("resend_api_key", ""),
            cfg.get("from_email", "NovaBlock <onboarding@resend.dev>"),
            cfg.get("friend_email", ""),
            cfg.get("friend_name", "ami"),
            cfg.get("user_name", "l'utilisateur"),
            wk, total,
            code=new_code,
        )
        if ok:
            config.update_code_hash(new_hash)
            msg = "Email envoyé à ton ami avec le code à utiliser."
            color = "#00b894"
        else:
            msg = f"Échec de l'envoi : {mailer.get_last_error()}"
            color = PRIMARY
        self.root.after(0, lambda: self.feedback_lbl.config(text=msg, fg=color))

    def _enter_code(self) -> None:
        dlg = CodeDialog(self.root)
        self.root.wait_window(dlg.top)
        if dlg.result:
            cfg = config.load()
            if crypto.verify_code(dlg.result, cfg.get("code_hash", "")):
                config.grant_temp_unlock(24)
                blocker.remove_full_block()
                self.feedback_lbl.config(text="✓ Code valide. Filtre désactivé pour 24h.", fg="#00b894")
                self._refresh()
            else:
                self.feedback_lbl.config(text="✗ Code incorrect.", fg=PRIMARY)

    def _request_uninstall(self) -> None:
        if not messagebox.askyesno(
            "Démarrer la désinstallation ?",
            "Cooldown de 7 jours. Pendant ces 7 jours :\n"
            "  • Le filtre reste 100% actif\n"
            "  • Tu peux annuler à tout moment\n"
            "Au bout des 7j il te faudra le code de ton ami pour finaliser.\n\n"
            "Continuer ?",
        ):
            return
        config.start_uninstall_cooldown()
        cfg = config.load()
        mailer.send_uninstall_request(
            cfg.get("resend_api_key", ""),
            cfg.get("from_email", "NovaBlock <onboarding@resend.dev>"),
            cfg.get("friend_email", ""),
            cfg.get("friend_name", "ami"),
            cfg.get("user_name", "l'utilisateur"),
        )
        self.feedback_lbl.config(text="Cooldown 7j démarré. Ton ami a été notifié.", fg=MUTED)
        self._refresh()

    def _cancel_uninstall(self) -> None:
        config.cancel_uninstall_cooldown()
        self.feedback_lbl.config(text="Cooldown annulé.", fg=MUTED)
        self._refresh()

    def _add_custom_site(self) -> None:
        dlg = tk.Toplevel(self.root)
        dlg.title("Bloquer un site")
        dlg.configure(bg=BG)
        _center(dlg, 480, 220)
        dlg.transient(self.root)
        dlg.grab_set()

        tk.Label(dlg, text="Domaine à bloquer", font=FONT_MD, fg=ACCENT, bg=BG).pack(anchor="w", padx=20, pady=(20, 4))
        tk.Label(dlg, text="Exemple : tiktok.com, instagram.com, twitter.com",
                 font=FONT_SM, fg=MUTED, bg=BG).pack(anchor="w", padx=20)
        entry = tk.Entry(dlg, font=FONT_MD, relief="solid", bd=1)
        entry.pack(fill="x", padx=20, pady=8, ipady=4)
        entry.focus_set()
        warn = tk.Label(dlg, text="⚠️  Tu pourras le rajouter mais le retirer demandera le code de ton ami.",
                        font=("Segoe UI", 9), fg=PRIMARY, bg=BG, wraplength=440, justify="left")
        warn.pack(anchor="w", padx=20)

        def _add():
            d = entry.get().strip()
            added = config.add_custom_domain(d)
            if not added:
                self.feedback_lbl.config(text=f"✗ Domaine invalide : {d}", fg=PRIMARY)
                dlg.destroy()
                return
            try:
                blocker.apply_full_block(kill_browsers=False)
            except Exception as e:
                log.exception("apply_full_block failed: %s", e)
            self.feedback_lbl.config(text=f"✓ {added} bloqué. Redémarre tes navigateurs pour effet immédiat.",
                                     fg="#00b894")
            dlg.destroy()
            self._refresh()

        btns = tk.Frame(dlg, bg=BG)
        btns.pack(fill="x", padx=20, pady=12)
        tk.Button(btns, text="Annuler", font=FONT_SM, bg="#ddd", fg=ACCENT,
                  relief="flat", padx=12, pady=6, command=dlg.destroy).pack(side="right", padx=(8, 0))
        tk.Button(btns, text="Bloquer", font=FONT_SM, bg=PRIMARY, fg="white",
                  relief="flat", padx=12, pady=6, command=_add).pack(side="right")
        entry.bind("<Return>", lambda _e: _add())

    def _remove_custom_site(self) -> None:
        customs = config.get_custom_domains()
        if not customs:
            messagebox.showinfo("Aucun site", "Tu n'as ajouté aucun site manuellement.")
            return

        # Step 1 — code required
        code_dlg = CodeDialog(self.root)
        self.root.wait_window(code_dlg.top)
        if not code_dlg.result:
            return
        cfg = config.load()
        if not crypto.verify_code(code_dlg.result, cfg.get("code_hash", "")):
            self.feedback_lbl.config(text="✗ Code incorrect.", fg=PRIMARY)
            return

        # Step 2 — pick which to remove
        dlg = tk.Toplevel(self.root)
        dlg.title("Retirer un site bloqué")
        dlg.configure(bg=BG)
        _center(dlg, 460, 380)
        dlg.transient(self.root)
        dlg.grab_set()

        tk.Label(dlg, text="Sélectionne les sites à retirer", font=FONT_MD, fg=ACCENT, bg=BG).pack(anchor="w", padx=20, pady=(20, 8))

        canvas = tk.Canvas(dlg, bg="white", highlightthickness=0)
        canvas.pack(fill="both", expand=True, padx=20, pady=4)
        inner = tk.Frame(canvas, bg="white")
        canvas.create_window((0, 0), window=inner, anchor="nw")

        vars_: dict[str, tk.BooleanVar] = {}
        for d in customs:
            v = tk.BooleanVar(value=False)
            vars_[d] = v
            tk.Checkbutton(inner, text=d, variable=v, font=FONT_SM, bg="white",
                           fg=ACCENT, anchor="w").pack(fill="x", anchor="w", padx=8, pady=2)
        inner.update_idletasks()
        canvas.config(scrollregion=canvas.bbox("all"))

        def _remove():
            removed = []
            for d, v in vars_.items():
                if v.get() and config.remove_custom_domain(d):
                    removed.append(d)
            if removed:
                try:
                    blocker.apply_full_block(kill_browsers=False)
                except Exception as e:
                    log.exception("apply_full_block: %s", e)
                self.feedback_lbl.config(text=f"✓ Retirés : {', '.join(removed)}", fg="#00b894")
            else:
                self.feedback_lbl.config(text="Aucun site sélectionné.", fg=MUTED)
            dlg.destroy()
            self._refresh()

        btns = tk.Frame(dlg, bg=BG)
        btns.pack(fill="x", padx=20, pady=12)
        tk.Button(btns, text="Annuler", font=FONT_SM, bg="#ddd", fg=ACCENT,
                  relief="flat", padx=12, pady=6, command=dlg.destroy).pack(side="right", padx=(8, 0))
        tk.Button(btns, text="Retirer", font=FONT_SM, bg=PRIMARY, fg="white",
                  relief="flat", padx=12, pady=6, command=_remove).pack(side="right")

    def show(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def run(self) -> None:
        self.root.mainloop()


class CodeDialog:
    """Modal: enter the 25-char unlock code."""

    def __init__(self, parent: tk.Misc):
        self.top = tk.Toplevel(parent)
        self.top.title("Code de déblocage")
        self.top.configure(bg=BG)
        _center(self.top, 480, 240)
        self.top.transient(parent)
        self.top.grab_set()
        self.result: Optional[str] = None
        self._build()

    def _build(self) -> None:
        frm = tk.Frame(self.top, bg=BG, padx=24, pady=20)
        frm.pack(fill="both", expand=True)
        tk.Label(frm, text="Entre le code envoyé à ton ami", font=FONT_MD, fg=ACCENT, bg=BG).pack(anchor="w")
        tk.Label(frm, text="Format : XXXXX-XXXXX-XXXXX-XXXXX-XXXXX",
                 font=FONT_SM, fg=MUTED, bg=BG).pack(anchor="w", pady=(0, 8))
        self.entry = tk.Entry(frm, font=FONT_MONO, relief="solid", bd=1, justify="center")
        self.entry.pack(fill="x", ipady=8)
        self.entry.focus_set()
        btns = tk.Frame(frm, bg=BG)
        btns.pack(fill="x", pady=(16, 0))
        tk.Button(btns, text="Annuler", font=FONT_MD, bg="#ddd", fg=ACCENT,
                  relief="flat", padx=14, pady=6, command=self._cancel).pack(side="right", padx=(8, 0))
        tk.Button(btns, text="Valider", font=FONT_MD, bg=PRIMARY, fg="white",
                  relief="flat", padx=14, pady=6, command=self._ok).pack(side="right")
        self.entry.bind("<Return>", lambda _e: self._ok())

    def _ok(self) -> None:
        self.result = self.entry.get().strip()
        self.top.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.top.destroy()


def _get_window_monitor_geom(hwnd: int) -> Optional[tuple[int, int, int, int]]:
    """Return (left, top, width, height) of the monitor containing hwnd."""
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        MONITOR_DEFAULTTONEAREST = 2
        hmon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
        if not hmon:
            return None

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD),
                        ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT),
                        ("dwFlags", wintypes.DWORD)]

        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if not user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            return None
        r = mi.rcMonitor
        return (r.left, r.top, r.right - r.left, r.bottom - r.top)
    except Exception:
        return None


class BlockedPopup:
    """Full-screen popup shown when a porn URL is detected in the active window.
    Positions itself on the same monitor as the offending browser.

    Uses tk.Toplevel (NOT tk.Tk) — multiple tk.Tk instances in one process are
    flaky on Windows and cause the popup to silently fail to appear."""

    _active: Optional["BlockedPopup"] = None
    _parent_root: Optional[tk.Tk] = None  # set by run_app

    @classmethod
    def set_parent_root(cls, root: tk.Tk) -> None:
        cls._parent_root = root

    @classmethod
    def show(cls, title: str, keyword: str, hwnd: int = 0) -> None:
        # If a popup is already up, just bring it forward
        if cls._active is not None:
            try:
                if cls._active.root.winfo_exists():
                    cls._active.root.lift()
                    cls._active.root.attributes("-topmost", True)
                    cls._active.root.focus_force()
                    return
                else:
                    cls._active = None  # stale reference
            except Exception:
                cls._active = None
        if cls._parent_root is None:
            log.error("BlockedPopup parent root not set; cannot show popup")
            return
        try:
            popup = cls(title, keyword, hwnd)
            cls._active = popup
        except Exception as e:
            log.exception("blocked popup failed: %s", e)
            cls._active = None

    def __init__(self, detected_title: str, keyword: str, hwnd: int = 0):
        self.detected_title = detected_title
        self.keyword = keyword
        self.target_hwnd = hwnd
        self.root = tk.Toplevel(BlockedPopup._parent_root)
        self.root.title("NovaBlock — Site bloqué")
        self.root.configure(bg=PRIMARY)
        self.root.overrideredirect(True)

        geom = _get_window_monitor_geom(hwnd) if hwnd else None
        if geom:
            x, y, w, h = geom
            self.root.geometry(f"{w}x{h}+{x}+{y}")
        else:
            self.root.attributes("-fullscreen", True)

        self.root.attributes("-topmost", True)
        self.root.bind("<Escape>", lambda _e: None)
        self.root.bind("<Alt-F4>", lambda _e: "break")
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)
        self.root.bind("<Destroy>", self._on_destroy)
        self._build()
        self._auto_close_browser_tab()
        self.root.after(150, self._force_focus)
        self.root.after(2000, self._reassert_topmost)

    def _on_destroy(self, event=None) -> None:
        # Triggered when the Toplevel is destroyed — only clear if it's the actual root
        if event is not None and event.widget is not self.root:
            return
        BlockedPopup._active = None

    def _force_focus(self) -> None:
        try:
            self.root.lift()
            self.root.focus_force()
            self.root.attributes("-topmost", True)
        except Exception:
            pass

    def _reassert_topmost(self) -> None:
        try:
            if self.root.winfo_exists():
                self.root.attributes("-topmost", True)
                self.root.lift()
                self.root.after(2000, self._reassert_topmost)
        except Exception:
            pass

    def _auto_close_browser_tab(self) -> None:
        """Aggressive: send Ctrl+W to close the tab AND optionally kill the
        browser process if title still matches after a brief delay."""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            if self.target_hwnd:
                user32.SetForegroundWindow(self.target_hwnd)
                time.sleep(0.05)
            VK_CONTROL = 0x11
            VK_W = 0x57
            KEYEVENTF_KEYUP = 0x0002
            user32.keybd_event(VK_CONTROL, 0, 0, 0)
            user32.keybd_event(VK_W, 0, 0, 0)
            user32.keybd_event(VK_W, 0, KEYEVENTF_KEYUP, 0)
            user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
        except Exception:
            pass
        # Schedule a follow-up kill: if title still contains banned keyword
        # 1s later, force-close the browser process.
        threading.Thread(target=self._followup_kill, daemon=True).start()

    def _followup_kill(self) -> None:
        try:
            time.sleep(1.0)
            import win32gui, win32process, psutil
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return
            title = (win32gui.GetWindowText(hwnd) or "").lower()
            if self.keyword.lower() not in title:
                return
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc = psutil.Process(pid)
            log.warning("Title still contains banned keyword — killing browser PID=%d", pid)
            proc.kill()
        except Exception as e:
            log.debug("followup_kill: %s", e)

    def _build(self) -> None:
        wrap = tk.Frame(self.root, bg=PRIMARY)
        wrap.pack(expand=True)
        card = tk.Frame(wrap, bg="white", padx=48, pady=40)
        card.pack(padx=40, pady=40)
        tk.Label(card, text="🚫", font=("Segoe UI", 72), bg="white", fg=PRIMARY).pack()
        tk.Label(card, text="Contenu adulte bloqué", font=("Segoe UI", 28, "bold"),
                 fg=PRIMARY, bg="white").pack(pady=(0, 8))
        tk.Label(card,
                 text=f"Mot-clé détecté : « {self.keyword} »",
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
        tk.Button(btns, text="Fermer (continuer à être bloqué)", font=FONT_SM,
                  bg="#dfe6e9", fg=ACCENT, relief="flat", padx=14, pady=8,
                  command=self.root.destroy).grid(row=0, column=2, padx=4)

        self.feedback = tk.Label(card, text="", font=FONT_SM, fg=MUTED, bg="white", wraplength=480)
        self.feedback.pack(pady=(20, 0))

    def _request_email(self) -> None:
        self.feedback.config(text="Envoi en cours…", fg=MUTED)
        self.root.update()
        threading.Thread(target=self._do_request_email, daemon=True).start()

    def _do_request_email(self) -> None:
        cfg = config.load()
        new_code = crypto.generate_unlock_code()
        new_hash = crypto.hash_code(new_code)
        wk = config.record_unlock_request()
        total = config.count_requests_total()
        ok = mailer.send_unlock_request(
            cfg.get("resend_api_key", ""),
            cfg.get("from_email", "NovaBlock <onboarding@resend.dev>"),
            cfg.get("friend_email", ""),
            cfg.get("friend_name", "ami"),
            cfg.get("user_name", "l'utilisateur"),
            wk, total,
            code=new_code,
            context=f"Tentative d'accès à un site contenant : « {self.keyword} »",
        )
        if ok:
            config.update_code_hash(new_hash)
            msg = "✓ Email envoyé à ton ami avec le code. Attends qu'il te le donne."
            color = "#00b894"
        else:
            msg = f"✗ Échec d'envoi : {mailer.get_last_error()}"
            color = PRIMARY
        self.root.after(0, lambda: self.feedback.config(text=msg, fg=color))

    def _enter_code(self) -> None:
        dlg = CodeDialog(self.root)
        self.root.wait_window(dlg.top)
        if dlg.result:
            cfg = config.load()
            if crypto.verify_code(dlg.result, cfg.get("code_hash", "")):
                config.grant_temp_unlock(24)
                blocker.remove_full_block()
                self.feedback.config(text="✓ Code valide. Filtre désactivé pour 24h.", fg="#00b894")
                self.root.after(2000, self.root.destroy)
            else:
                self.feedback.config(text="✗ Code incorrect.", fg=PRIMARY)
