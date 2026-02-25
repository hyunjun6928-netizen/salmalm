import { chat, input, btn, costEl, modelBadge, settingsEl, filePrev, fileIconEl, fileNameEl, fileSizeEl, imgPrev, inputArea, _tok, pendingFile, pendingFiles, _currentSession, _sessionCache, _isAutoRouting, set_tok, set_pendingFile, set_pendingFiles, set_currentSession, set_sessionCache, set_isAutoRouting } from './globals';

  /* --- Export chat --- */
  window.exportChat=function(fmt){
    var hist=JSON.parse(localStorage.getItem('salm_chat')||'[]');
    if(!hist.length){addMsg('assistant',t('no-chat-export'));return}
    var content='';
    if(fmt==='json'){
      content=JSON.stringify(hist,null,2);
      var blob=new Blob([content],{type:'application/json'});
      var a=document.createElement('a');a.href=URL.createObjectURL(blob);
      a.download='salmalm_chat_'+new Date().toISOString().slice(0,10)+'.json';a.click();
    }else{
      hist.forEach(function(m){
        var role=m.role==='user'?'👤 User':'😈 SalmAlm';
        content+=role+'\n'+m.text+'\n\n---\n\n';
      });
      var blob=new Blob([content],{type:'text/markdown'});
      var a=document.createElement('a');a.href=URL.createObjectURL(blob);
      a.download='salmalm_chat_'+new Date().toISOString().slice(0,10)+'.md';a.click();
    }
  };

