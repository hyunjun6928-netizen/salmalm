"""Engine optimization & routing API — SLA, routing, failover, engine settings."""

from salmalm.security.crypto import vault
import os
from salmalm.constants import MODELS


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
        from salmalm.core.model_selection import load_routing_config as get_routing_config

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
        from salmalm.core.llm_loop import get_failover_config
        from salmalm.core.llm_loop import get_cooldown_status

        self._json({"config": get_failover_config(), "cooldowns": get_cooldown_status()})

    def _post_api_routing(self):
        """Post api routing."""
        body = self._body
        if not self._require_auth("user"):
            return
        from salmalm.core.model_selection import _save_routing_config, load_routing_config as get_routing_config

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
        from salmalm.core.llm_loop import save_failover_config, get_failover_config

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
        import os
        from salmalm.constants import COMPACTION_THRESHOLD

        self._json(
            {
                "dynamic_tools": os.environ.get("SALMALM_ALL_TOOLS", "0") != "1",
                "planning": os.environ.get("SALMALM_PLANNING", "0") == "1",
                "reflection": os.environ.get("SALMALM_REFLECT", "0") == "1",
                "compaction_threshold": COMPACTION_THRESHOLD,
                "cost_cap": os.environ.get("SALMALM_COST_CAP", ""),
                "max_tool_iterations": int(os.environ.get("SALMALM_MAX_TOOL_ITER", "25")),
                "cache_ttl": int(os.environ.get("SALMALM_CACHE_TTL", "3600")),
                "batch_api": os.environ.get("SALMALM_BATCH_API", "0") == "1",
                "file_presummary": os.environ.get("SALMALM_FILE_PRESUMMARY", "0") == "1",
                "early_stop": os.environ.get("SALMALM_EARLY_STOP", "0") == "1",
                "temperature_chat": float(os.environ.get("SALMALM_TEMP_CHAT", "0.7")),
                "temperature_tool": float(os.environ.get("SALMALM_TEMP_TOOL", "0.3")),
                "max_tokens_chat": int(os.environ.get("SALMALM_MAX_TOKENS_CHAT", "512")),
                "max_tokens_code": int(os.environ.get("SALMALM_MAX_TOKENS_CODE", "4096")),
            }
        )

    def _post_api_engine_settings(self):
        """POST /api/engine/settings — toggle engine optimization settings."""
        import os
        import salmalm.constants as _const

        body = self._body
        _BOOL_SETTINGS = {
            "dynamic_tools": ("SALMALM_ALL_TOOLS", True),  # inverted
            "planning": ("SALMALM_PLANNING", False),
            "reflection": ("SALMALM_REFLECT", False),
            "batch_api": ("SALMALM_BATCH_API", False),
            "file_presummary": ("SALMALM_FILE_PRESUMMARY", False),
            "early_stop": ("SALMALM_EARLY_STOP", False),
        }
        for key, (env_key, inverted) in _BOOL_SETTINGS.items():
            if key in body:
                val = body[key]
                os.environ[env_key] = ("0" if val else "1") if inverted else ("1" if val else "0")
        _apply_int_setting(body, "compaction_threshold", 10000, 200000, const_attr=("COMPACTION_THRESHOLD", _const))
        _apply_int_setting(body, "max_tool_iterations", 3, 999, env_key="SALMALM_MAX_TOOL_ITER")
        _apply_int_setting(body, "cache_ttl", 0, 86400, env_key="SALMALM_CACHE_TTL", const_attr=("CACHE_TTL", _const))
        for _tk in ("temperature_chat", "temperature_tool"):
            if _tk in body:
                try:
                    val = float(body[_tk])
                    if 0.0 <= val <= 2.0:
                        os.environ["SALMALM_TEMP_CHAT" if _tk == "temperature_chat" else "SALMALM_TEMP_TOOL"] = str(val)
                except (ValueError, TypeError):
                    pass
        if "cost_cap" in body:
            cap = str(body["cost_cap"]).strip()
            if cap:
                os.environ["SALMALM_COST_CAP"] = cap
            elif "SALMALM_COST_CAP" in os.environ:
                del os.environ["SALMALM_COST_CAP"]
        # Max tokens per intent
        for _mt_key, _mt_env, _mt_const in [
            ("max_tokens_chat", "SALMALM_MAX_TOKENS_CHAT", "chat"),
            ("max_tokens_code", "SALMALM_MAX_TOKENS_CODE", "code"),
        ]:
            if _mt_key in body:
                try:
                    val = int(body[_mt_key])
                    if 0 <= val <= 32768:  # 0 = Auto (dynamic allocation)
                        os.environ[_mt_env] = str(val)
                        # Update runtime dict
                        from salmalm.core.classifier import INTENT_MAX_TOKENS

                        INTENT_MAX_TOKENS[_mt_const] = val
                except (ValueError, TypeError):
                    pass
        self._json({"ok": True})
