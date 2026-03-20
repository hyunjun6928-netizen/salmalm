"""Backward-compatibility shim for salmalm.core.slash_commands.

The actual implementation moved to salmalm.features.slash_commands (v0.30.11).
All public symbols are re-exported here so existing callers are unaffected.
"""
from salmalm.features.slash_commands import *  # noqa: F401, F403
from salmalm.features.slash_commands import (
    _dispatch_slash_command,
    record_response_usage,
    _get_session_usage,
    _session_usage,
    _SLASH_COMMANDS,
    _SLASH_PREFIX_COMMANDS,
    _cmd_plugins,
    _cmd_export_fn,
)
from salmalm.features.slash_commands_ext import (
    _cmd_context,
    _cmd_usage,
)
