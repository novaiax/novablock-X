"""Test the 24h temp-unlock + auto-reactivation logic in-memory."""
import sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

GREEN = "\033[92m"; RED = "\033[91m"; BLUE = "\033[94m"; RESET = "\033[0m"
passed = failed = 0

def t(name, ok, detail=""):
    global passed, failed
    icon = f"{GREEN}[OK]{RESET}" if ok else f"{RED}[FAIL]{RESET}"
    print(f"   {icon} {name}{(' — ' + detail) if detail else ''}")
    if ok: passed += 1
    else: failed += 1


print(f"\n{BLUE}{'=' * 60}\n  TEMP UNLOCK 24H — TESTS\n{'=' * 60}{RESET}\n")

# Simulate config layer with an in-memory dict and the same logic as config.py
state = {"temp_unlock_until": 0}

def is_temp_unlocked():
    return state["temp_unlock_until"] > time.time()

def grant_temp_unlock(hours):
    state["temp_unlock_until"] = int(time.time() + hours * 3600)

def revoke_temp_unlock():
    state["temp_unlock_until"] = 0


print(f"{BLUE}[1] Lifecycle 24h temp unlock{RESET}")
t("État initial : pas unlock", is_temp_unlocked() is False)

grant_temp_unlock(24)
t("Après grant_temp_unlock(24) : unlock actif", is_temp_unlocked() is True)

# Simulate now+24h+1s
state["temp_unlock_until"] = int(time.time() - 1)
t("Après 24h écoulées : is_temp_unlocked() == False", is_temp_unlocked() is False)

# Simulate watchdog tick after expiry
expired = state["temp_unlock_until"] > 0 and state["temp_unlock_until"] <= time.time()
t("Watchdog détecte expiry (temp_unlock_until <= now)", expired is True)

revoke_temp_unlock()
t("Après revoke : timestamp à 0", state["temp_unlock_until"] == 0)


print(f"\n{BLUE}[2] Watchdog tick logic — simulation{RESET}")

# Simulate the watchdog _tick logic
def watchdog_tick(state, hosts_present_before):
    """Mirrors the actual watchdog logic in watchdog.py _tick().
    Returns (action, hosts_after) where action is 'remove'|'apply'|'noop'."""
    if is_temp_unlocked():
        if hosts_present_before:
            return ("remove", False)
        return ("noop", False)
    # not unlocked branch
    action = "noop"
    hosts_after = hosts_present_before
    if not hosts_present_before:
        action = "apply"
        hosts_after = True
    # ALWAYS check expiry (matches real code structure)
    if state["temp_unlock_until"] > 0 and state["temp_unlock_until"] <= time.time():
        revoke_temp_unlock()
    return (action, hosts_after)


# Scenario A: Code entered, grant 24h, hosts removed
grant_temp_unlock(24)
action, hosts_after = watchdog_tick(state, hosts_present_before=True)
t("[A] Pendant unlock — watchdog ENLEVE le hosts", action == "remove" and not hosts_after)

# Scenario B: 24h passed, hosts is currently empty (we removed it during unlock)
state["temp_unlock_until"] = int(time.time() - 1)  # expired
action, hosts_after = watchdog_tick(state, hosts_present_before=False)
t("[B] Après 24h — watchdog REAPPLIQUE le hosts", action == "apply" and hosts_after)
t("[B] revoke_temp_unlock appelé après expiry", state["temp_unlock_until"] == 0)

# Scenario C: After re-apply, next tick is no-op
state["temp_unlock_until"] = 0  # already revoked
action, hosts_after = watchdog_tick(state, hosts_present_before=True)
t("[C] Tick suivant — hosts reste, pas d'action", action == "noop" and hosts_after)


print(f"\n{BLUE}[3] Edge cases{RESET}")

# Just before expiry: still unlocked
state["temp_unlock_until"] = int(time.time() + 60)  # 60s left
t("60s avant expiry : encore unlock", is_temp_unlocked() is True)

# 1s after expiry: no longer unlocked
state["temp_unlock_until"] = int(time.time() - 1)
t("1s après expiry : not unlock", is_temp_unlocked() is False)

# Exactly at expiry (timestamp == now): not unlocked (strict >)
state["temp_unlock_until"] = int(time.time())
t("À T=expiry exact : not unlock (>, pas >=)", is_temp_unlocked() is False)


print(f"\n{BLUE}[4] Scénario réel : utilisateur entre code, 24h, retour blocage{RESET}")

# T0: install
state["temp_unlock_until"] = 0
hosts_active = True

# T0+1: user enters code → grant_temp_unlock(24), remove block
grant_temp_unlock(24)
hosts_active = False
t("[T0+1m] Unlock actif, hosts vide", is_temp_unlocked() and not hosts_active)

# T0+12h: user browsing freely
state["temp_unlock_until"] = int(time.time() + 12 * 3600)  # 12h left
t("[T0+12h] Toujours unlock", is_temp_unlocked())

# T0+24h: expiry
state["temp_unlock_until"] = int(time.time() - 60)  # expired 1min ago
# Watchdog tick (every 30s in-app, every 60s via scheduled task)
action, hosts_active = watchdog_tick(state, hosts_present_before=hosts_active)
t("[T0+24h] Watchdog réapplique le blocage", action == "apply" and hosts_active)
t("[T0+24h] is_temp_unlocked() == False", is_temp_unlocked() is False)

# T0+24h+5min: still blocked
action, hosts_active = watchdog_tick(state, hosts_present_before=hosts_active)
t("[T0+24h+5min] Toujours bloqué, no-op",
  action == "noop" and hosts_active and is_temp_unlocked() is False)


total = passed + failed
color = GREEN if failed == 0 else RED
print(f"\n{BLUE}{'=' * 60}{RESET}")
print(f"{color}Résultat : {passed}/{total} passés, {failed} échec{RESET}")
print(f"{BLUE}{'=' * 60}{RESET}")
sys.exit(0 if failed == 0 else 1)
