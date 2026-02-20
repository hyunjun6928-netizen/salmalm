"""UI control tool — lets AI change UI settings via WebSocket commands."""
import logging
from salmalm.tool_registry import register

log = logging.getLogger('salmalm')

# Pending UI commands queue (consumed by WebSocket broadcast)
_pending_ui_commands: list = []

VALID_ACTIONS = {
    'set_lang': {'values': ['en', 'ko'], 'desc': 'Change UI language'},
    'set_theme': {'values': ['light', 'dark'], 'desc': 'Change UI theme'},
    'set_model': {'values': None, 'desc': 'Switch AI model (e.g. anthropic/claude-sonnet-4-6)'},
    'new_session': {'values': None, 'desc': 'Create a new chat session'},
    'show_panel': {'values': ['chat', 'settings', 'dashboard', 'sessions', 'cron', 'memory', 'docs'], 'desc': 'Navigate to a panel'},
    'add_cron': {'values': None, 'desc': 'Add a cron job (pass name, interval, prompt)'},
    'toggle_debug': {'values': ['on', 'off'], 'desc': 'Toggle debug auto-refresh'},
}


@register('ui_control')
def handle_ui_control(args: dict) -> str:
    """Execute a UI control command."""
    action = args.get('action', '')
    value = args.get('value', '')

    if action not in VALID_ACTIONS:
        return f"❌ Unknown action '{action}'. Valid: {', '.join(VALID_ACTIONS.keys())}"

    spec = VALID_ACTIONS[action]
    if spec['values'] and value not in spec['values']:
        return f"❌ Invalid value '{value}' for {action}. Valid: {', '.join(spec['values'])}"

    cmd = {'action': action, 'value': value}

    # For add_cron, pass extra params
    if action == 'add_cron':
        cmd['name'] = args.get('name', 'ai-job')
        cmd['interval'] = args.get('interval', 3600)
        cmd['prompt'] = args.get('prompt', '')

    _pending_ui_commands.append(cmd)
    log.info(f"[UI_CTRL] Queued: {action}={value}")

    desc = spec['desc']
    return f"✅ UI command sent: {action}={value} ({desc})"


def pop_pending_commands() -> list:
    """Pop all pending UI commands (called by WebSocket broadcaster)."""
    cmds = list(_pending_ui_commands)
    _pending_ui_commands.clear()
    return cmds
