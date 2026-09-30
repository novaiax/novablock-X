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
    "iexplore.exe", "tor.exe", "ucbrowser.exe", "ucbrowserlauncher.exe",
]


def is_uc_browser_process(name: str, executable: str = "") -> bool:
    name = (name or "").lower()
    path = (executable or "").lower().replace("/", "\\")
    return name in {"ucbrowser.exe", "ucbrowserlauncher.exe"} or any(
        marker in path for marker in ("\\ucbrowser\\", "\\uc browser\\", "\\ucweb\\")
    )


def close_uc_browser_processes() -> int:
    """Close an unverified browser before it can bypass system DNS filtering."""
    if not HAS_PSUTIL:
        return 0
    closed = 0
    for proc in psutil.process_iter(["name", "exe"]):
        try:
            if is_uc_browser_process(proc.info.get("name"), proc.info.get("exe")):
                proc.kill()
                closed += 1
        except Exception as exc:
            log.warning("Could not close UC Browser process: %s", exc)
    if closed:
        log.warning("Closed %d UC Browser process(es) because filtering cannot be verified", closed)
    return closed


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
