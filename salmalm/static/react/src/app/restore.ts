import { _currentSession, _isAutoRouting, _sessionCache, _storageKey, _tok, addMsg, btn, chat, costEl, fileIconEl, fileNameEl, filePrev, fileSizeEl, imgPrev, input, inputArea, loadSessionList, modelBadge, pendingFile, pendingFiles, set_currentSession, set_isAutoRouting, set_pendingFile, set_pendingFiles, set_sessionCache, set_tok, settingsEl, t } from './globals';

  /* --- Restore chat history (deferred until i18n t() is ready) --- */
  window._pendingRestore=function(){
    var stored=localStorage.getItem(_storageKey(_currentSession));
    if(stored)localStorage.setItem('salm_chat',stored);
    var hist=JSON.parse(localStorage.getItem('salm_chat')||'[]');
    if(hist.length){window._restoring=true;hist.forEach(function(m){if(m&&m.role)addMsg(m.role,m.text,m.model)});window._restoring=false}
    loadSessionList();
  };

