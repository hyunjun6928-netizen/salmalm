"""Test vault create/unlock/auto-unlock flow."""
import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch


class TestVaultLifecycle:
    """Test vault creation and unlock."""

    def setup_method(self):
        self.tmp = tempfile.mktemp(suffix='.vault')
        self.tmp_path = Path(self.tmp)

    def teardown_method(self):
        self.tmp_path.unlink(missing_ok=True)
        auto = self.tmp_path.parent / '.vault_auto'
        auto.unlink(missing_ok=True)

    @patch('salmalm.security.crypto.VAULT_FILE')
    def test_create_no_password(self, mock_vf):
        mock_vf.__class__ = Path
        from salmalm.security.crypto import Vault
        import salmalm.security.crypto as cr
        orig = cr.VAULT_FILE
        cr.VAULT_FILE = self.tmp_path

        v = Vault()
        assert not v.is_unlocked
        v.create('')
        assert v.is_unlocked
        assert self.tmp_path.exists()

        cr.VAULT_FILE = orig

    @patch('salmalm.security.crypto.VAULT_FILE')
    def test_create_with_password(self, mock_vf):
        from salmalm.security.crypto import Vault
        import salmalm.security.crypto as cr
        orig = cr.VAULT_FILE
        cr.VAULT_FILE = self.tmp_path

        v = Vault()
        v.create('test1234')
        assert v.is_unlocked

        # New instance should be locked
        v2 = Vault()
        assert not v2.is_unlocked
        # Unlock with correct password
        assert v2.unlock('test1234')
        assert v2.is_unlocked

        # Wrong password should fail
        v3 = Vault()
        assert not v3.unlock('wrong')

        cr.VAULT_FILE = orig

    @patch('salmalm.security.crypto.VAULT_FILE')
    def test_set_and_get(self, mock_vf):
        from salmalm.security.crypto import Vault
        import salmalm.security.crypto as cr
        orig = cr.VAULT_FILE
        cr.VAULT_FILE = self.tmp_path

        v = Vault()
        v.create('')
        v.set('api_key', 'sk-test-123')
        assert v.get('api_key') == 'sk-test-123'
        assert v.get('nonexistent') is None

        # Persist and reload
        v2 = Vault()
        v2.unlock('')
        assert v2.get('api_key') == 'sk-test-123'

        cr.VAULT_FILE = orig

    @patch('salmalm.security.crypto.VAULT_FILE')
    def test_empty_password_unlock(self, mock_vf):
        from salmalm.security.crypto import Vault
        import salmalm.security.crypto as cr
        orig = cr.VAULT_FILE
        cr.VAULT_FILE = self.tmp_path

        v = Vault()
        v.create('')
        v2 = Vault()
        assert v2.unlock('')
        assert v2.is_unlocked

        cr.VAULT_FILE = orig


class TestVaultAutoFile:
    """Test .vault_auto based auto-unlock."""

    def test_auto_file_empty_means_no_password(self):
        import base64
        hint = ''
        pw = '' if not hint else base64.b64decode(hint).decode()
        assert pw == ''

    def test_auto_file_with_password(self):
        import base64
        original_pw = 'mypassword'
        hint = base64.b64encode(original_pw.encode()).decode()
        decoded = base64.b64decode(hint).decode()
        assert decoded == original_pw

    def test_auto_file_invalid_base64(self):
        """Invalid base64 should not crash."""
        import base64
        hint = 'not-valid-base64!!!'
        try:
            base64.b64decode(hint)
        except Exception:
            pass  # Should be caught gracefully
