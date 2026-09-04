"""Mutual recovery for the main app and its companion.

The companion is a separate instance, including separate PyInstaller onefile
resources. The SYSTEM task is the fallback when both processes are stopped.
A privileged administrator can still terminate processes; this is recovery,
not an assertion that a user-space executable is unkillable.
"""
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import process_protect, recovery
from .paths import COMPANION_PID_FILE, MAIN_PID_FILE, ensure_dirs, exe_path

log = logging.getLogger("novablock.companion")
POLL_INTERVAL = 1.0
RELAUNCH_GRACE = 5.0
COMPANION_FLAG = "--companion"
_pending_companion_pid = 0


def _read_pid(p: Path) -> int:
    try:
        return int(p.read_text(encoding="utf-8").strip())
    except Exception:
        return 0


def _pid_alive(pid: int, role: str = "") -> bool:
    """Reject recycled PIDs belonging to a different program or mode.

    AccessDenied is inconclusive: conservatively avoid a duplicate spawn.
    The SYSTEM watchdog separately checks the global main-instance mutex.
    """
    if pid <= 0:
        return False
    try:
        import psutil
        proc = psutil.Process(pid)
        if not proc.is_running():
            return False
        actual_exe = os.path.normcase(os.path.abspath(proc.exe()))
        expected_exe = os.path.normcase(os.path.abspath(sys.executable))
        if actual_exe != expected_exe:
            return False
        argv = proc.cmdline()
        if not getattr(sys, "frozen", False):
            entry = str(Path(__file__).resolve().parent.parent / "__main__.py")
            if not any(os.path.normcase(os.path.abspath(a)) == os.path.normcase(entry)
                       for a in argv[1:] if not a.startswith("-")):
                return False
        if role == "companion":
            return COMPANION_FLAG in argv
        if role == "main":
            return not any(flag in argv for flag in
                           (COMPANION_FLAG, "--watchdog", "--uninstall", "--check", "--reapply", "--self-test"))
        return True
    except ImportError:
        log.error("psutil missing: cannot inspect companion process")
        return False
    except psutil.AccessDenied:
        return psutil.pid_exists(pid)
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        return False
    except Exception as e:
        log.debug("Cannot inspect pid %s: %s", pid, e)
        return False


def _write_pid_file(path: Path, pid: int) -> None:
    ensure_dirs()
    try:
        path.write_text(str(pid), encoding="utf-8")
    except Exception as e:
        log.warning("could not write %s: %s", path, e)


def _command(*args: str) -> list[str]:
    if getattr(sys, "frozen", False):
        return [str(exe_path()), *args]
    entry = Path(__file__).resolve().parent.parent / "__main__.py"
    return [sys.executable, str(entry), *args]


def _spawn(args: list[str]) -> int:
    """Spawn a detached, INDEPENDENT instance, not a PyInstaller worker.

    PyInstaller >=6.9 otherwise reuses the parent's extracted temporary files;
    those may disappear when the parent dies. A recovery child must outlive it.
    """
    try:
        flags = 0
        for flag in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP", "CREATE_NO_WINDOW"):
            flags |= getattr(subprocess, flag, 0)
        env = os.environ.copy()
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        proc = subprocess.Popen(
            args,
            creationflags=flags,
            env=env,
            cwd=str(Path(sys.executable).parent) if getattr(sys, "frozen", False)
                else str(Path(__file__).resolve().parent.parent),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        return proc.pid
    except Exception as e:
        log.error("spawn failed (%s): %s", args, e)
        return 0


def write_main_pid() -> None:
    _write_pid_file(MAIN_PID_FILE, os.getpid())


def spawn_companion() -> int:
    global _pending_companion_pid
    if recovery.recovery_paused():
        return 0
    # Onefile extraction can take longer than RELAUNCH_GRACE. Track the
    # bootloader PID until the actual Python child has written its own PID.
    for pid in (_read_pid(COMPANION_PID_FILE), _pending_companion_pid):
        if _pid_alive(pid, "companion"):
            return pid
    _pending_companion_pid = _spawn(_command(COMPANION_FLAG))
    if _pending_companion_pid:
        log.info("Companion spawned, launcher pid=%d", _pending_companion_pid)
    return _pending_companion_pid


def watch_companion(stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        if recovery.shutdown_requested():
            return
        try:
            if not recovery.recovery_paused() and not _pid_alive(_read_pid(COMPANION_PID_FILE), "companion"):
                spawn_companion()
                if stop_event.wait(RELAUNCH_GRACE):
                    return
                continue
        except Exception as e:
            log.exception("watch_companion error: %s", e)
        if stop_event.wait(POLL_INTERVAL):
            return


def start_companion_supervision() -> threading.Event:
    # Do not erase an updater/uninstaller's active shutdown request.
    stop_event = threading.Event()
    if recovery.shutdown_requested():
        stop_event.set()
        return stop_event
    if not process_protect.harden_current_process():
        log.warning("Process hardening unavailable; scheduled recovery remains required")
    write_main_pid()
    spawn_companion()
    threading.Thread(target=watch_companion, args=(stop_event,),
                     name="NovaBlockCompanionWatcher", daemon=True).start()
    return stop_event


def run_companion_loop() -> int:
    if recovery.shutdown_requested():
        return 0
    process_protect.harden_current_process()
    _write_pid_file(COMPANION_PID_FILE, os.getpid())
    log.info("Companion loop running (pid=%d)", os.getpid())
    pending_main_pid = 0
    while True:
        if recovery.shutdown_requested():
            if _read_pid(COMPANION_PID_FILE) == os.getpid():
                COMPANION_PID_FILE.unlink(missing_ok=True)
            return 0
        try:
            if _pid_alive(_read_pid(MAIN_PID_FILE), "main"):
                pending_main_pid = 0
            elif not recovery.recovery_paused() and not _pid_alive(pending_main_pid, "main"):
                log.warning("Main app is gone — respawning independent instance")
                pending_main_pid = _spawn(_command())
                time.sleep(RELAUNCH_GRACE)
                continue
        except Exception as e:
            log.exception("companion loop error: %s", e)
        time.sleep(POLL_INTERVAL)
