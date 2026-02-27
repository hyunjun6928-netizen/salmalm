"""User management API — list, delete, toggle, quota, settings, tenant config."""

from salmalm.security.crypto import vault
from salmalm.web.auth import auth_manager, extract_auth


class WebUsersMixin:
    GET_ROUTES = {
        "/api/users": "_get_api_users",
        "/api/users/quota": "_get_api_users_quota",
        "/api/users/settings": "_get_api_users_settings",
        "/api/tenant/config": "_get_api_tenant_config",
    }
    POST_ROUTES = {
        "/api/users/delete": "_post_api_users_delete",
        "/api/users/toggle": "_post_api_users_toggle",
        "/api/users/quota/set": "_post_api_users_quota_set",
        "/api/users/settings": "_post_api_users_settings",
        "/api/tenant/config": "_post_api_tenant_config",
    }

    """Mixin providing users route handlers."""

    def _get_api_users(self):
        # Admin: full user list with stats (멀티테넌트 사용자 관리)
        """Get api users."""
        user = extract_auth(dict(self.headers))
        if not user:
            ip = self._get_client_ip()
            if ip in ("127.0.0.1", "::1", "localhost") and vault.is_unlocked:
                user = {"username": "local", "role": "admin", "id": 0}
        if not user or user.get("role") != "admin":
            self._json({"error": "Admin access required"}, 403)
        else:
            from salmalm.features.users import user_manager

            self._json(
                {
                    "users": user_manager.get_all_users_with_stats(),
                    "multi_tenant": user_manager.multi_tenant_enabled,
                    "registration_mode": user_manager.get_registration_mode(),
                }
            )

    def _get_api_users_quota(self):
        # Get own quota (사용량 확인)
        """Get api users quota."""
        user = extract_auth(dict(self.headers))
        if not user:
            self._json({"error": "Authentication required"}, 401)
        else:
            from salmalm.features.users import user_manager

            uid = user.get("uid") or user.get("id", 0)
            quota = user_manager.get_quota(uid)
            self._json({"quota": quota})

    def _get_api_users_settings(self):
        # Get own settings
        """Get api users settings."""
        user = extract_auth(dict(self.headers))
        if not user:
            self._json({"error": "Authentication required"}, 401)
        else:
            from salmalm.features.users import user_manager

            uid = user.get("uid") or user.get("id", 0)
            settings = user_manager.get_user_settings(uid)
            self._json({"settings": settings})

    def _get_api_tenant_config(self):
        # Admin: get multi-tenant config
        """Get api tenant config."""
        user = extract_auth(dict(self.headers))
        if not user or user.get("role") != "admin":
            self._json({"error": "Admin access required"}, 403)
        else:
            from salmalm.features.users import user_manager

            self._json(
                {
                    "multi_tenant": user_manager.multi_tenant_enabled,
                    "registration_mode": user_manager.get_registration_mode(),
                    "telegram_allowlist": user_manager.get_telegram_allowlist_mode(),
                }
            )

    def _post_api_users_delete(self):
        """Post api users delete."""
        body = self._body
        requester = extract_auth(dict(self.headers))
        if not requester or requester.get("role") != "admin":
            self._json({"error": "Admin access required"}, 403)
            return
        uid = body.get("user_id")
        username = body.get("username", "")
        if username:
            ok = auth_manager.delete_user(username)
        elif uid:
            from salmalm.features.users import user_manager

            u = user_manager.get_user_by_id(uid)
            ok = auth_manager.delete_user(u["username"]) if u else False
        else:
            self._json({"error": "user_id or username required"}, 400)
            return
        self._json({"ok": ok})
        return

    def _post_api_users_toggle(self):
        """Post api users toggle."""
        body = self._body
        # Enable/disable user (admin only)
        requester = extract_auth(dict(self.headers))
        if not requester or requester.get("role") != "admin":
            self._json({"error": "Admin access required"}, 403)
            return
        from salmalm.features.users import user_manager

        uid = body.get("user_id")
        enabled = body.get("enabled", True)
        if not uid:
            self._json({"error": "user_id required"}, 400)
            return
        ok = user_manager.toggle_user(uid, enabled)
        self._json({"ok": ok})
        return

    def _post_api_users_quota_set(self):
        """Post api users quota set."""
        body = self._body
        # Set user quota (admin only)
        requester = extract_auth(dict(self.headers))
        if not requester or requester.get("role") != "admin":
            self._json({"error": "Admin access required"}, 403)
            return
        from salmalm.features.users import user_manager

        uid = body.get("user_id")
        if not uid:
            self._json({"error": "user_id required"}, 400)
            return
        user_manager.set_quota(
            uid,
            daily_limit=body.get("daily_limit"),
            monthly_limit=body.get("monthly_limit"),
        )
        self._json({"ok": True, "quota": user_manager.get_quota(uid)})
        return

    def _post_api_users_settings(self):
        """Post api users settings."""
        body = self._body
        # Update own settings
        user = extract_auth(dict(self.headers))
        if not user:
            self._json({"error": "Authentication required"}, 401)
            return
        from salmalm.features.users import user_manager

        uid = user.get("uid") or user.get("id", 0)
        allowed_keys = ("model_preference", "persona", "tts_enabled", "tts_voice")
        updates = {k: v for k, v in body.items() if k in allowed_keys}
        if updates:
            user_manager.set_user_settings(uid, **updates)
        self._json({"ok": True, "settings": user_manager.get_user_settings(uid)})
        return

    def _post_api_tenant_config(self):
        """Post api tenant config."""
        body = self._body
        # Admin: update multi-tenant config
        requester = extract_auth(dict(self.headers))
        if not requester or requester.get("role") != "admin":
            self._json({"error": "Admin access required"}, 403)
            return
        from salmalm.features.users import user_manager

        if "multi_tenant" in body:
            user_manager.enable_multi_tenant(body["multi_tenant"])
        if "registration_mode" in body:
            user_manager.set_registration_mode(body["registration_mode"])
        if "telegram_allowlist" in body:
            user_manager.set_telegram_allowlist_mode(body["telegram_allowlist"])
        self._json({"ok": True})
        return


# ── FastAPI router ────────────────────────────────────────────────────────────
import asyncio as _asyncio
from fastapi import APIRouter as _APIRouter, Request as _Request, Depends as _Depends, Query as _Query
from fastapi.responses import JSONResponse as _JSON, Response as _Response, HTMLResponse as _HTML, StreamingResponse as _SR, RedirectResponse as _RR
from salmalm.web.fastapi_deps import require_auth as _auth, optional_auth as _optauth
from salmalm.web.schemas import UserCreate, UserResponse, SuccessResponse

router = _APIRouter()

@router.get("/api/users")
async def get_users(request: _Request):
    from salmalm.web.auth import extract_auth
    from salmalm.security.crypto import vault
    user = extract_auth(dict(request.headers))
    if not user:
        ip = request.client.host if request.client else ""
        if ip in ("127.0.0.1", "::1", "localhost") and vault.is_unlocked:
            user = {"username": "local", "role": "admin", "id": 0}
    if not user or user.get("role") != "admin":
        return _JSON(content={"error": "Admin access required"}, status_code=403)
    from salmalm.features.users import user_manager
    return _JSON(content={"users": user_manager.get_all_users_with_stats(),
                          "multi_tenant": user_manager.multi_tenant_enabled,
                          "registration_mode": user_manager.get_registration_mode()})

@router.get("/api/users/quota")
async def get_users_quota(_u=_Depends(_auth)):
    from salmalm.features.users import user_manager
    uid = _u.get("uid") or _u.get("id", 0)
    return _JSON(content={"quota": user_manager.get_quota(uid)})

@router.get("/api/users/settings")
async def get_users_settings(_u=_Depends(_auth)):
    from salmalm.features.users import user_manager
    uid = _u.get("uid") or _u.get("id", 0)
    return _JSON(content={"settings": user_manager.get_user_settings(uid)})

@router.get("/api/tenant/config")
async def get_tenant_config(_u=_Depends(_auth)):
    if _u.get("role") != "admin":
        return _JSON(content={"error": "Admin access required"}, status_code=403)
    from salmalm.features.users import user_manager
    return _JSON(content={"multi_tenant": user_manager.multi_tenant_enabled,
                          "registration_mode": user_manager.get_registration_mode(),
                          "telegram_allowlist": user_manager.get_telegram_allowlist_mode()})

@router.post("/api/users/delete")
async def post_users_delete(request: _Request, _u=_Depends(_auth)):
    from salmalm.web.auth import auth_manager
    if _u.get("role") != "admin":
        return _JSON(content={"error": "Admin access required"}, status_code=403)
    body = await request.json()
    uid = body.get("user_id")
    username = body.get("username", "")
    if username:
        ok = auth_manager.delete_user(username)
    elif uid:
        from salmalm.features.users import user_manager
        u = user_manager.get_user_by_id(uid)
        ok = auth_manager.delete_user(u["username"]) if u else False
    else:
        return _JSON(content={"error": "user_id or username required"}, status_code=400)
    return _JSON(content={"ok": ok})

@router.post("/api/users/toggle")
async def post_users_toggle(request: _Request, _u=_Depends(_auth)):
    if _u.get("role") != "admin":
        return _JSON(content={"error": "Admin access required"}, status_code=403)
    from salmalm.features.users import user_manager
    body = await request.json()
    uid = body.get("user_id")
    enabled = body.get("enabled", True)
    if not uid:
        return _JSON(content={"error": "user_id required"}, status_code=400)
    return _JSON(content={"ok": user_manager.toggle_user(uid, enabled)})

@router.post("/api/users/quota/set")
async def post_users_quota_set(request: _Request, _u=_Depends(_auth)):
    if _u.get("role") != "admin":
        return _JSON(content={"error": "Admin access required"}, status_code=403)
    from salmalm.features.users import user_manager
    body = await request.json()
    uid = body.get("user_id")
    if not uid:
        return _JSON(content={"error": "user_id required"}, status_code=400)
    user_manager.set_quota(uid, daily_limit=body.get("daily_limit"), monthly_limit=body.get("monthly_limit"))
    return _JSON(content={"ok": True, "quota": user_manager.get_quota(uid)})

@router.post("/api/users/settings")
async def post_users_settings(request: _Request, _u=_Depends(_auth)):
    from salmalm.features.users import user_manager
    body = await request.json()
    uid = _u.get("uid") or _u.get("id", 0)
    allowed_keys = ("model_preference", "persona", "tts_enabled", "tts_voice")
    updates = {k: v for k, v in body.items() if k in allowed_keys}
    if updates:
        user_manager.set_user_settings(uid, **updates)
    return _JSON(content={"ok": True, "settings": user_manager.get_user_settings(uid)})

@router.post("/api/tenant/config")
async def post_tenant_config(request: _Request, _u=_Depends(_auth)):
    if _u.get("role") != "admin":
        return _JSON(content={"error": "Admin access required"}, status_code=403)
    from salmalm.features.users import user_manager
    body = await request.json()
    if "multi_tenant" in body:
        user_manager.enable_multi_tenant(body["multi_tenant"])
    if "registration_mode" in body:
        user_manager.set_registration_mode(body["registration_mode"])
    if "telegram_allowlist" in body:
        user_manager.set_telegram_allowlist_mode(body["telegram_allowlist"])
    return _JSON(content={"ok": True})
