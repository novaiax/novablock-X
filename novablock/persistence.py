"""Persistence layer: scheduled task + service registration so NovaBlock
relaunches automatically and resists kills. Run as admin."""
import logging
import os
import subprocess
import sys
from pathlib import Path

from .paths import TASK_NAME, exe_path

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
      <Command>{Path(exe_path()).as_posix().replace('/', '\\\\')}</Command>
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
