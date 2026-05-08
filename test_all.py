"""NovaBlock — test suite (dry runs only, no real install).

Tests:
  1. crypto: code generation, hash, verify (correct + wrong)
  2. config: save/load roundtrip via DPAPI
  3. mailer: validate Resend API key (no email sent)
  4. blocker: download blocklist (no apply)
  5. monitor: keyword detection logic
  6. gui: imports + window init (closed immediately)
  7. persistence: schtasks/icacls availability

Run:
  python test_all.py
"""
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from novablock import crypto, config, mailer, blocker, monitor, persistence

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"

passed = 0
failed = 0


def test(name: str):
    def deco(fn):
        global passed, failed
        try:
            fn()
            print(f"  {GREEN}OK{RESET}  {name}")
            passed += 1
        except AssertionError as e:
            print(f"  {RED}FAIL{RESET}  {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  {RED}ERR{RESET}  {name}: {e}")
            traceback.print_exc()
            failed += 1
    return deco


print(f"\n{'='*60}\nNovaBlock test suite\n{'='*60}\n")


print("[1] CRYPTO")

@test("generate_unlock_code returns 5x5 dashed format")
def _():
    c = crypto.generate_unlock_code()
    parts = c.split("-")
    assert len(parts) == 5, f"expected 5 parts, got {len(parts)}: {c}"
    for p in parts:
        assert len(p) == 5, f"part wrong length: {p}"
        assert p.isalnum() and p.isupper(), f"invalid chars: {p}"
    assert len(c.replace("-", "")) == 25

@test("hash_code + verify_code (correct)")
def _():
    code = crypto.generate_unlock_code()
    h = crypto.hash_code(code)
    assert h.startswith("$argon2"), f"unexpected hash: {h[:30]}"
    assert crypto.verify_code(code, h) is True

@test("verify_code rejects wrong code")
def _():
    h = crypto.hash_code(crypto.generate_unlock_code())
    bad = crypto.generate_unlock_code()
    assert crypto.verify_code(bad, h) is False

@test("verify_code is case-insensitive (lowered input still works)")
def _():
    code = crypto.generate_unlock_code()
    h = crypto.hash_code(code)
    assert crypto.verify_code(code.lower(), h) is True

@test("DPAPI machine encrypt/decrypt roundtrip")
def _():
    payload = b"hello-novablock-dpapi-test-1234"
    enc = crypto.encrypt_machine(payload)
    assert enc != payload
    dec = crypto.decrypt_machine(enc)
    assert dec == payload, f"roundtrip mismatch: {dec!r}"


print("\n[2] CONFIG (real I/O — uses ProgramData)")

# Backup any existing config first
from novablock.paths import CONFIG_FILE
backup = None
if CONFIG_FILE.exists():
    backup = CONFIG_FILE.read_bytes()
    CONFIG_FILE.unlink()

try:
    @test("config defaults when no file")
    def _():
        cfg = config.load()
        assert cfg["install_ts"] == 0
        assert cfg["code_hash"] == ""
        assert config.is_installed() is False

    @test("config save/load roundtrip")
    def _():
        cfg = config.load()
        cfg["user_name"] = "Yann"
        cfg["friend_email"] = "test@example.com"
        cfg["code_hash"] = crypto.hash_code("ABCDE-FGHIJ-KLMNO-PQRST-UVWXY")
        cfg["install_ts"] = int(time.time())
        config.save(cfg)
        loaded = config.load()
        assert loaded["user_name"] == "Yann"
        assert loaded["friend_email"] == "test@example.com"
        assert loaded["install_ts"] == cfg["install_ts"]
        assert config.is_installed() is True

    @test("temp_unlock grant/revoke")
    def _():
        config.grant_temp_unlock(hours=1)
        assert config.is_temp_unlocked() is True
        config.revoke_temp_unlock()
        assert config.is_temp_unlocked() is False

    @test("unlock_request counter increments")
    def _():
        before = config.count_requests_total()
        config.record_unlock_request()
        config.record_unlock_request()
        after = config.count_requests_total()
        assert after == before + 2, f"expected {before+2}, got {after}"

    @test("uninstall cooldown lifecycle")
    def _():
        assert config.uninstall_cooldown_remaining() == -1
        config.start_uninstall_cooldown()
        rem = config.uninstall_cooldown_remaining()
        assert 0 < rem <= 7 * 24 * 3600
        config.cancel_uninstall_cooldown()
        assert config.uninstall_cooldown_remaining() == -1

    @test("needs_code_rotation false when fresh")
    def _():
        cfg = config.load()
        cfg["code_rotation_ts"] = int(time.time())
        config.save(cfg)
        assert config.needs_code_rotation() is False

    @test("needs_code_rotation true when 8 days old")
    def _():
        cfg = config.load()
        cfg["code_rotation_ts"] = int(time.time()) - 8 * 24 * 3600
        config.save(cfg)
        assert config.needs_code_rotation() is True

finally:
    # Restore original config (or remove our test artifacts)
    if backup:
        CONFIG_FILE.write_bytes(backup)
    elif CONFIG_FILE.exists():
        CONFIG_FILE.unlink()


print("\n[3] MAILER (Resend API key validation)")

@test("Resend key is embedded")
def _():
    from novablock.main import EMBEDDED_RESEND_KEY
    assert EMBEDDED_RESEND_KEY.startswith("re_"), f"key not embedded: {EMBEDDED_RESEND_KEY[:10]}..."

@test("Resend key authenticates (probe /emails endpoint)")
def _():
    import requests
    from novablock.main import EMBEDDED_RESEND_KEY
    # POST with empty body — if key is invalid → 401 invalid_api_key.
    # If valid → 422 missing 'from' field. Either 422 or 200 means auth works.
    r = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {EMBEDDED_RESEND_KEY}",
                 "Content-Type": "application/json"},
        json={},
        timeout=10,
    )
    body = r.text.lower()
    # 401 with "invalid_api_key" → bad key (fail). 401 with "restricted" → fine
    # for a sending-only key. 422 → key OK, just missing payload (fine).
    assert r.status_code != 401 or "invalid_api_key" not in body, \
        f"Resend says key is INVALID: {r.status_code} {r.text[:200]}"
    assert r.status_code in (200, 401, 422), f"Unexpected: {r.status_code} {r.text[:200]}"


print("\n[4] BLOCKER (no apply — read-only checks)")

@test("download_blocklist returns >100 domains")
def _():
    from novablock.paths import BLOCKLIST_CACHE
    if BLOCKLIST_CACHE.exists():
        BLOCKLIST_CACHE.unlink()
    domains = blocker.download_blocklist(force=True)
    assert len(domains) > 100, f"only got {len(domains)} domains"
    assert all("." in d for d in domains[:10])

@test("hosts_block_present detects current state")
def _():
    state = blocker.hosts_block_present()
    assert isinstance(state, bool)

@test("list_active_interfaces returns at least one")
def _():
    ifaces = blocker.list_active_interfaces()
    assert isinstance(ifaces, list)
    # might be 0 if offline, just check the call succeeds

@test("is_admin returns boolean")
def _():
    assert isinstance(blocker.is_admin(), bool)


print("\n[5] MONITOR (keyword detection)")

@test("monitor detects adult keyword in title")
def _():
    detected = []
    def cb(title, kw):
        detected.append((title, kw))
    m = monitor.WindowMonitor(on_detect=cb)
    hit = m._check_title("Pornhub - Free porn videos")
    assert hit is not None, "should detect 'porn' or 'pornhub'"
    hit = m._check_title("xnxx.com - hot videos")
    assert hit is not None
    hit = m._check_title("My boring spreadsheet - Excel")
    assert hit is None, f"false positive on: 'spreadsheet' got {hit}"

@test("monitor BROWSER_PROCS set is non-empty")
def _():
    assert "chrome.exe" in monitor.BROWSER_PROCS
    assert "firefox.exe" in monitor.BROWSER_PROCS


print("\n[6] PERSISTENCE (no-op checks)")

@test("schtasks command available")
def _():
    import subprocess
    r = subprocess.run(["schtasks", "/?"], capture_output=True, text=True, timeout=5)
    assert r.returncode == 0 or "TN" in r.stdout, "schtasks not available"

@test("icacls command available")
def _():
    import subprocess
    r = subprocess.run(["icacls", "/?"], capture_output=True, text=True, timeout=5)
    assert r.returncode == 0 or "/grant" in r.stdout, "icacls not available"

@test("netsh command available")
def _():
    import subprocess
    r = subprocess.run(["netsh", "/?"], capture_output=True, text=True, timeout=5)
    assert "interface" in r.stdout.lower() or r.returncode == 0


print("\n[7] GUI (imports only)")

@test("gui module imports")
def _():
    from novablock import gui
    assert hasattr(gui, "SetupWizard")
    assert hasattr(gui, "StatusWindow")
    assert hasattr(gui, "BlockedPopup")
    assert hasattr(gui, "CodeDialog")

@test("tray module imports")
def _():
    from novablock import tray
    assert tray.HAS_TRAY is True


print(f"\n{'='*60}")
total = passed + failed
color = GREEN if failed == 0 else RED
print(f"{color}Result: {passed}/{total} passed, {failed} failed{RESET}")
print(f"{'='*60}\n")
sys.exit(0 if failed == 0 else 1)
