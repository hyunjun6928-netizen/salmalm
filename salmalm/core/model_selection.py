"""Model selection — single authority for choosing which model handles a message.

LLMRouter handles provider availability/failover only.
All routing decisions flow through select_model().
"""

from __future__ import annotations

import json
import re
from typing import Tuple

from salmalm.constants import MODELS as _MODELS, DATA_DIR
import logging
log = logging.getLogger(__name__)
# ── Complexity keywords ──
_SIMPLE_PATTERNS = re.compile(
    r"^(안녕|hi|hello|hey|ㅎㅇ|ㅎㅎ|ㄱㅅ|고마워|감사|ㅋㅋ|ㅎㅎ|ok|lol|yes|no|네|아니|응|ㅇㅇ|뭐해|잘자|굿|bye|잘가|좋아|ㅠㅠ|ㅜㅜ|오|와|대박|진짜|뭐|어|음|흠|뭐야|왜|어떻게|언제|어디|누구|얼마)[\?!？！.\s]*$",
    re.IGNORECASE,
)
_MODERATE_KEYWORDS = [
    "분석",
    "리뷰",
    "요약",
    "코드",
    "code",
    "analyze",
    "review",
    "summarize",
    "summary",
    "compare",
    "비교",
    "refactor",
    "리팩",
    "debug",
    "디버그",
    "explain",
    "설명",
    "번역",
    "translate",
]
_COMPLEX_KEYWORDS = [
    "설계",
    "아키텍처",
    "architecture",
    "design",
    "system design",
    "from scratch",
    "처음부터",
    "전체",
    "migration",
    "마이그레이션",
]

# ── Model name corrections (from constants — single source of truth) ──
from salmalm.constants import MODEL_NAME_FIXES as _MODEL_NAME_FIXES
import logging
log = logging.getLogger(__name__)

# ── Routing config ──
_ROUTING_CONFIG_FILE = DATA_DIR / "routing.json"


def fix_model_name(model: str) -> str:
    """Correct outdated model names to actual API IDs."""
    return _MODEL_NAME_FIXES.get(model, model)


def load_routing_config() -> dict:
    """Load user's model routing config. Returns {simple, moderate, complex} model IDs."""
    defaults = {"simple": "", "moderate": "", "complex": ""}
    try:
        if _ROUTING_CONFIG_FILE.exists():
            cfg = json.loads(_ROUTING_CONFIG_FILE.read_text(encoding="utf-8"))
            for k in ("simple", "moderate", "complex"):
                if k in cfg and cfg[k]:
                    defaults[k] = cfg[k]
    except Exception as e:
        log.debug(f"Suppressed: {e}")
    return defaults


def save_routing_config(config: dict) -> None:
    """Save user's model routing config."""
    try:
        _ROUTING_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        _ROUTING_CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")
    except Exception as e:
        log.debug(f"Suppressed: {e}")


# ── Cost-per-1M-token table (input/output) for auto-optimization ──
_MODEL_COSTS = {
    # Anthropic
    "anthropic/claude-haiku-3.5-20241022": (1.0, 5.0),
    "anthropic/claude-sonnet-4-20250514": (3.0, 15.0),
    "anthropic/claude-opus-4-6": (5.0, 25.0),
    # OpenAI
    "openai/gpt-4.1-nano": (0.1, 0.4),
    "openai/gpt-4.1-mini": (0.4, 1.6),
    "openai/gpt-4.1": (2.0, 8.0),
    "openai/gpt-5.3-codex": (2.0, 8.0),
    "openai/gpt-5.1-codex": (1.5, 6.0),
    "openai/o4-mini": (1.1, 4.4),
    # Google
    "google/gemini-2.5-flash": (0.15, 0.6),
    "google/gemini-3-flash-preview": (0.15, 0.6),
    "google/gemini-2.5-pro": (1.25, 10.0),
    "google/gemini-3-pro-preview": (1.25, 10.0),
    # xAI
    "xai/grok-3-mini": (0.3, 0.5),
    "xai/grok-3": (3.0, 15.0),
    "xai/grok-4": (3.0, 15.0),
}

# Tier candidates: (model_id, provider_key_name)
# Tier candidates: ordered by cost-effectiveness per tier.
# First match for a given provider wins → order matters!
# Rule: each provider must land on a DIFFERENT model per tier.
#   Simple   = cheapest (cost-optimized)
#   Moderate = mid-range (balanced quality/cost, must differ from simple)
#   Complex  = strongest (quality-first, must differ from moderate)
_TIER_CANDIDATES = {
    "simple": [
        # Goal: cheapest model per provider
        ("openai/gpt-4.1-nano", "openai_api_key"),  # $0.1/$0.4
        ("google/gemini-2.5-flash", "google_api_key"),  # $0.15/$0.6
        ("xai/grok-3-mini", "xai_api_key"),  # $0.3/$0.5
        ("openai/gpt-4.1-mini", "openai_api_key"),  # $0.4/$1.6
        ("anthropic/claude-haiku-3.5-20241022", "anthropic_api_key"),  # $1/$5
    ],
    "moderate": [
        # Goal: balanced — must be stronger than simple tier pick
        ("openai/gpt-4.1-mini", "openai_api_key"),  # $0.4/$1.6
        ("openai/o4-mini", "openai_api_key"),  # $1.1/$4.4 (reasoning)
        ("google/gemini-2.5-pro", "google_api_key"),  # $1.25/$10
        ("google/gemini-3-pro-preview", "google_api_key"),  # $1.25/$10
        ("openai/gpt-4.1", "openai_api_key"),  # $2/$8
        ("xai/grok-3", "xai_api_key"),  # $3/$15
        ("anthropic/claude-sonnet-4-20250514", "anthropic_api_key"),  # $3/$15
        ("anthropic/claude-haiku-3.5-20241022", "anthropic_api_key"),  # $1/$5 (last resort)
    ],
    "complex": [
        # Goal: strongest model per provider
        ("openai/gpt-4.1", "openai_api_key"),  # $2/$8
        ("openai/gpt-5.2-codex", "openai_api_key"),  # $2/$8
        ("google/gemini-3-pro-preview", "google_api_key"),  # $1.25/$10
        ("xai/grok-4", "xai_api_key"),  # $3/$15
        ("anthropic/claude-opus-4-6", "anthropic_api_key"),  # $5/$25 (max quality)
        ("anthropic/claude-sonnet-4-20250514", "anthropic_api_key"),  # $3/$15 (fallback)
        ("google/gemini-2.5-pro", "google_api_key"),  # $1.25/$10
    ],
}


def auto_optimize_routing(available_keys: list[str]) -> dict:
    """Generate optimal routing config based on available API keys.

    Args:
        available_keys: list of key names like ['anthropic_api_key', 'openai_api_key']

    Returns:
        dict with {simple, moderate, complex} model IDs optimized for cost.
    """
    key_set = set(available_keys)
    result = {}

    for tier in ("simple", "moderate", "complex"):
        for model_id, required_key in _TIER_CANDIDATES[tier]:
            if required_key in key_set:
                result[tier] = model_id
                break
        if tier not in result:
            # Fallback: use whatever is available
            result[tier] = _MODELS.get("sonnet", "anthropic/claude-sonnet-4-20250514")

    return result


def auto_optimize_and_save(available_keys: list[str]) -> dict:
    """Auto-optimize routing and save to config file. Returns the config."""
    config = auto_optimize_routing(available_keys)
    save_routing_config(config)
    return config


def _validate_tier_keys(rc: dict, prov_keys: dict) -> None:
    """Strip tier models whose provider has no API key."""
    try:
        from salmalm.security.crypto import vault
        for k in ("simple", "moderate", "complex"):
            model = rc.get(k, "")
            if model:
                prov = model.split("/")[0] if "/" in model else ""
                key_name = prov_keys.get(prov)
                if key_name and not vault.get(key_name):
                    rc[k] = ""
    except Exception as e:
        log.debug(f"Suppressed: {e}")


def select_model(message: str, session) -> Tuple[str, str]:
    """Select optimal model based on message complexity.

    Returns (model_id, complexity_level) where complexity is 'simple'|'moderate'|'complex'|'manual'.
    Respects session-level model_override (from /model command).
    """
    override = getattr(session, "model_override", None)
    if override and override != "auto":
        _OVERRIDE_MAP = {"haiku": ("simple", "haiku"), "sonnet": ("moderate", "sonnet"), "opus": ("complex", "opus")}
        if override in _OVERRIDE_MAP:
            level, key = _OVERRIDE_MAP[override]
            return _MODELS[key], level
        return override, "manual"

    rc = load_routing_config()
    # Smart defaults: simple→haiku (cheapest), moderate→sonnet, complex→sonnet
    _tier_defaults = {
        "simple": _MODELS.get("haiku", ""),
        "moderate": _MODELS.get("sonnet", ""),
        "complex": _MODELS.get("sonnet", ""),
    }
    _default_fallback = getattr(session, "_default_model", None)
    # If user chose a model during onboarding, use it for complex tier
    if _default_fallback and not rc.get("complex"):
        _tier_defaults["complex"] = _default_fallback
    # Validate: strip models whose provider has no API key
    _prov_keys = {
        "anthropic": "anthropic_api_key",
        "openai": "openai_api_key",
        "xai": "xai_api_key",
        "google": "google_api_key",
        "openrouter": "openrouter_api_key",
    }
    _validate_tier_keys(rc, _prov_keys)
    for k in ("simple", "moderate", "complex"):
        if not rc[k]:
            rc[k] = _tier_defaults.get(k, _MODELS.get("sonnet", ""))
    msg_lower = message.lower()
    msg_len = len(message)

    if getattr(session, "thinking_enabled", False):
        return rc["complex"], "complex"

    if msg_len > 500:
        return rc["complex"], "complex"
    for kw in _COMPLEX_KEYWORDS:
        if kw in msg_lower:
            return rc["complex"], "complex"

    if "```" in message or "def " in message or "class " in message:
        return rc["moderate"], "moderate"
    for kw in _MODERATE_KEYWORDS:
        if kw in msg_lower:
            return rc["moderate"], "moderate"

    if msg_len < 50 and _SIMPLE_PATTERNS.match(message.strip()):
        return rc["simple"], "simple"
    if msg_len < 50:
        return rc["simple"], "simple"

    return rc["moderate"], "moderate"
