"""Safety tests for family-filtering DNS selection and application."""

from novablock import blocker


UNFILTERED_QUAD9 = {
    "9.9.9.10",
    "149.112.112.10",
    "2620:fe::10",
    "2620:fe::fe:10",
}


def test_only_verified_family_providers_are_configured():
    configured = {address for entry in blocker.DNS_FALLBACKS for address in entry[1:]}

    assert configured.isdisjoint(UNFILTERED_QUAD9)
    assert [entry[0] for entry in blocker.DNS_FALLBACKS] == [
        "Cloudflare Family",
        "CleanBrowsing Family",
        "OpenDNS FamilyShield",
    ]
    assert all(entry[3] and entry[4] for entry in blocker.DNS_FALLBACKS)


def test_reachable_family_provider_is_selected_in_order(monkeypatch):
    probes = []

    def reachable(address, timeout):
        probes.append((address, timeout))
        return address == "185.228.168.168"

    monkeypatch.setattr(blocker, "_dns_reachable", reachable)

    selected = blocker.choose_family_dns()

    assert selected[0] == "CleanBrowsing Family"
    assert [address for address, _ in probes] == ["1.1.1.3", "185.228.168.168"]


def test_no_reachable_provider_keeps_filtered_default(monkeypatch):
    monkeypatch.setattr(blocker, "_dns_reachable", lambda *_args, **_kwargs: False)

    assert blocker.choose_family_dns() == blocker.DNS_FALLBACKS[0]


def test_dns_timeout_aborts_without_touching_other_stacks(monkeypatch):
    commands = []
    monkeypatch.setattr(blocker, "choose_family_dns", lambda: blocker.DNS_FALLBACKS[0])
    monkeypatch.setattr(blocker, "list_active_interfaces", lambda: ["Ethernet"])

    def run(command, **_kwargs):
        commands.append(command)
        return 1, "", "timeout"

    monkeypatch.setattr(blocker, "_run", run)

    assert blocker.set_family_dns() == 0
    assert len(commands) == 1
    assert commands[0][:5] == ["netsh", "interface", "ipv4", "set", "dns"]
