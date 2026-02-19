"""Tests for salmalm.sandbox — SandboxManager."""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from salmalm.sandbox import SandboxManager, SandboxResult, _DANGEROUS_PATTERNS


class TestSandboxResult(unittest.TestCase):
    def test_output_combined(self):
        r = SandboxResult(stdout="hello", stderr="warn", returncode=1)
        self.assertIn("hello", r.output)
        self.assertIn("[stderr]: warn", r.output)
        self.assertIn("[exit code]: 1", r.output)

    def test_output_empty(self):
        r = SandboxResult()
        self.assertEqual(r.output, "(no output)")

    def test_output_timeout(self):
        r = SandboxResult(timed_out=True, returncode=-1)
        self.assertIn("[timed out]", r.output)

    def test_repr(self):
        r = SandboxResult(mode="docker", returncode=0)
        self.assertIn("docker", repr(r))


class TestDangerousCommands(unittest.TestCase):
    def test_rm_rf_root(self):
        dangerous, _ = SandboxManager.is_dangerous("rm -rf /")
        self.assertTrue(dangerous)

    def test_rm_rf_star(self):
        dangerous, _ = SandboxManager.is_dangerous("rm -rf /*")
        self.assertTrue(dangerous)

    def test_sudo(self):
        dangerous, _ = SandboxManager.is_dangerous("sudo apt install foo")
        self.assertTrue(dangerous)

    def test_shutdown(self):
        dangerous, _ = SandboxManager.is_dangerous("shutdown -h now")
        self.assertTrue(dangerous)

    def test_safe_command(self):
        dangerous, _ = SandboxManager.is_dangerous("echo hello")
        self.assertFalse(dangerous)

    def test_ls(self):
        dangerous, _ = SandboxManager.is_dangerous("ls -la /tmp")
        self.assertFalse(dangerous)

    def test_reboot(self):
        dangerous, _ = SandboxManager.is_dangerous("reboot")
        self.assertTrue(dangerous)


class TestSandboxManagerConfig(unittest.TestCase):
    def test_default_config(self):
        sm = SandboxManager()
        self.assertIn("mode", sm.config)
        self.assertIn("docker", sm.config)
        self.assertIn("subprocess", sm.config)

    def test_custom_config(self):
        cfg = {"mode": "off", "docker": {"image": "alpine"}, "subprocess": {}}
        sm = SandboxManager(config=cfg)
        self.assertEqual(sm.config["mode"], "off")

    def test_save_load_config(self):
        with tempfile.TemporaryDirectory() as td:
            cfg_file = Path(td) / "sandbox.json"
            with patch("salmalm.sandbox._CONFIG_FILE", cfg_file), \
                 patch("salmalm.sandbox._CONFIG_DIR", Path(td)):
                sm = SandboxManager(config={"mode": "subprocess", "docker": {}, "subprocess": {}})
                sm.save_config()
                self.assertTrue(cfg_file.exists())
                data = json.loads(cfg_file.read_text())
                self.assertEqual(data["mode"], "subprocess")


class TestSubprocessMode(unittest.TestCase):
    def test_echo(self):
        sm = SandboxManager(config={"mode": "subprocess", "docker": {},
                                     "subprocess": {"isolateEnv": True, "blockDangerousCommands": True}})
        sm._mode = "subprocess"
        result = sm.run("echo hello world")
        self.assertEqual(result.returncode, 0)
        self.assertIn("hello world", result.stdout)
        self.assertEqual(result.mode, "subprocess")

    def test_dangerous_blocked(self):
        sm = SandboxManager(config={"mode": "subprocess", "docker": {},
                                     "subprocess": {"isolateEnv": True, "blockDangerousCommands": True}})
        sm._mode = "subprocess"
        result = sm.run("sudo rm -rf /")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Blocked", result.stderr)

    def test_timeout(self):
        sm = SandboxManager(config={"mode": "subprocess", "docker": {},
                                     "subprocess": {"isolateEnv": True, "blockDangerousCommands": True}})
        sm._mode = "subprocess"
        result = sm.run("sleep 10", timeout=1)
        self.assertTrue(result.timed_out)

    def test_env_isolation(self):
        sm = SandboxManager(config={"mode": "subprocess", "docker": {},
                                     "subprocess": {"isolateEnv": True, "blockDangerousCommands": True}})
        sm._mode = "subprocess"
        result = sm.run("env")
        # Should NOT contain the full original env
        self.assertNotIn("SHELL=", result.stdout)  # Typically not passed through

    def test_sandbox_off_param(self):
        sm = SandboxManager(config={"mode": "subprocess", "docker": {},
                                     "subprocess": {"isolateEnv": True, "blockDangerousCommands": True}})
        sm._mode = "subprocess"
        result = sm.run("echo direct", sandbox=False)
        self.assertEqual(result.mode, "off")
        self.assertIn("direct", result.stdout)

    def test_exec_command_interface(self):
        sm = SandboxManager(config={"mode": "subprocess", "docker": {},
                                     "subprocess": {"isolateEnv": True, "blockDangerousCommands": True}})
        sm._mode = "subprocess"
        output = sm.exec_command("echo tool_test")
        self.assertIn("tool_test", output)


class TestDockerMode(unittest.TestCase):
    @patch("subprocess.run")
    def test_docker_detection_available(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        sm = SandboxManager(config={"mode": "auto", "docker": {}, "subprocess": {}})
        sm._docker_available = None
        result = sm._detect_docker()
        self.assertTrue(result)

    @patch("subprocess.run")
    def test_docker_detection_unavailable(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        sm = SandboxManager(config={"mode": "auto", "docker": {}, "subprocess": {}})
        sm._docker_available = None
        result = sm._detect_docker()
        self.assertFalse(result)

    @patch("subprocess.run")
    def test_docker_run_cmd(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="output", stderr="")
        sm = SandboxManager(config={"mode": "docker",
                                     "docker": {"image": "python:3.12-slim", "network": "none",
                                                "workspaceAccess": "none", "timeoutSeconds": 300, "binds": []},
                                     "subprocess": {}})
        sm._mode = "docker"
        result = sm._run_docker("echo hello", timeout=30, workspace=None, env=None)
        self.assertEqual(result.mode, "docker")
        call_args = mock_run.call_args[0][0]
        self.assertEqual(call_args[0], "docker")
        self.assertIn("--network=none", call_args)
        self.assertIn("--rm", call_args)

    @patch("subprocess.run")
    def test_docker_timeout(self, mock_run):
        from subprocess import TimeoutExpired
        mock_run.side_effect = TimeoutExpired("docker", 5)
        sm = SandboxManager(config={"mode": "docker",
                                     "docker": {"image": "alpine", "network": "none",
                                                "workspaceAccess": "none", "timeoutSeconds": 5, "binds": []},
                                     "subprocess": {}})
        sm._mode = "docker"
        result = sm._run_docker("sleep 999", timeout=5, workspace=None, env=None)
        self.assertTrue(result.timed_out)


class TestModeResolution(unittest.TestCase):
    def test_mode_off(self):
        sm = SandboxManager(config={"mode": "off", "docker": {}, "subprocess": {}})
        self.assertEqual(sm.mode, "off")

    def test_mode_subprocess(self):
        sm = SandboxManager(config={"mode": "subprocess", "docker": {}, "subprocess": {}})
        self.assertEqual(sm.mode, "subprocess")

    @patch.object(SandboxManager, '_detect_docker', return_value=True)
    def test_mode_auto_docker(self, _):
        sm = SandboxManager(config={"mode": "auto", "docker": {}, "subprocess": {}})
        self.assertEqual(sm.mode, "docker")

    @patch.object(SandboxManager, '_detect_docker', return_value=False)
    def test_mode_auto_subprocess(self, _):
        sm = SandboxManager(config={"mode": "auto", "docker": {}, "subprocess": {}})
        self.assertEqual(sm.mode, "subprocess")


if __name__ == "__main__":
    unittest.main()
