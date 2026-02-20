"""Tests for salmalm.features.templates_chat."""
import json
import tempfile
import unittest
from pathlib import Path

from salmalm.features.templates_chat import (
    Template, TemplateManager, _parse_simple_yaml,
    handle_template_command, _BUILTIN_TEMPLATES,
)


class TestParseSimpleYaml(unittest.TestCase):
    def test_basic_kv(self):
        text = 'name: test\ndescription: A test template'
        d = _parse_simple_yaml(text)
        assert d['name'] == 'test'
        assert d['description'] == 'A test template'

    def test_list(self):
        text = 'tools:\n  - read_file\n  - write_file'
        d = _parse_simple_yaml(text)
        assert d['tools'] == ['read_file', 'write_file']

    def test_multiline(self):
        text = 'prompt: |\n  line1\n  line2\n|'
        d = _parse_simple_yaml(text)
        assert 'line1' in d['prompt']
        assert 'line2' in d['prompt']

    def test_empty(self):
        d = _parse_simple_yaml('')
        assert d == {}

    def test_comments(self):
        text = '# comment\nname: test'
        d = _parse_simple_yaml(text)
        assert d['name'] == 'test'

    def test_quoted_values(self):
        text = 'name: "quoted value"'
        d = _parse_simple_yaml(text)
        assert d['name'] == 'quoted value'


class TestTemplate(unittest.TestCase):
    def test_to_dict(self):
        t = Template(name='test', description='desc', system_prompt='prompt')
        d = t.to_dict()
        assert d['name'] == 'test'
        assert d['system_prompt'] == 'prompt'

    def test_from_dict(self):
        d = {'name': 'x', 'description': 'd', 'system_prompt': 'p', 'tools': ['a']}
        t = Template.from_dict(d)
        assert t.name == 'x'
        assert t.tools == ['a']

    def test_to_yaml(self):
        t = Template(name='test', system_prompt='hello\nworld', tools=['a', 'b'])
        yaml = t.to_yaml()
        assert 'name: test' in yaml
        assert 'hello' in yaml

    def test_display_name_default(self):
        t = Template(name='test')
        assert t.display_name == 'test'


class TestTemplateManager(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.mgr = TemplateManager(templates_dir=Path(self._tmpdir))

    def test_builtins_loaded(self):
        templates = self.mgr.list_templates()
        names = {t.name for t in templates}
        assert 'code-review' in names
        assert 'brainstorm' in names

    def test_get_builtin(self):
        t = self.mgr.get('code-review')
        assert t is not None
        assert t.system_prompt

    def test_use_template(self):
        t = self.mgr.use('brainstorm')
        assert t is not None
        assert self.mgr.active is not None
        assert self.mgr.active.name == 'brainstorm'

    def test_use_nonexistent(self):
        t = self.mgr.use('nonexistent')
        assert t is None

    def test_create_custom(self):
        t = self.mgr.create('my-template', system_prompt='Custom prompt', description='My template')
        assert t.name == 'my-template'
        # Should be saved as yaml
        yaml_path = Path(self._tmpdir) / 'my-template.yaml'
        assert yaml_path.exists()

    def test_remove_custom(self):
        self.mgr.create('removable', description='temp')
        assert self.mgr.remove('removable')
        assert self.mgr.get('removable') is None

    def test_remove_builtin_fails(self):
        assert self.mgr.remove('code-review') is False

    def test_deactivate(self):
        self.mgr.use('brainstorm')
        self.mgr.deactivate()
        assert self.mgr.active is None

    def test_persistence_custom(self):
        self.mgr.create('persistent', system_prompt='persist me')
        mgr2 = TemplateManager(templates_dir=Path(self._tmpdir))
        t = mgr2.get('persistent')
        assert t is not None

    def test_load_json_template(self):
        data = {'name': 'json-tmpl', 'description': 'from json', 'system_prompt': 'sp'}
        (Path(self._tmpdir) / 'json-tmpl.json').write_text(json.dumps(data))
        mgr2 = TemplateManager(templates_dir=Path(self._tmpdir))
        assert mgr2.get('json-tmpl') is not None


class TestHandleCommand(unittest.TestCase):
    def test_list(self):
        result = handle_template_command('/template list')
        assert 'Templates' in result or 'template' in result.lower()

    def test_use(self):
        result = handle_template_command('/template use code-review')
        assert '✅' in result

    def test_use_missing_name(self):
        result = handle_template_command('/template use')
        assert '❌' in result

    def test_use_nonexistent(self):
        result = handle_template_command('/template use nonexistent-xyz')
        assert '❌' in result

    def test_create(self):
        result = handle_template_command('/template create new-one')
        assert '✅' in result

    def test_create_missing_name(self):
        result = handle_template_command('/template create')
        assert '❌' in result

    def test_off(self):
        result = handle_template_command('/template off')
        assert '✅' in result

    def test_invalid(self):
        result = handle_template_command('/template xyz')
        assert '❌' in result
