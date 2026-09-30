"""The update must preserve one valid block per DoH rule name."""

import unittest
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from novablock import firewall, main


def _record(name: str, protocol: int, port: str, address: str, *, action="Block"):
    address_key = "RA6" if ":" in address else "RA4"
    raw = (f"v2.33|Action={action}|Active=TRUE|Dir=Out|Protocol={protocol}"
           f"|RPort={port}|{address_key}={address}|Name={name}|")
    return raw


class FirewallDuplicatePlannerTests(unittest.TestCase):
    def setUp(self):
        self.specs = list(firewall._rule_specs())
        self.records = [
            (f"rule-{index}", _record(name, protocol, port, address))
            for index, (name, protocol, port, address) in enumerate(self.specs)
        ]

    def test_healthy_78_rules_are_untouched(self):
        remove, missing, total = firewall._plan_registry_cleanup(self.records)
        self.assertEqual((remove, missing, total), ([], [], 78))

        with patch.object(firewall, "_read_registry_rules", return_value=self.records), \
             patch.object(firewall.subprocess, "run", side_effect=AssertionError("backup must not run")):
            report = firewall.repair_duplicate_rules_registry()
        self.assertEqual(report["before"], 78)
        self.assertEqual(report["after"], 78)
        self.assertEqual(report["removed"], 0)
        self.assertEqual(report["backup"], "")
        self.assertTrue(report["ok"])

    def test_duplicate_is_removed_after_retaining_a_valid_rule(self):
        self.records.append(("duplicate", self.records[0][1]))
        remove, missing, total = firewall._plan_registry_cleanup(self.records)
        self.assertEqual((remove, missing, total), (["duplicate"], [], 79))

    def test_invalid_first_rule_is_not_kept(self):
        name, protocol, port, address = self.specs[0]
        self.records[0] = ("invalid", _record(name, protocol, port, address, action="Allow"))
        self.records.append(("valid", _record(name, protocol, port, address)))
        remove, missing, total = firewall._plan_registry_cleanup(self.records)
        self.assertEqual((remove, missing, total), (["invalid"], [], 79))

    def test_legacy_single_address_formats_are_recognized(self):
        self.records[0] = (self.records[0][0], self.records[0][1].replace(
            "RA4=1.1.1.1|", "RA4=1.1.1.1/255.255.255.255|"))
        ipv6_index = next(index for index, spec in enumerate(self.specs) if ":" in spec[3])
        address = self.specs[ipv6_index][3]
        value_name, raw = self.records[ipv6_index]
        self.records[ipv6_index] = (value_name, raw.replace(
            f"RA6={address}|", f"RA6={address}-{address}|"))
        self.assertEqual(firewall._plan_registry_cleanup(self.records), ([], [], 78))

    def test_required_gap_prevents_all_deletion(self):
        self.records.pop()
        self.records.append(("duplicate", self.records[0][1]))
        remove, missing, total = firewall._plan_registry_cleanup(self.records)
        self.assertEqual(remove, [])
        self.assertEqual(len(missing), 1)
        self.assertEqual(total, 78)

    def test_legacy_70000_rule_set_plans_only_surplus_removal(self):
        surplus = 70_000 - len(self.records)
        legacy = self.records + [
            (f"legacy-{index}", self.records[index % len(self.records)][1])
            for index in range(surplus)
        ]
        remove, missing, total = firewall._plan_registry_cleanup(legacy)
        self.assertEqual(total, 70_000)
        self.assertEqual(len(remove), surplus)
        self.assertEqual(missing, [])
        self.assertFalse(set(remove).intersection(name for name, _raw in self.records))

    def test_watchdog_presence_check_requires_all_78_names(self):
        specs = {name: (protocol, port, address)
                 for name, protocol, port, address in self.specs}

        class Rules:
            def __init__(self, missing=None, disabled=None):
                self.missing = missing
                self.disabled = disabled
                self.lookups = 0

            def Item(self, name):
                self.lookups += 1
                if name == self.missing:
                    raise KeyError(name)
                protocol, port, address = specs[name]
                return SimpleNamespace(
                    Enabled=name != self.disabled,
                    Action=firewall.NET_FW_ACTION_BLOCK,
                    Direction=firewall.NET_FW_RULE_DIR_OUT,
                    Protocol=protocol,
                    RemotePorts=port,
                    RemoteAddresses=address,
                )

        rules = Rules(None)
        with patch.object(firewall, "_get_fw_policy", return_value=type("Policy", (), {"Rules": rules})()):
            self.assertTrue(firewall.doh_blocked())
        self.assertEqual(rules.lookups, 78)

        rules = Rules(self.specs[-1][0])
        with patch.object(firewall, "_get_fw_policy", return_value=type("Policy", (), {"Rules": rules})()):
            self.assertFalse(firewall.doh_blocked())
        self.assertEqual(rules.lookups, 78)

        rules = Rules(disabled=self.specs[-1][0])
        with patch.object(firewall, "_get_fw_policy", return_value=type("Policy", (), {"Rules": rules})()):
            self.assertFalse(firewall.doh_blocked())

    def test_disabled_existing_rule_is_reenabled(self):
        name, protocol, port, address = self.specs[0]
        rule = SimpleNamespace(
            Enabled=False, Action=firewall.NET_FW_ACTION_BLOCK,
            Direction=firewall.NET_FW_RULE_DIR_OUT, Protocol=protocol,
            RemotePorts=port, RemoteAddresses=address,
        )
        fw = SimpleNamespace(Rules=SimpleNamespace(Item=lambda _name: rule))
        self.assertTrue(firewall._rule_exists(fw, name, protocol, port, address))
        self.assertTrue(rule.Enabled)

    def test_update_cli_writes_a_report_without_starting_the_gui(self):
        report = {
            "ok": True, "before": 78, "after": 78, "expected": 78,
            "removed": 0, "missing": [], "reboot_required": False, "backup": "",
        }
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(sys, "argv", ["NovaBlock.exe", "--repair-firewall"]), \
                 patch.object(main, "setup_logging"), \
                 patch.object(main, "current_session_id", return_value=1), \
                 patch.object(main, "is_admin", return_value=True), \
                 patch.object(main, "PROGRAM_DATA", Path(temporary)), \
                 patch.object(firewall, "block_doh_endpoints") as apply, \
                 patch.object(firewall, "repair_duplicate_rules_registry", return_value=report):
                self.assertEqual(main.main(), 0)
            self.assertEqual(json.loads(
                (Path(temporary) / "firewall-repair-report.json").read_text()), report)
            apply.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
