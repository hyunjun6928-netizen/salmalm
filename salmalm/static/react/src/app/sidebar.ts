import { chat, input, btn, costEl, modelBadge, settingsEl, filePrev, fileIconEl, fileNameEl, fileSizeEl, imgPrev, inputArea, _tok, pendingFile, pendingFiles, _currentSession, _sessionCache, _isAutoRouting, set_tok, set_pendingFile, set_pendingFiles, set_currentSession, set_sessionCache, set_isAutoRouting } from './globals';

  /* --- Sidebar toggle (mobile) --- */
  window.toggleSidebar=function(){
    var sb=document.getElementById('sidebar'),ov=document.getElementById('side-overlay');
    sb.classList.toggle('open');ov.classList.toggle('open');
  };

