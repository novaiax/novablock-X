"""Safety tests for family-filtering DNS selection and application.

All network and command execution is mocked; no live DNS is changed.
"""

import unittest
from unittest.mock import patch

from novablock import blocker


UNFILTERED_QUAD9 = {"9.9.9.10", "149.112.112.10", "2620:fe::10", "2620:fe::fe:10"}


class FamilyDNSTests(unittest.TestCase):
    def test_only_verified_family_providers_are_configured(self):
        configured = {address for entry in blocker.DNS_FALLBACKS for address in entry[1:]}
        self.assertTrue(configured.isdisjoint(UNFILTERED_QUAD9))
        self.assertEqual([entry[0] for entry in blocker.DNS_FALLBACKS], [
            "Cloudflare Family", "CleanBrowsing Family", "OpenDNS FamilyShield",
        ])
        self.assertTrue(all(entry[3] and entry[4] for entry in blocker.DNS_FALLBACKS))

    def test_reachable_family_provider_is_selected_in_order(self):
        probes = []

        def reachable(address, timeout):
            probes.append((address, timeout))
            return address == "185.228.168.168"

        with patch.object(blocker, "_dns_reachable", side_effect=reachable):
            selected = blocker.choose_family_dns()
        self.assertEqual(selected[0], "CleanBrowsing Family")
        self.assertEqual([address for address, _ in probes], ["1.1.1.3", "185.228.168.168"])

    def test_no_reachable_provider_keeps_filtered_default(self):
        with patch.object(blocker, "_dns_reachable", return_value=False):
            self.assertEqual(blocker.choose_family_dns(), blocker.DNS_FALLBACKS[0])

    def test_dns_timeout_aborts_without_touching_other_stacks(self):
        commands = []

        def run(command, **_kwargs):
            commands.append(command)
            return 1, "", "timeout"

        with patch.object(blocker, "choose_family_dns", return_value=blocker.DNS_FALLBACKS[0]), \
             patch.object(blocker, "list_active_interfaces", return_value=["Ethernet"]), \
             patch.object(blocker, "_run", side_effect=run):
            self.assertEqual(blocker.set_family_dns(), 0)
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0][:5], ["netsh", "interface", "ipv4", "set", "dns"])


if __name__ == "__main__":
    unittest.main()
