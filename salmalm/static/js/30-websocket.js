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
            toolHtml+='<details class="tool-block" style="margin-top:4px"><summary class="tool-header">📥 Input</summary><pre class="tool-body">'+inputStr.replace(/</g,'&lt;')+'</pre></details>';
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
      var _wcIcons={simple:'⚡',moderate:'🔧',complex:'💎'};
      var _wcLabel=data.complexity&&data.complexity!=='auto'?(_wcIcons[data.complexity]||'')+data.complexity+' → ':'';
      var _wmShort=(data.model||'').split('/').pop();
      addMsg('assistant',data.text||'',_wcLabel+_wmShort+' · ⏱️'+_secs+'s');
      if(_wmShort)modelBadge.textContent=_wmShort;
      fetch('/api/status').then(function(r){return r.json()}).then(function(s){costEl.textContent='$'+s.usage.total_cost.toFixed(4)});
      /* Queue drain: send next queued message */
      if(window._msgQueue&&window._msgQueue.length>0){var _nextMsg=window._msgQueue.shift();setTimeout(function(){var _inp=document.getElementById('input');if(_inp){_inp.value=_nextMsg;window.doSend()}},500)}
      var _sb=document.getElementById('stop-btn');var _sbSend=document.getElementById('send-btn');if(_sb)_sb.style.display='none';if(_sbSend)_sbSend.style.display='flex';
      if(_wsPendingResolve){_wsPendingResolve({done:true});_wsPendingResolve=null}
    }else if(data.type==='error'){
      if(typingEl)typingEl.remove();
      addMsg('assistant','❌ '+data.error);
      var _sb2=document.getElementById('stop-btn');var _sb2Send=document.getElementById('send-btn');if(_sb2)_sb2.style.display='none';if(_sb2Send)_sb2Send.style.display='flex';
      if(_wsPendingResolve){_wsPendingResolve({done:true});_wsPendingResolve=null}
    }else if(data.type==='shutdown'){
      if(typingEl)typingEl.remove();
      addMsg('assistant','⚠️ '+(data.message||'Server is shutting down...'));
      var _sb3=document.getElementById('stop-btn');var _sb3Send=document.getElementById('send-btn');if(_sb3)_sb3.style.display='none';if(_sb3Send)_sb3Send.style.display='flex';
      if(_wsPendingResolve){_wsPendingResolve({done:true});_wsPendingResolve=null}
    }
  }

  /* Connect on load */
  _wsConnect();
