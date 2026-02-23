"""SalmAlm Web — WebFilesMixin routes."""


class WebFilesMixin:
    """Mixin for web_files routes."""

    def _post_api_agent_import_preview(self):
        """Post api agent import preview."""
        if not self._require_auth("user"):
            return
        # Read multipart file
        import zipfile
        import io
        import json as _json

        content_type = self.headers.get("Content-Type", "")
        if "multipart" not in content_type:
            self._json({"ok": False, "error": "Expected multipart upload"}, 400)
            return
        content_length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(content_length)
        # Find ZIP in multipart
        boundary = content_type.split("boundary=")[1].encode() if "boundary=" in content_type else b""
        parts = raw.split(b"--" + boundary)
        zip_data = None
        for part in parts:
            if b"filename=" in part:
                body_start = part.find(b"\r\n\r\n")
                if body_start > 0:
                    zip_data = part[body_start + 4 :]
                    if zip_data.endswith(b"\r\n"):
                        zip_data = zip_data[:-2]
                    break
        if not zip_data:
            self._json({"ok": False, "error": "No ZIP file found"}, 400)
            return
        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_data))
            manifest = _json.loads(zf.read("manifest.json")) if "manifest.json" in zf.namelist() else {}
            preview = {
                "files": zf.namelist(),
                "manifest": manifest,
                "size": len(zip_data),
            }
            self._json({"ok": True, "preview": preview})
        except Exception as e:
            self._json({"ok": False, "error": str(e)}, 400)

    def _post_api_upload(self):
        """Post api upload."""
        length = self._content_length
        if not vault.is_unlocked:
            self._json({"error": "Vault locked"}, 403)
            return
        # Parse multipart form data
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self._json({"error": "multipart required"}, 400)
            return
        try:
            raw = self.rfile.read(length)
            # Parse multipart using stdlib email.parser (robust edge-case handling)
            import email.parser
            import email.policy

            header_bytes = f"Content-Type: {content_type}\r\n\r\n".encode()
            msg = email.parser.BytesParser(policy=email.policy.compat32).parsebytes(header_bytes + raw)
            for part in msg.walk():
                fname_raw = part.get_filename()
                if not fname_raw:
                    continue
                fname = Path(fname_raw).name  # basename only (prevent path traversal)
                # Reject suspicious filenames
                if not fname or ".." in fname or not re.match(r"^[\w.\- ]+$", fname):
                    self._json({"error": "Invalid filename"}, 400)
                    return
                # Validate file type (Open WebUI style)
                from salmalm.features.edge_cases import validate_upload

                ok, err = validate_upload(fname, len(part.get_payload(decode=True) or b""))
                if not ok:
                    self._json({"error": err}, 400)
                    return
                file_data = part.get_payload(decode=True)
                if not file_data:
                    continue
                # Size limit: 50MB
                if len(file_data) > 50 * 1024 * 1024:
                    self._json({"error": "File too large (max 50MB)"}, 413)
                    return
                # Save
                save_dir = WORKSPACE_DIR / "uploads"  # noqa: F405
                save_dir.mkdir(exist_ok=True)
                save_path = save_dir / fname
                save_path.write_bytes(file_data)  # type: ignore[arg-type]
                size_kb = len(file_data) / 1024
                is_image = any(
                    fname.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
                )
                is_text = any(
                    fname.lower().endswith(ext)
                    for ext in (
                        ".txt",
                        ".md",
                        ".py",
                        ".js",
                        ".json",
                        ".csv",
                        ".log",
                        ".html",
                        ".css",
                        ".sh",
                        ".bat",
                        ".yaml",
                        ".yml",
                        ".xml",
                        ".sql",
                    )
                )
                is_pdf = fname.lower().endswith(".pdf")
                info = f"[{'🖼️ Image' if is_image else '📎 File'} uploaded: uploads/{fname} ({size_kb:.1f}KB)]"
                if is_pdf:
                    # PDF text extraction (Open WebUI style)
                    try:
                        from salmalm.features.edge_cases import process_uploaded_file

                        info = process_uploaded_file(fname, file_data)
                    except Exception as e:  # noqa: broad-except
                        info += "\n[PDF text extraction failed]"
                elif is_text:
                    try:
                        from salmalm.features.edge_cases import process_uploaded_file

                        info = process_uploaded_file(fname, file_data)
                    except Exception as e:  # noqa: broad-except
                        preview = file_data.decode("utf-8", errors="replace")[:3000]  # type: ignore[union-attr]
                        info += f"\n[File content]\n{preview}"
                log.info(f"[SEND] Web upload: {fname} ({size_kb:.1f}KB)")
                audit_log("web_upload", fname)
                resp = {
                    "ok": True,
                    "filename": fname,
                    "size": len(file_data),
                    "info": info,
                    "is_image": is_image,
                }
                if is_image:
                    import base64

                    ext = fname.rsplit(".", 1)[-1].lower()
                    mime = {
                        "png": "image/png",
                        "jpg": "image/jpeg",
                        "jpeg": "image/jpeg",
                        "gif": "image/gif",
                        "webp": "image/webp",
                        "bmp": "image/bmp",
                    }.get(ext, "image/png")
                    resp["image_base64"] = base64.b64encode(file_data).decode()  # type: ignore[arg-type]
                    resp["image_mime"] = mime
                self._json(resp)
                return
            self._json({"error": "No file found"}, 400)
        except Exception as e:
            log.error(f"Upload error: {e}")
            self._json({"error": str(e)[:200]}, 500)
            return

    def _get_api_sessions_export(self) -> None:
        """Handle GET /api/sessions/ routes."""
        if not self._require_auth("user"):
            return
        import urllib.parse

        m = re.match(r"^/api/sessions/([^/]+)/export", self.path)
        if not m:
            self._json({"error": "Invalid path"}, 400)
            return
        sid = m.group(1)
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        fmt = params.get("format", ["json"])[0]
        from salmalm.core import _get_db

        conn = _get_db()
        row = conn.execute(
            "SELECT messages, updated_at FROM session_store WHERE session_id=?",
            (sid,),
        ).fetchone()
        if not row:
            self._json({"error": "Session not found"}, 404)
            return
        msgs = json.loads(row[0])
        updated_at = row[1]
        if fmt == "md":
            lines = [
                "# SalmAlm Chat Export",
                "Session: {sid}",
                "Date: {updated_at}",
                "",
            ]
            for msg in msgs:
                role = msg.get("role", "")
                if role == "system":
                    continue
                content = msg.get("content", "")
                if isinstance(content, list):
                    content = " ".join(
                        b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
                    )
                icon = "## 👤 User" if role == "user" else "## 😈 Assistant"
                lines.append(icon)
                lines.append(str(content))
                lines.append("")
                lines.append("---")
                lines.append("")
            body = "\n".join(lines).encode("utf-8")
            fname = f"salmalm_{sid}_{updated_at[:10]}.md"
            self.send_response(200)
            self.send_header("Content-Type", "text/markdown; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
            self.send_header("Content-Length", str(len(body)))
            self._cors()
            self.end_headers()
            self.wfile.write(body)
        else:
            export_data = {
                "session_id": sid,
                "updated_at": updated_at,
                "messages": msgs,
            }
            body = json.dumps(export_data, ensure_ascii=False, indent=2).encode("utf-8")
            fname = f"salmalm_{sid}_{updated_at[:10]}.json"
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
            self.send_header("Content-Length", str(len(body)))
            self._cors()
            self.end_headers()
            self.wfile.write(body)
        return

    def _get_api_google_callback(self) -> None:
        """Handle GET /api/google/callback routes."""
        import urllib.parse

        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        code = params.get("code", [""])[0]
        state = params.get("state", [""])[0]
        error = params.get("error", [""])[0]
        # CSRF: validate state token
        if not state or state not in _google_oauth_pending_states:
            self._html(
                '<html><body><h2>Invalid OAuth State</h2>'
                "<p>CSRF protection: state token missing or invalid.</p>"
                '<p><a href="/">Back</a></p></body></html>'
            )
            return
        issued_at = _google_oauth_pending_states.pop(state)
        # Expire states older than 10 minutes
        if time.time() - issued_at > 600:
            self._html(
                '<html><body><h2>OAuth State Expired</h2>'
                '<p>Please try again.</p><p><a href="/">Back</a></p></body></html>'
            )
            return
        # Cleanup stale states (older than 15 min)
        cutoff = time.time() - 900
        stale = [k for k, v in _google_oauth_pending_states.items() if v < cutoff]
        for k in stale:
            _google_oauth_pending_states.pop(k, None)
        if error:
            self._html(
                f'<html><body><h2>Google OAuth Error</h2><p>{error}</p><p><a href="/">Back</a></p></body></html>'
            )
            return
        if not code:
            self._html('<html><body><h2>No code received</h2><p><a href="/">Back</a></p></body></html>')
            return
        client_id = vault.get("google_client_id") or ""
        client_secret = vault.get("google_client_secret") or ""
        port = self.server.server_address[1]
        redirect_uri = f"http://localhost:{port}/api/google/callback"
        try:
            data = json.dumps(
                {
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                }
            ).encode()
            req = urllib.request.Request(
                "https://oauth2.googleapis.com/token",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read())
            access_token = result.get("access_token", "")
            refresh_token = result.get("refresh_token", "")
            if refresh_token:
                vault.set("google_refresh_token", refresh_token)
            if access_token:
                vault.set("google_access_token", access_token)
            scopes = result.get("scope", "")
            self._html(f"""<html><body style="font-family:sans-serif;max-width:600px;margin:40px auto;text-align:center">
                <h2 style="color:#22c55e">\\u2705 Google Connected!</h2>
                <p>Refresh token saved to vault.</p>
                <p style="font-size:0.85em;color:#666">Scopes: {scopes}</p>
                <p><a href="/" style="color:#6366f1">\\u2190 Back to SalmAlm</a></p>
                </body></html>""")
            log.info(f"[OK] Google OAuth2 connected (scopes: {scopes})")
        except Exception as e:
            log.error(f"Google OAuth2 token exchange failed: {e}")
            self._html(f"""<html><body style="font-family:sans-serif;max-width:600px;margin:40px auto;text-align:center">
                <h2 style="color:#ef4444">\\u274c Token Exchange Failed</h2>
                <p>{str(e)[:200]}</p>
                <p><a href="/" style="color:#6366f1">\\u2190 Back</a></p>
                </body></html>""")

    def _get_api_agent_export(self) -> None:
        """Handle GET /api/agent/export routes."""
        # Vault export requires admin role
        from urllib.parse import parse_qs, urlparse

        qs = parse_qs(urlparse(self.path).query)
        inc_vault = qs.get("vault", ["0"])[0] == "1"
        _min_role = "admin" if inc_vault else "user"
        _export_user = self._require_auth(_min_role)
        if not _export_user:
            return
        inc_sessions = qs.get("sessions", ["1"])[0] == "1"
        inc_data = qs.get("data", ["1"])[0] == "1"
        import zipfile
        import io
        import json as _json
        import datetime

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            # Soul / personality
            soul_path = DATA_DIR / "soul.md"
            if soul_path.exists():
                zf.writestr("soul.md", soul_path.read_text(encoding="utf-8"))
            # Memory files
            from salmalm.constants import MEMORY_DIR as _mem_dir

            if _mem_dir.exists():
                for f in _mem_dir.glob("*"):
                    if f.is_file():
                        zf.writestr(f"memory/{f.name}", f.read_text(encoding="utf-8"))
            # Also include memory.md from DATA_DIR
            mem_md = DATA_DIR / "memory.md"
            if mem_md.exists():
                zf.writestr("memory.md", mem_md.read_text(encoding="utf-8"))
            # Config
            config_path = DATA_DIR / "config.json"
            if config_path.exists():
                zf.writestr("config.json", config_path.read_text(encoding="utf-8"))
            routing_path = DATA_DIR / "routing.json"
            if routing_path.exists():
                zf.writestr("routing.json", routing_path.read_text(encoding="utf-8"))
            # Sessions
            if inc_sessions:
                from salmalm.core import _get_db

                conn = _get_db()
                _export_uid = _export_user.get("id", 0)
                if _export_uid and _export_uid > 0:
                    rows = conn.execute(
                        "SELECT session_id, messages, title FROM session_store WHERE user_id=? OR user_id IS NULL",
                        (_export_uid,),
                    ).fetchall()
                else:
                    rows = conn.execute("SELECT session_id, messages, title FROM session_store").fetchall()
                sessions = []
                for r in rows:
                    sessions.append(
                        {
                            "id": r[0],
                            "data": r[1],
                            "title": r[2] if len(r) > 2 else "",
                        }
                    )
                zf.writestr(
                    "sessions.json",
                    _json.dumps(sessions, ensure_ascii=False, indent=2),
                )
            # Data (notes, expenses, habits, etc.)
            if inc_data:
                for name in (
                    "notes.json",
                    "expenses.json",
                    "habits.json",
                    "journal.json",
                    "dashboard.json",
                ):
                    p = DATA_DIR / name
                    if p.exists():
                        zf.writestr(f"data/{name}", p.read_text(encoding="utf-8"))
            # Vault (API keys) — only if explicitly requested
            if inc_vault:
                from salmalm.security.crypto import vault as _vault_mod

                if _vault_mod.is_unlocked:
                    keys = {}
                    # Use internal vault key names (lowercase)
                    for k in _vault_mod.keys():
                        v = _vault_mod.get(k)
                        if v:
                            keys[k] = v
                    if keys:
                        zf.writestr("vault_keys.json", _json.dumps(keys, indent=2))
            # Manifest
            zf.writestr(
                "manifest.json",
                _json.dumps(
                    {
                        "version": VERSION,
                        "exported_at": datetime.datetime.now().isoformat(),
                        "includes": {
                            "sessions": inc_sessions,
                            "data": inc_data,
                            "vault": inc_vault,
                        },
                    },
                    indent=2,
                ),
            )
        buf.seek(0)
        data = buf.getvalue()
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f'attachment; filename="salmalm-export-{ts}.zip"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _get_uploads(self) -> None:
        """Handle GET /uploads/ routes."""
        # Serve uploaded files (images, audio) — basename-only to prevent traversal
        fname = Path(self.path.split("/uploads/", 1)[-1]).name
        if not fname:
            self.send_error(400)
            return
        upload_dir = (WORKSPACE_DIR / "uploads").resolve()  # noqa: F405
        fpath = (upload_dir / fname).resolve()
        if not fpath.is_relative_to(upload_dir) or not fpath.exists():
            self.send_error(404)
            return
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".ogg": "audio/ogg",
        }
        ext = fpath.suffix.lower()
        mime = mime_map.get(ext, "application/octet-stream")
        # ETag caching for static uploads
        stat = fpath.stat()
        etag = f'"{int(stat.st_mtime)}-{stat.st_size}"'
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(stat.st_size))
        self.send_header("ETag", etag)
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        self.wfile.write(fpath.read_bytes())

