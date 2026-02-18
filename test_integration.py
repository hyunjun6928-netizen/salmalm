#!/usr/bin/env python3
"""SalmAlm v0.8.9 Integration Test — runs against a live server."""
import json, os, sys, time, urllib.request, urllib.error

BASE = os.environ.get('SALMALM_URL', 'http://127.0.0.1:18800')
PASS = FAIL = 0

def req(method, path, data=None):
    url = BASE + path
    body = json.dumps(data).encode() if data else None
    headers = {'Content-Type': 'application/json'} if data else {}
    r = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(r, timeout=15)
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except:
            return {'_error': str(e)}
    except Exception as e:
        return {'_error': str(e)}

def check(ok, name, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  ✅ {name}')
    else:
        FAIL += 1
        print(f'  ❌ {name} — {detail}')

def get_html(path='/'):
    r = urllib.request.urlopen(BASE + path, timeout=10)
    return r.read().decode()

print('═' * 50)
print(f'  SalmAlm Integration Test ({BASE})')
print('═' * 50)

# 1. Status
print('\n📡 1. Server Status')
d = req('GET', '/api/status')
check(d.get('version') == '0.8.9', 'Version = 0.8.9', d.get('version'))

# 2. Auto-unlock (GET / triggers it)
print('\n🔓 2. Auto-unlock')
html = get_html('/')
d2 = req('GET', '/api/status')
check(d2.get('unlocked') == True, 'Vault auto-unlocked after GET /', d2.get('unlocked'))

# 3. Onboarding page (no keys yet)
print('\n🌐 3. Pages')
check('Setup Wizard' in html or 'Web Chat' in html, 'Serves valid page', html[:100])

# 4. Save API keys
print('\n🔑 4. API Key Management')
for k in ['anthropic_api_key', 'openai_api_key', 'xai_api_key', 'google_api_key', 'brave_api_key']:
    r = req('POST', '/api/vault', {'action': 'set', 'key': k, 'value': f'test-{k}'})
    check(r.get('ok') == True, f'Save {k}', str(r))
    time.sleep(0.5)

# 5. Vault keys list
r = req('POST', '/api/vault', {'action': 'keys'})
check(len(r.get('keys', [])) >= 5, f'Vault has {len(r.get("keys",[]))} keys', str(r))

# 6. Web Chat page after keys
print('\n💬 6. Chat Page')
html2 = get_html('/')
check('Web Chat' in html2, 'Web Chat shown after keys saved', html2[:100])

# 7. English UI
print('\n🌍 7. English UI')
import re
for word in ['Settings', 'Usage', 'Channels', 'Tools', 'Cost:', 'Export', 'New Chat', 'Running']:
    check(word in html2, f'Contains "{word}"')
korean = re.findall(r'[\uAC00-\uD7AF]+', html2)
check(len(korean) == 0, f'No Korean text (found {len(korean)})', ', '.join(korean[:5]) if korean else '')

# 8. Test API keys
print('\n🧪 8. API Key Tests')
time.sleep(2)
for p in ['anthropic', 'openai']:
    r = req('POST', '/api/test-key', {'provider': p})
    has = 'result' in r
    check(has, f'Test {p} returns result', str(r)[:100])
    time.sleep(1.5)

# 9. Error language
print('\n🌍 9. Error Language')
time.sleep(2)
r = req('POST', '/api/test-key', {'provider': 'anthropic'})
msg = r.get('result', '')
check('Invalid' in msg or 'failed' in msg or 'not found' in msg, 'Error in English', msg[:100])

# 10. Check Update
print('\n🔄 10. Update System')
time.sleep(1)
r = req('GET', '/api/check-update')
check(r.get('current') == '0.8.9', f'Current = 0.8.9', r.get('current'))
check(r.get('latest') is not None, f'Latest fetched: {r.get("latest")}')

# 11-16. API Endpoints
print('\n🏥 11. Health & API Endpoints')
time.sleep(1)
for name, path, key in [
    ('Health', '/api/health', 'status'),
    ('RAG', '/api/rag', 'total_chunks'),
    ('WS', '/api/ws/status', 'running'),
    ('Metrics', '/api/metrics', 'total_requests'),
    ('Dashboard', '/api/dashboard', 'sessions'),
    ('Plugins', '/api/plugins', 'plugins'),
    ('MCP', '/api/mcp', 'servers'),
    ('Nodes', '/api/nodes', 'nodes'),
    ('Cron', '/api/cron', 'jobs'),
    ('Notifications', '/api/notifications', 'notifications'),
]:
    time.sleep(0.8)
    r = req('GET', path)
    check(key in r, f'{name} endpoint ({key})', str(r)[:80])

# 17. RAG search
time.sleep(1)
r = req('GET', '/api/rag/search?q=hello&n=3')
check('results' in r, f'RAG search ({len(r.get("results",[]))} results)', str(r)[:80])

# 18. Onboarding
print('\n🎓 18. Onboarding')
time.sleep(2)
r = req('POST', '/api/onboarding', {'anthropic_api_key': 'sk-fake', 'openai_api_key': 'sk-fake2'})
check(len(r.get('saved', [])) >= 2, f'Saves {len(r.get("saved",[]))} keys', str(r)[:80])
tr = r.get('test_result', '')
check('|' in tr, 'Tests keys individually', tr[:80])

# 19. Security headers
print('\n🛡️ 19. Security Headers')
time.sleep(1)
r = urllib.request.urlopen(BASE + '/', timeout=10)
hdrs = dict(r.headers)
check('Content-Security-Policy' in hdrs or 'content-security-policy' in hdrs, 'CSP header')
check('X-Frame-Options' in hdrs or 'x-frame-options' in hdrs, 'X-Frame-Options header')
check('X-Content-Type-Options' in hdrs or 'x-content-type-options' in hdrs, 'X-Content-Type-Options')

# Summary
print('\n' + '═' * 50)
total = PASS + FAIL
print(f'  RESULTS: {PASS}/{total} passed, {FAIL} failed')
print('═' * 50)
sys.exit(0 if FAIL == 0 else 1)
