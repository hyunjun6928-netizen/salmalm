import { chat, input, btn, costEl, modelBadge, settingsEl, filePrev, fileIconEl, fileNameEl, fileSizeEl, imgPrev, inputArea, _tok, pendingFile, pendingFiles, _currentSession, _sessionCache, _isAutoRouting, set_tok, set_pendingFile, set_pendingFiles, set_currentSession, set_sessionCache, set_isAutoRouting } from './globals';

  /* ── Backup / Restore Panel ── */
  window._doBackup=function(){
    var btn=document.getElementById('backup-btn');
    if(btn)btn.textContent='⏳...';
    var a=document.createElement('a');
    a.href='/api/backup';a.download='salmalm_backup.zip';
    // Need auth header — use fetch+blob
    fetch('/api/backup',{headers:{'X-Session-Token':_tok}}).then(function(r){
      if(!r.ok)throw new Error('HTTP '+r.status);
      return r.blob();
    }).then(function(blob){
      var url=URL.createObjectURL(blob);
      a.href=url;a.click();URL.revokeObjectURL(url);
      if(btn)btn.textContent='✅';
      setTimeout(function(){if(btn)btn.textContent='📥 Backup'},2000);
    }).catch(function(e){
      if(btn)btn.textContent='❌';
      alert('Backup failed: '+e);
    });
  };
  window._doRestore=function(){
    var inp=document.createElement('input');
    inp.type='file';inp.accept='.zip';
    inp.onchange=function(){
      if(!inp.files[0])return;
      var kr=document.documentElement.lang==='kr';
      if(!confirm(kr?'백업을 복원하시겠습니까? 현재 데이터를 덮어씁니다.':'Restore backup? This will overwrite current data.'))return;
      var btn=document.getElementById('restore-btn');
      if(btn)btn.textContent='⏳...';
      fetch('/api/backup/restore',{
        method:'POST',
        headers:{'X-Session-Token':_tok},
        body:inp.files[0]
      }).then(function(r){return r.json()}).then(function(d){
        if(d.ok){if(btn)btn.textContent='✅';alert(d.message||'Restored!')}
        else{if(btn)btn.textContent='❌';alert(d.error||'Failed')}
      }).catch(function(e){if(btn)btn.textContent='❌';alert('Restore failed: '+e)});
    };
    inp.click();
  };

