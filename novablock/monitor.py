"""Fast foreground-browser monitor.

Adult keywords and user-added sites both trigger the existing fullscreen
BlockedPopup. Custom entries are read from config at runtime, so they survive
updates and newly-added entries become active without restarting NovaBlock.
"""
import logging
import re
import threading
import time
from typing import Callable, Optional
from urllib.parse import urlsplit

try:
    import win32gui
    import win32process
    import psutil
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

log = logging.getLogger("novablock.monitor")

BROWSER_PROCS = {
    "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe",
    "opera.exe", "vivaldi.exe", "iexplore.exe", "tor.exe",
}

ADULT_KEYWORDS_SUBSTRING = [
    "porn", "xxx", "milf", "hentai", "onlyfans", "fansly",
    "stripchat", "chaturbate", "xhamster", "pornhub", "xvideos",
    "redtube", "youporn", "spankbang", "xnxx", "porntrex",
    "camgirl", "yandex", "yastatic", "rule34",
    "video x ", "film x ", "video porno", "site porno", "ya.ru",
    "brazzers", "bangbros", "naughtyamerica", "evilangel",
    "realitykings", "bellesa", "twistys", "vixenx",
    "pornstar", "porngif", "pornpic", "porntube", "amateurporn",
    "sexstories", "literotica", "imagefap", "fapdu", "fappening",
    "javhd", "javbus", "javdoe", "javfinder",
    "cumtribute", "cumshow", "cumpilation",
    "tnaflix", "elephantlist", "definebabe", "babesource",
    "motherless", "heavy-r", "thumbzilla", "drtuber",
    "kink.com", "wickedpictures", "digitalplayground",
]

ADULT_KEYWORDS_WORD = [
    "nsfw", "nude", "nudes", "naked", "boobs", "tits", "fap",
    "anal", "blowjob", "erotic", "erotique", "hardcore", "softcore",
    "leaked", "cam girl", "tube8", "sex", "sexe", "sexy", "fuck",
    "fucking", "pussy", "cock", "cocks", "dick", "dicks", "tit",
    "cum", "cums", "cumshot", "cumshots", "creampie", "creampies",
    "jizz", "semen", "bukkake", "deepthroat", "deepthroating",
    "gangbang", "gangbanged", "threesome", "foursome", "handjob",
    "handjobs", "rimjob", "footjob", "pegging", "fingering", "horny",
    "bbw", "gilf", "dilf", "twink", "ahegao", "gape", "gaping",
    "kink", "kinky", "fetish", "femdom", "bdsm", "shemale", "tranny",
    "trans porn", "pawg", "thicc", "yiff", "snuff", "incest",
    "stepmom", "stepmoms", "stepsis", "stepsister", "stepdaughter",
    "stepson", "stepbro", "stepbrother", "slut", "sluts", "whore",
    "whores", "thot", "thots", "webcam girl", "live cam", "camgirl",
    "leaks", "leak pack", "of leaks", "fansleaks", "r4r", "ddlg", "ddlb",
]
ADULT_KEYWORDS = ADULT_KEYWORDS_SUBSTRING + ADULT_KEYWORDS_WORD

# Very generic domain labels should never become title triggers.
_CUSTOM_TOKEN_BLACKLIST = {
    "www", "com", "net", "org", "fr", "io", "app", "co", "tv",
    "home", "index", "login", "account", "search", "www2",
}


class WindowMonitor:
    def __init__(self, on_detect: Callable[[str, str, int], None],
                 poll_interval: float = 0.5):
        self.on_detect = on_detect
        # Popup latency matters more than the caller's legacy 1s setting.
        # 100ms is effectively immediate to a human while remaining cheap.
        self.poll_interval = min(max(float(poll_interval), 0.05), 0.10)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._cooldown_until = 0.0
        self._custom_cache_until = 0.0
        self._custom_tokens: list[str] = []
        self._browser_cache: dict[int, tuple[float, bool]] = {}

    def start(self) -> None:
        if not HAS_WIN32:
            log.warning("win32gui not available, monitor disabled")
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="NovaBlockMonitor")
        self._thread.start()
        log.info("Monitor started (poll=%.0fms)", self.poll_interval * 1000)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _is_browser(self, pid: int) -> bool:
        now = time.monotonic()
        cached = self._browser_cache.get(pid)
        if cached and now < cached[0]:
            return cached[1]
        try:
            ok = psutil.Process(pid).name().lower() in BROWSER_PROCS
        except Exception:
            ok = False
        self._browser_cache[pid] = (now + 5.0, ok)
        if len(self._browser_cache) > 64:
            self._browser_cache = {
                p: value for p, value in self._browser_cache.items()
                if now < value[0]
            }
        return ok

    @staticmethod
    def _host_tokens(raw: str) -> set[str]:
        raw = (raw or "").strip().lower()
        if not raw:
            return set()
        if "://" not in raw:
            raw = "https://" + raw.lstrip("/")
        try:
            parsed = urlsplit(raw)
            host = (parsed.hostname or "").lower().removeprefix("www.")
        except Exception:
            return set()
        if not host:
            return set()
        tokens = {host}
        labels = [p for p in host.split(".") if p]
        # Brand/site label. For subdomains, include useful labels as well.
        for label in labels:
            if label not in _CUSTOM_TOKEN_BLACKLIST and len(label) >= 3:
                tokens.add(label)
        # x.com is intentionally supported despite the one-character brand.
        if host == "x.com":
            tokens.add("__x_brand__")
        return tokens

    def _reload_custom_tokens(self) -> None:
        now = time.monotonic()
        if now < self._custom_cache_until:
            return
        self._custom_cache_until = now + 0.25
        try:
            from . import config
            cfg = config.load()
            tokens: set[str] = set()
            for raw in cfg.get("custom_blocked_domains", []) or []:
                tokens.update(self._host_tokens(str(raw)))
            for raw in cfg.get("custom_blocked_urls", []) or []:
                tokens.update(self._host_tokens(str(raw)))
            self._custom_tokens = sorted(tokens, key=len, reverse=True)
        except Exception as e:
            log.debug("custom popup trigger reload failed: %s", e)

    @staticmethod
    def _token_in_title(token: str, title_lower: str) -> bool:
        if token == "__x_brand__":
            return bool(re.search(r"(?:^|[\s|\-–—•])x(?:$|[\s|\-–—•])", title_lower))
        if "." in token:
            return token in title_lower
        # Brand labels are matched as words so e.g. "threads" does not hit
        # an unrelated longer word containing the same letters.
        return bool(re.search(r"(?<![a-z0-9])" + re.escape(token) + r"(?![a-z0-9])",
                              title_lower))

    def _check_title(self, title: str) -> Optional[str]:
        t = title.lower()
        self._reload_custom_tokens()
        # User-added sites first: this is the explicit user intent and should
        # trigger the same popup as adult detection.
        for token in self._custom_tokens:
            if self._token_in_title(token, t):
                return token.replace("__x_brand__", "x.com")
        for kw in ADULT_KEYWORDS_SUBSTRING:
            if kw in t:
                return kw
        words = set(re.findall(r"[a-z0-9]+", t))
        for kw in ADULT_KEYWORDS_WORD:
            if " " in kw:
                if kw in t:
                    return kw
            elif kw in words:
                return kw
        return None

    def _loop(self) -> None:
        """Poll the foreground browser every ~100ms and trigger immediately."""
        while not self._stop.is_set():
            try:
                if time.monotonic() < self._cooldown_until:
                    self._stop.wait(self.poll_interval)
                    continue
                hwnd = win32gui.GetForegroundWindow()
                if not hwnd:
                    self._stop.wait(self.poll_interval)
                    continue
                title = win32gui.GetWindowText(hwnd) or ""
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if self._is_browser(pid):
                    hit = self._check_title(title)
                    if hit:
                        log.warning("Blocked trigger detected: %r (matched %r) hwnd=%s",
                                    title, hit, hwnd)
                        self._cooldown_until = time.monotonic() + 3.0
                        try:
                            self.on_detect(title, hit, hwnd)
                        except Exception as e:
                            log.error("on_detect callback failed: %s", e)
            except Exception as e:
                log.debug("monitor loop error: %s", e)
            self._stop.wait(self.poll_interval)
