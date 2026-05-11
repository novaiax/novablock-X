import ctypes
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

import requests

from .paths import (
    BLOCK_MARKER_END,
    BLOCK_MARKER_START,
    BLOCKLIST_CACHE,
    HOSTS_BACKUP,
    WINDOWS_HOSTS,
    ensure_dirs,
)

log = logging.getLogger("novablock.blocker")

BLOCKLIST_URL = "https://raw.githubusercontent.com/StevenBlack/hosts/master/alternates/porn-only/hosts"
FALLBACK_DOMAINS = [
    "pornhub.com", "www.pornhub.com",
    "xvideos.com", "www.xvideos.com",
    "xhamster.com", "www.xhamster.com",
    "redtube.com", "www.redtube.com",
    "youporn.com", "www.youporn.com",
    "tube8.com", "www.tube8.com",
    "spankbang.com", "www.spankbang.com",
    "xnxx.com", "www.xnxx.com",
    "porn.com", "www.porn.com",
    "porntrex.com", "www.porntrex.com",
    "stripchat.com", "www.stripchat.com",
    "chaturbate.com", "www.chaturbate.com",
    "onlyfans.com", "www.onlyfans.com",
    "fansly.com", "www.fansly.com",
    "rule34.xxx", "www.rule34.xxx",
    "e621.net", "www.e621.net",
    "literotica.com", "www.literotica.com",
]

# Always blocked, regardless of what the StevenBlack list returns.
# Yandex is a known porn-bypass (Russian search engine that indexes content
# Google/Bing filter out). All TLD variants are listed.
EXTRA_DOMAINS = [
    # Yandex search + ecosystem
    "yandex.com", "www.yandex.com", "yandex.ru", "www.yandex.ru",
    "yandex.net", "www.yandex.net", "yandex.eu", "www.yandex.eu",
    "yandex.com.tr", "www.yandex.com.tr", "yandex.kz", "www.yandex.kz",
    "yandex.by", "www.yandex.by", "yandex.ua", "www.yandex.ua",
    "yandex.fr", "www.yandex.fr", "yandex.de", "www.yandex.de",
    "yandex.uz", "www.yandex.uz", "yandex.tj", "www.yandex.tj",
    "yandex.tm", "www.yandex.tm", "yandex.az", "www.yandex.az",
    "yandex.com.ge", "www.yandex.com.ge", "yandex.com.am", "www.yandex.com.am",
    "ya.ru", "www.ya.ru",
    "yastatic.net", "yandex-team.ru",
    "search.yandex.com", "search.yandex.ru",
    "video.yandex.com", "video.yandex.ru",
    "images.yandex.com", "images.yandex.ru",
    "m.yandex.com", "m.yandex.ru",
    "mail.yandex.com", "mail.yandex.ru",
    "passport.yandex.com", "passport.yandex.ru",
    "yandex.com.mx", "yandex.com.ar",
    # Other porn-friendly search engines that bypass safe search
    "duckduckgo.com",  # disable if user wants — but DDG safe search is off-by-default
]

# By default we DON'T block DuckDuckGo (legit privacy search) — only Yandex.
EXTRA_DOMAINS = [d for d in EXTRA_DOMAINS if "duckduckgo" not in d]

FAMILY_DNS_PRIMARY = "1.1.1.3"
FAMILY_DNS_SECONDARY = "1.0.0.3"
# Cloudflare Family DNS in IPv6 — equivalent to 1.1.1.3 / 1.0.0.3. Required
# because Windows prefers IPv6 DNS over IPv4 when both are set. If we leave
# the DHCPv6-assigned IPv6 DNS in place (often the router's local resolver),
# resolutions go there first — and many home routers' IPv6 resolvers are
# unstable, breaking *all* internet access despite our IPv4 DNS being fine.
FAMILY_DNS_PRIMARY_V6 = "2606:4700:4700::1113"
FAMILY_DNS_SECONDARY_V6 = "2606:4700:4700::1003"

# Ordered list of family-safe DNS providers. All of these filter adult content
# at the DNS level. If the preferred provider (Cloudflare Family) is
# unreachable from the user's network, we fall back to the next one — but
# NEVER to DHCP/router DNS (that would defeat the block). The "" entries for
# v6 mean the provider doesn't offer IPv6, in which case we still set v4 and
# leave v6 to whatever was there (the Cloudflare v6 fallback above is tried
# separately).
DNS_FALLBACKS = [
    # (name, v4_primary, v4_secondary, v6_primary, v6_secondary)
    ("Cloudflare Family",
     "1.1.1.3", "1.0.0.3",
     "2606:4700:4700::1113", "2606:4700:4700::1003"),
    ("OpenDNS FamilyShield",
     "208.67.222.123", "208.67.220.123",
     "", ""),
    ("Quad9 (security + family)",
     "9.9.9.10", "149.112.112.10",
     "2620:fe::10", "2620:fe::fe:10"),
    ("CleanBrowsing Family",
     "185.228.168.168", "185.228.169.168",
     "2a0d:2a00:1::", "2a0d:2a00:2::"),
]


# DNS-level SafeSearch enforcement.
# Maps the public hostname → the Google/YouTube/Bing-provided "safe variant" IP.
# Works for ALL browsers (Firefox, Edge, Chrome, Brave, etc.) because the DNS
# resolver (system → hosts file) returns the safe IP before the browser even
# tries to load the real one.
SAFESEARCH_HOSTS_MAP = [
    # Google SafeSearch — forcesafesearch.google.com
    ("www.google.com", "216.239.38.120"),
    ("google.com", "216.239.38.120"),
    ("www.google.fr", "216.239.38.120"),
    ("google.fr", "216.239.38.120"),
    ("www.google.co.uk", "216.239.38.120"),
    ("google.co.uk", "216.239.38.120"),
    ("www.google.de", "216.239.38.120"),
    ("google.de", "216.239.38.120"),
    # YouTube Restricted Mode (Moderate) — restrictmoderate.youtube.com
    ("www.youtube.com", "216.239.38.119"),
    ("m.youtube.com", "216.239.38.119"),
    ("youtubei.googleapis.com", "216.239.38.119"),
    ("youtube.googleapis.com", "216.239.38.119"),
    # Bing SafeSearch (strict) — strict.bing.com
    ("www.bing.com", "204.79.197.220"),
    ("bing.com", "204.79.197.220"),
    # Note: DuckDuckGo and Yandex have no DNS-level safesearch.
    # DDG: not a problem (no image/video porn surfacing).
    # Yandex: blocked entirely via EXTRA_DOMAINS.
]


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _dns_reachable(ip: str, timeout: float = 2.0) -> bool:
    """Send a minimal DNS query (UDP 53) and wait briefly for a response.
    Used to pick a working family-safe DNS from the fallback list."""
    if not ip:
        return False
    import socket
    try:
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        # A-record query for "example.com" (0x1234 = transaction id)
        query = (
            b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00"
            b"\x07example\x03com\x00\x00\x01\x00\x01"
        )
        sock.sendto(query, (ip, 53))
        sock.recvfrom(512)
        sock.close()
        return True
    except Exception:
        return False


def choose_family_dns() -> tuple[str, str, str, str, str]:
    """Pick the first reachable family-safe DNS provider from DNS_FALLBACKS.
    Returns (name, v4_primary, v4_secondary, v6_primary, v6_secondary).

    If none of the fallbacks respond (e.g. captive portal, no internet),
    return Cloudflare Family anyway — the hosts file block stays in place and
    DNS will start working again once the network recovers. NEVER returns
    the user's DHCP DNS (that would defeat the family filter)."""
    for name, v4p, v4s, v6p, v6s in DNS_FALLBACKS:
        if _dns_reachable(v4p, timeout=1.5):
            log.info("DNS choice: %s (%s reachable)", name, v4p)
            return name, v4p, v4s, v6p, v6s
    log.warning("No family-safe DNS reachable — falling back to Cloudflare Family anyway")
    name, v4p, v4s, v6p, v6s = DNS_FALLBACKS[0]
    return name, v4p, v4s, v6p, v6s


def _run(cmd: list[str], check: bool = False, timeout: int = 30) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        if check and proc.returncode != 0:
            log.warning("cmd failed %s: %s", cmd, proc.stderr.strip())
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        log.warning("cmd timeout %s", cmd)
        return -1, "", "timeout"
    except Exception as e:
        log.warning("cmd error %s: %s", cmd, e)
        return -1, "", str(e)


def download_blocklist(force: bool = False) -> list[str]:
    ensure_dirs()
    if not force and BLOCKLIST_CACHE.exists():
        age = time.time() - BLOCKLIST_CACHE.stat().st_mtime
        if age < 7 * 24 * 3600:
            cached = BLOCKLIST_CACHE.read_text(encoding="utf-8", errors="ignore").splitlines()
            return list(set(cached + EXTRA_DOMAINS))

    domains: list[str] = []
    try:
        r = requests.get(BLOCKLIST_URL, timeout=20)
        r.raise_for_status()
        for line in r.text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[0] in ("0.0.0.0", "127.0.0.1"):
                d = parts[1].strip().lower()
                if d and "." in d and d != "0.0.0.0":
                    domains.append(d)
        if domains:
            domains = list(set(domains + EXTRA_DOMAINS))
            BLOCKLIST_CACHE.write_text("\n".join(sorted(set(domains))), encoding="utf-8")
            log.info("Downloaded %d domains from StevenBlack (+%d extras)",
                     len(domains) - len(EXTRA_DOMAINS), len(EXTRA_DOMAINS))
            return domains
    except Exception as e:
        log.warning("blocklist download failed: %s", e)

    if BLOCKLIST_CACHE.exists():
        cached = BLOCKLIST_CACHE.read_text(encoding="utf-8", errors="ignore").splitlines()
        return list(set(cached + EXTRA_DOMAINS))
    return list(set(FALLBACK_DOMAINS + EXTRA_DOMAINS))


def backup_hosts() -> None:
    ensure_dirs()
    if HOSTS_BACKUP.exists():
        return
    if WINDOWS_HOSTS.exists():
        shutil.copy2(WINDOWS_HOSTS, HOSTS_BACKUP)
        log.info("Backed up hosts file")


def _strip_block(content: str) -> str:
    if BLOCK_MARKER_START not in content:
        return content
    lines = content.splitlines(keepends=True)
    out = []
    skipping = False
    for ln in lines:
        if BLOCK_MARKER_START in ln:
            skipping = True
            continue
        if BLOCK_MARKER_END in ln:
            skipping = False
            continue
        if not skipping:
            out.append(ln)
    return "".join(out)


def _build_block(domains: list[str]) -> str:
    seen: set[str] = set()
    out = [BLOCK_MARKER_START]
    # SafeSearch redirects (specific IP, not 0.0.0.0) — at the top so they take precedence
    out.append("# SafeSearch enforcement (DNS-level, all browsers)")
    for host, ip in SAFESEARCH_HOSTS_MAP:
        if not ip or "." not in ip:
            continue
        out.append(f"{ip} {host}")
        seen.add(host)
    out.append("")
    out.append("# Adult content blocklist (StevenBlack + custom)")
    for d in domains:
        d = d.strip().lower()
        if not d or d in seen or "." not in d:
            continue
        seen.add(d)
        out.append(f"0.0.0.0 {d}")
    out.append(BLOCK_MARKER_END)
    return "\n".join(out) + "\n"


def unlock_hosts_acl() -> None:
    """Take ownership and grant Administrators full control on hosts."""
    # takeown is required because previous install may have removed
    # WRITE_DAC permission for Administrators.
    _run(["takeown", "/f", str(WINDOWS_HOSTS)], timeout=15)
    _run(["icacls", str(WINDOWS_HOSTS), "/reset"], timeout=15)
    _run(["icacls", str(WINDOWS_HOSTS), "/grant:r", "Administrators:F"], timeout=15)
    _run(["icacls", str(WINDOWS_HOSTS), "/grant:r", "SYSTEM:F"], timeout=15)
    _run(["icacls", str(WINDOWS_HOSTS), "/grant:r", "Users:R"], timeout=15)


def lock_hosts_acl() -> None:
    _run(["icacls", str(WINDOWS_HOSTS), "/inheritance:r"], timeout=15)
    _run(["icacls", str(WINDOWS_HOSTS), "/grant:r", "SYSTEM:F"], timeout=15)
    # Keep Administrators with Full so we can re-write at next watchdog tick.
    _run(["icacls", str(WINDOWS_HOSTS), "/grant:r", "Administrators:F"], timeout=15)
    _run(["icacls", str(WINDOWS_HOSTS), "/grant:r", "Users:R"], timeout=15)


def _atomic_write_hosts(content: str) -> None:
    """Write hosts atomically: write to a temp file in the same directory,
    then replace. Prevents the file from being truncated mid-write when the
    OS or another process holds a lock — that left users with a tiny / empty
    hosts file, which then made `hosts_block_present()` return False forever
    and the watchdog re-apply in a busy loop."""
    temp = WINDOWS_HOSTS.with_name(WINDOWS_HOSTS.name + ".novablock.tmp")
    temp.write_text(content, encoding="utf-8")
    # os.replace is atomic on Windows when both files are on the same volume
    # and the destination is not held with FILE_SHARE_DELETE=0.
    os.replace(str(temp), str(WINDOWS_HOSTS))


def _read_hosts_safe() -> str:
    """Read hosts file robustly. If unreadable or hosts is missing, restore
    from backup. If no backup, return a minimal default content."""
    if WINDOWS_HOSTS.exists():
        try:
            return WINDOWS_HOSTS.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            log.warning("hosts unreadable (%s) — attempting restore from backup", e)
    if HOSTS_BACKUP.exists():
        try:
            shutil.copy2(HOSTS_BACKUP, WINDOWS_HOSTS)
            log.warning("Restored hosts file from backup")
            return WINDOWS_HOSTS.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            log.error("backup restore failed: %s", e)
    # Last resort: minimal default that Windows ships with
    return (
        "# Copyright (c) 1993-2009 Microsoft Corp.\n"
        "# (Restored by NovaBlock — original hosts was missing.)\n"
        "127.0.0.1 localhost\n"
        "::1 localhost\n"
    )


def apply_hosts_block(domains: list[str] | None = None) -> int:
    """Apply the NovaBlock host block to the hosts file. Robust against
    PermissionError (one retry after re-unlocking the ACL) and missing /
    corrupted hosts (restore from backup, then re-apply)."""
    backup_hosts()
    if domains is None:
        domains = download_blocklist()

    last_err: Exception | None = None
    success = False
    for attempt in (1, 2, 3):
        try:
            unlock_hosts_acl()
            existing = _read_hosts_safe()
            cleaned = _strip_block(existing)
            if not cleaned.endswith("\n"):
                cleaned += "\n"
            new_content = cleaned + _build_block(domains)
            _atomic_write_hosts(new_content)
            _run(["ipconfig", "/flushdns"], timeout=10)
            log.info("Applied hosts block: %d domains (attempt %d)",
                     len(set(domains)), attempt)
            success = True
            return len(set(domains))
        except PermissionError as e:
            last_err = e
            log.warning("hosts write PermissionError (attempt %d) — re-unlocking ACL", attempt)
            time.sleep(1.5)
        except OSError as e:
            last_err = e
            log.warning("hosts write OSError (attempt %d): %s", attempt, e)
            time.sleep(1.5)
        finally:
            # Only re-lock the ACL on success. If we failed, leaving the ACL
            # unlocked makes the *next* tick more likely to succeed — locking
            # after a failure was making the system get stuck (PermissionError
            # forever, netsh/ipconfig timeouts, internet broken).
            if success:
                try:
                    lock_hosts_acl()
                except Exception:
                    pass
    log.error("Failed to apply hosts block after 3 attempts: %s", last_err)
    return 0


def remove_hosts_block() -> None:
    unlock_hosts_acl()
    try:
        if WINDOWS_HOSTS.exists():
            existing = WINDOWS_HOSTS.read_text(encoding="utf-8", errors="ignore")
            cleaned = _strip_block(existing)
            WINDOWS_HOSTS.write_text(cleaned, encoding="utf-8")
            _run(["ipconfig", "/flushdns"], timeout=10)
    finally:
        pass


def hosts_block_present() -> bool:
    """Check if the NovaBlock marker is in the hosts file. Optimised: reads
    only the last 4KB instead of the full ~2.5MB file (the END marker is at
    the very end, so finding it there proves the block is in place)."""
    if not WINDOWS_HOSTS.exists():
        return False
    try:
        size = WINDOWS_HOSTS.stat().st_size
        with open(WINDOWS_HOSTS, "rb") as f:
            f.seek(max(0, size - 4096))
            tail = f.read().decode("utf-8", errors="ignore")
        return BLOCK_MARKER_END in tail
    except Exception:
        return False


def list_active_interfaces() -> list[str]:
    code, out, _ = _run(
        ["powershell", "-NoProfile", "-Command",
         "Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | Select-Object -ExpandProperty Name"],
        timeout=15,
    )
    if code != 0:
        return []
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def set_family_dns() -> int:
    """Force a reachable family-safe DNS on BOTH IPv4 and IPv6 stacks of each
    active interface. Tries Cloudflare Family first, falls back to OpenDNS /
    Quad9 / CleanBrowsing if Cloudflare is unreachable from this network.

    Never leaves the user's DHCP DNS in place — that would defeat the family
    filter. If absolutely nothing is reachable, sets Cloudflare anyway and
    relies on the hosts file block alone until the network recovers."""
    name, v4p, v4s, v6p, v6s = choose_family_dns()
    n = 0
    for iface in list_active_interfaces():
        code_v4, _, _ = _run(
            ["netsh", "interface", "ipv4", "set", "dns",
             f"name={iface}", "static", v4p, "primary"],
            timeout=15,
        )
        if code_v4 == 0 and v4s:
            _run(
                ["netsh", "interface", "ipv4", "add", "dns",
                 f"name={iface}", v4s, "index=2"],
                timeout=15,
            )
        # IPv6 — only set if the chosen provider offers it. Errors silently
        # ignored on interfaces without IPv6 enabled.
        code_v6 = -1
        if v6p:
            code_v6, _, _ = _run(
                ["netsh", "interface", "ipv6", "set", "dns",
                 f"name={iface}", "static", v6p, "primary"],
                timeout=15,
            )
            if code_v6 == 0 and v6s:
                _run(
                    ["netsh", "interface", "ipv6", "add", "dns",
                     f"name={iface}", v6s, "index=2"],
                    timeout=15,
                )
        if code_v4 == 0 or code_v6 == 0:
            n += 1
    if n:
        _run(["ipconfig", "/flushdns"], timeout=10)
        log.info("Set %s DNS (v4+v6) on %d interface(s)", name, n)
    return n


def reset_dns() -> int:
    n = 0
    for iface in list_active_interfaces():
        code_v4, _, _ = _run(
            ["netsh", "interface", "ipv4", "set", "dns", f"name={iface}", "dhcp"],
            timeout=15,
        )
        _run(
            ["netsh", "interface", "ipv6", "set", "dns", f"name={iface}", "dhcp"],
            timeout=15,
        )
        if code_v4 == 0:
            n += 1
    if n:
        _run(["ipconfig", "/flushdns"], timeout=10)
    return n


def _any_iface_has_dns(reg_path: str, dns_ip: str) -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as root:
            n_subkeys, _, _ = winreg.QueryInfoKey(root)
            for i in range(n_subkeys):
                guid = winreg.EnumKey(root, i)
                try:
                    with winreg.OpenKey(root, guid) as ifkey:
                        try:
                            ns, _ = winreg.QueryValueEx(ifkey, "NameServer")
                        except FileNotFoundError:
                            ns = ""
                        if ns and dns_ip in ns:
                            return True
                except OSError:
                    continue
        return False
    except OSError:
        # Cannot read registry — assume OK so we don't spam re-applies.
        return True


def dns_is_locked() -> bool:
    """Check if BOTH IPv4 and IPv6 DNS are locked to *any* family-safe provider
    in DNS_FALLBACKS. Reads the registry directly (no PowerShell).

    Both stacks must be locked: if only IPv4 is locked, Windows prefers the
    DHCPv6-assigned IPv6 DNS (often the router) which may be unstable and
    breaks resolution. A half-locked state is treated as 'not locked' to
    trigger a re-apply that fixes both."""
    v4_root = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"
    v6_root = r"SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters\Interfaces"
    v4_ok = any(_any_iface_has_dns(v4_root, v4p) for _, v4p, _, _, _ in DNS_FALLBACKS)
    # For v6, accept locked if any provider's v6 primary is present, OR if no
    # provider with v6 is currently set — in that case Cloudflare v6 should
    # be there.
    v6_providers = [v6p for _, _, _, v6p, _ in DNS_FALLBACKS if v6p]
    v6_ok = any(_any_iface_has_dns(v6_root, v6p) for v6p in v6_providers)
    return v4_ok and v6_ok


def apply_full_block(kill_browsers: bool = True) -> dict:
    if not is_admin():
        log.warning("apply_full_block called without admin")
        return {"hosts": 0, "dns": 0, "admin": False}
    from . import browser_policies, firewall, browser_kill, config
    domains = download_blocklist()
    # Include user-defined custom domains + their www variants
    customs = config.get_custom_domains()
    for d in customs:
        domains.append(d)
        domains.append(f"www.{d}")
    n_hosts = apply_hosts_block(domains)
    n_dns = set_family_dns()
    pol = browser_policies.apply_all_browser_policies()
    n_fw = firewall.block_doh_endpoints()
    n_killed = browser_kill.kill_all_browsers() if kill_browsers else 0
    return {"hosts": n_hosts, "dns": n_dns, "policies": pol,
            "firewall": n_fw, "browsers_killed": n_killed,
            "custom": len(customs), "admin": True}


def remove_full_block() -> None:
    if not is_admin():
        log.warning("remove_full_block called without admin")
        return
    from . import browser_policies, firewall
    remove_hosts_block()
    reset_dns()
    browser_policies.remove_all_browser_policies()
    firewall.unblock_doh_endpoints()
