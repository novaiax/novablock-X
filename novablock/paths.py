import os
import sys
from pathlib import Path

PROGRAM_DATA = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "NovaBlock"
CONFIG_FILE = PROGRAM_DATA / "config.dat"
LOG_FILE = PROGRAM_DATA / "novablock.log"
HOSTS_BACKUP = PROGRAM_DATA / "hosts.original"
BLOCKLIST_CACHE = PROGRAM_DATA / "blocklist.txt"
LOCK_FILE = PROGRAM_DATA / "novablock.lock"
# Updated by the main-app in-process watchdog every tick. The headless
# --watchdog reads it to decide whether to re-apply: if the main app is
# active (recent heartbeat), the headless skips to avoid racing on hosts.
HEARTBEAT_FILE = PROGRAM_DATA / "watchdog.heartbeat"
# Mutual-watchdog: the main app and its companion process write their own PID
# to these files and each polls the other. If one dies, the other relaunches
# it. Used to defeat one-click 'End task' from Task Manager.
MAIN_PID_FILE = PROGRAM_DATA / "main.pid"
COMPANION_PID_FILE = PROGRAM_DATA / "companion.pid"
# Sentinel file: when present, the companion and main app exit themselves
# instead of respawning each other. Created only by the verified-code
# uninstall path. This is how a legitimate shutdown breaks the mutual-
# resurrection loop.
SHUTDOWN_SENTINEL = PROGRAM_DATA / "shutdown.sentinel"

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
