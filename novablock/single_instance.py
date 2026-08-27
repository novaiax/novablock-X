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


# ---------------------------------------------------------------------------
# Cross-process hosts-write lock
#
# is_running() alone cannot serialise hosts writes at boot: the scheduled-task
# watchdog and the main app start within milliseconds of each other, and the
# watchdog checks is_running() BEFORE the main app has reached acquire().
# Both then conclude they are alone and rewrite hosts simultaneously, which
# produced "hosts write PermissionError" on every boot and left a pending
# migration permanently unapplied. This mutex is held for the duration of the
# actual write, so the loser waits instead of colliding.
# ---------------------------------------------------------------------------

HOSTS_MUTEX_NAME = "Global\\NovaBlock_HostsWrite_Mutex"

_WAIT_OBJECT_0 = 0x00000000
_WAIT_ABANDONED = 0x00000080
_WAIT_TIMEOUT = 0x00000102

_kernel32.CreateMutexW.restype = wintypes.HANDLE
_kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.WaitForSingleObject.restype = wintypes.DWORD
_kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]


class HostsWriteLock:
    """Context manager serialising hosts writes across NovaBlock processes.

    Never raises: if the mutex cannot be created or the wait times out we
    proceed anyway. Blocking a block re-apply because of lock trouble would
    be worse than a rare collision, which the caller already retries."""

    def __init__(self, timeout_ms: int = 30000) -> None:
        self.timeout_ms = timeout_ms
        self._handle = None
        self.acquired = False

    def __enter__(self) -> "HostsWriteLock":
        try:
            self._handle = _kernel32.CreateMutexW(None, wintypes.BOOL(False), HOSTS_MUTEX_NAME)
            if not self._handle:
                return self
            rc = _kernel32.WaitForSingleObject(self._handle, wintypes.DWORD(self.timeout_ms))
            # WAIT_ABANDONED means the previous holder died mid-write; the
            # mutex is ours now and the caller rewrites the file wholesale
            # anyway, so treat it as acquired.
            self.acquired = rc in (_WAIT_OBJECT_0, _WAIT_ABANDONED)
        except Exception:
            self.acquired = False
        return self

    def __exit__(self, *exc) -> bool:
        try:
            if self._handle:
                if self.acquired:
                    _kernel32.ReleaseMutex(self._handle)
                _kernel32.CloseHandle(self._handle)
        except Exception:
            pass
        self._handle = None
        self.acquired = False
        return False


def hosts_write_lock(timeout_ms: int = 30000) -> HostsWriteLock:
    return HostsWriteLock(timeout_ms)
