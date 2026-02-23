  /* ── Doctor / Self-Diagnostics Panel ── */
  window._loadDoctor=function(){
    var el=document.getElementById('doctor-content');if(!el)return;
    var kr=document.documentElement.lang==='kr';
    el.innerHTML='<div style="text-align:center;padding:20px;color:var(--text2)">⏳ '+(kr?'진단 중...':'Running diagnostics...')+'</div>';
    fetch('/api/doctor',{headers:{'X-Session-Token':_tok}}).then(function(r){return r.json()}).then(function(d){
      var h='<div style="margin-bottom:12px;font-size:14px;font-weight:600">📊 '+d.passed+'/'+d.total+' '+(kr?'통과':'passed')+'</div>';
      (d.checks||[]).forEach(function(c){
        var icon=c.status==='ok'?'✅':'❌';
        var fix=c.fixable?' <span style="color:var(--accent);font-size:11px">(🔧 fixable)</span>':'';
        h+='<div style="padding:6px 0;border-bottom:1px solid var(--border);font-size:13px">'+icon+' '+c.message+fix+'</div>';
      });
      el.innerHTML=h;
    }).catch(function(e){
      el.innerHTML='<div style="color:var(--red)">Error: '+e+'</div>';
    });
  };
