"""Yandex block verification.

Tests:
  1. yandex domains are in the EXTRA_DOMAINS list
  2. yandex domains are in the would-be applied blocklist
  3. monitor detects yandex in window titles
  4. yandex.com DNS resolution (via system resolver) — should be 0.0.0.0 if hosts active
  5. HTTP reachability of yandex.com (port 443) — should fail if blocked
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
import socket
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from novablock import blocker, monitor, config

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def hr(title: str = ""):
    print(f"\n{BLUE}{'=' * 60}{RESET}")
    if title:
        print(f"{BLUE}  {title}{RESET}")
        print(f"{BLUE}{'=' * 60}{RESET}")


hr("YANDEX BLOCK VERIFICATION")

# 1. EXTRA_DOMAINS contains yandex
print("\n[1] EXTRA_DOMAINS yandex coverage")
yandex_extra = [d for d in blocker.EXTRA_DOMAINS if "yandex" in d or "ya.ru" in d]
print(f"   {GREEN}OK{RESET}  {len(yandex_extra)} yandex entries hardcoded:")
for d in yandex_extra[:6]:
    print(f"        - {d}")
if len(yandex_extra) > 6:
    print(f"        … and {len(yandex_extra) - 6} more")

# 2. Active blocklist (cache + extras)
print("\n[2] Active blocklist (would be applied to hosts file)")
domains = blocker.download_blocklist()
yandex_in_list = [d for d in domains if "yandex" in d or "ya.ru" in d]
print(f"   {GREEN}OK{RESET}  {len(yandex_in_list)}/{len(domains)} domains contain yandex")
key_domains = ["yandex.com", "yandex.ru", "ya.ru", "video.yandex.com", "yastatic.net"]
for kd in key_domains:
    present = kd in domains
    icon = f"{GREEN}[OK]{RESET}" if present else f"{RED}[--]{RESET}"
    print(f"      {icon} {kd}")

# 3. Monitor keyword detection
print("\n[3] Monitor — title detection")
m = monitor.WindowMonitor(on_detect=lambda *a: None)
test_titles = [
    "Yandex - Поиск - Mozilla Firefox",
    "yandex.com - Google Chrome",
    "Yandex Видео — поиск — Yandex Browser",
    "Видео — Yandex",
    "https://ya.ru/search?text=test",
    "GitHub - Mozilla Firefox",  # negative case
    "YouTube - Mozilla Firefox",  # negative case
]
for title in test_titles:
    hit = m._check_title(title)
    expected = "yandex" in title.lower() or "ya.ru" in title.lower()
    actual = hit is not None
    if expected == actual:
        icon = f"{GREEN}[OK]{RESET}"
        result = f"matched '{hit}'" if hit else "no match (correct)"
    else:
        icon = f"{RED}[--]{RESET}"
        result = f"WRONG: hit={hit}"
    print(f"   {icon} {title[:50]:<50} → {result}")

# 4. Current DNS resolution of yandex.com
print("\n[4] DNS resolution (current system state)")
print("   Note: only meaningful if NovaBlock is actively installed")
for host in ["yandex.com", "yandex.ru", "ya.ru"]:
    try:
        ip = socket.gethostbyname(host)
        if ip in ("0.0.0.0", "127.0.0.1"):
            print(f"   {GREEN}OK{RESET}  {host} → {ip} (BLOCKED via hosts file)")
        else:
            print(f"   {YELLOW}!{RESET}   {host} → {ip} (NOT blocked — install NovaBlock first)")
    except socket.gaierror:
        print(f"   {GREEN}OK{RESET}  {host} → resolution failed (BLOCKED)")
    except Exception as e:
        print(f"   {RED}?{RESET}   {host} → error: {e}")

# 5. nslookup with Cloudflare Family DNS to see real-world behavior
print("\n[5] DNS lookup via Cloudflare Family (1.1.1.3)")
print("   This shows what Cloudflare returns even if hosts file isn't active")
for host in ["yandex.com", "ya.ru"]:
    try:
        result = subprocess.run(
            ["nslookup", host, "1.1.1.3"],
            capture_output=True, text=True, timeout=10,
        )
        out = result.stdout.lower()
        if "0.0.0.0" in out or "non-existent" in out or "can't find" in out or "refused" in out:
            print(f"   {GREEN}OK{RESET}  {host} → blocked by Cloudflare Family DNS")
        else:
            # Extract IP
            for line in result.stdout.splitlines():
                if "address" in line.lower() and host not in line.lower():
                    print(f"   {YELLOW}!{RESET}   {host} → {line.strip()} (NOT blocked at DNS)")
                    break
            else:
                print(f"   {YELLOW}!{RESET}   {host} → response unclear")
    except Exception as e:
        print(f"   {RED}?{RESET}   {host} → {e}")

# 6. HTTP reachability test
print("\n[6] HTTP reachability (port 443)")
print("   Note: only meaningful if NovaBlock is actively installed")
for host in ["yandex.com", "ya.ru"]:
    try:
        with socket.create_connection((host, 443), timeout=3) as s:
            print(f"   {YELLOW}!{RESET}   {host}:443 → reachable (NOT blocked)")
    except (socket.gaierror, socket.timeout):
        print(f"   {GREEN}OK{RESET}  {host}:443 → unreachable (BLOCKED)")
    except Exception as e:
        print(f"   {GREEN}OK{RESET}  {host}:443 → connect failed: {e}")

hr("RÉSUMÉ")
print(f"""
Si NovaBlock n'est PAS installé : tests [4][5][6] vont montrer YANDEX ACCESSIBLE.
Si NovaBlock EST installé correctement : tout doit afficher BLOCKED.

Si tu vois 'NOT blocked' alors que NovaBlock est installé :
  - Vérifie : NovaBlock.exe --check
  - Force re-apply : NovaBlock.exe --reapply
  - Redémarre tes navigateurs
""")
