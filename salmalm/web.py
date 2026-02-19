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
from .templates import WEB_HTML, ONBOARDING_HTML, UNLOCK_HTML, SETUP_HTML

# ============================================================


class WebHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for web UI and API."""

    def log_message(self, format, *args):
        """Suppress default HTTP request logging."""
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

    def _security_headers(self, nonce: str = ''):
        """Add security headers to all responses."""
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Permissions-Policy', 'camera=(), microphone=(self), geolocation=()')
        script_src = f"'nonce-{nonce}'" if nonce else "'self'"
        self.send_header('Content-Security-Policy',
            f"default-src 'self'; "
            f"script-src {script_src}; "
            f"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://fonts.gstatic.com; "
            f"img-src 'self' data: blob:; "
            f"connect-src 'self' ws://127.0.0.1:* ws://localhost:* wss://127.0.0.1:* wss://localhost:*; "
            f"font-src 'self' data: https://fonts.gstatic.com; "
            f"object-src 'none'; "
            f"base-uri 'self'; "
            f"form-action 'self'"
        )

    def _html(self, content: str):
        import secrets as _sec
        nonce = _sec.token_hex(16)
        # Inject nonce into all <script> tags
        content = content.replace('<script>', f'<script nonce="{nonce}">')
        body = content.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self._security_headers(nonce=nonce)
        body = self._maybe_gzip(body)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # Public endpoints (no auth required)
    _PUBLIC_PATHS = {
        '/', '/index.html', '/api/status', '/api/health', '/api/unlock',
        '/api/auth/login', '/api/onboarding', '/api/setup', '/docs',
        '/api/google/callback',
    }

    def _require_auth(self, min_role: str = 'user') -> Optional[dict]:
        """Check auth for protected endpoints. Returns user dict or sends 401 and returns None.
        If vault is locked, also rejects (403)."""
        path = self.path.split('?')[0]
        if path in self._PUBLIC_PATHS:
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
        """Handle CORS preflight requests."""
        self.send_response(204)
        self._cors()
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
        self.end_headers()

    def do_GET(self):
        """Handle HTTP GET requests."""
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
        if VAULT_FILE.exists():
            # Try env password first, then empty password (no-password vault)
            if pw and vault.unlock(pw):
                return True
            if vault.unlock(''):
                return True  # No-password vault
            if not pw:
                return False  # Has password but no env var — show unlock screen
            return False
        elif pw:
            vault.create(pw)
            return True
        # No vault file, no env var → first run, handled by _needs_first_run
        return True

    def _needs_first_run(self) -> bool:
        """True if vault file doesn't exist and no env password — brand new install."""
        return not VAULT_FILE.exists() and not os.environ.get('SALMALM_VAULT_PW', '')

    def _do_get_inner(self):
        if self.path == '/' or self.path == '/index.html':
            if self._needs_first_run():
                self._html(SETUP_HTML)
                return
            self._auto_unlock_localhost()
            if not vault.is_unlocked:
                self._html(UNLOCK_HTML)
            elif self._needs_onboarding():
                self._html(ONBOARDING_HTML)
            else:
                self._html(WEB_HTML)
        elif self.path == '/api/sessions':
            if not self._require_auth('user'): return
            from .core import _get_db
            conn = _get_db()
            # Ensure title column exists
            try:
                conn.execute('ALTER TABLE session_store ADD COLUMN title TEXT DEFAULT ""')
                conn.commit()
            except Exception:
                pass
            rows = conn.execute(
                'SELECT session_id, updated_at, title, parent_session_id FROM session_store ORDER BY updated_at DESC'
            ).fetchall()
            sessions = []
            for r in rows:
                sid = r[0]
                stored_title = r[2] if len(r) > 2 else ''
                parent_sid = r[3] if len(r) > 3 else None
                if stored_title:
                    title = stored_title
                    msg_count = 0
                else:
                    try:
                        msgs = json.loads(
                            conn.execute('SELECT messages FROM session_store WHERE session_id=?', (sid,)).fetchone()[0]
                        )
                        title = ''
                        for m in msgs:
                            if m.get('role') == 'user' and isinstance(m.get('content'), str):
                                title = m['content'][:60]
                                break
                        msg_count = len([m for m in msgs if m.get('role') in ('user', 'assistant')])
                    except Exception:
                        title = sid
                        msg_count = 0
                entry = {'id': sid, 'title': title or sid, 'updated_at': r[1], 'messages': msg_count}
                if parent_sid:
                    entry['parent_session_id'] = parent_sid
                sessions.append(entry)
            self._json({'sessions': sessions})

        elif self.path == '/api/notifications':
            if not self._require_auth('user'): return
            from .core import _sessions
            web_session = _sessions.get('web')
            notifications = []
            if web_session and hasattr(web_session, '_notifications'):
                notifications = web_session._notifications
                web_session._notifications = []  # clear after read
            self._json({'notifications': notifications})
        elif self.path == '/api/dashboard':
            if not self._require_auth('user'): return
            # Dashboard data: sessions, costs, tools, cron jobs
            from .core import _sessions, _llm_cron, PluginLoader, SubAgent  # type: ignore[attr-defined]
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
            if not self._require_auth('user'): return
            from .core import _llm_cron  # type: ignore[attr-defined]
            self._json({'jobs': _llm_cron.list_jobs() if _llm_cron else []})
        elif self.path == '/api/plugins':
            if not self._require_auth('user'): return
            from .core import PluginLoader
            tools = PluginLoader.get_all_tools()
            plugins = [{'name': n, 'tools': len(p['tools']), 'path': p['path']}
                       for n, p in PluginLoader._plugins.items()]
            self._json({'plugins': plugins, 'total_tools': len(tools)})
        elif self.path == '/api/mcp':
            if not self._require_auth('user'): return
            from .mcp import mcp_manager
            servers = mcp_manager.list_servers()
            all_tools = mcp_manager.get_all_tools()
            self._json({'servers': servers, 'total_tools': len(all_tools)})
        elif self.path == '/api/rag':
            if not self._require_auth('user'): return
            from .rag import rag_engine
            self._json(rag_engine.get_stats())
        elif self.path.startswith('/api/rag/search'):
            if not self._require_auth('user'): return
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
            base_health = health_monitor.check_health()
            # Deep check: verify LLM connectivity
            llm_ok = False
            llm_error = None
            try:
                from .llm import _http_post
                model = router.force_model or router._pick_available(1)
                provider = model.split('/')[0] if '/' in model else 'anthropic'
                from .crypto import vault as _vault
                if provider == 'anthropic' and _vault.get('anthropic_api_key'):
                    _http_post('https://api.anthropic.com/v1/messages',
                        {'x-api-key': _vault.get('anthropic_api_key'),
                         'content-type': 'application/json', 'anthropic-version': '2023-06-01'},
                        {'model': 'claude-3-5-haiku-20241022', 'max_tokens': 5,
                         'messages': [{'role': 'user', 'content': 'ping'}]}, timeout=10)
                    llm_ok = True
                elif provider == 'google' and _vault.get('google_api_key'):
                    import urllib.request
                    gk = _vault.get('google_api_key')
                    req = urllib.request.Request(
                        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gk}",
                        data=json.dumps({'contents': [{'parts': [{'text': 'ping'}]}]}).encode(),
                        headers={'Content-Type': 'application/json'})
                    urllib.request.urlopen(req, timeout=10)
                    llm_ok = True
                else:
                    llm_error = f'No key for {provider}'
            except Exception as e:
                llm_error = str(e)[:200]
            base_health['llm_connected'] = llm_ok
            if llm_error:
                base_health['llm_error'] = llm_error
            self._json(base_health)
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
            from .core import _metrics
            usage = get_usage_report()
            _metrics['total_cost'] = usage.get('total_cost', 0.0)
            merged = {**request_logger.get_metrics(), **_metrics}
            self._json(merged)
        elif self.path == '/api/cert':
            from .tls import get_cert_info
            self._json(get_cert_info())
        elif self.path == '/api/auth/users':
            user = extract_auth(dict(self.headers))
            if not user or user.get('role') != 'admin':
                self._json({'error': 'Admin access required'}, 403)
            else:
                self._json({'users': auth_manager.list_users()})
        elif self.path == '/api/google/auth':
            if not self._require_auth('user'): return
            client_id = vault.get('google_client_id') or ''
            if not client_id:
                self._json({'error': 'Set google_client_id in vault first (Settings > Vault)'}, 400)
                return
            import urllib.parse
            port = self.server.server_address[1]
            redirect_uri = f'http://localhost:{port}/api/google/callback'
            params = urllib.parse.urlencode({
                'client_id': client_id,
                'redirect_uri': redirect_uri,
                'response_type': 'code',
                'scope': 'https://www.googleapis.com/auth/gmail.modify https://www.googleapis.com/auth/calendar',
                'access_type': 'offline',
                'prompt': 'consent',
            })
            url = f'https://accounts.google.com/o/oauth2/v2/auth?{params}'
            self.send_response(302)
            self.send_header('Location', url)
            self.end_headers()
        elif self.path.startswith('/api/google/callback'):
            import urllib.parse
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            code = params.get('code', [''])[0]
            error = params.get('error', [''])[0]
            if error:
                self._html(f'<html><body><h2>Google OAuth Error</h2><p>{error}</p><p><a href="/">Back</a></p></body></html>')
                return
            if not code:
                self._html('<html><body><h2>No code received</h2><p><a href="/">Back</a></p></body></html>')
                return
            client_id = vault.get('google_client_id') or ''
            client_secret = vault.get('google_client_secret') or ''
            port = self.server.server_address[1]
            redirect_uri = f'http://localhost:{port}/api/google/callback'
            try:
                data = json.dumps({
                    'code': code,
                    'client_id': client_id,
                    'client_secret': client_secret,
                    'redirect_uri': redirect_uri,
                    'grant_type': 'authorization_code',
                }).encode()
                req = urllib.request.Request(
                    'https://oauth2.googleapis.com/token',
                    data=data,
                    headers={'Content-Type': 'application/json'},
                    method='POST')
                with urllib.request.urlopen(req, timeout=15) as resp:
                    result = json.loads(resp.read())
                access_token = result.get('access_token', '')
                refresh_token = result.get('refresh_token', '')
                if refresh_token:
                    vault.set('google_refresh_token', refresh_token)
                if access_token:
                    vault.set('google_access_token', access_token)
                scopes = result.get('scope', '')
                self._html(f'''<html><body style="font-family:sans-serif;max-width:600px;margin:40px auto;text-align:center">
                    <h2 style="color:#22c55e">\\u2705 Google Connected!</h2>
                    <p>Refresh token saved to vault.</p>
                    <p style="font-size:0.85em;color:#666">Scopes: {scopes}</p>
                    <p><a href="/" style="color:#6366f1">\\u2190 Back to SalmAlm</a></p>
                    </body></html>''')
                log.info(f"[OK] Google OAuth2 connected (scopes: {scopes})")
            except Exception as e:
                log.error(f"Google OAuth2 token exchange failed: {e}")
                self._html(f'''<html><body style="font-family:sans-serif;max-width:600px;margin:40px auto;text-align:center">
                    <h2 style="color:#ef4444">\\u274c Token Exchange Failed</h2>
                    <p>{str(e)[:200]}</p>
                    <p><a href="/" style="color:#6366f1">\\u2190 Back</a></p>
                    </body></html>''')
        elif self.path == '/manifest.json':
            manifest = {
                "name": "SalmAlm — Personal AI Gateway",
                "short_name": "SalmAlm",
                "description": "Your personal AI gateway. 43 tools, 6 providers, zero dependencies.",
                "start_url": "/",
                "display": "standalone",
                "background_color": "#0f172a",
                "theme_color": "#6366f1",
                "icons": [
                    {"src": "/icon-192.svg", "sizes": "192x192", "type": "image/svg+xml"},
                    {"src": "/icon-512.svg", "sizes": "512x512", "type": "image/svg+xml"}
                ]
            }
            self.send_response(200)
            self._cors()
            self.send_header('Content-Type', 'application/manifest+json')
            self.end_headers()
            self.wfile.write(json.dumps(manifest).encode())

        elif self.path in ('/icon-192.svg', '/icon-512.svg'):
            size = 192 if '192' in self.path else 512
            svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}">
<rect width="{size}" height="{size}" rx="{size//6}" fill="#6366f1"/>
<text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle" font-size="{size//2}">😈</text>
</svg>'''
            self.send_response(200)
            self._cors()
            self.send_header('Content-Type', 'image/svg+xml')
            self.end_headers()
            self.wfile.write(svg.encode())

        elif self.path == '/sw.js':
            _ver = VERSION  # already imported via wildcard at module level
            sw_js = f'''const CACHE='salmalm-v{_ver}';
self.addEventListener('install',e=>{{self.skipWaiting()}});
self.addEventListener('activate',e=>{{
  e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>clients.claim()))
}});
self.addEventListener('fetch',e=>{{
  if(e.request.method!=='GET')return;
  e.respondWith(fetch(e.request).then(r=>{{
    if(r.ok){{const c=r.clone();caches.open(CACHE).then(ca=>ca.put(e.request,c))}}return r
  }}).catch(()=>caches.match(e.request)))
}});'''
            self.send_response(200)
            self._cors()
            self.send_header('Content-Type', 'application/javascript')
            self.end_headers()
            self.wfile.write(sw_js.encode())

        elif self.path == '/dashboard':
            if not self._require_auth('user'): return
            from .templates import DASHBOARD_HTML
            self._html(DASHBOARD_HTML)

        elif self.path == '/docs':
            from .docs import generate_api_docs_html
            self._html(generate_api_docs_html())
        elif self.path.startswith('/uploads/'):
            # Serve uploaded files (images, audio) — basename-only to prevent traversal
            fname = Path(self.path.split('/uploads/', 1)[-1]).name
            if not fname:
                self.send_error(400); return
            upload_dir = (WORKSPACE_DIR / 'uploads').resolve()
            fpath = (upload_dir / fname).resolve()
            if not str(fpath).startswith(str(upload_dir)) or not fpath.exists():
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

    def _check_origin(self) -> bool:
        """CSRF protection: reject cross-origin state-changing requests.
        CORS blocks response reading, but the request still executes.
        This blocks the request itself for non-whitelisted origins."""
        origin = self.headers.get('Origin', '')
        if not origin:
            # No Origin header = same-origin, curl, etc. → allow
            return True
        if origin in self._ALLOWED_ORIGINS:
            return True
        log.warning(f"[BLOCK] CSRF blocked: Origin={origin} on {self.path}")
        self.send_response(403)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"error":"Forbidden: cross-origin request"}')
        return False

    def do_POST(self):
        """Handle HTTP POST requests."""
        _start = time.time()
        import uuid
        set_correlation_id(str(uuid.uuid4())[:8])

        # CSRF protection: block cross-origin POST requests
        if self.path.startswith('/api/') and not self._check_origin():
            return

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
            body = {}  # type: ignore[var-annotated]
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

        if self.path == '/api/setup':
            # First-run setup — create vault with or without password
            if VAULT_FILE.exists():
                self._json({'error': 'Already set up'}, 400)
                return
            use_pw = body.get('use_password', False)
            pw = body.get('password', '')
            if use_pw:
                if len(pw) < 4:
                    self._json({'error': 'Password must be at least 4 characters'}, 400)
                    return
                vault.create(pw)
                audit_log('setup', 'vault created with password')
            else:
                # Create vault with empty password (auto-unlock on localhost)
                vault.create('')
                audit_log('setup', 'vault created without password')
            self._json({'ok': True})
            return

        if self.path == '/api/do-update':
            if not self._require_auth('admin'): return
            if self._get_client_ip() not in ('127.0.0.1', '::1', 'localhost'):
                self._json({'error': 'Update only allowed from localhost'}, 403); return
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
            if not self._require_auth('admin'): return
            if self._get_client_ip() not in ('127.0.0.1', '::1', 'localhost'):
                self._json({'error': 'Restart only allowed from localhost'}, 403); return
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
                    {'model': TEST_MODELS['anthropic'], 'max_tokens': 10,
                     'messages': [{'role': 'user', 'content': 'ping'}]}, timeout=15),
                'openai': lambda: _http_post(
                    'https://api.openai.com/v1/chat/completions',
                    {'Authorization': 'Bearer ' + (vault.get('openai_api_key') or ''),
                     'Content-Type': 'application/json'},
                    {'model': TEST_MODELS['openai'], 'max_tokens': 10,
                     'messages': [{'role': 'user', 'content': 'ping'}]}, timeout=15),
                'xai': lambda: _http_post(
                    'https://api.x.ai/v1/chat/completions',
                    {'Authorization': 'Bearer ' + (vault.get('xai_api_key') or ''),
                     'Content-Type': 'application/json'},
                    {'model': TEST_MODELS['xai'], 'max_tokens': 10,
                     'messages': [{'role': 'user', 'content': 'ping'}]}, timeout=15),
                'google': lambda: (lambda k: __import__('urllib.request', fromlist=['urlopen']).urlopen(
                    __import__('urllib.request', fromlist=['Request']).Request(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{TEST_MODELS['google']}:generateContent?key={k}",
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

        elif self.path == '/api/stt':
            if not self._require_auth('user'): return
            audio_b64 = body.get('audio_base64', '')
            lang = body.get('language', 'ko')
            if not audio_b64:
                self._json({'error': 'No audio data'}, 400)
                return
            try:
                from .tool_handlers import execute_tool
                result = execute_tool('stt', {'audio_base64': audio_b64, 'language': lang})  # type: ignore[assignment]
                text = result.replace('🎤 Transcription:\n', '') if isinstance(result, str) else ''
                self._json({'ok': True, 'text': text})
            except Exception as e:
                self._json({'ok': False, 'error': str(e)}, 500)

        elif self.path == '/api/sessions/delete':
            if not self._require_auth('user'): return
            sid = body.get('session_id', '')
            if not sid:
                self._json({'ok': False, 'error': 'Missing session_id'}, 400)
                return
            from .core import _sessions, _get_db
            if sid in _sessions:
                del _sessions[sid]
            conn = _get_db()
            conn.execute('DELETE FROM session_store WHERE session_id=?', (sid,))
            conn.commit()
            audit_log('session_delete', sid)
            self._json({'ok': True})

        elif self.path == '/api/sessions/rename':
            if not self._require_auth('user'): return
            sid = body.get('session_id', '')
            title = body.get('title', '').strip()[:60]
            if not sid or not title:
                self._json({'ok': False, 'error': 'Missing session_id or title'}, 400)
                return
            from .core import _get_db
            conn = _get_db()
            # Store title in a separate column (add if not exists)
            try:
                conn.execute('ALTER TABLE session_store ADD COLUMN title TEXT DEFAULT ""')
                conn.commit()
            except Exception:
                pass  # column already exists
            conn.execute('UPDATE session_store SET title=? WHERE session_id=?', (title, sid))
            conn.commit()
            self._json({'ok': True})

        elif self.path == '/api/sessions/rollback':
            if not self._require_auth('user'): return
            sid = body.get('session_id', '')
            count = int(body.get('count', 1))
            if not sid:
                self._json({'ok': False, 'error': 'Missing session_id'}, 400)
                return
            from .core import rollback_session
            result = rollback_session(sid, count)
            self._json(result)

        elif self.path == '/api/sessions/branch':
            if not self._require_auth('user'): return
            sid = body.get('session_id', '')
            message_index = body.get('message_index')
            if not sid or message_index is None:
                self._json({'ok': False, 'error': 'Missing session_id or message_index'}, 400)
                return
            from .core import branch_session
            result = branch_session(sid, int(message_index))
            self._json(result)

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
                tool_count = [0]
                def on_tool_sse(name, args):
                    tool_count[0] += 1
                    send_sse('tool', {'name': name, 'args': str(args)[:200], 'count': tool_count[0]})
                    send_sse('status', {'text': f'🔧 Running {name}...'})

                # Token-by-token streaming callback (OpenClaw-style)
                streamed_text = ['']
                def on_token_sse(event):
                    try:
                        etype = event.get('type', '')
                        if etype == 'text_delta':
                            text = event.get('text', '')
                            if text:
                                streamed_text[0] += text
                                send_sse('chunk', {'text': text, 'streaming': True})
                        elif etype == 'thinking_delta':
                            send_sse('thinking', {'text': event.get('text', '')})
                        elif etype == 'tool_use_start':
                            tool_count[0] += 1
                            send_sse('status', {'text': f'🔧 Running {event.get("name", "tool")}...'})
                            send_sse('tool', {'name': event.get('name', ''), 'count': tool_count[0]})
                        elif etype == 'error':
                            send_sse('error', {'text': event.get('error', '')})
                    except Exception:
                        pass  # SSE write errors are non-fatal

                try:
                    loop = asyncio.new_event_loop()
                    response = loop.run_until_complete(
                        process_message(session_id, message,
                                        image_data=(image_b64, image_mime) if image_b64 else None,
                                        on_tool=on_tool_sse,
                                        on_token=on_token_sse)
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
            elif action == 'change_password':
                old_pw = body.get('old_password', '')
                new_pw = body.get('new_password', '')
                if new_pw and len(new_pw) < 4:
                    self._json({'error': 'Password must be at least 4 characters'}, 400)
                elif vault.change_password(old_pw, new_pw):
                    audit_log('vault', 'master password changed')
                    self._json({'ok': True})
                else:
                    self._json({'error': 'Current password is incorrect'}, 403)
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
                raw = self.rfile.read(length)
                # Parse multipart using stdlib email.parser (robust edge-case handling)
                import email.parser, email.policy
                header_bytes = f"Content-Type: {content_type}\r\n\r\n".encode()
                msg = email.parser.BytesParser(policy=email.policy.compat32).parsebytes(header_bytes + raw)
                for part in msg.walk():
                    fname_raw = part.get_filename()
                    if not fname_raw:
                        continue
                    fname = Path(fname_raw).name  # basename only (prevent path traversal)
                    # Reject suspicious filenames
                    if not fname or '..' in fname or not re.match(r'^[\w.\- ]+$', fname):
                        self._json({'error': 'Invalid filename'}, 400)
                        return
                    file_data = part.get_payload(decode=True)
                    if not file_data:
                        continue
                    # Size limit: 50MB
                    if len(file_data) > 50 * 1024 * 1024:
                        self._json({'error': 'File too large (max 50MB)'}, 413)
                        return
                    # Save
                    save_dir = WORKSPACE_DIR / 'uploads'
                    save_dir.mkdir(exist_ok=True)
                    save_path = save_dir / fname
                    save_path.write_bytes(file_data)  # type: ignore[arg-type]
                    size_kb = len(file_data) / 1024
                    is_image = any(fname.lower().endswith(ext) for ext in ('.png','.jpg','.jpeg','.gif','.webp','.bmp'))
                    is_text = any(fname.lower().endswith(ext) for ext in ('.txt','.md','.py','.js','.json','.csv','.log','.html','.css','.sh','.bat','.yaml','.yml','.xml','.sql'))
                    info = f'[{"🖼️ Image" if is_image else "📎 File"} uploaded: uploads/{fname} ({size_kb:.1f}KB)]'
                    if is_text:
                        try:
                            preview = file_data.decode('utf-8', errors='replace')[:3000]  # type: ignore[union-attr]
                            info += f'\n[File content]\n{preview}'
                        except Exception:
                            pass
                    log.info(f"[SEND] Web upload: {fname} ({size_kb:.1f}KB)")
                    audit_log('web_upload', fname)
                    resp = {'ok': True, 'filename': fname, 'size': len(file_data),
                                'info': info, 'is_image': is_image}
                    if is_image:
                        import base64
                        ext = fname.rsplit('.', 1)[-1].lower()
                        mime = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
                                'gif': 'image/gif', 'webp': 'image/webp', 'bmp': 'image/bmp'}.get(ext, 'image/png')
                        resp['image_base64'] = base64.b64encode(file_data).decode()  # type: ignore[arg-type]
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
                        {'model': TEST_MODELS['anthropic'], 'max_tokens': 10,
                         'messages': [{'role': 'user', 'content': 'ping'}]}, timeout=15)
                    test_results.append('✅ Anthropic OK')
                except Exception as e:
                    test_results.append(f'⚠️ Anthropic: {str(e)[:80]}')
            if body.get('openai_api_key'):
                try:
                    _http_post('https://api.openai.com/v1/chat/completions',
                        {'Authorization': f'Bearer {body["openai_api_key"]}', 'Content-Type': 'application/json'},
                        {'model': TEST_MODELS['openai'], 'max_tokens': 10,
                         'messages': [{'role': 'user', 'content': 'ping'}]}, timeout=15)
                    test_results.append('✅ OpenAI OK')
                except Exception as e:
                    test_results.append(f'⚠️ OpenAI: {str(e)[:80]}')
            if body.get('xai_api_key'):
                try:
                    _http_post('https://api.x.ai/v1/chat/completions',
                        {'Authorization': f'Bearer {body["xai_api_key"]}', 'Content-Type': 'application/json'},
                        {'model': TEST_MODELS['xai'], 'max_tokens': 10,
                         'messages': [{'role': 'user', 'content': 'ping'}]}, timeout=15)
                    test_results.append('✅ xAI OK')
                except Exception as e:
                    test_results.append(f'⚠️ xAI: {str(e)[:80]}')
            if body.get('google_api_key'):
                try:
                    import urllib.request
                    gk = body['google_api_key']
                    req = urllib.request.Request(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{TEST_MODELS['google']}:generateContent?key={gk}",
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
            result = gateway.register(  # type: ignore[assignment]
                node_id, url,
                token=body.get('token', ''),
                capabilities=body.get('capabilities'),
                name=body.get('name', ''))
            self._json(result)  # type: ignore[arg-type]

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
                result = gateway.dispatch(node_id, tool, args)  # type: ignore[assignment]
            else:
                result = gateway.dispatch_auto(tool, args)  # type: ignore[assignment]
                if result is None:
                    result = {'error': 'No available node for this tool'}
            self._json(result)  # type: ignore[arg-type]

        elif self.path == '/api/node/execute':
            # Node endpoint: execute a tool locally (called by gateway)
            from .tool_handlers import execute_tool
            tool = body.get('tool', '')
            args = body.get('args', {})
            if not tool:
                self._json({'error': 'tool name required'}, 400)
                return
            try:
                result = execute_tool(tool, args)  # type: ignore[assignment]
                self._json({'ok': True, 'result': result[:50000]})  # type: ignore[index]
            except Exception as e:
                self._json({'error': str(e)[:500]}, 500)

        else:
            self._json({'error': 'Not found'}, 404)





