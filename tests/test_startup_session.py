"""Regression tests for Windows-session-aware NovaBlock startup."""

import sys

from novablock import main as app_main


def _quiet_logging(monkeypatch) -> None:
    monkeypatch.setattr(app_main, "setup_logging", lambda: None)


def test_legacy_service_mode_only_runs_headless_repair(monkeypatch):
    calls = []
    _quiet_logging(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["NovaBlock.exe", "--service-run"])
    monkeypatch.setattr(app_main, "is_admin", lambda: True)
    monkeypatch.setattr(app_main, "run_watchdog_headless", lambda: calls.append("headless"))
    monkeypatch.setattr(
        app_main,
        "current_session_id",
        lambda: (_ for _ in ()).throw(AssertionError("session lookup must not run")),
    )

    assert app_main.main() == 0
    assert calls == ["headless"]


def test_plain_launch_in_session_zero_never_starts_ui(monkeypatch):
    calls = []
    _quiet_logging(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["NovaBlock.exe"])
    monkeypatch.setattr(app_main, "current_session_id", lambda: 0)
    monkeypatch.setattr(app_main, "is_admin", lambda: True)
    monkeypatch.setattr(app_main, "run_watchdog_headless", lambda: calls.append("headless"))
    monkeypatch.setattr(app_main, "run_app", lambda: calls.append("ui"))

    assert app_main.main() == 0
    assert calls == ["headless"]


def test_plain_launch_in_interactive_session_starts_ui(monkeypatch):
    calls = []
    _quiet_logging(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["NovaBlock.exe"])
    monkeypatch.setattr(app_main, "current_session_id", lambda: 1)
    monkeypatch.setattr(app_main, "is_admin", lambda: True)
    monkeypatch.setattr(app_main.config, "is_installed", lambda: True)
    monkeypatch.setattr(app_main.recovery, "shutdown_requested", lambda: False)
    monkeypatch.setattr(app_main.single_instance, "acquire", lambda: True)
    monkeypatch.setattr(app_main.single_instance, "release", lambda: calls.append("release"))
    monkeypatch.setattr(app_main, "run_app", lambda: calls.append("ui"))

    assert app_main.main() == 0
    assert calls == ["ui", "release"]
