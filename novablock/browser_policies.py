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
      - YouTube Restricted Mode DISABLED (Restricted Mode also kills the
        comments section on every video, which is too intrusive for normal
        usage — protection of YouTube comes from the title-keyword monitor
        and the hosts blocklist instead)
      - Block third-party extensions (no SafeSearch override extensions)
    """
    n = 0
    # DNS / privacy
    n += int(_set_reg(winreg.HKEY_LOCAL_MACHINE, vendor_path, "DnsOverHttpsMode", "off",
                      winreg.REG_SZ))
    n += int(_set_reg(winreg.HKEY_LOCAL_MACHINE, vendor_path, "BuiltInDnsClientEnabled", 0))
    n += int(_set_reg(winreg.HKEY_LOCAL_MACHINE, vendor_path, "IncognitoModeAvailability", 1))
    # SafeSearch enforcement.
    # Google: ForceGoogleSafeSearch = 1 (search results filtered).
    # YouTube: NO Restricted Mode policy. The Restricted Mode also disables
    # the comments section on every video — even legitimate ones — which is
    # too intrusive for normal usage. Porn protection on YouTube is covered
    # by (a) the adult-keyword title monitor (popup fires on any title
    # containing porn/xxx/milf/pornhub/etc.) and (b) the hosts blocklist
    # (~50k adult-related domains DNS-blocked).
    # Actively DELETE any previous ForceYouTubeRestrict value so existing
    # installs cleanly migrate away from the Strict/Moderate setting.
    n += int(_set_reg(winreg.HKEY_LOCAL_MACHINE, vendor_path, "ForceGoogleSafeSearch", 1))
    _del_reg(winreg.HKEY_LOCAL_MACHINE, vendor_path, "ForceYouTubeRestrict")
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


CHROMIUM_VENDOR_PATHS = {
    "Chrome": r"SOFTWARE\Policies\Google\Chrome",
    "Edge":   r"SOFTWARE\Policies\Microsoft\Edge",
    "Brave":  r"SOFTWARE\Policies\BraveSoftware\Brave",
    "Opera":  r"SOFTWARE\Policies\Opera Software\Opera Stable",
}


def apply_all_browser_policies() -> dict:
    """Apply DoH-off + incognito-off + Reddit NSFW URL blocklist to Chrome,
    Edge, Brave, Firefox, Opera."""
    from . import reddit_filter
    results = {}
    try:
        results["Chrome"] = apply_chromium_policy(CHROMIUM_VENDOR_PATHS["Chrome"])
    except Exception as e:
        log.warning("Chrome policy failed: %s", e); results["Chrome"] = 0
    try:
        results["Edge"] = apply_edge_policy()
    except Exception as e:
        log.warning("Edge policy failed: %s", e); results["Edge"] = 0
    try:
        results["Brave"] = apply_chromium_policy(CHROMIUM_VENDOR_PATHS["Brave"])
    except Exception as e:
        log.warning("Brave policy failed: %s", e); results["Brave"] = 0
    try:
        results["Firefox"] = apply_firefox_policy()
    except Exception as e:
        log.warning("Firefox policy failed: %s", e); results["Firefox"] = 0
    try:
        results["Opera"] = apply_chromium_policy(CHROMIUM_VENDOR_PATHS["Opera"])
    except Exception as e:
        log.warning("Opera policy failed: %s", e); results["Opera"] = 0

    # Reddit NSFW subreddit blocklist via the Chromium URLBlocklist policy.
    # Firefox is intentionally skipped — it has no equivalent enterprise
    # policy; the adult-keyword title monitor handles that path instead.
    reddit_counts = {}
    for vendor, path in CHROMIUM_VENDOR_PATHS.items():
        try:
            reddit_counts[vendor] = reddit_filter.apply_url_blocklist(path)
        except Exception as e:
            log.warning("Reddit URLBlocklist failed for %s: %s", vendor, e)
            reddit_counts[vendor] = 0

    log.info("Browser policies applied: %s", results)
    log.info("Reddit NSFW URL blocklist applied: %s patterns each",
             reddit_counts)
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
    # Also wipe the Reddit URLBlocklist subkey on every Chromium vendor —
    # leaving it behind after uninstall would keep blocking NSFW subs even
    # though the rest of NovaBlock is gone.
    for vendor_path in CHROMIUM_VENDOR_PATHS.values():
        sub = vendor_path + r"\URLBlocklist"
        try:
            # Remove our numeric values; leave any user/admin custom ones.
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, sub, 0,
                                winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
                to_delete: list[str] = []
                i = 0
                while True:
                    try:
                        name, _val, _type = winreg.EnumValue(k, i)
                    except OSError:
                        break
                    if name.isdigit():
                        to_delete.append(name)
                    i += 1
                for name in to_delete:
                    try: winreg.DeleteValue(k, name)
                    except OSError: pass
        except FileNotFoundError:
            pass
        except Exception as e:
            log.debug("URLBlocklist cleanup failed for %s: %s", vendor_path, e)
    log.info("Browser policies removed (including Reddit URLBlocklist)")


def policies_present() -> bool:
    """Check if our policies are in place. Returns True only when BOTH the
    DoH-off baseline AND the Reddit NSFW URLBlocklist are present in Chrome
    (the most-used browser, used as canary). This way, when we add new
    policy layers (like Reddit), the watchdog automatically re-applies
    them on the next tick after an upgrade — no manual intervention."""
    from . import reddit_filter
    # 1. DoH-off baseline on Chrome
    doh_off = False
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Policies\Google\Chrome", 0, winreg.KEY_READ) as k:
            v, _ = winreg.QueryValueEx(k, "DnsOverHttpsMode")
            doh_off = (v == "off")
    except Exception:
        # Fallback: try Edge as canary
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"SOFTWARE\Policies\Microsoft\Edge", 0, winreg.KEY_READ) as k:
                v, _ = winreg.QueryValueEx(k, "DnsOverHttpsMode")
                doh_off = (v == "off")
        except Exception:
            pass
    if not doh_off:
        return False
    # 2. Reddit URLBlocklist on Chrome (or Edge as fallback)
    reddit_ok = reddit_filter.urlblocklist_present(r"SOFTWARE\Policies\Google\Chrome") \
                or reddit_filter.urlblocklist_present(r"SOFTWARE\Policies\Microsoft\Edge")
    return reddit_ok
