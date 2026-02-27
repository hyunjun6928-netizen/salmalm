"""Authentication endpoints — login, register, unlock, Google OAuth."""

import json
import os
import secrets
import time

from salmalm.security.crypto import vault, log
from salmalm.web.auth import rate_limiter, RateLimitExceeded  # noqa: F401
from salmalm.constants import VAULT_FILE
from salmalm.core import audit_log
from salmalm.web.auth import auth_manager, extract_auth


class WebAuthMixin:
    GET_ROUTES = {
        "/api/auth/users": "_get_api_auth_users",
        "/api/google/auth": "_get_api_google_auth",
    }
    POST_ROUTES = {
        "/api/users/register": "_post_api_users_register",
        "/api/auth/login": "_post_api_auth_login",
        "/api/auth/register": "_post_api_auth_register",
        "/api/unlock": "_post_api_unlock",
        "/api/auto-unlock": "_post_api_auto_unlock",
    }

    """Mixin providing auth route handlers."""

    def _auto_unlock_localhost(self) -> bool:
        """Auto-unlock vault for localhost connections.

        Priority: OS keychain → env var (deprecated) → empty password → prompt.
        """
        if vault.is_unlocked:
            return True
        ip = self._get_client_ip()
        if ip not in ("127.0.0.1", "::1", "localhost"):
            return False
        # 1. Try OS keychain first (most secure)
        if vault.try_keychain_unlock():
            return True
        # 1b. Try .vault_auto file (WSL/no-keychain fallback)
        try:
            _pw_hint_file = VAULT_FILE.parent / ".vault_auto"  # noqa: F405
            if _pw_hint_file.exists():
                _hint = _pw_hint_file.read_text(encoding="utf-8").strip()
                if _hint:
                    # Try base64 first, fall back to plain text
                    import base64
                    try:
                        _auto_pw = base64.b64decode(_hint).decode()
                    except Exception:
                        _auto_pw = _hint  # Plain text fallback
                else:
                    _auto_pw = ""
                if vault.unlock(_auto_pw, save_to_keychain=True):
                    return True
        except Exception as e:
            log.debug(f"Suppressed: {e}")
        pw = os.environ.get("SALMALM_VAULT_PW", "")
        if pw:
            import warnings

            warnings.warn(
                "SALMALM_VAULT_PW env var is deprecated and will be removed in v1.0. "
                "Use OS keychain instead: vault password is auto-saved on first unlock.",
                FutureWarning,
                stacklevel=2,
            )
        if VAULT_FILE.exists():  # noqa: F405
            # Check if this is a no-crypto marker file
            try:
                marker = VAULT_FILE.read_bytes()  # noqa: F405
                if b"no_crypto" in marker:
                    vault._data = {}
                    vault._password = ""
                    vault._salt = b"\x00" * 16
                    return True
            except Exception as e:
                log.debug(f"Suppressed: {e}")
            # 2. Try env password (deprecated), then empty password
            try:
                if pw and vault.unlock(pw, save_to_keychain=True):
                    return True
                if vault.unlock(""):
                    return True  # No-password vault
            except RuntimeError:
                log.warning("Vault unlock failed (cryptography not installed?)")
                return False
            if not pw:
                return False  # Has password but no env var — show unlock screen
            return False
        else:
            # No vault file — auto-create from .vault_auto or env pw
            _auto_pw = ""
            try:
                _pw_hint_file = VAULT_FILE.parent / ".vault_auto"  # noqa: F405
                if _pw_hint_file.exists():
                    _hint = _pw_hint_file.read_text(encoding="utf-8").strip()
                    if _hint:
                        import base64 as _b64
                        try:
                            _auto_pw = _b64.b64decode(_hint).decode()
                        except Exception:
                            _auto_pw = _hint
                elif pw:
                    _auto_pw = pw
            except Exception as e:
                log.debug(f"Suppressed: {e}")
            try:
                vault.create(_auto_pw)
                vault.unlock(_auto_pw, save_to_keychain=True)
                log.info("[UNLOCK] Vault auto-created and unlocked from localhost")
                return True
            except RuntimeError as e:
                log.warning(f"Vault create failed: {e}")
                return False
        # No vault file, no env var → first run, handled by _needs_first_run
        return True

    def _get_api_auth_users(self):
        """Get api auth users."""
        user = extract_auth(dict(self.headers))
        if not user or user.get("role") != "admin":
            self._json({"error": "Admin access required"}, 403)
        else:
            self._json({"users": auth_manager.list_users()})

    def _get_api_google_auth(self):
        """Get api google auth."""
        if not self._require_auth("user"):
            return
        client_id = vault.get("google_client_id") or ""
        if not client_id:
            self._json(
                {"error": "Set google_client_id in vault first (Settings > Vault)"},
                400,
            )
            return
        import urllib.parse

        import os as _os
        port = getattr(getattr(self, "server", None), "server_address", [None, None])[1] or int(_os.environ.get("SALMALM_PORT", 18800))
        redirect_uri = f"http://localhost:{port}/api/google/callback"
        # CSRF protection: generate and store state token
        state = secrets.token_urlsafe(32)
        from salmalm.web.web import _google_oauth_pending_states

        _google_oauth_pending_states[state] = time.time()
        # Cleanup stale states on every new auth attempt (prevent unbounded growth)
        _cutoff = time.time() - 900
        for _k in [k for k, v in _google_oauth_pending_states.items() if v < _cutoff]:
            _google_oauth_pending_states.pop(_k, None)
        params = urllib.parse.urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "https://www.googleapis.com/auth/gmail.modify https://www.googleapis.com/auth/calendar",
                "access_type": "offline",
                "prompt": "consent",
                "state": state,
            }
        )
        url = f"https://accounts.google.com/o/oauth2/v2/auth?{params}"
        self.send_response(302)
        self.send_header("Location", url)
        self.end_headers()

    def _post_api_users_register(self):
        """Post api users register."""
        body = self._body
        # Register new user (admin or open registration)
        from salmalm.features.users import user_manager

        requester = extract_auth(dict(self.headers))
        reg_mode = user_manager.get_registration_mode()
        if reg_mode == "admin_only":
            if not requester or requester.get("role") != "admin":
                self._json(
                    {"error": "Admin access required for registration / 관리자만 등록 가능"},
                    403,
                )
                return
        try:
            user = auth_manager.create_user(
                body.get("username", ""),
                body.get("password", ""),
                body.get("role", "user"),
            )
            user_manager.ensure_quota(user["id"])
            self._json({"ok": True, "user": user})
        except ValueError as e:
            self._json({"error": str(e)}, 400)
        return

    def _post_api_auth_login(self):
        """Post api auth login."""
        body = self._body
        username = body.get("username", "")
        password = body.get("password", "")
        user = auth_manager.authenticate(username, password)
        if user:
            token = auth_manager.create_token(user)
            audit_log(
                "auth_success",
                f"user={username}",
                detail_dict={"username": username, "ip": self._get_client_ip()},
            )
            self._json({"ok": True, "token": token, "user": user})
        else:
            audit_log(
                "auth_failure",
                f"user={username}",
                detail_dict={"username": username, "ip": self._get_client_ip()},
            )
            self._json({"error": "Invalid credentials"}, 401)
        return

    def _post_api_auth_register(self):
        """Post api auth register."""
        body = self._body
        requester = extract_auth(dict(self.headers))
        if not requester or requester.get("role") != "admin":
            self._json({"error": "Admin access required"}, 403)
            return
        try:
            user = auth_manager.create_user(
                body.get("username", ""),
                body.get("password", ""),
                body.get("role", "user"),
            )
            self._json({"ok": True, "user": user})
        except ValueError as e:
            self._json({"error": str(e)}, 400)
        return

    def _post_api_auto_unlock(self):
        """Auto-unlock vault from .vault_auto — called by unlock page on load."""
        if vault.is_unlocked:
            token = secrets.token_hex(32)
            self._json({"ok": True, "token": token})
            return
        ip = self._get_client_ip()
        if ip not in ("127.0.0.1", "::1", "localhost"):
            self._json({"ok": False}, 401)
            return
        # Try auto-unlock
        if self._auto_unlock_localhost():
            audit_log("unlock", "vault auto-unlocked from page load")
            token = secrets.token_hex(32)
            self._json({"ok": True, "token": token})
            return
        # Auto-unlock failed — do NOT destroy vault data.
        # Prompt the user to unlock manually via the web UI.
        log.warning("[VAULT] Auto-unlock failed — showing manual unlock screen")
        self._json({"ok": False}, 401)

    def _post_api_unlock(self):
        """Post api unlock."""
        body = self._body
        password = body.get("password", "")
        if VAULT_FILE.exists():  # noqa: F405
            ok = vault.unlock(password, save_to_keychain=True)
        else:
            vault.create(password, save_to_keychain=True)
            ok = True
        if ok:
            audit_log("unlock", "vault unlocked")
            token = secrets.token_hex(32)
            self._json({"ok": True, "token": token})
        else:
            audit_log("unlock_fail", "wrong password")
            self._json({"ok": False, "error": "Wrong password"}, 401)

    def _security_headers(self):
        """Add security headers to all responses.

        CSP defaults to nonce-based script-src (strict mode).
        Set SALMALM_CSP_COMPAT=1 to fall back to 'unsafe-inline' for compatibility.
        """
        self._csp_nonce = secrets.token_urlsafe(16)

        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(self), geolocation=()")
        # CSP: unsafe-inline by default (setup/unlock templates use inline scripts).
        # Set SALMALM_CSP_STRICT=1 to use nonce-based script-src instead.
        if os.environ.get("SALMALM_CSP_STRICT"):
            script_src = f"'self' 'nonce-{self._csp_nonce}'"
        else:
            script_src = "'self' 'unsafe-inline'"
        self.send_header(
            "Content-Security-Policy",
            f"default-src 'self'; "
            f"script-src {script_src}; "
            f"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://fonts.gstatic.com; "
            f"img-src 'self' data: blob:; "
            f"connect-src 'self' ws://127.0.0.1:* ws://localhost:* wss://127.0.0.1:* wss://localhost:*; "
            f"font-src 'self' data: https://fonts.gstatic.com; "
            f"object-src 'none'; "
            f"base-uri 'self'; "
            f"form-action 'self'",
        )

    def _check_rate_limit(self) -> bool:
        """Check rate limit. Returns True if OK, sends 429 if exceeded."""
        ip = self._get_client_ip()
        user = extract_auth(dict(self.headers))
        # Loopback admin bypass: only when server is bound to 127.0.0.1 (not 0.0.0.0)
        _bind = os.environ.get("SALMALM_BIND", "127.0.0.1")
        if (
            not user
            and ip in ("127.0.0.1", "::1", "localhost")
            and vault.is_unlocked
            and _bind in ("127.0.0.1", "::1", "localhost")
        ):
            user = {"username": "local", "role": "admin"}
        role = user.get("role", "anonymous") if user else "anonymous"
        key = user.get("username", ip) if user else ip
        try:
            rate_limiter.check(key, role)
            return True
        except RateLimitExceeded as e:
            self.send_response(429)
            self.send_header("Retry-After", str(int(e.retry_after)))
            self._cors()
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Rate limit exceeded", "retry_after": e.retry_after}).encode())
            return False


# ── FastAPI router ────────────────────────────────────────────────────────────
import asyncio as _asyncio
from fastapi import APIRouter as _APIRouter, Request as _Request, Depends as _Depends, Query as _Query
from fastapi.responses import JSONResponse as _JSON, Response as _Response, HTMLResponse as _HTML, StreamingResponse as _SR, RedirectResponse as _RR
from salmalm.web.fastapi_deps import require_auth as _auth, optional_auth as _optauth

from salmalm.web.schemas import LoginRequest, UnlockRequest, UserCreate

router = _APIRouter()

@router.get("/api/auth/users")
async def get_auth_users(request: _Request):
    from salmalm.web.auth import extract_auth, auth_manager
    user = extract_auth(dict(request.headers))
    if not user or user.get("role") != "admin":
        return _JSON(content={"error": "Admin access required"}, status_code=403)
    return _JSON(content={"users": auth_manager.list_users()})

@router.get("/api/google/auth")
async def get_google_auth(request: _Request, _u=_Depends(_auth)):
    import secrets, time, urllib.parse
    from salmalm.security.crypto import vault
    from salmalm.web.web import _google_oauth_pending_states
    import os as _os
    client_id = vault.get("google_client_id") or ""
    if not client_id:
        return _JSON(content={"error": "Set google_client_id in vault first (Settings > Vault)"}, status_code=400)
    port = int(_os.environ.get("SALMALM_PORT", 18800))
    redirect_uri = f"http://localhost:{port}/api/google/callback"
    state = secrets.token_urlsafe(32)
    _google_oauth_pending_states[state] = time.time()
    _cutoff = time.time() - 900
    for _k in [k for k, v in _google_oauth_pending_states.items() if v < _cutoff]:
        _google_oauth_pending_states.pop(_k, None)
    params = urllib.parse.urlencode({"client_id": client_id, "redirect_uri": redirect_uri,
        "response_type": "code", "scope": "https://www.googleapis.com/auth/gmail.modify https://www.googleapis.com/auth/calendar",
        "access_type": "offline", "prompt": "consent", "state": state})
    url = f"https://accounts.google.com/o/oauth2/v2/auth?{params}"
    return _RR(url=url, status_code=302)

@router.post("/api/users/register")
async def post_users_register(req: UserCreate, request: _Request):
    from salmalm.web.auth import extract_auth, auth_manager
    from salmalm.features.users import user_manager
    requester = extract_auth(dict(request.headers))
    reg_mode = user_manager.get_registration_mode()
    if reg_mode == "admin_only":
        if not requester or requester.get("role") != "admin":
            return _JSON(content={"error": "Admin access required for registration / 관리자만 등록 가능"}, status_code=403)
    try:
        user = auth_manager.create_user(req.username, req.password, req.role)
        user_manager.ensure_quota(user["id"])
        return _JSON(content={"ok": True, "user": user})
    except ValueError as e:
        return _JSON(content={"error": str(e)}, status_code=400)

@router.post("/api/auth/login")
async def post_auth_login(req: LoginRequest, request: _Request):
    from salmalm.web.auth import auth_manager
    from salmalm.core import audit_log
    username = req.username
    password = req.password
    user = auth_manager.authenticate(username, password)
    ip = request.client.host if request.client else "unknown"
    if user:
        token = auth_manager.create_token(user)
        audit_log("auth_success", f"user={username}", detail_dict={"username": username, "ip": ip})
        return _JSON(content={"ok": True, "token": token, "user": user})
    else:
        audit_log("auth_failure", f"user={username}", detail_dict={"username": username, "ip": ip})
        return _JSON(content={"error": "Invalid credentials"}, status_code=401)

@router.post("/api/auth/register")
async def post_auth_register(req: UserCreate, request: _Request):
    from salmalm.web.auth import extract_auth, auth_manager
    requester = extract_auth(dict(request.headers))
    if not requester or requester.get("role") != "admin":
        return _JSON(content={"error": "Admin access required"}, status_code=403)
    try:
        user = auth_manager.create_user(req.username, req.password, req.role)
        return _JSON(content={"ok": True, "user": user})
    except ValueError as e:
        return _JSON(content={"error": str(e)}, status_code=400)

@router.post("/api/unlock")
async def post_unlock(req: UnlockRequest):
    from salmalm.security.crypto import vault
    from salmalm.constants import VAULT_FILE
    from salmalm.core import audit_log
    import secrets
    password = req.password
    if VAULT_FILE.exists():
        ok = vault.unlock(password, save_to_keychain=True)
    else:
        vault.create(password, save_to_keychain=True)
        ok = True
    if ok:
        audit_log("unlock", "vault unlocked")
        return _JSON(content={"ok": True, "token": secrets.token_hex(32)})
    else:
        audit_log("unlock_fail", "wrong password")
        return _JSON(content={"ok": False, "error": "Wrong password"}, status_code=401)

@router.post("/api/auto-unlock")
async def post_auto_unlock(request: _Request):
    from salmalm.security.crypto import vault
    from salmalm.core import audit_log
    import secrets
    if vault.is_unlocked:
        return _JSON(content={"ok": True, "token": secrets.token_hex(32)})
    ip = request.client.host if request.client else "unknown"
    if ip not in ("127.0.0.1", "::1", "localhost"):
        return _JSON(content={"ok": False}, status_code=401)
    # Try auto-unlock via vault keychain/file
    if vault.try_keychain_unlock():
        audit_log("unlock", "vault auto-unlocked")
        return _JSON(content={"ok": True, "token": secrets.token_hex(32)})
    from salmalm.constants import VAULT_FILE
    import os
    try:
        _pw_hint_file = VAULT_FILE.parent / ".vault_auto"
        if _pw_hint_file.exists():
            _hint = _pw_hint_file.read_text(encoding="utf-8").strip()
            import base64
            try:
                _auto_pw = base64.b64decode(_hint).decode()
            except Exception:
                _auto_pw = _hint
            if vault.unlock(_auto_pw, save_to_keychain=True):
                audit_log("unlock", "vault auto-unlocked from page load")
                return _JSON(content={"ok": True, "token": secrets.token_hex(32)})
    except Exception:
        pass
    pw = os.environ.get("SALMALM_VAULT_PW", "")
    if pw and vault.unlock(pw, save_to_keychain=True):
        audit_log("unlock", "vault auto-unlocked from page load")
        return _JSON(content={"ok": True, "token": secrets.token_hex(32)})
    if VAULT_FILE.exists() and vault.unlock(""):
        audit_log("unlock", "vault auto-unlocked (no password)")
        return _JSON(content={"ok": True, "token": secrets.token_hex(32)})
    return _JSON(content={"ok": False}, status_code=401)
