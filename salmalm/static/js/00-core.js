  const chat=document.getElementById('chat'),input=document.getElementById('input'),
    btn=document.getElementById('send-btn'),costEl=document.getElementById('cost-display'),
    modelBadge=document.getElementById('model-badge'),settingsEl=document.getElementById('settings'),
    filePrev=document.getElementById('file-preview'),fileIconEl=document.getElementById('file-icon'),
    fileNameEl=document.getElementById('file-name'),fileSizeEl=document.getElementById('file-size'),
    imgPrev=document.getElementById('img-preview'),inputArea=document.getElementById('input-area');
  let _tok=sessionStorage.getItem('tok')||'',pendingFile=null;
  var _currentSession=localStorage.getItem('salm_active_session')||'web';
  var _sessionCache={};
  var _isAutoRouting=true;
  // CSRF: monkey-patch fetch to add X-Requested-With on same-origin /api/ requests
  const _origFetch=window.fetch;
  window.fetch=function(url,opts){
    opts=opts||{};
    const u=typeof url==='string'?url:(url&&url.url)||'';
    if(u.startsWith('/api/')){
      opts.headers=opts.headers||{};
      if(opts.headers instanceof Headers){opts.headers.set('X-Requested-With','SalmAlm');}
      else{opts.headers['X-Requested-With']='SalmAlm';}
    }
    return _origFetch.call(window,url,opts);
  };
