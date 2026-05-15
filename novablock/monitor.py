"""Active window monitor: detects browser navigation to adult sites and triggers
the block popup. Runs as a low-priority background thread. ~0% CPU at idle."""
import logging
import re
import threading
import time
from typing import Callable, Optional

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

# Keywords that match anywhere in the title (substring). Used for unique,
# unambiguous adult-site/term tokens that wouldn't appear inside a normal word.
ADULT_KEYWORDS_SUBSTRING = [
    "porn", "xxx", "milf", "hentai", "onlyfans", "fansly",
    "stripchat", "chaturbate", "xhamster", "pornhub", "xvideos",
    "redtube", "youporn", "spankbang", "xnxx", "porntrex",
    "camgirl", "yandex", "yastatic", "rule34",
    # Common French queries that surface adult content via search engines
    "video x ", "film x ", "video porno", "site porno",
    "ya.ru",
]

# Keywords that must match as a whole word — they are too short or too close
# to legitimate French/English words to be safely matched as substrings.
# Examples of false positives we avoid:
#   "anal"   → "analyse", "national", "analogique"
#   "fap"    → "japanese", "afap"
#   "nude"   → "denude", "Klaus Klude"
#   "tits"   → rare but "tit" appears in some words
#   "naked"  → "naked-eye observation"
ADULT_KEYWORDS_WORD = [
    "nsfw", "nude", "nudes", "naked", "boobs", "tits", "fap",
    "anal", "blowjob", "erotic", "erotique",
    "hardcore", "softcore", "leaked",
    "cam girl", "tube8",
]

# Backward-compat alias (some external code may still reference ADULT_KEYWORDS)
ADULT_KEYWORDS = ADULT_KEYWORDS_SUBSTRING + ADULT_KEYWORDS_WORD


class WindowMonitor:
    def __init__(self, on_detect: Callable[[str, str, int], None],
                 poll_interval: float = 0.5):
        self.on_detect = on_detect
        self.poll_interval = poll_interval
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_pid: int = 0
        self._last_title: str = ""
        self._cooldown_until: float = 0.0
        self._domain_keywords: list[str] = []
        self._load_domains()

    # Common English/French words that happen to be subdomains of porn sites
    # (e.g. articles.rsdnation.com → "articles"). Matched as whole words below,
    # but we also drop them from the keyword list outright to keep the set lean.
    _DOMAIN_KEYWORD_BLACKLIST = {
        "www", "static", "media", "cdn", "images", "video", "videos",
        "search", "articles", "article", "content", "pages", "files",
        "download", "downloads", "upload", "uploads", "support", "forum",
        "forums", "blog", "blogs", "news", "store", "shop", "login",
        "signin", "register", "account", "profile", "settings",
        # Generic web/marketing terms — high false-positive risk when matched
        # in legitimate site titles. None of these are adult-specific.
        "advertising", "advertise", "advertisement", "advertiser",
        "advertisers", "marketing", "analytics", "tracking", "tracker",
        "trackers", "banner", "banners", "popup", "popups", "promotion",
        "promotions", "affiliate", "affiliates", "network", "networks",
        "platform", "service", "services", "system", "systems",
        "website", "websites", "online", "internet", "browser",
        "google", "facebook", "youtube", "twitter",
    }

    def _load_domains(self) -> None:
        # Auto-extraction disabled: parsing 50k blocklist domains for ≥6-char
        # roots produced too many false positives (city names like "annecy",
        # generic terms like "advertising", brand names, etc.) that blocked
        # legitimate sites. The blocklist still DNS-blocks those domains, and
        # ADULT_KEYWORDS covers the title-detection layer with curated terms.
        # If a porn site slips through, add it to ADULT_KEYWORDS_SUBSTRING.
        self._domain_keywords = []

    def start(self) -> None:
        if not HAS_WIN32:
            log.warning("win32gui not available, monitor disabled")
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="NovaBlockMonitor")
        self._thread.start()
        log.info("Monitor started")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _is_browser(self, pid: int) -> bool:
        try:
            name = psutil.Process(pid).name().lower()
            return name in BROWSER_PROCS
        except Exception:
            return False

    def _check_title(self, title: str) -> Optional[str]:
        t = title.lower()
        # Substring match: unique, unambiguous tokens (e.g. "porn" → matches
        # "pornography", "pornhub", "hardcore-porn"…).
        for kw in ADULT_KEYWORDS_SUBSTRING:
            if kw in t:
                return kw
        # Word-boundary match: short or ambiguous keywords ("anal", "fap"…)
        # plus all domain keywords (auto-extracted from the blocklist) which
        # might collide with normal words like "articles".
        words = set(re.findall(r"[a-z0-9]+", t))
        for kw in ADULT_KEYWORDS_WORD:
            # multi-word phrases ("cam girl") aren't in `words`, fall back to
            # substring match for those
            if " " in kw:
                if kw in t:
                    return kw
            elif kw in words:
                return kw
        for d in self._domain_keywords:
            if d in words:
                return d
        return None

    def _loop(self) -> None:
        """Aggressive: re-triggers popup every 3s as long as a banned title
        is on screen. User cannot 'browse around' the popup."""
        while not self._stop.is_set():
            try:
                if time.time() < self._cooldown_until:
                    time.sleep(self.poll_interval)
                    continue
                hwnd = win32gui.GetForegroundWindow()
                if not hwnd:
                    time.sleep(self.poll_interval)
                    continue
                title = win32gui.GetWindowText(hwnd) or ""
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                is_browser = self._is_browser(pid)
                if not is_browser:
                    self._last_pid = pid
                    self._last_title = title
                    time.sleep(self.poll_interval)
                    continue
                hit = self._check_title(title)
                if hit:
                    log.warning("Adult content detected: %r (matched %r) hwnd=%s", title, hit, hwnd)
                    # Short cooldown to avoid spawning 100 popups but ensure
                    # popup re-triggers every 3s while user stays on banned page.
                    self._cooldown_until = time.time() + 3.0
                    try:
                        self.on_detect(title, hit, hwnd)
                    except Exception as e:
                        log.error("on_detect callback failed: %s", e)
                self._last_pid = pid
                self._last_title = title
            except Exception as e:
                log.debug("monitor loop error: %s", e)
            time.sleep(self.poll_interval)
