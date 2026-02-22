  /* --- Restore chat history (deferred until i18n t() is ready) --- */
  window._pendingRestore=function(){
    var stored=localStorage.getItem(_storageKey(_currentSession));
    if(stored)localStorage.setItem('salm_chat',stored);
    var hist=JSON.parse(localStorage.getItem('salm_chat')||'[]');
    if(hist.length){window._restoring=true;hist.forEach(function(m){if(m&&m.role)addMsg(m.role,m.text,m.model)});window._restoring=false}
    loadSessionList();
  };
