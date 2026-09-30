"""Persistence layer: scheduled task + service registration so NovaBlock
relaunches automatically and resists kills. Run as admin."""
import logging
import os
import subprocess
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape
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


def install_scheduled_task() -> bool:
    """Creates a scheduled task that:
    - runs at boot under SYSTEM
    - relaunches every 1 minute if not running
    - has highest privileges
    """
    command = escape(str(exe_path()))
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
      <Command>{command}</Command>
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
    return _scheduled_task_valid(TASK_NAME, "--watchdog", system=True)


def _scheduled_task_valid(task_name: str, arguments: str, *, system: bool = False,
                          user_sid: str | None = None) -> bool:
    """Presence alone is insufficient: reject disabled or retargeted tasks."""
    code, xml, _error = _run(["schtasks", "/Query", "/TN", task_name, "/XML"])
    if code != 0:
        return False
    try:
        root = ET.fromstring(xml)
        ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
        get = lambda path: (root.findtext(path, default="", namespaces=ns) or "").strip()
        command = get(".//t:Exec/t:Command").strip('"')
        expected = str(exe_path())
        if os.path.normcase(os.path.abspath(command)) != os.path.normcase(os.path.abspath(expected)):
            return False
        if get(".//t:Exec/t:Arguments") != arguments:
            return False
        # Task Scheduler omits Enabled when it uses the default True value.
        if get("./t:Settings/t:Enabled").lower() == "false":
            return False
        if get(".//t:Principal/t:RunLevel") != "HighestAvailable":
            return False
        sid = get(".//t:Principal/t:UserId")
        if system:
            return sid.upper() == "S-1-5-18" and root.find(".//t:BootTrigger", ns) is not None
        if get(".//t:Principal/t:LogonType") != "InteractiveToken":
            return False
        if user_sid and sid != user_sid:
            return False
        return root.find(".//t:LogonTrigger", ns) is not None
    except (ValueError, ET.ParseError, OSError):
        return False


def _process_session_id() -> int:
    import ctypes
    session = ctypes.c_uint32()
    if not ctypes.windll.kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(session)):
        raise RuntimeError("Cannot identify the interactive Windows session")
    return int(session.value)


def _current_user_sid() -> str:
    """Use the interactive session owner, not a different UAC admin account."""
    import win32security  # type: ignore
    import win32ts  # type: ignore

    session = _process_session_id()
    if session == 0:
        raise RuntimeError("Cannot register an interactive task from session 0")
    server = win32ts.WTS_CURRENT_SERVER_HANDLE
    user = win32ts.WTSQuerySessionInformation(server, session, win32ts.WTSUserName)
    domain = win32ts.WTSQuerySessionInformation(server, session, win32ts.WTSDomainName)
    if not user:
        raise RuntimeError("Interactive Windows session has no user")
    account = f"{domain}\\{user}" if domain else user
    sid_obj, _domain, _type = win32security.LookupAccountName(None, account)
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
    command = escape(str(exe_path()))

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
      <Command>{command}</Command>
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
    return _scheduled_task_valid(LOGON_TASK_NAME, "")


def logon_task_matches_current_user() -> bool:
    try:
        return _scheduled_task_valid(LOGON_TASK_NAME, "", user_sid=_current_user_sid())
    except Exception:
        return False


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


def startup_registry_matches() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
            value, kind = winreg.QueryValueEx(key, "NovaBlock")
        actual = os.path.normcase(os.path.abspath(str(value).strip().strip('"')))
        expected = os.path.normcase(os.path.abspath(str(exe_path())))
        return kind == winreg.REG_SZ and actual == expected
    except (ImportError, OSError, ValueError):
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
    try:
        import win32com.client  # type: ignore
        shell = win32com.client.Dispatch("WScript.Shell")
        expected = os.path.normcase(os.path.abspath(str(exe_path())))
        for common in (True, False):
            shortcut = _shortcut_path(common=common)
            if shortcut.exists():
                target = shell.CreateShortCut(str(shortcut)).Targetpath
                if os.path.normcase(os.path.abspath(str(target))) == expected:
                    return True
    except Exception as exc:
        log.warning("Cannot verify startup shortcut: %s", exc)
    return False
