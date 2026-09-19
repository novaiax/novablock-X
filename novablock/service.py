"""Lightweight NovaBlock LocalSystem guardian.

This service deliberately does NOT touch DNS, hosts, browser policies, or the
firewall. Those protections remain exactly on the v1.0.33 watchdog paths.

Its only job is process recovery:
  * run outside the interactive user session as LocalSystem;
  * notice when the main NovaBlock process is gone;
  * ask the existing NovaBlockApp scheduled task to relaunch it;
  * restart quickly if the guardian itself crashes.

This keeps the anti-kill layer isolated from networking so terminating the GUI
cannot trigger the v1.0.34 DNS/reconfiguration regression.
"""
import logging
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

log = logging.getLogger("novablock.guardian")

SERVICE_NAME = "NovaBlockGuardian"
SERVICE_DISPLAY = "NovaBlock Guardian"
SERVICE_DESCRIPTION = (
    "NovaBlock lightweight guardian - relaunches the interactive blocker only."
)

POLL_INTERVAL_SEC = 1.0
SPAWN_GRACE_SEC = 6.0


def _read_pid(path: Path) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except Exception:
        return 0


def _main_alive(pid: int) -> bool:
    """Validate that the PID still belongs to the main NovaBlock executable."""
    if pid <= 0:
        return False
    try:
        import psutil
        proc = psutil.Process(pid)
        if not proc.is_running():
            return False

        import sys
        expected = str(Path(sys.executable).resolve()).lower()
        actual = str(Path(proc.exe()).resolve()).lower()
        if actual != expected:
            return False

        argv = proc.cmdline()
        non_main_flags = {
            "--companion", "--watchdog", "--service-run", "--uninstall",
            "--check", "--reapply", "--self-test",
        }
        return not any(flag in argv for flag in non_main_flags)
    except Exception:
        return False


def _request_main_restart() -> bool:
    """Launch the GUI through the existing interactive scheduled task."""
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.run(
            ["schtasks", "/Run", "/TN", "NovaBlockApp"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=flags,
        )
        if proc.returncode != 0:
            log.warning("NovaBlockApp launch failed: %s", proc.stderr.strip())
            return False
        log.info("Requested NovaBlockApp interactive relaunch")
        return True
    except Exception as e:
        log.warning("NovaBlockApp launch failed: %s", e)
        return False


def _service_loop(stop_event) -> None:
    from . import config, process_protect, recovery
    from .paths import MAIN_PID_FILE

    # Best-effort extra friction. A sufficiently privileged administrator can
    # still override a process DACL, so service recovery remains mandatory.
    try:
        process_protect.harden_current_process()
    except Exception:
        pass

    last_spawn = 0.0
    while True:
        if recovery.shutdown_requested():
            log.info("Verified shutdown requested; guardian exits")
            return

        if config.is_installed() and not recovery.update_in_progress():
            pid = _read_pid(MAIN_PID_FILE)
            if not _main_alive(pid):
                now = time.monotonic()
                if now - last_spawn >= SPAWN_GRACE_SEC:
                    _request_main_restart()
                    last_spawn = now

        if HAS_WIN32_SERVICE and stop_event is not None:
            rc = win32event.WaitForSingleObject(
                stop_event, int(POLL_INTERVAL_SEC * 1000)
            )
            if rc == win32event.WAIT_OBJECT_0:
                return
        else:
            time.sleep(POLL_INTERVAL_SEC)


if HAS_WIN32_SERVICE:
    class NovaBlockGuardianService(win32serviceutil.ServiceFramework):
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
            _service_loop(self.stop_event)
            servicemanager.LogInfoMsg(f"{SERVICE_NAME} stopped")


def run_as_service() -> int:
    if not HAS_WIN32_SERVICE:
        log.error("pywin32 service modules unavailable")
        return 1
    try:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(NovaBlockGuardianService)
        servicemanager.StartServiceCtrlDispatcher()
        return 0
    except Exception as e:
        log.exception("StartServiceCtrlDispatcher failed: %s", e)
        return 1
