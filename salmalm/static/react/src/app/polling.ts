import { _currentSession, _isAutoRouting, _sessionCache, _tok, addMsg, btn, chat, costEl, fileIconEl, fileNameEl, filePrev, fileSizeEl, imgPrev, input, inputArea, modelBadge, pendingFile, pendingFiles, set_currentSession, set_isAutoRouting, set_pendingFile, set_pendingFiles, set_sessionCache, set_tok, settingsEl } from './globals';

  /* --- Notification polling (30s) --- */
  setInterval(async()=>{
    if(!_tok)return;
    try{
      var r=await fetch('/api/notifications',{headers:{'X-Session-Token':_tok}});
      if(!r.ok)return;
      var d=await r.json();
      if(d.notifications&&d.notifications.length){
        d.notifications.forEach(n=>addMsg('assistant',n.text,'notification'));
      }
    }catch(e){}
  },30000);

