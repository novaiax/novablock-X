"""NovaBlock entry point.

Modes:
  (no args)        -> setup wizard, or tray + watchdog + monitor.
  --watchdog       -> headless repair and interactive-app recovery.
  --uninstall      -> verified uninstall after the cooldown.
  --self-test PATH -> side-effect-free packaged runtime check for release CI.
"""
import argparse
import ctypes
import logging
import os
import sys
import threading
import time
from logging.handlers import RotatingFileHandler

from . import config, blocker, persistence, single_instance, companion, recovery
from .paths import HEARTBEAT_FILE, LOG_FILE, PROGRAM_DATA, ensure_dirs


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
    import subprocess
    params = subprocess.list2cmdline(sys.argv[1:])
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, params, None, 1
    )


def run_setup() -> bool:
    from .gui import SetupWizard
    wiz = SetupWizard(EMBEDDED_RESEND_KEY, EMBEDDED_FROM_EMAIL)
    return wiz.run()


def _migrate_hosts_if_youtube_present() -> None:
    """Remove legacy Restricted Mode and newly whitelisted hosts entries."""
    log = logging.getLogger("novablock.migration")
    try:
        from .paths import WINDOWS_HOSTS
        if not WINDOWS_HOSTS.exists():
            return
        content = WINDOWS_HOSTS.read_text(encoding="utf-8", errors="ignore")
        if "216.239.38.119" in content:
            log.info("Detected legacy YouTube Restricted Mode hosts entry — rewriting block")
            blocker.apply_full_block(kill_browsers=False)
            return
        for d in blocker.DOMAIN_WHITELIST:
            if f" {d}\n" in content or f" {d}\r" in content:
                log.info("Detected whitelisted domain %s still in hosts — rewriting", d)
                blocker.apply_full_block(kill_browsers=False)
                return
    except Exception as e:
        log.warning("youtube hosts migration check failed: %s", e)


def ensure_persistence() -> None:
    """Refresh task actions in place; never delete the recovery safety net.

    Both installers use schtasks /Create /F. In particular, do not delete the
    interactive task that may have just launched this very process.
    """
    log = logging.getLogger("novablock.persistence_check")
    _migrate_hosts_if_youtube_present()
    for label, install in (
        ("SYSTEM watchdog task", persistence.install_scheduled_task),
        ("interactive app task", persistence.install_logon_task),
        ("startup registry", persistence.add_startup_registry),
        ("startup shortcut", persistence.add_startup_shortcut),
    ):
        try:
            if not install():
                log.error("Could not refresh %s", label)
        except Exception as e:
            log.warning("Could not refresh %s: %s", label, e)


def run_app() -> None:
    """Main app loop: tray + watchdog + monitor + hidden status window."""
    from .custom_status import StatusWindow
    from .popup import BlockedPopup
    from .watchdog import Watchdog
    from .monitor import WindowMonitor
    from .tray import Tray

    log = logging.getLogger("novablock.main")
    companion_stop = companion.start_companion_supervision()
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

    sentinel_stop = threading.Event()

    def _sentinel_poller():
        while not sentinel_stop.is_set():
            if recovery.shutdown_requested():
                log.warning("Shutdown sentinel detected — main app exits voluntarily")
                try:
                    status.root.after(0, status.root.quit)
                except Exception:
                    os._exit(0)
                return
            if sentinel_stop.wait(1.0):
                return

    threading.Thread(target=_sentinel_poller, name="NovaBlockSentinelPoller", daemon=True).start()

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
        companion_stop.set()
        sentinel_stop.set()
        monitor.stop()
        watchdog.stop()
        tray.stop()


def run_watchdog_headless() -> None:
    """Repair blocking, then recover the app IN THE USER'S SESSION."""
    log = logging.getLogger("novablock.headless")
    if not config.is_installed():
        log.info("Not installed — headless watchdog exits")
        return
    if recovery.recovery_paused():
        log.info("Update/verified shutdown in progress — recovery paused")
        return

    main_alive = single_instance.is_running()
    try:
        if config.is_temp_unlocked():
            log.info("Temp unlocked — skipping filter repair, not app recovery")
            return
        heartbeat_fresh = False
        try:
            if HEARTBEAT_FILE.exists():
                last_beat = int(HEARTBEAT_FILE.read_text(encoding="utf-8").strip() or "0")
                heartbeat_fresh = 0 <= time.time() - last_beat < 180
        except Exception:
            pass
        if main_alive and heartbeat_fresh:
            log.debug("Main app alive and ticking — headless skip re-apply")
            return

        if not blocker.hosts_block_present() or not blocker.dns_is_locked():
            log.warning("Block missing and main app not ticking — re-applying from headless")
            blocker.apply_full_block(kill_browsers=False)
        try:
            persistence.add_startup_registry()
            if not persistence.startup_shortcut_present():
                persistence.add_startup_shortcut()
            if not persistence.logon_task_exists():
                log.error("Interactive app task missing — launch NovaBlock normally to repair it")
        except Exception as e:
            log.warning("persistence self-heal failed: %s", e)
    finally:
        if not main_alive:
            recovery.request_app_restart()


def run_diagnostic() -> int:
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
    lines.append("[Persistence / reprise]")
    lines.append(f"   Watchdog task    : {persistence.task_exists()}")
    lines.append(f"   Logon task       : {persistence.logon_task_exists()}")
    lines.append(f"   Startup shortcut : {persistence.startup_shortcut_present()}")
    lines.append(f"   Main mutex       : {single_instance.is_running()}")
    lines.append(f"   Companion PID    : {companion._read_pid(companion.COMPANION_PID_FILE)}")
    lines.append(f"   Maintenance      : {recovery.recovery_paused()}")
    lines.append("")
    lines.append("=" * 60)
    lines.append("Si Hosts=False OU DNS=False OU Firewall=False :")
    lines.append("relance NovaBlock.exe --reapply (admin) puis redémarre tes browsers")
    lines.append("=" * 60)
    ctypes.windll.user32.MessageBoxW(0, "\n".join(lines), "NovaBlock — Diagnostic", 0x40)
    return 0


def run_uninstall_check() -> int:
    from .gui import CodeDialog
    import tkinter as tk

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
    try:
        from .paths import SHUTDOWN_SENTINEL, MAIN_PID_FILE, COMPANION_PID_FILE
        ensure_dirs()
        SHUTDOWN_SENTINEL.write_text(str(int(time.time())), encoding="utf-8")
        time.sleep(3)
    except Exception:
        pass
    blocker.remove_full_block()
    persistence.remove_scheduled_task()
    persistence.remove_logon_task()
    persistence.remove_startup_registry()
    persistence.remove_startup_shortcut()
    try:
        from .paths import CONFIG_FILE
        CONFIG_FILE.unlink(missing_ok=True)
        MAIN_PID_FILE.unlink(missing_ok=True)
        COMPANION_PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass
    ctypes.windll.user32.MessageBoxW(0, "NovaBlock désinstallé.", "NovaBlock", 0x40)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="NovaBlock", add_help=False)
    parser.add_argument("--watchdog", action="store_true", help="Headless repair and app recovery")
    parser.add_argument("--companion", action="store_true", help="Mutual-watchdog companion")
    parser.add_argument("--uninstall", action="store_true", help="Finalize uninstall")
    parser.add_argument("--check", action="store_true", help="Run diagnostic")
    parser.add_argument("--reapply", action="store_true", help="Force re-apply blocking")
    parser.add_argument("--self-test", metavar="REPORT", help="Packaged runtime check; no installation")
    args, _ = parser.parse_known_args()
    if args.self_test:
        from .release_selftest import run
        return run(args.self_test)

    setup_logging()
    log = logging.getLogger("novablock.main")
    log.info("NovaBlock starting (argv=%s)", sys.argv)
    if args.companion:
        return companion.run_companion_loop() or 0
    if args.watchdog:
        if not is_admin():
            log.error("Watchdog tick has no admin rights — aborting")
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
    if recovery.shutdown_requested():
        log.info("Maintenance shutdown requested — normal launch deferred")
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
