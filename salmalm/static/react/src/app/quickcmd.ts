import { chat, input, btn, costEl, modelBadge, settingsEl, filePrev, fileIconEl, fileNameEl, fileSizeEl, imgPrev, inputArea, _tok, pendingFile, pendingFiles, _currentSession, _sessionCache, _isAutoRouting, set_tok, set_pendingFile, set_pendingFiles, set_currentSession, set_sessionCache, set_isAutoRouting } from './globals';

  /* --- Quick command from sidebar --- */
  window.quickCmd=function(msg){
    input.value=msg;input.focus();
    input.dispatchEvent(new Event('input'));
    /* close sidebar on mobile */
    var sb=document.getElementById('sidebar');if(sb.classList.contains('open'))toggleSidebar();
  };

