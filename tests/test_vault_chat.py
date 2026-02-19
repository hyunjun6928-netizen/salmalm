"""Tests for Encrypted Vault Chat."""
import time
from pathlib import Path

import pytest

from salmalm.vault_chat import VaultChat, _aes_gcm_encrypt, _aes_gcm_decrypt, _pbkdf2_derive


@pytest.fixture
def vault(tmp_path):
    return VaultChat(
        db_path=tmp_path / "vault_chat.db",
        meta_path=tmp_path / "vault_chat_meta.json",
    )


PW = "테스트비밀번호123"
PW2 = "newPassword456!"


def test_not_setup_initially(vault):
    assert vault.is_setup() is False
    assert vault.is_open() is False


def test_setup(vault):
    result = vault.setup(PW)
    assert "설정 완료" in result
    assert vault.is_setup() is True


def test_setup_twice(vault):
    vault.setup(PW)
    result = vault.setup(PW)
    assert "이미 설정" in result


def test_open_without_setup(vault):
    result = vault.open(PW)
    assert "설정되지" in result


def test_open_wrong_password(vault):
    vault.setup(PW)
    result = vault.open("wrong")
    assert "올바르지" in result


def test_open_close(vault):
    vault.setup(PW)
    result = vault.open(PW)
    assert "열렸습니다" in result
    assert vault.is_open() is True
    result = vault.close()
    assert "잠겼습니다" in result
    assert vault.is_open() is False


def test_close_already_closed(vault):
    result = vault.close()
    assert "이미" in result


def test_vault_note(vault):
    vault.setup(PW)
    vault.open(PW)
    result = vault.vault_note("비밀 메모입니다", category="personal")
    assert "저장" in result


def test_vault_list(vault):
    vault.setup(PW)
    vault.open(PW)
    vault.vault_note("첫번째 메모")
    vault.vault_note("두번째 메모", category="work")
    result = vault.vault_list()
    assert "볼트 항목" in result
    assert "#1" in result or "#2" in result


def test_vault_search(vault):
    vault.setup(PW)
    vault.open(PW)
    vault.vault_note("비밀 프로젝트 계획")
    vault.vault_note("일반 메모")
    result = vault.vault_search("프로젝트")
    assert "검색 결과" in result
    result = vault.vault_search("없는내용xyz")
    assert "결과가 없습니다" in result


def test_vault_delete(vault):
    vault.setup(PW)
    vault.open(PW)
    vault.vault_note("삭제할 메모")
    result = vault.vault_delete(1)
    assert "삭제" in result
    assert vault.entry_count() == 0


def test_vault_operations_when_locked(vault):
    vault.setup(PW)
    # Don't open
    result = vault.vault_note("should fail")
    assert "잠겨" in result
    result = vault.vault_list()
    assert "잠겨" in result
    result = vault.vault_search("test")
    assert "잠겨" in result


def test_auto_lock(vault):
    vault.setup(PW)
    vault.open(PW)
    vault._auto_lock_seconds = 0  # immediate
    vault._last_access = time.time() - 1
    result = vault.vault_note("should auto-lock")
    assert "잠겨" in result


def test_change_password(vault):
    vault.setup(PW)
    vault.open(PW)
    vault.vault_note("important data")
    vault.close()
    result = vault.change_password(PW, PW2)
    assert "변경" in result
    # Old password should fail
    result = vault.open(PW)
    assert "올바르지" in result
    # New password should work
    result = vault.open(PW2)
    assert "열렸습니다" in result
    # Data should persist
    result = vault.vault_list()
    assert "important" in result


def test_change_password_wrong_old(vault):
    vault.setup(PW)
    result = vault.change_password("wrong", PW2)
    assert "올바르지" in result


def test_export_backup(vault):
    vault.setup(PW)
    vault.open(PW)
    vault.vault_note("backup test")
    vault.close()
    result = vault.export_backup()
    assert "백업 완료" in result


def test_persistence_across_instances(vault, tmp_path):
    vault.setup(PW)
    vault.open(PW)
    vault.vault_note("persistent note")
    vault.close()

    vault2 = VaultChat(
        db_path=tmp_path / "vault_chat.db",
        meta_path=tmp_path / "vault_chat_meta.json",
    )
    vault2.open(PW)
    result = vault2.vault_list()
    assert "persistent" in result
    vault2.close()


def test_encryption_roundtrip():
    key = _pbkdf2_derive("password", b"salt" * 4)
    plaintext = b"hello world secret data"
    encrypted = _aes_gcm_encrypt(key, plaintext)
    decrypted = _aes_gcm_decrypt(key, encrypted)
    assert decrypted == plaintext


def test_encryption_wrong_key():
    key1 = _pbkdf2_derive("password1", b"salt" * 4)
    key2 = _pbkdf2_derive("password2", b"salt" * 4)
    encrypted = _aes_gcm_encrypt(key1, b"secret")
    with pytest.raises(ValueError, match="invalid password"):
        _aes_gcm_decrypt(key2, encrypted)


def test_status(vault):
    result = vault.status()
    assert "미설정" in result
    vault.setup(PW)
    result = vault.status()
    assert "잠김" in result
    vault.open(PW)
    result = vault.status()
    assert "열림" in result


def test_handle_command_status(vault):
    result = vault.handle_command("status")
    assert "볼트" in result


def test_handle_command_unknown(vault):
    result = vault.handle_command("foobar")
    assert "알 수 없는 명령" in result


def test_entry_count_when_closed(vault):
    assert vault.entry_count() == -1
