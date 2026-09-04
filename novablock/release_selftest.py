"""Side-effect-free release smoke test, invoked only by --self-test REPORT.

Does not install NovaBlock, edit configuration, touch filtering, or send mail.
The short-lived test process checks its own DACL and a uniquely named mutex.
"""
import json
import os
import sys
import time
import traceback
import uuid
from pathlib import Path


def run(report_path: str) -> int:
    result = {"ok": False, "checks": {}, "pid": os.getpid(),
              "packaged_dir": getattr(sys, "_MEIPASS", "")}
    report = Path(report_path)
    child_flag = "NOVABLOCK_RELEASE_TEST_CHILD"
    try:
        import win32api
        import win32security
        import psutil
        import tkinter
        from . import single_instance, process_protect, companion
        checks = result["checks"]
        checks["native_dependencies"] = bool(win32api.GetCurrentProcessId() and psutil.pid_exists(os.getpid()))
        old_name = single_instance.MUTEX_NAME
        single_instance.MUTEX_NAME = "Local\\NovaBlock_ReleaseTest_" + uuid.uuid4().hex
        try:
            checks["mutex_initially_absent"] = not single_instance.is_running()
            checks["mutex_acquired"] = single_instance.acquire()
            checks["mutex_detected"] = single_instance.is_running()
            single_instance.release()
            checks["mutex_closed"] = not single_instance.is_running()
        finally:
            single_instance.release()
            single_instance.MUTEX_NAME = old_name
        checks["process_hardening_applied"] = process_protect.harden_current_process()
        sd = win32security.GetSecurityInfo(
            win32api.GetCurrentProcess(), win32security.SE_KERNEL_OBJECT,
            win32security.DACL_SECURITY_INFORMATION,
        )
        ace = sd.GetSecurityDescriptorDacl().GetAce(0)
        mask = process_protect.PROCESS_TERMINATE | process_protect.PROCESS_SUSPEND_RESUME
        checks["deny_ace_first"] = ace[0][0] == win32security.ACCESS_DENIED_ACE_TYPE and (ace[1] & mask) == mask
        if os.environ.get(child_flag) != "1":
            child_report = report.with_name(report.name + ".child.json")
            child_report.unlink(missing_ok=True)
            previous = os.environ.get(child_flag)
            os.environ[child_flag] = "1"
            try:
                pid = companion._spawn(companion._command("--self-test", str(child_report)))
            finally:
                if previous is None:
                    os.environ.pop(child_flag, None)
                else:
                    os.environ[child_flag] = previous
            deadline = time.monotonic() + 60
            while pid and not child_report.exists() and time.monotonic() < deadline:
                time.sleep(0.2)
            child = json.loads(child_report.read_text(encoding="utf-8")) if child_report.exists() else {}
            checks["independent_child_started"] = bool(child.get("ok"))
            if getattr(sys, "frozen", False):
                checks["separate_onefile_resources"] = bool(child.get("packaged_dir")) and child["packaged_dir"] != result["packaged_dir"]
            result["child"] = child
        result["ok"] = all(checks.values())
    except Exception:
        result["error"] = traceback.format_exc()
    report.parent.mkdir(parents=True, exist_ok=True)
    tmp = report.with_name(report.name + ".tmp")
    tmp.write_text(json.dumps(result, indent=2), encoding="utf-8")
    tmp.replace(report)
    return 0 if result["ok"] else 1
