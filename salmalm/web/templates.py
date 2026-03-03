"""SalmAlm HTML templates — thin loader over static/ files.

Templates are stored as plain HTML in salmalm/static/ for easier editing.
Uses module-level __getattr__ so templates are re-read on every access
(no server restart needed during development).
"""

from pathlib import Path

_STATIC = Path(__file__).resolve().parent.parent / "static"


def _load(name: str) -> str:
    """Read a static HTML file, return empty string if missing."""
    p = _STATIC / name
    if p.exists():
        from salmalm import __version__

        import time as _t
        _ts = str(int(_t.time()) // 3600)  # changes every hour
        html = p.read_text(encoding="utf-8").replace("{{VERSION}}", f"v{__version__}.{_ts}")
        if name == "index.html":
            _ws_patch = """<script>
(function(){
  var _orig = window._wsOnMsg;
  function _patchWS(){
    if(!window._ws||window._ws._salmalm_patched)return;
    window._ws._salmalm_patched=true;
    var _origOnMsg=window._ws.onmessage;
    window._ws.onmessage=function(ev){
      if(_origOnMsg)_origOnMsg.call(this,ev);
      try{
        var d=JSON.parse(ev.data);
        if(d.type==='chat'&&d.content){
          var _te=document.getElementById('typing-row');if(_te)_te.remove();
          if(typeof addMsg==='function')addMsg('assistant',d.content);
          var _ot=document.title;
          document.title=(d.source==='cron'?'\u23F0 ':'🔔 ')+_ot;
          setTimeout(function(){document.title=_ot;},4000);
        }else if(d.type==='subagent_done'){
          var t=d.task||{};
          if(t.status==='completed'&&t.result&&typeof addMsg==='function'){
            addMsg('assistant','\u2705 \uc11c\ube0c\uc5d0\uc774\uc804\ud2b8 \uc644\ub8cc\n\n'+t.result.substring(0,500));
          }else if(t.status==='failed'&&typeof addMsg==='function'){
            addMsg('assistant','\u274c \uc2e4\ud328: '+(t.error||''));
          }
        }
      }catch(e){}
    };
  }
  var _orig_ws=window.WebSocket;
  window.WebSocket=function(url,protocols){
    var ws=protocols?new _orig_ws(url,protocols):new _orig_ws(url);
    window._ws=ws;
    ws.addEventListener('open',function(){_patchWS();});
    return ws;
  };
  window.WebSocket.prototype=_orig_ws.prototype;
  window.WebSocket.CONNECTING=_orig_ws.CONNECTING;
  window.WebSocket.OPEN=_orig_ws.OPEN;
  window.WebSocket.CLOSING=_orig_ws.CLOSING;
  window.WebSocket.CLOSED=_orig_ws.CLOSED;
  setTimeout(function(){if(window._ws)_patchWS();},2000);
})();
</script></body>"""
            html = html.replace("</body>", _ws_patch)
        return html
    return ""


_TEMPLATE_MAP = {
    "WEB_HTML": "index.html",
    "ONBOARDING_HTML": "onboarding.html",
    "SETUP_HTML": "setup.html",
    "UNLOCK_HTML": "unlock.html",
    "DASHBOARD_HTML": "dashboard.html",
}


def __getattr__(name: str):
    if name in _TEMPLATE_MAP:
        return _load(_TEMPLATE_MAP[name])
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
