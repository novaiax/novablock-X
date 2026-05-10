"""NovaBlock entry point.

Modes:
  (no args)        → if not installed: setup wizard. Else: tray + watchdog + monitor.
  --watchdog       → headless mode (called by scheduled task / boot).
  --uninstall      → finalize uninstall (only works if cooldown done + valid code).
"""
import argparse
import ctypes
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler

from . import config, blocker, persistence, single_instance
from .paths import LOG_FILE, PROGRAM_DATA, ensure_dirs

def _load_embedded() -> tuple[str, str]:
    try:
        from . import _keys
        return (
            getattr(_keys, "RESEND_KEY", ""),
            getattr(_keys, "FROM_EMAIL", "NovaBlock <onboarding@resend.dev>"),
        )
    except ImportError:
        return (
            os.environ.get("NOVABLOCK_RESEND_KEY", ""),
            os.environ.get("NOVABLOCK_FROM_EMAIL", "NovaBlock <onboarding@resend.dev>"),
        )


EMBEDDED_RESEND_KEY, EMBEDDED_FROM_EMAIL = _load_embedded()


def setup_logging() -> None:
    ensure_dirs()
    handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> None:
    params = " ".join(f'"{a}"' for a in sys.argv[1:])
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, params, None, 1
    )


def run_setup() -> bool:
    from .gui import SetupWizard
    wiz = SetupWizard(EMBEDDED_RESEND_KEY, EMBEDDED_FROM_EMAIL)
    return wiz.run()


def ensure_persistence() -> None:
    """At every launch, make sure the scheduled task, registry, and Startup
    shortcut all point to the CURRENT exe path. Three layers so a missing or
    tampered one doesn't kill autostart. In-place updates: overwrite the .exe,
    relaunch, and all three are auto-refreshed."""
    log = logging.getLogger("novablock.persistence_check")
    try:
        if not persistence.task_exists():
            log.info("Scheduled task missing — re-installing")
            persistence.install_scheduled_task()
        else:
            # Re-create to ensure the exe path is up-to-date (handles moves/updates)
            persistence.remove_scheduled_task()
            persistence.install_scheduled_task()
            log.info("Scheduled task refreshed to current exe path")
        # Logon task: launches full app (tray + monitor) at user logon, with
        # HighestAvailable privileges so the manifest UAC prompt is suppressed
        # for admin users. This is the layer that actually starts the app at
        # boot — HKLM\\Run and Startup folder shortcuts are blocked by UAC.
        if persistence.logon_task_exists():
            persistence.remove_logon_task()
        persistence.install_logon_task()
        persistence.add_startup_registry()
        persistence.add_startup_shortcut()
    except Exception as e:
        log.warning("ensure_persistence: %s", e)


def run_app() -> None:
    """Main app loop: tray + watchdog + monitor + hidden status window."""
    from .gui import StatusWindow, BlockedPopup
    from .watchdog import Watchdog
    from .monitor import WindowMonitor
    from .tray import Tray

    log = logging.getLogger("novablock.main")

    # Refresh persistence so updates work without reinstall
    ensure_persistence()

    status = StatusWindow()
    status.root.withdraw()
    BlockedPopup.set_parent_root(status.root)

    def trigger_block_popup(title: str, keyword: str, hwnd: int = 0) -> None:
        if config.is_temp_unlocked():
            return
        try:
            status.root.after(0, lambda: BlockedPopup.show(title, keyword, hwnd))
        except Exception as e:
            log.error("popup trigger failed: %s", e)

    monitor = WindowMonitor(on_detect=trigger_block_popup, poll_interval=1.0)
    watchdog = Watchdog(interval=30)

    monitor.start()
    watchdog.start()

    def show_status() -> None:
        try:
            status.root.after(0, status.show)
        except Exception:
            pass

    def quit_attempt() -> None:
        from tkinter import messagebox
        def _do():
            messagebox.showwarning(
                "NovaBlock",
                "Pour fermer NovaBlock, utilise le bouton 'Désinstaller' (cooldown 7j)\n"
                "et le code envoyé à ton ami. C'est volontaire."
            )
            status.show()
        status.root.after(0, _do)

    tray = Tray(on_open=show_status, on_quit_attempt=quit_attempt)
    tray.start()

    try:
        status.root.mainloop()
    finally:
        monitor.stop()
        watchdog.stop()
        tray.stop()


def run_watchdog_headless() -> None:
    """Called by scheduled task. Ensures block is in place AND repairs missing
    persistence layers (registry Run key, Startup shortcut). Runs as SYSTEM, so
    has rights to write to HKLM\\Run and the Common Startup folder."""
    log = logging.getLogger("novablock.headless")
    if not config.is_installed():
        log.info("Not installed — headless watchdog exits")
        return
    if config.is_temp_unlocked():
        log.info("Temp unlocked — skipping re-apply")
        return
    if not blocker.hosts_block_present() or not blocker.dns_is_locked():
        log.warning("Block missing — re-applying from headless")
        # NEVER kill browsers from the headless watchdog — would close
        # browsers every minute. Browser kill is only for install.
        blocker.apply_full_block(kill_browsers=False)
    # Self-heal persistence: if HKLM\Run, Startup shortcut, or the logon task
    # got tampered, re-create them. The watchdog scheduled task itself is not
    # re-installed here to avoid recursion (it IS what's calling us). The
    # logon task is recreated only if missing — refreshing it would require
    # re-resolving the user SID, which doesn't make sense from SYSTEM context.
    try:
        persistence.add_startup_registry()
        if not persistence.startup_shortcut_present():
            log.info("Startup shortcut missing — re-creating")
            persistence.add_startup_shortcut()
        if not persistence.logon_task_exists():
            log.warning("Logon task missing — cannot recreate from SYSTEM context (needs interactive user SID)")
    except Exception as e:
        log.warning("persistence self-heal failed: %s", e)


def run_diagnostic() -> int:
    """Print a status report on what is and isn't actually working."""
    from . import browser_policies, firewall
    cfg = config.load()
    lines = ["=" * 60, "NovaBlock — Diagnostic", "=" * 60, ""]

    lines.append(f"Installé : {config.is_installed()}")
    lines.append(f"Admin    : {blocker.is_admin()}")
    lines.append(f"Friend   : {cfg.get('friend_email','-')}")
    lines.append("")

    has_hosts = blocker.hosts_block_present()
    lines.append(f"[Hosts file] block présent : {has_hosts}")
    if has_hosts:
        try:
            content = blocker.WINDOWS_HOSTS.read_text(encoding="utf-8", errors="ignore")
            yandex = content.lower().count("yandex")
            pornhub = content.lower().count("pornhub")
            lines.append(f"   yandex entries  : {yandex}")
            lines.append(f"   pornhub entries : {pornhub}")
            lines.append(f"   total lines     : {len(content.splitlines())}")
        except Exception as e:
            lines.append(f"   read error: {e}")

    lines.append("")
    dns_ok = blocker.dns_is_locked()
    lines.append(f"[DNS] forcé sur Cloudflare Family : {dns_ok}")

    lines.append("")
    pol_ok = browser_policies.policies_present()
    lines.append(f"[Browser policies] DoH off + incognito off : {pol_ok}")

    lines.append("")
    fw_ok = firewall.doh_blocked()
    lines.append(f"[Firewall] DoH endpoints bloqués : {fw_ok}")

    lines.append("")
    lines.append("[Persistence]")
    lines.append(f"   Watchdog task    : {persistence.task_exists()}")
    lines.append(f"   Logon task       : {persistence.logon_task_exists()}")
    lines.append(f"   Startup shortcut : {persistence.startup_shortcut_present()}")

    lines.append("")
    lines.append("=" * 60)
    lines.append("Si Hosts=False OU DNS=False OU Firewall=False :")
    lines.append("relance NovaBlock.exe --reapply (admin) puis redémarre tes browsers")
    lines.append("=" * 60)

    msg = "\n".join(lines)
    ctypes.windll.user32.MessageBoxW(0, msg, "NovaBlock — Diagnostic", 0x40)
    return 0


def run_uninstall_check() -> int:
    from .gui import CodeDialog
    import tkinter as tk
    from tkinter import messagebox

    if not config.is_installed():
        return 0
    remaining = config.uninstall_cooldown_remaining()
    if remaining < 0:
        ctypes.windll.user32.MessageBoxW(
            0,
            "Lance la désinstallation depuis l'app (cooldown 7j obligatoire).",
            "NovaBlock", 0x10,
        )
        return 1
    if remaining > 0:
        d = remaining // 86400
        h = (remaining % 86400) // 3600
        ctypes.windll.user32.MessageBoxW(
            0,
            f"Cooldown encore en cours : {d}j {h}h restantes.",
            "NovaBlock", 0x10,
        )
        return 1
    root = tk.Tk()
    root.withdraw()
    dlg = CodeDialog(root)
    root.wait_window(dlg.top)
    root.destroy()
    if not dlg.result:
        return 1
    from . import crypto
    cfg = config.load()
    if not crypto.verify_code(dlg.result, cfg.get("code_hash", "")):
        ctypes.windll.user32.MessageBoxW(0, "Code incorrect.", "NovaBlock", 0x10)
        return 1
    blocker.remove_full_block()
    persistence.remove_scheduled_task()
    persistence.remove_logon_task()
    persistence.remove_startup_registry()
    persistence.remove_startup_shortcut()
    try:
        from .paths import CONFIG_FILE
        CONFIG_FILE.unlink(missing_ok=True)
    except Exception:
        pass
    ctypes.windll.user32.MessageBoxW(0, "NovaBlock désinstallé.", "NovaBlock", 0x40)
    return 0


def main() -> int:
    setup_logging()
    log = logging.getLogger("novablock.main")
    log.info("NovaBlock starting (argv=%s)", sys.argv)

    parser = argparse.ArgumentParser(prog="NovaBlock", add_help=False)
    parser.add_argument("--watchdog", action="store_true", help="Headless watchdog tick (used by scheduler)")
    parser.add_argument("--uninstall", action="store_true", help="Finalize uninstall")
    parser.add_argument("--check", action="store_true", help="Run diagnostic")
    parser.add_argument("--reapply", action="store_true", help="Force re-apply blocking")
    args, _ = parser.parse_known_args()

    # --watchdog must be invoked by the scheduled task running as SYSTEM.
    # Triggering UAC from a headless boot context fails silently and the
    # process dies — leaving NovaBlock un-launched at every reboot. So in
    # watchdog mode we NEVER attempt elevation: if we're not admin, the
    # scheduled task is misconfigured and must be re-installed by the
    # interactive app on next launch.
    if args.watchdog:
        if not is_admin():
            log.error("Watchdog tick has no admin rights — scheduled task is NOT running as SYSTEM. Aborting tick.")
            return 1
        run_watchdog_headless()
        return 0

    if not is_admin():
        log.warning("Not admin — re-launching with elevation")
        relaunch_as_admin()
        return 0

    if args.uninstall:
        return run_uninstall_check()

    if args.check:
        return run_diagnostic()

    if args.reapply:
        if config.is_installed():
            blocker.apply_full_block()
            ctypes.windll.user32.MessageBoxW(
                0, "Blocage réappliqué (hosts + DNS + browser policies).",
                "NovaBlock", 0x40,
            )
        return 0

    if not config.is_installed():
        ok = run_setup()
        if not ok:
            return 1
        time.sleep(0.5)

    if not single_instance.acquire():
        log.info("Another NovaBlock instance is already running")
        return 0

    try:
        run_app()
    finally:
        single_instance.release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
