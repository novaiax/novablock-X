"""Best-effort resistance to ordinary external process termination.

A privileged administrator can override discretionary permissions. Recovery
must work independently of this layer; never treat the process as unkillable.
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
            # A null DACL grants everything. Do not accidentally turn it into
            # a deny-only DACL (which would also block all inspection rights).
            log.warning("Process has a null DACL; keeping it unchanged and relying on recovery")
            return False
        everyone = win32security.ConvertStringSidToSid("S-1-1-0")
        dacl = win32security.ACL()
        # Windows processes ACEs in order. Appending a deny after an existing
        # allow, as the previous implementation did, can leave terminate
        # permission already granted. Put the explicit deny FIRST.
        dacl.AddAccessDeniedAce(
            win32security.ACL_REVISION,
            PROCESS_TERMINATE | PROCESS_SUSPEND_RESUME,
            everyone,
        )
        for index in range(old_dacl.GetAceCount()):
            dacl.AddAce(win32security.ACL_REVISION, dacl.GetAceCount(), old_dacl.GetAce(index))
        win32security.SetSecurityInfo(
            handle, win32security.SE_KERNEL_OBJECT,
            win32security.DACL_SECURITY_INFORMATION,
            None, None, dacl, None,
        )
        log.info("Process DACL updated: explicit terminate/suspend deny placed before allow ACEs")
        return True
    except Exception as e:
        log.warning("could not harden process (will rely on scheduled recovery): %s", e)
        return False
