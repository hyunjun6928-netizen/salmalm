"""Sub-agent REST API — list, spawn, detail, steer, kill, clear."""


class WebSubagentsMixin:
    GET_ROUTES = {
        "/api/subagents": "_get_subagents",
    }
    GET_PREFIX_ROUTES = [
        ("/api/subagents/", "_get_subagent_detail", None),
    ]
    POST_ROUTES = {
        "/api/subagents": "_post_spawn_subagent",
        "/api/subagents/clear": "_post_clear_subagents",
    }
    POST_PREFIX_ROUTES = [
        ("/api/subagents/", "_post_subagent_action", None),
    ]

    # ── GET ───────────────────────────────────────────────────────────────

    def _get_subagents(self):
        """GET /api/subagents — list all tasks (summary, no messages)."""
        if not self._require_auth("user"):
            return
        from salmalm.features.subagents import subagent_manager
        self._json({"tasks": subagent_manager.list_tasks()})

    def _get_subagent_detail(self):
        """GET /api/subagents/<id> — task + full message history."""
        if not self._require_auth("user"):
            return
        task_id = self.path.rstrip("/").split("/")[-1]
        from salmalm.features.subagents import subagent_manager
        task = subagent_manager.get_task(task_id)
        if not task:
            self._json({"error": f"Task {task_id} not found"}, 404)
            return
        self._json({"task": task.to_dict(include_messages=True)})

    # ── POST ──────────────────────────────────────────────────────────────

    def _post_spawn_subagent(self):
        """POST /api/subagents — spawn a new sub-agent."""
        if not self._require_auth("user"):
            return
        body = self._body
        description = (body.get("description") or "").strip()
        if not description:
            self._json({"error": "description required"}, 400)
            return
        from salmalm.features.subagents import subagent_manager
        task = subagent_manager.spawn(
            description=description,
            model=body.get("model") or None,
            thinking_level=body.get("thinking_level") or None,
            label=(body.get("label") or "").strip() or None,
            max_turns=int(body.get("max_turns", 10)),
            timeout_s=int(body.get("timeout_s", 300)),
            parent_session=body.get("parent_session", "web"),
        )
        self._json({"task": task.to_dict()})

    def _post_subagent_action(self):
        """POST /api/subagents/<id>/steer|kill — dynamic sub-routes."""
        if not self._require_auth("user"):
            return
        # path: /api/subagents/<id>/steer  or  /api/subagents/<id>/kill
        parts = [p for p in self.path.rstrip("/").split("/") if p]
        # parts: ['api', 'subagents', '<id>', 'steer']
        if len(parts) < 4:
            self._json({"error": "Not found"}, 404)
            return
        task_id = parts[2]
        action = parts[3]
        from salmalm.features.subagents import subagent_manager
        if action == "steer":
            message = (self._body.get("message") or "").strip()
            if not message:
                self._json({"error": "message required"}, 400)
                return
            result = subagent_manager.steer(task_id, message)
            self._json({"ok": True, "result": result})
        elif action == "kill":
            result = subagent_manager.kill(task_id)
            self._json({"ok": True, "result": result})
        else:
            self._json({"error": f"Unknown action: {action}"}, 404)

    def _post_clear_subagents(self):
        """POST /api/subagents/clear — remove completed/failed tasks."""
        if not self._require_auth("user"):
            return
        from salmalm.features.subagents import subagent_manager
        count = subagent_manager.clear_completed()
        self._json({"ok": True, "removed": count})
