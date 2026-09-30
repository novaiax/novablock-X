import json
import logging
import subprocess
import time
from typing import Any
from urllib.parse import urlsplit

from .crypto import encrypt_machine, decrypt_machine, verify_code as _verify_hash
from . import trusted_clock
from .paths import (CONFIG_FILE, LOGON_TASK_NAME, PROGRAM_DATA, TASK_NAME,
                    WINDOWS_HOSTS, BLOCK_MARKER_START, ensure_dirs)

log = logging.getLogger("novablock.config")
_corrupt_warning_emitted = False


# Sites intentionally excluded from user-defined popup monitoring.
# movix.cash remains protected by the normal adult-keyword monitor, but simply
# visiting the streaming site must not trigger a custom-site popup.
CUSTOM_SITE_ALLOWLIST = {"movix.cash"}

# Seeded only when no configuration exists yet. Existing installations keep
# their own popup list; Reddit's separate NSFW filter remains independent.
DEFAULT_POPUP_DOMAINS = (
    "botinok.porn",
    "domporno.me",
    "seksvideo.tv",
    "top-xxx.pro",
    "sexm.xxx",
    "nudevista.tv",
    "pornoopa.com",
    "ru.mylust.com",
    "ru.anysex.com",
    "myhomemadesex.com",
    "pornorussia.mobi",
    "vk.ru",
    "hqfukc.com",
    "xxxfilm.pro",
    "porn4e.com",
    "duckduckgo.com",
    "ucweb.com",
)

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
    "default_popup_sites_seeded": False,
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


def ensure_default_popup_sites() -> int:
    """Add the protected default popup sites once to an existing installation.

    The marker lets a valid code-based removal remain effective afterwards.
    Existing personal sites and precise URLs are retained.
    """
    cfg = load()
    if not cfg.get("code_hash") or not cfg.get("install_ts"):
        return 0
    if cfg.get("default_popup_sites_seeded"):
        return 0
    domains = _combined_popup_domains(cfg)
    missing = [domain for domain in DEFAULT_POPUP_DOMAINS if domain not in domains]
    cfg["custom_popup_domains"] = domains + missing
    cfg["default_popup_sites_seeded"] = True
    save(cfg)
    return len(missing)


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


# Compatibility API consumed by blocker.py/browser_policies.py. Custom sites
# are popup-only from v1.0.32 onward, so the network layers always receive an
# empty list even before the one-time config migration has run.
def get_custom_domains() -> list[str]:
    return []


def get_custom_urls() -> list[str]:
    return []


def needs_code_rotation() -> bool:
    cfg = load()
    if cfg.get("_config_unreadable"):
        return False
    if not cfg.get("install_ts"):
        return False
    last = cfg.get("code_rotation_ts") or cfg.get("install_ts", 0)
    now = trusted_clock.cached_now()
    if now is None:
        trusted_clock.refresh_in_background()
        return False
    try:
        days = min(max(int(cfg.get("code_rotation_days", 7)), 1), 7)
    except (TypeError, ValueError):
        days = 7
    return last > now + 300 or now - last > days * 24 * 3600


def verify_current_code(plain: str, cfg: dict[str, Any] | None = None) -> bool:
    """A stale code cannot become valid again by moving the Windows clock."""
    cfg = cfg if cfg is not None else load()
    if cfg.get("_config_unreadable"):
        return False
    now = trusted_clock.verified_now()
    last = cfg.get("code_rotation_ts") or cfg.get("install_ts", 0)
    if not last or last > now + 300 or now - last >= 7 * 24 * 3600:
        return False
    return _verify_hash(plain, cfg.get("code_hash", ""))


def update_code_hash(new_hash: str) -> None:
    cfg = load()
    cfg["code_hash"] = new_hash
    cfg["code_rotation_ts"] = int(trusted_clock.verified_now())
    save(cfg)


def start_uninstall_cooldown() -> int:
    cfg = load()
    now = int(trusted_clock.verified_now())
    cfg["uninstall_initiated_at"] = now
    save(cfg)
    return now


def cancel_uninstall_cooldown() -> None:
    cfg = load()
    cfg["uninstall_initiated_at"] = 0
    save(cfg)


def uninstall_cooldown_remaining(*, verified: bool = False) -> int:
    cfg = load()
    started = cfg.get("uninstall_initiated_at", 0)
    if not started:
        return -1
    now = trusted_clock.verified_now() if verified else trusted_clock.cached_now()
    if now is None:
        trusted_clock.refresh_in_background()
        return -2  # Unknown; never treat as an expired cooldown.
    if started > now + 300:
        return 7 * 24 * 3600
    elapsed = int(now) - started
    remaining = 7 * 24 * 3600 - elapsed
    return max(0, remaining)


def load() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        if _prior_install_present():
            return _protected_unreadable_config("missing")
        fresh = DEFAULTS.copy()
        fresh["custom_popup_domains"] = list(DEFAULT_POPUP_DOMAINS)
        fresh["default_popup_sites_seeded"] = True
        return fresh
    try:
        blob = CONFIG_FILE.read_bytes()
        raw = decrypt_machine(blob)
        data = json.loads(raw.decode("utf-8"))
        merged = DEFAULTS.copy()
        merged.update(data)
        return merged
    except Exception as exc:
        return _protected_unreadable_config(str(exc))


def _prior_install_present() -> bool:
    """A missing config is not a new install while persistence still exists."""
    if any((PROGRAM_DATA / name).exists() for name in (
        "runtime_7c31.exe", "blocklist.txt", "watchdog.heartbeat",
        "main.pid", "companion.pid",
    )):
        return True
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
            value, _kind = winreg.QueryValueEx(key, "NovaBlock")
            if value:
                return True
    except (ImportError, OSError):
        pass
    for task_name in (LOGON_TASK_NAME, TASK_NAME):
        try:
            result = subprocess.run(
                ["schtasks.exe", "/Query", "/TN", task_name],
                capture_output=True, timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode == 0:
                return True
        except (OSError, subprocess.TimeoutExpired):
            continue
    try:
        if BLOCK_MARKER_START in WINDOWS_HOSTS.read_text(encoding="utf-8", errors="ignore"):
            return True
    except OSError:
        pass
    return False


def _protected_unreadable_config(reason: str) -> dict[str, Any]:
    global _corrupt_warning_emitted
    if not _corrupt_warning_emitted:
        log.error("Installed configuration unavailable; keeping protection active: %s", reason)
        _corrupt_warning_emitted = True
    fallback = DEFAULTS.copy()
    now = int(time.time())
    fallback.update({
        "install_ts": now,
        "code_hash": "unreadable-installed-configuration",
        "code_rotation_ts": now,
        "custom_popup_domains": list(DEFAULT_POPUP_DOMAINS),
        "default_popup_sites_seeded": True,
        "_config_unreadable": True,
    })
    return fallback


def save(data: dict[str, Any]) -> None:
    if data.get("_config_unreadable"):
        raise RuntimeError("Cannot overwrite an unreadable installed configuration")
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
    until = cfg.get("temp_unlock_until", 0)
    if not until:
        return False
    now = trusted_clock.cached_now()
    if now is None:
        trusted_clock.refresh_in_background()
        return False
    return now < until <= now + 24 * 3600 + 300


def grant_temp_unlock(hours: int = 24) -> None:
    cfg = load()
    now = trusted_clock.verified_now()
    cfg["temp_unlock_until"] = int(now + min(max(hours, 0), 24) * 3600)
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
