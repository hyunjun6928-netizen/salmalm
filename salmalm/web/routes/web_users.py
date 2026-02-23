"""User management API — list, delete, toggle, quota, settings, tenant config."""



from salmalm.security.crypto import vault, log
from salmalm.web.auth import auth_manager, extract_auth


class WebUsersMixin:
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

