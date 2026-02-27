"""Engine optimization & routing API — SLA, routing, failover, engine settings."""

from salmalm.security.crypto import vault
import os
import json
import tempfile
from pathlib import Path
from salmalm.constants import MODELS, DATA_DIR
from salmalm import log

# ── Engine Settings Persistence ──────────────────────────────────────────────
_ENGINE_SETTINGS_FILE = DATA_DIR / "engine_settings.json"

# Keys that map directly to env vars (bool settings)
_BOOL_ENV_MAP = {
    "dynamic_tools": ("SALMALM_ALL_TOOLS", True),   # inverted: True→"0"
    "planning":      ("SALMALM_PLANNING", False),
    "reflection":    ("SALMALM_REFLECT", False),
    "batch_api":     ("SALMALM_BATCH_API", False),
    "file_presummary": ("SALMALM_FILE_PRESUMMARY", False),
    "early_stop":    ("SALMALM_EARLY_STOP", False),
}

# Int/float settings: key → (env_var, min, max, const_attr_or_None)
_INT_SETTINGS_MAP = [
    ("compaction_threshold", "SALMALM_COMPACTION_THRESHOLD", 10000, 200000),
    ("max_tool_iterations",  "SALMALM_MAX_TOOL_ITER",        3,     999),
    ("cache_ttl",            "SALMALM_CACHE_TTL",            0,     86400),
    ("max_tokens_chat",      "SALMALM_MAX_TOKENS_CHAT",      0,     32768),
    ("max_tokens_code",      "SALMALM_MAX_TOKENS_CODE",      0,     32768),
]
_FLOAT_SETTINGS_MAP = [
    ("temperature_chat", "SALMALM_TEMP_CHAT", 0.0, 2.0),
    ("temperature_tool", "SALMALM_TEMP_TOOL", 0.0, 2.0),
]


def _apply_engine_settings_to_runtime(settings: dict) -> None:
    """Apply a settings dict to os.environ and salmalm.constants at runtime."""
    import salmalm.constants as _const

    # Bool settings
    for key, (env_key, inverted) in _BOOL_ENV_MAP.items():
        if key in settings:
            val = settings[key]
            os.environ[env_key] = ("0" if val else "1") if inverted else ("1" if val else "0")

    # Int settings
    for key, env_key, min_val, max_val in _INT_SETTINGS_MAP:
        if key not in settings:
            continue
        try:
            val = int(settings[key])
            if min_val <= val <= max_val:
                os.environ[env_key] = str(val)
                # Patch constants module for in-process cache
                if key == "compaction_threshold":
                    setattr(_const, "COMPACTION_THRESHOLD", val)
                elif key == "cache_ttl":
                    setattr(_const, "CACHE_TTL", val)
        except (ValueError, TypeError):
            pass

    # Float settings
    for key, env_key, min_val, max_val in _FLOAT_SETTINGS_MAP:
        if key not in settings:
            continue
        try:
            val = float(settings[key])
            if min_val <= val <= max_val:
                os.environ[env_key] = str(val)
        except (ValueError, TypeError):
            pass

    # cost_cap (special: empty string = delete)
    if "cost_cap" in settings:
        cap = str(settings["cost_cap"]).strip()
        if cap:
            os.environ["SALMALM_COST_CAP"] = cap
        elif "SALMALM_COST_CAP" in os.environ:
            del os.environ["SALMALM_COST_CAP"]

    # max_tokens runtime dict patch (classifier)
    try:
        from salmalm.core.classifier import INTENT_MAX_TOKENS
        if "max_tokens_chat" in settings:
            val = int(settings["max_tokens_chat"])
            if 0 <= val <= 32768:
                INTENT_MAX_TOKENS["chat"] = val
        if "max_tokens_code" in settings:
            val = int(settings["max_tokens_code"])
            if 0 <= val <= 32768:
                INTENT_MAX_TOKENS["code"] = val
    except Exception:
        pass


def load_engine_settings() -> dict:
    """Load persisted engine settings from disk and apply to runtime.

    Called once at server startup. Safe to call if file doesn't exist yet.
    Returns the loaded settings dict (or empty dict if no file).
    """
    if not _ENGINE_SETTINGS_FILE.exists():
        return {}
    try:
        settings = json.loads(_ENGINE_SETTINGS_FILE.read_text(encoding="utf-8"))
        _apply_engine_settings_to_runtime(settings)
        log.info(f"[ENGINE-SETTINGS] Loaded {len(settings)} settings from {_ENGINE_SETTINGS_FILE}")
        return settings
    except Exception as e:
        log.warning(f"[ENGINE-SETTINGS] Failed to load {_ENGINE_SETTINGS_FILE}: {e}")
        return {}


def save_engine_settings(settings: dict) -> None:
    """Persist engine settings to disk atomically (tempfile + rename)."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=DATA_DIR, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            Path(tmp_path).replace(_ENGINE_SETTINGS_FILE)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as e:
        log.warning(f"[ENGINE-SETTINGS] Failed to save settings: {e}")


def _snapshot_current_settings() -> dict:
    """Capture current runtime state as a saveable settings dict."""
    from salmalm.constants import COMPACTION_THRESHOLD
    return {
        "dynamic_tools":       os.environ.get("SALMALM_ALL_TOOLS", "0") != "1",
        "planning":            os.environ.get("SALMALM_PLANNING", "0") == "1",
        "reflection":          os.environ.get("SALMALM_REFLECT", "0") == "1",
        "batch_api":           os.environ.get("SALMALM_BATCH_API", "0") == "1",
        "file_presummary":     os.environ.get("SALMALM_FILE_PRESUMMARY", "0") == "1",
        "early_stop":          os.environ.get("SALMALM_EARLY_STOP", "0") == "1",
        "compaction_threshold": COMPACTION_THRESHOLD,
        "max_tool_iterations": int(os.environ.get("SALMALM_MAX_TOOL_ITER", "25")),
        "cache_ttl":           int(os.environ.get("SALMALM_CACHE_TTL", "3600")),
        "temperature_chat":    float(os.environ.get("SALMALM_TEMP_CHAT", "0.7")),
        "temperature_tool":    float(os.environ.get("SALMALM_TEMP_TOOL", "0.3")),
        "max_tokens_chat":     int(os.environ.get("SALMALM_MAX_TOKENS_CHAT", "512")),
        "max_tokens_code":     int(os.environ.get("SALMALM_MAX_TOKENS_CODE", "4096")),
        "cost_cap":            os.environ.get("SALMALM_COST_CAP", ""),
    }


def _apply_int_setting(body: dict, key: str, min_val: int, max_val: int, env_key: str = None, const_attr=None) -> None:
    """Apply an integer setting from request body."""
    if key not in body:
        return
    try:
        val = int(body[key])
        if min_val <= val <= max_val:
            if env_key:
                os.environ[env_key] = str(val)
            if const_attr:
                attr_name, module = const_attr
                setattr(module, attr_name, val)
    except (ValueError, TypeError):
        pass


class WebEngineMixin:
    GET_ROUTES = {
        "/api/sla": "_get_sla",
        "/api/sla/config": "_get_sla_config",
        "/api/routing": "_get_routing",
        "/api/failover": "_get_failover",
        "/api/engine/settings": "_get_api_engine_settings",
    }
    POST_ROUTES = {
        "/api/routing": "_post_api_routing",
        "/api/routing/optimize": "_post_api_routing_optimize",
        "/api/failover": "_post_api_failover",
        "/api/sla/config": "_post_api_sla_config",
        "/api/engine/settings": "_post_api_engine_settings",
    }

    """Mixin providing engine route handlers."""

    def _get_sla(self):
        """Get sla."""
        from salmalm.features.sla import uptime_monitor, latency_tracker, watchdog, sla_config

        self._json(
            {
                "uptime": uptime_monitor.get_stats(),
                "latency": latency_tracker.get_stats(),
                "health": watchdog.get_last_report(),
                "config": sla_config.get_all(),
            }
        )

    def _get_sla_config(self):
        """Get sla config."""
        from salmalm.features.sla import sla_config

        self._json(sla_config.get_all())

    def _get_routing(self):
        """Get routing."""
        if not self._require_auth("user"):
            return
        from salmalm.core.engine import get_routing_config

        config = get_routing_config()
        # Validate: strip models whose provider has no key
        _provider_key_map = {
            "anthropic": "anthropic_api_key",
            "openai": "openai_api_key",
            "xai": "xai_api_key",
            "google": "google_api_key",
            "openrouter": "openrouter_api_key",
        }
        for tier in ("simple", "moderate", "complex"):
            model = config.get(tier, "")
            if not model or model == "auto":
                continue
            provider = model.split("/")[0] if "/" in model else ""
            key_name = _provider_key_map.get(provider)
            if key_name and not vault.get(key_name):
                config[tier] = ""  # Reset to auto default
        self._json({"config": config, "available_models": MODELS})

    def _get_failover(self):
        """Get failover."""
        if not self._require_auth("user"):
            return
        from salmalm.core.engine import get_failover_config
        from salmalm.core.llm_loop import get_cooldown_status

        self._json({"config": get_failover_config(), "cooldowns": get_cooldown_status()})

    def _post_api_routing(self):
        """Post api routing."""
        body = self._body
        if not self._require_auth("user"):
            return
        from salmalm.core.engine import _save_routing_config, get_routing_config

        cfg = get_routing_config()
        for k in ("simple", "moderate", "complex"):
            if k in body and body[k]:
                cfg[k] = body[k]
        _save_routing_config(cfg)
        self._json({"ok": True, "config": cfg})
        return

    def _post_api_routing_optimize(self):
        """POST /api/routing/optimize — Auto-optimize routing based on available keys."""
        if not self._require_auth("user"):
            return
        from salmalm.core.model_selection import auto_optimize_and_save

        available_keys = []
        for key_name in ("anthropic_api_key", "openai_api_key", "xai_api_key", "google_api_key"):
            if vault.get(key_name):
                available_keys.append(key_name)
        if not available_keys:
            self._json({"ok": False, "error": "No API keys configured"}, 400)
            return
        config = auto_optimize_and_save(available_keys)
        # Build human-readable summary
        from salmalm.core.model_selection import _MODEL_COSTS as MODEL_COSTS

        summary = {}
        for tier, model in config.items():
            cost = MODEL_COSTS.get(model, (0, 0))
            provider = model.split("/")[0] if "/" in model else "?"
            name = model.split("/")[-1] if "/" in model else model
            summary[tier] = {
                "model": model,
                "provider": provider,
                "name": name,
                "cost_input": cost[0],
                "cost_output": cost[1],
            }
        self._json({"ok": True, "config": config, "summary": summary, "keys_used": available_keys})

    def _post_api_failover(self):
        """Post api failover."""
        body = self._body
        if not self._require_auth("user"):
            return
        from salmalm.core.engine import save_failover_config, get_failover_config

        save_failover_config(body)
        self._json({"ok": True, "config": get_failover_config()})
        return

    def _post_api_sla_config(self):
        """Post api sla config."""
        body = self._body
        # Update SLA config (SLA 설정 업데이트)
        if not self._require_auth("admin"):
            return
        from salmalm.features.sla import sla_config

        sla_config.update(body)
        self._json({"ok": True, "config": sla_config.get_all()})

    def _get_api_engine_settings(self):
        """GET /api/engine/settings — return current engine optimization toggles."""
        if not self._require_auth("user"):
            return
        self._json(_snapshot_current_settings())

    def _post_api_engine_settings(self):
        """POST /api/engine/settings — apply + persist engine optimization settings."""
        if not self._require_auth("user"):
            return
        body = self._body
        # Apply to runtime (os.environ + module constants)
        _apply_engine_settings_to_runtime(body)
        # Persist: merge incoming keys over current snapshot, then save
        current = _snapshot_current_settings()
        save_engine_settings(current)
        self._json({"ok": True})


# ── FastAPI router ────────────────────────────────────────────────────────────
import asyncio as _asyncio
from fastapi import APIRouter as _APIRouter, Request as _Request, Depends as _Depends, Query as _Query
from fastapi.responses import JSONResponse as _JSON, Response as _Response, HTMLResponse as _HTML, StreamingResponse as _SR, RedirectResponse as _RR
from salmalm.web.fastapi_deps import require_auth as _auth, optional_auth as _optauth

router = _APIRouter()

@router.get("/api/sla")
async def get_sla():
    from salmalm.features.sla import uptime_monitor, latency_tracker, watchdog, sla_config
    return _JSON(content={"uptime": uptime_monitor.get_stats(), "latency": latency_tracker.get_stats(),
                           "health": watchdog.get_last_report(), "config": sla_config.get_all()})

@router.get("/api/sla/config")
async def get_sla_config():
    from salmalm.features.sla import sla_config
    return _JSON(content=sla_config.get_all())

@router.get("/api/routing")
async def get_routing(_u=_Depends(_auth)):
    from salmalm.security.crypto import vault
    from salmalm.core.engine import get_routing_config
    from salmalm.constants import MODELS
    config = get_routing_config()
    _provider_key_map = {"anthropic": "anthropic_api_key", "openai": "openai_api_key",
                         "xai": "xai_api_key", "google": "google_api_key", "openrouter": "openrouter_api_key"}
    for tier in ("simple", "moderate", "complex"):
        model = config.get(tier, "")
        if not model or model == "auto":
            continue
        provider = model.split("/")[0] if "/" in model else ""
        key_name = _provider_key_map.get(provider)
        if key_name and not vault.get(key_name):
            config[tier] = ""
    return _JSON(content={"config": config, "available_models": MODELS})

@router.get("/api/failover")
async def get_failover(_u=_Depends(_auth)):
    from salmalm.core.engine import get_failover_config
    from salmalm.core.llm_loop import get_cooldown_status
    return _JSON(content={"config": get_failover_config(), "cooldowns": get_cooldown_status()})

@router.get("/api/engine/settings")
async def get_engine_settings(_u=_Depends(_auth)):
    from salmalm.web.routes.web_engine import _snapshot_current_settings
    return _JSON(content=_snapshot_current_settings())

@router.post("/api/routing")
async def post_routing(request: _Request, _u=_Depends(_auth)):
    from salmalm.core.engine import _save_routing_config, get_routing_config
    body = await request.json()
    cfg = get_routing_config()
    for k in ("simple", "moderate", "complex"):
        if k in body and body[k]:
            cfg[k] = body[k]
    _save_routing_config(cfg)
    return _JSON(content={"ok": True, "config": cfg})

@router.post("/api/routing/optimize")
async def post_routing_optimize(_u=_Depends(_auth)):
    from salmalm.security.crypto import vault
    from salmalm.core.model_selection import auto_optimize_and_save
    available_keys = [k for k in ("anthropic_api_key", "openai_api_key", "xai_api_key", "google_api_key") if vault.get(k)]
    if not available_keys:
        return _JSON(content={"ok": False, "error": "No API keys configured"}, status_code=400)
    config = auto_optimize_and_save(available_keys)
    from salmalm.core.model_selection import _MODEL_COSTS as MODEL_COSTS
    summary = {}
    for tier, model in config.items():
        cost = MODEL_COSTS.get(model, (0, 0))
        provider = model.split("/")[0] if "/" in model else "?"
        name = model.split("/")[-1] if "/" in model else model
        summary[tier] = {"model": model, "provider": provider, "name": name, "cost_input": cost[0], "cost_output": cost[1]}
    return _JSON(content={"ok": True, "config": config, "summary": summary, "keys_used": available_keys})

@router.post("/api/failover")
async def post_failover(request: _Request, _u=_Depends(_auth)):
    from salmalm.core.engine import save_failover_config, get_failover_config
    body = await request.json()
    save_failover_config(body)
    return _JSON(content={"ok": True, "config": get_failover_config()})

@router.post("/api/sla/config")
async def post_sla_config(request: _Request, _u=_Depends(_auth)):
    if _u.get("role") != "admin":
        return _JSON(content={"error": "Admin access required"}, status_code=403)
    from salmalm.features.sla import sla_config
    body = await request.json()
    sla_config.update(body)
    return _JSON(content={"ok": True, "config": sla_config.get_all()})

@router.post("/api/engine/settings")
async def post_engine_settings(request: _Request, _u=_Depends(_auth)):
    from salmalm.web.routes.web_engine import _apply_engine_settings_to_runtime, _snapshot_current_settings, save_engine_settings
    body = await request.json()
    _apply_engine_settings_to_runtime(body)
    current = _snapshot_current_settings()
    save_engine_settings(current)
    return _JSON(content={"ok": True})
