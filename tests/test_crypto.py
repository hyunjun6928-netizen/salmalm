"""Tests for salmalm.crypto — Vault encryption/decryption."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

import salmalm.constants as constants
from salmalm.crypto import Vault, _derive_key

_test_dir = tempfile.mkdtemp()
_test_vault = Path(_test_dir) / '.vault_crypto_test.enc'


class TestVault(unittest.TestCase):

    def setUp(self):
        if _test_vault.exists():
            _test_vault.unlink()
        # Patch both constants AND crypto module references
        import salmalm.crypto as crypto_mod
        self._orig_const = constants.VAULT_FILE
        self._orig_crypto = crypto_mod.VAULT_FILE
        constants.VAULT_FILE = _test_vault
        crypto_mod.VAULT_FILE = _test_vault
        self.vault = Vault()

    def tearDown(self):
        import salmalm.crypto as crypto_mod
        constants.VAULT_FILE = self._orig_const
        crypto_mod.VAULT_FILE = self._orig_crypto

    def test_create_and_unlock(self):
        self.vault.create('test_password_123')
        self.assertTrue(self.vault.is_unlocked)
        self.assertTrue(_test_vault.exists())
        v2 = Vault()
        self.assertFalse(v2.is_unlocked)
        self.assertTrue(v2.unlock('test_password_123'))
        self.assertTrue(v2.is_unlocked)

    def test_wrong_password(self):
        self.vault.create('correct_pw')
        v2 = Vault()
        self.assertFalse(v2.unlock('wrong_pw'))

    def test_get_set_delete(self):
        self.vault.create('pw123')
        self.vault.set('api_key', 'sk-123')
        self.assertEqual(self.vault.get('api_key'), 'sk-123')
        self.assertIsNone(self.vault.get('nonexistent'))
        self.assertEqual(self.vault.get('nonexistent', 'default'), 'default')
        v2 = Vault()
        v2.unlock('pw123')
        self.assertEqual(v2.get('api_key'), 'sk-123')
        v2.delete('api_key')
        self.assertIsNone(v2.get('api_key'))

    def test_keys_list(self):
        self.vault.create('pw')
        self.vault.set('k1', 'v1')
        self.vault.set('k2', 'v2')
        self.assertEqual(sorted(self.vault.keys()), ['k1', 'k2'])

    def test_overwrite_value(self):
        self.vault.create('pw')
        self.vault.set('key', 'old')
        self.vault.set('key', 'new')
        v2 = Vault()
        v2.unlock('pw')
        self.assertEqual(v2.get('key'), 'new')

    def test_empty_vault(self):
        v = Vault()
        self.assertFalse(v.unlock('anything'))


class TestDeriveKey(unittest.TestCase):

    def test_deterministic(self):
        k1 = _derive_key('pw', b'salt123')
        k2 = _derive_key('pw', b'salt123')
        self.assertEqual(k1, k2)

    def test_different_salt(self):
        k1 = _derive_key('pw', b'salt1')
        k2 = _derive_key('pw', b'salt2')
        self.assertNotEqual(k1, k2)

    def test_key_length(self):
        self.assertEqual(len(_derive_key('pw', b'salt')), 32)

    def test_custom_length(self):
        self.assertEqual(len(_derive_key('pw', b'salt', length=16)), 16)


if __name__ == '__main__':
    unittest.main()
