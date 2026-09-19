"""Persistence layer: scheduled task + service registration so NovaBlock
relaunches automatically and resists kills. Run as admin."""
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from .paths import LOGON_TASK_NAME, TASK_NAME, exe_path

log = logging.getLogger("novablock.persistence")


def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except Exception as e:
        return -1, "", str(e)


def _exe() -> str:
    p = exe_path()
    return f'"{p}"'


def install_scheduled_task() -> bool:
    """Creates a scheduled task that:
    - runs at boot under SYSTEM
    - relaunches every 1 minute if not running
    - has highest privileges
    """
    cmd = _exe()
    xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>NovaBlock watchdog — relaunches the blocker if killed</Description>
  </RegistrationInfo>
  <Triggers>
    <BootTrigger>
      <Enabled>true</Enabled>
    </BootTrigger>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
    <TimeTrigger>
      <Repetition>
        <Interval>PT1M</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <StartBoundary>2024-01-01T00:00:00</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>S-1-5-18</UserId>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>false</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>5</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{Path(exe_path()).as_posix().replace('/', '\\')}</Command>
      <Arguments>--watchdog</Arguments>
    </Exec>
  </Actions>
</Task>
"""
    from .paths import PROGRAM_DATA, ensure_dirs
    ensure_dirs()
    xml_file = PROGRAM_DATA / "task.xml"
    xml_file.write_text(xml, encoding="utf-16")
    code, out, err = _run([
        "schtasks", "/Create", "/TN", TASK_NAME, "/XML", str(xml_file), "/F"
    ])
    if code != 0:
        log.error("schtasks create failed: %s", err)
        return False
    log.info("Scheduled task installed")
    return True


def remove_scheduled_task() -> bool:
    code, _, err = _run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"])
    if code != 0:
        log.warning("schtasks delete: %s", err)
        return False
    return True


def task_exists() -> bool:
    code, _, _ = _run(["schtasks", "/Query", "/TN", TASK_NAME])
    return code == 0


def _current_user_sid() -> str:
    """SID of the user installing NovaBlock — used so the logon task launches
    the full app under that user's interactive session (with their highest
    available privileges, no UAC prompt for admins)."""
    import getpass
    import win32security  # type: ignore
    sid_obj, _domain, _type = win32security.LookupAccountName(None, getpass.getuser())
    return win32security.ConvertSidToStringSid(sid_obj)


def install_logon_task() -> bool:
    """Creates a second scheduled task that launches the FULL app (tray +
    monitor + popup) at user logon, in the user's interactive session, with
    HighestAvailable privileges. This bypasses the UAC prompt that otherwise
    blocks HKLM\\Run and Startup folder shortcuts (because the manifest is
    'requireAdministrator')."""
    try:
        sid = _current_user_sid()
    except Exception as e:
        log.error("Cannot resolve current user SID for logon task: %s", e)
        return False

    xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>NovaBlock app — launches tray + monitor at user logon</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>{sid}</UserId>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{sid}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>false</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>5</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{Path(exe_path()).as_posix().replace('/', '\\')}</Command>
    </Exec>
  </Actions>
</Task>
"""
    from .paths import PROGRAM_DATA, ensure_dirs
    ensure_dirs()
    xml_file = PROGRAM_DATA / "task_app.xml"
    xml_file.write_text(xml, encoding="utf-16")
    code, _out, err = _run([
        "schtasks", "/Create", "/TN", LOGON_TASK_NAME, "/XML", str(xml_file), "/F"
    ])
    if code != 0:
        log.error("schtasks create logon task failed: %s", err)
        return False
    log.info("Logon scheduled task installed (user SID=%s)", sid)
    return True


def remove_logon_task() -> bool:
    code, _, err = _run(["schtasks", "/Delete", "/TN", LOGON_TASK_NAME, "/F"])
    if code != 0:
        log.warning("schtasks delete logon task: %s", err)
        return False
    return True


def logon_task_exists() -> bool:
    code, _, _ = _run(["schtasks", "/Query", "/TN", LOGON_TASK_NAME])
    return code == 0


def add_startup_registry() -> bool:
    """Backup persistence via HKLM Run key."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE,
        )
        winreg.SetValueEx(key, "NovaBlock", 0, winreg.REG_SZ, f'"{exe_path()}"')
        winreg.CloseKey(key)
        return True
    except Exception as e:
        log.warning("registry persistence failed: %s", e)
        return False


def remove_startup_registry() -> bool:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE,
        )
        winreg.DeleteValue(key, "NovaBlock")
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return True
    except Exception as e:
        log.warning("registry cleanup failed: %s", e)
        return False


def _common_startup_dir() -> Path:
    return (
        Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
        / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    )


def _user_startup_dir() -> Path:
    return (
        Path(os.environ.get("APPDATA", ""))
        / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    )


def _shortcut_path(common: bool) -> Path:
    base = _common_startup_dir() if common else _user_startup_dir()
    return base / "NovaBlock.lnk"


def add_startup_shortcut() -> bool:
    """Third persistence layer (after scheduled task + HKLM\\Run): a .lnk in the
    All Users Startup folder so the app launches at every logon even if the
    other two are tampered with. Falls back to the per-user Startup folder if
    All Users is not writable."""
    try:
        import win32com.client  # type: ignore
    except ImportError:
        log.warning("pywin32 missing — cannot create startup shortcut")
        return False

    target = str(exe_path())
    workdir = str(Path(exe_path()).parent)

    for common in (True, False):
        try:
            sc = _shortcut_path(common=common)
            sc.parent.mkdir(parents=True, exist_ok=True)
            shell = win32com.client.Dispatch("WScript.Shell")
            link = shell.CreateShortCut(str(sc))
            link.Targetpath = target
            link.WorkingDirectory = workdir
            link.Description = "NovaBlock — Adult content blocker"
            link.Save()
            log.info("Startup shortcut created at %s", sc)
            return True
        except Exception as e:
            log.warning("startup shortcut (common=%s) failed: %s", common, e)
            continue
    return False


def remove_startup_shortcut() -> bool:
    ok = True
    for common in (True, False):
        try:
            sc = _shortcut_path(common=common)
            if sc.exists():
                sc.unlink()
        except Exception as e:
            log.warning("startup shortcut removal (common=%s) failed: %s", common, e)
            ok = False
    return ok


def startup_shortcut_present() -> bool:
    return _shortcut_path(common=True).exists() or _shortcut_path(common=False).exists()


# ---------------------------------------------------------------------------
# Windows NT service — main protection layer against Task Manager kills.
# ---------------------------------------------------------------------------
# The service runs the same watchdog work as the scheduled task, but as a
# LocalSystem NT service instead of a per-minute scheduled action. Task
# Manager > Processes shows service processes differently and does not offer
# an "End task" that succeeds; the service can only be stopped via services
# .msc or `sc stop`, and even that path requires an admin who understands
# what they are doing. Combined with our restrictive DACL (set below) an
# admin has to take ownership of the service before Stop is accepted.
#
# The scheduled tasks and companion process stay in place as fallbacks.

from .service import SERVICE_NAME as _SERVICE_NAME


def _service_binpath() -> str:
    """binPath for sc.exe. We wrap the exe path in double quotes so any
    space in `C:\\Program Files\\...` doesn't split the argument."""
    exe = str(exe_path())
    return f'"{exe}" --service-run'


def install_service() -> bool:
    """Create the NovaBlockService via sc.exe. Idempotent: if the service
    already exists we just refresh its binPath (in case the exe moved after
    an update). Requires admin (setup wizard runs elevated)."""
    binpath = _service_binpath()

    # If the service exists, refresh its config only. Deleting first would
    # briefly leave a window with no protection.
    if service_exists():
        code, _out, err = _run([
            "sc.exe", "config", _SERVICE_NAME,
            "binPath=", binpath,
            "start=", "auto",
        ])
        if code != 0:
            log.warning("sc config refresh failed: %s", err)
            return False
        _apply_service_dacl()
        _run(["sc.exe", "description", _SERVICE_NAME,
              "NovaBlock system watchdog. Do not stop."])
        _run(["sc.exe", "start", _SERVICE_NAME])
        log.info("NovaBlockService config refreshed")
        return True

    code, _out, err = _run([
        "sc.exe", "create", _SERVICE_NAME,
        "binPath=", binpath,
        "start=", "auto",
        "DisplayName=", "NovaBlock Service",
        "type=", "own",
        "error=", "normal",
    ])
    if code != 0:
        log.error("sc create failed: %s", err)
        return False
    _run(["sc.exe", "description", _SERVICE_NAME,
          "NovaBlock system watchdog. Do not stop."])
    # Auto-restart on crash: reset every 24h, restart after 5s each of the
    # first two failures, then reset. Keeps the service alive even if the
    # user manages to crash it once.
    _run(["sc.exe", "failure", _SERVICE_NAME,
          "reset=", "86400",
          "actions=", "restart/5000/restart/5000/restart/30000"])
    _apply_service_dacl()
    _run(["sc.exe", "start", _SERVICE_NAME])
    log.info("NovaBlockService installed and started")
    return True


def _apply_service_dacl() -> None:
    """Tighten the service DACL so even an admin has to take ownership of
    the service before stopping it.

    Default service DACL is roughly:
      D:(A;;CCLCSWRPWPDTLOCRRC;;;SY)   SYSTEM full
      (A;;CCLCSWRPWPDTLOCRRC;;;BA)     Admin full (including STOP)
      (A;;CCLCSWLOCRRC;;;IU)           Interactive read
      (A;;CCLCSWLOCRRC;;;SU)           Service read

    We remove WP (write) from Admin so `sc stop` returns access denied
    unless they first take ownership. SY (SYSTEM) keeps full control so
    our own start/stop/config still work."""
    tight = (
        "D:"
        "(A;;CCLCSWRPWPDTLOCRRC;;;SY)"   # SYSTEM full
        "(A;;CCLCSWLORC;;;BA)"           # Admin: query/enum/start only, NO stop/delete/write
        "(A;;CCLCSWLORC;;;IU)"           # Interactive read
        "(A;;CCLCSWLORC;;;SU)"           # Service read
    )
    _run(["sc.exe", "sdset", _SERVICE_NAME, tight])


def remove_service() -> bool:
    """Stop + delete the service. Called during verified uninstall.
    The DACL lockdown from install_service applies to us too, so we
    take ownership back before Stop/Delete."""
    if not service_exists():
        return True
    # Restore permissive DACL so we can stop and delete cleanly.
    _run(["sc.exe", "sdset", _SERVICE_NAME,
          "D:(A;;CCLCSWRPWPDTLOCRRC;;;SY)(A;;CCLCSWRPWPDTLOCRRC;;;BA)"])
    _run(["sc.exe", "stop", _SERVICE_NAME])
    time.sleep(1)
    code, _out, err = _run(["sc.exe", "delete", _SERVICE_NAME])
    if code != 0:
        log.warning("sc delete failed: %s", err)
        return False
    log.info("NovaBlockService removed")
    return True


def service_exists() -> bool:
    code, _out, _err = _run(["sc.exe", "query", _SERVICE_NAME], timeout=10)
    return code == 0


def service_running() -> bool:
    code, out, _err = _run(["sc.exe", "query", _SERVICE_NAME], timeout=10)
    if code != 0:
        return False
    return "RUNNING" in out
