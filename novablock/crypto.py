import secrets
import string
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

try:
    import win32crypt
    HAS_DPAPI = True
except ImportError:
    HAS_DPAPI = False

CRYPTPROTECT_LOCAL_MACHINE = 0x4

_ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)

CODE_ALPHABET = string.ascii_uppercase + string.digits
CODE_LENGTH = 25


def generate_unlock_code() -> str:
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
    return f"{raw[:5]}-{raw[5:10]}-{raw[10:15]}-{raw[15:20]}-{raw[20:25]}"


def hash_code(plain: str) -> str:
    return _ph.hash(plain.strip().upper())


def verify_code(plain: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, plain.strip().upper())
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def encrypt_machine(data: bytes) -> bytes:
    if not HAS_DPAPI:
        raise RuntimeError("DPAPI unavailable; pywin32 required")
    blob = win32crypt.CryptProtectData(
        data, "NovaBlock", None, None, None, CRYPTPROTECT_LOCAL_MACHINE
    )
    return blob


def decrypt_machine(blob: bytes) -> bytes:
    if not HAS_DPAPI:
        raise RuntimeError("DPAPI unavailable; pywin32 required")
    _desc, data = win32crypt.CryptUnprotectData(blob, None, None, None, CRYPTPROTECT_LOCAL_MACHINE)
    return data
