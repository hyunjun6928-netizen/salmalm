"""Model & provider API — list models, switch, test keys, router info, usage."""

from salmalm.security.crypto import vault, log
import json
import os
from salmalm.constants import TEST_MODELS
from salmalm.core import router


class WebModelMixin:
    """Mixin providing model route handlers."""

    def _get_usage_models(self):
        """Get usage models."""
        if not self._require_auth("user"):
            return
        from salmalm.features.edge_cases import usage_tracker

        self._json({"breakdown": usage_tracker.model_breakdown()})

    def _get_models(self):
        """Get models."""
        if not self._require_auth("user"):
            return
        from salmalm.features.edge_cases import model_detector

        force = "?force" in self.path
        models = model_detector.detect_all(force=force)
        self._json({"models": models, "count": len(models)})

    def _get_llm_router_providers(self):
        """Get llm router providers."""
        if not self._require_auth("user"):
            return
        from salmalm.core.llm_router import (
            PROVIDERS,
            is_provider_available,
            list_available_models,
            llm_router,
        )

        providers = []
        for name, cfg in PROVIDERS.items():
            if name == "ollama":
                # Fetch real models from local endpoint instead of hardcoded list
                try:
                    from salmalm.features.model_detect import model_detector

                    detected = model_detector.detect_all(force=True)
                    local_models = [
                        {"name": m["name"], "full": m["id"]} for m in detected if m.get("provider") == "ollama"
                    ]
                except Exception as e:  # noqa: broad-except
                    local_models = [{"name": m, "full": f"ollama/{m}"} for m in cfg["models"]]
                providers.append(
                    {
                        "name": name,
                        "available": is_provider_available(name) or bool(local_models),
                        "env_key": "",
                        "models": local_models or [{"name": m, "full": f"ollama/{m}"} for m in cfg["models"]],
                    }
                )
            else:
                providers.append(
                    {
                        "name": name,
                        "available": is_provider_available(name),
                        "env_key": cfg.get("env_key", ""),
                        "models": [{"name": m, "full": f"{name}/{m}"} for m in cfg["models"]],
                    }
                )
        # Check session-level override (more accurate than global router state)
        _cur = llm_router.current_model
        try:
            _sid = self.headers.get("X-Session-Id") or "web"
            from salmalm.core import get_session as _gs_prov

            _s = _gs_prov(_sid)
            _override = getattr(_s, "model_override", None)
            if _override is not None and _override != "auto":
                _cur = _override
            elif _override == "auto":
                _cur = "auto"
        except Exception as e:
            log.debug(f"Suppressed: {e}")
        self._json(
            {
                "providers": providers,
                "current_model": _cur,
                "all_models": list_available_models(),
            }
        )

    def _get_llm_router_current(self):
        """Get llm router current."""
        if not self._require_auth("user"):
            return
        from salmalm.core.llm_router import llm_router

        self._json({"current_model": llm_router.current_model})

    def _get_api_health_providers(self):
        # Provider health check — Open WebUI style (프로바이더 상태 확인)
        """Get api health providers."""
        if not self._require_auth("user"):
            return
        from salmalm.features.edge_cases import provider_health

        force = "?force" in self.path or "force=1" in self.path
        self._json(provider_health.check_all(force=force))

    def _post_api_test_key(self):
        """Post api test key."""
        body = self._body
        if not self._require_auth("user"):
            return
        provider = body.get("provider", "")
        from salmalm.core.llm import _http_post

        tests = {
            "anthropic": lambda: _http_post(
                "https://api.anthropic.com/v1/messages",
                {
                    "x-api-key": vault.get("anthropic_api_key") or "",
                    "content-type": "application/json",
                    "anthropic-version": "2023-06-01",
                },
                {
                    "model": TEST_MODELS["anthropic"],
                    "max_tokens": 10,  # noqa: F405
                    "messages": [{"role": "user", "content": "ping"}],
                },
                timeout=15,
            ),
            "openai": lambda: _http_post(
                "https://api.openai.com/v1/chat/completions",
                {
                    "Authorization": "Bearer " + (vault.get("openai_api_key") or ""),
                    "Content-Type": "application/json",
                },
                {
                    "model": TEST_MODELS["openai"],
                    "max_tokens": 10,  # noqa: F405
                    "messages": [{"role": "user", "content": "ping"}],
                },
                timeout=15,
            ),
            "xai": lambda: _http_post(
                "https://api.x.ai/v1/chat/completions",
                {
                    "Authorization": "Bearer " + (vault.get("xai_api_key") or ""),
                    "Content-Type": "application/json",
                },
                {
                    "model": TEST_MODELS["xai"],
                    "max_tokens": 10,  # noqa: F405
                    "messages": [{"role": "user", "content": "ping"}],
                },
                timeout=15,
            ),
            "google": lambda: (
                lambda k: __import__("urllib.request", fromlist=["urlopen"]).urlopen(
                    __import__("urllib.request", fromlist=["Request"]).Request(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{TEST_MODELS['google']}:generateContent?key={k}",  # noqa: F405
                        data=json.dumps({"contents": [{"parts": [{"text": "ping"}]}]}).encode(),
                        headers={"Content-Type": "application/json"},
                    ),
                    timeout=15,
                )
            )(vault.get("google_api_key") or ""),
        }
        if provider not in tests:
            self._json({"ok": False, "result": f"❌ Unknown provider: {provider}"})
            return
        key = vault.get(f"{provider}_api_key") if provider != "google" else vault.get("google_api_key")
        if not key:
            self._json({"ok": False, "result": f"❌ {provider} API key not found in vault"})
            return
        try:
            tests[provider]()
            self._json({"ok": True, "result": f"✅ {provider} API connection successful!"})
        except Exception as e:
            self._json(
                {
                    "ok": False,
                    "result": f"❌ {provider} Test failed: {str(e)[:120]}",
                }
            )
        return

    def _post_api_model_switch(self):
        """Handle /api/llm-router/switch and /api/model/switch."""
        body = self._body
        if not self._require_auth("user"):
            return
        from salmalm.core.llm_router import llm_router

        model = body.get("model", "")
        if not model:
            self._json({"error": "model required"}, 400)
            return
        msg = llm_router.switch_model(model)
        # Also update session-level override so auto-routing respects UI selection
        sid = self.headers.get("X-Session-Id") or body.get("session") or "web"
        try:
            from salmalm.core import get_session as _gs_switch

            _s = _gs_switch(sid)
            _s.model_override = None if model == "auto" else model
        except Exception as e:
            log.debug(f"Suppressed: {e}")
        # Return the effective model (session override takes precedence)
        _effective = model if model else llm_router.current_model
        self._json({"ok": "✅" in msg, "message": msg, "current_model": _effective})

    def _post_api_test_provider(self):
        """Handle /api/llm-router/test-key and /api/test-provider."""
        body = self._body
        if not self._require_auth("user"):
            return
        provider = body.get("provider", "")
        api_key = body.get("api_key", "")
        if not provider or not api_key:
            self._json({"error": "provider and api_key required"}, 400)
            return
        from salmalm.core.llm_router import PROVIDERS

        prov_cfg = PROVIDERS.get(provider)
        if not prov_cfg:
            self._json({"ok": False, "message": f"Unknown provider: {provider}"})
            return
        env_key = prov_cfg.get("env_key", "")
        if env_key:
            old_val = os.environ.get(env_key)
            os.environ[env_key] = api_key
        try:
            import urllib.request
            import urllib.error

            if provider == "anthropic":
                url = f"{prov_cfg['base_url']}/messages"
                req = urllib.request.Request(
                    url,
                    data=json.dumps(
                        {
                            "model": TEST_MODELS["anthropic"],
                            "max_tokens": 1,  # noqa: E128
                            "messages": [{"role": "user", "content": "hi"}],
                        }
                    ).encode(),
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    method="POST",
                )
            elif provider == "ollama":
                url = f"{prov_cfg['base_url']}/api/tags"
                req = urllib.request.Request(url)
            else:
                url = f"{prov_cfg['base_url']}/models"
                req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
            urllib.request.urlopen(req, timeout=10)
            self._json({"ok": True, "message": f"✅ {provider} key is valid"})
        except urllib.error.HTTPError as e:
            self._json({"ok": False, "message": f"❌ HTTP {e.code}: Invalid key"})
        except Exception as e:
            self._json({"ok": False, "message": f"❌ Connection failed: {e}"})
        finally:
            if env_key:
                if old_val is not None:
                    os.environ[env_key] = old_val
                elif env_key in os.environ:
                    del os.environ[env_key]
