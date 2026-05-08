"""Watchdog: keeps the block in place. Periodically:
  - re-applies hosts block if missing
  - re-locks DNS if changed
  - rotates code if 7+ days passed
  - revokes temp-unlock when expired
Designed to be cheap: 1 check per 30 seconds.
"""
import logging
import threading
import time
from typing import Callable, Optional

from . import config, blocker, crypto, mailer, browser_policies, firewall

log = logging.getLogger("novablock.watchdog")


class Watchdog:
    def __init__(self, interval: int = 30,
                 on_rotation: Optional[Callable[[], None]] = None):
        self.interval = interval
        self.on_rotation = on_rotation
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="NovaBlockWatchdog")
        self._thread.start()
        log.info("Watchdog started (interval=%ds)", self.interval)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _tick(self) -> None:
        cfg = config.load()
        if not cfg.get("install_ts"):
            return

        if config.is_temp_unlocked():
            if blocker.hosts_block_present():
                blocker.remove_hosts_block()
                log.info("Temp unlock active — hosts block removed")
        else:
            if not blocker.hosts_block_present():
                log.warning("Hosts block missing — re-applying")
                blocker.apply_full_block(kill_browsers=False)
            elif not blocker.dns_is_locked():
                log.warning("DNS not locked — re-applying")
                blocker.set_family_dns()
            if not browser_policies.policies_present():
                log.warning("Browser policies missing — re-applying")
                browser_policies.apply_all_browser_policies()
            if not firewall.doh_blocked():
                log.warning("DoH firewall rules missing — re-applying")
                firewall.block_doh_endpoints()
            if cfg.get("temp_unlock_until", 0) and cfg["temp_unlock_until"] <= time.time():
                config.revoke_temp_unlock()
                log.info("Temp unlock expired — block restored")

        if config.needs_code_rotation():
            self._rotate_code(cfg)

    def _rotate_code(self, cfg: dict) -> None:
        """Silent rotation — invalidates the existing code so the friend's
        7-day-old code stops working. No email sent. Next 'demander' click
        from Yann will generate a fresh code and email it to the friend."""
        log.info("Silently rotating (invalidating) unlock code")
        # Generate a new random code we'll never reveal — the only effect is
        # that the friend's previous code no longer matches this hash.
        sentinel = crypto.generate_unlock_code()
        config.update_code_hash(crypto.hash_code(sentinel))
        if self.on_rotation:
            try:
                self.on_rotation()
            except Exception:
                pass
        log.info("Code invalidated. Next unlock request will email a fresh code.")

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as e:
                log.exception("watchdog tick error: %s", e)
            self._stop.wait(self.interval)
