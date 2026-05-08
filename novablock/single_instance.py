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
