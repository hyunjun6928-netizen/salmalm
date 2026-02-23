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
    var _stopBtn=document.getElementById('stop-btn');
    var _sendBtnEl=document.getElementById('send-btn');
    if(_stopBtn){_stopBtn.style.display='flex'}
    if(_sendBtnEl){_sendBtnEl.style.display='none'}
    var _sendStart=Date.now();
    _wsSendStart=_sendStart;
    var chatBody={message:msg,session:_currentSession,lang:_lang};
    if(imgData){chatBody.image_base64=imgData;chatBody.image_mime=imgMime}
    try{
      /* SSE primary (HTTP POST + stream) — no connection dependency
       * WS remains connected for real-time typing/thinking indicators only */
      await _sendViaSse(chatBody,_sendStart);
    }catch(se){var tr2=document.getElementById('typing-row');if(tr2)tr2.remove();addMsg('assistant','❌ Error: '+se.message)}
    finally{btn.disabled=false;input.focus();var _sb2=document.getElementById('stop-btn');var _sb3=document.getElementById('send-btn');if(_sb2)_sb2.style.display='none';if(_sb3)_sb3.style.display='flex'}
  }
  window.doSend=doSend;
