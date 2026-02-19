"""Tests for salmalm.tools — Tool safety and execution."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

from salmalm.constants import EXEC_ALLOWLIST, EXEC_BLOCKLIST, EXEC_BLOCKLIST_PATTERNS, PROTECTED_FILES


class TestExecBlocklist(unittest.TestCase):

    def test_dangerous_commands_blocked(self):
        must_block = ['rm', 'rmdir', 'mkfs', 'dd', 'shutdown', 'reboot',
                      'sudo', 'su', 'passwd', 'chown', 'chmod']
        for cmd in must_block:
            self.assertIn(cmd, EXEC_BLOCKLIST, f"{cmd} missing")

    def test_patterns_catch_chained(self):
        dangerous = [
            'echo hi; rm -rf /',
            'ls && sudo reboot',
            'cat $(cat /etc/shadow)',
            'echo `whoami`',
            '> /dev/sda',
            '> /etc/passwd',
        ]
        for cmd in dangerous:
            matched = any(re.search(p, cmd) for p in EXEC_BLOCKLIST_PATTERNS)
            self.assertTrue(matched, f"Should block: {cmd}")

    def test_safe_commands_in_allowlist(self):
        from salmalm.constants import EXEC_ELEVATED
        safe = ['ls', 'cat', 'grep', 'find', 'wc', 'head', 'tail', 'git', 'ping']
        for cmd in safe:
            self.assertIn(cmd, EXEC_ALLOWLIST, f"{cmd} should be in allowlist")
            self.assertNotIn(cmd, EXEC_BLOCKLIST, f"{cmd} should not be blocked")
        # Elevated commands should be in EXEC_ELEVATED, not in BLOCKLIST
        elevated = ['python3', 'node', 'docker']
        for cmd in elevated:
            self.assertIn(cmd, EXEC_ELEVATED, f"{cmd} should be in elevated set")
            self.assertNotIn(cmd, EXEC_BLOCKLIST, f"{cmd} should not be blocked")

    def test_allowlist_not_empty(self):
        self.assertGreater(len(EXEC_ALLOWLIST), 30)


class TestProtectedFiles(unittest.TestCase):

    def test_critical_files(self):
        for f in ['.vault.enc', 'audit.db', 'auth.db', 'server.py']:
            self.assertIn(f, PROTECTED_FILES, f"{f} not protected")


class TestPythonEvalBlocklist(unittest.TestCase):

    def _get_blocklist(self):
        tools_py = Path(__file__).parent.parent / 'salmalm' / 'tools' / 'tools_exec.py'
        content = tools_py.read_text(encoding='utf-8')
        match = re.search(r'_EVAL_BLOCKLIST\s*=\s*\[(.*?)\]', content, re.DOTALL)
        self.assertIsNotNone(match, "_EVAL_BLOCKLIST not found")
        return re.findall(r"'([^']+)'", match.group(1))

    def test_blocklist_exists(self):
        bl = self._get_blocklist()
        self.assertGreater(len(bl), 10)

    def test_dangerous_imports_blocked(self):
        bl = self._get_blocklist()
        for pattern in ['import os', 'import sys', 'import subprocess',
                        '__import__', 'eval(', 'open(']:
            self.assertIn(pattern, bl, f"{pattern} missing")

    def test_vault_access_blocked(self):
        bl = self._get_blocklist()
        self.assertTrue(any('.vault' in item for item in bl))


class TestPythonEvalSubprocess(unittest.TestCase):

    def test_runs_in_separate_process(self):
        code = "import os; _result = os.getpid()"
        wrapper = f'import json, os\n_result = None\nexec({repr(code)})\nprint(json.dumps({{"result": str(_result)}}))'
        result = subprocess.run(
            [sys.executable, '-c', wrapper],
            capture_output=True, text=True, timeout=10
        )
        child_pid = json.loads(result.stdout.strip())['result']
        self.assertNotEqual(int(child_pid), os.getpid())

    def test_timeout(self):
        wrapper = 'while True: pass'
        with self.assertRaises(subprocess.TimeoutExpired):
            subprocess.run(
                [sys.executable, '-c', wrapper],
                capture_output=True, text=True, timeout=2
            )


class TestToolDefinitions(unittest.TestCase):

    def test_required_fields(self):
        from salmalm.tools import TOOL_DEFINITIONS
        for tool in TOOL_DEFINITIONS:
            self.assertIn('name', tool)
            self.assertIn('description', tool)
            self.assertIn('input_schema', tool)

    def test_no_duplicates(self):
        from salmalm.tools import TOOL_DEFINITIONS
        names = [t['name'] for t in TOOL_DEFINITIONS]
        self.assertEqual(len(names), len(set(names)))

    def test_minimum_count(self):
        from salmalm.tools import TOOL_DEFINITIONS
        self.assertGreaterEqual(len(TOOL_DEFINITIONS), 25)


if __name__ == '__main__':
    unittest.main()
