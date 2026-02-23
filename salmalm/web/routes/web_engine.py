"""Engine optimization & routing API — SLA, routing, failover, engine settings."""



from salmalm.security.crypto import vault, log
import os
from salmalm.constants import COMPACTION_THRESHOLD, MODEL_COSTS


class WebEngineMixin:
    """Mixin providing engine route handlers."""
    def _get_sla(self):
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
        from salmalm.features.sla import sla_config

        self._json(sla_config.get_all())

    def _get_routing(self):
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
        if not self._require_auth("user"):
            return
        from salmalm.core.engine import get_failover_config
        from salmalm.core.llm_loop import get_cooldown_status

        self._json({"config": get_failover_config(), "cooldowns": get_cooldown_status()})

    def _post_api_routing(self):
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
        from salmalm.core.model_selection import MODEL_COSTS

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
        body = self._body
        if not self._require_auth("user"):
            return
        from salmalm.core.engine import save_failover_config, get_failover_config

        save_failover_config(body)
        self._json({"ok": True, "config": get_failover_config()})
        return

    def _post_api_sla_config(self):
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
                "max_tool_iterations": int(os.environ.get("SALMALM_MAX_TOOL_ITER", "15")),
                "cache_ttl": int(os.environ.get("SALMALM_CACHE_TTL", "3600")),
                "batch_api": os.environ.get("SALMALM_BATCH_API", "0") == "1",
                "file_presummary": os.environ.get("SALMALM_FILE_PRESUMMARY", "0") == "1",
                "early_stop": os.environ.get("SALMALM_EARLY_STOP", "0") == "1",
                "temperature_chat": float(os.environ.get("SALMALM_TEMP_CHAT", "0.7")),
                "temperature_tool": float(os.environ.get("SALMALM_TEMP_TOOL", "0.3")),
            }
        )

    def _post_api_engine_settings(self):
        """POST /api/engine/settings — toggle engine optimization settings."""
        import os
        import salmalm.constants as _const

        body = self._body
        if "dynamic_tools" in body:
            os.environ["SALMALM_ALL_TOOLS"] = "0" if body["dynamic_tools"] else "1"
        if "planning" in body:
            os.environ["SALMALM_PLANNING"] = "1" if body["planning"] else "0"
        if "reflection" in body:
            os.environ["SALMALM_REFLECT"] = "1" if body["reflection"] else "0"
        if "compaction_threshold" in body:
            try:
                val = int(body["compaction_threshold"])
                if 10000 <= val <= 200000:
                    _const.COMPACTION_THRESHOLD = val
            except (ValueError, TypeError):
                pass
        if "max_tool_iterations" in body:
            try:
                val = int(body["max_tool_iterations"])
                if 3 <= val <= 999:
                    os.environ["SALMALM_MAX_TOOL_ITER"] = str(val)
            except (ValueError, TypeError):
                pass
        if "cache_ttl" in body:
            try:
                val = int(body["cache_ttl"])
                if 0 <= val <= 86400:
                    os.environ["SALMALM_CACHE_TTL"] = str(val)
                    _const.CACHE_TTL = val
            except (ValueError, TypeError):
                pass
        if "batch_api" in body:
            os.environ["SALMALM_BATCH_API"] = "1" if body["batch_api"] else "0"
        if "file_presummary" in body:
            os.environ["SALMALM_FILE_PRESUMMARY"] = "1" if body["file_presummary"] else "0"
        if "early_stop" in body:
            os.environ["SALMALM_EARLY_STOP"] = "1" if body["early_stop"] else "0"
        for _tk in ("temperature_chat", "temperature_tool"):
            if _tk in body:
                try:
                    val = float(body[_tk])
                    if 0.0 <= val <= 2.0:
                        _env_key = "SALMALM_TEMP_CHAT" if _tk == "temperature_chat" else "SALMALM_TEMP_TOOL"
                        os.environ[_env_key] = str(val)
                except (ValueError, TypeError):
                    pass
        if "cost_cap" in body:
            cap = str(body["cost_cap"]).strip()
            if cap:
                os.environ["SALMALM_COST_CAP"] = cap
            elif "SALMALM_COST_CAP" in os.environ:
                del os.environ["SALMALM_COST_CAP"]
        self._json({"ok": True})

