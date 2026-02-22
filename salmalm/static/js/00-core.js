  const chat=document.getElementById('chat'),input=document.getElementById('input'),
    btn=document.getElementById('send-btn'),costEl=document.getElementById('cost-display'),
    modelBadge=document.getElementById('model-badge'),settingsEl=document.getElementById('settings'),
    filePrev=document.getElementById('file-preview'),fileIconEl=document.getElementById('file-icon'),
    fileNameEl=document.getElementById('file-name'),fileSizeEl=document.getElementById('file-size'),
    imgPrev=document.getElementById('img-preview'),inputArea=document.getElementById('input-area');
  let _tok=sessionStorage.getItem('tok')||'',pendingFile=null;
  var _currentSession=localStorage.getItem('salm_active_session')||'web';
  var _sessionCache={};
