import json
import time
from typing import Any
from urllib.parse import urlsplit

from .crypto import encrypt_machine, decrypt_machine
from .paths import CONFIG_FILE, ensure_dirs


# Sites intentionally excluded from user-defined popup monitoring.
# movix.cash remains protected by the normal adult-keyword monitor, but simply
# visiting the streaming site must not trigger the custom-site popup.
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
    "custom_blocked_domains": [],
    "custom_blocked_urls": [],
    "machine_name": "",
}


def _normalize_domain(d: str) -> str:
    d = d.strip().lower()
    for prefix in ("https://", "http://"):
        if d.startswith(prefix):
            d = d[len(prefix):]
    if d.startswith("www."):
        d = d[4:]
    d = d.split("/")[0].split(":")[0]
    return d


def _url_host(u: str) -> str:
    raw = (u or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw.lstrip("/")
    try:
        return (urlsplit(raw).hostname or "").lower().removeprefix("www.")
    except Exception:
        return ""


def _is_custom_allowed_host(host: str) -> bool:
    host = (host or "").lower().removeprefix("www.")
    return any(host == allowed or host.endswith("." + allowed)
               for allowed in CUSTOM_SITE_ALLOWLIST)


def sanitize_custom_sites() -> bool:
    """Remove allowlisted sites left in older custom-site configurations."""
    cfg = load()
    old_domains = list(cfg.get("custom_blocked_domains", []) or [])
    old_urls = list(cfg.get("custom_blocked_urls", []) or [])
    domains = [d for d in old_domains
               if not _is_custom_allowed_host(_normalize_domain(str(d)))]
    urls = [u for u in old_urls
            if not _is_custom_allowed_host(_url_host(str(u)))]
    if domains == old_domains and urls == old_urls:
        return False
    cfg["custom_blocked_domains"] = domains
    cfg["custom_blocked_urls"] = urls
    save(cfg)
    return True


def add_custom_domain(domain: str) -> str:
    """Add a domain to the user-defined popup monitor list."""
    d = _normalize_domain(domain)
    if not d or "." not in d or " " in d or _is_custom_allowed_host(d):
        return ""
    cfg = load()
    customs = cfg.setdefault("custom_blocked_domains", [])
    if d in customs:
        return d
    customs.append(d)
    save(cfg)
    return d


def remove_custom_domain(domain: str) -> bool:
    d = _normalize_domain(domain)
    cfg = load()
    customs = cfg.get("custom_blocked_domains", [])
    if d in customs:
        customs.remove(d)
        cfg["custom_blocked_domains"] = customs
        save(cfg)
        return True
    return False


def get_custom_domains() -> list[str]:
    return [str(d) for d in (load().get("custom_blocked_domains", []) or [])
            if not _is_custom_allowed_host(_normalize_domain(str(d)))]


def _normalize_url(u: str) -> str:
    u = u.strip()
    if not u:
        return ""
    if not (u.startswith("http://") or u.startswith("https://")):
        u = "https://" + u.lstrip("/")
    return u


def add_custom_url(url: str) -> str:
    """Add a precise URL to the user-defined popup monitor list."""
    u = _normalize_url(url)
    if not u or " " in u or "." not in u or _is_custom_allowed_host(_url_host(u)):
        return ""
    cfg = load()
    customs = cfg.setdefault("custom_blocked_urls", [])
    if u in customs:
        return u
    customs.append(u)
    save(cfg)
    return u


def remove_custom_url(url: str) -> bool:
    cfg = load()
    customs = cfg.get("custom_blocked_urls", [])
    if url in customs:
        customs.remove(url)
        cfg["custom_blocked_urls"] = customs
        save(cfg)
        return True
    return False


def get_custom_urls() -> list[str]:
    return [str(u) for u in (load().get("custom_blocked_urls", []) or [])
            if not _is_custom_allowed_host(_url_host(str(u)))]


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
