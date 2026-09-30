import os
import stat
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


def secure_program_data() -> int:
    """Keep state and recovery binaries writable only by Administrators/SYSTEM.

    Existing installations inherited Users:Write from ProgramData. Replace the
    DACL on the directory and its existing children. Never follow a junction or
    symlink outside the application directory.
    """
    import win32security  # type: ignore

    ensure_dirs()
    if getattr(PROGRAM_DATA.lstat(), "st_file_attributes", 0) & 0x400:
        raise RuntimeError("Application data directory is a reparse point")
    root = PROGRAM_DATA.resolve(strict=True)
    admin = win32security.ConvertStringSidToSid("S-1-5-32-544")
    system = win32security.ConvertStringSidToSid("S-1-5-18")
    flags = (win32security.DACL_SECURITY_INFORMATION |
             win32security.PROTECTED_DACL_SECURITY_INFORMATION)
    full_control = 0x1F01FF
    inherit_children = 0x03
    count = 0

    def already_secure(path: Path, directory: bool) -> bool:
        descriptor = win32security.GetNamedSecurityInfo(
            str(path), win32security.SE_FILE_OBJECT,
            win32security.DACL_SECURITY_INFORMATION,
        )
        control, _revision = descriptor.GetSecurityDescriptorControl()
        acl = descriptor.GetSecurityDescriptorDacl()
        if not (control & win32security.SE_DACL_PROTECTED) or acl is None:
            return False
        if acl.GetAceCount() != 2:
            return False
        expected = {"S-1-5-18", "S-1-5-32-544"}
        actual = set()
        for index in range(2):
            ace = acl.GetAce(index)
            ace_type, ace_flags = ace[0]
            if (ace_type != win32security.ACCESS_ALLOWED_ACE_TYPE or
                    (ace[1] & full_control) != full_control or
                    (ace_flags & inherit_children) != (inherit_children if directory else 0)):
                return False
            actual.add(win32security.ConvertSidToStringSid(ace[2]))
        return actual == expected

    def protect(path: Path, directory: bool) -> None:
        nonlocal count
        if already_secure(path, directory):
            return
        acl = win32security.ACL()
        ace_flags = inherit_children if directory else 0
        acl.AddAccessAllowedAceEx(win32security.ACL_REVISION_DS,
                                  ace_flags, full_control, system)
        acl.AddAccessAllowedAceEx(win32security.ACL_REVISION_DS,
                                  ace_flags, full_control, admin)
        win32security.SetNamedSecurityInfo(
            str(path), win32security.SE_FILE_OBJECT, flags,
            None, None, acl, None,
        )
        count += 1

    protect(root, True)
    pending = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                info = entry.stat(follow_symlinks=False)
                if getattr(info, "st_file_attributes", 0) & 0x400:
                    raise RuntimeError("Reparse point in protected application data")
                path = Path(entry.path)
                if os.path.commonpath((str(root), str(path.resolve()))) != str(root):
                    raise RuntimeError("Application data entry escaped its directory")
                is_directory = stat.S_ISDIR(info.st_mode)
                protect(path, is_directory)
                if is_directory:
                    pending.append(path)
    return count

def exe_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable)
    return Path(sys.argv[0]).resolve()
