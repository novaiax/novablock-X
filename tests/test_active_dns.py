"""Effective family DNS must be present on every connected adapter."""

import json
import unittest
from unittest.mock import patch

from novablock import blocker


FAMILY = {
    "name": "Ethernet",
    "v4": ["1.1.1.3", "1.0.0.3"],
    "v6": ["2606:4700:4700::1113", "2606:4700:4700::1003"],
    "v6Enabled": True,
}


class ActiveDnsTests(unittest.TestCase):
    def test_active_dns_probe_parses_every_connected_adapter(self):
        rows = [FAMILY, {**FAMILY, "name": "Wi-Fi"}]
        with patch.object(blocker, "_run", return_value=(0, json.dumps(rows), "")) as run:
            self.assertEqual(blocker._active_dns_rows(), rows)
        self.assertIn("Get-NetAdapter", run.call_args.args[0][-1])
        self.assertIn("Get-DnsClientServerAddress", run.call_args.args[0][-1])

    def test_an_unfiltered_active_adapter_fails_even_if_another_is_family(self):
        wifi = {**FAMILY, "name": "Wi-Fi", "v4": ["192.168.1.1"]}
        with patch.object(blocker, "_active_dns_rows", return_value=[FAMILY, wifi]):
            self.assertFalse(blocker.dns_is_locked())

    def test_unfiltered_secondary_or_ipv6_fails(self):
        with patch.object(blocker, "_active_dns_rows", return_value=[
            {**FAMILY, "v4": ["1.1.1.3", "8.8.8.8"]},
        ]):
            self.assertFalse(blocker.dns_is_locked())
        with patch.object(blocker, "_active_dns_rows", return_value=[
            {**FAMILY, "v6": ["fe80::1"]},
        ]):
            self.assertFalse(blocker.dns_is_locked())

    def test_ipv6_disabled_adapter_needs_only_family_ipv4(self):
        with patch.object(blocker, "_active_dns_rows", return_value=[
            {**FAMILY, "v6": [], "v6Enabled": False},
        ]):
            self.assertTrue(blocker.dns_is_locked())

    def test_unavailable_probe_is_unknown_not_protected(self):
        with patch.object(blocker, "_active_dns_rows", return_value=None):
            self.assertIsNone(blocker.dns_is_locked())


if __name__ == "__main__":
    unittest.main()
