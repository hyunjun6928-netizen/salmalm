"""Mesh and Canvas tool handlers. / 메시 및 캔버스 도구 핸들러."""

from salmalm.tools.tool_registry import register


@register("mesh")
def _mesh_status(mgr, args: dict) -> str:
    peers = mgr.list_peers()
    if not peers:
        return '📡 **SalmAlm Mesh** — No peers connected.\nAdd: mesh(action="add", url="http://192.168.1.x:18800")'
    lines = ["📡 **SalmAlm Mesh**\n"]
    for p in peers:
        icon = "🟢" if p["status"] == "online" else "🔴"
        ver = f" v{p['version']}" if p.get("version") else ""
        lines.append(f"{icon} **{p['name']}** [{p['peer_id']}] — {p['url']}{ver}")
    return "\n".join(lines)


def _mesh_add(mgr, args: dict) -> str:
    url = args.get("url", "")
    if not url:
        return "❌ url is required"
    return mgr.add_peer(url, name=args.get("name", ""), secret=args.get("secret", ""))


def _mesh_remove(mgr, args: dict) -> str:
    peer_id = args.get("peer_id", "")
    return mgr.remove_peer(peer_id) if peer_id else "❌ peer_id is required"


def _mesh_ping(mgr, args: dict) -> str:
    results = mgr.ping_all()
    if not results:
        return "📡 No peers to ping."
    lines = ["📡 **Ping Results**\n"]
    for pid, r in results.items():
        icon = "🟢" if r["online"] else "🔴"
        lines.append(f"{icon} {r['name']} — {'online' if r['online'] else 'offline'}")
    return "\n".join(lines)


def _mesh_task(mgr, args: dict) -> str:
    peer_id, task = args.get("peer_id", ""), args.get("task", "")
    if not peer_id or not task:
        return "❌ peer_id and task are required"
    result = mgr.delegate_task(peer_id, task, model=args.get("model"))
    if "error" in result:
        return f"❌ Task failed: {result['error']}"
    return f"✅ Task completed:\n\n{result.get('result', '')[:3000]}"


def _mesh_broadcast(mgr, args: dict) -> str:
    task = args.get("task", "")
    if not task:
        return "❌ task is required"
    results = mgr.broadcast_task(task)
    if not results:
        return "📡 No online peers for broadcast."
    lines = ["📡 **Broadcast Results**\n"]
    for r in results:
        s = "✅" if r.get("status") == "completed" else "❌"
        lines.append(f"{s} {r['peer']}: {r.get('result', r.get('error', '?'))[:200]}")
    return "\n".join(lines)


def _mesh_clipboard(mgr, args: dict) -> str:
    text = args.get("text", "")
    if text:
        mgr.share_clipboard(text)
        return "📋 Clipboard shared with all online peers."
    clip = mgr.get_clipboard()
    return f"📋 Shared clipboard:\n{clip['text'][:2000]}" if clip["text"] else "📋 Clipboard is empty."


def _mesh_discover(mgr, args: dict) -> str:
    urls = mgr.discover_lan()
    if not urls:
        return "📡 No SalmAlm instances found on LAN."
    return "📡 **Discovered on LAN**\n" + "\n".join(f"  🔗 {u}" for u in urls)


_MESH_DISPATCH = {
    "status": _mesh_status,
    "add": _mesh_add,
    "remove": _mesh_remove,
    "ping": _mesh_ping,
    "task": _mesh_task,
    "broadcast": _mesh_broadcast,
    "clipboard": _mesh_clipboard,
    "discover": _mesh_discover,
}


def handle_mesh(args: dict) -> str:
    """SalmAlm Mesh — peer-to-peer networking."""
    from salmalm.features.mesh import mesh_manager

    action = args.get("action", "status")
    handler = _MESH_DISPATCH.get(action)
    if handler:
        return handler(mesh_manager, args)
    return f"❌ Unknown action: {action}. Use: {', '.join(_MESH_DISPATCH)}"


@register("canvas")
def handle_canvas(args: dict) -> str:
    """Canvas — local HTML preview and rendering. / 로컬 HTML 프리뷰 및 렌더링."""
    from salmalm.features.canvas import canvas

    action = args.get("action", "status")

    if action == "status":
        status = canvas.get_status()
        if status["running"]:
            return f"🎨 Canvas: {status['url']} 에서 실행 중 ({status['pages']} pages)"
        return "🎨 Canvas: 미실행 (첫 사용 시 자동 시작) / not running (auto-start on first use)"

    if action == "present":
        html_content = args.get("html", "")
        title = args.get("title", "Preview")
        open_browser = args.get("open", False)
        if not html_content:
            return "❌ html content is required / html 내용을 입력하세요"
        result = canvas.present(html_content, title=title, open_browser=open_browser)
        return f"🎨 Canvas page created / 캔버스 페이지 생성: {result['url']}"

    if action == "markdown":
        md = args.get("text", "")
        title = args.get("title", "Markdown Preview")
        if not md:
            return "❌ text is required / text를 입력하세요"
        result = canvas.render_markdown(md, title=title)
        return f"🎨 Markdown rendered / 마크다운 렌더링 완료: {result['url']}"

    if action == "code":
        code = args.get("code", "")
        language = args.get("language", "python")
        title = args.get("title", "Code Preview")
        if not code:
            return "❌ code is required / code를 입력하세요"
        result = canvas.render_code(code, language=language, title=title)
        return f"🎨 Code rendered / 코드 렌더링 완료: {result['url']}"

    if action == "list":
        pages = canvas.list_pages()
        if not pages:
            return "🎨 No canvas pages. / 캔버스 페이지 없음"
        lines = ["🎨 **Canvas Pages / 캔버스 페이지**\n"]
        for p in pages:
            lines.append(f"  📄 [{p['id']}] {p['title']}")
        return "\n".join(lines)

    return f"❌ Unknown action / 알 수 없는 액션: {action}. Use: status, present, markdown, code, list"
