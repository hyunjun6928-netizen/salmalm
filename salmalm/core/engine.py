"""SalmAlm Intelligence Engine — backward-compatible re-export shim.

The actual implementation lives in salmalm/core/intelligence_engine.py.
All public symbols are re-exported here so existing consumers break nothing.

Import graph (no cycles):
  intelligence_engine.py  →  core modules (llm_loop, model_selection, …)
  engine_pipeline.py      →  intelligence_engine.py
  engine.py (this file)   →  intelligence_engine.py + engine_pipeline.py + …
"""

from __future__ import annotations

import re as _re

# ── Primary implementation ──────────────────────────────────────────────────
from salmalm.core.intelligence_engine import (  # noqa: F401
    IntelligenceEngine,
    _get_engine,
    _safe_callback,
    _MAIN_LOOP,
    _METRICS_LOCK,
)
from salmalm.core.intelligence_engine import _get_engine as _get_engine_singleton  # noqa: F401

# Backward-compat: _engine was an eager singleton; now lazy via property-like accessor.
# Code that does `from salmalm.core.engine import _engine` and then calls _engine.run()
# will still work because we bind the same singleton here at first access.
# engine_pipeline.py uses a lazy local import anyway, so this is belt-and-suspenders.
from salmalm.core import intelligence_engine as _ie_mod  # type: ignore[attr-defined]


def __getattr__(name: str):
    """Module-level __getattr__ — lazily expose _engine without eager init."""
    if name == "_engine":
        return _ie_mod._get_engine()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ── Constants ───────────────────────────────────────────────────────────────
from salmalm.constants import (  # noqa: F401
    VERSION,
    INTENT_SHORT_MSG,
    INTENT_COMPLEX_MSG,
    INTENT_CONTEXT_DEPTH,
    REFLECT_SNIPPET_LEN,
    MODEL_ALIASES as _CONST_ALIASES,
    COMMAND_MODEL,
)

_MAX_MESSAGE_LENGTH = 100_000
_SESSION_ID_RE = _re.compile(r"^[a-zA-Z0-9_\-\.]+$")
_THINKING_BUDGET_MAP = {"low": 4000, "medium": 10000, "high": 16000, "xhigh": 32000}
MODEL_ALIASES = {"auto": None, **_CONST_ALIASES}
_PRUNE_TAIL = 500  # backward compat

# ── Re-exports: engine_pipeline (process_message lives here) ────────────────
from salmalm.core.engine_pipeline import (  # noqa: F401
    process_message,
    _process_message_inner,
    _notify_completion,
    begin_shutdown,
    wait_for_active_requests,
)

# ── Re-exports: cost ────────────────────────────────────────────────────────
from salmalm.core.cost import (  # noqa: F401
    estimate_tokens,
    estimate_cost,
    MODEL_PRICING,
    get_pricing as _get_pricing,
)

# ── Re-exports: core ────────────────────────────────────────────────────────
from salmalm.core import (  # noqa: F401
    router,
    compact_messages,
    get_session,
    _sessions,
    _metrics,
    compact_session,
    auto_compact_if_needed,
    audit_log,
)

# ── Re-exports: session_manager ─────────────────────────────────────────────
from salmalm.core.session_manager import (  # noqa: F401
    _should_prune_for_cache,
    _record_api_call_time,
    prune_context,
    _has_image_block,
    _soft_trim,
    estimate_context_window,
    _PRUNE_KEEP_LAST_ASSISTANTS,
    _PRUNE_SOFT_LIMIT,
    _PRUNE_HARD_LIMIT,
    _PRUNE_HEAD,
)

# ── Re-exports: llm_loop ────────────────────────────────────────────────────
from salmalm.core.llm_loop import (  # noqa: F401
    _call_llm_async,
    _call_llm_streaming,
    _load_failover_config,
    _load_cooldowns,
    _save_cooldowns,
    _is_model_cooled_down,
    _record_model_failure,
    _clear_model_cooldown,
    get_failover_config,
    save_failover_config,
    call_with_failover as _call_with_failover_fn,
    try_llm_call as _try_llm_call_fn,
    STATUS_TYPING,
    STATUS_THINKING,
    STATUS_TOOL_RUNNING,
)

# ── Re-exports: model_selection ─────────────────────────────────────────────
from salmalm.core.model_selection import (  # noqa: F401
    select_model as _select_model_impl,
    fix_model_name as _fix_model_name,
    load_routing_config as _load_routing_config,
    save_routing_config as _save_routing_config,
    _SIMPLE_PATTERNS,
    _MODERATE_KEYWORDS,
    _COMPLEX_KEYWORDS,
    _MODEL_NAME_FIXES,
)
get_routing_config = _load_routing_config   # backward compat alias
_select_model = _select_model_impl          # backward compat alias

# ── Re-exports: classifier ──────────────────────────────────────────────────
from salmalm.core.classifier import (  # noqa: F401
    TaskClassifier,
    INTENT_TOOLS,
    _KEYWORD_TOOLS,
    INTENT_MAX_TOKENS,
    _DETAIL_KEYWORDS,
    _get_dynamic_max_tokens,
)

# ── Re-exports: error_messages ──────────────────────────────────────────────
from salmalm.core.error_messages import friendly_error as _friendly_error  # noqa: F401

# ── Re-exports: tools (tests mock salmalm.core.engine.execute_tool) ─────────
from salmalm.tools.tool_handlers import execute_tool  # noqa: F401

# ── Re-exports: slash_commands ──────────────────────────────────────────────
from salmalm.core.slash_commands import (  # noqa: F401
    _session_usage,
    _get_session_usage,
    record_response_usage,
    _SLASH_COMMANDS,
    _SLASH_PREFIX_COMMANDS,
    _dispatch_slash_command,
    _cmd_context,
    _cmd_usage,
    _cmd_plugins,
    _cmd_export_fn as _cmd_export,
)
