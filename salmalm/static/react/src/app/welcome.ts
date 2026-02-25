import { _currentSession, _isAutoRouting, _sessionCache, _tok, addMsg, btn, chat, costEl, fileIconEl, fileNameEl, filePrev, fileSizeEl, imgPrev, input, inputArea, modelBadge, pendingFile, pendingFiles, set_currentSession, set_isAutoRouting, set_pendingFile, set_pendingFiles, set_sessionCache, set_tok, settingsEl, t } from './globals';

  /* --- Welcome (only if no history) --- */
  if(!JSON.parse(localStorage.getItem('salm_chat')||'[]').length){
    addMsg('assistant',t('welcome-msg'),'system');
  }
  input.focus();

  /* --- Restore model preference from server --- */
  fetch('/api/status?session='+encodeURIComponent(_currentSession)).then(r=>r.json()).then(d=>{
    if(d.model&&d.model!=='auto'){
      set_isAutoRouting(false);
      var sel=document.getElementById('s-model');
      if(sel){sel.value=d.model;modelBadge.textContent=d.model.split('/').pop()}
    }else{set_isAutoRouting(true);modelBadge.textContent='auto routing'}
    /* Channel badges */
    var ch=d.channels||{};
    var tgB=document.querySelector('#tg-status .badge');
    var dcB=document.querySelector('#dc-status .badge');
    if(tgB){tgB.textContent=ch.telegram?'ON':'OFF';tgB.style.background=ch.telegram?'var(--accent)':'var(--bg3)';tgB.style.color=ch.telegram?'#fff':'var(--text2)'}
    if(dcB){dcB.textContent=ch.discord?'ON':'OFF';dcB.style.background=ch.discord?'#5865F2':'var(--bg3)';dcB.style.color=ch.discord?'#fff':'var(--text2)'}
  }).catch(()=>{});

