"""SalmAlm HTML templates."""
from pathlib import Path

_STATIC = Path(__file__).resolve().parent.parent / "static"

_WS_PATCH = """<script>
(function(){
  var O=window.WebSocket;
  window.WebSocket=function(u,p){
    var ws=p?new O(u,p):new O(u);
    ws.addEventListener('message',function(ev){
      try{
        var d=JSON.parse(ev.data);
        if(d.type==='chat'&&d.content){
          var te=document.getElementById('typing-row');if(te)te.remove();
          if(typeof addMsg==='function')addMsg('assistant',d.content);
          var ot=document.title;
          document.title=(d.source==='cron'?'[cron] ':'[notify] ')+ot;
          setTimeout(function(){document.title=ot;},4000);
        }else if(d.type==='subagent_done'){
          var t=d.task||{};
          if(t.status==='completed'&&t.result&&typeof addMsg==='function'){
            addMsg('assistant','[subagent done]\n\n'+t.result.substring(0,500));
          }else if(t.status==='failed'&&typeof addMsg==='function'){
            addMsg('assistant','[subagent failed]: '+(t.error||''));
          }
        }
      }catch(e){}
    });
    return ws;
  };
  Object.assign(window.WebSocket,O);
})();
</script></body>"""


def _load(name: str) -> str:
    p = _STATIC / name
    if not p.exists():
        return ""
    from salmalm import __version__
    import time as _t
    ts = str(int(_t.time()) // 3600)
    html = p.read_text(encoding="utf-8").replace("{{VERSION}}", f"v{__version__}.{ts}")
    if name == "index.html" and "</body>" in html:
        html = html.replace("</body>", _WS_PATCH)
    return html


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
