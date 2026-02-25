import { _closeCmdPalette, _currentSession, _isAutoRouting, _sessionCache, _tok, btn, chat, costEl, fileIconEl, fileNameEl, filePrev, fileSizeEl, imgPrev, input, inputArea, modelBadge, pendingFile, pendingFiles, set_currentSession, set_isAutoRouting, set_pendingFile, set_pendingFiles, set_sessionCache, set_tok, settingsEl, t } from './globals';

  /* --- Keyboard shortcuts + modals --- */
  var _shortcutModal=document.createElement('div');_shortcutModal.id='shortcut-modal';
  _shortcutModal.style.cssText='display:none;position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:var(--bg2);border:1px solid var(--border);border-radius:16px;padding:24px;z-index:10000;min-width:320px;box-shadow:0 20px 60px rgba(0,0,0,0.5)';
  _shortcutModal.innerHTML='<h3 style="margin-bottom:12px;color:var(--accent2)" data-i18n="shortcut-title">\u2328\ufe0f Keyboard Shortcuts</h3><div style="font-size:13px;line-height:2.2;color:var(--text)"><div><kbd style="background:var(--bg3);padding:2px 8px;border-radius:4px;border:1px solid var(--border);font-size:12px">Ctrl+K</kbd> <span data-i18n="shortcut-search">Search sessions</span></div><div><kbd style="background:var(--bg3);padding:2px 8px;border-radius:4px;border:1px solid var(--border);font-size:12px">Ctrl+N</kbd> <span data-i18n="shortcut-newchat">New chat</span></div><div><kbd style="background:var(--bg3);padding:2px 8px;border-radius:4px;border:1px solid var(--border);font-size:12px">Ctrl+Shift+S</kbd> <span data-i18n="shortcut-sidebar">Toggle sidebar</span></div><div><kbd style="background:var(--bg3);padding:2px 8px;border-radius:4px;border:1px solid var(--border);font-size:12px">Escape</kbd> <span data-i18n="shortcut-escape">Close modal / settings</span></div><div><kbd style="background:var(--bg3);padding:2px 8px;border-radius:4px;border:1px solid var(--border);font-size:12px">Ctrl+Shift+P</kbd> <span data-i18n="shortcut-cmdpalette">Command palette</span></div><div><kbd style="background:var(--bg3);padding:2px 8px;border-radius:4px;border:1px solid var(--border);font-size:12px">Ctrl+Shift+P</kbd> <span data-i18n="shortcut-cmdpalette">Command palette</span></div><div><kbd style="background:var(--bg3);padding:2px 8px;border-radius:4px;border:1px solid var(--border);font-size:12px">Ctrl+/</kbd> <span data-i18n="shortcut-help">This help</span></div></div><button data-action="closeShortcutModal" style="margin-top:12px;padding:6px 16px;border-radius:8px;border:none;background:var(--accent);color:#fff;cursor:pointer;font-size:13px" data-i18n="btn-close">Close</button>';
  document.body.appendChild(_shortcutModal);
  var _shortcutOv=document.createElement('div');_shortcutOv.style.cssText='display:none;position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:9999';_shortcutOv.setAttribute('data-action','closeShortcutModal');document.body.appendChild(_shortcutOv);

  var _filterModal=document.createElement('div');_filterModal.id='filter-modal';
  _filterModal.style.cssText='display:none;position:fixed;top:20%;left:50%;transform:translateX(-50%);background:var(--bg2);border:1px solid var(--border);border-radius:16px;padding:20px;z-index:10000;min-width:400px;max-width:90vw;box-shadow:0 20px 60px rgba(0,0,0,0.5)';
  _filterModal.innerHTML='<input id="session-filter-input" type="text" data-i18n-ph="filter-ph" placeholder="Search sessions..." style="width:100%;padding:10px 14px;border-radius:8px;border:1px solid var(--border);background:var(--bg);color:var(--text);font-size:14px;outline:none" autocomplete="off"><div id="session-filter-results" style="margin-top:8px;max-height:300px;overflow-y:auto"></div>';
  document.body.appendChild(_filterModal);
  var _filterOv=document.createElement('div');_filterOv.style.cssText='display:none;position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:9999';_filterOv.setAttribute('data-action','closeFilterModal');document.body.appendChild(_filterOv);

  function _showFilterModal(){
    _filterModal.style.display='block';_filterOv.style.display='block';
    var fi=document.getElementById('session-filter-input');fi.value='';fi.focus();
    _filterSessions('');fi.oninput=function(){_filterSessions(fi.value)};
  }
  function _filterSessions(q){
    fetch('/api/sessions',{headers:{'X-Session-Token':_tok}}).then(function(r){return r.json()}).then(function(d){
      var el=document.getElementById('session-filter-results');
      if(!d.sessions){el.innerHTML='';return}
      var filtered=q?d.sessions.filter(function(s){return(s.title||s.id).toLowerCase().indexOf(q.toLowerCase())>=0}):d.sessions;
      el.innerHTML=filtered.slice(0,20).map(function(s){
        return '<div style="padding:8px 12px;cursor:pointer;border-radius:6px;font-size:13px;color:var(--text)" data-action="filterSelect" data-sid="'+s.id+'">'+(s.title||s.id)+'</div>';
      }).join('')||'<div style="padding:8px;color:var(--text2);font-size:13px">'+t('filter-no-results')+'</div>';
    });
  }
  function _closeAllModals(){_shortcutModal.style.display='none';_shortcutOv.style.display='none';_filterModal.style.display='none';_filterOv.style.display='none'}

  document.addEventListener('keydown',function(e){
    var tag=document.activeElement&&document.activeElement.tagName;
    var isFilterInput=document.activeElement&&document.activeElement.id==='session-filter-input';
    var isTyping=(tag==='INPUT'||tag==='TEXTAREA')&&!isFilterInput;
    if(e.key==='Escape'){e.preventDefault();
      if(typeof _cmdPalette!=='undefined'&&_cmdPalette&&_cmdPalette.classList.contains&&_cmdPalette.classList.contains('open')){_closeCmdPalette();return}
      if(_searchModal&&_searchModal.classList.contains('open')){_closeSearchModal();return}
      if(_shortcutModal.style.display!=='none'||_filterModal.style.display!=='none'){_closeAllModals();return}
      if(settingsEl.style.display==='block'){showChat();return}return}
    if(isTyping)return;
    var mod=e.ctrlKey||e.metaKey;
    if(mod&&e.shiftKey&&(e.key==='P'||e.key==='p')){e.preventDefault();if(typeof _openCmdPalette==='function')_openCmdPalette();return}
    if(mod&&e.key==='k'){e.preventDefault();_openSearchModal();return}
    if(mod&&e.key==='n'){e.preventDefault();window.newSession();return}
    if(mod&&e.shiftKey&&(e.key==='S'||e.key==='s')){e.preventDefault();toggleSidebar();return}
    if(mod&&e.key==='/'){e.preventDefault();_shortcutModal.style.display='block';_shortcutOv.style.display='block';return}
  });
  document.addEventListener('keydown',function(e){
    if(_filterModal.style.display==='none')return;
    if(e.key==='Enter'){var first=document.querySelector('#session-filter-results [data-sid]');if(first){_closeAllModals();switchSession(first.getAttribute('data-sid'))}}
  });

  /* --- Search Modal (Ctrl+K) — full message search --- */
  var _searchModal=document.getElementById('search-modal');
  var _searchInput=document.getElementById('search-input');
  var _searchResults=document.getElementById('search-results');
  var _searchTimer=null;
  function _openSearchModal(){_searchModal.classList.add('open');_searchInput.value='';_searchResults.innerHTML='<div style="padding:16px;text-align:center;color:var(--text2)">'+t('search-type-to-search')+'</div>';_searchInput.focus()}
  function _closeSearchModal(){_searchModal.classList.remove('open')}
  _searchModal.addEventListener('click',function(e){if(e.target===_searchModal)_closeSearchModal()});
  _searchInput.addEventListener('keydown',function(e){
    if(e.key==='Escape'){_closeSearchModal();e.preventDefault()}
    if(e.key==='Enter'){var first=_searchResults.querySelector('.search-item');if(first){var sid=first.getAttribute('data-sid');if(sid){_closeSearchModal();switchSession(sid)}}}
  });
  _searchInput.addEventListener('input',function(){
    clearTimeout(_searchTimer);
    var q=_searchInput.value.trim();
    if(q.length<2){_searchResults.innerHTML='<div style="padding:16px;text-align:center;color:var(--text2)">'+t('search-type-to-search')+'</div>';return}
    _searchTimer=setTimeout(function(){
      fetch('/api/search?q='+encodeURIComponent(q)+'&limit=15',{headers:{'X-Session-Token':_tok}})
      .then(function(r){return r.json()}).then(function(d){
        if(!d.results||!d.results.length){_searchResults.innerHTML='<div style="padding:16px;text-align:center;color:var(--text2)">'+t('search-no-results')+' "'+q+'"</div>';return}
        var html='';
        var re=new RegExp('('+q.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+')','gi');
        d.results.forEach(function(r){
          var snippet=(r.match_snippet||r.content||'').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(re,'<mark>$1</mark>');
          var icon=r.role==='user'?'👤':'😈';
          html+='<div class="search-item" data-action="searchGo" data-sid="'+r.session_id+'">'
            +'<div class="sr-session">'+icon+' '+r.session_id+' · '+(r.updated_at||'')+'</div>'
            +'<div class="sr-snippet">'+snippet+'</div></div>';
        });
        _searchResults.innerHTML=html;
      }).catch(function(){_searchResults.innerHTML='<div style="padding:16px;text-align:center;color:var(--red)">'+t('search-error')+'</div>'});
    },300);
  });
  window._closeAllModals = _closeAllModals;
  window._closeSearchModal = _closeSearchModal;
