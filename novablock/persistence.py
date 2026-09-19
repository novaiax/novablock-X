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
# Windows NT guardian service.
# ---------------------------------------------------------------------------
# This service is deliberately NOT a second network watchdog.
# DNS, hosts, browser policies and firewall repair remain owned by the normal
# v1.0.33 watchdog paths. The service only watches process liveness and asks
# the existing interactive NovaBlockApp scheduled task to relaunch the GUI.
#
# The old v1.0.34 service was named NovaBlockService. v1.0.35 migrates away
# from it so a stale installation cannot keep running the retired code path.

from .service import SERVICE_NAME as _SERVICE_NAME

_LEGACY_SERVICE_NAME = "NovaBlockService"
_FULL_SERVICE_DACL = (
    "D:"
    "(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;SY)"
    "(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)"
)
_TIGHT_SERVICE_DACL = (
    "D:"
    "(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;SY)"
    "(A;;CCLCSWRPLORCWD;;;BA)"
    "(A;;CCLCSWLOCRRC;;;IU)"
    "(A;;CCLCSWLOCRRC;;;SU)"
)


def _service_binpath() -> str:
    return f'"{exe_path()}" --service-run'


def _service_exists_name(name: str) -> bool:
    code, _out, _err = _run(["sc.exe", "query", name], timeout=10)
    return code == 0


def _remove_service_name(name: str) -> bool:
    if not _service_exists_name(name):
        return True

    # Administrators retain WRITE_DAC on the v1.0.35 service specifically so
    # a verified uninstall/update can restore full control before Stop/Delete.
    _run(["sc.exe", "sdset", name, _FULL_SERVICE_DACL])
    _run(["sc.exe", "stop", name])
    time.sleep(0.5)
    code, _out, err = _run(["sc.exe", "delete", name])
    if code != 0:
        log.warning("Could not delete service %s: %s", name, err)
        return False
    return True


def remove_legacy_service() -> bool:
    """Best-effort cleanup of the retired v1.0.34 NovaBlockService."""
    ok = _remove_service_name(_LEGACY_SERVICE_NAME)
    if ok:
        log.info("Legacy NovaBlockService absent or removed")
    return ok


def _apply_service_dacl() -> bool:
    code, _out, err = _run(["sc.exe", "sdset", _SERVICE_NAME, _TIGHT_SERVICE_DACL])
    if code != 0:
        log.warning("Could not tighten guardian service DACL: %s", err)
        return False
    return True


def install_service() -> bool:
    """Install/refresh the lightweight LocalSystem guardian.

    The guardian never touches DNS, hosts, browser policy or firewall state.
    It only relaunches the interactive NovaBlock process when it disappears.
    """
    # Remove the retired v1.0.34 service first. Failure is logged, but does not
    # stop us from installing the new guardian under a different service name.
    remove_legacy_service()

    binpath = _service_binpath()

    if _service_exists_name(_SERVICE_NAME):
        # Temporarily restore admin control so an in-place update can refresh
        # binPath/config, then tighten the DACL again.
        _run(["sc.exe", "sdset", _SERVICE_NAME, _FULL_SERVICE_DACL])
        code, _out, err = _run([
            "sc.exe", "config", _SERVICE_NAME,
            "binPath=", binpath,
            "start=", "auto",
        ])
        if code != 0:
            log.warning("sc config guardian refresh failed: %s", err)
            _apply_service_dacl()
            return False
    else:
        code, _out, err = _run([
            "sc.exe", "create", _SERVICE_NAME,
            "binPath=", binpath,
            "start=", "auto",
            "DisplayName=", "NovaBlock Guardian",
            "type=", "own",
            "error=", "normal",
        ])
        if code != 0:
            log.error("sc create guardian failed: %s", err)
            return False

    _run([
        "sc.exe", "description", _SERVICE_NAME,
        "NovaBlock lightweight guardian. Relaunch only; no DNS/hosts/firewall changes."
    ])
    _run([
        "sc.exe", "failure", _SERVICE_NAME,
        "reset=", "86400",
        "actions=", "restart/1000/restart/1000/restart/5000",
    ])
    _apply_service_dacl()
    _run(["sc.exe", "start", _SERVICE_NAME])
    log.info("NovaBlock Guardian installed/refreshed")
    return True


def remove_service() -> bool:
    """Remove v1.0.35 guardian and any leftover v1.0.34 service."""
    ok_guardian = _remove_service_name(_SERVICE_NAME)
    ok_legacy = _remove_service_name(_LEGACY_SERVICE_NAME)
    return ok_guardian and ok_legacy


def service_exists() -> bool:
    return _service_exists_name(_SERVICE_NAME)


def service_running() -> bool:
    code, out, _err = _run(["sc.exe", "query", _SERVICE_NAME], timeout=10)
    return code == 0 and "RUNNING" in out

