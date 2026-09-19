"""NovaBlock Windows NT service.

Runs as LocalSystem, which gives us three properties that a user-mode
process (even one with our PROCESS_TERMINATE-denying DACL) cannot match:

  1. Task Manager > Processes lists the underlying svchost or the service
     host, not our binary as an End-Task target. The user can't just
     right-click NovaBlock.exe and pick End task.

  2. Task Manager > Services requires special privileges to Stop the
     service. Even an admin has to accept a UAC prompt via services.msc
     or sc.exe stop, and if we tighten the service DACL (via sc sdset)
     they need to take ownership first, which is a multi-step deliberate
     action rather than one click.

  3. LocalSystem is above the user's session, so a per-user tool that
     tries to enumerate and kill our processes doesn't see us in its
     own PID list.

What the service does:
  - Runs the same headless watchdog work as run_watchdog_headless (hosts
    block, DNS Family lock, browser policies, firewall DoH rules) on a
    5-second cadence.
  - Respawns the main GUI (tray, monitor, popup) when it dies. The GUI
    stays in the user session because it has to show Tk windows, which
    Session 0 isolation forbids to LocalSystem services.
  - Exits cleanly when SHUTDOWN_SENTINEL appears (verified-code uninstall
    path via the app, or update.bat).

The existing scheduled tasks (NovaBlockWatchdog every minute, and the
mutual companion process) stay in place as belt-and-braces fallbacks in
case the service is stopped.
"""
import logging
import os
import subprocess
import time
from pathlib import Path

try:
    import servicemanager
    import win32event
    import win32service
    import win32serviceutil
    HAS_WIN32_SERVICE = True
except ImportError:
    HAS_WIN32_SERVICE = False

log = logging.getLogger("novablock.service")

SERVICE_NAME = "NovaBlockService"
SERVICE_DISPLAY = "NovaBlock Service"
SERVICE_DESCRIPTION = (
    "NovaBlock adult content blocker - system-mode watchdog. "
    "Do not stop; use the app to request an unlock code."
)

# Polling interval for the service main loop.
POLL_INTERVAL_SEC = 5

# Wait grace after respawning the GUI so we don't respawn twice in a row.
SPAWN_GRACE_SEC = 8


def _read_pid(path: Path) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except Exception:
        return 0


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import psutil
        return psutil.pid_exists(pid)
    except Exception:
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            h = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid,
            )
            if h:
                ctypes.windll.kernel32.CloseHandle(h)
                return True
            return False
        except Exception:
            return False


def _spawn_main_gui(exe: str) -> None:
    """Spawn the main GUI in the user session. Cross-session spawn from a
    SYSTEM service is non-trivial, so we go through the standard scheduled
    task NovaBlockApp which is registered under the user's SID. Running
    /Run on it fires an interactive-session launch."""
    try:
        subprocess.run(
            ["schtasks", "/Run", "/TN", "NovaBlockApp"],
            capture_output=True, timeout=10,
            creationflags=(
                subprocess.CREATE_NO_WINDOW
                if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            ),
        )
        log.info("Requested NovaBlockApp scheduled task run (respawn main GUI)")
    except Exception as e:
        log.error("Cross-session spawn via schtasks failed: %s", e)


def _apply_protections_tick() -> None:
    """The same idempotent re-apply cycle the headless watchdog does.
    Kept local to the service so a change in main.run_watchdog_headless
    doesn't accidentally rewire what SYSTEM is doing."""
    from . import blocker, browser_policies, config, firewall

    if not config.is_installed():
        return
    if config.is_temp_unlocked():
        return

    try:
        if not blocker.hosts_block_present():
            blocker.apply_full_block(kill_browsers=False)
        elif not blocker.dns_is_locked():
            blocker.set_family_dns()
    except Exception as e:
        log.warning("hosts/DNS re-apply failed in service: %s", e)

    try:
        if not browser_policies.policies_present():
            browser_policies.apply_all_browser_policies()
    except Exception as e:
        log.warning("browser policies re-apply failed in service: %s", e)

    try:
        if not firewall.doh_blocked():
            firewall.block_doh_endpoints()
    except Exception as e:
        log.warning("firewall re-apply failed in service: %s", e)


def _service_loop(stop_event) -> None:
    """Main service loop. Runs until stop_event is set or the shutdown
    sentinel appears (via recovery.shutdown_requested, which enforces a
    max-age window so a stale marker cannot silently keep the service
    disabled forever)."""
    from .paths import MAIN_PID_FILE
    from . import recovery

    last_spawn_ts = 0.0
    while True:
        # 1. Legitimate shutdown signal (verified-code uninstall / update).
        if recovery.shutdown_requested():
            log.info("Shutdown sentinel present, service exits voluntarily")
            return

        # 2. Do not fight an in-progress updater.
        if not recovery.update_in_progress():
            # 3. Watchdog: relaunch main GUI if the user or a bug killed it.
            try:
                main_pid = _read_pid(MAIN_PID_FILE)
                if not _pid_alive(main_pid):
                    now = time.time()
                    if now - last_spawn_ts >= SPAWN_GRACE_SEC:
                        log.warning("Main GUI process gone, respawning")
                        _spawn_main_gui(str(_this_exe()))
                        last_spawn_ts = now
            except Exception as e:
                log.exception("main-GUI supervision error: %s", e)

            # 4. Re-apply the block if any layer got tampered with.
            try:
                _apply_protections_tick()
            except Exception as e:
                log.exception("protections tick error: %s", e)

        # 5. Wait, but wake early if a stop request comes in.
        if HAS_WIN32_SERVICE and stop_event is not None:
            rc = win32event.WaitForSingleObject(
                stop_event, int(POLL_INTERVAL_SEC * 1000),
            )
            if rc == win32event.WAIT_OBJECT_0:
                return
        else:
            time.sleep(POLL_INTERVAL_SEC)


def _this_exe() -> Path:
    """Absolute path to the NovaBlock.exe currently running as this
    service. Used to figure out the binPath when re-registering the
    service and to spawn the main GUI."""
    import sys as _sys
    if getattr(_sys, "frozen", False):
        return Path(_sys.executable)
    return Path(_sys.argv[0]).resolve()


if HAS_WIN32_SERVICE:

    class NovaBlockService(win32serviceutil.ServiceFramework):
        _svc_name_ = SERVICE_NAME
        _svc_display_name_ = SERVICE_DISPLAY
        _svc_description_ = SERVICE_DESCRIPTION

        def __init__(self, args):
            win32serviceutil.ServiceFramework.__init__(self, args)
            self.stop_event = win32event.CreateEvent(None, 0, 0, None)

        def SvcStop(self) -> None:
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self.stop_event)

        def SvcDoRun(self) -> None:
            servicemanager.LogInfoMsg(f"{SERVICE_NAME} starting")
            try:
                _service_loop(self.stop_event)
            except Exception as e:
                log.exception("service loop crashed: %s", e)
            servicemanager.LogInfoMsg(f"{SERVICE_NAME} stopped")


def run_as_service() -> int:
    """Called from main.py when the process is launched with --service-run.
    Hands control to the Service Control Manager."""
    if not HAS_WIN32_SERVICE:
        log.error("pywin32 service modules not available, cannot run as service")
        return 1
    try:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(NovaBlockService)
        servicemanager.StartServiceCtrlDispatcher()
        return 0
    except Exception as e:
        log.exception("StartServiceCtrlDispatcher failed: %s", e)
        return 1
