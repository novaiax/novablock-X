"""Single-instance and hosts-write mutexes, with pointer-safe Win32 calls."""
import ctypes
import logging
from ctypes import wintypes

log = logging.getLogger("novablock.single_instance")
MUTEX_NAME = "Global\\NovaBlock_SingleInstance_Mutex"
HOSTS_MUTEX_NAME = "Global\\NovaBlock_HostsWrite_Mutex"
ERROR_ALREADY_EXISTS = 183
ERROR_ACCESS_DENIED = 5
ERROR_FILE_NOT_FOUND = 2
SYNCHRONIZE = 0x00100000
_WAIT_OBJECT_0 = 0x00000000
_WAIT_ABANDONED = 0x00000080
_WAIT_TIMEOUT = 0x00000102

# Every function accepting/returning a HANDLE needs an explicit signature.
# ctypes defaults to c_int, which can truncate handles on 64-bit Windows.
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateMutexW.restype = wintypes.HANDLE
_kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.OpenMutexW.restype = wintypes.HANDLE
_kernel32.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.CloseHandle.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.ReleaseMutex.restype = wintypes.BOOL
_kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
_kernel32.WaitForSingleObject.restype = wintypes.DWORD
_kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_handle = None


def acquire() -> bool:
    global _handle
    if _handle is not None:
        return True
    ctypes.set_last_error(0)
    handle = _kernel32.CreateMutexW(None, True, MUTEX_NAME)
    error = ctypes.get_last_error()
    if not handle:
        log.warning("Cannot acquire main mutex (WinError %d)", error)
        return False
    if error == ERROR_ALREADY_EXISTS:
        _kernel32.CloseHandle(handle)
        return False
    _handle = handle
    return True


def release() -> None:
    global _handle
    handle, _handle = _handle, None
    if handle is not None:
        try:
            _kernel32.ReleaseMutex(handle)
        finally:
            _kernel32.CloseHandle(handle)


def is_running() -> bool:
    ctypes.set_last_error(0)
    handle = _kernel32.OpenMutexW(SYNCHRONIZE, False, MUTEX_NAME)
    error = ctypes.get_last_error()
    if handle:
        _kernel32.CloseHandle(handle)
        return True
    # AccessDenied means the object may belong to another security context;
    # it is not evidence of absence. Avoid spawning duplicates in that case.
    if error == ERROR_ACCESS_DENIED:
        return True
    if error not in (0, ERROR_FILE_NOT_FOUND):
        log.warning("Cannot inspect main mutex (WinError %d)", error)
    return False


class HostsWriteLock:
    """Best-effort serialization of hosts writes, preserving previous policy."""
    def __init__(self, timeout_ms: int = 30000) -> None:
        self.timeout_ms = timeout_ms
        self._handle = None
        self.acquired = False

    def __enter__(self) -> "HostsWriteLock":
        try:
            self._handle = _kernel32.CreateMutexW(None, False, HOSTS_MUTEX_NAME)
            if not self._handle:
                return self
            rc = _kernel32.WaitForSingleObject(self._handle, self.timeout_ms)
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
