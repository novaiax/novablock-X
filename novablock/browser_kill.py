"""Force-kill browser processes so they restart and pick up new policies."""
import logging

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

log = logging.getLogger("novablock.browser_kill")

BROWSERS = [
    "chrome.exe", "msedge.exe", "firefox.exe",
    "brave.exe", "opera.exe", "vivaldi.exe",
    "iexplore.exe",
]


def kill_all_browsers() -> int:
    """Kill all running browser processes. Returns count killed.
    User loses tabs but it's necessary to apply DoH policy + flush DNS cache."""
    if not HAS_PSUTIL:
        return 0
    n = 0
    for proc in psutil.process_iter(["name"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if name in BROWSERS:
                proc.kill()
                n += 1
        except Exception:
            pass
    if n:
        log.info("Killed %d browser processes", n)
    return n
