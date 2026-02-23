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
    var pending=localStorage.getItem('salm_sse_pending');
    console.log('[Recovery] checking pending:',pending,'tok:',_tok?'yes':'NO');
    if(!pending)return;
    var pd;try{pd=JSON.parse(pending)}catch(e){localStorage.removeItem('salm_sse_pending');return}
    var sid=pd.session||'web';
    var msgCount=pd.msgCount||0;
    var startTime=pd.ts||0;
    /* If pending flag is older than 5 minutes, discard */
    if(startTime&&Date.now()-startTime>300000){console.log('[Recovery] expired, discarding');localStorage.removeItem('salm_sse_pending');return}
    localStorage.removeItem('salm_sse_pending');
    /* Show recovery indicator */
    addMsg('assistant','⏳ Recovering response after refresh...');
    var polls=0;
    function _rpoll(){
      polls++;
      console.log('[Recovery] poll #'+polls+' sid='+sid+' msgCount='+msgCount);
      fetch('/api/sessions/'+encodeURIComponent(sid)+'/last',{headers:{'X-Session-Token':_tok}})
      .then(function(r){return r.json()}).then(function(d){
        console.log('[Recovery] response:',JSON.stringify(d).substring(0,200));
        if(d.ok&&d.message&&d.msg_count>msgCount){
          /* Remove the "recovering" message and show actual response */
          var rows=chat.querySelectorAll('.msg-row');
          var last=rows[rows.length-1];
          if(last){var b=last.querySelector('.bubble');if(b&&b.textContent.indexOf('Recovering')>-1)last.remove()}
          addMsg('assistant',d.message,'🔄 recovered after refresh');
        }else if(polls<30){
          /* Server still processing — keep polling (up to 60s) */
          setTimeout(_rpoll,2000);
        }else{
          /* Give up */
          var rows2=chat.querySelectorAll('.msg-row');
          var last2=rows2[rows2.length-1];
          if(last2){var b2=last2.querySelector('.bubble');if(b2&&b2.textContent.indexOf('Recovering')>-1)last2.remove()}
          addMsg('assistant','⚠️ Response may still be processing. Check back shortly or resend.');
        }
      }).catch(function(e){console.error('[Recovery] fetch error:',e);if(polls<30)setTimeout(_rpoll,2000)});
    }
    /* Wait for server to finish processing */
    setTimeout(_rpoll,3000);
  };

  async function _sendViaSse(chatBody,_sendStart){
    try{
      /* Mark pending so page refresh can recover */
      var _preMsgCount=chat.querySelectorAll('.msg-row').length;
      localStorage.setItem('salm_sse_pending',JSON.stringify({session:chatBody.session||'web',msgCount:_preMsgCount,ts:Date.now()}));
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
            if(typingEl){var tb4=typingEl.querySelector('.bubble');if(tb4){if(!tb4._streaming){tb4._streaming=true;var thinkKeep2=tb4.querySelector('.think-stream');tb4.innerHTML='';if(thinkKeep2)tb4.appendChild(thinkKeep2)}tb4.insertAdjacentHTML('beforeend',edata.text.replace(/</g,'&lt;'))}}
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
            localStorage.removeItem('salm_sse_pending');
            if(typingEl)typingEl.remove();
            /* Auto-switch back to chat if user navigated away during generation */
            if(chat.style.display==='none'&&window.showChat)window.showChat();
            var _secs=((Date.now()-_sendStart)/1000).toFixed(1);
            var _cIcons={simple:'⚡',moderate:'🔧',complex:'💎',auto:''};
            var _cLabel=edata.complexity&&edata.complexity!=='auto'?(_cIcons[edata.complexity]||'')+edata.complexity+' → ':'';
            var _mShort=(edata.model||'').split('/').pop();
            var _sMeta=(_cLabel||'')+(_mShort||'');if(_sMeta)_sMeta+=' · ';_sMeta+='⏱️'+_secs+'s';addMsg('assistant',edata.response||'',_sMeta);
            modelBadge.textContent=_mShort||'auto routing';
            fetch('/api/status').then(function(r2){return r2.json()}).then(function(s){costEl.textContent='$'+s.usage.total_cost.toFixed(4)});
          }
        }
      }
      if(!gotDone)throw new Error('stream incomplete');
      if(document.getElementById('typing-row'))document.getElementById('typing-row').remove();
    }catch(streamErr){
      localStorage.removeItem('salm_sse_pending');
      console.warn('SSE failed, falling back:',streamErr);
      var typRow=document.getElementById('typing-row');
      if(typRow){var tb3=typRow.querySelector('.bubble');if(tb3)tb3.innerHTML='<div class="typing-indicator"><span></span><span></span><span></span></div> Processing...'}
      var r2=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},
        body:JSON.stringify(chatBody)});
      var d=await r2.json();
      if(document.getElementById('typing-row'))document.getElementById('typing-row').remove();
      var _secs2=((Date.now()-_sendStart)/1000).toFixed(1);
      if(d.response){var _fcI={simple:'⚡',moderate:'🔧',complex:'💎'};var _fcL=d.complexity&&d.complexity!=='auto'?(_fcI[d.complexity]||'')+d.complexity+' → ':'';var _fmS=(d.model||'').split('/').pop();var _meta=(_fcL||'')+(_fmS||'');if(_meta)_meta+=' · ';_meta+='⏱️'+_secs2+'s';addMsg('assistant',d.response,_meta);if(_fmS)modelBadge.textContent=_fmS;}
      else if(d.error)addMsg('assistant','❌ '+d.error);
      fetch('/api/status').then(function(r3){return r3.json()}).then(function(s){costEl.textContent='$'+s.usage.total_cost.toFixed(4)});
    }
  }
