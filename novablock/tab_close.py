"""Close exactly one tab in the browser window that triggered NovaBlock.

This module deliberately never terminates the browser process. The target
HWND is captured by the monitor when the popup is created; on explicit user
dismissal we restore/focus that same browser window and send one Ctrl+W.
"""
import ctypes
import logging
import time
from ctypes import wintypes

log = logging.getLogger("novablock.tab_close")

WM_NULL = 0x0000
SW_RESTORE = 9
VK_CONTROL = 0x11
VK_W = 0x57
KEYEVENTF_KEYUP = 0x0002


def close_one_tab(hwnd: int) -> bool:
    """Close one active tab in *hwnd* and never kill the browser process.

    Returns True when the key sequence was sent to a valid target window.
    Windows may still reject foreground activation in unusual desktop states;
    callers should simply keep the popup closed rather than escalating to a
    process kill.
    """
    if not hwnd:
        return False

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    # Explicit signatures matter on 64-bit Windows.
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    user32.AttachThreadInput.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.BringWindowToTop.argtypes = [wintypes.HWND]
    user32.BringWindowToTop.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.SetFocus.argtypes = [wintypes.HWND]
    user32.SetFocus.restype = wintypes.HWND
    kernel32.GetCurrentThreadId.argtypes = []
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD

    if not user32.IsWindow(hwnd):
        return False

    pid = wintypes.DWORD(0)
    target_tid = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    current_tid = kernel32.GetCurrentThreadId()
    attached = False
    try:
        if target_tid and target_tid != current_tid:
            attached = bool(user32.AttachThreadInput(current_tid, target_tid, True))

        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        try:
            user32.SetFocus(hwnd)
        except Exception:
            pass
        # Give the browser a brief moment to become the keyboard target.
        time.sleep(0.08)

        # Exactly one Ctrl+W sequence: closes the active tab in this window.
        user32.keybd_event(VK_CONTROL, 0, 0, 0)
        user32.keybd_event(VK_W, 0, 0, 0)
        user32.keybd_event(VK_W, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
        log.info("Sent one Ctrl+W to browser hwnd=%s pid=%s", hwnd, pid.value)
        return True
    except Exception as e:
        log.warning("Could not close target tab hwnd=%s: %s", hwnd, e)
        return False
    finally:
        if attached:
            try:
                user32.AttachThreadInput(current_tid, target_tid, False)
            except Exception:
                pass
