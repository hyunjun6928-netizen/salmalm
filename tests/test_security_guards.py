"""Unit tests for security guard functions — exec, path, SSRF."""
import unittest


class TestExecSafety(unittest.TestCase):
    """Test _is_safe_command and exec approval logic."""

    def test_safe_commands_allowed(self):
        from salmalm.tools.tools_common import _is_safe_command
        for cmd in ['ls -la', 'cat /etc/hostname', 'grep foo bar.txt', 'git status']:
            ok, _ = _is_safe_command(cmd)
            self.assertTrue(ok, f"Should be safe: {cmd}")

    def test_dangerous_commands_blocked(self):
        from salmalm.tools.tools_common import _is_safe_command
        for cmd in ['rm -rf /', 'sudo reboot', 'shutdown now']:
            ok, _ = _is_safe_command(cmd)
            self.assertFalse(ok, f"Should be blocked: {cmd}")

    def test_elevated_commands_flagged(self):
        from salmalm.constants import EXEC_ELEVATED
        self.assertIn('pip', EXEC_ELEVATED)
        self.assertIn('npm', EXEC_ELEVATED)
        # python3 moved to EXEC_BLOCKED_INTERPRETERS (P0-1 hardening)
        from salmalm.constants import EXEC_BLOCKED_INTERPRETERS
        self.assertIn('python3', EXEC_BLOCKED_INTERPRETERS)

    def test_pattern_blocked_eval(self):
        from salmalm.tools.tools_common import _is_safe_command
        ok, _ = _is_safe_command('eval "malicious code"')
        self.assertFalse(ok)

    def test_pattern_blocked_substitution(self):
        from salmalm.tools.tools_common import _is_safe_command
        ok, _ = _is_safe_command('echo $(cat /etc/shadow)')
        self.assertFalse(ok)

    def test_env_override_blocked(self):
        from salmalm.security.exec_approvals import check_env_override
        safe, reason = check_env_override({'LD_PRELOAD': '/tmp/evil.so'})
        self.assertFalse(safe)

    def test_env_safe_allowed(self):
        from salmalm.security.exec_approvals import check_env_override
        safe, _ = check_env_override({'HOME': '/home/user'})
        self.assertTrue(safe)


class TestPathSafety(unittest.TestCase):
    def test_protected_files(self):
        from salmalm.constants import PROTECTED_FILES
        self.assertIn('.vault.enc', PROTECTED_FILES)
        self.assertIn('audit.db', PROTECTED_FILES)


class TestSSRFGuard(unittest.TestCase):
    def test_private_ips_blocked(self):
        from salmalm.tools.tools_common import _is_private_url
        for url in ['http://127.0.0.1/', 'http://169.254.169.254/latest/',
                     'http://10.0.0.1/', 'http://192.168.1.1/']:
            blocked, _ = _is_private_url(url)
            self.assertTrue(blocked, f"Should block: {url}")

    def test_public_urls_allowed(self):
        from salmalm.tools.tools_common import _is_private_url
        for url in ['https://google.com', 'https://api.openai.com/v1']:
            blocked, _ = _is_private_url(url)
            self.assertFalse(blocked, f"Should allow: {url}")


class TestDataDir(unittest.TestCase):
    def test_data_dir_not_site_packages(self):
        from salmalm.constants import DATA_DIR
        self.assertNotIn('site-packages', str(DATA_DIR))

    def test_base_dir_has_init(self):
        from salmalm.constants import BASE_DIR
        self.assertTrue((BASE_DIR / '__init__.py').exists())

    def test_salmalm_home_env(self):
        import os, importlib
        os.environ['SALMALM_HOME'] = '/tmp/test_salmalm_home'
        from salmalm import constants
        importlib.reload(constants)
        self.assertEqual(str(constants.DATA_DIR), '/tmp/test_salmalm_home')
        del os.environ['SALMALM_HOME']
        importlib.reload(constants)


if __name__ == '__main__':
    unittest.main()
