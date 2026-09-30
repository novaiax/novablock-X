"""A missing policy in any managed browser must trigger repair."""

import unittest
from unittest.mock import patch

from novablock import browser_policies, reddit_filter


def _expected_values():
    values = {}
    for vendor, path in browser_policies.CHROMIUM_VENDOR_PATHS.items():
        values[(path, "DnsOverHttpsMode")] = "off"
        values[(path, "BuiltInDnsClientEnabled")] = 0
        values[(path, "IncognitoModeAvailability")] = 1
        values[(path, "ForceGoogleSafeSearch")] = 1
        if vendor == "Edge":
            values[(path, "InPrivateModeAvailability")] = 1
            values[(path, "ForceBingSafeSearch")] = 2
    firefox = r"SOFTWARE\Policies\Mozilla\Firefox"
    values[(firefox + r"\DNSOverHTTPS", "Enabled")] = 0
    values[(firefox + r"\DNSOverHTTPS", "Locked")] = 1
    values[(firefox, "DisablePrivateBrowsing")] = 1
    return values


class BrowserPolicyCoverageTests(unittest.TestCase):
    def test_all_browser_policies_are_required(self):
        values = _expected_values()
        with patch.object(browser_policies, "_policy_value",
                          side_effect=lambda path, name: values.get((path, name))), \
             patch.object(reddit_filter, "urlblocklist_present", return_value=True):
            self.assertTrue(browser_policies.policies_present())

            brave = browser_policies.CHROMIUM_VENDOR_PATHS["Brave"]
            values[(brave, "DnsOverHttpsMode")] = "automatic"
            self.assertFalse(browser_policies.policies_present())
            values[(brave, "DnsOverHttpsMode")] = "off"

            firefox = r"SOFTWARE\Policies\Mozilla\Firefox"
            values[(firefox + r"\DNSOverHTTPS", "Locked")] = None
            self.assertFalse(browser_policies.policies_present())

    def test_one_missing_reddit_policy_is_not_hidden_by_other_browsers(self):
        values = _expected_values()
        opera = browser_policies.CHROMIUM_VENDOR_PATHS["Opera"]
        with patch.object(browser_policies, "_policy_value",
                          side_effect=lambda path, name: values.get((path, name))), \
             patch.object(reddit_filter, "urlblocklist_present",
                          side_effect=lambda path: path != opera):
            self.assertFalse(browser_policies.policies_present())


if __name__ == "__main__":
    unittest.main()
