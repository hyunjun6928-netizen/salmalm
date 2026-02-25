  /* --- Helpers --- */
  var _copyId=0;
  function escHtml(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
  function _renderToolBlocks(t){
    /* Merge consecutive tool_call+tool_result into single compact block */
    t=t.replace(/<tool_call>\s*([\s\S]*?)\s*<\/tool_call>\s*<tool_result>\s*([\s\S]*?)\s*<\/tool_result>/g,function(_,callBody,resultBody){
      var name2=(callBody.match(/\"?name\"?\s*[:=]\s*"?(\w+)/)||['','tool'])[1];
      var preview2=resultBody.length>300?resultBody.substring(0,300)+'…':resultBody;
      return '<details class="tool-block"><summary class="tool-header">🔧 <b>'+name2+'</b> <span style="margin-left:auto;font-size:10px;opacity:0.6">✓ done</span></summary><pre class="tool-body">'+preview2.replace(/</g,'&lt;').replace(/>/g,'&gt;')+'</pre></details>';
    });
    /* Remaining unmatched tool_call (no result yet) */
    t=t.replace(/<tool_call>\s*([\s\S]*?)\s*<\/tool_call>/g,function(_,body){
      var name='tool';var args='';
      try{var parsed=JSON.parse(body.trim());name=parsed.name||'tool';args=JSON.stringify(parsed.arguments||parsed,null,2)}catch(e){args=body.trim()}
      if(args.length>200)args=args.substring(0,200)+'…';
      return '<details class="tool-block"><summary class="tool-header">🔧 <strong>'+name+'</strong> <span style="margin-left:auto;font-size:10px;opacity:0.6">⏳</span></summary><pre class="tool-body">'+args.replace(/</g,'&lt;').replace(/>/g,'&gt;')+'</pre></details>';
    });
    t=t.replace(/<tool_result>\s*([\s\S]*?)\s*<\/tool_result>/g,function(_,body){
      var preview=body.trim();if(preview.length>300)preview=preview.substring(0,300)+'...';
      return '<details class="tool-block"><summary class="tool-header">📤 Result</summary><pre class="tool-body">'+preview.replace(/</g,'&lt;').replace(/>/g,'&gt;')+'</pre></details>';
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
    /* Markdown transforms BEFORE restoring code blocks (so code content is not affected) */
    t=t.replace(/`([^`]+)`/g,function(_,c){return '<code>'+c+'</code>'});
    t=t.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
    t=t.replace(/\*([^*]+)\*/g,'<em>$1</em>');
    /* Tables — separator row → <!--TSEP--> marker for header detection */
    t=t.replace(/^\|(.+)\|\s*$/gm,function(_,row){
      var cells=row.split('|').map(function(c){return c.trim()});
      if(cells.every(function(c){return /^[-:]+$/.test(c)}))return '<!--TSEP-->';
      return '<tr>'+cells.map(function(c){return '<td style="padding:4px 8px;border:1px solid var(--border)">'+c+'</td>'}).join('')+'</tr>';
    });
    /* Wrap consecutive rows (and TSEP markers) in <table> */
    t=t.replace(/((<tr>.*?<[/]tr>|<!--TSEP-->)\s*)+/g,function(match){
      /* Convert first <tr> before TSEP to header row with <th> cells */
      var processed=match.replace(/(<tr>)(.*?)(<\/tr>)\s*<!--TSEP-->/,function(_,open,cells,close){
        var hdr=cells
          .replace(/<td style="([^"]*)"/g,'<th style="$1;background:var(--accent-dim,rgba(99,140,255,0.12));font-weight:600"')
          .replace(/<\/td>/g,'</th>');
        return '<thead>'+open+hdr+close+'</thead><tbody>';
      });
      /* Remove any remaining TSEP markers (e.g. tables with no header) */
      processed=processed.replace(/<!--TSEP-->\s*/g,'');
      /* Close tbody if we opened it */
      var closeTbody=processed.includes('<tbody>') ? '</tbody>' : '';
      return '<table style="border-collapse:collapse;margin:8px 0;font-size:13px;width:auto">'+processed+closeTbody+'</table>';
    });
    t=t.replace(/^### (.+)$/gm,'<h4 style="margin:8px 0 4px;font-size:13px;color:var(--accent2)">$1</h4>');
    t=t.replace(/^## (.+)$/gm,'<h3 style="margin:10px 0 6px;font-size:14px;color:var(--accent2)">$1</h3>');
    t=t.replace(/^# (.+)$/gm,'<h2 style="margin:12px 0 8px;font-size:16px;color:var(--accent2)">$1</h2>');
    t=t.replace(/^-{3,}$/gm,'<hr style="border:none;border-top:1px solid var(--border);margin:8px 0">');
    t=t.replace(/^[•\-] (.+)$/gm,'<div style="padding-left:16px;position:relative"><span style="position:absolute;left:4px">•</span>$1</div>');
    t=t.replace(/^(\d+)\. (.+)$/gm,'<div style="padding-left:16px">$1. $2</div>');
    /* Link rendering — sanitize href to block javascript:/data:/vbscript: XSS */
    t=t.replace(/\[([^\]]+)\]\(([^)]+)\)/g,function(_,label,url){
      var safeUrl=url.trim();
      /* Allow only http/https/ftp/mailto/relative URLs — block js/data/vbscript injection */
      if(/^(javascript|data|vbscript):/i.test(safeUrl))safeUrl='#blocked';
      return '<a href="'+safeUrl+'" target="_blank" rel="noopener noreferrer" style="color:var(--accent2);text-decoration:underline">'+label+'</a>';
    });
    t=t.replace(/uploads[/]([\w.-]+[.](png|jpg|jpeg|gif|webp))/gi,'<img src="/uploads/$1" style="max-width:400px;max-height:400px;border-radius:8px;display:block;margin:8px 0;cursor:pointer" alt="$1" data-action="openImage">');
    t=t.replace(/uploads[/]([\w.-]+[.](mp3|wav|ogg))/gi,'<audio controls src="/uploads/$1" style="display:block;margin:8px 0"></audio> 🔊 $1');
    /* Restore code blocks AFTER all markdown transforms */
    for(var ci=0;ci<codeBlocks.length;ci++){t=t.replace('%%CODEBLOCK'+ci+'%%',codeBlocks[ci])}
    /* Collapse 2+ consecutive blank lines into 1 */
    t=t.replace(/\n{2,}/g,'\n\n');
    t=t.replace(/\n/g,'<br>');
    /* Collapse excessive <br> chains */
    t=t.replace(/(<br>\s*){2,}/g,'<br>');
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
    /* Fix #6: store raw text for SSE recovery dedup comparison */
    bubble.dataset.rawtext=_cleanText.substring(0,200);
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
    /* Copy button for assistant messages */
    if(role==='assistant'&&_cleanText&&_cleanText.length>5){
      var copyBtn=document.createElement('button');copyBtn.className='tts-btn';copyBtn.textContent='📋';copyBtn.title=t('btn-copy-title')||'Copy';
      copyBtn.onclick=function(){
        var raw=_cleanText.replace(/<[^>]*>/g,'').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&amp;/g,'&');
        navigator.clipboard.writeText(raw).then(function(){copyBtn.textContent='✅';setTimeout(function(){copyBtn.textContent='📋'},1500)}).catch(function(){copyBtn.textContent='❌';setTimeout(function(){copyBtn.textContent='📋'},1500)});
      };
      mt.appendChild(copyBtn);
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
    var _sb=document.getElementById('stop-btn');var _sb2=document.getElementById('send-btn');
    if(_sb)_sb.style.display='none';if(_sb2)_sb2.style.display='flex';
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
