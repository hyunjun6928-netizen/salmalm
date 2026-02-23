"""Setup & onboarding API — first run, setup wizard, onboarding flow."""

from salmalm.security.crypto import vault, log
import json
import os
from salmalm.constants import DATA_DIR, VAULT_FILE
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
        return not VAULT_FILE.exists() and not os.environ.get("SALMALM_VAULT_PW", "")  # noqa: F405

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
        audit_log("onboarding", f"keys: {', '.join(saved)}")
        # Auto-optimize routing based on available keys
        routing_config = {}
        try:
            from salmalm.core.model_selection import auto_optimize_and_save

            available_keys = []
            for key_name in ("anthropic_api_key", "openai_api_key", "xai_api_key", "google_api_key"):
                if vault.get(key_name):
                    available_keys.append(key_name)
            if available_keys:
                routing_config = auto_optimize_and_save(available_keys)
                log.info(f"[ONBOARDING] Auto-optimized routing: {routing_config}")
        except Exception as e:
            log.warning(f"[ONBOARDING] Auto-routing failed (ignored): {e}")
        test_result = " | ".join(test_results) if test_results else "Keys saved."
        self._json({"ok": True, "saved": saved, "test_result": test_result, "routing": routing_config})
        return

    def _post_api_onboarding_preferences(self):
        """Post api onboarding preferences."""
        body = self._body
        # Save model + persona preferences from setup wizard
        model = body.get("model", "auto")
        persona = body.get("persona", "expert")
        if model and model != "auto":
            vault.set("default_model", model)
        # Write SOUL.md persona template
        persona_templates = {
            "expert": "# SOUL.md\n\nYou are a professional AI expert. Be precise, detail-oriented, and thorough in your responses. Use technical language when appropriate and always provide well-structured answers.",
            "friend": "# SOUL.md\n\nYou are a friendly and warm conversational partner. Be casual, use humor when appropriate, and make the user feel comfortable. Keep things light and engaging while still being helpful.",
            "assistant": "# SOUL.md\n\nYou are an efficient personal assistant. Be concise, task-focused, and proactive. Prioritize actionable information and minimize unnecessary verbosity.",
        }
        template = persona_templates.get(persona, persona_templates["expert"])
        try:
            soul_path = os.path.join(str(DATA_DIR), "SOUL.md")
            if not os.path.exists(soul_path):
                os.makedirs(os.path.dirname(soul_path), exist_ok=True)
                with open(soul_path, "w", encoding="utf-8") as f:
                    f.write(template)
        except Exception as e:
            log.debug(f"Suppressed: {e}")
        audit_log("onboarding", f"preferences: model={model}, persona={persona}")
        self._json({"ok": True})
        return
