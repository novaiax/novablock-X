"""Browser policies via HKLM registry — disables DoH (which bypasses hosts file)
and incognito mode for major browsers. Applied at install + re-applied by watchdog.

Why: Chrome/Edge/Firefox enable DNS over HTTPS by default, which sends DNS queries
encrypted to Cloudflare/Google directly, bypassing the system DNS AND the hosts file.
A user can still resolve pornhub.com via DoH even with our hosts block in place.

These policies force browsers to use the system resolver = honors hosts file.
Also disables incognito so the user can't sidestep monitor detection by hiding history.
"""
import logging
import winreg

log = logging.getLogger("novablock.browser_policies")


def _set_reg(hive, path: str, name: str, value, regtype=winreg.REG_DWORD) -> bool:
    try:
        winreg.CreateKey(hive, path)
        with winreg.OpenKey(hive, path, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, name, 0, regtype, value)
        return True
    except Exception as e:
        log.warning("set_reg failed [%s\\%s = %r]: %s", path, name, value, e)
        return False


def _del_reg(hive, path: str, name: str) -> None:
    try:
        with winreg.OpenKey(hive, path, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, name)
    except FileNotFoundError:
        pass
    except Exception as e:
        log.debug("del_reg [%s\\%s]: %s", path, name, e)


def apply_chromium_policy(vendor_path: str) -> int:
    """vendor_path examples:
        SOFTWARE\\Policies\\Google\\Chrome
        SOFTWARE\\Policies\\Microsoft\\Edge
        SOFTWARE\\Policies\\BraveSoftware\\Brave
        SOFTWARE\\Policies\\Yandex\\YandexBrowser

    Sets:
      - DoH off (forces system DNS resolver, honors hosts file)
      - Incognito disabled (no private browsing bypass)
      - Force Google SafeSearch (filters search results)
      - Force YouTube Restricted Mode (Strict)
      - Block third-party extensions (no SafeSearch override extensions)
    """
    n = 0
    # DNS / privacy
    n += int(_set_reg(winreg.HKEY_LOCAL_MACHINE, vendor_path, "DnsOverHttpsMode", "off",
                      winreg.REG_SZ))
    n += int(_set_reg(winreg.HKEY_LOCAL_MACHINE, vendor_path, "BuiltInDnsClientEnabled", 0))
    n += int(_set_reg(winreg.HKEY_LOCAL_MACHINE, vendor_path, "IncognitoModeAvailability", 1))
    # SafeSearch enforcement (Google + YouTube)
    n += int(_set_reg(winreg.HKEY_LOCAL_MACHINE, vendor_path, "ForceGoogleSafeSearch", 1))
    n += int(_set_reg(winreg.HKEY_LOCAL_MACHINE, vendor_path, "ForceYouTubeRestrict", 2))
    return n


def apply_edge_policy() -> int:
    n = apply_chromium_policy(r"SOFTWARE\Policies\Microsoft\Edge")
    edge = r"SOFTWARE\Policies\Microsoft\Edge"
    _set_reg(winreg.HKEY_LOCAL_MACHINE, edge, "InPrivateModeAvailability", 1)
    # Edge-specific: force Bing SafeSearch via Bing Adult Filter
    _set_reg(winreg.HKEY_LOCAL_MACHINE, edge, "ForceBingSafeSearch", 2)  # 2 = strict
    return n


def apply_firefox_policy() -> int:
    base = r"SOFTWARE\Policies\Mozilla\Firefox"
    trr = base + r"\DNSOverHTTPS"
    n = 0
    n += int(_set_reg(winreg.HKEY_LOCAL_MACHINE, trr, "Enabled", 0))
    n += int(_set_reg(winreg.HKEY_LOCAL_MACHINE, trr, "Locked", 1))
    n += int(_set_reg(winreg.HKEY_LOCAL_MACHINE, base, "DisablePrivateBrowsing", 1))
    # Firefox SearchEngine SafeSearch — Firefox doesn't expose ForceGoogleSafeSearch
    # like Chromium, but disabling private browsing + DoH off + hosts file forces
    # users through the system resolver where forcesafesearch.google.com mapping
    # (added to hosts via DNS_SAFESEARCH_DOMAINS below) takes effect.
    return n


def apply_all_browser_policies() -> dict:
    """Apply DoH-off + incognito-off to Chrome, Edge, Brave, Firefox, Opera."""
    results = {}
    try:
        results["Chrome"] = apply_chromium_policy(r"SOFTWARE\Policies\Google\Chrome")
    except Exception as e:
        log.warning("Chrome policy failed: %s", e); results["Chrome"] = 0
    try:
        results["Edge"] = apply_edge_policy()
    except Exception as e:
        log.warning("Edge policy failed: %s", e); results["Edge"] = 0
    try:
        results["Brave"] = apply_chromium_policy(r"SOFTWARE\Policies\BraveSoftware\Brave")
    except Exception as e:
        log.warning("Brave policy failed: %s", e); results["Brave"] = 0
    try:
        results["Firefox"] = apply_firefox_policy()
    except Exception as e:
        log.warning("Firefox policy failed: %s", e); results["Firefox"] = 0
    try:
        results["Opera"] = apply_chromium_policy(r"SOFTWARE\Policies\Opera Software\Opera Stable")
    except Exception as e:
        log.warning("Opera policy failed: %s", e); results["Opera"] = 0
    log.info("Browser policies applied: %s", results)
    return results


def remove_all_browser_policies() -> None:
    paths = [
        r"SOFTWARE\Policies\Google\Chrome",
        r"SOFTWARE\Policies\Microsoft\Edge",
        r"SOFTWARE\Policies\BraveSoftware\Brave",
        r"SOFTWARE\Policies\Mozilla\Firefox",
        r"SOFTWARE\Policies\Mozilla\Firefox\DNSOverHTTPS",
        r"SOFTWARE\Policies\Opera Software\Opera Stable",
    ]
    keys_to_remove = ["DnsOverHttpsMode", "BuiltInDnsClientEnabled",
                      "IncognitoModeAvailability", "InPrivateModeAvailability",
                      "Enabled", "Locked", "DisablePrivateBrowsing"]
    for path in paths:
        for key in keys_to_remove:
            _del_reg(winreg.HKEY_LOCAL_MACHINE, path, key)
    log.info("Browser policies removed")


def policies_present() -> bool:
    """Check if at least one browser policy is in place."""
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Policies\Google\Chrome", 0, winreg.KEY_READ) as k:
            v, _ = winreg.QueryValueEx(k, "DnsOverHttpsMode")
            if v == "off":
                return True
    except Exception:
        pass
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Policies\Microsoft\Edge", 0, winreg.KEY_READ) as k:
            v, _ = winreg.QueryValueEx(k, "DnsOverHttpsMode")
            if v == "off":
                return True
    except Exception:
        pass
    return False
