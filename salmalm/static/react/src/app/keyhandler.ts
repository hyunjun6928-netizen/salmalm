import { chat, input, btn, costEl, modelBadge, settingsEl, filePrev, fileIconEl, fileNameEl, fileSizeEl, imgPrev, inputArea, _tok, pendingFile, pendingFiles, _currentSession, _sessionCache, _isAutoRouting, set_tok, set_pendingFile, set_pendingFiles, set_currentSession, set_sessionCache, set_isAutoRouting } from './globals';

  /* --- Key handler --- */
  input.addEventListener('keydown',function(e){
    if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();doSend()}
  });
  input.addEventListener('input',function(){input.style.height='auto';input.style.height=Math.min(input.scrollHeight,150)+'px'});
  btn.addEventListener('click',function(){doSend()});

