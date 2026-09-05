"""Fast foreground-browser monitor.

Adult detection uses the page title. User-added sites use the real active-tab
URL through Windows UI Automation, with title matching as a fallback. Custom
configuration is reloaded live from config.dat.
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

try:
    from pywinauto import Desktop
    HAS_UIA = True
except Exception:
    Desktop = None
    HAS_UIA = False

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

_CUSTOM_TOKEN_BLACKLIST = {
    "www", "com", "net", "org", "fr", "io", "app", "co", "tv",
    "home", "index", "login", "account", "search", "www2",
}


class WindowMonitor:
    def __init__(self, on_detect: Callable[[str, str, int], None],
                 poll_interval: float = 0.5):
        self.on_detect = on_detect
        # 10 checks/s: visually immediate once the browser exposes the URL/title.
        self.poll_interval = min(max(float(poll_interval), 0.05), 0.10)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._cooldown_until = 0.0
        self._custom_cache_until = 0.0
        self._custom_tokens: list[str] = []
        self._custom_domains: list[str] = []
        self._custom_urls: list[str] = []
        self._browser_cache: dict[int, tuple[float, bool]] = {}
        self._url_cache: dict[int, tuple[float, str]] = {}

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
        log.info("Monitor started (poll=%.0fms, URL-UIA=%s)",
                 self.poll_interval * 1000, HAS_UIA)

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
        return ok

    @staticmethod
    def _normalize_host(raw: str) -> str:
        raw = (raw or "").strip().lower()
        if not raw:
            return ""
        if "://" not in raw:
            raw = "https://" + raw.lstrip("/")
        try:
            return (urlsplit(raw).hostname or "").lower().removeprefix("www.")
        except Exception:
            return ""

    @staticmethod
    def _normalize_url(raw: str) -> str:
        raw = (raw or "").strip()
        if not raw:
            return ""
        if "://" not in raw:
            raw = "https://" + raw.lstrip("/")
        try:
            p = urlsplit(raw)
            host = (p.hostname or "").lower().removeprefix("www.")
            if not host:
                return ""
            path = p.path or "/"
            if p.query:
                path += "?" + p.query
            return host + path
        except Exception:
            return ""

    @staticmethod
    def _host_tokens(raw: str) -> set[str]:
        host = WindowMonitor._normalize_host(raw)
        if not host:
            return set()
        tokens = {host}
        for label in host.split("."):
            if label not in _CUSTOM_TOKEN_BLACKLIST and len(label) >= 3:
                tokens.add(label)
        if host == "x.com":
            tokens.add("__x_brand__")
        return tokens

    def _reload_custom_config(self) -> None:
        now = time.monotonic()
        if now < self._custom_cache_until:
            return
        self._custom_cache_until = now + 0.25
        try:
            from . import config
            cfg = config.load()
            domains: list[str] = []
            urls: list[str] = []
            tokens: set[str] = set()
            for raw in cfg.get("custom_blocked_domains", []) or []:
                host = self._normalize_host(str(raw))
                if host:
                    domains.append(host)
                    tokens.update(self._host_tokens(host))
            for raw in cfg.get("custom_blocked_urls", []) or []:
                normalized = self._normalize_url(str(raw))
                if normalized:
                    urls.append(normalized)
                    tokens.update(self._host_tokens(str(raw)))
            self._custom_domains = sorted(set(domains), key=len, reverse=True)
            self._custom_urls = sorted(set(urls), key=len, reverse=True)
            self._custom_tokens = sorted(tokens, key=len, reverse=True)
        except Exception as e:
            log.debug("custom popup config reload failed: %s", e)

    @staticmethod
    def _token_in_title(token: str, title_lower: str) -> bool:
        if token == "__x_brand__":
            return bool(re.search(r"(?:^|[\s|\-–—•])x(?:$|[\s|\-–—•])", title_lower))
        if "." in token:
            return token in title_lower
        return bool(re.search(r"(?<![a-z0-9])" + re.escape(token) + r"(?![a-z0-9])",
                              title_lower))

    def _match_custom_url(self, raw_url: str) -> Optional[str]:
        """Return the configured custom entry matching the actual active URL."""
        self._reload_custom_config()
        if not raw_url or (not self._custom_domains and not self._custom_urls):
            return None
        normalized = self._normalize_url(raw_url)
        host = self._normalize_host(raw_url)
        if not host:
            return None
        for domain in self._custom_domains:
            if host == domain or host.endswith("." + domain):
                return domain
        for configured in self._custom_urls:
            # Precise URL entries match that page and descendants/query variants.
            if normalized == configured or normalized.startswith(configured.rstrip("/") + "/") \
               or normalized.startswith(configured + "?"):
                return configured
        return None

    @staticmethod
    def _looks_like_url(value: str) -> bool:
        v = (value or "").strip().lower()
        if not v or " " in v[:20]:
            return False
        return v.startswith(("http://", "https://")) or "." in v.split("/")[0]

    def _read_active_browser_url(self, hwnd: int) -> str:
        """Read address-bar URL with Windows UI Automation.

        pywinauto exposes Chrome/Edge/Brave/Firefox address-bar controls via
        UIA. We inspect edit/combobox values and keep only URL-looking values.
        A very short cache avoids hammering COM while preserving ~100ms latency.
        """
        if not HAS_UIA or not self._custom_domains and not self._custom_urls:
            return ""
        now = time.monotonic()
        cached = self._url_cache.get(hwnd)
        if cached and now < cached[0]:
            return cached[1]
        found = ""
        try:
            window = Desktop(backend="uia").window(handle=hwnd)
            controls = []
            for control_type in ("Edit", "ComboBox"):
                try:
                    controls.extend(window.descendants(control_type=control_type))
                except Exception:
                    pass
            # The address bar is normally near the top and exposes a Value
            # pattern. Match against configured sites first to avoid mistaking
            # a page form field containing a URL for the browser address bar.
            candidates: list[str] = []
            for control in controls:
                for getter in ("get_value", "window_text"):
                    try:
                        value = str(getattr(control, getter)() or "").strip()
                    except Exception:
                        continue
                    if value and self._looks_like_url(value):
                        candidates.append(value)
            for value in candidates:
                if self._match_custom_url(value):
                    found = value
                    break
            if not found and candidates:
                found = candidates[0]
        except Exception as e:
            log.debug("UIA URL read failed hwnd=%s: %s", hwnd, e)
        self._url_cache[hwnd] = (now + 0.08, found)
        return found

    def _check_title(self, title: str) -> Optional[str]:
        t = title.lower()
        self._reload_custom_config()
        # Fallback for browsers/pages where UIA address-bar access is absent.
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
                    self._reload_custom_config()
                    hit = None
                    if self._custom_domains or self._custom_urls:
                        active_url = self._read_active_browser_url(hwnd)
                        hit = self._match_custom_url(active_url)
                        if hit:
                            log.warning("Custom site URL detected: %r (matched %r) hwnd=%s",
                                        active_url, hit, hwnd)
                    if not hit:
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
