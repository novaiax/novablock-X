"""Shared, bounded maintenance guards for automatic process recovery.

No email or configuration writes. These markers coordinate with the existing
updater and verified uninstall; they are not an authentication mechanism.
"""
import time
from pathlib import Path

from .paths import PROGRAM_DATA, SHUTDOWN_SENTINEL

# Same lease length as outils/update.bat. A crashed updater must not leave
# automatic recovery disabled forever. Do not delete markers here: another
# process may have just renewed one.
MAINTENANCE_MAX_AGE = 1800
UPDATE_LOCK = PROGRAM_DATA / "update.lock"


def _recent_marker(path: Path) -> bool:
    try:
        age = time.time() - path.stat().st_mtime
        return -MAINTENANCE_MAX_AGE < age < MAINTENANCE_MAX_AGE
    except FileNotFoundError:
        return False
    except OSError:
        # Avoid racing a legitimate update when its marker cannot be read.
        return True


def shutdown_requested() -> bool:
    """True during the updater's stop/swap stage or verified uninstall."""
    return _recent_marker(SHUTDOWN_SENTINEL)


def update_in_progress() -> bool:
    """True while a recent update lock exists (including download stage)."""
    try:
        started = int(UPDATE_LOCK.read_text(encoding="utf-8").strip())
    except FileNotFoundError:
        return False
    except (OSError, ValueError):
        # A writer may have created the file but not written its timestamp.
        return _recent_marker(UPDATE_LOCK)
    age = time.time() - started
    return -MAINTENANCE_MAX_AGE < age < MAINTENANCE_MAX_AGE


def recovery_paused() -> bool:
    return shutdown_requested() or update_in_progress()
