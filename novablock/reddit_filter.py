"""Surgical Reddit filter: blocks NSFW subreddits via Chromium URLBlocklist.

Problem: Reddit doesn't expose any DNS-level safe mode (unlike Google or
YouTube). Blocking reddit.com entirely would kill regular use — posting,
commenting, non-NSFW subs. We need a way to keep all of that working while
preventing the user from reaching the porn side of the site.

Approach: Chromium browsers (Chrome, Edge, Brave, Opera, Vivaldi) honor the
URLBlocklist enterprise policy in HKLM\\Software\\Policies\\<vendor>\\<browser>\\URLBlocklist.
Each pattern is a numbered REG_SZ value (\"1\", \"2\", ...). When the user
navigates to a blocked URL, the browser shows its own \"This site is blocked
by your administrator\" page. No popup, no detour through NovaBlock — Chrome
just refuses to load.

The patterns block specifically `https://<host>/r/<subname>` and
`https://<host>/r/<subname>/*` for every host Reddit serves the same
content under (www, old, new, m, sh, np). Posting interface
(/submit), profile (/user/<u>), inbox (/message), and every non-NSFW
subreddit remain reachable.

Firefox is NOT covered: it has no equivalent enterprise URL blocklist
policy that ships out of the box. The adult-keyword title monitor in
monitor.py still catches obvious cases there (titles containing 'NSFW',
'porn', etc.).

Maintenance: NSFW_SUBREDDITS is a curated seed list of the most popular
adult subs. New subs that emerge can be added here. The blocklist is
versioned with the binary so updates ship via the normal release flow.
"""
import logging

log = logging.getLogger("novablock.reddit")


# Two patterns cover every Reddit subdomain. Chromium URLBlocklist supports
# wildcard subdomains via `*.host` (matches any subdomain) but doesn't
# match the bare apex domain — so we need both `reddit.com` and
# `*.reddit.com`. Together they cover www / old / new / m / sh / np /
# whatever-Reddit-launches-next.
REDDIT_HOSTS = [
    "reddit.com",
    "*.reddit.com",
]


# Curated list of NSFW subreddits — the most-trafficked ones plus the
# obvious adult-keyword names. Sorted alphabetically for easy maintenance.
# Add to this list as new ones surface; do not remove entries lightly.
NSFW_SUBREDDITS = [
    # General NSFW catch-alls
    "nsfw", "nsfw_gif", "nsfw_gifs", "nsfw_amateurs", "nsfw411",
    "porn", "porninfifteenseconds", "porninaminute", "pornvids",
    "60fpsporn", "highresnsfw", "hardcore", "softcore",
    "rule34", "rule34lol", "rule34_comics",
    "freeuse", "tinytits", "biggerthanyouthought",

    # GoneWild family (amateur-posted nudes)
    "gonewild", "gonewildplus", "gonewildcurvy", "gonewildtube",
    "gonewildaudio", "gonewildstories", "gonewild30plus",
    "petitegonewild", "asiansgonewild", "latinagonewild",
    "altgonewild", "ebonygonewild", "indiangw", "irlgonewild",
    "midgetgonewild", "milfgonewild", "uniformporn",
    "treesgonewild", "gymgonewild",

    # Body part / category subs
    "ass", "asstastic", "facedownassup", "buttsharpies",
    "boobs", "tits", "boobies", "boobbounce", "burstingout",
    "thick", "thicc", "thicker", "pawg",
    "milf", "milfs", "mature", "gilf",
    "asianhotties", "asiansgw", "asianporn",
    "ebony", "ebonyteens",
    "redheads", "blondes", "brunettes",
    "freckles", "tattoos_nsfw", "altgw",

    # Activity / fetish
    "anal", "analgw", "buttplug", "anal_gifs",
    "blowjobs", "blowjobsandwich", "cumsluts", "cumshots",
    "creampie", "creampies", "facials_official",
    "doublepenetration", "threesome", "groupsex",
    "bdsm", "kink", "kinky", "fetish", "femdom",
    "spanking", "bondage", "rough_sex",
    "publicflashing", "publicsex", "exhibitionism",

    # Hentai / drawn
    "hentai", "rule34hentai", "hentaiporn",
    "ecchi", "anime_titties", "thick_hentai",

    # LGBT NSFW
    "gaybrosgonewild", "gaysex", "gaybears",
    "girlsfinishingthejob", "lesbians", "lesbianpornhd",
    "transporn", "tgirls", "trapsgonewild",

    # Couples / amateurs
    "couplesgonewild", "amateur", "amateurcumsluts", "realamateurs",
    "homemade", "homemadexxx", "amateurfetish",

    # Dating / contact subs (where porn typically gets traded)
    "dirtyr4r", "r4r", "gonewildchat", "sext", "sextingtok",
    "nsfwsnap", "snapleaks", "snapchatsex",

    # Cosplay / fitness NSFW spinoffs
    "nsfwcosplay", "cosplayporn", "cosplaybutts",
    "fitgirls", "fitness_nsfw",

    # OnlyFans / leak-aggregation
    "onlyfans", "onlyfansgirls101", "onlyfansadvice",
    "fansly", "leakedmodels", "fansonly",
]


def _safe_set_reg_string(path: str, name: str, value: str) -> bool:
    """Best-effort REG_SZ write. Returns True on success, False otherwise."""
    try:
        import winreg
        winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, path)
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
        return True
    except Exception as e:
        log.debug("reg write failed [%s\\%s]: %s", path, name, e)
        return False


def _clear_urlblocklist_subkey(parent_path: str) -> None:
    """Delete every existing value under <parent>\\URLBlocklist so we don't
    leave stale entries when the curated list shrinks. Keeps any non-numeric
    custom entries the user / admin added manually."""
    try:
        import winreg
        sub = parent_path + r"\URLBlocklist"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, sub, 0,
                            winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
            to_delete: list[str] = []
            i = 0
            while True:
                try:
                    name, _val, _type = winreg.EnumValue(k, i)
                except OSError:
                    break
                # Only nuke purely-numeric value names — those are the ones
                # we write. A user / admin custom value with a name like
                # "MyCustomBlock" stays put.
                if name.isdigit():
                    to_delete.append(name)
                i += 1
            for name in to_delete:
                try:
                    winreg.DeleteValue(k, name)
                except OSError:
                    pass
    except FileNotFoundError:
        # Subkey doesn't exist yet — nothing to clear
        pass
    except Exception as e:
        log.debug("URLBlocklist clear failed for %s: %s", parent_path, e)


def build_url_blocklist() -> list[str]:
    """Cartesian product: every (host, sub) pair, one pattern each.

    Chromium URLBlocklist semantics: the path `/r/sub` matches `/r/sub` AND
    `/r/sub/anything`, so no separate `/*` pattern is needed. With 2 host
    patterns × N subs, the list stays well under Chrome's documented
    1000-entry URLBlocklist cap even with many subs.
    """
    patterns: list[str] = []
    for sub in NSFW_SUBREDDITS:
        for host in REDDIT_HOSTS:
            patterns.append(f"https://{host}/r/{sub}")
    return patterns


def apply_url_blocklist(vendor_path: str) -> int:
    """Write the NSFW blocklist into <vendor_path>\\URLBlocklist as numbered
    REG_SZ values. Returns the number of patterns successfully written.

    vendor_path examples:
        SOFTWARE\\Policies\\Google\\Chrome
        SOFTWARE\\Policies\\Microsoft\\Edge
        SOFTWARE\\Policies\\BraveSoftware\\Brave
    """
    _clear_urlblocklist_subkey(vendor_path)
    sub = vendor_path + r"\URLBlocklist"
    patterns = build_url_blocklist()
    n = 0
    for idx, pattern in enumerate(patterns, start=1):
        if _safe_set_reg_string(sub, str(idx), pattern):
            n += 1
    return n


def urlblocklist_present(vendor_path: str) -> bool:
    """Cheap presence check used by the watchdog: do we already have at
    least the first pattern in the blocklist? If yes, we assume the rest
    is in place too (apply_url_blocklist writes them contiguously)."""
    try:
        import winreg
        sub = vendor_path + r"\URLBlocklist"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, sub, 0, winreg.KEY_READ) as k:
            val, _ = winreg.QueryValueEx(k, "1")
            # If something else owns the "1" slot, it's not ours.
            return isinstance(val, str) and val.startswith("https://") and "/r/" in val
    except (FileNotFoundError, OSError):
        return False
    except Exception:
        return False
