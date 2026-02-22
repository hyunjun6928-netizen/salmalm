  /* --- Session Management --- */
  function _genId(){return 's_'+Date.now().toString(36)+'_'+Math.random().toString(36).slice(2,6)}
  function _storageKey(sid){return 'salm_chat_'+sid}

  function loadSessionList(){
    /* Load agents for sidebar dropdown (에이전트 로드) */
    fetch('/api/agents',{headers:{'X-Session-Token':_tok}}).then(function(r){return r.json()}).then(function(d){
      var sel=document.getElementById('agent-select');if(!sel)return;
      var agents=d.agents||[];
      sel.innerHTML=agents.map(function(a){return '<option value="'+a.id+'">🤖 '+a.display_name+'</option>'}).join('');
    }).catch(function(){});
    fetch('/api/sessions',{headers:{'X-Session-Token':_tok}})
    .then(function(r){return r.json()})
    .then(function(d){
      var el=document.getElementById('session-list');if(!el)return;
      if(!d.sessions||!d.sessions.length){
        el.innerHTML='<div style="padding:8px 12px;opacity:0.5;font-size:12px">'+t('no-sessions')+'</div>';
        return;
      }
      var html='';
      var childMap={};
      d.sessions.forEach(function(s){
        if(s.parent_session_id){
          if(!childMap[s.parent_session_id])childMap[s.parent_session_id]=[];
          childMap[s.parent_session_id].push(s);
        }
      });
      var rendered={};
      function renderSession(s,indent){
        if(rendered[s.id])return '';
        rendered[s.id]=true;
        var active=s.id===_currentSession?' style="background:var(--accent-dim);border-radius:8px"':'';
        var title=s.title||s.id;
        if(title.length>40)title=title.slice(0,40)+'...';
        var pad=indent?'padding-left:'+(10+indent*16)+'px;':'';
        var icon=s.parent_session_id?'↳ ':'';
        var h='<div class="nav-item session-item"'+active+' data-action="switchSession" data-sid="'+s.id+'" style="'+pad+'">'
          +'<span class="session-title" data-sid="'+s.id+'" title="Double-click to rename" style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+icon+title+'</span>'
          +'<span class="session-del" data-action="deleteSession" data-sid="'+s.id+'" title="Delete" style="opacity:0.4;cursor:pointer;padding:2px 4px;font-size:11px">✕</span>'
          +'</div>';
        if(childMap[s.id]){childMap[s.id].forEach(function(c){h+=renderSession(c,(indent||0)+1);});}
        return h;
      }
      d.sessions.forEach(function(s){if(!s.parent_session_id)html+=renderSession(s,0);});
      d.sessions.forEach(function(s){if(!rendered[s.id])html+=renderSession(s,1);});
      el.innerHTML=html;
    }).catch(function(){});
  }

  window.switchSession=function(sid){
    /* Save current chat to cache */
    _sessionCache[_currentSession]=chat.innerHTML;
    localStorage.setItem(_storageKey(_currentSession),localStorage.getItem('salm_chat')||'[]');
    /* Switch */
    _currentSession=sid;
    localStorage.setItem('salm_active_session',sid);
    /* Restore from cache or localStorage */
    chat.innerHTML='';
    localStorage.removeItem('salm_chat');
    var stored=localStorage.getItem(_storageKey(sid));
    if(stored){
      localStorage.setItem('salm_chat',stored);
      var hist=JSON.parse(stored);
      if(hist.length){window._restoring=true;hist.forEach(function(m){if(m&&m.role)addMsg(m.role,m.text,m.model)});window._restoring=false}
    }
    loadSessionList();
    /* Refresh model panel to reflect this session's override */
    if(typeof window._loadModelRouter==='function')window._loadModelRouter();
    /* Return to chat view if on settings/usage/dashboard */
    showChat();
    /* Close sidebar on mobile */
    var sb=document.getElementById('sidebar');if(sb&&sb.classList.contains('open'))toggleSidebar();
  };

  window.newSession=function(){
    var sid=_genId();
    _sessionCache[_currentSession]=chat.innerHTML;
    localStorage.setItem(_storageKey(_currentSession),localStorage.getItem('salm_chat')||'[]');
    _currentSession=sid;
    localStorage.setItem('salm_active_session',sid);
    localStorage.removeItem('salm_chat');
    chat.innerHTML='';
    addMsg('system',t('new-session-msg'));
    /* Register new session on server immediately so it appears in sidebar */
    fetch('/api/sessions/create',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},
      body:JSON.stringify({session_id:sid})})
    .then(function(){loadSessionList()})
    .catch(function(){loadSessionList()});
    var sb=document.getElementById('sidebar');if(sb&&sb.classList.contains('open'))toggleSidebar();
  };

  window.deleteSession=function(sid){
    if(!confirm(t('confirm-delete')))return;
    fetch('/api/sessions/delete',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},
      body:JSON.stringify({session_id:sid})}).then(function(){
      localStorage.removeItem(_storageKey(sid));
      delete _sessionCache[sid];
      if(sid===_currentSession){
        /* Switch back to 'web' session and restore its messages */
        _currentSession='web';
        localStorage.setItem('salm_active_session','web');
        var webData=localStorage.getItem(_storageKey('web'))||'[]';
        localStorage.setItem('salm_chat',webData);
        chat.innerHTML='';
        var hist=JSON.parse(webData);
        if(hist.length){window._restoring=true;hist.forEach(function(m){if(m&&m.role)addMsg(m.role,m.text,m.model)});window._restoring=false}
        else{addMsg('system',t('new-session-msg'))}
      }
      loadSessionList();
    }).catch(function(){});
  };
