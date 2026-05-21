"""Mutual watchdog: a second process that resurrects the main app.

Two processes:
  * main app (NovaBlock.exe, no args) — does the actual blocking.
  * companion (NovaBlock.exe --companion) — does nothing but watch.

Each writes its PID to a file in C:\\ProgramData\\NovaBlock and polls
the other's PID file every second. If the watched PID is gone, the
watcher spawns a fresh instance of it.

To actually stop NovaBlock you'd need to terminate BOTH processes
within the same ~1s poll window, AND the SYSTEM scheduled task would
have to miss its next 1-minute tick. Task Manager kills one process
at a time, so the survivor always relaunches its dead partner before
the user can click the second 'End task'.

The companion process is intentionally minimal — no Tk, no GUI, no
network. Just a poll loop. Smaller surface area = less to crash.
"""
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import process_protect
from .paths import (
    COMPANION_PID_FILE,
    MAIN_PID_FILE,
    SHUTDOWN_SENTINEL,
    ensure_dirs,
    exe_path,
)

log = logging.getLogger("novablock.companion")

POLL_INTERVAL = 1.0          # seconds between alive-checks
RELAUNCH_GRACE = 5.0         # wait after relaunch before next check
COMPANION_FLAG = "--companion"


# ---------- helpers ----------

def _read_pid(p: Path) -> int:
    try:
        return int(p.read_text(encoding="utf-8").strip())
    except Exception:
        return 0


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import psutil
        return psutil.pid_exists(pid)
    except Exception:
        # Fallback via OpenProcess
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            h = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid
            )
            if h:
                ctypes.windll.kernel32.CloseHandle(h)
                return True
            return False
        except Exception:
            return False


def _write_pid_file(path: Path, pid: int) -> None:
    ensure_dirs()
    try:
        path.write_text(str(pid), encoding="utf-8")
    except Exception as e:
        log.warning("could not write %s: %s", path, e)


def _spawn(args: list[str]) -> int:
    """Spawn a detached child. Returns its PID, 0 on failure."""
    try:
        flags = 0
        if hasattr(subprocess, "DETACHED_PROCESS"):
            flags |= subprocess.DETACHED_PROCESS
        if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            flags |= subprocess.CREATE_NEW_PROCESS_GROUP
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            flags |= subprocess.CREATE_NO_WINDOW
        proc = subprocess.Popen(
            args,
            creationflags=flags,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        return proc.pid
    except Exception as e:
        log.error("spawn failed (%s): %s", args, e)
        return 0


# ---------- main-side hooks ----------

def write_main_pid() -> None:
    """Called once by main app at startup."""
    _write_pid_file(MAIN_PID_FILE, os.getpid())


def spawn_companion() -> int:
    """Launch the companion process. Idempotent: if a companion PID is
    already alive, returns it without spawning a second one."""
    existing = _read_pid(COMPANION_PID_FILE)
    if _pid_alive(existing):
        log.info("Companion already alive (pid=%d)", existing)
        return existing
    args = [str(exe_path()), COMPANION_FLAG]
    pid = _spawn(args)
    if pid:
        log.info("Companion spawned, pid=%d", pid)
    return pid


def watch_companion(stop_event: threading.Event) -> None:
    """Background thread (in the main app). Restarts the companion if it
    dies. Exits cleanly when stop_event is set OR when the shutdown
    sentinel is present (legitimate uninstall)."""
    while not stop_event.is_set():
        if SHUTDOWN_SENTINEL.exists():
            log.info("Shutdown sentinel present — main no longer guards companion")
            return
        try:
            cpid = _read_pid(COMPANION_PID_FILE)
            if not _pid_alive(cpid):
                log.warning("Companion process is gone — respawning")
                spawn_companion()
                # Let the new companion settle before next check.
                if stop_event.wait(RELAUNCH_GRACE):
                    return
                continue
        except Exception as e:
            log.exception("watch_companion error: %s", e)
        if stop_event.wait(POLL_INTERVAL):
            return


def start_companion_supervision() -> threading.Event:
    """One-shot helper: harden self, write own PID, spawn companion, and
    start the watcher thread. Returns the stop_event so the caller can
    cancel supervision at shutdown."""
    # Clear any stale shutdown sentinel from a previous (uninstall) session.
    # If we're starting normally, supervision must be active.
    try:
        SHUTDOWN_SENTINEL.unlink(missing_ok=True)
    except Exception:
        pass
    process_protect.harden_current_process()
    write_main_pid()
    spawn_companion()
    stop_event = threading.Event()
    t = threading.Thread(
        target=watch_companion,
        args=(stop_event,),
        name="NovaBlockCompanionWatcher",
        daemon=True,
    )
    t.start()
    return stop_event


# ---------- companion-side entry point ----------

def run_companion_loop() -> int:
    """Entry point when launched with --companion. Hardens itself, then
    polls the main PID file forever, relaunching the main app whenever
    it dies. Exits cleanly when the shutdown sentinel appears (this is
    how the verified-code uninstall path breaks the mutual-resurrection
    loop — the companion can't be killed from outside, but it can be
    asked to exit by an authenticated caller)."""
    process_protect.harden_current_process()
    _write_pid_file(COMPANION_PID_FILE, os.getpid())
    log.info("Companion loop running (pid=%d)", os.getpid())

    while True:
        if SHUTDOWN_SENTINEL.exists():
            log.info("Shutdown sentinel present — companion exits voluntarily")
            try:
                COMPANION_PID_FILE.unlink(missing_ok=True)
            except Exception:
                pass
            return 0
        try:
            main_pid = _read_pid(MAIN_PID_FILE)
            if not _pid_alive(main_pid):
                log.warning("Main app is gone — respawning")
                _spawn([str(exe_path())])
                time.sleep(RELAUNCH_GRACE)
                continue
        except Exception as e:
            log.exception("companion loop error: %s", e)
        time.sleep(POLL_INTERVAL)
