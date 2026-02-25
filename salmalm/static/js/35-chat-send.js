  /* --- Send via WebSocket with SSE fallback --- */
  function _sendViaWs(msg,session){
    return new Promise(function(resolve){
      if(!_wsReady||!_ws||_ws.readyState!==WebSocket.OPEN){resolve({fallback:true});return}
      _wsPendingResolve=resolve;
      _wsRequestPending=true;
      _wsRequestMsgCount=chat.querySelectorAll('.msg-row').length;
      var _wsPayload={type:'message',text:msg,session:session};
      if(window._pendingWsImage){_wsPayload.image=window._pendingWsImage.data;_wsPayload.image_mime=window._pendingWsImage.mime;window._pendingWsImage=null}
      _ws.send(JSON.stringify(_wsPayload));
    });
  }

  /* On page load, check if there was a pending SSE request that got interrupted by refresh.
     Called after auth is complete and chat is loaded (from 95-events.js or init flow). */
  window._checkPendingRecovery=function(){
    var sid=localStorage.getItem('salm_sse_pending');
    if(!sid)return;
    localStorage.removeItem('salm_sse_pending');
    /* Wait for server to finish, then check if last response is already shown */
    var polls=0;
    function _rpoll(){
      polls++;
      fetch('/api/sessions/'+encodeURIComponent(sid)+'/last',{headers:{'X-Session-Token':_tok}})
      .then(function(r){return r.json()}).then(function(d){
        if(!d.ok||!d.message){
          /* No assistant message yet — server still processing */
          if(polls<30)setTimeout(_rpoll,2000);
          return;
        }
        /* Fix #6: check if already displayed — compare raw text (dataset.rawtext) not rendered HTML */
        var snippet=d.message.substring(0,80);
        /* Strip markdown symbols for textContent fallback comparison */
        var snippetPlain=snippet.replace(/[*#`_\[\]()!>~]/g,'').replace(/\s+/g,' ').trim();
        var bubbles=chat.querySelectorAll('.msg-row.assistant .bubble');
        var alreadyShown=false;
        for(var i=bubbles.length-1;i>=Math.max(0,bubbles.length-5);i--){
          /* Primary: compare against stored raw text (exact) */
          var rawText=bubbles[i].dataset.rawtext||'';
          if(rawText&&rawText.indexOf(snippet.substring(0,rawText.length||80))>-1){alreadyShown=true;break}
          /* Fallback: compare markdown-stripped snippet against textContent */
          if(snippetPlain&&bubbles[i].textContent.indexOf(snippetPlain)>-1){alreadyShown=true;break}
        }
        if(!alreadyShown){
          addMsg('assistant',d.message,'🔄 recovered');
        }else if(polls<15){
          /* Maybe server hasn't finished yet, keep checking */
          setTimeout(_rpoll,2000);
        }
      }).catch(function(){if(polls<30)setTimeout(_rpoll,2000)});
    }
    /* First poll after 3s, then every 2s */
    setTimeout(_rpoll,3000);
  };

  async function _sendViaSse(chatBody,_sendStart){
    try{
      /* Mark pending so page refresh can recover */
      localStorage.setItem('salm_sse_pending',chatBody.session||'web');
      _currentAbort=new AbortController();
      var r=await fetch('/api/chat/stream',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},
        body:JSON.stringify(chatBody),signal:_currentAbort.signal});
      if(!r.ok||!r.body){throw new Error('stream unavailable')}
      var reader=r.body.getReader();var decoder=new TextDecoder();var buf='';var gotDone=false;
      var typingEl=document.getElementById('typing-row');
      /* Per-chunk stall timeout: if server holds connection open but sends nothing for 60s,
         abort and fall back to HTTP POST (prevents indefinite hang) */
      var _STALL_MS=60000;
      var _stallTimer=null;
      function _readWithTimeout(){
        return Promise.race([
          reader.read(),
          new Promise(function(_,reject){_stallTimer=setTimeout(function(){reject(new Error('SSE stall: no data for '+_STALL_MS+'ms'))},_STALL_MS)})
        ]);
      }
      while(true){
        var chunk=await _readWithTimeout();
        clearTimeout(_stallTimer);
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
              if(edata.input){var inp=typeof edata.input==='string'?edata.input:JSON.stringify(edata.input,null,2);if(inp.length>200)inp=inp.substring(0,200)+'...';toolH+='<details class="tool-block" style="margin-top:4px"><summary class="tool-header">📥 Input</summary><pre class="tool-body">'+inp.replace(/</g,'&lt;')+'</pre></details>'}
              if(!tb2._toolLog){tb2._toolLog='';tb2.innerHTML=''}
              tb2._toolLog+=toolH;tb2.innerHTML=tb2._toolLog;
            }}
          }else if(etype==='thinking'){
            if(typingEl){var tb5=typingEl.querySelector('.bubble');if(tb5){
              var thinkEl2=tb5.querySelector('.think-stream');
              if(!thinkEl2){tb5.innerHTML='<details class="think-stream" open style="font-size:12px;color:var(--text2);margin-bottom:6px"><summary style="cursor:pointer;font-weight:600">🧠 Thinking...</summary><pre class="think-content" style="white-space:pre-wrap;max-height:200px;overflow-y:auto;margin:4px 0;font-size:11px;opacity:0.7"></pre></details>';thinkEl2=tb5.querySelector('.think-stream')}
              var tc2=thinkEl2.querySelector('.think-content');if(tc2){tc2.textContent+=edata.text||'';tc2.scrollTop=tc2.scrollHeight}
            }}
          }else if(etype==='chunk'){
            if(typingEl){var tb4=typingEl.querySelector('.bubble');if(tb4){if(!tb4._streaming){tb4._streaming=true;tb4._streamBuf='';var thinkKeep2=tb4.querySelector('.think-stream');tb4.innerHTML='';if(thinkKeep2)tb4.appendChild(thinkKeep2);tb4._thinkEl=thinkKeep2||null}tb4._streamBuf+=(edata.text||'');if(!tb4._renderPending){tb4._renderPending=true;requestAnimationFrame(function(){if(!tb4._renderPending)return;tb4._renderPending=false;var buf=tb4._streamBuf||'';var fences=(buf.match(/```/g)||[]).length;if(fences%2!==0)buf+='```';var rendered=renderMd(buf);var tEl=tb4._thinkEl;tb4.innerHTML='';if(tEl)tb4.appendChild(tEl);tb4.insertAdjacentHTML('beforeend',rendered);var chatEl=document.getElementById('chat');if(chatEl)chatEl.scrollTop=chatEl.scrollHeight;})}}}
          }else if(etype==='ui_cmd'){
            /* AI-driven UI control */
            var act=edata.action,val=edata.value||'';
            if(act==='set_lang'){window.setLang(val)}
            else if(act==='set_theme'){document.body.setAttribute('data-theme',val);localStorage.setItem('salmalm-theme',val)}
            else if(act==='set_model'){fetch('/api/model/switch',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},body:JSON.stringify({model:val})}).then(function(){modelBadge.textContent=val.split('/').pop()})}
            else if(act==='new_session'){window.newSession&&window.newSession()}
            else if(act==='show_panel'){var panelMap={chat:'showChat',settings:'showSettings',dashboard:'showDashboard',sessions:'showSessions',cron:'showCron',memory:'showMemory',docs:'showDocs'};var fn=panelMap[val];if(fn&&window[fn])window[fn]()}
            else if(act==='add_cron'){fetch('/api/cron/add',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},body:JSON.stringify({name:edata.name||'ai-job',interval:edata.interval||3600,prompt:edata.prompt||''})}).then(function(){if(window._loadCron)window._loadCron()})}
          }else if(etype==='done'){
            gotDone=true;
            _currentAbort=null; /* Prevent stale abort after completion */
            localStorage.removeItem('salm_sse_pending');
            if(typingEl)typingEl.remove();
            /* Restore send button immediately */
            var _sbD=document.getElementById('stop-btn');var _sbDS=document.getElementById('send-btn');
            if(_sbD)_sbD.style.display='none';if(_sbDS)_sbDS.style.display='flex';
            btn.disabled=false;
            /* Auto-switch back to chat if user navigated away during generation */
            if(chat.style.display==='none'&&window.showChat)window.showChat();
            var _secs=((Date.now()-_sendStart)/1000).toFixed(1);
            var _cIcons={simple:'⚡',moderate:'🔧',complex:'💎',auto:''};
            var _cLabel=edata.complexity&&edata.complexity!=='auto'&&edata.complexity!=='manual'?(_cIcons[edata.complexity]||'')+edata.complexity+' → ':'';
            if(edata.complexity==='manual')_isAutoRouting=false;
            var _mShort=(edata.model||'').split('/').pop();
            var _sMeta=(_cLabel||'')+(_mShort||'');if(_sMeta)_sMeta+=' · ';_sMeta+='⏱️'+_secs+'s';addMsg('assistant',edata.response||'',_sMeta);
            modelBadge.textContent=_mShort?(_isAutoRouting?'Auto → '+_mShort:_mShort):'auto routing';
            fetch('/api/status').then(function(r2){return r2.json()}).then(function(s){costEl.textContent='$'+s.usage.total_cost.toFixed(4)});
            break; /* Exit reader loop immediately after done event */
          }
        }
        if(gotDone)break; /* Also break outer chunk loop */
      }
      /* Process any remaining data in buffer */
      if(buf.trim()){
        var em2=buf.match(/^event: (\w+)\ndata: (.+)$/m);
        if(em2){
          var etype2=em2[1],edata2=JSON.parse(em2[2]);
          if(etype2==='done'){
            gotDone=true;
            localStorage.removeItem('salm_sse_pending');
            if(document.getElementById('typing-row'))document.getElementById('typing-row').remove();
            if(chat.style.display==='none'&&window.showChat)window.showChat();
            var _secs3=((Date.now()-_sendStart)/1000).toFixed(1);
            var _cI2={simple:'⚡',moderate:'🔧',complex:'💎',auto:''};
            var _cL2=edata2.complexity&&edata2.complexity!=='auto'&&edata2.complexity!=='manual'?(_cI2[edata2.complexity]||'')+edata2.complexity+' → ':'';
            if(edata2.complexity==='manual')_isAutoRouting=false;
            var _mS2=(edata2.model||'').split('/').pop();
            var _sM2=(_cL2||'')+(_mS2||'');if(_sM2)_sM2+=' · ';_sM2+='⏱️'+_secs3+'s';addMsg('assistant',edata2.response||'',_sM2);
            modelBadge.textContent=_mS2?(_isAutoRouting?'Auto → '+_mS2:_mS2):'auto routing';
            fetch('/api/status').then(function(r2){return r2.json()}).then(function(s){costEl.textContent='$'+s.usage.total_cost.toFixed(4)});
          }
        }
      }
      if(!gotDone)throw new Error('stream incomplete');
      if(document.getElementById('typing-row'))document.getElementById('typing-row').remove();
    }catch(streamErr){
      /* User-initiated abort: clean up and stop — don't fallback */
      if(streamErr.name==='AbortError'){
        console.log('SSE aborted by user');
        if(document.getElementById('typing-row'))document.getElementById('typing-row').remove();
        return;
      }
      /* Do NOT remove salm_sse_pending here — page refresh triggers abort,
         and we need the flag to survive for recovery on reload */
      console.warn('SSE failed, falling back:',streamErr);
      var typRow=document.getElementById('typing-row');
      if(typRow){var tb3=typRow.querySelector('.bubble');if(tb3)tb3.innerHTML='<div class="typing-indicator"><span></span><span></span><span></span></div> Processing...'}
      try{
        var r2=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},
          body:JSON.stringify(chatBody)});
        var d=await r2.json();
        if(document.getElementById('typing-row'))document.getElementById('typing-row').remove();
        var _secs2=((Date.now()-_sendStart)/1000).toFixed(1);
        if(d.response){localStorage.removeItem('salm_sse_pending');var _fcI={simple:'⚡',moderate:'🔧',complex:'💎'};var _fcL=d.complexity&&d.complexity!=='auto'?(_fcI[d.complexity]||'')+d.complexity+' → ':'';var _fmS=(d.model||'').split('/').pop();var _meta=(_fcL||'')+(_fmS||'');if(_meta)_meta+=' · ';_meta+='⏱️'+_secs2+'s';addMsg('assistant',d.response,_meta);if(_fmS)modelBadge.textContent=_isAutoRouting?'Auto → '+_fmS:_fmS;}
        else if(d.error){localStorage.removeItem('salm_sse_pending');addMsg('assistant','❌ '+d.error);}
        fetch('/api/status').then(function(r3){return r3.json()}).then(function(s){costEl.textContent='$'+s.usage.total_cost.toFixed(4)});
      }catch(fbErr){
        console.error('Fallback POST also failed:',fbErr);
        if(document.getElementById('typing-row'))document.getElementById('typing-row').remove();
        localStorage.removeItem('salm_sse_pending');
        addMsg('assistant','❌ Connection error. Please try again.');
      }
    }
  }
