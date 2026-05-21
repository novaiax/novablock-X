"""Process self-hardening against ordinary kill.

Applies a deny-ACE to the current process kernel object that revokes
PROCESS_TERMINATE and PROCESS_SUSPEND_RESUME for *every* security
principal — including admins. The result:

* Task Manager 'End task' fails with 'Access is denied'.
* `taskkill /F /PID <pid>` fails the same way.
* `psutil.Process(pid).kill()` raises AccessDenied.

What still works (intentional):

* The process can terminate **itself** (sys.exit, os._exit, normal
  Python shutdown). The ACL is checked on TerminateProcess against a
  *handle*, not on the process exiting on its own.
* The SYSTEM-context scheduled task can launch a *new* NovaBlock.exe
  via CreateProcess — it doesn't need to terminate the old one.
* An admin who knows what they're doing can take ownership of the
  process and reset the DACL via SeTakeOwnershipPrivilege. That's a
  multi-step sequence Yann won't trigger by accident.

This is a defence-in-depth layer on top of the scheduled-task and
mutual-watchdog respawn. It's not a kernel-mode rootkit — it just
raises the bar from 'one click' to 'deliberate multi-step action'.
"""
import logging

log = logging.getLogger("novablock.protect")

# From WinNT.h — process-specific access rights we want to deny.
PROCESS_TERMINATE = 0x0001
PROCESS_SUSPEND_RESUME = 0x0800


def harden_current_process() -> bool:
    """Deny PROCESS_TERMINATE on the current process for Everyone.

    Returns True if the DACL was successfully tightened. Returns False
    (and only logs a warning) on any failure — we never abort startup
    because of this; the scheduled task + mutual watchdog are still in
    place as fallbacks.
    """
    try:
        import win32api
        import win32security
    except ImportError:
        log.warning("pywin32 missing — skipping process hardening")
        return False

    try:
        handle = win32api.GetCurrentProcess()
        sd = win32security.GetSecurityInfo(
            handle,
            win32security.SE_KERNEL_OBJECT,
            win32security.DACL_SECURITY_INFORMATION,
        )
        dacl = sd.GetSecurityDescriptorDacl()
        if dacl is None:
            dacl = win32security.ACL()

        # 'Everyone' SID — denies the right for absolutely every principal,
        # including the user who launched the process. The process can still
        # exit itself; only external Terminate is blocked.
        everyone, _, _ = win32security.LookupAccountName("", "Everyone")
        dacl.AddAccessDeniedAce(
            win32security.ACL_REVISION,
            PROCESS_TERMINATE | PROCESS_SUSPEND_RESUME,
            everyone,
        )

        win32security.SetSecurityInfo(
            handle,
            win32security.SE_KERNEL_OBJECT,
            win32security.DACL_SECURITY_INFORMATION,
            None,  # owner unchanged
            None,  # group unchanged
            dacl,  # new DACL
            None,  # sacl unchanged
        )
        log.info("Process hardened: PROCESS_TERMINATE denied to Everyone")
        return True
    except Exception as e:
        log.warning("could not harden process (will rely on watchdog respawn): %s", e)
        return False
