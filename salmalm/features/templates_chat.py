"""Conversation Templates — predefined chat templates with system prompts.

stdlib-only. YAML-like config (parsed manually, no pyyaml dependency).
Provides:
  - /template list — list templates
  - /template use <name> — apply template
  - /template create <name> — create custom template
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from salmalm.constants import BASE_DIR

log = logging.getLogger(__name__)

TEMPLATES_DIR = BASE_DIR / 'templates'

# Built-in templates
_BUILTIN_TEMPLATES: Dict[str, Dict[str, Any]] = {
    'code-review': {
        'name': 'code-review',
        'display_name': 'Code Review',
        'description': 'Thorough code review with best practices',
        'system_prompt': (
            'You are an expert code reviewer. Analyze code for:\n'
            '- Bugs and potential issues\n'
            '- Performance improvements\n'
            '- Security vulnerabilities\n'
            '- Code style and readability\n'
            '- Best practices\n'
            'Be specific and constructive. Suggest fixes with code examples.'
        ),
        'tools': ['read_file', 'write_file', 'exec_command'],
        'tags': ['dev', 'review'],
    },
    'brainstorm': {
        'name': 'brainstorm',
        'display_name': 'Brainstorming',
        'description': 'Creative brainstorming session',
        'system_prompt': (
            'You are a creative brainstorming partner. Help generate ideas by:\n'
            '- Building on existing ideas\n'
            '- Challenging assumptions\n'
            '- Offering unexpected perspectives\n'
            '- Using analogies from different domains\n'
            'Be enthusiastic and encourage wild ideas. No idea is too crazy.'
        ),
        'tools': [],
        'tags': ['creative', 'ideation'],
    },
    'interview-prep': {
        'name': 'interview-prep',
        'display_name': 'Interview Preparation',
        'description': 'Technical interview practice',
        'system_prompt': (
            'You are a technical interviewer. Help the user prepare by:\n'
            '- Asking progressively harder questions\n'
            '- Evaluating answers with feedback\n'
            '- Suggesting improvements\n'
            '- Covering algorithms, system design, and behavioral questions\n'
            'Be encouraging but honest about areas for improvement.'
        ),
        'tools': [],
        'tags': ['career', 'practice'],
    },
    'writing': {
        'name': 'writing',
        'display_name': 'Writing Assistant',
        'description': 'Help with writing and editing',
        'system_prompt': (
            'You are a skilled writing editor. Help with:\n'
            '- Grammar and style improvements\n'
            '- Clarity and conciseness\n'
            '- Tone and voice consistency\n'
            '- Structure and flow\n'
            '- Audience-appropriate language\n'
            'Explain your suggestions. Preserve the author\'s voice.'
        ),
        'tools': ['read_file', 'write_file'],
        'tags': ['writing', 'editing'],
    },
    'debug': {
        'name': 'debug',
        'display_name': 'Debug Helper',
        'description': 'Systematic debugging assistance',
        'system_prompt': (
            'You are a debugging expert. Help diagnose issues by:\n'
            '- Asking clarifying questions about the problem\n'
            '- Suggesting systematic debugging steps\n'
            '- Analyzing error messages and stack traces\n'
            '- Proposing hypotheses and tests\n'
            '- Identifying root causes, not just symptoms'
        ),
        'tools': ['read_file', 'exec_command', 'web_search'],
        'tags': ['dev', 'debug'],
    },
}


def _parse_simple_yaml(text: str) -> Dict[str, Any]:
    """Parse simple YAML-like format (key: value, no nesting beyond lists)."""
    result: Dict[str, Any] = {}
    current_key = None
    current_list: Optional[List] = None
    multiline_key = None
    multiline_lines: List[str] = []

    for line in text.split('\n'):
        stripped = line.strip()

        # Multi-line end
        if multiline_key and stripped == '|':
            result[multiline_key] = '\n'.join(multiline_lines)
            multiline_key = None
            multiline_lines = []
            continue

        if multiline_key:
            multiline_lines.append(line.rstrip())
            continue

        # Empty or comment
        if not stripped or stripped.startswith('#'):
            if current_list is not None and current_key:
                result[current_key] = current_list
                current_list = None
                current_key = None
            continue

        # List item
        if stripped.startswith('- ') and current_key:
            if current_list is None:
                current_list = []
            current_list.append(stripped[2:].strip().strip('"').strip("'"))
            continue

        # Key: value
        m = re.match(r'^(\w[\w_-]*)\s*:\s*(.*)', stripped)
        if m:
            # Save previous list
            if current_list is not None and current_key:
                result[current_key] = current_list
                current_list = None

            key = m.group(1)
            val = m.group(2).strip()

            if val == '|':
                multiline_key = key
                multiline_lines = []
            elif val == '':
                current_key = key
                current_list = []
            else:
                result[key] = val.strip('"').strip("'")
                current_key = key

    # Finalize
    if current_list is not None and current_key:
        result[current_key] = current_list
    if multiline_key:
        result[multiline_key] = '\n'.join(multiline_lines)

    return result


class Template:
    """Chat template."""
    __slots__ = ('name', 'display_name', 'description', 'system_prompt', 'tools', 'tags')

    def __init__(self, name: str, display_name: str = '', description: str = '',
                 system_prompt: str = '', tools: Optional[List[str]] = None,
                 tags: Optional[List[str]] = None):
        self.name = name
        self.display_name = display_name or name
        self.description = description
        self.system_prompt = system_prompt
        self.tools = tools or []
        self.tags = tags or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name, 'display_name': self.display_name,
            'description': self.description, 'system_prompt': self.system_prompt,
            'tools': self.tools, 'tags': self.tags,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> 'Template':
        return cls(
            name=d.get('name', ''), display_name=d.get('display_name', ''),
            description=d.get('description', ''), system_prompt=d.get('system_prompt', ''),
            tools=d.get('tools', []), tags=d.get('tags', []),
        )

    def to_yaml(self) -> str:
        """Serialize to simple YAML-like format."""
        lines = [
            f'name: {self.name}',
            f'display_name: {self.display_name}',
            f'description: {self.description}',
            'system_prompt: |',
        ]
        for sl in self.system_prompt.split('\n'):
            lines.append(f'  {sl}')
        lines.append('|')
        lines.append('tools:')
        for t in self.tools:
            lines.append(f'  - {t}')
        lines.append('tags:')
        for t in self.tags:
            lines.append(f'  - {t}')
        return '\n'.join(lines)


class TemplateManager:
    """Manage conversation templates."""

    def __init__(self, templates_dir: Optional[Path] = None):
        self._dir = templates_dir or TEMPLATES_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._templates: Dict[str, Template] = {}
        self._active: Optional[str] = None
        self._load_builtins()
        self._load_custom()

    def _load_builtins(self):
        for name, data in _BUILTIN_TEMPLATES.items():
            self._templates[name] = Template.from_dict(data)

    def _load_custom(self):
        """Load custom templates from YAML files."""
        for f in self._dir.glob('*.yaml'):
            try:
                text = f.read_text(encoding='utf-8')
                data = _parse_simple_yaml(text)
                name = data.get('name', f.stem)
                self._templates[name] = Template.from_dict(data)
            except Exception as e:
                log.warning(f'Failed to load template {f}: {e}')
        for f in self._dir.glob('*.json'):
            try:
                data = json.loads(f.read_text(encoding='utf-8'))
                name = data.get('name', f.stem)
                self._templates[name] = Template.from_dict(data)
            except Exception as e:
                log.warning(f'Failed to load template {f}: {e}')

    def list_templates(self) -> List[Template]:
        return sorted(self._templates.values(), key=lambda t: t.name)

    def get(self, name: str) -> Optional[Template]:
        return self._templates.get(name)

    def use(self, name: str) -> Optional[Template]:
        """Activate a template. Returns template or None."""
        t = self._templates.get(name)
        if t:
            self._active = name
        return t

    @property
    def active(self) -> Optional[Template]:
        if self._active:
            return self._templates.get(self._active)
        return None

    def deactivate(self):
        self._active = None

    def create(self, name: str, system_prompt: str = '', description: str = '',
               tools: Optional[List[str]] = None, tags: Optional[List[str]] = None) -> Template:
        """Create and save a custom template."""
        t = Template(name=name, display_name=name, description=description,
                     system_prompt=system_prompt, tools=tools or [], tags=tags or [])
        self._templates[name] = t
        # Save as YAML
        path = self._dir / f'{name}.yaml'
        path.write_text(t.to_yaml(), encoding='utf-8')
        return t

    def remove(self, name: str) -> bool:
        if name in self._templates and name not in _BUILTIN_TEMPLATES:
            del self._templates[name]
            path = self._dir / f'{name}.yaml'
            if path.exists():
                path.unlink()
            if self._active == name:
                self._active = None
            return True
        return False


# Singleton
template_manager = TemplateManager()


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def handle_template_command(cmd: str, session=None, **kw) -> str:
    """Handle /template list|use|create."""
    parts = cmd.strip().split(maxsplit=2)
    sub = parts[1] if len(parts) > 1 else 'list'

    if sub == 'list':
        templates = template_manager.list_templates()
        if not templates:
            return '📋 No templates available.'
        lines = ['**Conversation Templates:**\n']
        for t in templates:
            active = ' ← active' if template_manager.active and template_manager.active.name == t.name else ''
            lines.append(f'• `{t.name}` — {t.description}{active}')
        return '\n'.join(lines)

    if sub == 'use':
        if len(parts) < 3:
            return '❌ Usage: `/template use <name>`'
        name = parts[2].strip()
        t = template_manager.use(name)
        if not t:
            return f'❌ Template `{name}` not found'
        return f'✅ Template **{t.display_name}** activated\n\n_{t.description}_'

    if sub == 'create':
        if len(parts) < 3:
            return '❌ Usage: `/template create <name>`'
        name = parts[2].strip()
        t = template_manager.create(name=name, description='Custom template')
        return f'✅ Template `{t.name}` created. Edit: `{template_manager._dir}/{name}.yaml`'

    if sub == 'off' or sub == 'deactivate':
        template_manager.deactivate()
        return '✅ Template deactivated.'

    return '❌ Usage: `/template list|use <name>|create <name>|off`'


def register_commands(router):
    """Register /template commands."""
    router.register_prefix('/template', handle_template_command)


def register_tools(registry_module=None):
    """Register template tools."""
    try:
        from salmalm.tools.tool_registry import register_dynamic
        register_dynamic('template_list', lambda args: handle_template_command('/template list'), {
            'name': 'template_list',
            'description': 'List available conversation templates',
            'input_schema': {'type': 'object', 'properties': {}},
        })
    except Exception as e:
        log.warning(f'Failed to register template tools: {e}')
