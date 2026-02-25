import { chat, input, btn, costEl, modelBadge, settingsEl, filePrev, fileIconEl, fileNameEl, fileSizeEl, imgPrev, inputArea, _tok, pendingFile, pendingFiles, _currentSession, _sessionCache, _isAutoRouting, set_tok, set_pendingFile, set_pendingFiles, set_currentSession, set_sessionCache, set_isAutoRouting } from './globals';

  /* --- Drag & drop --- */
  /* Fullscreen dropzone overlay */
  var _dragCtr=0;
  var _dropOv=document.createElement('div');
  _dropOv.style.cssText='display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(99,102,241,0.15);z-index:9999;pointer-events:none;align-items:center;justify-content:center';
  _dropOv.innerHTML='<div style="padding:32px 48px;background:var(--bg2);border:3px dashed var(--accent);border-radius:16px;color:var(--accent);font-size:20px;font-weight:600;pointer-events:none" data-i18n="drop-overlay">📎 Drop image or file here</div>';
  document.body.appendChild(_dropOv);
  document.addEventListener('dragenter',function(e){e.preventDefault();_dragCtr++;if(_dragCtr===1)_dropOv.style.display='flex'});
  document.addEventListener('dragleave',function(e){e.preventDefault();_dragCtr--;if(_dragCtr<=0){_dragCtr=0;_dropOv.style.display='none'}});
  document.addEventListener('dragover',function(e){e.preventDefault()});
  document.addEventListener('drop',function(e){e.preventDefault();_dragCtr=0;_dropOv.style.display='none';
    var _dfs=e.dataTransfer&&e.dataTransfer.files;if(_dfs&&_dfs.length>1){window.setFiles(Array.from(_dfs))}else if(_dfs&&_dfs[0]){window.setFile(_dfs[0])}});

