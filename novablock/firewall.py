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
import subprocess
from datetime import datetime, timezone

from .paths import PROGRAM_DATA

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
FIREWALL_RULES_KEY = (
    r"SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters"
    r"\FirewallPolicy\FirewallRules"
)

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


def _rule_matches(rule, protocol: int, port: str, remote_ip: str) -> bool:
    address = str(rule.RemoteAddresses).lower()
    expected = remote_ip.lower()
    equivalents = {expected, f"{expected}-{expected}"}
    if ":" not in remote_ip:
        equivalents.add(f"{expected}/255.255.255.255")
    return bool(
        rule.Enabled and rule.Action == NET_FW_ACTION_BLOCK
        and rule.Direction == NET_FW_RULE_DIR_OUT
        and rule.Protocol == protocol and str(rule.RemotePorts) == port
        and address in equivalents
    )


def _rule_exists(fw, name: str, protocol: int, port: str, remote_ip: str) -> bool:
    """Look up and repair one named rule without enumerating the full policy.

    Rules.Item() is an indexed lookup: it either finds the rule or raises.
    Unlike a full enumeration it cannot come back partial, which matters
    because a partial snapshot is what let duplicates run away (see the
    comment in block_doh_endpoints)."""
    try:
        rule = fw.Rules.Item(name)
        if rule is None:
            return False
        if not _rule_matches(rule, protocol, port, remote_ip):
            rule.Direction = NET_FW_RULE_DIR_OUT
            rule.Action = NET_FW_ACTION_BLOCK
            rule.Protocol = protocol
            rule.RemoteAddresses = remote_ip
            rule.RemotePorts = port
            rule.Enabled = True
            log.warning("Repaired inactive or incorrect DoH rule %s", name)
        return _rule_matches(rule, protocol, port, remote_ip)
    except Exception as exc:
        log.debug("DoH rule %s missing or could not be repaired: %s", name, exc)
        return False


def _registry_rule_fields(raw: str) -> dict[str, str]:
    return dict(part.split("=", 1) for part in raw.split("|") if "=" in part)


def _valid_registry_rule(fields: dict[str, str], spec: tuple[int, str, str]) -> bool:
    protocol, port, address = spec
    address_field = "RA6" if ":" in address else "RA4"
    actual_address = fields.get(address_field, "").lower()
    expected_address = address.lower()
    equivalent_addresses = {expected_address, f"{expected_address}-{expected_address}"}
    if address_field == "RA4":
        equivalent_addresses.add(f"{expected_address}/255.255.255.255")
    return (
        fields.get("Action") == "Block"
        and fields.get("Active") == "TRUE"
        and fields.get("Dir") == "Out"
        and fields.get("Protocol") == str(protocol)
        and fields.get("RPort") == port
        and actual_address in equivalent_addresses
    )


def _plan_registry_cleanup(records: list[tuple[str, str]]) -> tuple[list[str], list[str], int]:
    """Keep one active block for each current DoH endpoint and protocol.

    The planner is pure so duplicate and missing-rule cases can be tested
    without touching the live Windows Firewall policy.
    """
    specs = {name: (protocol, port, address)
             for name, protocol, port, address in _rule_specs()}
    groups: dict[str, list[tuple[str, dict[str, str]]]] = {}
    total = 0
    for value_name, raw in records:
        fields = _registry_rule_fields(raw)
        name = fields.get("Name", "")
        if name.startswith(RULE_PREFIX):
            groups.setdefault(name, []).append((value_name, fields))
            total += 1

    keep: set[str] = set()
    missing: list[str] = []
    for name, spec in specs.items():
        valid = [value_name for value_name, fields in groups.get(name, [])
                 if _valid_registry_rule(fields, spec)]
        if valid:
            keep.add(valid[0])
        else:
            missing.append(name)

    if missing:
        return [], missing, total
    remove = [value_name for entries in groups.values()
              for value_name, _fields in entries if value_name not in keep]
    return remove, [], total


def _read_registry_rules() -> list[tuple[str, str]]:
    import winreg

    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, FIREWALL_RULES_KEY) as key:
        count = winreg.QueryInfoKey(key)[1]
        records = []
        for index in range(count):
            value_name, value, _kind = winreg.EnumValue(key, index)
            if isinstance(value, str) and RULE_PREFIX in value:
                records.append((value_name, value))
        return records


def repair_duplicate_rules_registry() -> dict[str, object]:
    """Prune legacy duplicate DoH rules while retaining all 78 valid blocks.

    The normal 78-rule state is read only. A required-rule gap aborts before
    any deletion. A full registry backup is mandatory before pruning.
    """
    import winreg

    records = _read_registry_rules()
    remove, missing, before = _plan_registry_cleanup(records)
    expected = len(list(_rule_specs()))
    report: dict[str, object] = {
        "ok": not missing, "before": before, "after": before,
        "expected": expected, "removed": 0, "missing": missing,
        "reboot_required": False, "backup": "",
    }
    if missing:
        log.error("Firewall cleanup refused: %d required rules are absent or invalid", len(missing))
        return report
    if not remove:
        log.info("Firewall cleanup: %d valid rules, no changes needed", before)
        return report

    PROGRAM_DATA.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = PROGRAM_DATA / f"firewall-rules-before-dedup-{stamp}.reg"
    try:
        subprocess.run(
            ["reg.exe", "export", rf"HKLM\{FIREWALL_RULES_KEY}", str(backup), "/y"],
            capture_output=True, text=True, timeout=180, check=True,
        )
        if not backup.is_file() or backup.stat().st_size == 0:
            raise RuntimeError("firewall registry backup is empty")
        report["backup"] = str(backup)
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, FIREWALL_RULES_KEY,
                            0, winreg.KEY_SET_VALUE) as key:
            for value_name in remove:
                winreg.DeleteValue(key, value_name)
        final_records = _read_registry_rules()
        remaining, final_missing, after = _plan_registry_cleanup(final_records)
        report.update(
            ok=not remaining and not final_missing and after == expected,
            after=after, removed=before - after, missing=final_missing,
            reboot_required=before != after,
        )
        log.warning("Firewall duplicate cleanup: %d -> %d rules; backup=%s; reboot=%s",
                    before, after, backup, report["reboot_required"])
    except Exception as exc:
        report["ok"] = False
        report["error"] = str(exc)
        log.exception("Firewall duplicate cleanup failed; backup=%s", backup)
    return report


def block_doh_endpoints() -> int:
    """Idempotent: add only the rules that don't already exist. Returns the
    number of NEW rules added (existing rules counted in the log)."""
    fw = _get_fw_policy()
    if fw is None:
        return 0

    added = 0
    existing = 0
    try:
        import win32com.client
    except ImportError:
        return 0

    for name, protocol, port, remote_ip in _rule_specs():
        # Do NOT decide this from the enumeration snapshot alone. On a large
        # rule set the scan is slow and can return partial - _snapshot_existing
        # swallows per-rule errors - and every name it misses gets re-added.
        # That feedback loop is how 78 rules became 93723 duplicates: more
        # duplicates make the scan slower and more likely to come back short,
        # which adds more duplicates. Item() is an indexed lookup that cannot
        # go partial, so it is the authority here.
        if _rule_exists(fw, name, protocol, port, remote_ip):
            existing += 1
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
                 added, existing, len(list(_rule_specs())))
    return added


def _wipe_all_doh_rules(fw) -> int:
    """Remove every rule whose name starts with RULE_PREFIX during uninstall."""
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
    """Require all current DoH rules, using indexed lookups on every tick."""
    fw = _get_fw_policy()
    if fw is None:
        return False
    for name, protocol, port, address in _rule_specs():
        try:
            rule = fw.Rules.Item(name)
            if not rule or not _rule_matches(rule, protocol, port, address):
                return False
        except Exception:
            return False
    return True
