import { chat, input, btn, costEl, modelBadge, settingsEl, filePrev, fileIconEl, fileNameEl, fileSizeEl, imgPrev, inputArea, _tok, pendingFile, pendingFiles, _currentSession, _sessionCache, _isAutoRouting, set_tok, set_pendingFile, set_pendingFiles, set_currentSession, set_sessionCache, set_isAutoRouting } from './globals';

  /* --- Double-click to rename session title --- */
  document.addEventListener('dblclick',function(e){
    var el=e.target.closest('.session-title');if(!el)return;
    e.stopPropagation();
    var sid=el.getAttribute('data-sid');
    var oldTitle=el.textContent.replace(/^↳ /,'');
    var inp=document.createElement('input');
    inp.type='text';inp.value=oldTitle;
    inp.style.cssText='width:100%;padding:2px 4px;border:1px solid var(--accent);border-radius:4px;background:var(--bg);color:var(--text);font-size:12px;outline:none';
    el.textContent='';el.appendChild(inp);inp.focus();inp.select();
    function save(){
      var newTitle=inp.value.trim()||oldTitle;
      el.textContent=newTitle;
      if(newTitle!==oldTitle){
        fetch('/api/sessions/rename',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},
          body:JSON.stringify({session_id:sid,title:newTitle})}).catch(function(){});
      }
    }
    inp.addEventListener('blur',save);
    inp.addEventListener('keydown',function(ev){if(ev.key==='Enter'){ev.preventDefault();inp.blur()}if(ev.key==='Escape'){inp.value=oldTitle;inp.blur()}});
  });

  /* Auto-check for updates on load */
  setTimeout(function(){
    fetch('/api/update/check').then(function(r){return r.json()}).then(function(d){
      if(d.update_available&&d.latest){
        var banner=document.getElementById('update-banner');
        if(banner){banner.style.display='flex';document.getElementById('banner-ver').textContent='v'+d.latest+' available';}
      }
    }).catch(function(){});
  },3000);

