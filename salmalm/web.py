"""SalmAlm Web UI — HTML + WebHandler."""
import warnings
warnings.filterwarnings('ignore', category=SyntaxWarning, module='web')
import asyncio, gzip, http.server, json, os, re, secrets, sys, time
from pathlib import Path
from typing import Optional

from .constants import *
from .crypto import vault, log
from .core import get_usage_report, router, audit_log
from .auth import auth_manager, rate_limiter, extract_auth, RateLimitExceeded
from .logging_ext import request_logger, set_correlation_id
from .templates import WEB_HTML, ONBOARDING_HTML, UNLOCK_HTML

# ============================================================


class WebHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for web UI and API."""

    def log_message(self, format, *args):
        pass  # Suppress default logging

    # Allowed origins for CORS (same-host only)
    _ALLOWED_ORIGINS = {
        'http://127.0.0.1:18800', 'http://localhost:18800',
        'http://127.0.0.1:18801', 'http://localhost:18801',
        'https://127.0.0.1:18800', 'https://localhost:18800',
    }

    def _cors(self):
        origin = self.headers.get('Origin', '')
        if origin in self._ALLOWED_ORIGINS:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
        # No Origin header (same-origin requests, curl, etc) → no CORS headers needed
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-API-Key')

    def _maybe_gzip(self, body: bytes) -> bytes:
        """Compress body if client accepts gzip and body is large enough."""
        if len(body) < 1024:
            return body
        ae = self.headers.get('Accept-Encoding', '')
        if 'gzip' not in ae:
            return body
        import gzip as _gzip
        compressed = _gzip.compress(body, compresslevel=6)
        if len(compressed) < len(body):
            self.send_header('Content-Encoding', 'gzip')
            return compressed
        return body

    def _json(self, data: dict, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self._cors()
        self._security_headers()
        body = self._maybe_gzip(body)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _security_headers(self):
        """Add security headers to all responses."""
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
        # CSP: allow inline scripts (required) but block external scripts/objects
        self.send_header('Content-Security-Policy',
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "connect-src 'self' ws://127.0.0.1:* wss://127.0.0.1:*; "
            "font-src 'self' data:; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )

    def _html(self, content: str):
        body = content.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self._security_headers()
        body = self._maybe_gzip(body)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # Public endpoints (no auth required)
    _PUBLIC_PATHS = {
        '/', '/index.html', '/api/status', '/api/health', '/api/unlock',
        '/api/auth/login', '/api/onboarding', '/docs',
    }

    def _require_auth(self, min_role: str = 'user') -> Optional[dict]:
        """Check auth for protected endpoints. Returns user dict or sends 401 and returns None.
        If vault is locked, also rejects (403)."""
        path = self.path.split('?')[0]
        if path in self._PUBLIC_PATHS or path.startswith('/uploads/'):
            return {'username': 'public', 'role': 'public', 'id': 0}  # skip auth for public endpoints

        # Try token/api-key auth first
        user = extract_auth(dict(self.headers))
        if user:
            role_rank = {'admin': 3, 'user': 2, 'readonly': 1}
            if role_rank.get(user.get('role', ''), 0) >= role_rank.get(min_role, 2):
                return user
            self._json({'error': 'Insufficient permissions'}, 403)
            return None

        # Fallback: if request is from loopback AND vault is unlocked, allow (single-user local mode)
        ip = self._get_client_ip()
        if ip in ('127.0.0.1', '::1', 'localhost') and vault.is_unlocked:
            return {'username': 'local', 'role': 'admin', 'id': 0}

        self._json({'error': 'Authentication required'}, 401)
        return None

    def _get_client_ip(self) -> str:
        """Get client IP. Only trusts X-Forwarded-For if SALMALM_TRUST_PROXY is set."""
        if os.environ.get('SALMALM_TRUST_PROXY'):
            xff = self.headers.get('X-Forwarded-For')
            if xff:
                return xff.split(',')[0].strip()
        return self.client_address[0] if self.client_address else '?'

    def _check_rate_limit(self) -> bool:
        """Check rate limit. Returns True if OK, sends 429 if exceeded."""
        ip = self._get_client_ip()
        user = extract_auth(dict(self.headers))
        if not user and ip in ('127.0.0.1', '::1', 'localhost') and vault.is_unlocked:
            user = {'username': 'local', 'role': 'admin'}
        role = user.get('role', 'anonymous') if user else 'anonymous'
        key = user.get('username', ip) if user else ip
        try:
            rate_limiter.check(key, role)
            return True
        except RateLimitExceeded as e:
            self.send_response(429)
            self.send_header('Retry-After', str(int(e.retry_after)))
            self._cors()
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'Rate limit exceeded',
                                         'retry_after': e.retry_after}).encode())
            return False

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
        self.end_headers()

    def do_GET(self):
        _start = time.time()
        import uuid
        set_correlation_id(str(uuid.uuid4())[:8])

        if self.path.startswith('/api/') and not self._check_rate_limit():
            return

        try:
            self._do_get_inner()
        except Exception as e:
            log.error(f"GET {self.path} error: {e}")
            self._json({'error': 'Internal server error'}, 500)
        finally:
            duration = (time.time() - _start) * 1000
            request_logger.log_request('GET', self.path.split('?')[0],
                                        ip=self._get_client_ip(),
                                        duration_ms=duration)

    def _needs_onboarding(self) -> bool:
        """Check if first-run onboarding is needed (no API keys or Ollama configured)."""
        if not vault.is_unlocked:
            return False
        providers = ['anthropic_api_key', 'openai_api_key', 'xai_api_key', 'google_api_key']
        has_api_key = any(vault.get(k) for k in providers)
        has_ollama = bool(vault.get('ollama_url'))
        return not (has_api_key or has_ollama)

    def _auto_unlock_localhost(self):
        """Auto-unlock vault for localhost connections."""
        if vault.is_unlocked:
            return True
        ip = self._get_client_ip()
        if ip not in ('127.0.0.1', '::1', 'localhost'):
            return False
        pw = os.environ.get('SALMALM_VAULT_PW', '')
        if not pw:
            # No vault password set — skip vault, rely on .env for API keys
            return True
        if VAULT_FILE.exists():
            return vault.unlock(pw)
        else:
            vault.create(pw)
            return True

    def _do_get_inner(self):
        if self.path == '/' or self.path == '/index.html':
            self._auto_unlock_localhost()
            if not vault.is_unlocked:
                self._html(UNLOCK_HTML)
            elif self._needs_onboarding():
                self._html(ONBOARDING_HTML)
            else:
                self._html(WEB_HTML)
        elif self.path == '/api/notifications':
            from .core import _sessions
            web_session = _sessions.get('web')
            notifications = []
            if web_session and hasattr(web_session, '_notifications'):
                notifications = web_session._notifications
                web_session._notifications = []  # clear after read
            self._json({'notifications': notifications})
        elif self.path == '/api/dashboard':
            # Dashboard data: sessions, costs, tools, cron jobs
            from .core import _sessions, _llm_cron, PluginLoader, SubAgent
            sessions_info = [
                {'id': s.id, 'messages': len(s.messages),
                 'last_active': s.last_active, 'created': s.created}
                for s in _sessions.values()
            ]
            cron_jobs = _llm_cron.list_jobs() if _llm_cron else []
            plugins = [{'name': n, 'tools': len(p['tools'])}
                       for n, p in PluginLoader._plugins.items()]
            subagents = SubAgent.list_agents()
            usage = get_usage_report()
            # Cost by hour (from audit)
            cost_timeline = []
            try:
                import sqlite3 as _sq
                _conn = _sq.connect(str(AUDIT_DB))
                cur = _conn.execute(
                    "SELECT substr(ts,1,13) as hour, COUNT(*) as cnt "
                    "FROM audit_log WHERE event='tool_exec' "
                    "GROUP BY hour ORDER BY hour DESC LIMIT 24")
                cost_timeline = [{'hour': r[0], 'count': r[1]} for r in cur.fetchall()]
                _conn.close()
            except Exception:
                pass
            self._json({
                'sessions': sessions_info,
                'usage': usage,
                'cron_jobs': cron_jobs,
                'plugins': plugins,
                'subagents': subagents,
                'cost_timeline': cost_timeline
            })
        elif self.path == '/api/cron':
            from .core import _llm_cron
            self._json({'jobs': _llm_cron.list_jobs() if _llm_cron else []})
        elif self.path == '/api/plugins':
            from .core import PluginLoader
            tools = PluginLoader.get_all_tools()
            plugins = [{'name': n, 'tools': len(p['tools']), 'path': p['path']}
                       for n, p in PluginLoader._plugins.items()]
            self._json({'plugins': plugins, 'total_tools': len(tools)})
        elif self.path == '/api/mcp':
            from .mcp import mcp_manager
            servers = mcp_manager.list_servers()
            all_tools = mcp_manager.get_all_tools()
            self._json({'servers': servers, 'total_tools': len(all_tools)})
        elif self.path == '/api/rag':
            from .rag import rag_engine
            self._json(rag_engine.get_stats())
        elif self.path.startswith('/api/rag/search'):
            from .rag import rag_engine
            import urllib.parse
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            query = params.get('q', [''])[0]
            if not query:
                self._json({'error': 'Missing q parameter'}, 400)
            else:
                results = rag_engine.search(query, max_results=int(params.get('n', ['5'])[0]))
                self._json({'query': query, 'results': results})
        elif self.path == '/api/ws/status':
            from .ws import ws_server
            self._json({
                'running': ws_server._running,
                'clients': ws_server.client_count,
                'port': ws_server.port,
            })
        elif self.path == '/api/health':
            from .stability import health_monitor
            self._json(health_monitor.check_health())
        elif self.path == '/api/nodes':
            from .nodes import node_manager
            self._json({'nodes': node_manager.list_nodes()})
        elif self.path == '/api/gateway/nodes':
            from .nodes import gateway
            self._json({'nodes': gateway.list_nodes()})
        elif self.path == '/api/status':
            self._json({'app': APP_NAME, 'version': VERSION,
                        'unlocked': vault.is_unlocked,
                        'usage': get_usage_report(),
                        'model': router.force_model or 'auto'})
        elif self.path == '/api/check-update':
            try:
                import urllib.request
                resp = urllib.request.urlopen('https://pypi.org/pypi/salmalm/json', timeout=10)
                data = json.loads(resp.read().decode())
                latest = data.get('info', {}).get('version', VERSION)
                is_exe = getattr(sys, 'frozen', False)
                result = {'current': VERSION, 'latest': latest, 'exe': is_exe}
                if is_exe:
                    result['download_url'] = 'https://github.com/hyunjun6928-netizen/salmalm/releases/latest'
                self._json(result)
            except Exception as e:
                self._json({'current': VERSION, 'latest': None, 'error': str(e)[:100]})
        elif self.path == '/api/metrics':
            self._json(request_logger.get_metrics())
        elif self.path == '/api/cert':
            from .tls import get_cert_info
            self._json(get_cert_info())
        elif self.path == '/api/auth/users':
            user = extract_auth(dict(self.headers))
            if not user or user.get('role') != 'admin':
                self._json({'error': 'Admin access required'}, 403)
            else:
                self._json({'users': auth_manager.list_users()})
        elif self.path == '/docs':
            from .docs import generate_api_docs_html
            self._html(generate_api_docs_html())
        elif self.path.startswith('/uploads/'):
            # Serve uploaded files (images, audio)
            fname = self.path.split('/uploads/')[-1]
            fpath = WORKSPACE_DIR / 'uploads' / fname
            if not fpath.exists():
                self.send_error(404)
                return
            mime_map = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                        '.gif': 'image/gif', '.webp': 'image/webp', '.mp3': 'audio/mpeg',
                        '.wav': 'audio/wav', '.ogg': 'audio/ogg'}
            ext = fpath.suffix.lower()
            mime = mime_map.get(ext, 'application/octet-stream')
            # ETag caching for static uploads
            stat = fpath.stat()
            etag = f'"{int(stat.st_mtime)}-{stat.st_size}"'
            if self.headers.get('If-None-Match') == etag:
                self.send_response(304)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(stat.st_size))
            self.send_header('ETag', etag)
            self.send_header('Cache-Control', 'public, max-age=86400')
            self.end_headers()
            self.wfile.write(fpath.read_bytes())
        else:
            self.send_error(404)

    def do_POST(self):
        _start = time.time()
        import uuid
        set_correlation_id(str(uuid.uuid4())[:8])

        if self.path.startswith('/api/') and not self._check_rate_limit():
            return

        try:
            self._do_post_inner()
        except Exception as e:
            log.error(f"POST {self.path} error: {e}")
            self._json({'error': 'Internal server error'}, 500)
        finally:
            duration = (time.time() - _start) * 1000
            request_logger.log_request('POST', self.path,
                                        ip=self._get_client_ip(),
                                        duration_ms=duration)

    def _do_post_inner(self):
        from .engine import process_message
        length = int(self.headers.get('Content-Length', 0))
        # Don't parse multipart as JSON
        if self.path == '/api/upload':
            body = {}
        else:
            body = json.loads(self.rfile.read(length)) if length else {}

        if self.path == '/api/auth/login':
            username = body.get('username', '')
            password = body.get('password', '')
            user = auth_manager.authenticate(username, password)
            if user:
                token = auth_manager.create_token(user)
                self._json({'ok': True, 'token': token, 'user': user})
            else:
                self._json({'error': 'Invalid credentials'}, 401)
            return

        if self.path == '/api/auth/register':
            requester = extract_auth(dict(self.headers))
            if not requester or requester.get('role') != 'admin':
                self._json({'error': 'Admin access required'}, 403)
                return
            try:
                user = auth_manager.create_user(
                    body.get('username', ''), body.get('password', ''),
                    body.get('role', 'user'))
                self._json({'ok': True, 'user': user})
            except ValueError as e:
                self._json({'error': str(e)}, 400)
            return

        if self.path == '/api/do-update':
            try:
                import subprocess, sys
                result = subprocess.run(
                    [sys.executable, '-m', 'pip', 'install', '--upgrade', '--no-cache-dir', 'salmalm'],
                    capture_output=True, text=True, timeout=60)
                if result.returncode == 0:
                    # Get installed version
                    ver_result = subprocess.run(
                        [sys.executable, '-c', 'from salmalm.constants import VERSION; print(VERSION)'],
                        capture_output=True, text=True, timeout=10)
                    new_ver = ver_result.stdout.strip() or '?'
                    audit_log('update', f'upgraded to v{new_ver}')
                    self._json({'ok': True, 'version': new_ver, 'output': result.stdout[-200:]})
                else:
                    self._json({'ok': False, 'error': result.stderr[-200:]})
            except Exception as e:
                self._json({'ok': False, 'error': str(e)[:200]})
            return

        if self.path == '/api/restart':
            import sys, subprocess
            audit_log('restart', 'user-initiated restart')
            self._json({'ok': True, 'message': 'Restarting...'})
            # Restart the server process
            os.execv(sys.executable, [sys.executable] + sys.argv)
            return

        if self.path == '/api/test-key':
            provider = body.get('provider', '')
            from .llm import _http_post
            tests = {
                'anthropic': lambda: _http_post(
                    'https://api.anthropic.com/v1/messages',
                    {'x-api-key': vault.get('anthropic_api_key') or '',
                     'content-type': 'application/json', 'anthropic-version': '2023-06-01'},
                    {'model': 'claude-haiku-4-5-20250414', 'max_tokens': 10,
                     'messages': [{'role': 'user', 'content': 'ping'}]}, timeout=15),
                'openai': lambda: _http_post(
                    'https://api.openai.com/v1/chat/completions',
                    {'Authorization': 'Bearer ' + (vault.get('openai_api_key') or ''),
                     'Content-Type': 'application/json'},
                    {'model': 'gpt-4.1-nano', 'max_tokens': 10,
                     'messages': [{'role': 'user', 'content': 'ping'}]}, timeout=15),
                'xai': lambda: _http_post(
                    'https://api.x.ai/v1/chat/completions',
                    {'Authorization': 'Bearer ' + (vault.get('xai_api_key') or ''),
                     'Content-Type': 'application/json'},
                    {'model': 'grok-3-mini', 'max_tokens': 10,
                     'messages': [{'role': 'user', 'content': 'ping'}]}, timeout=15),
                'google': lambda: (lambda k: __import__('urllib.request', fromlist=['urlopen']).urlopen(
                    __import__('urllib.request', fromlist=['Request']).Request(
                        f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={k}',
                        data=json.dumps({'contents': [{'parts': [{'text': 'ping'}]}]}).encode(),
                        headers={'Content-Type': 'application/json'}), timeout=15))(vault.get('google_api_key') or ''),
            }
            if provider not in tests:
                self._json({'ok': False, 'result': f'❌ Unknown provider: {provider}'})
                return
            key = vault.get(f'{provider}_api_key') if provider != 'google' else vault.get('google_api_key')
            if not key:
                self._json({'ok': False, 'result': f'❌ {provider} API key not found in vault'})
                return
            try:
                tests[provider]()
                self._json({'ok': True, 'result': f'✅ {provider} API connection successful!'})
            except Exception as e:
                self._json({'ok': False, 'result': f'❌ {provider} Test failed: {str(e)[:120]}'})
            return

        if self.path == '/api/unlock':
            password = body.get('password', '')
            if VAULT_FILE.exists():
                ok = vault.unlock(password)
            else:
                vault.create(password)
                ok = True
            if ok:
                audit_log('unlock', 'vault unlocked')
                token = secrets.token_hex(32)
                self._json({'ok': True, 'token': token})
            else:
                audit_log('unlock_fail', 'wrong password')
                self._json({'ok': False, 'error': 'Wrong password'}, 401)

        elif self.path in ('/api/chat', '/api/chat/stream'):
            self._auto_unlock_localhost()
            if not vault.is_unlocked:
                self._json({'error': 'Vault locked'}, 403)
                return
            message = body.get('message', '')
            session_id = body.get('session', 'web')
            image_b64 = body.get('image_base64')
            image_mime = body.get('image_mime', 'image/png')
            use_stream = self.path.endswith('/stream')

            if use_stream:
                # SSE streaming response
                self.send_response(200)
                self._cors()
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Connection', 'keep-alive')
                self.end_headers()

                def send_sse(event, data):
                    try:
                        payload = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                        self.wfile.write(payload.encode())
                        self.wfile.flush()
                    except Exception:
                        pass

                send_sse('status', {'text': '🤔 Thinking...'})
                try:
                    loop = asyncio.new_event_loop()
                    response = loop.run_until_complete(
                        process_message(session_id, message,
                                        image_data=(image_b64, image_mime) if image_b64 else None,
                                        on_tool=lambda name, args: send_sse('tool', {'name': name, 'args': str(args)[:200]}))
                    )
                    loop.close()
                except Exception as e:
                    log.error(f"SSE process_message error: {e}")
                    response = f'❌ Internal error: {type(e).__name__}'
                send_sse('done', {'response': response, 'model': router.force_model or 'auto'})
                try:
                    self.wfile.write(b"event: close\ndata: {}\n\n")
                    self.wfile.flush()
                except Exception:
                    pass
            else:
                try:
                    loop = asyncio.new_event_loop()
                    response = loop.run_until_complete(
                        process_message(session_id, message,
                                        image_data=(image_b64, image_mime) if image_b64 else None)
                    )
                    loop.close()
                except Exception as e:
                    log.error(f"Chat process_message error: {e}")
                    response = f'❌ Internal error: {type(e).__name__}'
                self._json({'response': response, 'model': router.force_model or 'auto'})

        elif self.path == '/api/vault':
            if not vault.is_unlocked:
                self._json({'error': 'Vault locked'}, 403)
                return
            # Vault ops require admin
            user = extract_auth(dict(self.headers))
            ip = self._get_client_ip()
            if not user and ip not in ('127.0.0.1', '::1', 'localhost'):
                self._json({'error': 'Admin access required'}, 403)
                return
            action = body.get('action')
            if action == 'set':
                vault.set(body['key'], body['value'])
                self._json({'ok': True})
            elif action == 'get':
                val = vault.get(body['key'])
                self._json({'value': val})
            elif action == 'keys':
                self._json({'keys': vault.keys()})
            elif action == 'delete':
                vault.delete(body['key'])
                self._json({'ok': True})
            else:
                self._json({'error': 'Unknown action'}, 400)

        elif self.path == '/api/upload':
            if not vault.is_unlocked:
                self._json({'error': 'Vault locked'}, 403)
                return
            # Parse multipart form data
            content_type = self.headers.get('Content-Type', '')
            if 'multipart/form-data' not in content_type:
                self._json({'error': 'multipart required'}, 400)
                return
            try:
                boundary = content_type.split('boundary=')[1].strip()
                raw = self.rfile.read(length)
                # Simple multipart parser
                parts = raw.split(f'--{boundary}'.encode())
                for part in parts:
                    if b'filename="' not in part:
                        continue
                    # Extract filename
                    header_end = part.find(b'\r\n\r\n')
                    if header_end < 0:
                        continue
                    header = part[:header_end].decode('utf-8', errors='replace')
                    fname_match = re.search(r'filename="([^"]+)"', header)
                    if not fname_match:
                        continue
                    fname = Path(fname_match.group(1)).name  # basename only (prevent path traversal)
                    # Reject suspicious filenames
                    if not fname or '..' in fname or not re.match(r'^[\w.\- ]+$', fname):
                        self._json({'error': 'Invalid filename'}, 400)
                        return
                    file_data = part[header_end+4:]
                    # Remove trailing \r\n--
                    if file_data.endswith(b'\r\n'):
                        file_data = file_data[:-2]
                    if file_data.endswith(b'--'):
                        file_data = file_data[:-2]
                    if file_data.endswith(b'\r\n'):
                        file_data = file_data[:-2]
                    # Size limit: 50MB
                    if len(file_data) > 50 * 1024 * 1024:
                        self._json({'error': 'File too large (max 50MB)'}, 413)
                        return
                    # Save
                    save_dir = WORKSPACE_DIR / 'uploads'
                    save_dir.mkdir(exist_ok=True)
                    save_path = save_dir / fname
                    save_path.write_bytes(file_data)
                    size_kb = len(file_data) / 1024
                    is_image = any(fname.lower().endswith(ext) for ext in ('.png','.jpg','.jpeg','.gif','.webp','.bmp'))
                    is_text = any(fname.lower().endswith(ext) for ext in ('.txt','.md','.py','.js','.json','.csv','.log','.html','.css','.sh','.bat','.yaml','.yml','.xml','.sql'))
                    info = f'[{"🖼️ Image" if is_image else "📎 File"} uploaded: uploads/{fname} ({size_kb:.1f}KB)]'
                    if is_text:
                        try:
                            preview = file_data.decode('utf-8', errors='replace')[:3000]
                            info += f'\n[File content]\n{preview}'
                        except Exception:
                            pass
                    log.info(f"📤 Web upload: {fname} ({size_kb:.1f}KB)")
                    audit_log('web_upload', fname)
                    resp = {'ok': True, 'filename': fname, 'size': len(file_data),
                                'info': info, 'is_image': is_image}
                    if is_image:
                        import base64
                        ext = fname.rsplit('.', 1)[-1].lower()
                        mime = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
                                'gif': 'image/gif', 'webp': 'image/webp', 'bmp': 'image/bmp'}.get(ext, 'image/png')
                        resp['image_base64'] = base64.b64encode(file_data).decode()
                        resp['image_mime'] = mime
                    self._json(resp)
                    return
                self._json({'error': 'No file found'}, 400)
            except Exception as e:
                log.error(f"Upload error: {e}")
                self._json({'error': str(e)[:200]}, 500)
                return

        elif self.path == '/api/onboarding':
            if not vault.is_unlocked:
                self._json({'error': 'Vault locked'}, 403)
                return
            # Save all provided API keys + Ollama URL
            saved = []
            for key in ('anthropic_api_key', 'openai_api_key', 'xai_api_key',
                        'google_api_key', 'brave_api_key'):
                val = body.get(key, '').strip()
                if val:
                    vault.set(key, val)
                    saved.append(key.replace('_api_key', ''))
            dc_token = body.get('discord_token', '').strip()
            if dc_token:
                vault.set('discord_token', dc_token)
                saved.append('discord')
            ollama_url = body.get('ollama_url', '').strip()
            if ollama_url:
                vault.set('ollama_url', ollama_url)
                saved.append('ollama')
            # Test all provided keys
            from .llm import _http_post
            test_results = []
            if body.get('anthropic_api_key'):
                try:
                    _http_post('https://api.anthropic.com/v1/messages',
                        {'x-api-key': body['anthropic_api_key'], 'content-type': 'application/json',
                         'anthropic-version': '2023-06-01'},
                        {'model': 'claude-haiku-4-5-20250414', 'max_tokens': 10,
                         'messages': [{'role': 'user', 'content': 'ping'}]}, timeout=15)
                    test_results.append('✅ Anthropic OK')
                except Exception as e:
                    test_results.append(f'⚠️ Anthropic: {str(e)[:80]}')
            if body.get('openai_api_key'):
                try:
                    _http_post('https://api.openai.com/v1/chat/completions',
                        {'Authorization': f'Bearer {body["openai_api_key"]}', 'Content-Type': 'application/json'},
                        {'model': 'gpt-4.1-nano', 'max_tokens': 10,
                         'messages': [{'role': 'user', 'content': 'ping'}]}, timeout=15)
                    test_results.append('✅ OpenAI OK')
                except Exception as e:
                    test_results.append(f'⚠️ OpenAI: {str(e)[:80]}')
            if body.get('xai_api_key'):
                try:
                    _http_post('https://api.x.ai/v1/chat/completions',
                        {'Authorization': f'Bearer {body["xai_api_key"]}', 'Content-Type': 'application/json'},
                        {'model': 'grok-3-mini', 'max_tokens': 10,
                         'messages': [{'role': 'user', 'content': 'ping'}]}, timeout=15)
                    test_results.append('✅ xAI OK')
                except Exception as e:
                    test_results.append(f'⚠️ xAI: {str(e)[:80]}')
            if body.get('google_api_key'):
                try:
                    import urllib.request
                    gk = body['google_api_key']
                    req = urllib.request.Request(
                        f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gk}',
                        data=json.dumps({'contents': [{'parts': [{'text': 'ping'}]}]}).encode(),
                        headers={'Content-Type': 'application/json'})
                    urllib.request.urlopen(req, timeout=15)
                    test_results.append('✅ Google OK')
                except Exception as e:
                    test_results.append(f'⚠️ Google: {str(e)[:80]}')
            audit_log('onboarding', f'keys: {", ".join(saved)}')
            test_result = ' | '.join(test_results) if test_results else 'Keys saved.'
            self._json({'ok': True, 'saved': saved, 'test_result': test_result})
            return

        elif self.path == '/api/config/telegram':
            if not vault.is_unlocked:
                self._json({'error': 'Vault locked'}, 403)
                return
            vault.set('telegram_token', body.get('token', ''))
            vault.set('telegram_owner_id', body.get('owner_id', ''))
            self._json({'ok': True, 'message': 'Telegram config saved. Restart required.'})

        # === Gateway-Node Protocol ===
        elif self.path == '/api/gateway/register':
            from .nodes import gateway
            node_id = body.get('node_id', '')
            url = body.get('url', '')
            if not node_id or not url:
                self._json({'error': 'node_id and url required'}, 400)
                return
            result = gateway.register(
                node_id, url,
                token=body.get('token', ''),
                capabilities=body.get('capabilities'),
                name=body.get('name', ''))
            self._json(result)

        elif self.path == '/api/gateway/heartbeat':
            from .nodes import gateway
            node_id = body.get('node_id', '')
            self._json(gateway.heartbeat(node_id))

        elif self.path == '/api/gateway/unregister':
            from .nodes import gateway
            node_id = body.get('node_id', '')
            self._json(gateway.unregister(node_id))

        elif self.path == '/api/gateway/dispatch':
            from .nodes import gateway
            node_id = body.get('node_id', '')
            tool = body.get('tool', '')
            args = body.get('args', {})
            if node_id:
                result = gateway.dispatch(node_id, tool, args)
            else:
                result = gateway.dispatch_auto(tool, args)
                if result is None:
                    result = {'error': 'No available node for this tool'}
            self._json(result)

        elif self.path == '/api/node/execute':
            # Node endpoint: execute a tool locally (called by gateway)
            from .tool_handlers import execute_tool
            tool = body.get('tool', '')
            args = body.get('args', {})
            if not tool:
                self._json({'error': 'tool name required'}, 400)
                return
            try:
                result = execute_tool(tool, args)
                self._json({'ok': True, 'result': result[:50000]})
            except Exception as e:
                self._json({'error': str(e)[:500]}, 500)

        else:
            self._json({'error': 'Not found'}, 404)





