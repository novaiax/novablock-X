"""Scheduled-task recovery must reject retargeted or disabled actions."""

import unittest
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from novablock import paths, persistence


def _task_xml(*, command=r"C:\Apps\NovaBlock.exe", arguments="", sid="S-1-5-18",
              logon_type="", enabled="", trigger="BootTrigger") -> str:
    enabled_xml = f"<Enabled>{enabled}</Enabled>" if enabled else ""
    logon_xml = f"<LogonType>{logon_type}</LogonType>" if logon_type else ""
    arguments_xml = f"<Arguments>{arguments}</Arguments>" if arguments else ""
    return f'''<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
      <Triggers><{trigger}><Enabled>true</Enabled></{trigger}></Triggers>
      <Principals><Principal><UserId>{sid}</UserId>{logon_xml}
        <RunLevel>HighestAvailable</RunLevel></Principal></Principals>
      <Settings>{enabled_xml}</Settings>
      <Actions><Exec><Command>{command}</Command>{arguments_xml}</Exec></Actions>
    </Task>'''


class TaskValidationTests(unittest.TestCase):
    def test_logon_task_uses_interactive_owner_even_under_another_admin_token(self):
        import win32ts
        def session_info(_server, _session, kind):
            return "Yann" if kind == win32ts.WTSUserName else "LAPTOP"

        with patch.object(persistence, "_process_session_id", return_value=3), \
             patch("win32ts.WTSQuerySessionInformation", side_effect=session_info), \
             patch("win32security.LookupAccountName", return_value=("sid", "", 1)) as lookup, \
             patch("win32security.ConvertSidToStringSid", return_value="S-1-5-21-123"):
            self.assertEqual(persistence._current_user_sid(), "S-1-5-21-123")
            lookup.assert_called_once_with(None, r"LAPTOP\Yann")
        with patch.object(persistence, "_process_session_id", return_value=0):
            with self.assertRaises(RuntimeError):
                persistence._current_user_sid()

    def test_task_xml_escapes_an_install_path_with_ampersand(self):
        executable = Path(r"C:\Apps\Yann & Cyril\NovaBlock.exe")
        with tempfile.TemporaryDirectory() as temporary, \
             patch.object(paths, "PROGRAM_DATA", Path(temporary)), \
             patch.object(persistence, "exe_path", return_value=executable), \
             patch.object(persistence, "_current_user_sid", return_value="S-1-5-21-123"), \
             patch.object(persistence, "_run", return_value=(0, "", "")):
            self.assertTrue(persistence.install_scheduled_task())
            self.assertTrue(persistence.install_logon_task())
            ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
            for name in ("task.xml", "task_app.xml"):
                root = ET.parse(Path(temporary) / name).getroot()
                self.assertEqual(root.findtext(".//t:Exec/t:Command", namespaces=ns), str(executable))

    def test_system_task_requires_correct_executable_mode_and_principal(self):
        with patch.object(persistence, "exe_path", return_value=Path(r"C:\Apps\NovaBlock.exe")), \
             patch.object(persistence, "_run", return_value=(
                 0, _task_xml(arguments="--watchdog"), "")):
            self.assertTrue(persistence.task_exists())

        for xml in (
            _task_xml(command=r"C:\Temp\NovaBlock.exe", arguments="--watchdog"),
            _task_xml(arguments=""),
            _task_xml(arguments="--watchdog", sid="S-1-5-21-123"),
            _task_xml(arguments="--watchdog", enabled="false"),
        ):
            with self.subTest(xml=xml), \
                 patch.object(persistence, "exe_path", return_value=Path(r"C:\Apps\NovaBlock.exe")), \
                 patch.object(persistence, "_run", return_value=(0, xml, "")):
                self.assertFalse(persistence.task_exists())

    def test_interactive_task_rejects_wrong_user_or_arguments(self):
        valid = _task_xml(sid="S-1-5-21-123", logon_type="InteractiveToken",
                          trigger="LogonTrigger")
        with patch.object(persistence, "exe_path", return_value=Path(r"C:\Apps\NovaBlock.exe")), \
             patch.object(persistence, "_run", return_value=(0, valid, "")), \
             patch.object(persistence, "_current_user_sid", return_value="S-1-5-21-123"):
            self.assertTrue(persistence.logon_task_exists())
            self.assertTrue(persistence.logon_task_matches_current_user())

        altered = _task_xml(sid="S-1-5-21-999", logon_type="InteractiveToken",
                            arguments="--service-run", trigger="LogonTrigger")
        with patch.object(persistence, "exe_path", return_value=Path(r"C:\Apps\NovaBlock.exe")), \
             patch.object(persistence, "_run", return_value=(0, altered, "")), \
             patch.object(persistence, "_current_user_sid", return_value="S-1-5-21-123"):
            self.assertFalse(persistence.logon_task_exists())
            self.assertFalse(persistence.logon_task_matches_current_user())


if __name__ == "__main__":
    unittest.main()
