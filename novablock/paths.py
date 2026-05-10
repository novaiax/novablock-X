import os
import sys
from pathlib import Path

PROGRAM_DATA = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "NovaBlock"
CONFIG_FILE = PROGRAM_DATA / "config.dat"
LOG_FILE = PROGRAM_DATA / "novablock.log"
HOSTS_BACKUP = PROGRAM_DATA / "hosts.original"
BLOCKLIST_CACHE = PROGRAM_DATA / "blocklist.txt"
LOCK_FILE = PROGRAM_DATA / "novablock.lock"

WINDOWS_HOSTS = Path(r"C:\Windows\System32\drivers\etc\hosts")

BLOCK_MARKER_START = "# === NOVABLOCK START === DO NOT EDIT ==="
BLOCK_MARKER_END = "# === NOVABLOCK END ==="

TASK_NAME = "NovaBlockWatchdog"
LOGON_TASK_NAME = "NovaBlockApp"

def ensure_dirs():
    PROGRAM_DATA.mkdir(parents=True, exist_ok=True)

def exe_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable)
    return Path(sys.argv[0]).resolve()
