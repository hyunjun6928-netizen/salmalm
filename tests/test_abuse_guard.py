"""Tests for API Abuse Guard: LLMRateLimiter, IPBanList (SQLite), DailyQuotaManager.

Covers:
- LLMRateLimiter: tighter buckets, per-role limits
- IPBanList: violation tracking, auto-ban, manual unban, SQLite persistence
- DailyQuotaManager: quota check, add_usage, get_usage, role limits, env override
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


class TestLLMRateLimiter(unittest.TestCase):
    """LLMRateLimiter — tighter token bucket for LLM paths."""

    def setUp(self):
        from salmalm.web.auth import LLMRateLimiter
        self.limiter = LLMRateLimiter()

    def test_llm_limits_tighter_than_global(self):
        """LLM limits must be lower than global RateLimiter limits."""
        from salmalm.web.auth import RateLimiter
        global_lim = RateLimiter()
        # user: LLM 10/min vs global 30/min
        self.assertLess(
            self.limiter._limits["user"]["rate"],
            global_lim._limits["user"]["rate"],
        )
        # anonymous: LLM 2/min vs global 5/min
        self.assertLess(
            self.limiter._limits["anonymous"]["rate"],
            global_lim._limits["anonymous"]["rate"],
        )

    def test_admin_unlimited_relative(self):
        """Admin should have the highest LLM limit."""
        limits = self.limiter._limits
        self.assertGreater(limits["admin"]["rate"], limits["user"]["rate"])
        self.assertGreater(limits["user"]["rate"], limits["anonymous"]["rate"])

    def test_anon_exhausts_quickly(self):
        """Anonymous bucket exhausts after burst limit."""
        from salmalm.web.auth import RateLimitExceeded
        burst = self.limiter._limits["anonymous"]["burst"]
        # Drain the burst
        for _ in range(burst):
            self.limiter.check("anon_test_key", "anonymous")
        # Next call must raise
        with self.assertRaises(RateLimitExceeded):
            self.limiter.check("anon_test_key", "anonymous")

    def test_separate_keys_independent(self):
        """Different keys should not share buckets."""
        from salmalm.web.auth import RateLimitExceeded
        burst = self.limiter._limits["anonymous"]["burst"]
        for _ in range(burst):
            self.limiter.check("user_A", "anonymous")
        with self.assertRaises(RateLimitExceeded):
            self.limiter.check("user_A", "anonymous")
        # user_B should still have full bucket
        self.assertTrue(self.limiter.check("user_B", "anonymous"))

    def test_get_remaining_decrements(self):
        """get_remaining() should decrease with each check."""
        key = "remaining_test"
        self.limiter.check(key, "user")
        remaining = self.limiter.get_remaining(key)
        self.limiter.check(key, "user")
        self.assertLessEqual(self.limiter.get_remaining(key), remaining)


class TestIPBanList(unittest.TestCase):
    """IPBanList — auto-ban + SQLite persistence."""

    def setUp(self):
        """Use a temporary DB for each test."""
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = Path(self.tmpdir) / "auth.db"
        # Patch AUTH_DB to our temp path
        import salmalm.web.auth as auth_mod
        self._orig_auth_db = auth_mod.AUTH_DB
        auth_mod.AUTH_DB = self.db_path
        from salmalm.web.auth import IPBanList
        self.ban_list = IPBanList(ban_threshold=3, ban_duration=60)

    def tearDown(self):
        import salmalm.web.auth as auth_mod
        auth_mod.AUTH_DB = self._orig_auth_db

    def test_not_banned_initially(self):
        is_banned, _ = self.ban_list.is_banned("1.2.3.4")
        self.assertFalse(is_banned)

    def test_auto_ban_after_threshold(self):
        """IP should be banned after ban_threshold violations."""
        for _ in range(2):
            result = self.ban_list.record_violation("1.2.3.4")
            self.assertFalse(result)
        # 3rd violation hits threshold=3
        result = self.ban_list.record_violation("1.2.3.4")
        self.assertTrue(result)
        is_banned, remaining = self.ban_list.is_banned("1.2.3.4")
        self.assertTrue(is_banned)
        self.assertGreater(remaining, 0)
        self.assertLessEqual(remaining, 60)

    def test_already_banned_returns_true(self):
        """record_violation on already-banned IP returns True immediately."""
        for _ in range(3):
            self.ban_list.record_violation("5.5.5.5")
        result = self.ban_list.record_violation("5.5.5.5")
        self.assertTrue(result)

    def test_manual_unban(self):
        """unban() clears ban in memory and DB."""
        for _ in range(3):
            self.ban_list.record_violation("9.9.9.9")
        self.assertTrue(self.ban_list.is_banned("9.9.9.9")[0])
        self.ban_list.unban("9.9.9.9")
        self.assertFalse(self.ban_list.is_banned("9.9.9.9")[0])

    def test_list_banned(self):
        """list_banned() returns only currently active bans."""
        for _ in range(3):
            self.ban_list.record_violation("10.0.0.1")
        bans = self.ban_list.list_banned()
        self.assertEqual(len(bans), 1)
        self.assertEqual(bans[0]["ip"], "10.0.0.1")
        self.assertIn("remaining", bans[0])

    def test_sqlite_persistence(self):
        """Bans survive creating a new IPBanList instance from same DB."""
        for _ in range(3):
            self.ban_list.record_violation("persist.test")

        # Create a fresh instance — should load ban from DB
        import salmalm.web.auth as auth_mod
        from salmalm.web.auth import IPBanList
        new_ban_list = IPBanList(ban_threshold=3, ban_duration=60)
        is_banned, remaining = new_ban_list.is_banned("persist.test")
        self.assertTrue(is_banned, "Ban should be loaded from SQLite on startup")
        self.assertGreater(remaining, 0)

    def test_unban_removes_from_db(self):
        """unban() removes record from SQLite."""
        for _ in range(3):
            self.ban_list.record_violation("clean.me")
        self.ban_list.unban("clean.me")

        # Verify DB is clean
        conn = sqlite3.connect(str(self.db_path))
        row = conn.execute(
            "SELECT banned_until FROM ip_bans WHERE ip=?", ("clean.me",)
        ).fetchone()
        conn.close()
        self.assertIsNone(row)

    def test_cleanup_removes_expired(self):
        """cleanup() removes stale in-memory records."""
        # Manually inject an expired record
        self.ban_list._records["old.ip"] = {
            "count": 3,
            "first_at": time.time() - 10000,
            "last_at": time.time() - 10000,
            "banned_until": time.time() - 5000,  # expired
        }
        self.ban_list.cleanup()
        self.assertNotIn("old.ip", self.ban_list._records)

    def test_sliding_window_uses_last_at(self):
        """Window reset must be based on last violation time, not first.

        P0 security fix: an attacker who violates (threshold-1) times, waits 1 h,
        then repeats must eventually be banned — not loop forever.
        The old code reset on 'first_at' which allowed exactly that bypass.
        """
        ip = "bypass.attacker"
        threshold = self.ban_list._ban_threshold  # 3

        # Inject a record that looks 1h old based on first_at but has
        # a recent last_at — window should NOT reset.
        now = time.time()
        self.ban_list._records[ip] = {
            "count": threshold - 1,          # one away from ban
            "first_at": now - 7200,          # 2h ago — OLD first_at
            "last_at":  now - 10,            # 10 s ago — RECENT last violation
            "banned_until": 0.0,
        }
        # Next violation: last_at is recent, so window must NOT reset
        result = self.ban_list.record_violation(ip)
        self.assertTrue(result, "Should be banned — last violation was only 10 s ago")

    def test_sliding_window_resets_after_idle(self):
        """Window resets after 1 h of *no* violations (last_at is stale)."""
        ip = "idle.attacker"
        threshold = self.ban_list._ban_threshold  # 3
        now = time.time()
        # Record was last violated 2h ago — window should reset
        self.ban_list._records[ip] = {
            "count": threshold - 1,    # one away from ban
            "first_at": now - 7200,
            "last_at":  now - 7200,    # 2h idle → reset expected
            "banned_until": 0.0,
        }
        result = self.ban_list.record_violation(ip)
        self.assertFalse(result, "Count reset after idle — should not be banned yet")
        self.assertEqual(self.ban_list._records[ip]["count"], 1)

    def test_unban_clears_record_entirely(self):
        """unban() must remove the record from _records, not just zero fields."""
        for _ in range(3):
            self.ban_list.record_violation("nuke.me")
        self.assertTrue(self.ban_list.is_banned("nuke.me")[0])
        self.ban_list.unban("nuke.me")
        # Record must be gone — not left with count=0, banned_until=0
        self.assertNotIn("nuke.me", self.ban_list._records,
                         "unban() must delete record, not zero it in place")


class TestDailyQuotaManager(unittest.TestCase):
    """DailyQuotaManager — per-user daily token limits."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = Path(self.tmpdir) / "auth.db"
        import salmalm.web.auth as auth_mod
        self._orig_auth_db = auth_mod.AUTH_DB
        auth_mod.AUTH_DB = self.db_path
        from salmalm.web.auth import DailyQuotaManager
        self.quota = DailyQuotaManager()

    def tearDown(self):
        import salmalm.web.auth as auth_mod
        auth_mod.AUTH_DB = self._orig_auth_db

    def test_initial_usage_zero(self):
        self.assertEqual(self.quota.get_usage("new_user"), 0)

    def test_add_usage_increments(self):
        self.quota.add_usage("u1", 1000)
        self.assertEqual(self.quota.get_usage("u1"), 1000)
        self.quota.add_usage("u1", 500)
        self.assertEqual(self.quota.get_usage("u1"), 1500)

    def test_check_passes_under_limit(self):
        """check() should not raise when under limit."""
        self.quota.add_usage("u2", 100)
        # Should not raise
        self.quota.check("u2", "user")

    def test_check_raises_over_limit(self):
        """check() raises DailyQuotaExceeded when at/over limit."""
        from salmalm.web.auth import DailyQuotaExceeded
        limit = self.quota.limit_for("anonymous")
        self.quota.add_usage("anon1", limit)
        with self.assertRaises(DailyQuotaExceeded) as ctx:
            self.quota.check("anon1", "anonymous")
        self.assertEqual(ctx.exception.used, limit)
        self.assertEqual(ctx.exception.limit, limit)

    def test_admin_unlimited(self):
        """Admin role should never be blocked regardless of usage."""
        self.quota.add_usage("admin1", 10_000_000)
        # Should not raise
        self.quota.check("admin1", "admin")
        self.assertEqual(self.quota.limit_for("admin"), -1)

    def test_role_limits_hierarchy(self):
        """admin > user > readonly > anonymous in terms of limit."""
        limits = {
            role: self.quota.limit_for(role)
            for role in ("admin", "user", "readonly", "anonymous")
        }
        # admin unlimited
        self.assertEqual(limits["admin"], -1)
        # user > readonly > anonymous
        self.assertGreater(limits["user"], limits["readonly"])
        self.assertGreater(limits["readonly"], limits["anonymous"])

    def test_env_override_user(self):
        """SALMALM_DAILY_QUOTA_USER env var overrides user limit."""
        from salmalm.web.auth import DailyQuotaManager
        with patch.dict(os.environ, {"SALMALM_DAILY_QUOTA_USER": "12345"}):
            q = DailyQuotaManager()
            self.assertEqual(q.limit_for("user"), 12345)

    def test_env_override_anon(self):
        """SALMALM_DAILY_QUOTA_ANON env var overrides anon limit."""
        from salmalm.web.auth import DailyQuotaManager
        with patch.dict(os.environ, {"SALMALM_DAILY_QUOTA_ANON": "999"}):
            q = DailyQuotaManager()
            self.assertEqual(q.limit_for("anonymous"), 999)

    def test_separate_users_independent(self):
        """Different users have independent quotas."""
        self.quota.add_usage("alice", 1000)
        self.quota.add_usage("bob", 2000)
        self.assertEqual(self.quota.get_usage("alice"), 1000)
        self.assertEqual(self.quota.get_usage("bob"), 2000)

    def test_get_all_today(self):
        """get_all_today() returns all users' usage sorted by tokens."""
        self.quota.add_usage("heavy_user", 9000)
        self.quota.add_usage("light_user", 100)
        all_usage = self.quota.get_all_today()
        self.assertGreaterEqual(len(all_usage), 2)
        # Sorted descending
        tokens = [u["tokens"] for u in all_usage]
        self.assertEqual(tokens, sorted(tokens, reverse=True))

    def test_sqlite_persistence(self):
        """Usage persists across DailyQuotaManager instances."""
        self.quota.add_usage("persist_user", 5000)
        from salmalm.web.auth import DailyQuotaManager
        new_quota = DailyQuotaManager()
        self.assertEqual(new_quota.get_usage("persist_user"), 5000)

    def test_daily_quota_exceeded_message(self):
        """DailyQuotaExceeded carries used/limit attributes."""
        from salmalm.web.auth import DailyQuotaExceeded
        exc = DailyQuotaExceeded(used=50001, limit=50000)
        self.assertEqual(exc.used, 50001)
        self.assertEqual(exc.limit, 50000)
        self.assertIn("50001", str(exc))

    def test_zero_tokens_no_op(self):
        """add_usage(0) should not increment counter."""
        self.quota.add_usage("zero_user", 0)
        self.assertEqual(self.quota.get_usage("zero_user"), 0)


class TestAboveGuardIntegration(unittest.TestCase):
    """Integration: rate_limit_exceeded increments ban violations."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = Path(self.tmpdir) / "auth.db"
        import salmalm.web.auth as auth_mod
        self._orig_auth_db = auth_mod.AUTH_DB
        auth_mod.AUTH_DB = self.db_path

    def tearDown(self):
        import salmalm.web.auth as auth_mod
        auth_mod.AUTH_DB = self._orig_auth_db

    def test_rate_limit_exceeded_exception_attributes(self):
        """RateLimitExceeded carries retry_after attribute."""
        from salmalm.web.auth import RateLimitExceeded
        exc = RateLimitExceeded(retry_after=30.5)
        self.assertAlmostEqual(exc.retry_after, 30.5)
        self.assertIn("30", str(exc))

    def test_ip_and_quota_independent(self):
        """IP bans and daily quota operate independently."""
        from salmalm.web.auth import IPBanList, DailyQuotaManager, DailyQuotaExceeded
        ban = IPBanList(ban_threshold=3, ban_duration=60)
        quota = DailyQuotaManager()

        # Exhaust quota for anon_ip
        limit = quota.limit_for("anonymous")
        quota.add_usage("ip:192.168.1.1", limit)

        # IP not banned
        self.assertFalse(ban.is_banned("192.168.1.1")[0])

        # Quota exceeded
        with self.assertRaises(DailyQuotaExceeded):
            quota.check("ip:192.168.1.1", "anonymous")

        # Record violations — separate from quota
        for _ in range(3):
            ban.record_violation("192.168.1.1")
        self.assertTrue(ban.is_banned("192.168.1.1")[0])


if __name__ == "__main__":
    unittest.main()
