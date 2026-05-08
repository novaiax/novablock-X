"""Comprehensive code-unlock flow test.

Verifies that the 25-char unlock code mechanism works end-to-end including:
  - Code generation format
  - Hash + verify (correct case)
  - User-input edge cases: lowercase, leading/trailing space, line breaks
  - Wrong codes rejected
  - Hash rotation (each new code invalidates the previous)
  - Full flow: setup → emit → request unlock → friend gets new code → user enters → unlock
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from novablock import crypto, config

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

passed = 0
failed = 0

def t(name: str, ok: bool, detail: str = ""):
    global passed, failed
    if ok:
        print(f"   {GREEN}[OK]{RESET}   {name}{(' — ' + detail) if detail else ''}")
        passed += 1
    else:
        print(f"   {RED}[FAIL]{RESET} {name}{(' — ' + detail) if detail else ''}")
        failed += 1


print(f"\n{BLUE}{'=' * 60}\n  CODE UNLOCK FLOW — TESTS\n{'=' * 60}{RESET}\n")

# ---------- Section 1: format ----------
print(f"{BLUE}[1] Format du code{RESET}")
code = crypto.generate_unlock_code()
t("Format 5x5 dashed", code.count("-") == 4 and len(code) == 29, f"got {code}")
t("All chars uppercase + alnum", all(c.isalnum() and (c.isupper() or c.isdigit()) for c in code if c != "-"))
t("Length without dashes = 25", len(code.replace("-", "")) == 25)

# Generate 100 codes — check uniqueness
codes = {crypto.generate_unlock_code() for _ in range(100)}
t("100 codes uniques", len(codes) == 100, f"got {len(codes)}/100 unique")

# ---------- Section 2: basic hash + verify ----------
print(f"\n{BLUE}[2] Hash + verify standard{RESET}")
code = crypto.generate_unlock_code()
h = crypto.hash_code(code)
t("Hash starts with $argon2", h.startswith("$argon2"))
t("Verify correct code", crypto.verify_code(code, h) is True)
t("Verify wrong code rejected", crypto.verify_code(crypto.generate_unlock_code(), h) is False)
t("Verify empty rejected", crypto.verify_code("", h) is False)
t("Verify random garbage rejected", crypto.verify_code("xxxxxxxxxxxxxxxxxxxxxxxxx", h) is False)

# ---------- Section 3: user-input edge cases ----------
print(f"\n{BLUE}[3] Cas d'usage utilisateur (copy/paste imparfait){RESET}")
code = crypto.generate_unlock_code()
h = crypto.hash_code(code)

t("Lowercase entrée", crypto.verify_code(code.lower(), h) is True)
t("Mixed case entrée", crypto.verify_code(code.swapcase(), h) is True)
t("Avec espaces avant/après", crypto.verify_code(f"   {code}   ", h) is True)
t("Avec tabulations", crypto.verify_code(f"\t{code}\t", h) is True)
t("Avec newlines", crypto.verify_code(f"\n{code}\n", h) is True)

# Truncated/extra chars should fail
t("Code tronqué 1 char en moins", crypto.verify_code(code[:-1], h) is False)
t("Code avec 1 char en plus", crypto.verify_code(code + "X", h) is False)
t("Code avec un caractère changé", crypto.verify_code(code[:-2] + "ZZ", h) is False)

# Without dashes (user might strip them)
code_no_dash = code.replace("-", "")
t("Code sans tirets — doit échouer (différent format)", crypto.verify_code(code_no_dash, h) is False)

# ---------- Section 4: hash rotation ----------
print(f"\n{BLUE}[4] Rotation du hash (sécurité){RESET}")
code1 = crypto.generate_unlock_code()
code2 = crypto.generate_unlock_code()
h1 = crypto.hash_code(code1)
h2 = crypto.hash_code(code2)

t("Deux hash de codes différents diffèrent", h1 != h2)
t("Code1 valide contre h1", crypto.verify_code(code1, h1) is True)
t("Code1 invalide contre h2", crypto.verify_code(code1, h2) is False)
t("Code2 invalide contre h1", crypto.verify_code(code2, h1) is False)

# Same code hashed twice produces different hashes (salt) but both verify
ha = crypto.hash_code(code1)
hb = crypto.hash_code(code1)
t("Salt unique : h(code) ≠ h(code)", ha != hb)
t("Mais les deux verify correctement", crypto.verify_code(code1, ha) and crypto.verify_code(code1, hb))

# ---------- Section 5: full flow simulation (in-memory, no real config) ----------
print(f"\n{BLUE}[5] Flow complet : install → demander → débloquer (in-memory){RESET}")

# Simulate the config storage in memory only — no I/O on real config file
state: dict = {"code_hash": ""}

# Step 1: setup
setup_code = crypto.generate_unlock_code()
state["code_hash"] = crypto.hash_code(setup_code)
t("[setup] Hash de setup généré", bool(state["code_hash"]))
t("[setup] Code initial fonctionne", crypto.verify_code(setup_code, state["code_hash"]) is True)

# Step 2: user clicks "demander" → new code, hash updated
new_code = crypto.generate_unlock_code()
state["code_hash"] = crypto.hash_code(new_code)
t("[demande] Ancien code (setup) ne fonctionne PLUS",
  crypto.verify_code(setup_code, state["code_hash"]) is False)
t("[demande] Nouveau code fonctionne",
  crypto.verify_code(new_code, state["code_hash"]) is True)

# Step 3: edge cases — friend copy/pastes the code from email
t("[email] Préfixe espace OK",
  crypto.verify_code(" " + new_code, state["code_hash"]) is True)
t("[email] Suffixe espace + retour ligne OK",
  crypto.verify_code(new_code + " \n", state["code_hash"]) is True)
t("[email] Code en lowercase (recopié à la main) OK",
  crypto.verify_code(new_code.lower(), state["code_hash"]) is True)
t("[email] Mauvais caractère — refusé",
  crypto.verify_code(new_code[:-3] + "ZZZ", state["code_hash"]) is False)

# Step 4: silent rotation (after 7 days)
sentinel = crypto.generate_unlock_code()
state["code_hash"] = crypto.hash_code(sentinel)
t("[rotation 7j] Code 'demande' invalidé silencieusement",
  crypto.verify_code(new_code, state["code_hash"]) is False)

# Step 5: next demande generates a new code
fresh_code = crypto.generate_unlock_code()
state["code_hash"] = crypto.hash_code(fresh_code)
t("[nouvelle demande] Génère un code valide",
  crypto.verify_code(fresh_code, state["code_hash"]) is True)

# Step 6: replay attack — old code can never come back
t("[sécurité] Anciens codes ne reviennent jamais valides",
  crypto.verify_code(setup_code, state["code_hash"]) is False
  and crypto.verify_code(new_code, state["code_hash"]) is False
  and crypto.verify_code(sentinel, state["code_hash"]) is False)

# ---------- summary ----------
total = passed + failed
color = GREEN if failed == 0 else RED
print(f"\n{BLUE}{'=' * 60}{RESET}")
print(f"{color}Résultat : {passed}/{total} passés, {failed} échec{RESET}")
print(f"{BLUE}{'=' * 60}{RESET}\n")
sys.exit(0 if failed == 0 else 1)
