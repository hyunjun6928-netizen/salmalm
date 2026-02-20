"""Tests for persona system — list, switch, create, delete."""

import os
import sys
import tempfile
import shutil
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestPersonas(unittest.TestCase):
    """Test persona management."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        import salmalm.core.prompt as prompt_mod
        self._orig_dir = prompt_mod.PERSONAS_DIR
        prompt_mod.PERSONAS_DIR = Path(self.tmpdir) / 'personas'
        # Reset builtin flag
        prompt_mod._active_personas.clear()

    def tearDown(self):
        import salmalm.core.prompt as prompt_mod
        prompt_mod.PERSONAS_DIR = self._orig_dir
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_list_personas_returns_builtins(self):
        from salmalm.core.prompt import list_personas
        personas = list_personas()
        self.assertIsInstance(personas, list)
        names = [p['name'] for p in personas]
        self.assertIn('default', names)
        self.assertIn('coding', names)

    def test_list_personas_has_required_fields(self):
        from salmalm.core.prompt import list_personas
        personas = list_personas()
        for p in personas:
            self.assertIn('name', p)
            self.assertIn('title', p)
            self.assertIn('builtin', p)

    def test_get_persona_default(self):
        from salmalm.core.prompt import get_persona
        content = get_persona('default')
        self.assertIsNotNone(content)
        self.assertIn('assistant', content.lower())

    def test_get_persona_coding(self):
        from salmalm.core.prompt import get_persona
        content = get_persona('coding')
        self.assertIsNotNone(content)
        self.assertIn('code', content.lower())

    def test_get_persona_nonexistent(self):
        from salmalm.core.prompt import get_persona
        content = get_persona('nonexistent_persona_xyz')
        self.assertIsNone(content)

    def test_create_persona(self):
        from salmalm.core.prompt import create_persona, list_personas
        ok = create_persona('test_persona', '# Test\nYou are a test bot.')
        self.assertTrue(ok)
        names = [p['name'] for p in list_personas()]
        self.assertIn('test_persona', names)

    def test_create_persona_invalid_name(self):
        from salmalm.core.prompt import create_persona
        ok = create_persona('', 'content')
        self.assertFalse(ok)

    def test_delete_persona_custom(self):
        from salmalm.core.prompt import create_persona, delete_persona, list_personas
        create_persona('deleteme', '# Delete me')
        ok = delete_persona('deleteme')
        self.assertTrue(ok)
        names = [p['name'] for p in list_personas()]
        self.assertNotIn('deleteme', names)

    def test_delete_builtin_persona_fails(self):
        from salmalm.core.prompt import delete_persona
        ok = delete_persona('default')
        self.assertFalse(ok)

    def test_switch_persona(self):
        from salmalm.core.prompt import switch_persona, get_active_persona
        content = switch_persona('test_session', 'coding')
        self.assertIsNotNone(content)
        active = get_active_persona('test_session')
        self.assertEqual(active, 'coding')


if __name__ == '__main__':
    unittest.main()
