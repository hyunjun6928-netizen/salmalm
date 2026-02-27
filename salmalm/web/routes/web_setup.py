"""Setup & onboarding API — first run, setup wizard, onboarding flow."""

from salmalm.security.crypto import vault, log
import json
import os
from salmalm.constants import DATA_DIR, VAULT_FILE, TEST_MODELS
from salmalm.core import audit_log


def _ensure_vault_unlocked(vault) -> bool:
    """Ensure vault is unlocked (auto-create or unlock with empty password). Returns True if unlocked."""
    try:
        from salmalm.security.crypto import VAULT_FILE

        if not VAULT_FILE.exists():
            vault.create("", save_to_keychain=False)
        else:
            vault.unlock("")
    except Exception as e:
        log.debug(f"Suppressed: {e}")
    return vault.is_unlocked


class WebSetupMixin:
    GET_ROUTES = {
        "/api/onboarding": "_get_api_onboarding",
        "/setup": "_get_setup",
    }
    POST_ROUTES = {
        "/api/setup": "_post_api_setup",
        "/api/onboarding": "_post_api_onboarding",
        "/api/onboarding/preferences": "_post_api_onboarding_preferences",
    }

    """Mixin providing setup route handlers."""

    def _needs_onboarding(self) -> bool:
        """Check if first-run onboarding is needed (no API keys or Ollama configured)."""
        if not vault.is_unlocked:
            return False
        providers = [
            "anthropic_api_key",
            "openai_api_key",
            "xai_api_key",
            "google_api_key",
            "openrouter_api_key",
        ]
        has_api_key = any(vault.get(k) for k in providers)
        has_ollama = bool(vault.get("ollama_url"))
        return not (has_api_key or has_ollama)

    def _get_api_onboarding(self):
        """GET /api/onboarding — return onboarding status."""
        needs = self._needs_onboarding() if vault.is_unlocked else False
        self._json({"needs_onboarding": needs, "vault_unlocked": vault.is_unlocked})

    def _needs_first_run(self) -> bool:
        """True if vault file doesn't exist and no env password — brand new install."""
        if VAULT_FILE.exists():  # noqa: F405
            return False
        if os.environ.get("SALMALM_VAULT_PW", ""):
            return False
        # If .vault_auto exists, auto-create vault with that password
        try:
            _pw_hint_file = VAULT_FILE.parent / ".vault_auto"  # noqa: F405
            if _pw_hint_file.exists():
                _hint = _pw_hint_file.read_text(encoding="utf-8").strip()
                if _hint:
                    import base64
                    try:
                        _auto_pw = base64.b64decode(_hint).decode()
                    except Exception:
                        _auto_pw = _hint
                else:
                    _auto_pw = ""
                vault.create(_auto_pw)
                vault.unlock(_auto_pw, save_to_keychain=True)
                log.info("[SETUP] Vault auto-created from .vault_auto")
                return False
        except Exception as e:
            log.debug(f"vault_auto create failed: {e}")
        return True

    # ── Extracted GET handlers ────────────────────────────────

    def _get_setup(self):
        # Allow re-running the setup wizard anytime
        """Get setup."""
        from salmalm.web import templates as _tmpl

        self._html(_tmpl.ONBOARDING_HTML)

    def _post_api_setup(self):
        """Post api setup."""
        body = self._body
        # First-run setup — create vault with or without password
        if VAULT_FILE.exists():  # noqa: F405
            self._json({"error": "Already set up"}, 400)
            return
        use_pw = body.get("use_password", False)
        pw = body.get("password", "")
        if use_pw:
            if len(pw) < 4:
                self._json({"error": "Password must be at least 4 characters"}, 400)
                return
        try:
            _vault_pw = pw if use_pw else ""
            vault.create(_vault_pw)
            # Auto-unlock vault after creation so API keys can be saved immediately
            vault.unlock(_vault_pw, save_to_keychain=True)
            # Save password hint file for auto-unlock on restart (WSL lacks keychain)
            try:
                _pw_hint_file = VAULT_FILE.parent / ".vault_auto"  # noqa: F405
                if not use_pw:
                    _pw_hint_file.write_text("", encoding="utf-8")
                else:
                    # Store obfuscated pw for auto-unlock (local machine only)
                    import base64

                    _pw_hint_file.write_text(base64.b64encode(_vault_pw.encode()).decode(), encoding="utf-8")
                _pw_hint_file.chmod(0o600)
            except Exception as e:
                log.debug(f"Suppressed: {e}")
            audit_log("setup", f"vault created {'with' if use_pw else 'without'} password")
        except RuntimeError:
            # cryptography not installed and fallback not enabled —
            # proceed without vault; create a marker file so setup doesn't loop
            log.warning("[SETUP] Vault unavailable (no cryptography). Proceeding without encryption.")
            audit_log("setup", "vault skipped — no cryptography package")
            vault._data = {}
            vault._password = ""
            vault._salt = b"\x00" * 16
            # Write a marker so _needs_first_run() returns False next time
            try:
                VAULT_FILE.parent.mkdir(parents=True, exist_ok=True)  # noqa: F405
                VAULT_FILE.write_bytes(b'{"no_crypto": true}')  # noqa: F405
            except Exception as e:
                log.debug(f"Suppressed: {e}")
        self._json({"ok": True})
        return

    def _post_api_onboarding(self):
        """Post api onboarding."""
        try:
            return self._post_api_onboarding_inner()
        except Exception as e:
            log.exception(f"[ONBOARDING] Unhandled error: {e}")
            self._json({"error": f"Internal error: {str(e)[:200]}"}, 500)

    def _post_api_onboarding_inner(self):
        """Post api onboarding inner."""
        body = self._body
        if not vault.is_unlocked:
            if not _ensure_vault_unlocked(vault):
                self._json({"error": "Vault locked"}, 403)
                return
        # Save all provided API keys + Ollama URL
        saved = []
        for key in (
            "anthropic_api_key",
            "openai_api_key",
            "xai_api_key",
            "google_api_key",
            "brave_api_key",
            "openrouter_api_key",
        ):
            val = body.get(key, "").strip()
            if val:
                vault.set(key, val)
                saved.append(key.replace("_api_key", ""))
        dc_token = body.get("discord_token", "").strip()
        if dc_token:
            vault.set("discord_token", dc_token)
            saved.append("discord")
        ollama_url = body.get("ollama_url", "").strip()
        if ollama_url:
            vault.set("ollama_url", ollama_url)
            saved.append("ollama")
        ollama_key = body.get("ollama_api_key", "").strip()
        if ollama_key:
            vault.set("ollama_api_key", ollama_key)
            saved.append("ollama_key")
        # Test all provided keys
        from salmalm.core.llm import _http_post  # noqa: F811

        test_results = []
        if body.get("anthropic_api_key"):
            try:
                _http_post(
                    "https://api.anthropic.com/v1/messages",
                    {
                        "x-api-key": body["anthropic_api_key"],
                        "content-type": "application/json",
                        "anthropic-version": "2023-06-01",
                    },
                    {
                        "model": TEST_MODELS["anthropic"],
                        "max_tokens": 10,  # noqa: F405
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                    timeout=15,
                )
                test_results.append("✅ Anthropic OK")
            except Exception as e:
                test_results.append(f"⚠️ Anthropic: {str(e)[:80]}")
        if body.get("openai_api_key"):
            try:
                _http_post(
                    "https://api.openai.com/v1/chat/completions",
                    {
                        "Authorization": f"Bearer {body['openai_api_key']}",
                        "Content-Type": "application/json",
                    },
                    {
                        "model": TEST_MODELS["openai"],
                        "max_tokens": 10,  # noqa: F405
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                    timeout=15,
                )
                test_results.append("✅ OpenAI OK")
            except Exception as e:
                test_results.append(f"⚠️ OpenAI: {str(e)[:80]}")
        if body.get("xai_api_key"):
            try:
                _http_post(
                    "https://api.x.ai/v1/chat/completions",
                    {
                        "Authorization": f"Bearer {body['xai_api_key']}",
                        "Content-Type": "application/json",
                    },
                    {
                        "model": TEST_MODELS["xai"],
                        "max_tokens": 10,  # noqa: F405
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                    timeout=15,
                )
                test_results.append("✅ xAI OK")
            except Exception as e:
                test_results.append(f"⚠️ xAI: {str(e)[:80]}")
        if body.get("google_api_key"):
            try:
                import urllib.request

                gk = body["google_api_key"]
                req = urllib.request.Request(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{TEST_MODELS['google']}:generateContent?key={gk}",  # noqa: F405
                    data=json.dumps({"contents": [{"parts": [{"text": "ping"}]}]}).encode(),
                    headers={"Content-Type": "application/json"},
                )
                urllib.request.urlopen(req, timeout=15)
                test_results.append("✅ Google OK")
            except Exception as e:
                test_results.append(f"⚠️ Google: {str(e)[:80]}")
        if body.get("openrouter_api_key"):
            try:
                _http_post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    {
                        "Authorization": f"Bearer {body['openrouter_api_key']}",
                        "Content-Type": "application/json",
                    },
                    {
                        "model": "openai/gpt-4o-mini",
                        "max_tokens": 10,
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                    timeout=15,
                )
                test_results.append("✅ OpenRouter OK")
            except Exception as e:
                test_results.append(f"⚠️ OpenRouter: {str(e)[:80]}")
        audit_log("onboarding", f"keys: {', '.join(saved)}")
        # Auto-optimize routing based on available keys
        routing_config = {}
        try:
            from salmalm.core.model_selection import auto_optimize_and_save

            available_keys = []
            for key_name in ("anthropic_api_key", "openai_api_key", "xai_api_key", "google_api_key", "openrouter_api_key"):
                if vault.get(key_name):
                    available_keys.append(key_name)
            if available_keys:
                routing_config = auto_optimize_and_save(available_keys)
                log.info(f"[ONBOARDING] Auto-optimized routing: {routing_config}")
        except Exception as e:
            log.warning(f"[ONBOARDING] Auto-routing failed (ignored): {e}")
        test_result = " | ".join(test_results) if test_results else "Keys saved."
        # all_ok: True only when every tested key passed (no ⚠️ in any result)
        all_ok = not any("⚠️" in r for r in test_results)
        self._json({"ok": True, "saved": saved, "test_result": test_result, "all_ok": all_ok, "routing": routing_config})
        return

    def _post_api_onboarding_preferences(self):
        """Post api onboarding preferences."""
        body = self._body
        # Save model + persona preferences from setup wizard
        model = body.get("model", "auto")
        persona = body.get("persona", "expert")
        log.info(f"[SETUP] Onboarding preferences: model={model!r}, persona={persona!r}")
        if model and model != "auto":
            vault.set("default_model", model)
            log.info(f"[SETUP] Saved model to vault: {model}")
            # Also persist to router's model pref file so it takes effect immediately
            try:
                from salmalm.core.core import router
                router.set_force_model(model)
                log.info(f"[SETUP] Applied model to router: {model}, force_model={router.force_model}")
            except Exception as e:
                log.warning(f"[SETUP] Failed to set router model: {e}")
        # Write SOUL.md persona template
        persona_templates = {
            "expert": "# SOUL.md\n\nYou are a professional AI expert. Be precise, detail-oriented, and thorough in your responses. Use technical language when appropriate and always provide well-structured answers.",
            "friend": "# SOUL.md\n\nYou are a friendly and warm conversational partner. Be casual, use humor when appropriate, and make the user feel comfortable. Keep things light and engaging while still being helpful.",
            "assistant": "# SOUL.md\n\nYou are an efficient personal assistant. Be concise, task-focused, and proactive. Prioritize actionable information and minimize unnecessary verbosity.",
        }
        template = persona_templates.get(persona, persona_templates["expert"])
        try:
            soul_path = os.path.join(str(DATA_DIR), "SOUL.md")
            os.makedirs(os.path.dirname(soul_path), exist_ok=True)
            with open(soul_path, "w", encoding="utf-8") as f:
                f.write(template)
            log.info(f"[SETUP] SOUL.md written for persona={persona!r}")
        except Exception as e:
            log.debug(f"Suppressed: {e}")
        audit_log("onboarding", f"preferences: model={model}, persona={persona}")
        self._json({"ok": True})
        return


# ── FastAPI router ────────────────────────────────────────────────────────────
import asyncio as _asyncio
from fastapi import APIRouter as _APIRouter, Request as _Request, Depends as _Depends, Query as _Query
from fastapi.responses import JSONResponse as _JSON, Response as _Response, HTMLResponse as _HTML, StreamingResponse as _SR, RedirectResponse as _RR
from salmalm.web.fastapi_deps import require_auth as _auth, optional_auth as _optauth

router = _APIRouter()

@router.get("/api/onboarding")
async def get_onboarding():
    from salmalm.security.crypto import vault
    from salmalm.web.routes.web_setup import WebSetupMixin
    _result = {}
    class _H(WebSetupMixin):
        def _json(self, data, status=200): _result["d"] = data
    h = _H.__new__(_H)
    import types
    h._json = types.MethodType(_H._json, h)
    h._get_api_onboarding()
    return _JSON(content=_result.get("d", {}))

@router.get("/setup")
async def get_setup():
    from salmalm.web import templates as _tmpl
    return _HTML(content=_tmpl.ONBOARDING_HTML)

@router.post("/api/setup")
async def post_setup(request: _Request):
    import os, base64
    from salmalm.security.crypto import vault, log
    from salmalm.constants import VAULT_FILE
    from salmalm.core import audit_log
    body = await request.json()
    if VAULT_FILE.exists():
        return _JSON(content={"error": "Already set up"}, status_code=400)
    use_pw = body.get("use_password", False)
    pw = body.get("password", "")
    if use_pw and len(pw) < 4:
        return _JSON(content={"error": "Password must be at least 4 characters"}, status_code=400)
    try:
        _vault_pw = pw if use_pw else ""
        vault.create(_vault_pw)
        vault.unlock(_vault_pw, save_to_keychain=True)
        try:
            _pw_hint_file = VAULT_FILE.parent / ".vault_auto"
            if not use_pw:
                _pw_hint_file.write_text("", encoding="utf-8")
            else:
                _pw_hint_file.write_text(base64.b64encode(_vault_pw.encode()).decode(), encoding="utf-8")
            _pw_hint_file.chmod(0o600)
        except Exception as e:
            log.debug(f"Suppressed: {e}")
        audit_log("setup", f"vault created {'with' if use_pw else 'without'} password")
    except RuntimeError:
        log.warning("[SETUP] Vault unavailable (no cryptography). Proceeding without encryption.")
        audit_log("setup", "vault skipped — no cryptography package")
        vault._data = {}
        vault._password = ""
        vault._salt = b"\x00" * 16
        try:
            VAULT_FILE.parent.mkdir(parents=True, exist_ok=True)
            VAULT_FILE.write_bytes(b'{"no_crypto": true}')
        except Exception:
            pass
    return _JSON(content={"ok": True})

@router.post("/api/onboarding")
async def post_onboarding(request: _Request):
    from salmalm.web.routes.web_setup import WebSetupMixin, _ensure_vault_unlocked
    from salmalm.security.crypto import vault, log
    body = await request.json()
    _result = {}
    class _H(WebSetupMixin):
        @property
        def _body(self): return body
        def _json(self, data, status=200): _result["d"] = (data, status)
    h = _H.__new__(_H)
    import types
    h._json = types.MethodType(_H._json, h)
    h._body = body
    h._post_api_onboarding_inner()
    data, status = _result.get("d", ({}, 200))
    return _JSON(content=data, status_code=status)

@router.post("/api/onboarding/preferences")
async def post_onboarding_preferences(request: _Request):
    import os
    from salmalm.security.crypto import vault, log
    from salmalm.constants import DATA_DIR
    from salmalm.core import audit_log
    body = await request.json()
    model = body.get("model", "auto")
    persona = body.get("persona", "expert")
    if model and model != "auto":
        vault.set("default_model", model)
        try:
            from salmalm.core.core import router as _router
            _router.set_force_model(model)
        except Exception as e:
            log.warning(f"[SETUP] Failed to set router model: {e}")
    persona_templates = {
        "expert": "# SOUL.md\n\nYou are a professional AI expert. Be precise, detail-oriented, and thorough.",
        "friend": "# SOUL.md\n\nYou are a friendly and warm conversational partner. Be casual and engaging.",
        "assistant": "# SOUL.md\n\nYou are an efficient personal assistant. Be concise and task-focused.",
    }
    template = persona_templates.get(persona, persona_templates["expert"])
    try:
        soul_path = os.path.join(str(DATA_DIR), "SOUL.md")
        os.makedirs(os.path.dirname(soul_path), exist_ok=True)
        with open(soul_path, "w", encoding="utf-8") as f:
            f.write(template)
    except Exception as e:
        log.debug(f"Suppressed: {e}")
    audit_log("onboarding", f"preferences: model={model}, persona={persona}")
    return _JSON(content={"ok": True})
