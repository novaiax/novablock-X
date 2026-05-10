"""Single-instance lock via a named mutex. Prevents two NovaBlock processes
fighting over hosts file."""
import ctypes
from ctypes import wintypes

MUTEX_NAME = "Global\\NovaBlock_SingleInstance_Mutex"
ERROR_ALREADY_EXISTS = 183

_kernel32 = ctypes.windll.kernel32
_handle = None


def acquire() -> bool:
    global _handle
    _handle = _kernel32.CreateMutexW(None, wintypes.BOOL(True), MUTEX_NAME)
    if not _handle:
        return False
    if ctypes.GetLastError() == ERROR_ALREADY_EXISTS:
        _kernel32.CloseHandle(_handle)
        _handle = None
        return False
    return True


def release() -> None:
    global _handle
    if _handle:
        _kernel32.ReleaseMutex(_handle)
        _kernel32.CloseHandle(_handle)
        _handle = None


def is_running() -> bool:
    """Returns True if a main NovaBlock instance is already running (lock held
    by another process). Used by the headless watchdog to skip ticks that
    would race with the in-process watchdog over the hosts file."""
    h = _kernel32.OpenMutexW(0x100000, False, MUTEX_NAME)  # SYNCHRONIZE
    if h:
        _kernel32.CloseHandle(h)
        return True
    return False
