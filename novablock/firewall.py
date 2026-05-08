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
"""
import logging
import subprocess

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


def _run(cmd: list[str], timeout: int = 15) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except Exception as e:
        return -1, "", str(e)


def _add_rule(name: str, remote_ip: str, port: str, protocol: str) -> bool:
    code, _, err = _run([
        "netsh", "advfirewall", "firewall", "add", "rule",
        f"name={name}",
        "dir=out",
        "action=block",
        f"protocol={protocol}",
        f"remoteip={remote_ip}",
        f"remoteport={port}",
        "enable=yes",
    ])
    if code != 0:
        log.debug("add rule %s failed: %s", name, err)
        return False
    return True


def block_doh_endpoints() -> int:
    """Add Windows Firewall outbound block rules for DoH IPs on TCP/UDP 443/853.
    Returns the number of rules added."""
    n = 0
    for ip in DOH_IPS:
        # TCP 443 (HTTPS / DoH)
        rule = f"{RULE_PREFIX}TCP443_{ip.replace(':', '_').replace('.', '_')}"
        if _add_rule(rule, ip, "443", "TCP"):
            n += 1
        # TCP 853 (DoT)
        rule = f"{RULE_PREFIX}TCP853_{ip.replace(':', '_').replace('.', '_')}"
        if _add_rule(rule, ip, "853", "TCP"):
            n += 1
        # UDP 443 (HTTP/3 DoH)
        rule = f"{RULE_PREFIX}UDP443_{ip.replace(':', '_').replace('.', '_')}"
        if _add_rule(rule, ip, "443", "UDP"):
            n += 1
    log.info("DoH firewall: %d rules added", n)
    return n


def unblock_doh_endpoints() -> int:
    """Remove all NovaBlock DoH rules."""
    n = 0
    for ip in DOH_IPS:
        for proto, port in [("TCP", "443"), ("TCP", "853"), ("UDP", "443")]:
            rule = f"{RULE_PREFIX}{proto}{port}_{ip.replace(':', '_').replace('.', '_')}"
            c, _, _ = _run([
                "netsh", "advfirewall", "firewall", "delete", "rule",
                f"name={rule}"
            ])
            if c == 0:
                n += 1
    log.info("DoH firewall: %d rules removed", n)
    return n


def doh_blocked() -> bool:
    """Check if at least one NovaBlock DoH rule is active."""
    code, out, _ = _run([
        "netsh", "advfirewall", "firewall", "show", "rule",
        f"name={RULE_PREFIX}TCP443_1_1_1_1"
    ], timeout=10)
    return code == 0 and "Enabled:" in out and "Yes" in out
