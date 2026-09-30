"""Clock changes on the PC must not shorten cooldowns or extend unlocks."""

from email.utils import parsedate_to_datetime
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from novablock import config, trusted_clock


class TrustedClockTests(unittest.TestCase):
    def test_https_sample_advances_with_monotonic_not_system_clock(self):
        first = "Wed, 30 Sep 2026 15:00:00 GMT"
        second = "Wed, 30 Sep 2026 15:00:01 GMT"
        epoch = parsedate_to_datetime(first).timestamp()
        replies = [SimpleNamespace(status_code=200, headers={"Date": first}),
                   SimpleNamespace(status_code=200, headers={"Date": second})]
        with patch.object(trusted_clock, "_sample_epoch", 0.0), \
             patch.object(trusted_clock, "_sample_monotonic", 0.0), \
             patch.object(trusted_clock, "_sample_wall", 0.0), \
             patch.object(trusted_clock.requests, "head", side_effect=replies) as head, \
             patch.object(trusted_clock.time, "monotonic", return_value=100.0) as mono, \
             patch.object(trusted_clock.time, "time", return_value=epoch + 100) as wall:
            self.assertEqual(trusted_clock.verified_now(), epoch)
            self.assertEqual(head.call_count, 2)
            mono.return_value = 160.0
            wall.return_value = epoch + 160
            self.assertEqual(trusted_clock.cached_now(), epoch + 60)
            wall.return_value = epoch + 500000
            self.assertIsNone(trusted_clock.cached_now())

    def test_conflicting_https_sources_fail_closed(self):
        replies = [SimpleNamespace(status_code=200, headers={"Date": "Wed, 30 Sep 2026 15:00:00 GMT"}),
                   SimpleNamespace(status_code=200, headers={"Date": "Wed, 30 Sep 2026 15:10:00 GMT"})]
        with patch.object(trusted_clock, "_sample_epoch", 0.0), \
             patch.object(trusted_clock.requests, "head", side_effect=replies):
            with self.assertRaises(trusted_clock.ClockUnavailable):
                trusted_clock.verified_now()

    def test_seven_day_code_and_uninstall_gates_ignore_local_clock(self):
        day = 24 * 3600
        now = 1_800_000_000.0
        cfg = {"install_ts": now - 20 * day, "code_hash": "stored",
               "code_rotation_ts": now - 8 * day,
               "uninstall_initiated_at": now - 6 * day}
        with patch.object(config, "load", return_value=cfg), \
             patch.object(config.trusted_clock, "verified_now", return_value=now), \
             patch.object(config.trusted_clock, "cached_now", return_value=now), \
             patch.object(config, "_verify_hash", return_value=True) as verify, \
             patch.object(config.time, "time", return_value=now + 100 * day):
            self.assertFalse(config.verify_current_code("correct", cfg))
            verify.assert_not_called()
            self.assertEqual(config.uninstall_cooldown_remaining(verified=True), day)
            cfg["code_rotation_ts"] = now - day
            self.assertTrue(config.verify_current_code("correct", cfg))
            cfg["temp_unlock_until"] = now + 3600
            self.assertTrue(config.is_temp_unlocked())
            cfg["temp_unlock_until"] = now + 25 * 3600
            self.assertFalse(config.is_temp_unlocked())


if __name__ == "__main__":
    unittest.main()
