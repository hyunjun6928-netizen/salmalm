"""Tests for salmalm.auth — Authentication, JWT, rate limiting."""
from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

_test_dir = tempfile.mkdtemp()
_test_db = Path(_test_dir) / 'auth_test.db'

import salmalm.auth as auth_mod
auth_mod.AUTH_DB = _test_db

from salmalm.auth import (
    AuthManager, RateLimiter, RateLimitExceeded, TokenManager,
    _hash_password, _verify_password
)


class TestPasswordHashing(unittest.TestCase):

    def test_hash_and_verify(self):
        pw_hash, salt = _hash_password('mypassword')
        self.assertTrue(_verify_password('mypassword', pw_hash, salt))

    def test_wrong_password(self):
        pw_hash, salt = _hash_password('correct')
        self.assertFalse(_verify_password('wrong', pw_hash, salt))

    def test_unique_salts(self):
        _, salt1 = _hash_password('pw')
        _, salt2 = _hash_password('pw')
        self.assertNotEqual(salt1, salt2)


class TestTokenManager(unittest.TestCase):

    def setUp(self):
        self.tm = TokenManager(secret=b'test_secret_32bytes_padding_here')

    def test_create_and_verify(self):
        token = self.tm.create({'user': 'alice', 'role': 'admin'})
        payload = self.tm.verify(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload['user'], 'alice')

    def test_expired_token(self):
        token = self.tm.create({'user': 'bob'}, expires_in=-1)
        self.assertIsNone(self.tm.verify(token))

    def test_tampered_token(self):
        token = self.tm.create({'user': 'alice'})
        parts = token.rsplit('.', 1)
        tampered = parts[0] + '.00000000000000000000000000000000'
        self.assertIsNone(self.tm.verify(tampered))

    def test_garbage_token(self):
        self.assertIsNone(self.tm.verify(''))
        self.assertIsNone(self.tm.verify('singlestring'))


class TestRateLimiter(unittest.TestCase):

    def setUp(self):
        self.rl = RateLimiter()

    def test_allows_normal_requests(self):
        for _ in range(5):
            self.assertTrue(self.rl.check('user1', 'anonymous'))

    def test_blocks_excessive_requests(self):
        blocked = False
        for _ in range(20):
            try:
                self.rl.check('flood_user', 'anonymous')
            except RateLimitExceeded:
                blocked = True
                break
        self.assertTrue(blocked, "Should have been rate limited")

    def test_admin_has_higher_limit(self):
        for _ in range(50):
            self.assertTrue(self.rl.check('admin1', 'admin'))

    def test_cleanup(self):
        self.rl.check('old_user', 'user')
        self.rl._buckets['old_user']['last_refill'] = time.time() - 7200
        self.rl.cleanup()
        self.assertNotIn('old_user', self.rl._buckets)


class TestAuthManager(unittest.TestCase):

    def setUp(self):
        if _test_db.exists():
            _test_db.unlink()
        self.am = AuthManager()
        self.am._initialized = False

    def test_default_admin_created(self):
        self.am._ensure_db()
        users = self.am.list_users()
        self.assertGreaterEqual(len(users), 1)
        self.assertEqual(users[0]['username'], 'admin')

    def test_create_user(self):
        self.am._ensure_db()
        user = self.am.create_user('testuser', 'longpassword123', 'user')
        self.assertEqual(user['username'], 'testuser')
        self.assertIn('api_key', user)

    def test_duplicate_user(self):
        self.am._ensure_db()
        self.am.create_user('dup', 'password123', 'user')
        with self.assertRaises(ValueError):
            self.am.create_user('dup', 'password456', 'user')

    def test_short_password(self):
        self.am._ensure_db()
        with self.assertRaises(ValueError):
            self.am.create_user('user2', 'short', 'user')

    def test_api_key_auth(self):
        self.am._ensure_db()
        user = self.am.create_user('apiuser', 'password123', 'user')
        result = self.am.authenticate_api_key(user['api_key'])
        self.assertIsNotNone(result)
        self.assertEqual(result['username'], 'apiuser')

    def test_token_roundtrip(self):
        self.am._ensure_db()
        user = self.am.create_user('tokuser', 'password123', 'user')
        token = self.am.create_token(user)
        verified = self.am.verify_token(token)
        self.assertIsNotNone(verified)
        self.assertEqual(verified['usr'], 'tokuser')

    def test_permissions(self):
        self.assertTrue(self.am.has_permission({'role': 'admin'}, 'exec'))
        self.assertFalse(self.am.has_permission({'role': 'readonly'}, 'exec'))
        self.assertTrue(self.am.has_permission({'role': 'readonly'}, 'chat'))


if __name__ == '__main__':
    unittest.main()
