  /* --- Send --- */
  var _sending=false;
  var _pendingQueue=[];
  async function doSend(){
    var _inputText=input.value.trim();
    if(!_inputText&&!pendingFile)return;
    /* If already sending, queue the message instead of aborting */
    if(_sending){
      _pendingQueue.push({text:_inputText,files:pendingFiles.slice()});
      input.value='';input.style.height='auto';
      if(_inputText)addMsg('user',_inputText);
      if(pendingFiles.length)window.clearFile();
      return;
    }
    _sending=true;
    /* Client-side /rollback N command */
    var rollMatch=_inputText.match(/^\/rollback\s+(\d+)$/);
    if(rollMatch){
      input.value='';_sending=false;
      var cnt=parseInt(rollMatch[1]);
      fetch('/api/sessions/rollback',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},
        body:JSON.stringify({session_id:_currentSession,count:cnt})})
      .then(function(r){return r.json()}).then(function(d){
        if(d.ok){
          addMsg('assistant',t('rollback-done')+' '+d.removed+' '+t('rollback-pairs'));
          switchSession(_currentSession);
        }else{addMsg('assistant',t('rollback-fail')+' '+(d.error||''));}
      });
      return;
    }
    /* Client-side /branch command */
    if(_inputText==='/branch'){
      input.value='';_sending=false;
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
    var _filesToSend=pendingFiles.length?pendingFiles:(pendingFile?[pendingFile]:[]);
    if(_filesToSend.length){
      for(var fi=0;fi<_filesToSend.length;fi++){
        var _f=_filesToSend[fi];
        var isImg=_f.type.startsWith('image/');
        if(isImg){
          var reader=new FileReader();
          var previewUrl=await new Promise(function(res){reader.onload=function(){res(reader.result)};reader.readAsDataURL(_f)});
          addMsg('user','<img src="'+previewUrl+'" style="max-width:300px;max-height:300px;border-radius:8px;display:block;margin:4px 0" alt="'+_f.name+'">');
        }
        var fd=new FormData();fd.append('file',_f);
        try{
          var ur=await fetch('/api/upload',{method:'POST',body:fd});
          var ud=await ur.json();
          if(ud.ok){fileMsg+=(fileMsg?'\n':'')+ud.info;if(ud.image_base64&&!imgData){imgData=ud.image_base64;imgMime=ud.image_mime;window._pendingWsImage={data:imgData,mime:imgMime}}}
          else addMsg('assistant',t('upload-fail')+' '+(ud.error||''));
        }catch(ue){addMsg('assistant',t('upload-error')+' '+ue.message)}
      }
      window.clearFile();
    }

    var msg=(fileMsg?fileMsg+'\n':'')+_inputText;
    if(_inputText)addMsg('user',_inputText);
    if(!msg){btn.disabled=false;return}

    addTyping();
    var _stopBtn=document.getElementById('stop-btn');
    var _sendBtnEl=document.getElementById('send-btn');
    if(_stopBtn){_stopBtn.style.display='flex'}
    if(_sendBtnEl){_sendBtnEl.style.display='none'}
    /* Safety timeout: if typing still showing after 3 minutes, force cleanup */
    var _safetyTimer=setTimeout(function(){
      var tr=document.getElementById('typing-row');if(tr){tr.remove();addMsg('assistant','⚠️ '+(t('timeout-msg')||'Response timed out. Please try again.'));btn.disabled=false;var sb=document.getElementById('stop-btn');var sb2=document.getElementById('send-btn');if(sb)sb.style.display='none';if(sb2)sb2.style.display='flex'}
    },180000);
    var _sendStart=Date.now();
    _wsSendStart=_sendStart;
    var chatBody={message:msg,session:_currentSession,lang:_lang};
    if(imgData){chatBody.image_base64=imgData;chatBody.image_mime=imgMime}
    try{
      /* SSE primary (HTTP POST + stream) — no connection dependency
       * WS remains connected for real-time typing/thinking indicators only */
      await _sendViaSse(chatBody,_sendStart);
    }catch(se){var tr2=document.getElementById('typing-row');if(tr2)tr2.remove();addMsg('assistant','❌ Error: '+se.message)}
    finally{clearTimeout(_safetyTimer);_sending=false;btn.disabled=false;input.focus();var _sb2=document.getElementById('stop-btn');var _sb3=document.getElementById('send-btn');if(_sb2)_sb2.style.display='none';if(_sb3)_sb3.style.display='flex';var _tr3=document.getElementById('typing-row');if(_tr3)_tr3.remove();
      /* Process queued messages */
      if(_pendingQueue.length){var _next=_pendingQueue.shift();input.value=_next.text;if(_next.files&&_next.files.length){window.setFiles(_next.files)}doSend()}}
  }
  window.doSend=doSend;
  window._resetSendState=function(){_sending=false;_pendingQueue=[];};
