(function(){
  const chat=document.getElementById('chat'),input=document.getElementById('input'),
    btn=document.getElementById('send-btn'),costEl=document.getElementById('cost-display'),
    modelBadge=document.getElementById('model-badge'),settingsEl=document.getElementById('settings'),
    filePrev=document.getElementById('file-preview'),fileIconEl=document.getElementById('file-icon'),
    fileNameEl=document.getElementById('file-name'),fileSizeEl=document.getElementById('file-size'),
    imgPrev=document.getElementById('img-preview'),inputArea=document.getElementById('input-area');
  let _tok=sessionStorage.getItem('tok')||'',pendingFile=null;
  var _currentSession=localStorage.getItem('salm_active_session')||'web';
  var _sessionCache={};

  /* Global error handlers — catch unhandled promise rejections silently */
  window.addEventListener('unhandledrejection',function(e){e.preventDefault();console.warn('Unhandled:',e.reason)});

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

  /* --- Restore chat history (deferred until i18n t() is ready) --- */
  window._pendingRestore=function(){
    var stored=localStorage.getItem(_storageKey(_currentSession));
    if(stored)localStorage.setItem('salm_chat',stored);
    var hist=JSON.parse(localStorage.getItem('salm_chat')||'[]');
    if(hist.length){window._restoring=true;hist.forEach(function(m){if(m&&m.role)addMsg(m.role,m.text,m.model)});window._restoring=false}
    loadSessionList();
  };

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

  /* --- New chat --- */
  window.newChat=function(){
    window.newSession();
  };

  /* --- Theme --- */
  var _theme=localStorage.getItem('salm_theme')||'light';
  if(_theme==='light')document.documentElement.setAttribute('data-theme','light');
  window.toggleTheme=function(){
    _theme=_theme==='dark'?'light':'dark';
    document.documentElement.setAttribute('data-theme',_theme==='light'?'light':'');
    localStorage.setItem('salm_theme',_theme);
    var btn=document.getElementById('theme-toggle');
    btn.textContent=_theme==='dark'?'🌙':'☀️';
  };
  document.getElementById('theme-toggle').textContent=_theme==='dark'?'🌙':'☀️';

  /* --- Sidebar toggle (mobile) --- */
  window.toggleSidebar=function(){
    var sb=document.getElementById('sidebar'),ov=document.getElementById('side-overlay');
    sb.classList.toggle('open');ov.classList.toggle('open');
  };

  /* --- Quick command from sidebar --- */
  window.quickCmd=function(msg){
    input.value=msg;input.focus();
    input.dispatchEvent(new Event('input'));
    /* close sidebar on mobile */
    var sb=document.getElementById('sidebar');if(sb.classList.contains('open'))toggleSidebar();
  };

  /* --- Helpers --- */
  var _copyId=0;
  function escHtml(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
  function _renderToolBlocks(t){
    /* Convert <tool_call>...</tool_call> and <tool_result>...</tool_result> to collapsible UI */
    t=t.replace(/<tool_call>\s*([\s\S]*?)\s*<\/tool_call>/g,function(_,body){
      var name='tool';var args='';
      try{var parsed=JSON.parse(body.trim());name=parsed.name||'tool';args=JSON.stringify(parsed.arguments||parsed,null,2)}catch(e){args=body.trim()}
      return '<details style="margin:6px 0;border:1px solid var(--border);border-radius:8px;padding:0;overflow:hidden"><summary style="padding:8px 12px;background:var(--bg2);cursor:pointer;font-size:13px;font-weight:500">🔧 <strong>'+name+'</strong></summary><pre style="padding:8px 12px;margin:0;font-size:11px;overflow-x:auto;background:var(--bg);border-top:1px solid var(--border)">'+args.replace(/</g,'&lt;').replace(/>/g,'&gt;')+'</pre></details>';
    });
    t=t.replace(/<tool_result>\s*([\s\S]*?)\s*<\/tool_result>/g,function(_,body){
      var preview=body.trim();if(preview.length>300)preview=preview.substring(0,300)+'...';
      return '<details style="margin:6px 0;border:1px solid var(--border);border-radius:8px;padding:0;overflow:hidden"><summary style="padding:8px 12px;background:var(--bg2);cursor:pointer;font-size:13px;font-weight:500">📤 Result</summary><pre style="padding:8px 12px;margin:0;font-size:11px;overflow-x:auto;background:var(--bg);border-top:1px solid var(--border)">'+preview.replace(/</g,'&lt;').replace(/>/g,'&gt;')+'</pre></details>';
    });
    return t;
  }
  function renderMd(t){
    if(t.startsWith('<img ')||t.startsWith('<audio '))return t;
    t=_renderToolBlocks(t);
    /* Extract code blocks first, escape everything else, then restore */
    var codeBlocks=[];
    t=t.replace(/```(\w+)?\n?([\s\S]*?)```/g,function(_,lang,code){
      _copyId++;var id='cp'+_copyId;
      var safe='<pre style="position:relative"><button class="copy-btn" data-action="copyCode" data-copy-id="'+id+'" id="btn'+id+'">📋 Copy</button><code id="'+id+'">'+(lang?'/* '+lang+' */\n':'')+escHtml(code)+'</code></pre>';
      codeBlocks.push(safe);return '%%CODEBLOCK'+(codeBlocks.length-1)+'%%';
    });
    /* Escape remaining HTML to prevent XSS */
    t=escHtml(t);
    /* Restore code blocks */
    for(var ci=0;ci<codeBlocks.length;ci++){t=t.replace('%%CODEBLOCK'+ci+'%%',codeBlocks[ci])}
    t=t.replace(/`([^`]+)`/g,function(_,c){return '<code>'+c+'</code>'});
    t=t.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
    t=t.replace(/\*([^*]+)\*/g,'<em>$1</em>');
    /* Tables */
    t=t.replace(/^\|(.+)\|\s*$/gm,function(_,row){
      var cells=row.split('|').map(function(c){return c.trim()});
      if(cells.every(function(c){return /^[-:]+$/.test(c)}))return '';
      return '<tr>'+cells.map(function(c){return '<td style="padding:4px 8px;border:1px solid var(--border)">'+c+'</td>'}).join('')+'</tr>';
    });
    t=t.replace(/((<tr>.*?<[/]tr>\s*)+)/g,'<table style="border-collapse:collapse;margin:8px 0;font-size:13px">$1</table>');
    t=t.replace(/^### (.+)$/gm,'<h4 style="margin:8px 0 4px;font-size:13px;color:var(--accent2)">$1</h4>');
    t=t.replace(/^## (.+)$/gm,'<h3 style="margin:10px 0 6px;font-size:14px;color:var(--accent2)">$1</h3>');
    t=t.replace(/^# (.+)$/gm,'<h2 style="margin:12px 0 8px;font-size:16px;color:var(--accent2)">$1</h2>');
    t=t.replace(/^[•\-] (.+)$/gm,'<div style="padding-left:16px;position:relative"><span style="position:absolute;left:4px">•</span>$1</div>');
    t=t.replace(/^(\d+)\. (.+)$/gm,'<div style="padding-left:16px">$1. $2</div>');
    t=t.replace(/\[([^\]]+)\]\(([^)]+)\)/g,'<a href="$2" target="_blank" style="color:var(--accent2);text-decoration:underline">$1</a>');
    t=t.replace(/uploads[/]([\w.-]+[.](png|jpg|jpeg|gif|webp))/gi,'<img src="/uploads/$1" style="max-width:400px;max-height:400px;border-radius:8px;display:block;margin:8px 0;cursor:pointer" alt="$1" data-action="openImage">');
    t=t.replace(/uploads[/]([\w.-]+[.](mp3|wav|ogg))/gi,'<audio controls src="/uploads/$1" style="display:block;margin:8px 0"></audio> 🔊 $1');
    t=t.replace(/\n/g,'<br>');
    return t;
  }
  window.copyCode=function(id){
    var el=document.getElementById(id);if(!el)return;
    navigator.clipboard.writeText(el.textContent).then(function(){
      var btn=document.getElementById('btn'+id);btn.textContent='✅ Copied';
      setTimeout(function(){btn.textContent='📋 Copy'},1500);
    });
  };
  function addMsg(role,text,model){
    if(text==null)text='';
    const row=document.createElement('div');row.className='msg-row '+role;
    const av=document.createElement('div');av.className='avatar';
    av.textContent=role==='user'?'👤':'😈';
    const wrap=document.createElement('div');
    const bubble=document.createElement('div');bubble.className='bubble';
    /* Parse inline buttons marker: <!--buttons:["a","b","c"]--> */
    var _btnLabels=[];
    var _cleanText=text.replace(/<!--buttons:(\[.*?\])-->/g,function(_,j){try{_btnLabels=JSON.parse(j)}catch(e){}return ''});
    bubble.innerHTML=renderMd(_cleanText);
    if(role==='assistant'&&_btnLabels.length>0){
      var _btnRow=document.createElement('div');_btnRow.style.cssText='display:flex;flex-wrap:wrap;gap:6px;margin-top:8px';
      _btnLabels.forEach(function(label){
        var _b=document.createElement('button');_b.textContent=label;
        _b.style.cssText='padding:6px 14px;border-radius:16px;border:1px solid var(--accent);background:transparent;color:var(--accent);cursor:pointer;font-size:13px;transition:all 0.15s';
        _b.onmouseenter=function(){_b.style.background='var(--accent)';_b.style.color='#fff'};
        _b.onmouseleave=function(){_b.style.background='transparent';_b.style.color='var(--accent)'};
        _b.onclick=function(){input.value=label;doSend()};
        _btnRow.appendChild(_b);
      });
      bubble.appendChild(_btnRow);
    }
    wrap.appendChild(bubble);
    var meta_parts=[];
    if(model){
      /* Show model as badge */
      var modelShort=model.replace(/anthropic\//,'').replace(/openai\//,'').replace(/xai\//,'').replace(/google\//,'');
      meta_parts.push(modelShort);
    }
    meta_parts.push(new Date().toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit'}));
    var mt=document.createElement('div');mt.className='meta';
    /* Add model badge if present */
    if(model&&role==='assistant'){
      var _mShort=(model||'').split('/').pop()||model;
      if(_mShort.length>30)_mShort=_mShort.slice(0,30);
      var badge=document.createElement('span');badge.className='model-tag';badge.textContent=_mShort;
      mt.appendChild(badge);
    }
    mt.appendChild(document.createTextNode(meta_parts.filter(function(p){return!p.includes('/')}).join(' · ')));
    /* TTS button for assistant messages */
    if(role==='assistant'&&_cleanText&&_cleanText.length>5){
      var ttsBtn=document.createElement('button');ttsBtn.className='tts-btn';ttsBtn.textContent='🔊';ttsBtn.title=t('btn-tts-title');
      ttsBtn.onclick=function(){
        if('speechSynthesis' in window){
          window.speechSynthesis.cancel();
          var utter=new SpeechSynthesisUtterance(_cleanText.replace(/<[^>]*>/g,'').replace(/```[\s\S]*?```/g,'').slice(0,5000));
          utter.lang=navigator.language||'ko-KR';
          utter.rate=1.0;
          ttsBtn.textContent='🔇';
          utter.onend=function(){ttsBtn.textContent='🔊'};
          utter.onerror=function(){ttsBtn.textContent='🔊'};
          window.speechSynthesis.speak(utter);
        }
      };
      mt.appendChild(ttsBtn);
    }
    if(role==='assistant'&&text){
      var regenBtn=document.createElement('span');
      regenBtn.textContent=' 🔄';regenBtn.style.cursor='pointer';regenBtn.title=t('btn-regen-title');
      regenBtn.onclick=function(){
        var hist=JSON.parse(localStorage.getItem('salm_chat')||'[]');
        /* Find last user message */
        for(var i=hist.length-1;i>=0;i--){if(hist[i].role==='user'){
          /* Remove this assistant msg and resend */
          hist.splice(i+1);localStorage.setItem('salm_chat',JSON.stringify(hist));
          row.remove();input.value=hist[i].text||'';doSend();break;
        }}
      };
      mt.appendChild(regenBtn);
    }
    /* Edit/Delete buttons for user messages */
    if(role==='user'&&text&&!text.startsWith('<img ')){
      var editActions=document.createElement('span');editActions.className='msg-edit-actions';
      var editBtn=document.createElement('button');editBtn.textContent='✏️';editBtn.title=t('btn-edit');
      editBtn.onclick=function(){
        var origText=text;
        var ta=document.createElement('textarea');ta.className='edit-textarea';ta.value=origText.replace(/<[^>]*>/g,'');
        var bar=document.createElement('div');bar.className='edit-bar';
        var saveB=document.createElement('button');saveB.className='save-btn';saveB.textContent=t('edit-save');
        var cancelB=document.createElement('button');cancelB.className='cancel-btn';cancelB.textContent=t('edit-cancel');
        bar.appendChild(saveB);bar.appendChild(cancelB);
        bubble.innerHTML='';bubble.appendChild(ta);bubble.appendChild(bar);
        ta.focus();ta.setSelectionRange(ta.value.length,ta.value.length);
        cancelB.onclick=function(){bubble.innerHTML=renderMd(origText)};
        saveB.onclick=function(){
          var newText=ta.value.trim();if(!newText)return;
          var allMsgs=chat.querySelectorAll('.msg-row');
          var idx=-1;for(var ei=0;ei<allMsgs.length;ei++){if(allMsgs[ei]===row){idx=ei;break;}}
          fetch('/api/messages/edit',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},
            body:JSON.stringify({session_id:_currentSession,message_index:idx,content:newText})})
          .then(function(r){return r.json()}).then(function(d){
            if(d.ok){
              bubble.innerHTML=renderMd(newText);text=newText;
              var allAfter=chat.querySelectorAll('.msg-row');
              for(var ri=allAfter.length-1;ri>idx;ri--){allAfter[ri].remove();}
              var hist=JSON.parse(localStorage.getItem('salm_chat')||'[]');
              hist=hist.slice(0,idx+1);hist[idx]={role:'user',text:newText,model:null};
              localStorage.setItem('salm_chat',JSON.stringify(hist));
              localStorage.setItem(_storageKey(_currentSession),JSON.stringify(hist));
              if(confirm(t('confirm-regen-after-edit'))){input.value=newText;doSend();}
            }else{bubble.innerHTML=renderMd(origText);alert(d.error||'Edit failed');}
          }).catch(function(){bubble.innerHTML=renderMd(origText)});
        };
        ta.addEventListener('keydown',function(ev){if(ev.key==='Enter'&&!ev.shiftKey){ev.preventDefault();saveB.click();}if(ev.key==='Escape'){cancelB.click();}});
      };
      var delBtn=document.createElement('button');delBtn.textContent='🗑️';delBtn.title=t('btn-delete');
      delBtn.onclick=function(){
        if(!confirm(t('confirm-delete-msg')))return;
        var allMsgs=chat.querySelectorAll('.msg-row');
        var idx=-1;for(var di=0;di<allMsgs.length;di++){if(allMsgs[di]===row){idx=di;break;}}
        fetch('/api/messages/delete',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},
          body:JSON.stringify({session_id:_currentSession,message_index:idx})})
        .then(function(r){return r.json()}).then(function(d){
          if(d.ok){
            row.remove();
            var nextRow=chat.querySelectorAll('.msg-row')[idx];
            if(nextRow&&nextRow.classList.contains('assistant'))nextRow.remove();
            var hist=JSON.parse(localStorage.getItem('salm_chat')||'[]');
            hist.splice(idx,d.removed||1);
            localStorage.setItem('salm_chat',JSON.stringify(hist));
            localStorage.setItem(_storageKey(_currentSession),JSON.stringify(hist));
          }else{alert(d.error||'Delete failed');}
        });
      };
      editActions.appendChild(editBtn);editActions.appendChild(delBtn);
      mt.appendChild(editActions);
    }
    var branchBtn=document.createElement('span');
    branchBtn.textContent=' 🌿';branchBtn.style.cssText='cursor:pointer;opacity:0;transition:opacity 0.15s;font-size:12px';
    branchBtn.title=t('btn-branch-title');
    branchBtn.onclick=function(){
      var allMsgs=chat.querySelectorAll('.msg-row');
      var idx=-1;for(var bi=0;bi<allMsgs.length;bi++){if(allMsgs[bi]===row){idx=bi;break;}}
      if(idx<0)return;
      fetch('/api/sessions/branch',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},
        body:JSON.stringify({session_id:_currentSession,message_index:idx})})
      .then(function(r){return r.json()}).then(function(d){
        if(d.ok){switchSession(d.new_session_id);loadSessionList();}
        else{alert(d.error||t('branch-fail'));}
      });
    };
    mt.appendChild(branchBtn);
    row.onmouseenter=function(){branchBtn.style.opacity='0.7'};
    row.onmouseleave=function(){branchBtn.style.opacity='0'};
    wrap.appendChild(mt);
    row.appendChild(av);row.appendChild(wrap);
    chat.appendChild(row);chat.scrollTop=999999;
    if(!window._restoring){
      var hist=JSON.parse(localStorage.getItem('salm_chat')||'[]');
      hist.push({role:role,text:text,model:model||null});
      if(hist.length>200)hist=hist.slice(-200);
      localStorage.setItem('salm_chat',JSON.stringify(hist));
      localStorage.setItem(_storageKey(_currentSession),JSON.stringify(hist));
      /* Auto-refresh session list after first user message */
      if(role==='user'&&hist.filter(function(m){return m.role==='user'}).length===1)setTimeout(loadSessionList,500);
    }
  }
  var _currentAbort=null;
  function addTyping(statusText){
    const row=document.createElement('div');row.className='msg-row assistant';row.id='typing-row';
    const av=document.createElement('div');av.className='avatar';av.textContent='😈';
    const wrap=document.createElement('div');
    const b=document.createElement('div');b.className='bubble';b.style.display='flex';b.style.alignItems='center';b.style.gap='8px';
    var label=statusText||'';
    b.innerHTML='<div style="flex:1"><div class="typing-indicator"><span></span><span></span><span></span></div>'+(label?' '+label:'')+'</div>';
    var cancelBtn=document.createElement('button');
    cancelBtn.textContent='⏹';cancelBtn.title=t('btn-cancel-gen')||'Stop generating';
    cancelBtn.style.cssText='border:none;background:var(--bg3);color:var(--red,#f87171);border-radius:50%;width:28px;height:28px;cursor:pointer;font-size:14px;flex-shrink:0;transition:all 0.15s';
    cancelBtn.onmouseenter=function(){cancelBtn.style.background='var(--red,#f87171)';cancelBtn.style.color='#fff'};
    cancelBtn.onmouseleave=function(){cancelBtn.style.background='var(--bg3)';cancelBtn.style.color='var(--red,#f87171)'};
    cancelBtn.onclick=function(){window._cancelGeneration()};
    b.appendChild(cancelBtn);
    wrap.appendChild(b);row.appendChild(av);row.appendChild(wrap);
    chat.appendChild(row);chat.scrollTop=999999;
  }
  window._cancelGeneration=function(){
    if(_currentAbort){_currentAbort.abort();_currentAbort=null}
    if(_ws&&_wsReady){try{_ws.send(JSON.stringify({type:'cancel'}))}catch(e){}}
    var tr=document.getElementById('typing-row');if(tr)tr.remove();
    addMsg('assistant','⏹ '+(t('gen-cancelled')||'Generation cancelled.'));
    btn.disabled=false;input.focus();
  };
  function updateTypingStatus(status, detail){
    var el=document.getElementById('typing-row');
    if(!el)return;
    var b=el.querySelector('.bubble');
    if(!b||b._streaming)return;
    var label='';
    if(status==='thinking')label='🧠 Thinking...';
    else if(status==='compacting')label='✨ Compacting context...';
    else if(status==='tool_running')label=detail||'🔧 Running tool...';
    else label=detail||'';
    b.innerHTML='<div class="typing-indicator"><span></span><span></span><span></span></div>'+(label?' '+label:'');
  }

  /* --- File handling --- */
  window.setFile=function(file){
    if(file.type.startsWith('image/')&&file.size>5*1024*1024){alert(t('img-too-large'));return}
    pendingFile=file;
    const isImg=file.type.startsWith('image/');
    fileIconEl.textContent=isImg?'🖼️':'📎';
    fileNameEl.textContent=file.name;
    fileSizeEl.textContent=(file.size/1024).toFixed(1)+'KB';
    filePrev.style.display='block';
    if(isImg){const r=new FileReader();r.onload=function(e){imgPrev.src=e.target.result;imgPrev.style.display='block'};r.readAsDataURL(file)}
    else{imgPrev.style.display='none'}
    input.focus();
  };
  window.clearFile=function(){pendingFile=null;filePrev.style.display='none';imgPrev.style.display='none'};

  /* --- Ctrl+V --- */
  document.addEventListener('paste',function(e){
    var items=e.clipboardData&&e.clipboardData.items;if(!items)return;
    for(var i=0;i<items.length;i++){
      if(items[i].kind==='file'){e.preventDefault();var f=items[i].getAsFile();if(f)window.setFile(f);return}
    }
  });

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
    var f=e.dataTransfer&&e.dataTransfer.files&&e.dataTransfer.files[0];if(f)window.setFile(f)});

  /* --- WebSocket Connection Manager --- */
  var _ws=null,_wsReady=false,_wsBackoff=500,_wsMaxBackoff=5000,_wsTimer=null,_wsPingTimer=null;
  var _wsPendingResolve=null,_wsSendStart=0;

  function _wsUrl(){
    var proto=location.protocol==='https:'?'wss:':'ws:';
    var host=location.hostname||'localhost';
    return proto+'//'+host+':18801';
  }

  function _wsConnect(){
    if(_ws&&(_ws.readyState===WebSocket.CONNECTING||_ws.readyState===WebSocket.OPEN))return;
    try{_ws=new WebSocket(_wsUrl())}catch(e){console.warn('WS connect error:',e);_wsScheduleReconnect();return}
    _ws.onopen=function(){
      _wsReady=true;_wsBackoff=500;
      console.log('WS connected');
      _wsStartPing();
    };
    _ws.onclose=function(){
      _wsReady=false;_wsStopPing();
      if(_wsPendingResolve){_wsPendingResolve({fallback:true});_wsPendingResolve=null}
      _wsScheduleReconnect();
    };
    _ws.onerror=function(){_wsReady=false};
    _ws.onmessage=function(ev){
      var data;try{data=JSON.parse(ev.data)}catch(e){return}
      if(data.type==='pong')return;
      if(data.type==='welcome')return;
      if(data.type==='typing'){updateTypingStatus(data.status,data.detail);return;}
      _wsHandleMessage(data);
    };
  }

  function _wsScheduleReconnect(){
    if(_wsTimer)return;
    _wsTimer=setTimeout(function(){_wsTimer=null;_wsConnect()},_wsBackoff);
    _wsBackoff=Math.min(_wsBackoff*2,_wsMaxBackoff);
  }

  function _wsStartPing(){
    _wsStopPing();
    _wsPingTimer=setInterval(function(){
      if(_ws&&_ws.readyState===WebSocket.OPEN)_ws.send(JSON.stringify({type:'ping'}));
    },30000);
  }
  function _wsStopPing(){if(_wsPingTimer){clearInterval(_wsPingTimer);_wsPingTimer=null}}

  function _wsHandleMessage(data){
    var typingEl=document.getElementById('typing-row');
    if(data.type==='chunk'){
      if(typingEl){var tb=typingEl.querySelector('.bubble');if(tb){if(!tb._streaming){tb._streaming=true;tb.innerHTML=''}tb.innerHTML+=data.text.replace(/</g,'&lt;')}}
    }else if(data.type==='tool'){
      if(typingEl){
        var tb2=typingEl.querySelector('.bubble');
        if(tb2){
          /* Show tool execution detail */
          var toolHtml='<div style="display:flex;align-items:center;gap:8px"><div class="typing-indicator"><span></span><span></span><span></span></div> <span style="font-weight:600">🔧 '+data.name+'</span></div>';
          if(data.input){
            var inputStr=typeof data.input==='string'?data.input:JSON.stringify(data.input,null,2);
            if(inputStr.length>200)inputStr=inputStr.substring(0,200)+'...';
            toolHtml+='<details style="margin-top:4px;font-size:11px"><summary style="cursor:pointer;color:var(--text2)">📥 Input</summary><pre style="background:var(--bg);padding:6px;border-radius:4px;margin:4px 0;overflow-x:auto;font-size:11px;max-height:150px">'+inputStr.replace(/</g,'&lt;')+'</pre></details>';
          }
          /* Append to tool log instead of replacing */
          if(!tb2._toolLog){tb2._toolLog='';tb2.innerHTML=''}
          tb2._toolLog+=toolHtml;
          tb2.innerHTML=tb2._toolLog;
        }
      }
    }else if(data.type==='done'){
      if(typingEl)typingEl.remove();
      var _secs=((Date.now()-_wsSendStart)/1000).toFixed(1);
      addMsg('assistant',data.text||'','⏱️'+_secs+'s');
      fetch('/api/status').then(function(r){return r.json()}).then(function(s){costEl.textContent='$'+s.usage.total_cost.toFixed(4)});
      if(_wsPendingResolve){_wsPendingResolve({done:true});_wsPendingResolve=null}
    }else if(data.type==='error'){
      if(typingEl)typingEl.remove();
      addMsg('assistant','❌ '+data.error);
      if(_wsPendingResolve){_wsPendingResolve({done:true});_wsPendingResolve=null}
    }else if(data.type==='shutdown'){
      if(typingEl)typingEl.remove();
      addMsg('assistant','⚠️ '+(data.message||'Server is shutting down...'));
      if(_wsPendingResolve){_wsPendingResolve({done:true});_wsPendingResolve=null}
    }
  }

  /* Connect on load */
  _wsConnect();

  /* --- Send via WebSocket with SSE fallback --- */
  function _sendViaWs(msg,session){
    return new Promise(function(resolve){
      if(!_wsReady||!_ws||_ws.readyState!==WebSocket.OPEN){resolve({fallback:true});return}
      _wsPendingResolve=resolve;
      var _wsPayload={type:'message',text:msg,session:session};
      if(window._pendingWsImage){_wsPayload.image=window._pendingWsImage.data;_wsPayload.image_mime=window._pendingWsImage.mime;window._pendingWsImage=null}
      _ws.send(JSON.stringify(_wsPayload));
    });
  }

  async function _sendViaSse(chatBody,_sendStart){
    try{
      _currentAbort=new AbortController();
      var r=await fetch('/api/chat/stream',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},
        body:JSON.stringify(chatBody),signal:_currentAbort.signal});
      if(!r.ok||!r.body){throw new Error('stream unavailable')}
      var reader=r.body.getReader();var decoder=new TextDecoder();var buf='';var gotDone=false;
      var typingEl=document.getElementById('typing-row');
      while(true){
        var chunk=await reader.read();
        if(chunk.done)break;
        buf+=decoder.decode(chunk.value,{stream:true});
        var evts=buf.split('\n\n');buf=evts.pop();
        for(var i=0;i<evts.length;i++){
          var evt=evts[i];
          var em=evt.match(/^event: (\w+)\ndata: (.+)$/m);
          if(!em)continue;
          var etype=em[1],edata=JSON.parse(em[2]);
          if(etype==='status'){
            if(typingEl){var tb=typingEl.querySelector('.bubble');if(tb)tb.innerHTML='<div class="typing-indicator"><span></span><span></span><span></span></div> '+edata.text}
          }else if(etype==='tool'){
            if(typingEl){var tb2=typingEl.querySelector('.bubble');if(tb2){
              var toolH='<div style="display:flex;align-items:center;gap:8px"><div class="typing-indicator"><span></span><span></span><span></span></div> <span style="font-weight:600">🔧 '+edata.name+'</span>'+(edata.count?' <span style="font-size:11px;color:var(--text2)">('+edata.count+')</span>':'')+'</div>';
              if(edata.input){var inp=typeof edata.input==='string'?edata.input:JSON.stringify(edata.input,null,2);if(inp.length>200)inp=inp.substring(0,200)+'...';toolH+='<details style="margin-top:4px;font-size:11px"><summary style="cursor:pointer;color:var(--text2)">📥 Input</summary><pre style="background:var(--bg);padding:6px;border-radius:4px;margin:4px 0;overflow-x:auto;font-size:11px;max-height:150px">'+inp.replace(/</g,'&lt;')+'</pre></details>'}
              if(!tb2._toolLog){tb2._toolLog='';tb2.innerHTML=''}
              tb2._toolLog+=toolH;tb2.innerHTML=tb2._toolLog;
            }}
          }else if(etype==='chunk'){
            if(typingEl){var tb4=typingEl.querySelector('.bubble');if(tb4){if(!tb4._streaming){tb4._streaming=true;tb4.innerHTML=''}tb4.innerHTML+=edata.text.replace(/</g,'&lt;')}}
          }else if(etype==='ui_cmd'){
            /* AI-driven UI control */
            var act=edata.action,val=edata.value||'';
            if(act==='set_lang'){window.setLang(val)}
            else if(act==='set_theme'){document.body.setAttribute('data-theme',val);localStorage.setItem('salmalm-theme',val)}
            else if(act==='set_model'){fetch('/api/model/set',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},body:JSON.stringify({model:val})}).then(function(){modelBadge.textContent=val.split('/').pop()})}
            else if(act==='new_session'){window.newSession&&window.newSession()}
            else if(act==='show_panel'){var panelMap={chat:'showChat',settings:'showSettings',dashboard:'showDashboard',sessions:'showSessions',cron:'showCron',memory:'showMemory',docs:'showDocs'};var fn=panelMap[val];if(fn&&window[fn])window[fn]()}
            else if(act==='add_cron'){fetch('/api/cron/add',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},body:JSON.stringify({name:edata.name||'ai-job',interval:edata.interval||3600,prompt:edata.prompt||''})}).then(function(){if(window._loadCron)window._loadCron()})}
          }else if(etype==='done'){
            gotDone=true;
            if(typingEl)typingEl.remove();
            var _secs=((Date.now()-_sendStart)/1000).toFixed(1);
            addMsg('assistant',edata.response||'',(edata.model||'')+' · ⏱️'+_secs+'s');
            fetch('/api/status').then(function(r2){return r2.json()}).then(function(s){costEl.textContent='$'+s.usage.total_cost.toFixed(4)});
          }
        }
      }
      if(!gotDone)throw new Error('stream incomplete');
      if(document.getElementById('typing-row'))document.getElementById('typing-row').remove();
    }catch(streamErr){
      console.warn('SSE failed, falling back:',streamErr);
      var typRow=document.getElementById('typing-row');
      if(typRow){var tb3=typRow.querySelector('.bubble');if(tb3)tb3.innerHTML='<div class="typing-indicator"><span></span><span></span><span></span></div> Processing...'}
      var r2=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},
        body:JSON.stringify(chatBody)});
      var d=await r2.json();
      if(document.getElementById('typing-row'))document.getElementById('typing-row').remove();
      var _secs2=((Date.now()-_sendStart)/1000).toFixed(1);
      if(d.response)addMsg('assistant',d.response,(d.model||'')+' · ⏱️'+_secs2+'s');
      else if(d.error)addMsg('assistant','❌ '+d.error);
      fetch('/api/status').then(function(r3){return r3.json()}).then(function(s){costEl.textContent='$'+s.usage.total_cost.toFixed(4)});
    }
  }

  /* --- Send --- */
  async function doSend(){
    var t=input.value.trim();
    if(!t&&!pendingFile)return;
    /* Client-side /rollback N command */
    var rollMatch=t.match(/^\/rollback\s+(\d+)$/);
    if(rollMatch){
      input.value='';
      var cnt=parseInt(rollMatch[1]);
      fetch('/api/sessions/rollback',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},
        body:JSON.stringify({session_id:_currentSession,count:cnt})})
      .then(function(r){return r.json()}).then(function(d){
        if(d.ok){
          addMsg('assistant',t('rollback-done')+' '+d.removed+' '+t('rollback-pairs'));
          /* Reload session */
          switchSession(_currentSession);
        }else{addMsg('assistant',t('rollback-fail')+' '+(d.error||''));}
      });
      return;
    }
    /* Client-side /branch command */
    if(t==='/branch'){
      input.value='';
      var allMsgs=chat.querySelectorAll('.msg-row');
      var idx=allMsgs.length-1;
      fetch('/api/sessions/branch',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},
        body:JSON.stringify({session_id:_currentSession,message_index:idx})})
      .then(function(r){return r.json()}).then(function(d){
        if(d.ok){switchSession(d.new_session_id);loadSessionList();}
        else{addMsg('assistant',t('branch-fail')+' '+(d.error||''));}
      });
      return;
    }
    input.value='';input.style.height='auto';btn.disabled=true;

    var fileMsg='';var imgData=null;var imgMime=null;
    if(pendingFile){
      var isImg=pendingFile.type.startsWith('image/');
      if(isImg){
        var reader=new FileReader();
        var previewUrl=await new Promise(function(res){reader.onload=function(){res(reader.result)};reader.readAsDataURL(pendingFile)});
        addMsg('user','<img src="'+previewUrl+'" style="max-width:300px;max-height:300px;border-radius:8px;display:block;margin:4px 0" alt="'+pendingFile.name+'">');
      }else{addMsg('user','[📎 '+pendingFile.name+' Uploading...]')}
      var fd=new FormData();fd.append('file',pendingFile);
      try{
        var ur=await fetch('/api/upload',{method:'POST',body:fd});
        var ud=await ur.json();
        if(ud.ok){fileMsg=ud.info;if(ud.image_base64){imgData=ud.image_base64;imgMime=ud.image_mime;window._pendingWsImage={data:imgData,mime:imgMime}}}
        else addMsg('assistant',t('upload-fail')+' '+(ud.error||''));
      }catch(ue){addMsg('assistant',t('upload-error')+' '+ue.message)}
      window.clearFile();
    }

    var msg=(fileMsg?fileMsg+'\n':'')+t;
    if(t)addMsg('user',t);
    if(!msg){btn.disabled=false;return}

    addTyping();
    var _sendStart=Date.now();
    _wsSendStart=_sendStart;
    var chatBody={message:msg,session:_currentSession,lang:_lang};
    if(imgData){chatBody.image_base64=imgData;chatBody.image_mime=imgMime}
    try{
      /* Try WebSocket first, fall back to SSE */
      var wsResult=await _sendViaWs(msg,_currentSession);
      if(wsResult.fallback){
        await _sendViaSse(chatBody,_sendStart);
      }
    }catch(se){var tr2=document.getElementById('typing-row');if(tr2)tr2.remove();addMsg('assistant','❌ Error: '+se.message)}
    finally{btn.disabled=false;input.focus()}
  }
  window.doSend=doSend;

  /* --- Key handler --- */
  input.addEventListener('keydown',function(e){
    if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();doSend()}
  });
  input.addEventListener('input',function(){input.style.height='auto';input.style.height=Math.min(input.scrollHeight,150)+'px'});
  btn.addEventListener('click',function(){doSend()});

  /* --- i18n --- */
  var _i18n={
    en:{
      'nav-chat':'💬 Chat','nav-settings':'⚙️ Settings','nav-dashboard':'📈 Dashboard',
      'tab-general':'⚙️ General','tab-features':'📖 Features',
      'features-search-ph':'Search features...','features-empty':'No features found.',
      'h-model':'🤖 Model Settings','h-keys':'🔑 API Key Management','h-update':'🔄 Update','h-lang':'🌐 Language',
      'lbl-model':'Default Model','lbl-ollama':'Ollama URL',
      'btn-save':'Save','btn-test':'Test','btn-check':'Check for Updates','btn-update':'⬆️ Update',
      'btn-export':'📥 Export','btn-send':'Send',
      'lbl-anthropic':'Anthropic API Key','lbl-openai':'OpenAI API Key',
      'lbl-xai':'xAI API Key (Grok)','lbl-google':'Google API Key (Gemini)','lbl-brave':'Brave Search API Key',
      'welcome-title':'Welcome to SalmAlm','welcome-sub':'Your personal AI gateway',
      'input-ph':'Type a message...',
      'usage-input':'Input','usage-output':'Output','usage-cost':'Cost','usage-uptime':'Uptime',
      'h-vault':'🗝️ Stored Keys','h-usage':'📊 Usage',
      'update-uptodate':'✅ You are up to date','update-checking':'⏳ Checking PyPI...',
      'update-new':'🆕 New version','update-available':'available!','update-download':'⬇️ Download',
      'update-installing':'Running pip install --upgrade salmalm...',
      'nav-webchat':'Web Chat','nav-sysmon':'System Monitor','nav-memory':'Memory',
      'nav-cost':'Cost Tracker','nav-cron':'Cron Manager','nav-python':'Python Exec',
      'nav-image':'Image Gen','nav-tts':'TTS','nav-calendar':'Calendar','nav-mail':'Mail',
      'nav-weather':'Weather','nav-rss':'RSS','nav-remind':'Reminders','nav-translate':'Translate',
      'nav-workflow':'Workflows','nav-qr':'QR Code','nav-notify':'Notifications','nav-fileindex':'File Search',
      'btn-save-ollama':'Save Ollama URL','btn-newchat':'🗨 New Chat',
      'sec-chats':'💬 Chats','sec-channels':'Channels','sec-admin':'Admin','sec-manage':'Manage',
      'h-password':'🔒 Master Password',
      'pw-current':'Current Password','pw-new':'New Password','pw-confirm':'Confirm New Password',
      'pw-new-hint':'New password (4+ chars, leave empty to remove)','pw-confirm-hint':'Re-enter new password',
      'pw-change':'Change','pw-remove':'Remove Password','pw-set':'Set Password',
      'pw-not-set':'No password is currently set.',
      'pw-min4':'Password (4+ characters)','pw-reenter':'Re-enter',
      'pw-mismatch':'New passwords do not match','pw-changed':'✅ Password changed',
      'pw-fail':'❌ Change failed','pw-enter-current':'Please enter current password',
      'h-routing':'🔀 Auto Routing Models',
      'routing-desc':'When "Auto Routing" is selected, messages are classified by complexity and routed to these models:',
      'lbl-route-simple':'⚡ Simple (greetings, short questions)',
      'lbl-route-moderate':'🔧 Moderate (code, analysis, summaries)',
      'lbl-route-complex':'💎 Complex (architecture, long reasoning)',
      'btn-save-routing':'Save Routing',
      'h-soul':'📜 SOUL.md (Custom System Prompt)',
      'soul-desc':'Set a custom system prompt. It will be prepended to all conversations.',
      'soul-path':'~/.salmalm/SOUL.md · Leave empty to restore default',
      'soul-ph':'# My Custom Persona\n\nYou are ...',
      'btn-save-soul':'💾 Save','btn-reset-soul':'🔄 Reset',
      'h-google-oauth':'🔗 Google Integration (Calendar & Gmail)',
      'google-oauth-desc':'OAuth2 integration is required for Google Calendar and Gmail features.',
      'google-oauth-console':'Create an OAuth 2.0 Client ID at Google Cloud Console.',
      'lbl-google-client-id':'Google Client ID','lbl-google-client-secret':'Google Client Secret',
      'btn-google-connect':'🔗 Connect Google Account','btn-google-disconnect':'Disconnect',
      'google-guide-title':'📋 Setup Guide',
      'google-guide-1':'Google Cloud Console → Create/Select Project',
      'google-guide-2':'APIs & Services → Credentials → Create OAuth 2.0 Client ID',
      'google-guide-3':'Application type: Web application',
      'google-guide-4':'Authorized redirect URI:',
      'google-guide-5':'Enter Client ID and Client Secret above',
      'google-guide-6':'Click Connect Google Account',
      'google-connected':'🟢 Connected','google-not-connected':'⚪ Not connected',
      'google-no-client-id':'❌ Save Client ID first',
      'google-redirecting':'🔗 Redirecting to Google login...',
      'google-confirm-disconnect':'Disconnect Google integration?',
      'google-disconnected':'✅ Google integration disconnected',
      'search-ph':'🔍 Search conversations... (Ctrl+K)',
      'search-hint':'Esc to close · Enter to select · Type to search',
      'search-type-to-search':'Type to search across all conversations',
      'search-no-results':'No results for',
      'search-error':'Search error',
      'shortcut-title':'⌨️ Keyboard Shortcuts',
      'shortcut-search':'Search sessions',
      'shortcut-newchat':'New chat','shortcut-sidebar':'Toggle sidebar',
      'shortcut-escape':'Close modal / settings','shortcut-cmdpalette':'Command palette','shortcut-help':'This help',
      'btn-close':'Close',
      'drop-overlay':'📎 Drop image or file here',
      'input-hint':'Enter to send · Shift+Enter newline · Ctrl+V paste · Drag&Drop files',
      'thinking-on':'🧠 Extended Thinking: ON','thinking-off':'Extended Thinking: OFF',
      'btn-thinking-title':'Extended Thinking','btn-attach-title':'Attach file',
      'btn-mic-title':'Voice input','btn-tts-title':'Read aloud',
      'btn-branch-title':'Branch from here','btn-regen-title':'Regenerate',
      'confirm-delete':'Delete this conversation?',
      'no-sessions':'No conversations yet',
      'new-session-msg':'😈 New conversation started.',
      'no-chat-export':'No chat to export.',
      'welcome-msg':'😈 Welcome to SalmAlm!\n\nUse on Telegram and Web simultaneously.\nCtrl+V paste image · Drag&Drop · Enter to send\nType /help for commands',
      'dash-back':'← Back to Chat','dash-title':'📈 Dashboard','dash-desc':'See where tokens go, when sessions spike, and what drives cost.','dash-filters':'Filters','dash-loading':'Loading...',
      'sidebar-running':'Running',
      'sidebar-channels':'📡 Channels',
      'sidebar-tools':'🛠️ Tools ▾',
      'filter-ph':'Search sessions...','filter-no-results':'No results',
      'img-too-large':'Image too large (max 5MB)','mic-denied':'Microphone access denied.','mic-hint-localhost':'💡 Try accessing via http://localhost:18800 instead of 127.0.0.1 (Chrome requires secure context for microphone).',
      'rollback-done':'⏪ Rolled back','rollback-pairs':'message pair(s).',
      'rollback-fail':'❌ Rollback failed:','branch-fail':'❌ Branch failed:',
      'upload-fail':'❌ Upload failed:','upload-error':'❌ Upload error:',
      'btn-edit':'Edit','btn-delete':'Delete',
      'confirm-delete-msg':'Delete this message and its response?',
      'confirm-regen-after-edit':'Regenerate response after edit?',
      'edit-save':'Save','edit-cancel':'Cancel',
      'msg-edited':'✏️ Message edited','msg-deleted':'🗑️ Message deleted',
      'cmd-placeholder':'Type a command...',
      'cmd-new-chat':'New Chat','cmd-export':'Export Chat','cmd-settings':'Settings',
      'cmd-search':'Search','cmd-theme':'Toggle Theme','cmd-sidebar':'Toggle Sidebar',
      'cmd-dashboard':'Dashboard',
      'shortcut-cmdpalette':'Command palette',
      'btn-cancel-gen':'Stop generating','gen-cancelled':'Generation cancelled.',
      'mr-active':'Active Model','mr-providers-title':'📦 Models by Provider','mr-providers-desc':'Click a model to switch. Pricing per 1M tokens (input / output).','mr-keys-desc':'Enter API keys to enable providers. Keys are tested in real-time.',
      'nav-sessions':'📋 Sessions','nav-docs':'📖 Docs','nav-cron':'⏰ Cron Jobs','nav-memory':'🧠 Memory',
      'cron-title':'⏰ Cron Jobs','cron-add':'➕ Add Job','cron-name':'Name','cron-interval':'Interval (seconds)','cron-schedule':'Schedule','cron-at':'Run at (optional)','cron-prompt':'Prompt','btn-cancel':'Cancel',
      'mem-title':'🧠 Memory','mem-select':'Select a memory file to view',
      'sess-title':'📋 Sessions','sess-search-ph':'Search sessions...',
      'ch-title':'📡 Channels','docs-title':'📖 Documentation','docs-search-ph':'Search docs...',
      'tab-debug':'🔬 Debug','h-debug':'🔬 Debug Diagnostics',
      'tab-logs':'📋 Logs','h-logs':'📋 Server Logs',
      'pwa-install-text':'Install SalmAlm as an app','pwa-install-btn':'Install','pwa-dismiss':'Later',
    },
    ko:{
      'nav-chat':'💬 채팅','nav-settings':'⚙️ 설정','nav-dashboard':'📈 대시보드',
      'tab-general':'⚙️ 일반','tab-features':'📖 기능 가이드',
      'features-search-ph':'기능 검색...','features-empty':'검색 결과가 없습니다.',
      'h-model':'🤖 모델 설정','h-keys':'🔑 API 키 관리','h-update':'🔄 업데이트','h-lang':'🌐 언어',
      'lbl-model':'기본 모델','lbl-ollama':'Ollama URL',
      'btn-save':'저장','btn-test':'테스트','btn-check':'업데이트 확인','btn-update':'⬆️ 업데이트',
      'btn-export':'📥 내보내기','btn-send':'전송',
      'lbl-anthropic':'Anthropic API 키','lbl-openai':'OpenAI API 키',
      'lbl-xai':'xAI API 키 (Grok)','lbl-google':'Google API 키 (Gemini)','lbl-brave':'Brave Search API 키',
      'welcome-title':'삶앎에 오신 것을 환영합니다','welcome-sub':'나만의 AI 게이트웨이',
      'input-ph':'메시지를 입력하세요...',
      'usage-input':'입력','usage-output':'출력','usage-cost':'비용','usage-uptime':'가동시간',
      'h-vault':'🗝️ 저장된 키','h-usage':'📊 사용량',
      'update-uptodate':'✅ 최신 버전입니다','update-checking':'⏳ PyPI 확인 중...',
      'update-new':'🆕 새 버전','update-available':'사용 가능!','update-download':'⬇️ 다운로드',
      'update-installing':'pip install --upgrade salmalm 실행 중...',
      'nav-webchat':'웹 채팅','nav-sysmon':'시스템 모니터','nav-memory':'메모리',
      'nav-cost':'비용 추적','nav-cron':'크론 관리','nav-python':'Python 실행',
      'nav-image':'이미지 생성','nav-tts':'음성 합성','nav-calendar':'캘린더','nav-mail':'메일',
      'nav-weather':'날씨','nav-rss':'뉴스 피드','nav-remind':'리마인더','nav-translate':'번역',
      'nav-workflow':'워크플로우','nav-qr':'QR 코드','nav-notify':'알림','nav-fileindex':'파일 검색',
      'btn-save-ollama':'Ollama URL 저장','btn-newchat':'🗨 새 대화',
      'sec-chats':'💬 대화','sec-channels':'채널','sec-admin':'관리','sec-manage':'관리',
      'h-password':'🔒 마스터 비밀번호',
      'pw-current':'현재 비밀번호','pw-new':'새 비밀번호','pw-confirm':'새 비밀번호 확인',
      'pw-new-hint':'새 비밀번호 (4자 이상, 비우면 해제)','pw-confirm-hint':'새 비밀번호 다시 입력',
      'pw-change':'변경','pw-remove':'비밀번호 해제','pw-set':'비밀번호 설정',
      'pw-not-set':'현재 비밀번호가 설정되어 있지 않습니다.',
      'pw-min4':'비밀번호 (4자 이상)','pw-reenter':'다시 입력',
      'pw-mismatch':'새 비밀번호가 일치하지 않습니다','pw-changed':'✅ 비밀번호가 변경되었습니다',
      'pw-fail':'❌ 변경 실패','pw-enter-current':'현재 비밀번호를 입력하세요',
      'h-routing':'🔀 자동 라우팅 모델',
      'routing-desc':'자동 라우팅을 선택하면, 메시지가 복잡도에 따라 분류되어 해당 모델로 전달됩니다:',
      'lbl-route-simple':'⚡ 간단 (인사, 짧은 질문)',
      'lbl-route-moderate':'🔧 보통 (코드, 분석, 요약)',
      'lbl-route-complex':'💎 복잡 (설계, 긴 추론)',
      'btn-save-routing':'라우팅 저장',
      'h-soul':'📜 SOUL.md (커스텀 시스템 프롬프트)',
      'soul-desc':'커스텀 시스템 프롬프트를 설정합니다. 모든 대화의 앞에 삽입됩니다.',
      'soul-path':'~/.salmalm/SOUL.md · 비우면 기본값 복원',
      'soul-ph':'# 나만의 페르소나\n\n당신은 ...',
      'btn-save-soul':'💾 저장','btn-reset-soul':'🔄 초기화',
      'h-google-oauth':'🔗 Google 연동 (Calendar & Gmail)',
      'google-oauth-desc':'Google Calendar, Gmail 기능을 사용하려면 OAuth2 연동이 필요합니다.',
      'google-oauth-console':'Google Cloud Console에서 OAuth 2.0 Client ID를 생성하세요.',
      'lbl-google-client-id':'Google Client ID','lbl-google-client-secret':'Google Client Secret',
      'btn-google-connect':'🔗 Google 계정 연결','btn-google-disconnect':'연결 해제',
      'google-guide-title':'📋 설정 가이드',
      'google-guide-1':'Google Cloud Console → 프로젝트 생성/선택',
      'google-guide-2':'API 및 서비스 → 사용자 인증 정보 → OAuth 2.0 클라이언트 ID 만들기',
      'google-guide-3':'애플리케이션 유형: 웹 애플리케이션',
      'google-guide-4':'승인된 리디렉션 URI:',
      'google-guide-5':'Client ID와 Client Secret을 위에 입력',
      'google-guide-6':'🔗 Google 계정 연결 클릭',
      'google-connected':'🟢 연결됨','google-not-connected':'⚪ 연결 안됨',
      'google-no-client-id':'❌ Client ID를 먼저 저장하세요',
      'google-redirecting':'🔗 Google 로그인 페이지로 이동합니다...',
      'google-confirm-disconnect':'Google 연동을 해제하시겠습니까?',
      'google-disconnected':'✅ Google 연동이 해제되었습니다',
      'search-ph':'🔍 대화 검색... (Ctrl+K)',
      'search-hint':'Esc 닫기 · Enter 선택 · 입력하여 검색',
      'search-type-to-search':'모든 대화에서 검색합니다',
      'search-no-results':'검색 결과 없음:',
      'search-error':'검색 오류',
      'shortcut-title':'⌨️ 키보드 단축키',
      'shortcut-search':'세션 검색',
      'shortcut-newchat':'새 대화','shortcut-sidebar':'사이드바 토글',
      'shortcut-escape':'모달 / 설정 닫기','shortcut-cmdpalette':'커맨드 팔레트','shortcut-help':'이 도움말',
      'btn-close':'닫기',
      'drop-overlay':'📎 이미지 또는 파일을 놓으세요',
      'input-hint':'Enter 전송 · Shift+Enter 줄바꿈 · Ctrl+V 붙여넣기 · 파일 드래그&드롭',
      'thinking-on':'🧠 확장 사고 모드: 켜짐','thinking-off':'확장 사고 모드: 꺼짐',
      'btn-thinking-title':'확장 사고 모드','btn-attach-title':'파일 첨부',
      'btn-mic-title':'음성 입력','btn-tts-title':'소리로 듣기',
      'btn-branch-title':'여기서 분기','btn-regen-title':'다시 생성',
      'confirm-delete':'이 대화를 삭제하시겠습니까?',
      'no-sessions':'아직 대화가 없습니다',
      'new-session-msg':'😈 새 대화가 시작되었습니다.',
      'no-chat-export':'내보낼 대화가 없습니다.',
      'welcome-msg':'😈 삶앎에 오신 것을 환영합니다!\n\nTelegram과 웹에서 동시에 사용할 수 있습니다.\nCtrl+V 이미지 붙여넣기 · 드래그&드롭 · Enter로 전송\n/help로 명령어 확인',
      'dash-back':'← 채팅으로 돌아가기','dash-title':'📈 대시보드','dash-desc':'토큰 사용처, 세션 추이, 비용 분석을 확인하세요.','dash-filters':'필터','dash-loading':'불러오는 중...',
      'sidebar-running':'실행 중',
      'sidebar-channels':'📡 채널',
      'sidebar-tools':'🛠️ 도구 ▾',
      'filter-ph':'세션 검색...','filter-no-results':'결과 없음',
      'img-too-large':'이미지가 너무 큽니다 (최대 5MB)','mic-denied':'마이크 접근이 거부되었습니다.','mic-hint-localhost':'💡 127.0.0.1 대신 http://localhost:18800 으로 접속해보세요 (Chrome은 보안 컨텍스트에서만 마이크를 허용합니다).',
      'rollback-done':'⏪ 되돌리기 완료:','rollback-pairs':'개의 메시지 쌍',
      'rollback-fail':'❌ 되돌리기 실패:','branch-fail':'❌ 분기 실패:',
      'upload-fail':'❌ 업로드 실패:','upload-error':'❌ 업로드 오류:',
      'btn-edit':'편집','btn-delete':'삭제',
      'confirm-delete-msg':'이 메시지와 응답을 삭제하시겠습니까?',
      'confirm-regen-after-edit':'편집 후 응답을 재생성하시겠습니까?',
      'edit-save':'저장','edit-cancel':'취소',
      'msg-edited':'✏️ 메시지가 편집되었습니다','msg-deleted':'🗑️ 메시지가 삭제되었습니다',
      'cmd-placeholder':'명령어 입력...',
      'cmd-new-chat':'새 대화','cmd-export':'대화 내보내기','cmd-settings':'설정',
      'cmd-search':'검색','cmd-theme':'테마 전환','cmd-sidebar':'사이드바 전환',
      'cmd-dashboard':'대시보드',
      'shortcut-cmdpalette':'커맨드 팔레트',
      'btn-cancel-gen':'생성 중단','gen-cancelled':'생성이 중단되었습니다.',
      'mr-active':'활성 모델','mr-providers-title':'📦 프로바이더별 모델','mr-providers-desc':'모델을 클릭하면 전환됩니다. 가격: 1M 토큰당 (입력 / 출력).','mr-keys-desc':'API 키를 입력하면 프로바이더가 활성화됩니다. 키는 실시간으로 테스트됩니다.',
      'nav-sessions':'📋 세션','nav-docs':'📖 문서','nav-cron':'⏰ 크론 작업','nav-memory':'🧠 기억',
      'cron-title':'⏰ 크론 작업','cron-add':'➕ 작업 추가','cron-name':'이름','cron-interval':'간격 (초)','cron-schedule':'스케줄','cron-at':'실행 시각 (선택)','cron-prompt':'프롬프트','btn-cancel':'취소',
      'mem-title':'🧠 기억','mem-select':'보려는 기억 파일을 선택하세요',
      'sess-title':'📋 세션 관리','sess-search-ph':'세션 검색...',
      'ch-title':'📡 채널','docs-title':'📖 문서','docs-search-ph':'문서 검색...',
      'tab-debug':'🔬 디버그','h-debug':'🔬 디버그 진단',
      'tab-logs':'📋 로그','h-logs':'📋 서버 로그',
      'pwa-install-text':'SalmAlm을 앱으로 설치','pwa-install-btn':'설치','pwa-dismiss':'나중에',
    }
  };
  var _lang=localStorage.getItem('salmalm-lang')||(navigator.language&&navigator.language.startsWith('ko')?'ko':'en');
  function t(k){return (_i18n[_lang]||_i18n.en)[k]||(_i18n.en[k]||k)}
  /* Now that t() is defined, restore deferred chat history */
  if(window._pendingRestore){try{window._pendingRestore()}catch(e){console.warn('Chat restore failed:',e);localStorage.removeItem('salm_chat')}delete window._pendingRestore;}
  /* File input change handler */
  var _fileInput=document.getElementById('file-input-hidden');
  if(_fileInput)_fileInput.addEventListener('change',function(){if(this.files[0])window.setFile(this.files[0]);this.value=''});
  /* Tool i18n map: name -> {icon, en, kr, cmd} */
  var _toolI18n={
    apply_patch:{icon:'🩹',en:'Apply Patch',kr:'패치 적용',cmd:'/patch'},
    brave_context:{icon:'🔍',en:'Brave Context',kr:'Brave 컨텍스트',cmd:'Search context with Brave',req:'brave'},
    brave_images:{icon:'🖼️',en:'Brave Images',kr:'Brave 이미지 검색',cmd:'Search images',req:'brave'},
    brave_news:{icon:'📰',en:'Brave News',kr:'Brave 뉴스 검색',cmd:'Search news',req:'brave'},
    brave_search:{icon:'🔎',en:'Brave Search',kr:'Brave 웹 검색',cmd:'Search the web for',req:'brave'},
    briefing:{icon:'📋',en:'Briefing',kr:'브리핑',cmd:'/briefing'},
    browser:{icon:'🌐',en:'Browser',kr:'브라우저 자동화',cmd:'Open browser',req:'browser'},
    calendar_add:{icon:'📅',en:'Add Calendar',kr:'일정 추가',cmd:'Add calendar event',req:'google'},
    calendar_delete:{icon:'🗑️',en:'Delete Calendar',kr:'일정 삭제',cmd:'Delete calendar event',req:'google'},
    calendar_list:{icon:'📆',en:'List Calendar',kr:'일정 목록',cmd:'Show calendar',req:'google'},
    clipboard:{icon:'📋',en:'Clipboard',kr:'클립보드',cmd:'Copy to clipboard'},
    cron_manage:{icon:'⏰',en:'Cron Manager',kr:'크론 관리',cmd:'/cron list'},
    diff_files:{icon:'📊',en:'Diff Files',kr:'파일 비교',cmd:'Compare files'},
    edit_file:{icon:'✏️',en:'Edit File',kr:'파일 편집',cmd:'Edit file'},
    email_inbox:{icon:'📬',en:'Email Inbox',kr:'이메일 수신함',cmd:'Check email inbox',req:'google'},
    email_read:{icon:'📧',en:'Read Email',kr:'이메일 읽기',cmd:'Read email',req:'google'},
    email_search:{icon:'🔍',en:'Search Email',kr:'이메일 검색',cmd:'Search email',req:'google'},
    email_send:{icon:'📤',en:'Send Email',kr:'이메일 발송',cmd:'Send email',req:'google'},
    exec:{icon:'💻',en:'Shell Exec',kr:'셸 실행',cmd:'Run command:'},
    exec_session:{icon:'🖥️',en:'Exec Session',kr:'세션 실행',cmd:'Start exec session'},
    expense:{icon:'💳',en:'Expense',kr:'지출 기록',cmd:'Track expense'},
    file_index:{icon:'📁',en:'File Index',kr:'파일 인덱스',cmd:'Index files'},
    gmail:{icon:'📧',en:'Gmail',kr:'Gmail',cmd:'Check Gmail',req:'google'},
    google_calendar:{icon:'📅',en:'Google Calendar',kr:'구글 캘린더',cmd:'Show Google Calendar',req:'google'},
    hash_text:{icon:'#️⃣',en:'Hash Text',kr:'해시 생성',cmd:'Hash text'},
    health_check:{icon:'🏥',en:'Health Check',kr:'상태 점검',cmd:'/health'},
    http_request:{icon:'🌐',en:'HTTP Request',kr:'HTTP 요청',cmd:'Make HTTP request'},
    image_analyze:{icon:'🔬',en:'Image Analyze',kr:'이미지 분석',cmd:'Analyze image',req:'openai'},
    image_generate:{icon:'🎨',en:'Image Generate',kr:'이미지 생성',cmd:'Generate image:',req:'openai'},
    json_query:{icon:'📦',en:'JSON Query',kr:'JSON 쿼리',cmd:'Query JSON'},
    mcp_manage:{icon:'🔌',en:'MCP Manager',kr:'MCP 관리',cmd:'/mcp list'},
    memory_read:{icon:'🧠',en:'Memory Read',kr:'기억 읽기',cmd:'/memory'},
    memory_search:{icon:'🔍',en:'Memory Search',kr:'기억 검색',cmd:'Search memory for'},
    memory_write:{icon:'📝',en:'Memory Write',kr:'기억 저장',cmd:'Remember this:'},
    node_manage:{icon:'🖧',en:'Node Manager',kr:'노드 관리',cmd:'/node list'},
    note:{icon:'📒',en:'Note',kr:'메모',cmd:'Take note:'},
    notification:{icon:'🔔',en:'Notification',kr:'알림',cmd:'Send notification'},
    plugin_manage:{icon:'🧩',en:'Plugin Manager',kr:'플러그인 관리',cmd:'/plugin list'},
    pomodoro:{icon:'🍅',en:'Pomodoro',kr:'뽀모도로 타이머',cmd:'/pomodoro start'},
    python_eval:{icon:'🐍',en:'Python Exec',kr:'파이썬 실행',cmd:'Calculate in Python:'},
    qr_code:{icon:'📱',en:'QR Code',kr:'QR 코드 생성',cmd:'Generate QR code for'},
    rag_search:{icon:'📚',en:'RAG Search',kr:'RAG 검색',cmd:'Search documents for'},
    read_file:{icon:'📖',en:'Read File',kr:'파일 읽기',cmd:'Read file'},
    regex_test:{icon:'🔤',en:'Regex Test',kr:'정규식 테스트',cmd:'Test regex'},
    reminder:{icon:'⏰',en:'Reminder',kr:'리마인더',cmd:'/remind'},
    routine:{icon:'🔁',en:'Routine',kr:'루틴 관리',cmd:'/routine list'},
    rss_reader:{icon:'📡',en:'RSS Reader',kr:'RSS 리더',cmd:'Read RSS feed'},
    save_link:{icon:'🔗',en:'Save Link',kr:'링크 저장',cmd:'Save link:'},
    screenshot:{icon:'📸',en:'Screenshot',kr:'스크린샷',cmd:'Take screenshot',req:'browser'},
    skill_manage:{icon:'🎓',en:'Skill Manager',kr:'스킬 관리',cmd:'/skill list'},
    stt:{icon:'🎙️',en:'Speech to Text',kr:'음성→텍스트',cmd:'Transcribe audio',req:'openai'},
    sub_agent:{icon:'🤖',en:'Sub Agent',kr:'서브 에이전트',cmd:'/agent list'},
    system_monitor:{icon:'🖥️',en:'System Monitor',kr:'시스템 모니터',cmd:'Check system status'},
    translate:{icon:'🌍',en:'Translate',kr:'번역',cmd:'Translate to Korean:'},
    tts:{icon:'🔊',en:'TTS',kr:'텍스트→음성',cmd:'Convert to speech:',req:'openai'},
    tts_generate:{icon:'🗣️',en:'TTS Generate',kr:'음성 생성',cmd:'Generate speech:',req:'openai'},
    usage_report:{icon:'📊',en:'Usage Report',kr:'사용량 리포트',cmd:'/usage'},
    weather:{icon:'🌤️',en:'Weather',kr:'날씨',cmd:'Check weather in'},
    web_fetch:{icon:'📥',en:'Web Fetch',kr:'웹 페이지 가져오기',cmd:'Fetch URL:'},
    web_search:{icon:'🔎',en:'Web Search',kr:'웹 검색',cmd:'Search the web for'},
    workflow:{icon:'⚙️',en:'Workflow',kr:'워크플로우',cmd:'/workflow list'},
    write_file:{icon:'💾',en:'Write File',kr:'파일 쓰기',cmd:'Write file'},
    ui_control:{icon:'🎛️',en:'UI Control',kr:'UI 제어',cmd:'Change theme to dark'}
  };
  var _allTools=[];
  /* Load dynamic tool list */
  fetch('/api/tools/list',{headers:{'X-Session-Token':_tok}}).then(function(r){return r.json()}).then(function(d){
    _allTools=(d.tools||[]).map(function(t){var m=_toolI18n[t.name];return{name:t.name,icon:m?m.icon:'🔧',en:m?m.en:t.name,kr:m?m.kr:t.name,cmd:m?m.cmd:'',req:m?m.req||'':''}});
    var th=document.getElementById('tools-header');
    if(th)th.textContent='🛠️ '+(_lang==='ko'?'도구':'Tools')+' ('+_allTools.length+') ▾';
    _renderToolsList('');
  }).catch(function(){});
  function _renderToolsList(q){
    var c=document.getElementById('tools-items');if(!c)return;
    var ql=q.toLowerCase();
    var filtered=ql?_allTools.filter(function(t){return t.name.toLowerCase().indexOf(ql)>=0||t.en.toLowerCase().indexOf(ql)>=0||t.kr.indexOf(ql)>=0}):_allTools;
    c.innerHTML=filtered.map(function(t){
      var label=_lang==='ko'?t.kr:t.en;
      var reqAttr=t.req?' data-tool-req="'+t.req+'"':'';
      var reqLabels={google:'Google',brave:'Brave',openai:'OpenAI',browser:'Browser'};
      var reqBadge=t.req?' <span style="font-size:9px;color:#f59e0b;margin-left:auto;background:#fef3c7;padding:1px 6px;border-radius:8px">🔗 '+reqLabels[t.req]+'</span>':'';
      return '<div class="nav-item" data-action="tool-run" data-tool-cmd="'+t.cmd.replace(/"/g,'&quot;')+'" data-tool-name="'+t.name+'"'+reqAttr+' title="'+(t.req?(_lang==='ko'?'설정 필요: ':'Setup required: ')+reqLabels[t.req]:t.name)+'">'+t.icon+' '+label+reqBadge+'</div>';
    }).join('');
    if(!filtered.length)c.innerHTML='<div style="padding:8px 12px;color:var(--text2);font-size:12px">'+(_lang==='ko'?'검색 결과 없음':'No results')+'</div>';
  }
  document.getElementById('tools-search').addEventListener('input',function(){_renderToolsList(this.value)});
  function applyLang(){
    document.querySelectorAll('[data-i18n]').forEach(function(el){
      var k=el.getAttribute('data-i18n');
      if(el.tagName==='INPUT'||el.tagName==='TEXTAREA')el.placeholder=t(k);
      else el.textContent=t(k);
    });
    document.querySelectorAll('[data-i18n-ph]').forEach(function(el){
      el.placeholder=t(el.getAttribute('data-i18n-ph'));
    });
    // Translate Save/Test buttons by content matching
    document.querySelectorAll('button').forEach(function(btn){
      var txt=btn.textContent.trim();
      if(txt==='Save'||txt==='저장')btn.textContent=t('btn-save');
      else if(txt==='Test'||txt==='테스트')btn.textContent=t('btn-test');
    });
    var sel=document.getElementById('s-lang');
    if(sel)sel.value=_lang;
    /* Refresh tools list on lang change */
    var th2=document.getElementById('tools-header');
    if(th2&&_allTools.length)th2.textContent='🛠️ '+(_lang==='ko'?'도구':'Tools')+' ('+_allTools.length+') ▾';
    var ts=document.getElementById('tools-search');
    if(ts){ts.placeholder=_lang==='ko'?'도구 검색...':'Search tools...';_renderToolsList(ts.value)}
  }
  window.setLang=function(v){_lang=v;localStorage.setItem('salmalm-lang',v);applyLang();if(typeof renderFeatures==='function')renderFeatures(document.getElementById('features-search')?document.getElementById('features-search').value:'');};
  /* --- Settings --- */
  var dashView=document.getElementById('dashboard-view');
  var sessView=document.getElementById('sessions-view');
  /* channels panel removed */
  var docsView=document.getElementById('docs-view');
  var cronView=document.getElementById('cron-view');
  var memView=document.getElementById('memory-view');
  function _hideAll(){settingsEl.style.display='none';dashView.style.display='none';sessView.style.display='none';docsView.style.display='none';cronView.style.display='none';memView.style.display='none';chat.style.display='none';inputArea.style.display='none'}
  window.showChat=function(){_hideAll();chat.style.display='flex';inputArea.style.display='block'};
  window.showSessions=function(){_hideAll();sessView.style.display='block';window._loadSessions()};
  window.showChannels=function(){window.showSettings()};
  window.showDocs=function(){_hideAll();docsView.style.display='block';try{window._renderDocs('')}catch(e){console.error('Docs render error:',e);document.getElementById('docs-content').innerHTML='<p style="color:#f87171">Render error: '+e.message+'</p>'}};
  window.showCron=function(){_hideAll();cronView.style.display='block';window._loadCron()};
  window.showMemory=function(){_hideAll();memView.style.display='block';window._loadMemory()};
  window.showSettings=function(){_hideAll();settingsEl.style.display='block';
    /* Load personas */
    if(window.loadPersonas)window.loadPersonas();
    /* Load users panel */
    if(window.loadUsers)window.loadUsers();
    /* Load routing config */
    fetch('/api/routing',{headers:{'X-Session-Token':_tok}}).then(function(r){return r.json()}).then(function(d){
      var cfg=d.config||{};var models=d.available_models||{};
      var opts='';var allModels=[];
      for(var k in models){allModels.push({key:k,val:models[k]})}
      /* Also add model options from the main select */
      var mainSel=document.getElementById('s-model');
      if(mainSel){for(var i=0;i<mainSel.options.length;i++){var o=mainSel.options[i];if(o.value&&o.value!=='auto'){var found=false;for(var j=0;j<allModels.length;j++){if(allModels[j].val===o.value){found=true;break}}if(!found)allModels.push({key:o.value,val:o.value})}}}
      opts='';for(var i=0;i<allModels.length;i++){opts+='<option value="'+allModels[i].val+'">'+allModels[i].val.split('/').pop()+' ('+allModels[i].key+')</option>'}
      ['simple','moderate','complex'].forEach(function(tier){
        var sel=document.getElementById('route-'+tier);if(sel){sel.innerHTML=opts;sel.value=cfg[tier]||''}
      });
    }).catch(function(){});
    /* Load SOUL.md */
    fetch('/api/soul',{headers:{'X-Session-Token':_tok}}).then(function(r){return r.json()}).then(function(d){
      var ed=document.getElementById('soul-editor');if(ed)ed.value=d.content||'';
    }).catch(function(){});
    fetch('/api/vault',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'keys'})})
      .then(function(r){return r.json()}).then(function(d){
        document.getElementById('vault-keys').innerHTML=d.keys.map(function(k){return '<div style="padding:4px 0;font-size:13px;color:var(--text2)">🔑 '+k+'</div>'}).join('')});
    if(window.checkGoogleStatus)window.checkGoogleStatus();
    fetch('/api/status').then(function(r){return r.json()}).then(function(d){
      var u=d.usage,h='<div style="font-size:13px;line-height:2">📥 Input: '+u.total_input.toLocaleString()+' tokens<br>📤 Output: '+u.total_output.toLocaleString()+' tokens<br>💰 Cost: $'+u.total_cost.toFixed(4)+'<br>⏱️ Uptime: '+u.elapsed_hours+'h</div>';
      if(u.by_model){h+='<div style="margin-top:12px;font-size:12px">';for(var m in u.by_model){var v=u.by_model[m];h+='<div style="padding:4px 0;color:var(--text2)">'+m+': '+v.calls+'calls · $'+v.cost.toFixed(4)+'</div>'}h+='</div>'}
      document.getElementById('usage-detail').innerHTML=h});
  };
  window.showUsage=function(){window.showDashboard()};

  /* --- Settings Tabs --- */
  document.querySelectorAll('.settings-tab').forEach(function(tab){
    tab.addEventListener('click',function(){
      document.querySelectorAll('.settings-tab').forEach(function(t){t.classList.remove('active')});
      tab.classList.add('active');
      var which=tab.getAttribute('data-settings-tab');
      document.getElementById('settings-general').style.display=which==='general'?'block':'none';
      document.getElementById('settings-features').style.display=which==='features'?'block':'none';
      document.getElementById('settings-model-router').style.display=which==='model-router'?'block':'none';
      document.getElementById('settings-debug').style.display=which==='debug'?'block':'none';
      document.getElementById('settings-logs').style.display=which==='logs'?'block':'none';
      if(which==='features'&&!window._featuresLoaded){window._featuresLoaded=true;loadFeatures()}
      if(which==='model-router'){window._loadModelRouter()}
      if(which==='debug'){window._loadDebug()}
      if(which==='logs'){window._loadLogs()}
    });
  });

  /* --- Model Router Tab --- */
  /* Model pricing data (per 1M tokens: input/output) */
  var _MODEL_PRICES={
    'claude-opus-4-6':{i:5,o:25},'claude-sonnet-4-6':{i:3,o:15},'claude-haiku-4-5-20251001':{i:1,o:5},
    'gpt-5.2-codex':{i:2,o:8},'gpt-5.1-codex':{i:1.5,o:6},'gpt-4.1':{i:2,o:8},'gpt-4.1-mini':{i:0.4,o:1.6},'gpt-4.1-nano':{i:0.1,o:0.4},
    'o3':{i:10,o:40},'o3-mini':{i:1.1,o:4.4},'o4-mini':{i:1.1,o:4.4},
    'grok-4-0709':{i:3,o:15},'grok-3':{i:3,o:15},'grok-3-mini':{i:0.3,o:0.5},
    'gemini-3-pro-preview':{i:1.25,o:10},'gemini-3-flash-preview':{i:0.15,o:0.6},'gemini-2.5-pro':{i:1.25,o:10},'gemini-2.5-flash':{i:0.15,o:0.6}
  };
  function _getPrice(modelId){
    var short=modelId.split('/').pop();
    return _MODEL_PRICES[short]||null;
  }
  window._loadModelRouter=function(){
    var hdr={'X-Session-Token':_tok};
    fetch('/api/llm-router/providers',{headers:hdr}).then(function(r){return r.json()}).then(function(d){
      var cur=d.current_model||'auto';
      document.getElementById('mr-current-name').textContent=cur==='auto'?'🔄 Auto Routing':cur;
      /* Update s-model dropdown */
      var sel=document.getElementById('s-model');
      if(sel){
        sel.innerHTML='<option value="auto">🔄 Auto Routing</option>';
        d.providers.forEach(function(p){
          p.models.forEach(function(m){
            var opt=document.createElement('option');opt.value=m.full;opt.textContent=m.name;
            if(cur===m.full)opt.selected=true;
            sel.appendChild(opt);
          });
        });
        if(cur==='auto')sel.value='auto';
      }
      /* Provider grid */
      var gridEl=document.getElementById('mr-provider-grid');
      var kr=_lang==='ko';
      var provIcons={anthropic:'🟣',openai:'🟢',xai:'🔵',google:'🟡',openrouter:'🔷',ollama:'🦙'};
      var h='';
      d.providers.forEach(function(p){
        var icon=provIcons[p.name]||'📦';
        var status=p.available?'<span style="color:var(--green,#4ade80)">●</span>':'<span style="color:var(--red,#f87171)">●</span>';
        h+='<div style="border:1px solid var(--border);border-radius:12px;padding:14px;background:var(--bg)">';
        h+='<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">';
        h+='<span style="font-size:18px">'+icon+'</span>';
        h+='<span style="font-weight:600;font-size:14px">'+p.name.charAt(0).toUpperCase()+p.name.slice(1)+'</span>';
        h+=status;
        h+='<span style="font-size:11px;color:var(--text2);margin-left:auto">'+(p.available?(kr?'연결됨':'Connected'):(kr?'키 없음':'No key'))+'</span>';
        h+='</div>';
        p.models.forEach(function(m){
          var isActive=cur&&(cur===m.full||cur===m.name);
          var price=_getPrice(m.full);
          var priceStr=price?'$'+price.i+' / $'+price.o:'';
          h+='<div data-action="switchModel" data-model="'+m.full+'" style="display:flex;align-items:center;gap:8px;padding:8px 10px;border-radius:8px;cursor:pointer;margin-bottom:4px;border:1px solid '+(isActive?'var(--accent)':'transparent')+';background:'+(isActive?'var(--accent-dim)':'transparent')+';transition:all 0.12s"'+(p.available?'':' class="disabled-model"')+'>';
          h+='<div style="flex:1"><div style="font-size:13px;font-weight:500;color:'+(isActive?'var(--accent2)':'var(--text)')+'">'+m.name+(isActive?' ●':'')+'</div>';
          if(priceStr)h+='<div style="font-size:10px;color:var(--text2)">'+priceStr+' '+(kr?'/ 1M 토큰':'/ 1M tok')+'</div>';
          h+='</div></div>';
        });
        h+='</div>';
      });
      gridEl.innerHTML=h;
    }).catch(function(e){
      document.getElementById('mr-provider-grid').innerHTML='<div style="color:var(--red)">Failed to load: '+e+'</div>';
    });
  };

  /* --- Features Guide --- */
  var FEATURE_CATEGORIES=[
    {id:'core',icon:'🤖',title:'Core AI',title_kr:'핵심 AI',features:[
      {name:'Multi-model Routing',name_kr:'멀티 모델 라우팅',desc:'Auto-routes to haiku/sonnet/opus based on complexity',desc_kr:'복잡도에 따라 haiku/sonnet/opus 자동 선택',command:'/model'},
      {name:'Extended Thinking',name_kr:'확장 사고',desc:'Deep reasoning for complex tasks',desc_kr:'복잡한 작업을 위한 심층 추론',command:'/thinking on'},
      {name:'Context Compaction',name_kr:'컨텍스트 압축',desc:'Auto-summarize long sessions',desc_kr:'긴 세션 자동 요약',command:'/compact'},
      {name:'Prompt Caching',name_kr:'프롬프트 캐싱',desc:'Anthropic cache for cost savings',desc_kr:'Anthropic 캐시로 비용 절감',command:'/context'},
      {name:'Self-Evolving Prompt',name_kr:'자가 진화 프롬프트',desc:'AI learns your preferences over time',desc_kr:'대화할수록 선호도 자동 학습',command:'/evolve status'},
      {name:'Mood-Aware Response',name_kr:'기분 감지 응답',desc:'Adjusts tone based on your emotion',desc_kr:'감정에 따라 톤 자동 조절',command:'/mood on'},
      {name:'A/B Split Response',name_kr:'A/B 분할 응답',desc:'Two perspectives on one question',desc_kr:'하나의 질문에 두 관점 동시 응답',command:'/split'}
    ]},
    {id:'tools',icon:'🔧',title:'Tools',title_kr:'도구',features:[
      {name:'Web Search',name_kr:'웹 검색',desc:'Search the internet',desc_kr:'인터넷 검색'},
      {name:'Code Execution',name_kr:'코드 실행',desc:'Run code with sandbox protection',desc_kr:'샌드박스 보호 하에 코드 실행',command:'/bash'},
      {name:'File Operations',name_kr:'파일 작업',desc:'Read, write, edit files',desc_kr:'파일 읽기/쓰기/편집'},
      {name:'Browser Automation',name_kr:'브라우저 자동화',desc:'Control Chrome via CDP',desc_kr:'Chrome DevTools Protocol 제어',command:'/screen'},
      {name:'Image Vision',name_kr:'이미지 분석',desc:'Analyze images with AI',desc_kr:'AI로 이미지 분석'},
      {name:'TTS / STT',name_kr:'음성 입출력',desc:'Text-to-speech and speech-to-text',desc_kr:'텍스트↔음성 변환'},
      {name:'PDF Extraction',name_kr:'PDF 추출',desc:'Extract text from PDFs',desc_kr:'PDF에서 텍스트 추출'}
    ]},
    {id:'personal',icon:'👤',title:'Personal Assistant',title_kr:'개인 비서',features:[
      {name:'Daily Briefing',name_kr:'데일리 브리핑',desc:'Morning/evening digest',desc_kr:'아침/저녁 종합 브리핑',command:'/life'},
      {name:'Smart Reminders',name_kr:'스마트 리마인더',desc:'Natural language time parsing',desc_kr:'자연어 시간 파싱'},
      {name:'Expense Tracker',name_kr:'가계부',desc:'Track spending by category',desc_kr:'카테고리별 지출 추적'},
      {name:'Pomodoro Timer',name_kr:'포모도로 타이머',desc:'25min focus sessions',desc_kr:'25분 집중 세션'},
      {name:'Notes & Links',name_kr:'메모 & 링크',desc:'Save and search notes/links',desc_kr:'메모와 링크 저장/검색'},
      {name:'Routines',name_kr:'루틴',desc:'Daily habit tracking',desc_kr:'일일 습관 추적'},
      {name:'Google Calendar',name_kr:'구글 캘린더',desc:'View, add, delete events',desc_kr:'일정 보기/추가/삭제'},
      {name:'Gmail',name_kr:'지메일',desc:'Read, send, search emails',desc_kr:'이메일 읽기/보내기/검색'},
      {name:'Life Dashboard',name_kr:'인생 대시보드',desc:'All-in-one life overview',desc_kr:'원페이지 인생 현황판',command:'/life'}
    ]},
    {id:'unique',icon:'✨',title:'Unique Features',title_kr:'독자 기능',features:[
      {name:'Thought Stream',name_kr:'생각 스트림',desc:'Quick thought timeline with tags',desc_kr:'해시태그 기반 생각 타임라인',command:'/think'},
      {name:'Time Capsule',name_kr:'타임캡슐',desc:'Messages to your future self',desc_kr:'미래의 나에게 보내는 메시지',command:'/capsule'},
      {name:"Dead Man's Switch",name_kr:'데드맨 스위치',desc:'Emergency actions on inactivity',desc_kr:'비활동 시 긴급 조치',command:'/deadman'},
      {name:'Shadow Mode',name_kr:'분신술',desc:'AI replies in your style when away',desc_kr:'부재 시 내 말투로 대리 응답',command:'/shadow on'},
      {name:'Encrypted Vault',name_kr:'비밀 금고',desc:'Double-encrypted private chat',desc_kr:'이중 암호화 비밀 대화',command:'/vault open'},
      {name:'Agent-to-Agent',name_kr:'AI간 통신',desc:'Negotiate with other SalmAlm instances',desc_kr:'다른 SalmAlm과 자동 협상',command:'/a2a'}
    ]},
    {id:'infra',icon:'⚙️',title:'Infrastructure',title_kr:'인프라',features:[
      {name:'Workflow Engine',name_kr:'워크플로우 엔진',desc:'Multi-step automation pipelines',desc_kr:'다단계 자동화 파이프라인',command:'/workflow'},
      {name:'MCP Marketplace',name_kr:'MCP 마켓',desc:'One-click MCP server install',desc_kr:'MCP 서버 원클릭 설치',command:'/mcp catalog'},
      {name:'Plugin System',name_kr:'플러그인',desc:'Extend with custom plugins',desc_kr:'커스텀 플러그인으로 확장'},
      {name:'Multi-Agent',name_kr:'다중 에이전트',desc:'Isolated sub-agents for parallel work',desc_kr:'병렬 작업용 격리 서브에이전트',command:'/subagents'},
      {name:'Sandboxing',name_kr:'샌드박싱',desc:'OS-native sandbox (bubblewrap/sandbox-exec/rlimit)',desc_kr:'OS 기본 샌드박스 (bubblewrap/sandbox-exec/rlimit)'},
      {name:'Mesh Network',name_kr:'메시 네트워크',desc:'P2P networking between SalmAlm instances',desc_kr:'SalmAlm 인스턴스 간 P2P 네트워킹'},
      {name:'Canvas',name_kr:'캔버스',desc:'Local HTML/code/chart preview server (:18803)',desc_kr:'로컬 HTML/코드/차트 프리뷰 서버 (:18803)'},
      {name:'OAuth Auth',name_kr:'OAuth 인증',desc:'Anthropic/OpenAI subscription auth',desc_kr:'API 키 없이 구독 인증',command:'/oauth'},
      {name:'Prompt Caching',name_kr:'프롬프트 캐싱',desc:'Reduce API costs with caching',desc_kr:'캐싱으로 API 비용 절감',command:'/context'}
    ]},
    {id:'channels',icon:'📱',title:'Channels',title_kr:'채널',features:[
      {name:'Web UI',name_kr:'웹 UI',desc:'Full-featured web interface',desc_kr:'풀기능 웹 인터페이스'},
      {name:'Telegram',name_kr:'텔레그램',desc:'Bot with topics, reactions, groups',desc_kr:'토픽/반응/그룹 지원 봇'},
      {name:'Discord',name_kr:'디스코드',desc:'Bot with threads and reactions',desc_kr:'스레드/반응 지원 봇'},
      {name:'Slack',name_kr:'슬랙',desc:'Event API + Web API',desc_kr:'Event API + Web API'},
      {name:'PWA',name_kr:'PWA',desc:'Install as desktop/mobile app',desc_kr:'데스크톱/모바일 앱 설치'}
    ]},
    {id:'commands',icon:'⌨️',title:'Commands',title_kr:'명령어',features:[
      {name:'/help',desc:'Show help',desc_kr:'도움말'},{name:'/status',desc:'Session status',desc_kr:'세션 상태'},
      {name:'/model',desc:'Switch model',desc_kr:'모델 전환'},{name:'/compact',desc:'Compress context',desc_kr:'컨텍스트 압축'},
      {name:'/context',desc:'Token breakdown',desc_kr:'토큰 분석'},{name:'/usage',desc:'Token/cost tracking',desc_kr:'토큰/비용 추적'},
      {name:'/think',desc:'Record a thought / set thinking level',desc_kr:'생각 기록 / 사고 레벨'},
      {name:'/persona',desc:'Switch persona',desc_kr:'페르소나 전환'},{name:'/branch',desc:'Branch conversation',desc_kr:'대화 분기'},
      {name:'/rollback',desc:'Rollback messages',desc_kr:'메시지 롤백'},{name:'/life',desc:'Life dashboard',desc_kr:'인생 대시보드'},
      {name:'/remind',desc:'Set reminder',desc_kr:'리마인더 설정'},{name:'/expense',desc:'Track expense',desc_kr:'지출 기록'},
      {name:'/pomodoro',desc:'Start pomodoro',desc_kr:'포모도로 시작'},{name:'/note',desc:'Save note',desc_kr:'메모 저장'},
      {name:'/link',desc:'Save link',desc_kr:'링크 저장'},{name:'/routine',desc:'Manage routines',desc_kr:'루틴 관리'},
      {name:'/shadow',desc:'Shadow mode',desc_kr:'분신술'},{name:'/vault',desc:'Encrypted vault',desc_kr:'비밀 금고'},
      {name:'/capsule',desc:'Time capsule',desc_kr:'타임캡슐'},{name:'/deadman',desc:"Dead man's switch",desc_kr:'데드맨 스위치'},
      {name:'/a2a',desc:'Agent-to-agent',desc_kr:'AI간 통신'},{name:'/workflow',desc:'Workflow engine',desc_kr:'워크플로우'},
      {name:'/mcp',desc:'MCP management',desc_kr:'MCP 관리'},{name:'/subagents',desc:'Sub-agents',desc_kr:'서브에이전트'},
      {name:'/oauth',desc:'OAuth setup',desc_kr:'OAuth 설정'},{name:'/bash',desc:'Run shell command',desc_kr:'셸 명령 실행'},
      {name:'/screen',desc:'Browser control',desc_kr:'브라우저 제어'},{name:'/evolve',desc:'Evolving prompt',desc_kr:'진화 프롬프트'},
      {name:'/mood',desc:'Mood detection',desc_kr:'감정 감지'},{name:'/split',desc:'A/B split',desc_kr:'A/B 분할'}
    ]}
  ];

  function loadFeatures(){renderFeatures('')}
  function renderFeatures(q){
    var el=document.getElementById('features-list');
    var empty=document.getElementById('features-empty');
    var kr=_lang==='ko';
    var ql=q.toLowerCase();
    var html='';var total=0;
    FEATURE_CATEGORIES.forEach(function(cat){
      var items=cat.features.filter(function(f){
        if(!ql)return true;
        return (f.name+(f.name_kr||'')+(f.desc||'')+(f.desc_kr||'')+(f.command||'')).toLowerCase().indexOf(ql)>=0;
      });
      if(!items.length)return;
      total+=items.length;
      var open=ql?'open':'';
      html+='<div class="feat-cat '+open+'"><div class="feat-cat-header" data-action="toggleFeatCat"><span class="arrow">▶</span><span>'+cat.icon+' '+(kr&&cat.title_kr?cat.title_kr:cat.title)+'</span><span style="margin-left:auto;font-size:12px;color:var(--text2)">'+items.length+'</span></div><div class="feat-cat-body">';
      items.forEach(function(f){
        var nm=kr&&f.name_kr?f.name_kr:f.name;
        var ds=kr&&f.desc_kr?f.desc_kr:(f.desc||'');
        html+='<div class="feat-card"><div class="feat-name">'+nm+'</div><div class="feat-desc">'+ds+'</div>';
        if(f.command)html+='<button class="feat-cmd" data-action="fillCommand" data-cmd="'+f.command.replace(/"/g,'&quot;')+'">'+f.command+'</button>';
        html+='</div>';
      });
      html+='</div></div>';
    });
    el.innerHTML=html;
    empty.style.display=total?'none':'block';
  }
  document.getElementById('features-search').addEventListener('input',function(){renderFeatures(this.value)});

  /* ── Users Panel (Multi-tenant) ── */
  window.loadUsers=function(){
    fetch('/api/users',{headers:{'Authorization':'Bearer '+(_tok||localStorage.getItem('salm_token')||'')}})
    .then(function(r){return r.json()}).then(function(d){
      if(d.error){document.getElementById('user-list').textContent=d.error;return}
      document.getElementById('mt-toggle').checked=!!d.multi_tenant;
      var sel=document.getElementById('reg-mode');if(sel)sel.value=d.registration_mode||'admin_only';
      var users=d.users||[];
      if(!users.length){document.getElementById('user-list').textContent='No users yet.';return}
      var h='<table style="width:100%;border-collapse:collapse;font-size:12px"><tr style="border-bottom:1px solid var(--border)"><th>User</th><th>Role</th><th>Cost</th><th>Quota (D/M)</th><th>Status</th><th></th></tr>';
      users.forEach(function(u){
        var q=u.quota||{};
        var status=u.enabled?'✅':'⛔';
        h+='<tr style="border-bottom:1px solid var(--border);line-height:2.2">';
        h+='<td>'+u.username+'</td><td>'+u.role+'</td>';
        h+='<td>$'+(u.total_cost||0).toFixed(2)+'</td>';
        h+='<td>$'+(q.current_daily||0).toFixed(2)+'/$'+(q.daily_limit||5).toFixed(0)+' / $'+(q.current_monthly||0).toFixed(2)+'/$'+(q.monthly_limit||50).toFixed(0)+'</td>';
        h+='<td>'+status+'</td>';
        h+='<td>';
        if(u.role!=='admin'){
          var toggleLabel=u.enabled?'Disable':'Enable';
          h+='<button data-action="toggleUser" data-uid="'+u.id+'" data-enabled="'+(!u.enabled)+'" style="font-size:11px;padding:2px 8px;border:1px solid var(--border);border-radius:4px;background:var(--bg3);color:var(--text2);cursor:pointer">'+toggleLabel+'</button> ';
          h+='<button data-action="deleteUser" data-username="'+u.username+'" style="font-size:11px;padding:2px 8px;border:1px solid var(--red);border-radius:4px;background:var(--bg3);color:var(--red);cursor:pointer">Delete</button>';
        }
        h+='</td></tr>';
      });
      h+='</table>';
      document.getElementById('user-list').innerHTML=h;
    }).catch(function(e){document.getElementById('user-list').textContent='Error: '+e});
  };
  window.createUser=function(){
    var name=document.getElementById('new-user-name').value.trim();
    var pw=document.getElementById('new-user-pw').value;
    var role=document.getElementById('new-user-role').value;
    if(!name||!pw){alert('Username and password required');return}
    fetch('/api/users/register',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+(_tok||localStorage.getItem('salm_token')||'')},
      body:JSON.stringify({username:name,password:pw,role:role})})
    .then(function(r){return r.json()}).then(function(d){
      if(d.ok){document.getElementById('new-user-name').value='';document.getElementById('new-user-pw').value='';window.loadUsers()}
      else alert(d.error||'Failed')
    });
  };
  window.toggleUser=function(uid,enabled){
    fetch('/api/users/toggle',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+(_tok||localStorage.getItem('salm_token')||'')},
      body:JSON.stringify({user_id:uid,enabled:enabled})})
    .then(function(){window.loadUsers()});
  };
  window.deleteUser=function(username){
    if(!confirm('Delete user '+username+'?'))return;
    fetch('/api/users/delete',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+(_tok||localStorage.getItem('salm_token')||'')},
      body:JSON.stringify({username:username})})
    .then(function(){window.loadUsers()});
  };
  document.getElementById('mt-toggle').addEventListener('change',function(){
    fetch('/api/tenant/config',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+(_tok||localStorage.getItem('salm_token')||'')},
      body:JSON.stringify({multi_tenant:this.checked})});
  });
  document.getElementById('reg-mode').addEventListener('change',function(){
    fetch('/api/tenant/config',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+(_tok||localStorage.getItem('salm_token')||'')},
      body:JSON.stringify({registration_mode:this.value})});
  });

  var _dashMode='tokens';
  window.showDashboard=function(){
    _hideAll();dashView.style.display='block';
    /* Set default date range to today */
    var today=new Date().toISOString().slice(0,10);
    if(!document.getElementById('dash-from').value){document.getElementById('dash-from').value=today;document.getElementById('dash-to').value=today}
    window._refreshDash();
    var sb=document.getElementById('sidebar');if(sb&&sb.classList.contains('open'))toggleSidebar();
  };
  window._refreshDash=function(){
    var dc=document.getElementById('dashboard-content');dc.innerHTML='<p style="color:var(--text2)">Loading...</p>';
    var hdr={'X-Session-Token':_tok};
    Promise.all([
      fetch('/api/dashboard',{headers:hdr}).then(function(r){return r.json()}),
      fetch('/api/usage/daily',{headers:hdr}).then(function(r){return r.json()})
    ]).then(function(arr){
      var d=arr[0],daily=(arr[1].report||[]);
      var u=d.usage||{};var kr=_lang==='ko';var mode=_dashMode;
      var totalCost=(u.total_cost||0).toFixed(4);
      var totalTokens=(u.total_input||0)+(u.total_output||0);
      var totalCalls=0;var bm=u.by_model||{};
      for(var k in bm)totalCalls+=bm[k].calls||0;
      var uptime=(u.elapsed_hours||0).toFixed(1);
      var sessions=d.sessions||[];
      var totalMsgs=0;sessions.forEach(function(s){totalMsgs+=s.messages||0});
      var h='';
      /* Summary cards */
      h+='<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:20px">';
      var cards=[
        ['💰',kr?'총 비용':'Total Cost','$'+totalCost],
        ['📡',kr?'API 호출':'API Calls',totalCalls],
        ['🔤',kr?'총 토큰':'Total Tokens',totalTokens.toLocaleString()],
        ['💬',kr?'세션':'Sessions',sessions.length],
        ['📝',kr?'메시지':'Messages',totalMsgs],
        ['⏱️',kr?'가동 시간':'Uptime',uptime+'h']
      ];
      cards.forEach(function(c){h+='<div style="background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:14px"><div style="font-size:11px;color:var(--text2);text-transform:uppercase">'+c[0]+' '+c[1]+'</div><div style="font-size:24px;font-weight:700;color:var(--accent);margin-top:4px">'+c[2]+'</div></div>'});
      h+='</div>';
      /* Activity by Time (CSS bar chart) */
      if(daily.length){
        var byDay={};daily.forEach(function(r){
          if(!byDay[r.date])byDay[r.date]={tokens:0,cost:0,calls:0};
          byDay[r.date].tokens+=(r.input_tokens||0)+(r.output_tokens||0);
          byDay[r.date].cost+=r.cost||0;
          byDay[r.date].calls+=r.calls||0;
        });
        var days=Object.keys(byDay).sort();
        var maxVal=0;days.forEach(function(d2){var v=mode==='tokens'?byDay[d2].tokens:byDay[d2].cost;if(v>maxVal)maxVal=v});
        var totalFiltered=0;days.forEach(function(d2){totalFiltered+=mode==='tokens'?byDay[d2].tokens:byDay[d2].cost});
        h+='<div style="background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:16px">';
        h+='<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px"><div><span style="font-weight:600">'+(kr?'시간별 활동':'Activity by Time')+'</span><br><span style="font-size:11px;color:var(--text2)">'+(kr?'일별 추이':'Daily trend')+'</span></div>';
        h+='<div style="font-size:20px;font-weight:700;color:var(--accent)">'+(mode==='tokens'?totalFiltered.toLocaleString()+' tokens':'$'+totalFiltered.toFixed(4))+'</div></div>';
        h+='<div style="display:flex;align-items:flex-end;gap:3px;height:120px;padding:0 4px">';
        days.forEach(function(d2){
          var v=mode==='tokens'?byDay[d2].tokens:byDay[d2].cost;
          var pct=maxVal?Math.max((v/maxVal)*100,2):2;
          var lbl=d2.slice(5);/* MM-DD */
          var tip=d2+': '+(mode==='tokens'?v.toLocaleString()+' tokens':'$'+v.toFixed(4))+' ('+byDay[d2].calls+' calls)';
          h+='<div style="flex:1;display:flex;flex-direction:column;align-items:center" title="'+tip+'"><div style="width:100%;background:var(--accent);border-radius:4px 4px 0 0;height:'+pct+'%;min-height:2px;opacity:0.8"></div><div style="font-size:9px;color:var(--text2);margin-top:4px;white-space:nowrap">'+lbl+'</div></div>';
        });
        h+='</div></div>';
      }
      /* Daily Usage table */
      if(daily.length){
        h+='<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">';
        /* Left: Daily breakdown */
        h+='<div style="background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:16px">';
        h+='<h3 style="font-size:13px;margin-bottom:12px">'+(kr?'일별 사용량':'Daily Usage')+'</h3>';
        var byDayArr=Object.keys(byDay).sort().reverse();
        h+='<table style="width:100%;font-size:12px;border-collapse:collapse">';
        h+='<tr style="color:var(--text2)"><th style="text-align:left;padding:6px">'+(kr?'날짜':'Date')+'</th><th style="text-align:right;padding:6px">'+(kr?'토큰':'Tokens')+'</th><th style="text-align:right;padding:6px">'+(kr?'호출':'Calls')+'</th><th style="text-align:right;padding:6px">'+(kr?'비용':'Cost')+'</th></tr>';
        byDayArr.forEach(function(d2){var v=byDay[d2];h+='<tr style="border-top:1px solid var(--border)"><td style="padding:6px">'+d2+'</td><td style="text-align:right;padding:6px">'+v.tokens.toLocaleString()+'</td><td style="text-align:right;padding:6px">'+v.calls+'</td><td style="text-align:right;padding:6px;color:var(--accent)">$'+v.cost.toFixed(4)+'</td></tr>'});
        h+='</table></div>';
        /* Right: Model breakdown */
        h+='<div style="background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:16px">';
        h+='<h3 style="font-size:13px;margin-bottom:12px">🤖 '+(kr?'모델별':'By Model')+'</h3>';
        if(Object.keys(bm).length){
          h+='<table style="width:100%;font-size:12px;border-collapse:collapse">';
          h+='<tr style="color:var(--text2)"><th style="text-align:left;padding:6px">'+(kr?'모델':'Model')+'</th><th style="text-align:right;padding:6px">'+(kr?'호출':'Calls')+'</th><th style="text-align:right;padding:6px">'+(kr?'비용':'Cost')+'</th></tr>';
          for(var m in bm){var v2=bm[m];h+='<tr style="border-top:1px solid var(--border)"><td style="padding:6px;font-weight:500">'+m+'</td><td style="text-align:right;padding:6px">'+v2.calls+'</td><td style="text-align:right;padding:6px;color:var(--accent)">$'+v2.cost.toFixed(4)+'</td></tr>'}
          h+='</table>';
        }else{h+='<div style="color:var(--text2);font-size:12px">'+(kr?'데이터 없음':'No data')+'</div>'}
        h+='</div></div>';
      }else{
        h+='<div style="background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:24px;text-align:center;color:var(--text2);margin-bottom:16px">'+(kr?'아직 사용 데이터가 없습니다':'No usage data yet')+'</div>';
      }
      dc.innerHTML=h;
    }).catch(function(e){dc.innerHTML='<p style="color:#f87171">Failed to load: '+e.message+'</p>'});
  };
  window.changePw=function(){
    var o=document.getElementById('pw-old').value,n=document.getElementById('pw-new').value,c=document.getElementById('pw-confirm').value;
    var re=document.getElementById('pw-result');
    if(!o||!n){re.innerHTML='<span style="color:#f87171">'+t('pw-enter-current')+'</span>';return}
    if(n!==c){re.innerHTML='<span style="color:#f87171">'+t('pw-mismatch')+'</span>';return}
    if(n.length<4){re.innerHTML='<span style="color:#f87171">'+t('pw-min4')+'</span>';return}
    fetch('/api/vault',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'change_password',old_password:o,new_password:n})}).then(function(r){return r.json()}).then(function(d){
      if(d.ok){re.innerHTML='<span style="color:#4ade80">'+t('pw-changed')+'</span>';document.getElementById('pw-old').value='';document.getElementById('pw-new').value='';document.getElementById('pw-confirm').value=''}
      else{re.innerHTML='<span style="color:#f87171">'+t('pw-fail')+' '+(d.error||'')+'</span>'}
    }).catch(function(e){re.innerHTML='<span style="color:#f87171">❌ '+e.message+'</span>'})};
  window.removePw=function(){
    var o=document.getElementById('pw-old').value;var re=document.getElementById('pw-result');
    if(!o){re.innerHTML='<span style="color:#f87171">'+t('pw-enter-current')+'</span>';return}
    fetch('/api/vault',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'change_password',old_password:o,new_password:''})}).then(function(r){return r.json()}).then(function(d){
      if(d.ok){re.innerHTML='<span style="color:#4ade80">✅ '+t('pw-remove')+'</span>';document.getElementById('pw-old').value='';document.getElementById('pw-section-change').style.display='none';document.getElementById('pw-section-set').style.display='block'}
      else{re.innerHTML='<span style="color:#f87171">'+t('pw-fail')+' '+(d.error||'')+'</span>'}}).catch(function(e){re.innerHTML='<span style="color:#f87171">❌ '+e.message+'</span>'})};
  window.setPw=function(){
    var n=document.getElementById('pw-set-new').value,c=document.getElementById('pw-set-confirm').value;var re=document.getElementById('pw-result');
    if(!n){re.innerHTML='<span style="color:#f87171">'+t('pw-enter-current')+'</span>';return}
    if(n.length<4){re.innerHTML='<span style="color:#f87171">'+t('pw-min4')+'</span>';return}
    if(n!==c){re.innerHTML='<span style="color:#f87171">'+t('pw-mismatch')+'</span>';return}
    fetch('/api/vault',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'change_password',old_password:'',new_password:n})}).then(function(r){return r.json()}).then(function(d){
      if(d.ok){re.innerHTML='<span style="color:#4ade80">'+t('pw-changed')+'</span>';document.getElementById('pw-set-new').value='';document.getElementById('pw-set-confirm').value='';document.getElementById('pw-section-set').style.display='none';document.getElementById('pw-section-change').style.display='block'}
      else{re.innerHTML='<span style="color:#f87171">'+t('pw-fail')+' '+(d.error||'')+'</span>'}}).catch(function(e){re.innerHTML='<span style="color:#f87171">❌ '+e.message+'</span>'})};
  window.checkUpdate=function(){
    var re=document.getElementById('update-result');
    re.innerHTML='<span style="color:var(--text2)">⏳ Checking PyPI...</span>';
    fetch('/api/check-update').then(function(r){return r.json()}).then(function(d){
      document.getElementById('cur-ver').textContent=d.current;
      if(d.latest&&d.latest!==d.current){
        if(d.exe){
          re.innerHTML='<span style="color:#fbbf24">🆕 New version v'+d.latest+' available!</span> <a href="'+d.download_url+'" target="_blank" style="color:#60a5fa">⬇️ Download</a>';
        }else{
          re.innerHTML='<span style="color:#fbbf24">🆕 New version v'+d.latest+' available!</span>';
          document.getElementById('do-update-btn').style.display='inline-block';
        }
      }else{re.innerHTML='<span style="color:#4ade80">✅ You are up to date (v'+d.current+')</span>';
        document.getElementById('do-update-btn').style.display='none'}
    }).catch(function(e){re.innerHTML='<span style="color:#f87171">❌ Check failed: '+e.message+'</span>'})};
  window.doUpdate=function(){
    var re=document.getElementById('update-result');
    var btn=document.getElementById('do-update-btn');
    btn.disabled=true;btn.textContent='⏳ Installing...';
    re.innerHTML='<span style="color:var(--text2)">Running pip install --upgrade salmalm... (up to 30s)</span>';
    fetch('/api/do-update',{method:'POST'}).then(function(r){return r.json()}).then(function(d){
      if(d.ok){re.innerHTML='<span style="color:#4ade80">✅ v'+d.version+' Installed! Please restart the server.</span>';
        var rb=document.createElement('button');rb.className='btn';rb.style.marginTop='8px';rb.textContent='🔄 Restart Now';
        rb.onclick=function(){fetch('/api/restart',{method:'POST'});setTimeout(function(){location.reload()},3000)};re.appendChild(rb);
      }else{re.innerHTML='<span style="color:#f87171">❌ Failed: '+d.error+'</span>'}
      btn.disabled=false;btn.textContent='⬆️ Update'})
    .catch(function(e){re.innerHTML='<span style="color:#f87171">❌ '+e.message+'</span>';btn.disabled=false;btn.textContent='⬆️ Update'})};
  window.saveKey=function(vaultKey,inputId){
    var v=document.getElementById(inputId).value.trim();
    if(!v){addMsg('assistant','Please enter a key');return}
    fetch('/api/vault',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({action:'set',key:vaultKey,value:v})})
    .then(function(r){return r.json()}).then(function(d){
      var re=document.getElementById('key-test-result');
      re.innerHTML='<span style="color:#4ade80">✅ '+vaultKey+' Saved</span>';
      document.getElementById(inputId).value='';
      window.showSettings()})};
  window.testKey=function(provider){
    var re=document.getElementById('key-test-result');
    re.innerHTML='<span style="color:var(--text2)">⏳ '+provider+' Testing...</span>';
    fetch('/api/test-key',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({provider:provider})})
    .then(function(r){return r.json()}).then(function(d){
      re.innerHTML=d.ok?'<span style="color:#4ade80">'+d.result+'</span>':'<span style="color:#f87171">'+d.result+'</span>'})
    .catch(function(e){re.innerHTML='<span style="color:#f87171">❌ Error: '+e.message+'</span>'})
  };
  window.googleConnect=function(){
    var re=document.getElementById('google-result');
    re.innerHTML='<span style="color:var(--text2)">⏳ Checking credentials...</span>';
    fetch('/api/vault',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({action:'get',key:'google_client_id'})})
    .then(function(r){return r.json()}).then(function(d){
      if(!d.value){re.innerHTML='<span style="color:#f87171">'+t('google-no-client-id')+'</span>';return}
      re.innerHTML='<span style="color:#4ade80">'+t('google-redirecting')+'</span>';
      window.open('/api/google/auth','_blank','width=500,height=600')})
    .catch(function(e){re.innerHTML='<span style="color:#f87171">❌ '+e.message+'</span>'})
  };
  window.googleDisconnect=function(){
    var re=document.getElementById('google-result');
    if(!confirm(t('google-confirm-disconnect')))return;
    Promise.all([
      fetch('/api/vault',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'delete',key:'google_refresh_token'})}),
      fetch('/api/vault',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'delete',key:'google_access_token'})})
    ]).then(function(){
      re.innerHTML='<span style="color:#4ade80">'+t('google-disconnected')+'</span>';
      document.getElementById('google-status').innerHTML='<span style="color:var(--text2)">'+t('google-not-connected')+'</span>';
    }).catch(function(e){re.innerHTML='<span style="color:#f87171">❌ '+e.message+'</span>'})
  };
  window.checkGoogleStatus=function(){
    var st=document.getElementById('google-status');
    if(!st)return;
    fetch('/api/vault',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({action:'get',key:'google_refresh_token'})})
    .then(function(r){return r.json()}).then(function(d){
      if(d.value){st.innerHTML='<span style="color:#4ade80">'+t('google-connected')+'</span>'}
      else{st.innerHTML='<span style="color:var(--text2)">'+t('google-not-connected')+'</span>'}
    }).catch(function(){st.innerHTML=''})
  };
  window.setModel=function(m){modelBadge.textContent=m==='auto'?'auto routing':m.split('/').pop();
    fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:'/model '+(m==='auto'?'auto':m),session:_currentSession})})};

  /* --- Drag highlight --- */
  var ia=document.getElementById('input-area');
  ia.addEventListener('dragenter',function(e){e.preventDefault();ia.classList.add('drag-over')});
  ia.addEventListener('dragover',function(e){e.preventDefault()});
  ia.addEventListener('dragleave',function(){ia.classList.remove('drag-over')});
  ia.addEventListener('drop',function(e){e.preventDefault();ia.classList.remove('drag-over');
    var files=e.dataTransfer.files;if(files.length>0){window.setFile(files[0])}});

  /* --- Scroll to bottom button --- */
  var scrollBtn=document.createElement('button');scrollBtn.id='scroll-bottom';scrollBtn.textContent='↓';
  document.body.appendChild(scrollBtn);
  chat.addEventListener('scroll',function(){
    var atBottom=chat.scrollHeight-chat.scrollTop-chat.clientHeight<100;
    scrollBtn.style.display=atBottom?'none':'flex';
  });
  scrollBtn.addEventListener('click',function(){chat.scrollTop=chat.scrollHeight});

  /* --- Syntax highlighting (pure JS, no external libs) --- */
  var _hlKeywords={
    javascript:'\b(function|const|let|var|if|else|for|while|return|import|from|export|default|class|new|this|typeof|instanceof|try|catch|finally|throw|async|await|yield|switch|case|break|continue|do|in|of|null|undefined|true|false|void|delete)\b',
    python:'\b(def|class|if|elif|else|for|while|return|import|from|as|try|except|finally|raise|with|yield|async|await|lambda|pass|break|continue|and|or|not|in|is|None|True|False|global|nonlocal|del|assert)\b',
    bash:'\b(if|then|else|elif|fi|for|while|do|done|case|esac|function|return|exit|echo|export|source|alias|local|readonly|shift|eval|exec|trap|set|cd|pwd|ls|cat|grep|sed|awk|find|sudo|apt|pip|npm|git|docker|curl|wget)\b',
    html:'\b(html|head|body|div|span|p|a|img|script|style|link|meta|title|ul|ol|li|table|tr|td|th|form|input|button|select|option|textarea|nav|header|footer|section|article|main|class|id|href|src|type|rel)\b',
    css:'\b(color|background|margin|padding|border|font|display|flex|grid|position|width|height|top|left|right|bottom|opacity|transition|transform|animation|overflow|none|auto|inherit|solid|relative|absolute|fixed|block|inline|important)\b',
    json:''
  };
  function highlightCode(){
    document.querySelectorAll('.bubble pre code').forEach(function(el){
      if(el.dataset.hl)return;el.dataset.hl='1';
      var h=el.innerHTML;
      var lang='';
      var lm=h.match(/^\/\*\s*(\w+)\s*\*\/\n?/);
      if(lm){lang=lm[1].toLowerCase();h=h.replace(lm[0],'')}
      var tokens=[];
      h=h.replace(/(\/\*[\s\S]*?\*\/)/g,function(m){tokens.push('<span class="cmt">'+m+'</span>');return '%%TOK'+(tokens.length-1)+'%%'});
      h=h.replace(/(\/\/.*$|#(?![\da-f]{3,8}\b).*$)/gm,function(m){tokens.push('<span class="cmt">'+m+'</span>');return '%%TOK'+(tokens.length-1)+'%%'});
      h=h.replace(/(&quot;(?:[^&]|&(?!quot;))*?&quot;|"(?:[^"\\]|\\.)*?"|'(?:[^'\\]|\\.)*?'|`(?:[^`\\]|\\.)*?`)/g,function(m){tokens.push('<span class="str">'+m+'</span>');return '%%TOK'+(tokens.length-1)+'%%'});
      h=h.replace(/\b(\d+\.?\d*(?:e[+-]?\d+)?)\b/gi,function(m){return '<span class="num">'+m+'</span>'});
      var kwPattern=_hlKeywords[lang]||_hlKeywords.javascript+'|'+_hlKeywords.python;
      if(kwPattern){h=h.replace(new RegExp(kwPattern,'g'),function(m){return '<span class="kw">'+m+'</span>'})}
      for(var i=0;i<tokens.length;i++){h=h.replace('%%TOK'+i+'%%',tokens[i])}
      el.innerHTML=h;
    });
  }
  var _hlObs=new MutationObserver(highlightCode);
  _hlObs.observe(chat,{childList:true,subtree:true});

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

  /* --- Welcome (only if no history) --- */
  if(!JSON.parse(localStorage.getItem('salm_chat')||'[]').length){
    addMsg('assistant',t('welcome-msg'),'system');
  }
  input.focus();

  /* --- Restore model preference from server --- */
  fetch('/api/status').then(r=>r.json()).then(d=>{
    if(d.model&&d.model!=='auto'){
      var sel=document.getElementById('s-model');
      if(sel){sel.value=d.model;modelBadge.textContent=d.model.split('/').pop()}
    }
    /* Channel badges */
    var ch=d.channels||{};
    var tgB=document.querySelector('#tg-status .badge');
    var dcB=document.querySelector('#dc-status .badge');
    if(tgB){tgB.textContent=ch.telegram?'ON':'OFF';tgB.style.background=ch.telegram?'var(--accent)':'var(--bg3)';tgB.style.color=ch.telegram?'#fff':'var(--text2)'}
    if(dcB){dcB.textContent=ch.discord?'ON':'OFF';dcB.style.background=ch.discord?'#5865F2':'var(--bg3)';dcB.style.color=ch.discord?'#fff':'var(--text2)'}
  }).catch(()=>{});

  /* --- Notification polling (30s) --- */
  setInterval(async()=>{
    if(!_tok)return;
    try{
      var r=await fetch('/api/notifications',{headers:{'X-Session-Token':_tok}});
      if(!r.ok)return;
      var d=await r.json();
      if(d.notifications&&d.notifications.length){
        d.notifications.forEach(n=>addMsg('assistant',n.text,'notification'));
      }
    }catch(e){}
  },30000);
  /* --- Export menu toggle --- */
  window.toggleExportMenu=function(){var m=document.getElementById('export-menu');m.classList.toggle('open')};
  document.addEventListener('click',function(e){if(!e.target.closest('.export-dropdown')){var m=document.getElementById('export-menu');if(m)m.classList.remove('open')}});
  window.exportMd=function(){document.getElementById('export-menu').classList.remove('open');window.exportChat('md')};
  window.exportJson=function(){document.getElementById('export-menu').classList.remove('open');window.exportChat('json')};
  window.exportServerMd=function(){document.getElementById('export-menu').classList.remove('open');window.open('/api/sessions/'+encodeURIComponent(_currentSession)+'/export?format=md')};
  window.exportServerJson=function(){document.getElementById('export-menu').classList.remove('open');window.open('/api/sessions/'+encodeURIComponent(_currentSession)+'/export?format=json')};

  /* --- Command Palette (Ctrl+Shift+P) --- */
  var _cmdPalette=document.createElement('div');_cmdPalette.id='cmd-palette';
  _cmdPalette.innerHTML='<input id="cmd-input" type="text" placeholder="'+t('cmd-placeholder')+'" autocomplete="off"><div id="cmd-results"></div>';
  document.body.appendChild(_cmdPalette);
  var _cmdOv=document.createElement('div');_cmdOv.id='cmd-overlay';document.body.appendChild(_cmdOv);
  var _cmdCommands=[
    {icon:'🗨',label:'cmd-new-chat',action:function(){window.newSession()},shortcut:'Ctrl+N'},
    {icon:'📥',label:'cmd-export',action:function(){window.exportChat('md')}},
    {icon:'⚙️',label:'cmd-settings',action:function(){window.showSettings()}},
    {icon:'🔍',label:'cmd-search',action:function(){_openSearchModal()},shortcut:'Ctrl+K'},
    {icon:'🎨',label:'cmd-theme',action:function(){window.toggleTheme()}},
    {icon:'☰',label:'cmd-sidebar',action:function(){window.toggleSidebar()}},
    {icon:'📈',label:'cmd-dashboard',action:function(){window.showDashboard()}},
    {icon:'🤖',label:'/model',action:function(){input.value='/model ';input.focus()},raw:true},
    {icon:'🧠',label:'/thinking',action:function(){window.toggleThinking()},raw:true},
    {icon:'📦',label:'/compact',action:function(){input.value='/compact';doSend()},raw:true},
    {icon:'⏪',label:'/rollback',action:function(){input.value='/rollback';doSend()},raw:true},
    {icon:'🌿',label:'/branch',action:function(){input.value='/branch';doSend()},raw:true},
    {icon:'📜',label:'/soul',action:function(){input.value='/soul';doSend()},raw:true},
    {icon:'🔊',label:'/tts',action:function(){input.value='/tts ';input.focus()},raw:true},
    {icon:'🎤',label:'/voice',action:function(){window.toggleMic()},raw:true},
    {icon:'❓',label:'/help',action:function(){input.value='/help';doSend()},raw:true},
  ];
  var _cmdSel=0;
  function _fuzzyMatch(query,text){query=query.toLowerCase();text=text.toLowerCase();if(!query)return true;var qi=0;for(var ti=0;ti<text.length&&qi<query.length;ti++){if(text[ti]===query[qi])qi++}return qi===query.length}
  function _renderCmdResults(q){
    var el=document.getElementById('cmd-results');
    var filtered=_cmdCommands.filter(function(c){var label=c.raw?c.label:t(c.label);return _fuzzyMatch(q,label)||_fuzzyMatch(q,c.icon+' '+label)});
    _cmdSel=0;
    el.innerHTML=filtered.map(function(c,i){
      var label=c.raw?c.label:t(c.label);
      var sc=c.shortcut?'<span class="cmd-shortcut">'+c.shortcut+'</span>':'';
      return '<div class="cmd-item'+(i===0?' selected':'')+'" data-cmd-idx="'+i+'"><span class="cmd-icon">'+c.icon+'</span><span class="cmd-label">'+label+'</span>'+sc+'</div>';
    }).join('');
    el._filtered=filtered;
  }
  function _openCmdPalette(){_cmdPalette.classList.add('open');_cmdOv.classList.add('open');var ci=document.getElementById('cmd-input');ci.value='';ci.focus();_renderCmdResults('');ci.oninput=function(){_renderCmdResults(ci.value)}}
  function _closeCmdPalette(){_cmdPalette.classList.remove('open');_cmdOv.classList.remove('open')}
  _cmdOv.addEventListener('click',_closeCmdPalette);
  document.addEventListener('keydown',function(e){
    if(!_cmdPalette||!_cmdPalette.classList.contains('open'))return;
    var el=document.getElementById('cmd-results');var filtered=el._filtered||[];
    var items=el.querySelectorAll('.cmd-item');
    if(e.key==='ArrowDown'){e.preventDefault();_cmdSel=Math.min(_cmdSel+1,items.length-1);items.forEach(function(it,i){it.classList.toggle('selected',i===_cmdSel)})}
    else if(e.key==='ArrowUp'){e.preventDefault();_cmdSel=Math.max(_cmdSel-1,0);items.forEach(function(it,i){it.classList.toggle('selected',i===_cmdSel)})}
    else if(e.key==='Enter'){e.preventDefault();if(filtered[_cmdSel]){_closeCmdPalette();filtered[_cmdSel].action()}}
  });
  document.getElementById('cmd-results').addEventListener('click',function(e){
    var item=e.target.closest('.cmd-item');if(!item)return;
    var idx=parseInt(item.getAttribute('data-cmd-idx'));
    var el=document.getElementById('cmd-results');var filtered=el._filtered||[];
    if(filtered[idx]){_closeCmdPalette();filtered[idx].action();}
  });

  /* --- PWA Install Prompt --- */
  var _deferredPrompt=null;
  var _pwaBanner=document.createElement('div');_pwaBanner.id='pwa-install';
  _pwaBanner.innerHTML='<span>😈 '+t('pwa-install-text')+'</span><button class="install-btn" data-action="pwaInstall">'+t('pwa-install-btn')+'</button><button class="dismiss-btn" data-action="pwaDismiss">'+t('pwa-dismiss')+'</button>';
  document.body.appendChild(_pwaBanner);
  window.addEventListener('beforeinstallprompt',function(e){e.preventDefault();_deferredPrompt=e;if(!localStorage.getItem('pwa-dismissed'))_pwaBanner.classList.add('show')});
  window.pwaInstall=function(){if(_deferredPrompt){_deferredPrompt.prompt();_deferredPrompt.userChoice.then(function(){_deferredPrompt=null;_pwaBanner.classList.remove('show')})}};
  window.pwaDismiss=function(){_pwaBanner.classList.remove('show');localStorage.setItem('pwa-dismissed','1')};

  applyLang();

  /* --- CSP-safe event delegation --- */
  var _qcMap={'qc-help':'/help','qc-sysmon':'Check system status','qc-memory':'Show memory files',
    'qc-cost':'Show cost report','qc-cron':'Show cron jobs','qc-python':'Calculate 1+1 in Python',
    'qc-image':'Generate image: a cat in galaxy','qc-tts':'Convert to speech: Hello world'};
  document.addEventListener('click',function(e){
    var el=e.target.closest('[data-action]');if(!el)return;
    var a=el.getAttribute('data-action');
    if(a==='newSession')window.newSession();
    else if(a==='showChat')window.showChat();
    else if(a==='showSettings')window.showSettings();
    else if(a==='showUsage')window.showDashboard();
    else if(a==='showDashboard')window.showDashboard();
    else if(a==='refreshDashboard')window._refreshDash();
    else if(a==='dashRange'){var r=el.getAttribute('data-range');var t2=new Date();var f=new Date();if(r==='today'){}else if(r==='7d')f.setDate(f.getDate()-7);else if(r==='30d')f.setDate(f.getDate()-30);document.getElementById('dash-from').value=f.toISOString().slice(0,10);document.getElementById('dash-to').value=t2.toISOString().slice(0,10);window._refreshDash()}
    else if(a==='dashMode'){_dashMode=el.getAttribute('data-mode');document.getElementById('dash-mode-tokens').style.background=_dashMode==='tokens'?'var(--accent)':'var(--bg3)';document.getElementById('dash-mode-tokens').style.color=_dashMode==='tokens'?'#fff':'var(--text)';document.getElementById('dash-mode-cost').style.background=_dashMode==='cost'?'var(--accent)':'var(--bg3)';document.getElementById('dash-mode-cost').style.color=_dashMode==='cost'?'#fff':'var(--text)';window._refreshDash()}
    else if(a==='showCron')window.showCron();
    else if(a==='showMemory')window.showMemory();
    else if(a==='refreshCron')window._loadCron();
    else if(a==='refreshMemory')window._loadMemory();
    else if(a==='addCronForm'){document.getElementById('cron-add-form').style.display='block'}
    else if(a==='cancelCron'){document.getElementById('cron-add-form').style.display='none'}
    else if(a==='saveCron'){window._saveCron()}
    else if(a==='toggleCronJob'){fetch('/api/cron/toggle',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},body:JSON.stringify({id:el.getAttribute('data-cron-id')})}).then(function(){window._loadCron()})}
    else if(a==='deleteCronJob'){if(confirm(_lang==='ko'?'삭제하시겠습니까?':'Delete this job?'))fetch('/api/cron/delete',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},body:JSON.stringify({id:el.getAttribute('data-cron-id')})}).then(function(){window._loadCron()})}
    else if(a==='memRead'){window._readMemFile(el.getAttribute('data-mem-path'))}
    else if(a==='showSessions')window.showSessions();
    else if(a==='showChannels')window.showChannels();
    else if(a==='showDocs')window.showDocs();
    else if(a==='refreshSessions')window._loadSessions();
    else if(a==='sess-delete'){var sid=el.getAttribute('data-sid');if(sid&&confirm((_lang==='ko'?'세션을 삭제하시겠습니까?':'Delete this session?')+'\n'+sid)){fetch('/api/sessions/delete',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},body:JSON.stringify({session_id:sid})}).then(function(){window._loadSessions();loadSessions()})}}
    else if(a==='sess-open'){var sid2=el.getAttribute('data-sid');if(sid2){window._currentSession=sid2;showChat();loadSessions();loadChatHistory(sid2)}}
    else if(a==='toggleSidebar')window.toggleSidebar();
    else if(a==='toggleTheme')window.toggleTheme();
    else if(a==='openDashboard')window.showDashboard();
    else if(a==='exportChat')window.exportChat('md');
    else if(a==='toggleExportMenu')window.toggleExportMenu();
    else if(a==='exportMd')window.exportMd();
    else if(a==='exportJson')window.exportJson();
    else if(a==='exportServerMd')window.exportServerMd();
    else if(a==='exportServerJson')window.exportServerJson();
    else if(a==='pwaInstall')window.pwaInstall();
    else if(a==='pwaDismiss')window.pwaDismiss();
    else if(a==='toggleThinking')window.toggleThinking();
    else if(a==='toggleMic')window.toggleMic();
    else if(a==='clearFile')window.clearFile();
    else if(a==='toggleTools'){var tl=document.getElementById('tools-list');tl.style.display=tl.style.display==='none'?'block':'none'}
    else if(a==='tool-run'){var treq=el.getAttribute('data-tool-req');if(treq){var kr2=_lang==='ko';var reqMap={
      google:{title:kr2?'🔗 Google OAuth 연동 필요':'🔗 Google OAuth Required',
        msg:kr2?'이 도구는 Google 계정 연동이 필요합니다.\n\n설정 방법:\n1. Settings → Google Integration\n2. Google Cloud Console에서 OAuth Client ID 생성\n3. Client ID와 Secret 입력\n4. "Connect Google Account" 클릭\n\n연동 후 Gmail, Calendar 도구를 사용할 수 있습니다.':'This tool requires Google account connection.\n\nSetup:\n1. Settings → Google Integration\n2. Create OAuth Client ID at Google Cloud Console\n3. Enter Client ID and Secret\n4. Click "Connect Google Account"\n\nAfter connecting, Gmail and Calendar tools will work.'},
      brave:{title:kr2?'🔑 Brave API 키 필요':'🔑 Brave API Key Required',
        msg:kr2?'이 도구는 Brave Search API 키가 필요합니다.\n\n설정 방법:\n1. https://brave.com/search/api/ 에서 API 키 발급\n2. Settings → Model 탭 → Brave API Key 입력\n\n입력 후 웹 검색, 이미지 검색, 뉴스 검색을 사용할 수 있습니다.':'This tool requires a Brave Search API key.\n\nSetup:\n1. Get an API key at https://brave.com/search/api/\n2. Settings → Model tab → Enter Brave API Key\n\nAfter setup, web search, image search, and news search will work.'},
      openai:{title:kr2?'🔑 OpenAI API 키 필요':'🔑 OpenAI API Key Required',
        msg:kr2?'이 도구는 OpenAI API 키가 필요합니다.\n\n설정 방법:\n1. https://platform.openai.com/api-keys 에서 키 발급\n2. Settings → Model 탭 → OpenAI API Key 입력\n\n입력 후 이미지 생성(DALL-E), 음성 변환(TTS/STT) 등을 사용할 수 있습니다.':'This tool requires an OpenAI API key.\n\nSetup:\n1. Get a key at https://platform.openai.com/api-keys\n2. Settings → Model tab → Enter OpenAI API Key\n\nAfter setup, image generation (DALL-E), TTS/STT will work.'},
      browser:{title:kr2?'🌐 브라우저 환경 필요':'🌐 Browser Environment Required',
        msg:kr2?'이 도구는 Playwright 또는 Selenium이 설치된 환경에서만 작동합니다.\n\n현재는 서버 환경(headless)에서 제한적으로 지원됩니다.\n로컬 데스크톱 환경에서 사용하세요.':'This tool requires Playwright or Selenium.\n\nCurrently limited support in server (headless) environments.\nUse on a local desktop environment.'}
    };var info=reqMap[treq]||{title:'⚠️',msg:kr2?'추가 설정이 필요합니다':'Additional setup required'};alert(info.title+'\n\n'+info.msg)}else{var tcmd=el.getAttribute('data-tool-cmd');if(tcmd)window.quickCmd(tcmd)}}
    else if(a==='toggleDocDetail'){var dd=el.querySelector('.doc-detail');var ch=el.querySelector('.doc-chevron');if(dd){var vis=dd.style.display==='none';dd.style.display=vis?'block':'none';if(ch)ch.textContent=vis?'▼':'▶'}}
    else if(a.startsWith('qc-'))window.quickCmd(_qcMap[a]);
    else if(a==='save-anthropic')window.saveKey('anthropic_api_key','sk-anthropic');
    else if(a==='test-anthropic')window.testKey('anthropic');
    else if(a==='save-openai')window.saveKey('openai_api_key','sk-openai');
    else if(a==='test-openai')window.testKey('openai');
    else if(a==='save-xai')window.saveKey('xai_api_key','sk-xai');
    else if(a==='test-xai')window.testKey('xai');
    else if(a==='save-google')window.saveKey('google_api_key','sk-google');
    else if(a==='test-google')window.testKey('google');
    else if(a==='save-brave')window.saveKey('brave_api_key','sk-brave');
    else if(a==='save-google-client-id')window.saveKey('google_client_id','sk-google-client-id');
    else if(a==='save-google-client-secret')window.saveKey('google_client_secret','sk-google-client-secret');
    else if(a==='googleConnect')window.googleConnect();
    else if(a==='googleDisconnect')window.googleDisconnect();
    else if(a==='changePw')window.changePw();
    else if(a==='removePw')window.removePw();
    else if(a==='setPw')window.setPw();
    else if(a==='checkUpdate')window.checkUpdate();
    else if(a==='doUpdate')window.doUpdate();else if(a==='triggerImportFile'){var ii=document.getElementById('import-file-input');if(ii)ii.click();}
    else if(a==='exportAgent')window.exportAgent();
    else if(a==='importAgent')window.importAgent();
    else if(a==='quickSyncExport')window.quickSyncExport();
    else if(a==='refreshDebug'){window._loadDebug()}
    else if(a==='refreshLogs'){window._loadLogs()}
    else if(a==='attachFile'){document.getElementById('file-input-hidden').click()}
    else if(a==='switchModel'){
      var model=el.getAttribute('data-model');
      el.style.opacity='0.5';
      fetch('/api/model/switch',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},body:JSON.stringify({model:model})})
      .then(function(r){return r.json()}).then(function(res){if(res.ok)window._loadModelRouter();else alert(res.message||'Failed')})
      .catch(function(){el.style.opacity='1'});
    }
    else if(a==='toggleFeatCat'){el.parentElement.classList.toggle('open')}
    else if(a==='fillCommand'){var inp=document.getElementById('input');inp.value=el.getAttribute('data-cmd');inp.focus()}
    else if(a==='toggleUser'){var uid=parseInt(el.getAttribute('data-uid'));var en=el.getAttribute('data-enabled')==='true';window.toggleUser(uid,en)}
    else if(a==='deleteUser'){window.deleteUser(el.getAttribute('data-username'))}
    else if(a==='saveOllama'){var u=document.getElementById('s-ollama-url').value;fetch('/api/vault',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'set',key:'ollama_url',value:u})}).then(function(){addMsg('assistant','✅ Saved')})}
    else if(a==='saveRouting'){var rc={simple:document.getElementById('route-simple').value,moderate:document.getElementById('route-moderate').value,complex:document.getElementById('route-complex').value};fetch('/api/routing',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},body:JSON.stringify(rc)}).then(function(r){return r.json()}).then(function(d){var st=document.getElementById('route-status');if(st){st.textContent='✅ Saved!';setTimeout(function(){st.textContent=''},2000)}}).catch(function(){var st=document.getElementById('route-status');if(st)st.textContent='❌ Error'})}
    else if(a==='saveSoul'){
      var sc=document.getElementById('soul-editor').value;
      fetch('/api/soul',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},body:JSON.stringify({content:sc})}).then(function(r){return r.json()}).then(function(d){
        document.getElementById('soul-result').innerHTML='<span style="color:#4ade80">'+(d.message||'Saved')+'</span>'})
    }
    else if(a==='resetSoul'){
      document.getElementById('soul-editor').value='';
      fetch('/api/soul',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},body:JSON.stringify({content:''})}).then(function(r){return r.json()}).then(function(d){
        document.getElementById('soul-result').innerHTML='<span style="color:#4ade80">'+(d.message||'Reset')+'</span>'})
    }
    else if(a==='reloadPlugins'){fetch('/api/plugins/manage',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},body:JSON.stringify({action:'reload'})}).then(function(){window.showSettings()})}
    else if(a==='reloadHooks'){fetch('/api/hooks',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},body:JSON.stringify({action:'reload'})}).then(function(){window.showSettings()})}
    else if(a==='closeShortcutModal'||a==='closeFilterModal'){_closeAllModals()}
    else if(a==='filterSelect'){_closeAllModals();switchSession(el.getAttribute('data-sid'))}
    else if(a==='switchSession'){e.stopPropagation();window.switchSession(el.getAttribute('data-sid'))}
    else if(a==='deleteSession'){e.stopPropagation();window.deleteSession(el.getAttribute('data-sid'))}
    else if(a==='copyCode'){var cid=el.getAttribute('data-copy-id');window.copyCode(cid)}
    else if(a==='searchGo'){var sid=el.getAttribute('data-sid');if(sid){_closeSearchModal();switchSession(sid)}}
    else if(a==='openImage')window.open(el.src);
    else if(a==='save'&&typeof save==='function')save();
    else if(a==='reload')location.reload();
    else if(a==='pickTrue'&&typeof pick==='function')pick(true);
    else if(a==='pickFalse'&&typeof pick==='function')pick(false);
    else if(a==='go'&&typeof go==='function')go();
    else if(a==='unlock'&&typeof unlock==='function')unlock();
  });
  document.addEventListener('change',function(e){
    var el=e.target.closest('[data-action]');if(!el)return;
    var a=el.getAttribute('data-action');
    if(a==='setLang')window.setLang(el.value);
    else if(a==='setModel')window.setModel(el.value);
  });
  document.addEventListener('keydown',function(e){
    if(e.key!=='Enter')return;
    var el=e.target.closest('[data-enter-action]');if(!el)return;
    var a=el.getAttribute('data-enter-action');
    if(a==='go'&&typeof go==='function')go();
    else if(a==='unlock'&&typeof unlock==='function')unlock();
  });

  /* STT — Voice Input */
  /* --- Extended Thinking Toggle --- */
  var _thinkingOn=false;
  window.toggleThinking=function(){
    _thinkingOn=!_thinkingOn;
    var btn=document.getElementById('thinking-btn');
    if(_thinkingOn){
      btn.style.background='var(--accent)';btn.style.color='#fff';
      fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},
        body:JSON.stringify({message:'/thinking on',session:_currentSession})}).catch(function(){});
      addMsg('system',t('thinking-on'));
    }else{
      btn.style.background='var(--bg3)';btn.style.color='var(--text2)';
      fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},
        body:JSON.stringify({message:'/thinking off',session:_currentSession})}).catch(function(){});
      addMsg('system',t('thinking-off'));
    }
  };

  var _mediaRec=null,_audioChunks=[];
  window.toggleMic=function(){
    var btn=document.getElementById('mic-btn');
    if(_mediaRec&&_mediaRec.state==='recording'){
      _mediaRec.stop();
      btn.style.background='var(--bg3)';btn.style.color='var(--text2)';
      return;
    }
    navigator.mediaDevices.getUserMedia({audio:true}).then(function(stream){
      _audioChunks=[];
      _mediaRec=new MediaRecorder(stream,{mimeType:'audio/webm'});
      _mediaRec.ondataavailable=function(e){if(e.data.size>0)_audioChunks.push(e.data)};
      _mediaRec.onstop=function(){
        stream.getTracks().forEach(function(t){t.stop()});
        var blob=new Blob(_audioChunks,{type:'audio/webm'});
        var reader=new FileReader();
        reader.onload=function(){
          var b64=reader.result.split(',')[1];
          btn.textContent='⏳';
          fetch('/api/stt',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},
            body:JSON.stringify({audio_base64:b64,language:'ko'})})
          .then(function(r){return r.json()})
          .then(function(d){
            if(d.text){
              var inp=document.getElementById('input');
              inp.value=(inp.value?inp.value+' ':'')+d.text;
              inp.focus();inp.dispatchEvent(new Event('input'));
            }
            btn.textContent='🎤';
          }).catch(function(){btn.textContent='🎤'});
        };
        reader.readAsDataURL(blob);
      };
      _mediaRec.start();
      btn.style.background='var(--red)';btn.style.color='#fff';
    }).catch(function(err){
      var msg=t('mic-denied');
      if(location.hostname==='127.0.0.1'){msg+=' '+t('mic-hint-localhost')}
      addMsg('assistant',msg);
    });
  };

  /* --- Double-click to rename session title --- */
  document.addEventListener('dblclick',function(e){
    var el=e.target.closest('.session-title');if(!el)return;
    e.stopPropagation();
    var sid=el.getAttribute('data-sid');
    var oldTitle=el.textContent.replace(/^↳ /,'');
    var inp=document.createElement('input');
    inp.type='text';inp.value=oldTitle;
    inp.style.cssText='width:100%;padding:2px 4px;border:1px solid var(--accent);border-radius:4px;background:var(--bg);color:var(--text);font-size:12px;outline:none';
    el.textContent='';el.appendChild(inp);inp.focus();inp.select();
    function save(){
      var newTitle=inp.value.trim()||oldTitle;
      el.textContent=newTitle;
      if(newTitle!==oldTitle){
        fetch('/api/sessions/rename',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},
          body:JSON.stringify({session_id:sid,title:newTitle})}).catch(function(){});
      }
    }
    inp.addEventListener('blur',save);
    inp.addEventListener('keydown',function(ev){if(ev.key==='Enter'){ev.preventDefault();inp.blur()}if(ev.key==='Escape'){inp.value=oldTitle;inp.blur()}});
  });

  /* Auto-check for updates on load */
  setTimeout(function(){
    fetch('/api/update/check').then(function(r){return r.json()}).then(function(d){
      if(d.update_available&&d.latest){
        var banner=document.getElementById('update-banner');
        if(banner){banner.style.display='flex';document.getElementById('banner-ver').textContent='v'+d.latest+' available';}
      }
    }).catch(function(){});
  },3000);

  /* --- Agent Migration (에이전트 이동) --- */
  window.exportAgent=function(){
    var s=document.getElementById('exp-sessions').checked?'1':'0';
    var d=document.getElementById('exp-data').checked?'1':'0';
    var v=document.getElementById('exp-vault').checked?'1':'0';
    window.open('/api/agent/export?sessions='+s+'&data='+d+'&vault='+v,'_blank');
  };
  window.quickSyncExport=function(){
    fetch('/api/agent/sync',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},body:JSON.stringify({action:'export'})})
    .then(function(r){return r.json()}).then(function(d){
      if(d.ok){var blob=new Blob([JSON.stringify(d.data,null,2)],{type:'application/json'});var a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='salmalm-quick-sync.json';a.click()}
    });
  };
  var _importZipData=null;
  var dropzone=document.getElementById('import-dropzone');
  if(dropzone){
    dropzone.addEventListener('dragover',function(e){e.preventDefault();dropzone.style.borderColor='var(--accent)'});
    dropzone.addEventListener('dragleave',function(){dropzone.style.borderColor='var(--border)'});
    dropzone.addEventListener('drop',function(e){e.preventDefault();dropzone.style.borderColor='var(--border)';if(e.dataTransfer.files[0])_handleImportFile(e.dataTransfer.files[0])});
  }
  var impInput=document.getElementById('import-file-input');
  if(impInput)impInput.addEventListener('change',function(){if(this.files[0])_handleImportFile(this.files[0]);this.value=''});
  function _handleImportFile(file){
    if(!file.name.endsWith('.zip')){document.getElementById('import-result').textContent='❌ Please select a ZIP file';return}
    var reader=new FileReader();
    reader.onload=function(){
      _importZipData=reader.result;
      document.getElementById('import-btn').disabled=false;
      /* Preview */
      var fd=new FormData();fd.append('file',file);
      fetch('/api/agent/import/preview',{method:'POST',headers:{'X-Session-Token':_tok},body:fd})
      .then(function(r){return r.json()}).then(function(d){
        var prev=document.getElementById('import-preview');
        if(d.ok){
          var m=d.manifest||{};
          prev.innerHTML='<strong>'+file.name+'</strong> ('+Math.round(d.size_bytes/1024)+'KB)<br>'+
            'Agent: '+(m.agent_name||'?')+' · v'+(m.version||'?')+'<br>'+
            'Sections: '+(d.sections||[]).join(', ')+'<br>'+
            'Files: '+d.file_count;
          prev.style.display='block';
        }else{prev.textContent='⚠️ '+(d.error||'Preview failed');prev.style.display='block'}
      }).catch(function(){});
    };
    reader.readAsArrayBuffer(file);
  }
  window.importAgent=function(){
    if(!_importZipData)return;
    var mode=document.getElementById('import-mode').value;
    var blob=new Blob([_importZipData],{type:'application/zip'});
    var fd=new FormData();fd.append('file',blob,'agent-export.zip');fd.append('conflict_mode',mode);
    document.getElementById('import-result').textContent='⏳ Importing...';
    fetch('/api/agent/import',{method:'POST',headers:{'X-Session-Token':_tok},body:fd})
    .then(function(r){return r.json()}).then(function(d){
      var res=document.getElementById('import-result');
      if(d.ok){res.innerHTML='✅ Imported: '+(d.imported||[]).join(', ')+(d.warnings&&d.warnings.length?' <br>⚠️ '+d.warnings.join('; '):'')}
      else{res.textContent='❌ '+(d.errors||[]).join('; ')||(d.error||'Import failed')}
      _importZipData=null;document.getElementById('import-btn').disabled=true;
    }).catch(function(e){document.getElementById('import-result').textContent='❌ '+e});
  };

  /* PWA Service Worker */
  if('serviceWorker' in navigator){
    /* Unregister any existing SW and clear caches — no offline cache needed */
    navigator.serviceWorker.getRegistrations().then(function(regs){regs.forEach(function(r){r.unregister()})});
    caches.keys().then(function(ks){ks.forEach(function(k){caches.delete(k)})});
  }

  /* ── Logs Tab ── */
  var _logAutoTimer=null;
  /* ── Cron Panel ── */
  window._loadCron=function(){
    var c=document.getElementById('cron-table');if(!c)return;
    c.innerHTML='Loading...';
    fetch('/api/cron',{headers:{'X-Session-Token':_tok}}).then(function(r){return r.json()}).then(function(d){
      var jobs=d.jobs||[];var kr=_lang==='ko';
      if(!jobs.length){c.innerHTML='<div style="padding:24px;text-align:center;color:var(--text2);border:1px dashed var(--border);border-radius:10px">'+(kr?'크론 작업 없음 — 위의 ➕ 버튼으로 추가하세요':'No cron jobs — click ➕ above to add one')+'</div>';return}
      var h='<div style="border:1px solid var(--border);border-radius:10px;overflow:hidden">';
      h+='<div style="display:grid;grid-template-columns:1fr auto auto auto auto;background:var(--bg3);font-weight:600;font-size:12px">';
      h+='<div style="padding:10px 14px">'+(kr?'이름':'Name')+'</div><div style="padding:10px 14px">'+(kr?'간격':'Interval')+'</div><div style="padding:10px 14px">'+(kr?'실행 횟수':'Runs')+'</div><div style="padding:10px 14px">'+(kr?'상태':'Status')+'</div><div style="padding:10px 14px"></div></div>';
      jobs.forEach(function(j){
        var sched=j.schedule||{};var interval=sched.seconds?_fmtInterval(sched.seconds):(sched.expr||'—');
        h+='<div style="display:grid;grid-template-columns:1fr auto auto auto auto;font-size:13px;border-top:1px solid var(--border)">';
        h+='<div style="padding:10px 14px;font-weight:500">'+j.name+'</div>';
        h+='<div style="padding:10px 14px;color:var(--text2)">'+interval+'</div>';
        h+='<div style="padding:10px 14px;color:var(--text2)">'+j.run_count+'</div>';
        h+='<div style="padding:10px 14px"><button data-action="toggleCronJob" data-cron-id="'+j.id+'" style="background:none;border:none;cursor:pointer;font-size:13px">'+(j.enabled?'🟢 '+(kr?'활성':'On'):'🔴 '+(kr?'비활성':'Off'))+'</button></div>';
        h+='<div style="padding:10px 14px"><button data-action="deleteCronJob" data-cron-id="'+j.id+'" style="background:none;border:none;cursor:pointer;font-size:14px" title="Delete">🗑️</button></div>';
        h+='</div>';
      });
      h+='</div>';
      c.innerHTML=h;
    }).catch(function(e){c.innerHTML='Error: '+e.message});
  };
  function _fmtInterval(s){if(s<60)return s+'s';if(s<3600)return Math.round(s/60)+'m';if(s<86400)return Math.round(s/3600)+'h';return Math.round(s/86400)+'d'}
  /* Cron preset buttons */
  document.querySelectorAll('.cron-preset').forEach(function(btn){
    btn.addEventListener('click',function(){
      var s=parseInt(this.getAttribute('data-seconds'));
      document.getElementById('cron-interval').value=s;
      document.querySelectorAll('.cron-preset').forEach(function(b){b.style.background='var(--bg3)';b.style.color='var(--text)'});
      this.style.background='var(--accent)';this.style.color='#fff';
    });
  });
  window._saveCron=function(){
    var name=document.getElementById('cron-name').value.trim()||'untitled';
    var interval=parseInt(document.getElementById('cron-interval').value)||3600;
    var prompt=document.getElementById('cron-prompt').value.trim();
    var runAt=document.getElementById('cron-at').value||'';
    if(!prompt){alert(_lang==='ko'?'프롬프트를 입력하세요':'Enter a prompt');return}
    var payload={name:name,interval:interval,prompt:prompt};
    if(runAt)payload.run_at=runAt;
    fetch('/api/cron/add',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},
      body:JSON.stringify(payload)
    }).then(function(r){return r.json()}).then(function(d){
      if(d.ok){document.getElementById('cron-add-form').style.display='none';window._loadCron()}
      else alert(d.error||'Failed');
    });
  };

  /* ── Memory Panel ── */
  window._loadMemory=function(){
    var fl=document.getElementById('mem-file-list');if(!fl)return;
    fl.innerHTML='<div style="padding:12px;color:var(--text2);font-size:12px">Loading...</div>';
    fetch('/api/memory/files',{headers:{'X-Session-Token':_tok}}).then(function(r){return r.json()}).then(function(d){
      var files=d.files||[];var kr=_lang==='ko';
      if(!files.length){fl.innerHTML='<div style="padding:16px;color:var(--text2);font-size:12px">'+(kr?'메모리 파일 없음':'No memory files')+'</div>';return}
      var h='';
      files.forEach(function(f){
        var icon=f.name.endsWith('.json')?'📦':f.name.endsWith('.md')?'📝':'📄';
        var sz=f.size>1024?(f.size/1024).toFixed(1)+'KB':f.size+'B';
        h+='<div class="nav-item" data-action="memRead" data-mem-path="'+f.path+'" style="padding:10px 14px;border-bottom:1px solid var(--border);cursor:pointer;display:flex;justify-content:space-between;font-size:13px"><span>'+icon+' '+f.name+'</span><span style="color:var(--text2);font-size:11px">'+sz+'</span></div>';
      });
      fl.innerHTML=h;
    }).catch(function(e){fl.innerHTML='Error: '+e.message});
  };
  window._readMemFile=function(path){
    var mc=document.getElementById('mem-file-content');if(!mc)return;
    mc.innerHTML='<div style="color:var(--text2)">Loading...</div>';
    fetch('/api/memory/read?file='+encodeURIComponent(path),{headers:{'X-Session-Token':_tok}}).then(function(r){return r.json()}).then(function(d){
      if(d.error){mc.innerHTML='<div style="color:#f87171">'+d.error+'</div>';return}
      var ext=path.split('.').pop();
      var h='<div style="margin-bottom:8px;font-weight:600;font-size:13px">'+path+' <span style="color:var(--text2);font-weight:400;font-size:11px">'+(d.size/1024).toFixed(1)+'KB</span></div>';
      h+='<pre style="background:var(--bg);padding:12px;border-radius:8px;font-size:12px;line-height:1.6;white-space:pre-wrap;word-break:break-all;max-height:400px;overflow-y:auto">'+d.content.replace(/</g,'&lt;')+'</pre>';
      mc.innerHTML=h;
    }).catch(function(e){mc.innerHTML='Error: '+e.message});
  };

  /* ── Sessions Panel ── */
  window._loadSessions=function(){
    var container=document.getElementById('sessions-table');if(!container)return;
    container.innerHTML='Loading...';
    fetch('/api/sessions',{headers:{'X-Session-Token':_tok}}).then(function(r){return r.json()}).then(function(d){
      var sessions=d.sessions||[];var kr=_lang==='ko';
      var q=(document.getElementById('sess-search')||{}).value||'';
      var ql=q.toLowerCase();
      if(ql)sessions=sessions.filter(function(s){return(s.title||'').toLowerCase().indexOf(ql)>=0||s.id.toLowerCase().indexOf(ql)>=0});
      if(!sessions.length){container.innerHTML='<div style="padding:20px;text-align:center;color:var(--text2)">'+(kr?'세션 없음':'No sessions')+'</div>';return}
      var h='<div style="display:grid;grid-template-columns:1fr auto auto auto;gap:0;border:1px solid var(--border);border-radius:10px;overflow:hidden">';
      h+='<div style="padding:10px 14px;font-weight:600;font-size:12px;background:var(--bg3);border-bottom:1px solid var(--border)">'+(kr?'제목':'Title')+'</div>';
      h+='<div style="padding:10px 14px;font-weight:600;font-size:12px;background:var(--bg3);border-bottom:1px solid var(--border)">'+(kr?'메시지':'Msgs')+'</div>';
      h+='<div style="padding:10px 14px;font-weight:600;font-size:12px;background:var(--bg3);border-bottom:1px solid var(--border)">'+(kr?'마지막 활동':'Last Active')+'</div>';
      h+='<div style="padding:10px 14px;font-weight:600;font-size:12px;background:var(--bg3);border-bottom:1px solid var(--border)"></div>';
      sessions.forEach(function(s){
        var title=(s.title||s.id).substring(0,50);
        var ago=s.updated_at?_timeAgo(s.updated_at):'—';
        var isBranch=s.parent_session_id?'🔀 ':'';
        h+='<div style="padding:8px 14px;font-size:13px;border-bottom:1px solid var(--border);cursor:pointer;display:flex;align-items:center" data-action="sess-open" data-sid="'+s.id+'">'+isBranch+title+'</div>';
        h+='<div style="padding:8px 14px;font-size:12px;border-bottom:1px solid var(--border);color:var(--text2);text-align:center">'+(s.messages||0)+'</div>';
        h+='<div style="padding:8px 14px;font-size:12px;border-bottom:1px solid var(--border);color:var(--text2)">'+ago+'</div>';
        h+='<div style="padding:8px 14px;font-size:12px;border-bottom:1px solid var(--border);text-align:center"><button data-action="sess-delete" data-sid="'+s.id+'" style="background:none;border:none;cursor:pointer;font-size:14px" title="Delete">🗑️</button></div>';
      });
      h+='</div>';
      h+='<div style="margin-top:8px;font-size:12px;color:var(--text2)">'+(kr?'총 '+sessions.length+'개 세션':sessions.length+' sessions')+'</div>';
      container.innerHTML=h;
    }).catch(function(e){container.innerHTML='Error: '+e.message});
  };
  function _timeAgo(dt){
    var d=new Date(dt);var now=new Date();var diff=Math.floor((now-d)/1000);
    if(diff<60)return diff+'s';if(diff<3600)return Math.floor(diff/60)+'m';
    if(diff<86400)return Math.floor(diff/3600)+'h';return Math.floor(diff/86400)+'d';
  }
  if(document.getElementById('sess-search'))document.getElementById('sess-search').addEventListener('input',function(){window._loadSessions()});

  /* ── Channels Panel ── */
  /* ── Docs Panel ── */
  var _docsData=[
    {catKr:'슬래시 커맨드',catEn:'Slash Commands',items:[
      {cmd:'/help',en:'Show all commands and tools',kr:'모든 명령어와 도구 표시',detailEn:'Displays a complete list of all available slash commands, built-in tools, and unique features. Use this as a quick reference when you forget a command name.',detailKr:'사용 가능한 모든 슬래시 커맨드, 내장 도구, 고유 기능의 전체 목록을 표시합니다. 명령어 이름이 기억나지 않을 때 빠른 참조용으로 사용하세요.'},
      {cmd:'/status',en:'Session status (model, tokens, cost)',kr:'세션 상태 (모델, 토큰, 비용)',detailEn:'Shows current session info: active model, token count (input/output), estimated cost, thinking mode, and persona. Useful for monitoring usage.',detailKr:'현재 세션 정보를 표시합니다: 활성 모델, 토큰 수(입력/출력), 예상 비용, 사고 모드, 페르소나. 사용량 모니터링에 유용합니다.'},
      {cmd:'/model <name>',en:'Switch AI model',kr:'AI 모델 전환',detailEn:'Switch between models: opus, sonnet, haiku, gpt, grok, gemini, auto. "auto" enables smart routing that picks the best model per query complexity. Example: /model opus',detailKr:'모델 전환: opus, sonnet, haiku, gpt, grok, gemini, auto. "auto"는 질문 복잡도에 따라 최적 모델을 자동 선택합니다. 예: /model opus'},
      {cmd:'/compact',en:'Compress conversation context',kr:'대화 컨텍스트 압축',detailEn:'Summarizes the conversation history to reduce token usage. Automatically triggered at 80K tokens, but you can run it manually anytime. Preserves key information while cutting context size by ~70%.',detailKr:'대화 기록을 요약하여 토큰 사용량을 줄입니다. 80K 토큰에서 자동 실행되지만 수동으로도 가능합니다. 핵심 정보를 보존하면서 컨텍스트 크기를 ~70% 줄입니다.'},
      {cmd:'/context',en:'Token count breakdown',kr:'토큰 수 분석',detailEn:'Shows detailed token breakdown: system prompt, conversation history, tool definitions, and available context window. Helps you understand how close you are to the context limit.',detailKr:'상세 토큰 분석: 시스템 프롬프트, 대화 기록, 도구 정의, 사용 가능한 컨텍스트 윈도우. 컨텍스트 한도에 얼마나 가까운지 파악할 수 있습니다.'},
      {cmd:'/usage',en:'Token and cost tracking',kr:'토큰 및 비용 추적',detailEn:'Displays cumulative token usage and cost across all sessions. Shows input/output tokens, cache hits, and estimated USD cost per provider. Resets monthly.',detailKr:'모든 세션의 누적 토큰 사용량과 비용을 표시합니다. 입력/출력 토큰, 캐시 히트, 프로바이더별 예상 USD 비용을 보여줍니다. 월별 초기화.'},
      {cmd:'/think [level]',en:'Extended thinking mode (low/medium/high)',kr:'확장 사고 모드 (low/medium/high)',detailEn:'Enables deep reasoning with configurable budget. "low" uses ~1K thinking tokens, "medium" ~5K, "high" ~20K. The AI shows its reasoning process before answering. Great for complex coding/math.',detailKr:'설정 가능한 예산으로 심층 추론을 활성화합니다. "low" ~1K, "medium" ~5K, "high" ~20K 사고 토큰. AI가 답변 전 추론 과정을 보여줍니다. 복잡한 코딩/수학에 적합.'},
      {cmd:'/persona <name>',en:'Switch persona',kr:'페르소나 전환',detailEn:'Changes the AI personality. Built-in: expert, friend, assistant. Custom personas are loaded from SOUL.md in your data directory. The persona affects tone, formality, and response style.',detailKr:'AI 성격을 변경합니다. 내장: expert, friend, assistant. 커스텀 페르소나는 데이터 디렉토리의 SOUL.md에서 로드됩니다. 톤, 격식, 응답 스타일에 영향을 줍니다.'},
      {cmd:'/branch',en:'Branch conversation',kr:'대화 분기',detailEn:'Creates a new conversation branch from the current point. Useful for exploring alternative directions without losing the original thread. Branches are visible in the Sessions panel.',detailKr:'현재 지점에서 새 대화 분기를 생성합니다. 원래 스레드를 잃지 않고 대안을 탐색할 때 유용합니다. 분기는 세션 패널에서 확인 가능.'},
      {cmd:'/rollback [n]',en:'Rollback last n messages',kr:'마지막 n개 메시지 롤백',detailEn:'Removes the last n message pairs (user + assistant). Default n=1. Useful when the AI misunderstands or you want to rephrase. The messages are permanently deleted from the session.',detailKr:'마지막 n개 메시지 쌍(사용자+AI)을 제거합니다. 기본 n=1. AI가 오해했거나 다시 질문하고 싶을 때 유용합니다. 메시지는 세션에서 영구 삭제됩니다.'},
      {cmd:'/remind <time> <msg>',en:'Set a reminder',kr:'리마인더 설정',detailEn:'Schedule a reminder. Supports natural language: "/remind 30m check email", "/remind 2h meeting", "/remind tomorrow 9am call dentist". Uses the cron system internally.',detailKr:'리마인더를 예약합니다. 자연어 지원: "/remind 30m 이메일 확인", "/remind 2h 회의", "/remind tomorrow 9am 치과 전화". 내부적으로 크론 시스템 사용.'},
      {cmd:'/expense <amount> <desc>',en:'Track an expense',kr:'지출 기록',detailEn:'Log expenses for the Life Dashboard. Example: "/expense 15000 lunch". Amounts are stored with timestamps and categories. View summaries with /life.',detailKr:'라이프 대시보드용 지출을 기록합니다. 예: "/expense 15000 점심". 금액은 타임스탬프와 카테고리와 함께 저장됩니다. /life로 요약 확인.'},
      {cmd:'/pomodoro',en:'Pomodoro timer',kr:'뽀모도로 타이머',detailEn:'Starts a 25-minute focus timer with 5-minute breaks. Tracks your productivity sessions. The AI will notify you when each interval ends.',detailKr:'25분 집중 타이머와 5분 휴식을 시작합니다. 생산성 세션을 추적합니다. 각 구간이 끝나면 AI가 알려줍니다.'},
      {cmd:'/note <text>',en:'Quick note',kr:'빠른 메모',detailEn:'Saves a quick note to your memory directory. Notes are timestamped and searchable. They persist across sessions and can be referenced by the AI.',detailKr:'메모리 디렉토리에 빠른 메모를 저장합니다. 메모는 타임스탬프가 찍히고 검색 가능합니다. 세션 간에 유지되며 AI가 참조할 수 있습니다.'},
      {cmd:'/link <url>',en:'Save a link',kr:'링크 저장',detailEn:'Bookmarks a URL with optional description. Links are stored in your data directory and can be searched or listed later.',detailKr:'URL을 선택적 설명과 함께 북마크합니다. 링크는 데이터 디렉토리에 저장되며 나중에 검색하거나 목록을 볼 수 있습니다.'},
      {cmd:'/routine',en:'Manage daily routines',kr:'일일 루틴 관리',detailEn:'Create, list, and track daily routines (morning workout, journaling, etc.). The AI reminds you of incomplete routines and tracks streaks.',detailKr:'일일 루틴을 생성, 목록 확인, 추적합니다 (아침 운동, 일기 등). AI가 미완료 루틴을 알려주고 연속 기록을 추적합니다.'},
      {cmd:'/shadow',en:'Shadow mode (silent learning)',kr:'섀도우 모드 (무음 학습)',detailEn:'AI silently learns your communication style by analyzing your messages. When activated, it can reply as you when you\'re away. Toggle: /shadow on, /shadow off, /shadow status.',detailKr:'AI가 메시지를 분석하여 당신의 소통 스타일을 조용히 학습합니다. 활성화하면 부재 시 대리 응답이 가능합니다. 토글: /shadow on, /shadow off, /shadow status.'},
      {cmd:'/vault',en:'Encrypted vault operations',kr:'암호화 금고 작업',detailEn:'Manage encrypted secrets: /vault set <key> <value>, /vault get <key>, /vault list, /vault delete <key>. All data encrypted with AES-256-GCM (or HMAC-CTR fallback). API keys are stored here.',detailKr:'암호화된 비밀 관리: /vault set <키> <값>, /vault get <키>, /vault list, /vault delete <키>. 모든 데이터는 AES-256-GCM(또는 HMAC-CTR 폴백)으로 암호화. API 키가 여기에 저장됩니다.'},
      {cmd:'/capsule',en:'Time capsule messages',kr:'타임캡슐 메시지',detailEn:'Write a message to your future self: "/capsule 7d Remember to review this code". The message will be delivered after the specified time. Supports: Nd (days), Nw (weeks), Nm (months).',detailKr:'미래의 나에게 메시지 작성: "/capsule 7d 이 코드 리뷰하기". 지정 시간 후 메시지가 전달됩니다. 지원: Nd(일), Nw(주), Nm(월).'},
      {cmd:'/deadman',en:'Dead man\'s switch',kr:'데드맨 스위치',detailEn:'Configure automated actions if you go inactive: send emails, post messages, or run commands after N days of silence. Setup: /deadman set <days> <action>. Cancel: /deadman off.',detailKr:'비활성 시 자동 조치 설정: N일간 침묵 후 이메일 전송, 메시지 게시, 명령 실행. 설정: /deadman set <일수> <조치>. 취소: /deadman off.'},
      {cmd:'/a2a',en:'Agent-to-agent protocol',kr:'에이전트 간 프로토콜',detailEn:'Send HMAC-SHA256 signed messages between SalmAlm instances. Setup: /a2a register <name> <url> <secret>. Send: /a2a send <name> <message>. Enables multi-agent collaboration.',detailKr:'SalmAlm 인스턴스 간 HMAC-SHA256 서명된 메시지를 전송합니다. 설정: /a2a register <이름> <url> <시크릿>. 전송: /a2a send <이름> <메시지>. 멀티에이전트 협업 가능.'},
      {cmd:'/workflow',en:'Workflow engine',kr:'워크플로우 엔진',detailEn:'Create multi-step AI workflows: /workflow create <name>, /workflow add <name> <step>, /workflow run <name>. Steps can include tool calls, conditions, and loops.',detailKr:'다단계 AI 워크플로우 생성: /workflow create <이름>, /workflow add <이름> <단계>, /workflow run <이름>. 단계에 도구 호출, 조건, 루프 포함 가능.'},
      {cmd:'/mcp',en:'MCP server management',kr:'MCP 서버 관리',detailEn:'Manage Model Context Protocol servers: /mcp list, /mcp add <name> <command>, /mcp remove <name>. Connect to external tool servers following the MCP standard.',detailKr:'Model Context Protocol 서버 관리: /mcp list, /mcp add <이름> <명령>, /mcp remove <이름>. MCP 표준을 따르는 외부 도구 서버에 연결합니다.'},
      {cmd:'/subagents',en:'Sub-agent management',kr:'서브 에이전트 관리',detailEn:'Spawn and manage background AI workers: /subagents spawn <task> [--model opus], /subagents list, /subagents stop <id|#N|all>, /subagents steer <id> <message>, /subagents log <id>, /subagents info <id>, /subagents collect. Sub-agents run independently with isolated sessions, tool access, and auto-notification on completion.',detailKr:'백그라운드 AI 워커 생성 및 관리: /subagents spawn <작업> [--model opus], /subagents list, /subagents stop <id|#N|all>, /subagents steer <id> <메시지>, /subagents log <id>, /subagents info <id>, /subagents collect. 서브에이전트가 격리된 세션에서 독립 실행, 도구 사용, 완료 시 자동 알림.'},
      {cmd:'/evolve',en:'Self-evolving prompt rules',kr:'자기 진화 프롬프트 규칙',detailEn:'View and manage auto-generated prompt rules. The AI learns patterns from your conversations and creates rules (max 20, FIFO). /evolve list, /evolve clear, /evolve remove <n>.',detailKr:'자동 생성된 프롬프트 규칙을 확인하고 관리합니다. AI가 대화 패턴을 학습하여 규칙을 생성합니다 (최대 20개, FIFO). /evolve list, /evolve clear, /evolve remove <n>.'},
      {cmd:'/mood',en:'Mood-aware mode',kr:'감정 인식 모드',detailEn:'Toggle emotional state detection. When active, the AI analyzes your message tone and adapts its response style — more empathetic when stressed, more energetic when excited.',detailKr:'감정 상태 감지를 토글합니다. 활성화 시 AI가 메시지 톤을 분석하여 응답 스타일을 조정합니다 — 스트레스 시 더 공감적, 흥분 시 더 에너지 넘치게.'},
      {cmd:'/split',en:'A/B split response comparison',kr:'A/B 분할 응답 비교',detailEn:'Get two different model responses to the same question side-by-side. Example: "/split What\'s the best programming language?" Useful for comparing perspectives.',detailKr:'같은 질문에 대해 두 모델의 응답을 나란히 비교합니다. 예: "/split 최고의 프로그래밍 언어는?" 다양한 관점 비교에 유용합니다.'},
      {cmd:'/cron',en:'Cron job management',kr:'크론 작업 관리',detailEn:'Schedule recurring AI tasks: /cron add "0 9 * * *" "Check my email", /cron list, /cron delete <id>. Uses standard cron syntax. Tasks run in isolated sessions.',detailKr:'반복 AI 작업 예약: /cron add "0 9 * * *" "이메일 확인", /cron list, /cron delete <id>. 표준 크론 문법 사용. 작업은 격리된 세션에서 실행.'},
      {cmd:'/bash <cmd>',en:'Run shell command',kr:'셸 명령 실행',detailEn:'Execute a shell command directly. Output is captured and displayed. Shell operators (|, >, &&) require SALMALM_ALLOW_SHELL=1 env var. Interpreters (python, node) are blocked — use python_eval tool instead. Dangerous flags are blocked per-command: find -exec, awk system(), tar --to-command, git clone/push, sed -i, xargs -I.',detailKr:'셸 명령을 직접 실행합니다. 출력이 캡처되어 표시됩니다. 셸 연산자(|, >, &&)는 SALMALM_ALLOW_SHELL=1 환경변수 필요. 인터프리터(python, node)는 차단 — python_eval 도구를 대신 사용. 명령별 위험 플래그 차단: find -exec, awk system(), tar --to-command, git clone/push, sed -i, xargs -I.'},
      {cmd:'/screen',en:'Browser control',kr:'브라우저 제어',detailEn:'Remote browser automation: /screen open <url>, /screen click <selector>, /screen type <text>. Requires a browser automation backend. Useful for web scraping and testing.',detailKr:'원격 브라우저 자동화: /screen open <url>, /screen click <선택자>, /screen type <텍스트>. 브라우저 자동화 백엔드 필요. 웹 스크래핑과 테스트에 유용.'},
      {cmd:'/life',en:'Life dashboard',kr:'라이프 대시보드',detailEn:'Unified personal dashboard showing: expense summary, habit streaks, upcoming reminders, mood trends, and routine completion. All data from /expense, /routine, /mood, /remind.',detailKr:'통합 개인 대시보드: 지출 요약, 습관 연속 기록, 예정 리마인더, 감정 추이, 루틴 완료율. /expense, /routine, /mood, /remind의 모든 데이터.'},
      {cmd:'/oauth',en:'OAuth setup',kr:'OAuth 설정',detailEn:'Configure OAuth2 for Gmail and Google Calendar integration. Guides you through the Google Cloud Console setup and stores tokens securely in the vault.',detailKr:'Gmail과 Google 캘린더 연동을 위한 OAuth2 설정. Google Cloud Console 설정 과정을 안내하고 토큰을 금고에 안전하게 저장합니다.'},
      {cmd:'/queue',en:'Message queue management (5 modes)',kr:'메시지 큐 관리 (5가지 모드)',detailEn:'Advanced message processing: /queue batch (collect then process), /queue priority (urgent first), /queue schedule (delayed send), /queue pipeline (chain tools), /queue broadcast (multi-channel).',detailKr:'고급 메시지 처리: /queue batch (수집 후 처리), /queue priority (긴급 우선), /queue schedule (지연 전송), /queue pipeline (도구 체인), /queue broadcast (멀티채널).'},
      {cmd:'/debug',en:'Real-time system diagnostics',kr:'실시간 시스템 진단',detailEn:'Shows 5 diagnostic cards: system info, active sessions, model status, tool usage, and error log. Auto-refreshes.',detailKr:'5개 진단 카드 표시: 시스템 정보, 활성 세션, 모델 상태, 도구 사용량, 에러 로그. 자동 새로고침.'},
      {cmd:'/security',en:'Security status overview',kr:'보안 상태 요약',detailEn:'Shows vault status, bind address, sandbox level, exec restrictions, active tokens, and login lockout state.',detailKr:'금고 상태, 바인드 주소, 샌드박스 레벨, exec 제한, 활성 토큰, 로그인 잠금 상태를 표시합니다.'},
      {cmd:'/plugins',en:'Plugin management',kr:'플러그인 관리',detailEn:'List, enable, disable, or reload plugins. Plugins are auto-discovered from the plugins/ directory.',detailKr:'플러그인 목록 확인, 활성화, 비활성화, 리로드. plugins/ 디렉토리에서 자동 발견됩니다.'},
      {cmd:'/export',en:'Export session data',kr:'세션 데이터 내보내기',detailEn:'Export current session as JSON or Markdown. Useful for backup or sharing conversations.',detailKr:'현재 세션을 JSON 또는 Markdown으로 내보냅니다. 백업이나 대화 공유에 유용합니다.'},
      {cmd:'/config',en:'Configuration management',kr:'설정 관리',detailEn:'View or modify runtime configuration. Shows current env vars, bind address, port, model, and security settings.',detailKr:'런타임 설정을 확인하거나 변경합니다. 현재 환경변수, 바인드 주소, 포트, 모델, 보안 설정을 표시합니다.'},
      {cmd:'/new',en:'Start new session',kr:'새 세션 시작',detailEn:'Creates a fresh conversation session. Previous session is saved and accessible from the Sessions panel.',detailKr:'새 대화 세션을 생성합니다. 이전 세션은 저장되어 세션 패널에서 접근할 수 있습니다.'},
      {cmd:'/clear',en:'Clear current session',kr:'현재 세션 초기화',detailEn:'Removes all messages from the current session. The session itself is preserved but emptied.',detailKr:'현재 세션의 모든 메시지를 제거합니다. 세션 자체는 유지되지만 비워집니다.'},
      {cmd:'/tools',en:'List available tools',kr:'사용 가능한 도구 목록',detailEn:'Shows all 62 built-in tools with descriptions. Includes dynamic and plugin tools if registered.',detailKr:'62개 내장 도구의 전체 목록과 설명을 표시합니다. 동적 등록/플러그인 도구도 포함됩니다.'},
      {cmd:'/health',en:'System health check',kr:'시스템 건강 점검',detailEn:'Quick overview of system health: CPU, memory, disk, uptime, and active connections.',detailKr:'시스템 건강 요약: CPU, 메모리, 디스크, 가동시간, 활성 연결.'},
      {cmd:'/prune',en:'Prune context manually',kr:'컨텍스트 수동 정리',detailEn:'Manually triggers context pruning to reduce token usage. More aggressive than /compact.',detailKr:'토큰 사용량을 줄이기 위해 컨텍스트 정리를 수동 실행합니다. /compact보다 적극적입니다.'},
      {cmd:'/approve',en:'Approve pending exec commands',kr:'대기 중인 실행 명령 승인',detailEn:'Review and approve or reject pending shell commands that require user confirmation (elevated commands).',detailKr:'사용자 확인이 필요한 대기 중인 셸 명령(상승된 명령)을 검토하고 승인 또는 거부합니다.'},
      {cmd:'/whoami',en:'Current user info',kr:'현재 사용자 정보',detailEn:'Shows your username, role, session ID, and authentication status.',detailKr:'사용자 이름, 역할, 세션 ID, 인증 상태를 표시합니다.'},
    ]},
    {catKr:'단축키',catEn:'Keyboard Shortcuts',items:[
      {cmd:'Enter',en:'Send message',kr:'메시지 전송',detailEn:'Sends the current message in the input field.',detailKr:'입력 필드의 현재 메시지를 전송합니다.'},
      {cmd:'Shift+Enter',en:'New line',kr:'줄바꿈',detailEn:'Inserts a line break without sending the message.',detailKr:'메시지를 전송하지 않고 줄바꿈을 삽입합니다.'},
      {cmd:'Ctrl+K',en:'Search conversations',kr:'대화 검색',detailEn:'Opens the search modal to find messages across all sessions by keyword.',detailKr:'모든 세션에서 키워드로 메시지를 찾는 검색 모달을 엽니다.'},
      {cmd:'Ctrl+/',en:'Command palette',kr:'명령 팔레트',detailEn:'Opens the command palette for quick access to any slash command without typing it.',detailKr:'슬래시 커맨드에 빠르게 접근할 수 있는 명령 팔레트를 엽니다.'},
      {cmd:'Ctrl+V',en:'Paste image/file',kr:'이미지/파일 붙여넣기',detailEn:'Paste an image from clipboard directly into the chat. Supports PNG, JPEG, GIF, WebP. Images are sent to vision-capable models for analysis.',detailKr:'클립보드의 이미지를 채팅에 직접 붙여넣기. PNG, JPEG, GIF, WebP 지원. 이미지는 비전 모델에 전송되어 분석됩니다.'},
      {cmd:'Esc',en:'Close modal / Back to chat',kr:'모달 닫기 / 채팅으로 돌아가기',detailEn:'Closes any open modal (search, settings, command palette) and returns focus to the chat input.',detailKr:'열린 모달(검색, 설정, 명령 팔레트)을 닫고 채팅 입력에 포커스를 돌려줍니다.'},
    ]},
    {catKr:'고유 기능',catEn:'Unique Features',items:[
      {cmd:'Self-Evolving Prompt',en:'AI auto-generates prompt rules from conversations (max 20)',kr:'대화에서 프롬프트 규칙 자동 생성 (최대 20개)',detailEn:'The AI observes your preferences, corrections, and patterns over time. It automatically creates system prompt rules (max 20, oldest removed first) that make responses better aligned with your style. View with /evolve list.',detailKr:'AI가 시간이 지나며 당신의 선호, 수정, 패턴을 관찰합니다. 응답을 당신의 스타일에 맞추는 시스템 프롬프트 규칙을 자동 생성합니다 (최대 20개, 오래된 것부터 제거). /evolve list로 확인.'},
      {cmd:'Dead Man\'s Switch',en:'Automated actions if owner goes inactive',kr:'소유자 비활성 시 자동 조치',detailEn:'If you don\'t interact with SalmAlm for a configured number of days, it automatically executes pre-set actions: send notification emails, post status updates, or run cleanup scripts. A safety net for digital life.',detailKr:'설정된 일수 동안 SalmAlm과 상호작용하지 않으면 미리 설정된 조치를 자동 실행합니다: 알림 이메일 전송, 상태 업데이트 게시, 정리 스크립트 실행. 디지털 생활의 안전망.'},
      {cmd:'Shadow Mode',en:'AI silently observes without responding',kr:'AI가 응답 없이 조용히 관찰',detailEn:'In Shadow Mode, the AI reads all your messages but doesn\'t respond. Instead, it builds a profile of your communication style — word choice, tone, emoji usage, typical responses. When you\'re away, it can reply as you.',detailKr:'섀도우 모드에서 AI는 모든 메시지를 읽지만 응답하지 않습니다. 대신 소통 스타일 프로필을 구축합니다 — 단어 선택, 톤, 이모지 사용, 전형적인 응답. 부재 시 대리 응답 가능.'},
      {cmd:'Life Dashboard',en:'Unified view of health, finance, habits',kr:'건강, 재정, 습관 통합 뷰',detailEn:'A single /life command shows everything: expense totals and trends, habit completion streaks, upcoming events, mood history, and routine progress. Your personal life at a glance.',detailKr:'/life 하나로 모든 것을 표시: 지출 합계와 추이, 습관 완료 연속 기록, 예정 이벤트, 감정 이력, 루틴 진행률. 한눈에 보는 당신의 삶.'},
      {cmd:'Mood-Aware',en:'Emotional state detection and adaptation',kr:'감정 상태 감지 및 적응',detailEn:'Uses NLP signals (word choice, punctuation, message length) to estimate your current emotional state. Adjusts response tone: more gentle when you seem frustrated, more celebratory when excited, more focused when stressed.',detailKr:'NLP 신호(단어 선택, 구두점, 메시지 길이)로 현재 감정 상태를 추정합니다. 응답 톤 조정: 좌절감 감지 시 더 부드럽게, 흥분 시 더 축하하는 톤, 스트레스 시 더 집중적으로.'},
      {cmd:'Encrypted Vault',en:'AES-256-GCM encrypted secret storage',kr:'AES-256-GCM 암호화 비밀 저장소',detailEn:'All sensitive data (API keys, tokens, personal notes) is encrypted with AES-256-GCM using a PBKDF2-derived key (200K iterations). Without the cryptography package, falls back to HMAC-CTR. Data is useless without your password.',detailKr:'모든 민감 데이터(API 키, 토큰, 개인 메모)가 PBKDF2 유도 키(200K 반복)를 사용한 AES-256-GCM으로 암호화됩니다. cryptography 패키지 없으면 HMAC-CTR로 폴백. 비밀번호 없이는 데이터를 읽을 수 없습니다.'},
      {cmd:'A/B Split Response',en:'Compare two model responses side-by-side',kr:'두 모델 응답을 나란히 비교',detailEn:'Ask one question, get two answers from different models simultaneously. Perfect for comparing reasoning approaches, writing styles, or checking accuracy. Models are selected automatically or you can specify them.',detailKr:'하나의 질문으로 두 모델의 답변을 동시에 받습니다. 추론 방식, 작문 스타일 비교나 정확도 확인에 완벽합니다. 모델은 자동 선택되거나 직접 지정 가능.'},
      {cmd:'Time Capsule',en:'Schedule messages to future self',kr:'미래의 나에게 메시지 예약',detailEn:'Write a message and set a delivery date. The message is stored encrypted and delivered when the time comes — as a chat notification. Great for goals, reflections, or reminders to future-you.',detailKr:'메시지를 작성하고 전달 날짜를 설정합니다. 메시지는 암호화되어 저장되고 시간이 되면 채팅 알림으로 전달됩니다. 목표, 성찰, 미래의 나에게 보내는 리마인더에 적합.'},
      {cmd:'Thought Stream',en:'Private journaling with mood tracking',kr:'감정 추적 포함 개인 일기',detailEn:'A private journaling timeline. Entries are tagged with timestamps, mood scores, and hashtags. Search by #tag or date range. All entries are stored locally and never sent to AI providers.',detailKr:'개인 일기 타임라인. 항목에 타임스탬프, 감정 점수, 해시태그가 태그됩니다. #태그 또는 날짜 범위로 검색. 모든 항목은 로컬에 저장되며 AI 프로바이더에 전송되지 않습니다.'},
      {cmd:'Agent-to-Agent',en:'HMAC-signed inter-agent communication',kr:'HMAC 서명된 에이전트 간 통신',detailEn:'Connect multiple SalmAlm instances for collaboration. Messages are authenticated with HMAC-SHA256 to prevent tampering. Use cases: home server ↔ work server, personal ↔ team assistant.',detailKr:'여러 SalmAlm 인스턴스를 연결하여 협업합니다. 메시지는 HMAC-SHA256으로 인증되어 변조를 방지합니다. 활용: 집 서버 ↔ 직장 서버, 개인 ↔ 팀 어시스턴트.'},
    ]},
  ];
  window._renderDocs=function(q){
    var c=document.getElementById('docs-content');if(!c)return;
    var kr=_lang==='ko';var ql=q.toLowerCase();var h='';
    _docsData.forEach(function(sec){
      var catTitle=kr?sec.catKr:sec.catEn;
      var items=sec.items;
      if(ql)items=items.filter(function(i){return i.cmd.toLowerCase().indexOf(ql)>=0||(kr?i.kr:i.en).toLowerCase().indexOf(ql)>=0||i.en.toLowerCase().indexOf(ql)>=0||i.kr.indexOf(ql)>=0||(i.detailEn||'').toLowerCase().indexOf(ql)>=0||(i.detailKr||'').indexOf(ql)>=0});
      if(!items.length)return;
      h+='<div style="margin-bottom:20px"><h3 style="margin-bottom:10px;font-size:15px">'+catTitle+'</h3>';
      h+='<div style="border:1px solid var(--border);border-radius:10px;overflow:hidden">';
      items.forEach(function(i,idx){
        var bg=idx%2===0?'var(--bg)':'var(--bg3)';
        var detail=kr?(i.detailKr||''):(i.detailEn||'');
        var hasDetail=!!detail;
        h+='<div data-action="toggleDocDetail" style="padding:10px 14px;background:'+bg+';border-bottom:1px solid var(--border);'+(hasDetail?'cursor:pointer;':'')+'">';
        h+='<div style="display:flex;gap:16px;align-items:baseline">';
        h+='<code style="font-size:13px;font-weight:600;white-space:nowrap;min-width:180px;color:var(--accent2)">'+i.cmd+'</code>';
        h+='<span style="font-size:13px;color:var(--text);flex:1">'+(kr?i.kr:i.en)+'</span>';
        if(hasDetail)h+='<span style="font-size:11px;color:var(--text2);transition:transform 0.2s" class="doc-chevron">▶</span>';
        h+='</div>';
        if(hasDetail)h+='<div class="doc-detail" style="display:none;margin-top:8px;padding:10px 12px;font-size:12.5px;line-height:1.6;color:var(--text2);background:var(--bg2);border-radius:8px;border-left:3px solid var(--accent)">'+detail+'</div>';
        h+='</div>';
      });
      h+='</div></div>';
    });
    if(!h)h='<div style="padding:20px;text-align:center;color:var(--text2)">'+(kr?'검색 결과 없음':'No results')+'</div>';
    c.innerHTML=h;
  };
  if(document.getElementById('docs-search'))document.getElementById('docs-search').addEventListener('input',function(){window._renderDocs(this.value)});
  /* Pre-render docs so content is ready when panel opens */
  try{window._renderDocs('')}catch(e){console.warn('Docs pre-render:',e)}

  /* ── Debug Tab ── */
  var _debugAutoTimer=null;
  window._loadDebug=function(){
    var panel=document.getElementById('debug-panel');if(!panel)return;
    panel.innerHTML='<div style="grid-column:1/-1;color:var(--text2);font-size:12px">Loading...</div>';
    fetch('/api/debug',{headers:{'X-Session-Token':_tok}}).then(function(r){return r.json()}).then(function(d){
      var kr=_lang==='ko';
      function card(icon,title,rows){
        var h='<div style="background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:14px"><div style="font-weight:600;margin-bottom:10px;font-size:13px">'+icon+' '+title+'</div>';
        rows.forEach(function(r){h+='<div style="display:flex;justify-content:space-between;font-size:12px;padding:3px 0;border-bottom:1px solid var(--border)"><span style="color:var(--text2)">'+r[0]+'</span><span style="font-weight:500">'+r[1]+'</span></div>'});
        return h+'</div>';
      }
      var dot=function(ok){return ok?'🟢':'🔴'};
      // System
      var sysRows=[[kr?'Python':'Python',d.python.split(' ')[0]],[kr?'플랫폼':'Platform',d.platform],[kr?'PID':'PID',d.pid],[kr?'메모리':'Memory',d.memory_mb+'MB'],[kr?'GC (0/1/2)':'GC (0/1/2)',d.gc.gen0+'/'+d.gc.gen1+'/'+d.gc.gen2]];
      // Engine
      var m=d.metrics||{};
      var engRows=[[kr?'활성 요청':'Active Requests',d.active_requests],[kr?'종료 중':'Shutting Down',d.shutting_down?'⚠️ Yes':'No'],[kr?'총 요청':'Total Requests',m.requests||0],[kr?'도구 호출':'Tool Calls',m.tool_calls||0],[kr?'에러':'Errors',m.errors||0],[kr?'캐시 히트':'Cache Hits',m.cache_hits||0]];
      // Session
      var sessRows=[[kr?'메시지 수':'Messages',d.session.messages],[kr?'컨텍스트 크기':'Context Size',(d.session.context_chars/1024).toFixed(1)+'KB']];
      // Tools
      var toolRows=[[kr?'등록된 도구':'Registered',d.tools.registered],[kr?'동적 도구':'Dynamic',d.tools.dynamic]];
      // Providers
      var provRows=[];
      for(var pn in d.providers){provRows.push([pn,dot(d.providers[pn])+' '+(d.providers[pn]?(kr?'연결됨':'Connected'):(kr?'키 없음':'No key'))])}
      provRows.push([kr?'Vault':'Vault',dot(d.vault_unlocked)+' '+(d.vault_unlocked?(kr?'열림':'Unlocked'):(kr?'잠김':'Locked'))]);
      panel.innerHTML=card('🖥️',kr?'시스템':'System',sysRows)+card('⚡',kr?'엔진':'Engine',engRows)+card('💬',kr?'세션 (web)':'Session (web)',sessRows)+card('🔧',kr?'도구':'Tools',toolRows)+card('🔑',kr?'프로바이더':'Providers',provRows);
    }).catch(function(e){panel.innerHTML='<div style="grid-column:1/-1;color:#f87171">Error: '+e.message+'</div>'});
  };
  document.getElementById('debug-auto-refresh').addEventListener('change',function(){
    if(this.checked){window._loadDebug();_debugAutoTimer=setInterval(window._loadDebug,3000)}
    else{clearInterval(_debugAutoTimer);_debugAutoTimer=null}
  });

  window._loadLogs=function(){
    var level=document.getElementById('log-level').value;
    var lines=document.getElementById('log-lines').value;
    var viewer=document.getElementById('log-viewer');
    viewer.textContent='Loading...';
    fetch('/api/logs?lines='+lines+'&level='+level,{headers:{'X-Session-Token':_tok}})
    .then(function(r){return r.json()}).then(function(d){
      var logs=d.logs||[];
      if(!logs.length){viewer.textContent='No logs found.';return}
      var html='';
      logs.forEach(function(ln){
        var cls='';
        if(ln.indexOf('[ERROR]')!==-1)cls='color:#f87171;font-weight:600';
        else if(ln.indexOf('[WARNING]')!==-1)cls='color:#fbbf24';
        else if(ln.indexOf('[INFO]')!==-1)cls='color:var(--text2)';
        html+='<div style="'+cls+';padding:1px 0;border-bottom:1px solid var(--border)">'+ln.replace(/</g,'&lt;').replace(/>/g,'&gt;')+'</div>';
      });
      viewer.innerHTML=html;
      viewer.scrollTop=viewer.scrollHeight;
    }).catch(function(e){viewer.textContent='Error: '+e.message});
  };
  document.getElementById('log-auto-refresh').addEventListener('change',function(){
    if(this.checked){_logAutoTimer=setInterval(window._loadLogs,5000)}
    else{clearInterval(_logAutoTimer);_logAutoTimer=null}
  });

  /* ── Model Router Tab (v2) ── */
})();
