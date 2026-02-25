import { chat, input, btn, costEl, modelBadge, settingsEl, filePrev, fileIconEl, fileNameEl, fileSizeEl, imgPrev, inputArea, _tok, pendingFile, pendingFiles, _currentSession, _sessionCache, _isAutoRouting, set_tok, set_pendingFile, set_pendingFiles, set_currentSession, set_sessionCache, set_isAutoRouting } from './globals';

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

