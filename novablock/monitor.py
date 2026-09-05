"""Fast foreground-browser monitor.

Adult detection uses the page title. User-added sites are different: they are
matched only against the browser address bar after navigation is engaged.
Merely typing, displaying or mentioning a custom-site address must never show
a popup.
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

# Accessible names used by common browsers for their address bar. Geometry is
# also checked, so localization differences do not make this list mandatory.
_ADDRESS_NAME_HINTS = (
    "address", "adresse", "omnibox", "url", "search or enter",
    "search google or type a url", "rechercher ou saisir",
    "rechercher avec", "entrer une adresse", "saisir une adresse",
)


class WindowMonitor:
    def __init__(self, on_detect: Callable[[str, str, int], None],
                 poll_interval: float = 0.5):
        self.on_detect = on_detect
        # 10 checks/s: visually immediate once navigation is committed.
        self.poll_interval = min(max(float(poll_interval), 0.05), 0.10)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._cooldown_until = 0.0
        self._custom_cache_until = 0.0
        self._custom_domains: list[str] = []
        self._custom_urls: list[str] = []
        self._browser_cache: dict[int, tuple[float, bool]] = {}
        self._address_cache: dict[int, tuple[float, str, bool]] = {}

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
        log.info("Monitor started (poll=%.0fms, navigation-UIA=%s)",
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

    def _reload_custom_config(self) -> None:
        now = time.monotonic()
        if now < self._custom_cache_until:
            return
        self._custom_cache_until = now + 0.25
        try:
            from . import config
            # The getters apply the custom allowlist (including movix.cash).
            domains = [self._normalize_host(v) for v in config.get_custom_domains()]
            urls = [self._normalize_url(v) for v in config.get_custom_urls()]
            self._custom_domains = sorted({d for d in domains if d}, key=len, reverse=True)
            self._custom_urls = sorted({u for u in urls if u}, key=len, reverse=True)
        except Exception as e:
            log.debug("custom popup config reload failed: %s", e)

    def _match_custom_url(self, raw_url: str) -> Optional[str]:
        """Match only an actual browser address, never arbitrary visible text."""
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
            if (normalized == configured
                    or normalized.startswith(configured.rstrip("/") + "/")
                    or normalized.startswith(configured + "?")):
                return configured
        return None

    @staticmethod
    def _looks_like_url(value: str) -> bool:
        v = (value or "").strip().lower()
        if not v or " " in v[:20]:
            return False
        return v.startswith(("http://", "https://")) or "." in v.split("/")[0]

    @staticmethod
    def _control_has_focus(control) -> bool:
        try:
            return bool(control.has_keyboard_focus())
        except Exception:
            try:
                return bool(control.element_info.element.CurrentHasKeyboardFocus)
            except Exception:
                return False

    @staticmethod
    def _control_name(control) -> str:
        try:
            return str(control.element_info.name or "").strip().lower()
        except Exception:
            try:
                return str(control.window_text() or "").strip().lower()
            except Exception:
                return ""

    @staticmethod
    def _control_is_near_browser_top(control, window) -> bool:
        """Reject page form fields that merely contain a URL.

        The address bar lives in the browser chrome, near the top edge. We
        accept only controls inside the top 22% (minimum 140px) of the window.
        """
        try:
            cr = control.rectangle()
            wr = window.rectangle()
            max_y = wr.top + max(140, int((wr.bottom - wr.top) * 0.22))
            return cr.top >= wr.top and cr.top <= max_y
        except Exception:
            return False

    def _read_address_bar(self, hwnd: int) -> tuple[str, bool]:
        """Return (address_text, address_bar_has_keyboard_focus).

        A matching URL is deliberately ignored while the address bar has
        keyboard focus. That is the key distinction between *typing a site*
        and *having actually navigated to it*. Once Enter commits navigation,
        browsers normally move focus out of the omnibox and detection becomes
        active on the next ~100ms tick.
        """
        if not HAS_UIA or (not self._custom_domains and not self._custom_urls):
            return "", False
        now = time.monotonic()
        cached = self._address_cache.get(hwnd)
        if cached and now < cached[0]:
            return cached[1], cached[2]

        best_url = ""
        best_focused = False
        best_y = 10**9
        try:
            window = Desktop(backend="uia").window(handle=hwnd)
            controls = []
            for control_type in ("Edit", "ComboBox"):
                try:
                    controls.extend(window.descendants(control_type=control_type))
                except Exception:
                    pass

            for control in controls:
                if not self._control_is_near_browser_top(control, window):
                    continue
                name = self._control_name(control)
                values: list[str] = []
                for getter in ("get_value", "window_text"):
                    try:
                        value = str(getattr(control, getter)() or "").strip()
                    except Exception:
                        continue
                    if value and value not in values:
                        values.append(value)
                url_value = next((v for v in values if self._looks_like_url(v)), "")
                if not url_value:
                    continue
                # Prefer explicitly named address controls, otherwise choose the
                # highest URL-looking edit/combobox in browser chrome.
                try:
                    y = control.rectangle().top
                except Exception:
                    y = best_y
                named_address = any(hint in name for hint in _ADDRESS_NAME_HINTS)
                if named_address:
                    y -= 10000
                if y < best_y:
                    best_y = y
                    best_url = url_value
                    best_focused = self._control_has_focus(control)
        except Exception as e:
            log.debug("UIA address read failed hwnd=%s: %s", hwnd, e)

        self._address_cache[hwnd] = (now + 0.06, best_url, best_focused)
        return best_url, best_focused

    def _match_committed_custom_navigation(self, hwnd: int) -> Optional[str]:
        """Custom popup gate: URL must match AND address editing must be over."""
        self._reload_custom_config()
        if not self._custom_domains and not self._custom_urls:
            return None
        address, editing = self._read_address_bar(hwnd)
        if editing:
            # Typing/pasting/reading a URL in the omnibox is NOT navigation.
            return None
        return self._match_custom_url(address)

    def _check_title(self, title: str) -> Optional[str]:
        """Adult-content title detection only.

        Custom sites are intentionally absent here. A custom site's name may
        appear in another page, search result, message, document, or title and
        must not trigger anything unless the browser is actually navigating to
        that custom URL.
        """
        t = title.lower()
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
                    hit = self._match_committed_custom_navigation(hwnd)
                    if hit:
                        log.warning("Committed custom navigation detected: %r hwnd=%s", hit, hwnd)
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
