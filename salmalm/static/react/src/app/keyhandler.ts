import { _currentSession, _isAutoRouting, _sessionCache, _tok, btn, chat, costEl, doSend, fileIconEl, fileNameEl, filePrev, fileSizeEl, imgPrev, input, inputArea, modelBadge, pendingFile, pendingFiles, set_currentSession, set_isAutoRouting, set_pendingFile, set_pendingFiles, set_sessionCache, set_tok, settingsEl } from './globals';

  /* --- Key handler --- */
  input.addEventListener('keydown',function(e){
    if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();doSend()}
  });
  input.addEventListener('input',function(){input.style.height='auto';input.style.height=Math.min(input.scrollHeight,150)+'px'});
  btn.addEventListener('click',function(){doSend()});

