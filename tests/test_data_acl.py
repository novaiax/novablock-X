"""The data directory must not keep ProgramData's inherited Users:Write ACE."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import win32security

from novablock import paths


class DataAclTests(unittest.TestCase):
    def test_root_reparse_point_is_rejected_before_any_acl_change(self):
        with patch.object(paths, "ensure_dirs"), \
             patch.object(paths, "PROGRAM_DATA") as root, \
             patch.object(win32security, "SetNamedSecurityInfo") as setter:
            root.lstat.return_value = SimpleNamespace(st_file_attributes=0x400)
            with self.assertRaises(RuntimeError):
                paths.secure_program_data()
            setter.assert_not_called()

    def test_every_existing_entry_gets_only_admin_and_system_full_control(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            nested = root / "nested"
            nested.mkdir(parents=True)
            (root / "config.dat").write_bytes(b"encrypted")
            (nested / "main.pid").write_text("123", encoding="ascii")
            calls = []
            with patch.object(paths, "PROGRAM_DATA", root), \
                 patch.object(win32security, "SetNamedSecurityInfo",
                              side_effect=lambda *args: calls.append(args)):
                self.assertEqual(paths.secure_program_data(), 4)
            self.assertEqual({Path(args[0]).resolve() for args in calls}, {
                root.resolve(), nested.resolve(), (root / "config.dat").resolve(),
                (nested / "main.pid").resolve(),
            })
            for _name, _object_type, flags, _owner, _group, acl, _sacl in calls:
                self.assertTrue(flags & win32security.PROTECTED_DACL_SECURITY_INFORMATION)
                sids = {
                    win32security.ConvertSidToStringSid(acl.GetAce(index)[2])
                    for index in range(acl.GetAceCount())
                }
                self.assertEqual(sids, {"S-1-5-18", "S-1-5-32-544"})


if __name__ == "__main__":
    unittest.main()
