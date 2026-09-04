"""Best-effort resistance to ordinary external process termination.

A privileged administrator can override discretionary permissions. Recovery
must work independently; a user-space process is not unkillable.
The process can still exit itself during an update or verified uninstall.
"""
import logging

log = logging.getLogger("novablock.protect")
PROCESS_TERMINATE = 0x0001
PROCESS_SUSPEND_RESUME = 0x0800


def harden_current_process() -> bool:
    try:
        import win32api
        import win32security
    except ImportError:
        log.warning("pywin32 missing — skipping process hardening")
        return False
    try:
        handle = win32api.GetCurrentProcess()
        sd = win32security.GetSecurityInfo(
            handle, win32security.SE_KERNEL_OBJECT,
            win32security.DACL_SECURITY_INFORMATION,
        )
        old_dacl = sd.GetSecurityDescriptorDacl()
        if old_dacl is None:
            log.warning("Process has a null DACL; leaving it unchanged and relying on recovery")
            return False
        everyone = win32security.ConvertStringSidToSid("S-1-1-0")
        revision = win32security.ACL_REVISION_DS
        dacl = win32security.ACL()
        # Explicit deny first, before any existing grant of terminate rights.
        dacl.AddAccessDeniedAceEx(
            revision, 0, PROCESS_TERMINATE | PROCESS_SUSPEND_RESUME, everyone,
        )
        # PyACL has no generic AddAce method. Copy each supported ACE with
        # its original flags, access mask, SID and optional object GUIDs.
        # Unknown ACE types abort BEFORE applying changes, never drop them.
        for index in range(old_dacl.GetAceCount()):
            ace = old_dacl.GetAce(index)
            ace_type, flags = ace[0]
            if ace_type == win32security.ACCESS_ALLOWED_ACE_TYPE:
                dacl.AddAccessAllowedAceEx(revision, flags, ace[1], ace[2])
            elif ace_type == win32security.ACCESS_DENIED_ACE_TYPE:
                dacl.AddAccessDeniedAceEx(revision, flags, ace[1], ace[2])
            elif ace_type == win32security.ACCESS_ALLOWED_OBJECT_ACE_TYPE:
                dacl.AddAccessAllowedObjectAce(revision, flags, ace[1], ace[2], ace[3], ace[4])
            elif ace_type == win32security.ACCESS_DENIED_OBJECT_ACE_TYPE:
                dacl.AddAccessDeniedObjectAce(revision, flags, ace[1], ace[2], ace[3], ace[4])
            else:
                raise ValueError(f"Unsupported process ACE type {ace_type}; original DACL preserved")
        win32security.SetSecurityInfo(
            handle, win32security.SE_KERNEL_OBJECT,
            win32security.DACL_SECURITY_INFORMATION,
            None, None, dacl, None,
        )
        log.info("Process DACL updated: terminate/suspend deny before allow ACEs")
        return True
    except Exception as e:
        log.warning("could not harden process (will rely on scheduled recovery): %s", e)
        return False
