import json
import time
from typing import Any
from urllib.parse import urlsplit

from .crypto import encrypt_machine, decrypt_machine
from .paths import CONFIG_FILE, ensure_dirs


# Sites intentionally excluded from user-defined popup monitoring.
# movix.cash remains protected by the normal adult-keyword monitor, but simply
# visiting the streaming site must not trigger a custom-site popup.
CUSTOM_SITE_ALLOWLIST = {"movix.cash"}

DEFAULTS: dict[str, Any] = {
    "version": 1,
    "friend_email": "",
    "friend_name": "",
    "user_email": "",
    "user_name": "",
    "code_hash": "",
    "install_ts": 0,
    "unlock_requests": [],
    "temp_unlock_until": 0,
    "uninstall_initiated_at": 0,
    "last_weekly_report": 0,
    "weekly_report_enabled": True,
    "resend_api_key": "",
    "from_email": "novablock@resend.dev",
    "code_rotation_ts": 0,
    "code_rotation_days": 7,
    # Legacy network-block keys retained only for migration from <=1.0.31.
    "custom_blocked_domains": [],
    "custom_blocked_urls": [],
    # v1.0.32+: user-added sites live here and are popup-only.
    "custom_popup_domains": [],
    "custom_popup_urls": [],
    "custom_popup_only_migrated": False,
    # v1.0.34+: exact user-defined words/phrases that trigger a popup in the
    # active browser title, address bar or focused editable field.
    "custom_popup_words": [],
    "machine_name": "",
}


def _normalize_domain(d: str) -> str:
    d = (d or "").strip().lower()
    for prefix in ("https://", "http://"):
        if d.startswith(prefix):
            d = d[len(prefix):]
    if d.startswith("www."):
        d = d[4:]
    d = d.split("/")[0].split(":")[0]
    return d


def _normalize_url(u: str) -> str:
    u = (u or "").strip()
    if not u:
        return ""
    if not (u.startswith("http://") or u.startswith("https://")):
        u = "https://" + u.lstrip("/")
    return u


def _normalize_popup_word(word: str) -> str:
    """Canonical form for a user-defined popup word/phrase.

    Matching is case-insensitive and exact at word boundaries. Whitespace is
    collapsed so accidental double spaces do not create duplicate rules.
    """
    value = " ".join(str(word or "").strip().lower().split())
    if not value or len(value) > 120:
        return ""
    return value


def _url_host(u: str) -> str:
    raw = _normalize_url(u)
    if not raw:
        return ""
    try:
        return (urlsplit(raw).hostname or "").lower().removeprefix("www.")
    except Exception:
        return ""


def _is_custom_allowed_host(host: str) -> bool:
    host = (host or "").lower().removeprefix("www.")
    return any(host == allowed or host.endswith("." + allowed)
               for allowed in CUSTOM_SITE_ALLOWLIST)


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _combined_popup_domains(cfg: dict[str, Any]) -> list[str]:
    # Include legacy values until migration has persisted them, so an update
    # can never make the user's custom popup list appear to vanish.
    values = list(cfg.get("custom_popup_domains", []) or [])
    values += list(cfg.get("custom_blocked_domains", []) or [])
    domains = [_normalize_domain(str(v)) for v in values]
    return _dedupe([
        d for d in domains if d and not _is_custom_allowed_host(d)
    ])


def _combined_popup_urls(cfg: dict[str, Any]) -> list[str]:
    values = list(cfg.get("custom_popup_urls", []) or [])
    values += list(cfg.get("custom_blocked_urls", []) or [])
    urls = [_normalize_url(str(v)) for v in values]
    return _dedupe([
        u for u in urls if u and not _is_custom_allowed_host(_url_host(u))
    ])


def migrate_custom_sites_to_popup_only() -> bool:
    """Move <=1.0.31 custom blocks to popup-only storage exactly once.

    The old keys are emptied so stale data cannot be reused by old network
    layers. movix.cash is discarded during migration.
    """
    cfg = load()
    if cfg.get("custom_popup_only_migrated"):
        return False
    cfg["custom_popup_domains"] = _combined_popup_domains(cfg)
    cfg["custom_popup_urls"] = _combined_popup_urls(cfg)
    cfg["custom_blocked_domains"] = []
    cfg["custom_blocked_urls"] = []
    cfg["custom_popup_only_migrated"] = True
    save(cfg)
    return True


def add_custom_domain(domain: str) -> str:
    """Add a domain to the popup-only monitor list."""
    d = _normalize_domain(domain)
    if not d or "." not in d or " " in d or _is_custom_allowed_host(d):
        return ""
    cfg = load()
    customs = _combined_popup_domains(cfg)
    if d not in customs:
        customs.append(d)
    cfg["custom_popup_domains"] = _dedupe(customs)
    cfg["custom_blocked_domains"] = []
    save(cfg)
    return d


def remove_custom_domain(domain: str) -> bool:
    d = _normalize_domain(domain)
    cfg = load()
    customs = _combined_popup_domains(cfg)
    if d not in customs:
        return False
    customs.remove(d)
    cfg["custom_popup_domains"] = customs
    cfg["custom_blocked_domains"] = []
    save(cfg)
    return True


def get_popup_domains() -> list[str]:
    return _combined_popup_domains(load())


def add_custom_url(url: str) -> str:
    """Add a precise URL to the popup-only monitor list."""
    u = _normalize_url(url)
    if not u or " " in u or "." not in u or _is_custom_allowed_host(_url_host(u)):
        return ""
    cfg = load()
    customs = _combined_popup_urls(cfg)
    if u not in customs:
        customs.append(u)
    cfg["custom_popup_urls"] = _dedupe(customs)
    cfg["custom_blocked_urls"] = []
    save(cfg)
    return u


def remove_custom_url(url: str) -> bool:
    u = _normalize_url(url)
    cfg = load()
    customs = _combined_popup_urls(cfg)
    if u not in customs:
        return False
    customs.remove(u)
    cfg["custom_popup_urls"] = customs
    cfg["custom_blocked_urls"] = []
    save(cfg)
    return True


def get_popup_urls() -> list[str]:
    return _combined_popup_urls(load())


def add_custom_word(word: str) -> str:
    """Add an exact popup word/phrase. Adding never requires the unlock code."""
    value = _normalize_popup_word(word)
    if not value:
        return ""
    cfg = load()
    words = [_normalize_popup_word(v) for v in (cfg.get("custom_popup_words", []) or [])]
    words = _dedupe([v for v in words if v])
    if value not in words:
        words.append(value)
    cfg["custom_popup_words"] = words
    save(cfg)
    return value


def remove_custom_word(word: str) -> bool:
    value = _normalize_popup_word(word)
    cfg = load()
    words = [_normalize_popup_word(v) for v in (cfg.get("custom_popup_words", []) or [])]
    words = _dedupe([v for v in words if v])
    if value not in words:
        return False
    words.remove(value)
    cfg["custom_popup_words"] = words
    save(cfg)
    return True


def get_popup_words() -> list[str]:
    words = [_normalize_popup_word(v) for v in (load().get("custom_popup_words", []) or [])]
    return _dedupe([v for v in words if v])


# Compatibility API consumed by blocker.py/browser_policies.py. Custom sites
# are popup-only from v1.0.32 onward, so the network layers always receive an
# empty list even before the one-time config migration has run.
def get_custom_domains() -> list[str]:
    return []


def get_custom_urls() -> list[str]:
    return []


def needs_code_rotation() -> bool:
    cfg = load()
    if not cfg.get("install_ts"):
        return False
    last = cfg.get("code_rotation_ts") or cfg.get("install_ts", 0)
    days = cfg.get("code_rotation_days", 7)
    return time.time() - last > days * 24 * 3600


def update_code_hash(new_hash: str) -> None:
    cfg = load()
    cfg["code_hash"] = new_hash
    cfg["code_rotation_ts"] = int(time.time())
    save(cfg)


def start_uninstall_cooldown() -> int:
    cfg = load()
    now = int(time.time())
    cfg["uninstall_initiated_at"] = now
    save(cfg)
    return now


def cancel_uninstall_cooldown() -> None:
    cfg = load()
    cfg["uninstall_initiated_at"] = 0
    save(cfg)


def uninstall_cooldown_remaining() -> int:
    cfg = load()
    started = cfg.get("uninstall_initiated_at", 0)
    if not started:
        return -1
    elapsed = int(time.time()) - started
    remaining = 7 * 24 * 3600 - elapsed
    return max(0, remaining)


def load() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return DEFAULTS.copy()
    try:
        blob = CONFIG_FILE.read_bytes()
        raw = decrypt_machine(blob)
        data = json.loads(raw.decode("utf-8"))
        merged = DEFAULTS.copy()
        merged.update(data)
        return merged
    except Exception:
        return DEFAULTS.copy()


def save(data: dict[str, Any]) -> None:
    ensure_dirs()
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    blob = encrypt_machine(raw)
    tmp = CONFIG_FILE.with_suffix(".tmp")
    tmp.write_bytes(blob)
    tmp.replace(CONFIG_FILE)


def is_installed() -> bool:
    cfg = load()
    return bool(cfg.get("code_hash")) and cfg.get("install_ts", 0) > 0


def is_temp_unlocked() -> bool:
    cfg = load()
    return cfg.get("temp_unlock_until", 0) > time.time()


def grant_temp_unlock(hours: int = 24) -> None:
    cfg = load()
    cfg["temp_unlock_until"] = int(time.time() + hours * 3600)
    save(cfg)


def revoke_temp_unlock() -> None:
    cfg = load()
    cfg["temp_unlock_until"] = 0
    save(cfg)


def record_unlock_request() -> int:
    cfg = load()
    now = int(time.time())
    cfg.setdefault("unlock_requests", []).append(now)
    cfg["unlock_requests"] = [t for t in cfg["unlock_requests"] if now - t < 30 * 24 * 3600]
    save(cfg)
    return count_requests_last_week(cfg)


def count_requests_last_week(cfg: dict[str, Any] | None = None) -> int:
    cfg = cfg if cfg is not None else load()
    now = int(time.time())
    return sum(1 for t in cfg.get("unlock_requests", []) if now - t < 7 * 24 * 3600)


def count_requests_total(cfg: dict[str, Any] | None = None) -> int:
    cfg = cfg if cfg is not None else load()
    return len(cfg.get("unlock_requests", []))
