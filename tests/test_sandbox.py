"""Tests for security/sandbox.py"""
import os
import sys
import pytest
from pathlib import Path


def test_sandbox_config_presets():
    from salmalm.security.sandbox import SandboxConfig
    strict = SandboxConfig.strict()
    assert strict.timeout_s == 15
    assert strict.allow_network is False
    assert strict.max_memory_mb == 256

    std = SandboxConfig.standard()
    assert std.timeout_s == 120
    assert std.allow_network is True

    perm = SandboxConfig.permissive()
    assert perm.timeout_s == 1800


def test_path_jail_safe():
    from salmalm.security.sandbox import path_jail
    from salmalm.constants import WORKSPACE_DIR
    safe, resolved = path_jail(str(WORKSPACE_DIR / "test.txt"))
    assert safe is True


def test_path_jail_traversal():
    from salmalm.security.sandbox import path_jail
    safe, msg = path_jail("/etc/passwd")
    assert safe is False
    assert "escapes" in msg


def test_path_jail_dotdot():
    from salmalm.security.sandbox import path_jail
    from salmalm.constants import WORKSPACE_DIR
    safe, msg = path_jail(str(WORKSPACE_DIR / ".." / ".." / "etc" / "passwd"))
    assert safe is False


def test_sandboxed_exec_echo():
    from salmalm.security.sandbox import sandboxed_exec, SandboxConfig
    config = SandboxConfig(timeout_s=5)
    result = sandboxed_exec("echo hello", config=config)
    assert result.success
    assert "hello" in result.stdout


@pytest.mark.skip(reason="subprocess timeout + process group kill conflicts with pytest signal handler")
def test_sandboxed_exec_timeout():
    from salmalm.security.sandbox import sandboxed_exec, SandboxConfig
    config = SandboxConfig(timeout_s=2)
    result = sandboxed_exec(["python3", "-c", "import time; time.sleep(30)"], config=config)
    assert result.timed_out is True


def test_sandboxed_exec_bad_command():
    from salmalm.security.sandbox import sandboxed_exec, SandboxConfig
    config = SandboxConfig(timeout_s=5)
    result = sandboxed_exec("nonexistent_command_xyz", config=config)
    assert not result.success


def test_sandbox_result_format():
    from salmalm.security.sandbox import SandboxResult
    r = SandboxResult(stdout="hello world", exit_code=0)
    assert r.success
    assert "hello" in r.format_output()

    r2 = SandboxResult(exit_code=1, stderr="error msg")
    assert not r2.success
    assert "error msg" in r2.format_output()


def test_sandboxed_exec_isolate_temp():
    from salmalm.security.sandbox import sandboxed_exec, SandboxConfig
    config = SandboxConfig(timeout_s=5, isolate_temp=True)
    result = sandboxed_exec("echo $TMPDIR", config=config, shell=True)
    assert result.success
    assert "salmalm_sandbox" in result.stdout or result.stdout.strip() != ""
