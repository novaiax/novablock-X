"""Bounded maintenance guards and interactive-session recovery.

No email or configuration writes. The existing updater and verified uninstall
use these markers for coordination; markers are not authentication tokens.
"""
import logging
import time
from pathlib import Path

from .paths import PROGRAM_DATA, SHUTDOWN_SENTINEL, LOGON_TASK_NAME

log = logging.getLogger("novablock.recovery")
MAINTENANCE_MAX_AGE = 1800
UPDATE_LOCK = PROGRAM_DATA / "update.lock"


def _recent_marker(path: Path) -> bool:
    try:
        age = time.time() - path.stat().st_mtime
        return -MAINTENANCE_MAX_AGE < age < MAINTENANCE_MAX_AGE
    except FileNotFoundError:
        return False
    except OSError:
        # Do not race a legitimate update whose marker cannot be read.
        return True


def shutdown_requested() -> bool:
    return _recent_marker(SHUTDOWN_SENTINEL)


def update_in_progress() -> bool:
    try:
        started = int(UPDATE_LOCK.read_text(encoding="utf-8").strip())
    except FileNotFoundError:
        return False
    except (OSError, ValueError):
        return _recent_marker(UPDATE_LOCK)
    age = time.time() - started
    return -MAINTENANCE_MAX_AGE < age < MAINTENANCE_MAX_AGE


def recovery_paused() -> bool:
    return shutdown_requested() or update_in_progress()


def request_app_restart() -> bool:
    """Ask the existing InteractiveToken task to restart the GUI.

    Never Popen the GUI as SYSTEM: that would put it in session 0, invisible
    to the user. schtasks /Run uses the account/session saved in NovaBlockApp.
    A successful request is not proof that startup has finished; subsequent
    watchdog ticks recheck the actual main mutex.
    """
    from . import config, persistence, single_instance
    if recovery_paused() or not config.is_installed():
        return False
    if single_instance.is_running():
        return False
    if not persistence.logon_task_exists():
        log.error("Cannot recover GUI: NovaBlockApp task missing; launch the app to repair registration")
        return False
    try:
        code, out, err = persistence._run(
            ["schtasks", "/Run", "/TN", LOGON_TASK_NAME], timeout=15
        )
        if code != 0:
            log.error("Interactive restart request failed (%s): %s %s", code, out, err)
            return False
        log.warning("Main app absent: requested interactive restart via %s", LOGON_TASK_NAME)
        return True
    except Exception as e:
        log.error("Interactive restart request failed: %s", e)
        return False
