"""Short-lived HTTPS time for code and cooldown authorization decisions.

The local Windows clock is user-adjustable. A trusted sample advances with
time.monotonic() while this process is alive; after a restart or an expired
sample, protected actions wait for a fresh HTTPS Date header.
"""

from datetime import timezone
from email.utils import parsedate_to_datetime
import logging
import threading
import time

import requests


log = logging.getLogger("novablock.trusted_clock")
SOURCES = ("https://api.github.com", "https://www.cloudflare.com")
CACHE_SECONDS = 600.0
_lock = threading.Lock()
_sample_epoch = 0.0
_sample_monotonic = 0.0
_sample_wall = 0.0
_refreshing = False
_next_background_attempt = 0.0


class ClockUnavailable(RuntimeError):
    pass


def cached_now() -> float | None:
    with _lock:
        elapsed = time.monotonic() - _sample_monotonic
        wall_elapsed = time.time() - _sample_wall
        if (_sample_epoch <= 0 or elapsed < 0 or elapsed > CACHE_SECONDS
                or abs(wall_elapsed - elapsed) > 120):
            return None
        return _sample_epoch + elapsed


def _fetch_epoch() -> float:
    samples: list[float] = []
    for url in SOURCES:
        try:
            response = requests.head(
                url, timeout=4, allow_redirects=False,
                headers={"Cache-Control": "no-cache"},
            )
            if not (200 <= response.status_code < 400):
                continue
            header = response.headers.get("Date", "")
            parsed = parsedate_to_datetime(header)
            if parsed.tzinfo is None:
                continue
            samples.append(parsed.astimezone(timezone.utc).timestamp())
        except (requests.RequestException, TypeError, ValueError, OverflowError):
            continue
    if not samples:
        raise ClockUnavailable("No HTTPS time source could be verified")
    if len(samples) > 1 and max(samples) - min(samples) > 120:
        raise ClockUnavailable("HTTPS time sources disagree")
    # The earlier valid sample cannot shorten a seven-day cooldown.
    return min(samples)


def verified_now() -> float:
    cached = cached_now()
    if cached is not None:
        return cached
    epoch = _fetch_epoch()
    with _lock:
        global _sample_epoch, _sample_monotonic, _sample_wall
        _sample_epoch = epoch
        _sample_monotonic = time.monotonic()
        _sample_wall = time.time()
    return epoch


def refresh_in_background() -> None:
    global _refreshing, _next_background_attempt
    if cached_now() is not None:
        return
    with _lock:
        now = time.monotonic()
        if _refreshing or now < _next_background_attempt:
            return
        _refreshing = True
        _next_background_attempt = now + 30

    def fetch() -> None:
        global _refreshing
        try:
            verified_now()
        except ClockUnavailable as exc:
            log.warning("Protected time unavailable: %s", exc)
        finally:
            with _lock:
                _refreshing = False

    threading.Thread(target=fetch, name="NovaBlockClockRefresh", daemon=True).start()
