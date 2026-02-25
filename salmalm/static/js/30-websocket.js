  /* --- WebSocket Connection Manager --- */
  var _ws=null,_wsReady=false,_wsBackoff=500,_wsMaxBackoff=30000,_wsTimer=null,_wsPingTimer=null;
  var _wsPendingResolve=null,_wsSendStart=0,_wsRequestPending=false,_wsRequestMsgCount=0;
  var _wsRetryCount=0,_wsLastConnectedAt=0;

  function _wsUrl(){
    var proto=location.protocol==='https:'?'wss:':'ws:';
    var host=location.hostname||'localhost';
    var port=location.port;
    /* Behind nginx (port 80/443/empty): WS through same nginx host */
    if(!port||port==='80'||port==='443'){return proto+'//'+location.host;}
    /* Direct access: WS on port 18801 */
    return proto+'//'+host+':18801';
  }

  function _wsConnect(){
    if(_ws&&(_ws.readyState===WebSocket.CONNECTING||_ws.readyState===WebSocket.OPEN))return;
    try{_ws=new WebSocket(_wsUrl())}catch(e){console.warn('WS connect error:',e);_wsScheduleReconnect();return}
    _ws.onopen=function(){
      _wsReady=true;_wsBackoff=500;_wsRetryCount=0;_wsLastConnectedAt=Date.now();
      /* Restore badge color silently on reconnect */
      if(modelBadge)modelBadge.style.opacity='';
      console.log('WS connected');
      _wsStartPing();
      /* Recover lost response after reconnect */
      if(_wsRequestPending){
        _wsRequestPending=false;
        setTimeout(function(){_wsRecoverResponse()},500);
      }
    };
    _ws.onclose=function(ev){
      _wsReady=false;_wsStopPing();
      /* Dim badge slightly — silent visual cue, no modal/error */
      if(modelBadge)modelBadge.style.opacity='0.45';
      if(_wsPendingResolve){_wsPendingResolve({fallback:true});_wsPendingResolve=null}
      /* Auto-reconnect — always retry, with exponential backoff + jitter */
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
    _wsRetryCount++;
    /* Exponential backoff with ±20% jitter to avoid thundering herd */
    var jitter=_wsBackoff*0.2*(Math.random()*2-1);
    var delay=Math.min(_wsBackoff+jitter,_wsMaxBackoff);
    _wsTimer=setTimeout(function(){_wsTimer=null;_wsConnect();},delay);
    _wsBackoff=Math.min(_wsBackoff*1.5,_wsMaxBackoff);
    if(_wsRetryCount<=3)console.log('WS reconnect in '+(delay|0)+'ms (attempt '+_wsRetryCount+')');
  }

  function _wsStartPing(){
    _wsStopPing();
    _wsPingTimer=setInterval(function(){
      if(_ws&&_ws.readyState===WebSocket.OPEN)_ws.send(JSON.stringify({type:'ping'}));
      /* Also detect stale connections: if no pong in 10s, reconnect */
    },25000);
  }
  function _wsStopPing(){if(_wsPingTimer){clearInterval(_wsPingTimer);_wsPingTimer=null}}

  function _wsHandleMessage(data){
    var typingEl=document.getElementById('typing-row');
    if(data.type==='thinking'){
      if(typingEl){var tb0=typingEl.querySelector('.bubble');if(tb0){
        var thinkEl=tb0.querySelector('.think-stream');
        if(!thinkEl){tb0.innerHTML='<details class="think-stream" open style="font-size:12px;color:var(--text2);margin-bottom:6px"><summary style="cursor:pointer;font-weight:600">🧠 Thinking...</summary><pre class="think-content" style="white-space:pre-wrap;max-height:200px;overflow-y:auto;margin:4px 0;font-size:11px;opacity:0.7"></pre></details>';thinkEl=tb0.querySelector('.think-stream')}
        var tc=thinkEl.querySelector('.think-content');if(tc){tc.textContent+=data.text||'';tc.scrollTop=tc.scrollHeight}
      }}
      return;
    }
    if(data.type==='chunk'){
      if(typingEl){var tb=typingEl.querySelector('.bubble');if(tb){if(!tb._streaming){tb._streaming=true;var thinkKeep=tb.querySelector('.think-stream');tb.innerHTML='';if(thinkKeep)tb.appendChild(thinkKeep)}tb.insertAdjacentHTML('beforeend',data.text.replace(/</g,'&lt;'))}}
    }else if(data.type==='tool'){
      if(typingEl){
        var tb2=typingEl.querySelector('.bubble');
        if(tb2){
          /* Show tool execution detail */
          var toolHtml='<div style="display:flex;align-items:center;gap:8px"><div class="typing-indicator"><span></span><span></span><span></span></div> <span style="font-weight:600">🔧 '+data.name+'</span></div>';
          if(data.input){
            var inputStr=typeof data.input==='string'?data.input:JSON.stringify(data.input,null,2);
            if(inputStr.length>200)inputStr=inputStr.substring(0,200)+'...';
            toolHtml+='<details class="tool-block" style="margin-top:4px"><summary class="tool-header">📥 Input</summary><pre class="tool-body">'+inputStr.replace(/</g,'&lt;')+'</pre></details>';
          }
          /* Append to tool log instead of replacing */
          if(!tb2._toolLog){tb2._toolLog='';tb2.innerHTML=''}
          tb2._toolLog+=toolHtml;
          tb2.innerHTML=tb2._toolLog;
        }
      }
    }else if(data.type==='done'){
      _wsRequestPending=false;
      if(typingEl)typingEl.remove();
      var _secs=((Date.now()-_wsSendStart)/1000).toFixed(1);
      var _wcIcons={simple:'⚡',moderate:'🔧',complex:'💎'};
      var _wcLabel=data.complexity&&data.complexity!=='auto'&&data.complexity!=='manual'?(_wcIcons[data.complexity]||'')+data.complexity+' → ':'';
      if(data.complexity==='manual')_isAutoRouting=false;
      var _wmShort=(data.model||'').split('/').pop();
      addMsg('assistant',data.text||'',_wcLabel+_wmShort+' · ⏱️'+_secs+'s');
      if(_wmShort)modelBadge.textContent=_isAutoRouting?'Auto → '+_wmShort:_wmShort;
      fetch('/api/status').then(function(r){return r.json()}).then(function(s){costEl.textContent='$'+s.usage.total_cost.toFixed(4)});
      /* Queue drain: send next queued message */
      if(window._msgQueue&&window._msgQueue.length>0){var _nextMsg=window._msgQueue.shift();setTimeout(function(){var _inp=document.getElementById('input');if(_inp){_inp.value=_nextMsg;window.doSend()}},500)}
      var _sb=document.getElementById('stop-btn');var _sbSend=document.getElementById('send-btn');if(_sb)_sb.style.display='none';if(_sbSend)_sbSend.style.display='flex';
      if(_wsPendingResolve){_wsPendingResolve({done:true});_wsPendingResolve=null}
    }else if(data.type==='error'){
      _wsRequestPending=false;
      if(typingEl)typingEl.remove();
      addMsg('assistant','❌ '+data.error);
      var _sb2=document.getElementById('stop-btn');var _sb2Send=document.getElementById('send-btn');if(_sb2)_sb2.style.display='none';if(_sb2Send)_sb2Send.style.display='flex';
      if(_wsPendingResolve){_wsPendingResolve({done:true});_wsPendingResolve=null}
    }else if(data.type==='shutdown'){
      if(typingEl)typingEl.remove();
      addMsg('assistant','⚠️ '+(data.message||'Server is shutting down...'));
      var _sb3=document.getElementById('stop-btn');var _sb3Send=document.getElementById('send-btn');if(_sb3)_sb3.style.display='none';if(_sb3Send)_sb3Send.style.display='flex';
      if(_wsPendingResolve){_wsPendingResolve({done:true});_wsPendingResolve=null}
    }else if(data.type==='update_status'){
      if(data.status==='installing'){
        addMsg('assistant','⏳ Updating SalmAlm... please wait.');
      }else if(data.status==='complete'){
        addMsg('assistant','✅ Updated to v'+(data.version||'?')+'. Restarting...');
        _waitForServerThenReload();
      }
    }
  }

  /* Recover response after WS reconnect */
  function _wsRecoverResponse(){
    var typingEl=document.getElementById('typing-row');
    var sid=window._currentSession||'web';
    var _pollCount=0;
    function _poll(){
      _pollCount++;
      fetch('/api/sessions/'+encodeURIComponent(sid)+'/last',{headers:{'X-Session-Token':_tok}})
      .then(function(r){return r.json()}).then(function(d){
        if(d.ok&&d.message&&d.msg_count>_wsRequestMsgCount){
          /* New response arrived — show it */
          if(typingEl)typingEl.remove();
          addMsg('assistant',d.message,'🔄 recovered');
          var _sb=document.getElementById('stop-btn');var _sbS=document.getElementById('send-btn');
          if(_sb)_sb.style.display='none';if(_sbS)_sbS.style.display='flex';
          if(_wsPendingResolve){_wsPendingResolve({done:true});_wsPendingResolve=null}
        }else if(_pollCount<20){
          /* Still processing — poll again */
          if(typingEl){var tb=typingEl.querySelector('.bubble');if(tb&&!tb._streaming)tb.innerHTML='<div class="typing-indicator"><span></span><span></span><span></span></div> ⏳ Reconnected, waiting for response...'}
          setTimeout(_poll,3000);
        }else{
          /* Give up */
          if(typingEl)typingEl.remove();
          addMsg('assistant','⚠️ Response may have been lost. Check chat history or resend.');
          if(_wsPendingResolve){_wsPendingResolve({done:true});_wsPendingResolve=null}
        }
      }).catch(function(){if(_pollCount<20)setTimeout(_poll,3000)});
    }
    _poll();
  }

  /* Poll /api/health until server is back up, then reload — prevents blank page on restart */
  function _waitForServerThenReload(maxTries,interval){
    maxTries=maxTries||30;interval=interval||1000;
    var tries=0;
    function _poll(){
      tries++;
      fetch('/api/health',{cache:'no-store'})
      .then(function(r){
        if(r.ok){location.reload();}
        else if(tries<maxTries){setTimeout(_poll,interval);}
        else{location.reload();} /* give up and reload anyway */
      })
      .catch(function(){
        if(tries<maxTries){setTimeout(_poll,interval);}
        else{location.reload();}
      });
    }
    /* Wait 1s before first attempt (server is shutting down) */
    setTimeout(_poll,1000);
  }
  window._waitForServerThenReload=_waitForServerThenReload;

  /* Connect on load */
  _wsConnect();
