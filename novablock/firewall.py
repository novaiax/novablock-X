"""Windows Firewall rules that block known DNS-over-HTTPS endpoints.

Why: even with browser policies disabling DoH, an existing browser session can
keep using DoH until restart. Worse, some browsers (Firefox especially) embed
their own DNS resolver. The only reliable way to force browsers to use the
system DNS resolver (and therefore honor our hosts file) is to block outbound
traffic to known DoH endpoint IPs.

We block TCP/UDP 443 + 853 to:
  - Cloudflare DoH (1.1.1.x, 1.0.0.x, mozilla.cloudflare-dns.com IPs)
  - Google DoH (8.8.8.8, 8.8.4.4, dns.google)
  - Quad9 DoH (9.9.9.9, 149.112.112.112)
  - OpenDNS, NextDNS

Note: regular DNS on port 53 to the same IPs is still allowed, so our
Cloudflare Family DNS (1.1.1.3) still works.

Implementation: uses the Windows Firewall COM API (HNetCfg.FwPolicy2) instead
of `netsh advfirewall firewall add rule`. Two reasons:

  1. Speed: netsh add/delete each take ~1–2s and serialize behind a global
     firewall lock. 78 rules × 2 calls (delete-then-add for dedup) = 2–3
     minutes. COM Add is sub-millisecond per rule — 78 rules in ~0.1s.

  2. Native dedup by name: COM Rules.Item(name) tells us if a rule exists
     in O(1). No need for the delete-then-add dance that caused the
     accumulation bug when delete failed silently.
"""
import logging

log = logging.getLogger("novablock.firewall")

DOH_IPS = [
    # Cloudflare general + Family DNS
    "1.1.1.1", "1.0.0.1",
    "1.1.1.2", "1.0.0.2",
    "1.1.1.3", "1.0.0.3",
    # Cloudflare DoH endpoints (mozilla.cloudflare-dns.com, chrome.cloudflare-dns.com)
    "162.159.36.5", "162.159.46.5",
    "172.64.36.5", "172.64.46.5",
    # Google DoH (dns.google)
    "8.8.8.8", "8.8.4.4",
    "2001:4860:4860::8888", "2001:4860:4860::8844",
    # Quad9
    "9.9.9.9", "149.112.112.112",
    "9.9.9.10", "149.112.112.10",
    "9.9.9.11", "149.112.112.11",
    # OpenDNS
    "208.67.222.222", "208.67.220.220",
    # NextDNS (variable IPs but block its primary endpoints)
    "45.90.28.0", "45.90.30.0",
    # AdGuard DNS
    "94.140.14.14", "94.140.15.15",
]

RULE_PREFIX = "NovaBlock_DoH_"

# Windows Firewall COM constants (from netfw.h)
NET_FW_RULE_DIR_OUT       = 2
NET_FW_ACTION_BLOCK       = 0
NET_FW_IP_PROTOCOL_TCP    = 6
NET_FW_IP_PROTOCOL_UDP    = 17
NET_FW_PROFILE2_ALL       = 0x7FFFFFFF  # all profiles (domain + private + public)


def _get_fw_policy():
    """Return the FwPolicy2 COM object, or None if pywin32 / COM unavailable.
    The caller falls back to a no-op (the rest of NovaBlock still works,
    we just lose DoH blocking until next attempt)."""
    try:
        import win32com.client
        return win32com.client.Dispatch("HNetCfg.FwPolicy2")
    except Exception as e:
        log.warning("Could not initialise Windows Firewall COM: %s", e)
        return None


def _make_rule_name(proto_label: str, ip: str) -> str:
    return f"{RULE_PREFIX}{proto_label}_{ip.replace(':', '_').replace('.', '_')}"


def _rule_specs():
    """Yield (name, protocol_const, port, remote_ip) tuples for every rule
    NovaBlock should have. Single source of truth for both add and remove."""
    for ip in DOH_IPS:
        yield _make_rule_name("TCP443", ip), NET_FW_IP_PROTOCOL_TCP, "443", ip
        yield _make_rule_name("TCP853", ip), NET_FW_IP_PROTOCOL_TCP, "853", ip
        yield _make_rule_name("UDP443", ip), NET_FW_IP_PROTOCOL_UDP, "443", ip


# A single name can carry thousands of duplicate rule objects, so cap the
# per-name removal loop rather than trusting it to terminate on its own.
_MAX_DUPES_PER_NAME = 50_000


def _snapshot_existing(fw) -> tuple[set[str], int]:
    """One-pass scan of the rules collection. Returns (unique names, TOTAL
    number of rule objects) carrying our RULE_PREFIX.

    The total matters and the set alone is not enough: every duplicate shares
    the same Name, so a set of names saturates at len(_rule_specs()) however
    many thousands of rule objects actually exist. Sizing the duplicate check
    off the set made the cleanup in block_doh_endpoints unreachable, and one
    machine accumulated ~95000 leftover rules - enough that the Windows
    Firewall service stalled the whole network stack at boot and left it on
    "Identifying" for several minutes."""
    names: set[str] = set()
    total = 0
    try:
        for r in fw.Rules:
            try:
                n = r.Name
                if n and n.startswith(RULE_PREFIX):
                    names.add(n)
                    total += 1
            except Exception:
                pass
    except Exception as e:
        log.warning("Could not enumerate firewall rules: %s", e)
    return names, total


def _snapshot_existing_names(fw) -> set[str]:
    """Back-compat wrapper: unique names only."""
    return _snapshot_existing(fw)[0]


def block_doh_endpoints() -> int:
    """Idempotent: add only the rules that don't already exist. Returns the
    number of NEW rules added (existing rules counted in the log)."""
    fw = _get_fw_policy()
    if fw is None:
        return 0

    existing, total_rules = _snapshot_existing(fw)

    # If we previously accumulated duplicates (the old netsh add-without-dedup
    # bug could leave thousands), drop everything matching the prefix first
    # so we end up with exactly len(specs) rules. The threshold catches the
    # pathological case (10k+ rules) but skips the cheap path when count is
    # already normal.
    expected_count = 26 * 3  # 26 IPs × {TCP443, TCP853, UDP443} = 78
    if total_rules > expected_count * 2:
        log.warning("Found %d NovaBlock_DoH rule objects under %d distinct names "
                    "(expected %d) — wiping duplicates",
                    total_rules, len(existing), expected_count)
        removed = _wipe_all_doh_rules(fw)
        log.info("Removed %d duplicate rules", removed)
        existing = set()

    added = 0
    try:
        import win32com.client
    except ImportError:
        return 0

    for name, protocol, port, remote_ip in _rule_specs():
        if name in existing:
            continue
        try:
            rule = win32com.client.Dispatch("HNetCfg.FWRule")
            rule.Name             = name
            rule.Direction        = NET_FW_RULE_DIR_OUT
            rule.Action           = NET_FW_ACTION_BLOCK
            rule.Protocol         = protocol
            rule.RemoteAddresses  = remote_ip
            rule.RemotePorts      = port
            rule.Enabled          = True
            rule.Profiles         = NET_FW_PROFILE2_ALL
            rule.Description      = "NovaBlock: blocks a known DoH/DoT endpoint"
            fw.Rules.Add(rule)
            added += 1
        except Exception as e:
            log.debug("add rule %s failed: %s", name, e)

    if added or existing:
        log.info("DoH firewall: %d added, %d already present (target: %d)",
                 added, len(existing), expected_count)
    return added


def _wipe_all_doh_rules(fw) -> int:
    """Remove every rule whose name starts with RULE_PREFIX. Used to clean up
    accumulated duplicates from old netsh-based versions, and by
    unblock_doh_endpoints below."""
    names, _total = _snapshot_existing(fw)
    removed = 0
    for n in names:
        # Rules.Remove(name) deletes ONE rule per call. A single pass over the
        # unique names therefore leaves every duplicate in place - which is
        # how ~95000 rules survived a "wipe" on one machine. Loop until
        # Remove raises, meaning nothing is left under that name.
        for _ in range(_MAX_DUPES_PER_NAME):
            try:
                fw.Rules.Remove(n)
                removed += 1
            except Exception:
                break
    return removed


def unblock_doh_endpoints() -> int:
    """Remove all NovaBlock DoH rules. Used by uninstall."""
    fw = _get_fw_policy()
    if fw is None:
        return 0
    n = _wipe_all_doh_rules(fw)
    log.info("DoH firewall: %d rules removed", n)
    return n


def doh_blocked() -> bool:
    """Check if at least one NovaBlock DoH rule is active. Uses COM Item()
    for O(1) lookup instead of scanning the whole rule list."""
    fw = _get_fw_policy()
    if fw is None:
        return False
    canary = _make_rule_name("TCP443", "1.1.1.1")
    try:
        rule = fw.Rules.Item(canary)
        return bool(rule and rule.Enabled)
    except Exception:
        return False
