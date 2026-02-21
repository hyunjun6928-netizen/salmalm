"""Mesh and Canvas tool handlers. / 메시 및 캔버스 도구 핸들러."""
from salmalm.tools.tool_registry import register


@register('mesh')
def handle_mesh(args: dict) -> str:
    """SalmAlm Mesh — peer-to-peer networking. / P2P 인스턴스 네트워킹."""
    from salmalm.features.mesh import mesh_manager
    action = args.get('action', 'status')

    if action == 'status':
        peers = mesh_manager.list_peers()
        if not peers:
            return ('📡 **SalmAlm Mesh** — No peers connected. / 연결된 피어 없음\n'
                    'Add: mesh(action="add", url="http://192.168.1.x:18800")')
        lines = ['📡 **SalmAlm Mesh**\n']
        for p in peers:
            icon = '🟢' if p['status'] == 'online' else '🔴'
            ver = f' v{p["version"]}' if p.get('version') else ''
            lines.append(f'{icon} **{p["name"]}** [{p["peer_id"]}] — {p["url"]}{ver}')
        return '\n'.join(lines)

    if action == 'add':
        url = args.get('url', '')
        name = args.get('name', '')
        secret = args.get('secret', '')
        if not url:
            return '❌ url is required / url을 입력하세요'
        return mesh_manager.add_peer(url, name=name, secret=secret)

    if action == 'remove':
        peer_id = args.get('peer_id', '')
        if not peer_id:
            return '❌ peer_id is required / peer_id를 입력하세요'
        return mesh_manager.remove_peer(peer_id)

    if action == 'ping':
        results = mesh_manager.ping_all()
        if not results:
            return '📡 No peers to ping. / 핑할 피어 없음'
        lines = ['📡 **Ping Results / 핑 결과**\n']
        for pid, r in results.items():
            icon = '🟢' if r['online'] else '🔴'
            lines.append(f'{icon} {r["name"]} — {"online" if r["online"] else "offline"}')
        return '\n'.join(lines)

    if action == 'task':
        peer_id = args.get('peer_id', '')
        task = args.get('task', '')
        if not peer_id or not task:
            return '❌ peer_id and task are required / peer_id와 task를 입력하세요'
        result = mesh_manager.delegate_task(peer_id, task, model=args.get('model'))
        if 'error' in result:
            return f'❌ Task failed / 작업 실패: {result["error"]}'
        return f'✅ Task completed on peer / 피어에서 작업 완료:\n\n{result.get("result", "")[:3000]}'

    if action == 'broadcast':
        task = args.get('task', '')
        if not task:
            return '❌ task is required / task를 입력하세요'
        results = mesh_manager.broadcast_task(task)
        if not results:
            return '📡 No online peers for broadcast. / 브로드캐스트할 온라인 피어 없음'
        lines = ['📡 **Broadcast Results / 브로드캐스트 결과**\n']
        for r in results:
            status = '✅' if r.get('status') == 'completed' else '❌'
            lines.append(f'{status} {r["peer"]}: {r.get("result", r.get("error", "?"))[:200]}')
        return '\n'.join(lines)

    if action == 'clipboard':
        text = args.get('text', '')
        if text:
            mesh_manager.share_clipboard(text)
            return '📋 Clipboard shared with all online peers. / 클립보드를 모든 온라인 피어와 공유함'
        clip = mesh_manager.get_clipboard()
        if clip['text']:
            return f'📋 Shared clipboard / 공유 클립보드:\n{clip["text"][:2000]}'
        return '📋 Clipboard is empty. / 클립보드가 비어있음'

    if action == 'discover':
        urls = mesh_manager.discover_lan()
        if not urls:
            return '📡 No SalmAlm instances found on LAN. / LAN에서 SalmAlm 인스턴스를 찾지 못함'
        lines = ['📡 **Discovered on LAN / LAN 탐색 결과**\n']
        for url in urls:
            lines.append(f'  🔗 {url}')
        return '\n'.join(lines)

    return f'❌ Unknown action / 알 수 없는 액션: {action}. Use: status, add, remove, ping, task, broadcast, clipboard, discover'


@register('canvas')
def handle_canvas(args: dict) -> str:
    """Canvas — local HTML preview and rendering. / 로컬 HTML 프리뷰 및 렌더링."""
    from salmalm.features.canvas import canvas
    action = args.get('action', 'status')

    if action == 'status':
        status = canvas.get_status()
        if status['running']:
            return f'🎨 Canvas: {status["url"]} 에서 실행 중 ({status["pages"]} pages)'
        return '🎨 Canvas: 미실행 (첫 사용 시 자동 시작) / not running (auto-start on first use)'

    if action == 'present':
        html_content = args.get('html', '')
        title = args.get('title', 'Preview')
        open_browser = args.get('open', False)
        if not html_content:
            return '❌ html content is required / html 내용을 입력하세요'
        result = canvas.present(html_content, title=title, open_browser=open_browser)
        return f'🎨 Canvas page created / 캔버스 페이지 생성: {result["url"]}'

    if action == 'markdown':
        md = args.get('text', '')
        title = args.get('title', 'Markdown Preview')
        if not md:
            return '❌ text is required / text를 입력하세요'
        result = canvas.render_markdown(md, title=title)
        return f'🎨 Markdown rendered / 마크다운 렌더링 완료: {result["url"]}'

    if action == 'code':
        code = args.get('code', '')
        language = args.get('language', 'python')
        title = args.get('title', 'Code Preview')
        if not code:
            return '❌ code is required / code를 입력하세요'
        result = canvas.render_code(code, language=language, title=title)
        return f'🎨 Code rendered / 코드 렌더링 완료: {result["url"]}'

    if action == 'list':
        pages = canvas.list_pages()
        if not pages:
            return '🎨 No canvas pages. / 캔버스 페이지 없음'
        lines = ['🎨 **Canvas Pages / 캔버스 페이지**\n']
        for p in pages:
            lines.append(f'  📄 [{p["id"]}] {p["title"]}')
        return '\n'.join(lines)

    return f'❌ Unknown action / 알 수 없는 액션: {action}. Use: status, present, markdown, code, list'
