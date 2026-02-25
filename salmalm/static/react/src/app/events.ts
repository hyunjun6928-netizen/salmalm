import { chat, input, btn, costEl, modelBadge, settingsEl, filePrev, fileIconEl, fileNameEl, fileSizeEl, imgPrev, inputArea, _tok, pendingFile, pendingFiles, _currentSession, _sessionCache, _isAutoRouting, set_tok, set_pendingFile, set_pendingFiles, set_currentSession, set_sessionCache, set_isAutoRouting } from './globals';

  /* --- CSP-safe event delegation --- */
  var _qcMap={'qc-help':'/help','qc-sysmon':'Check system status','qc-memory':'Show memory files',
    'qc-cost':'Show cost report','qc-cron':'Show cron jobs','qc-python':'Calculate 1+1 in Python',
    'qc-image':'Generate image: a cat in galaxy','qc-tts':'Convert to speech: Hello world'};
  document.addEventListener('click',function(e){
    var el=e.target.closest('[data-action]');if(!el)return;
    var a=el.getAttribute('data-action');
    if(a==='newSession')window.newSession();
    else if(a==='clearAllSessions')window.clearAllSessions();
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
    else if(a==='runCronJob'){el.textContent='⏳';fetch('/api/cron/run',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok,'X-Requested-With':'XMLHttpRequest'},body:JSON.stringify({id:el.getAttribute('data-cron-id')})}).then(function(r){return r.json()}).then(function(d){el.textContent=d.ok?'✅':'❌';setTimeout(function(){el.textContent='▶️'},2000)}).catch(function(){el.textContent='❌'})}
    else if(a==='runDoctor'){if(typeof window._loadDoctor==='function')window._loadDoctor()}
    else if(a==='doBackup'){if(typeof window._doBackup==='function')window._doBackup()}
    else if(a==='doRestore'){if(typeof window._doRestore==='function')window._doRestore()}
    else if(a==='memRead'){window._readMemFile(el.getAttribute('data-mem-path'))}
    else if(a==='showSessions')window.showSessions();
    else if(a==='showChannels')window.showChannels();
    else if(a==='showDocs')window.showDocs();
    else if(a==='refreshSessions')window._loadSessions();
    else if(a==='sess-delete'){var sid=el.getAttribute('data-sid');if(sid&&confirm((_lang==='ko'?'세션을 삭제하시겠습니까?':'Delete this session?')+'\n'+sid)){fetch('/api/sessions/delete',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},body:JSON.stringify({session_id:sid})}).then(function(){window._loadSessions();loadSessions()})}}
    else if(a==='sess-open'){var sid2=el.getAttribute('data-sid');if(sid2){window._currentSession=sid2;showChat();loadSessions();loadChatHistory(sid2)}}
    else if(a==='toggleSidebar')window.toggleSidebar();
    else if(a==='toggleTheme')window.toggleTheme();
    else if(a==='setColorDot'){window.setColor(el.getAttribute('data-color'))}
    else if(a==='openDashboard')window.showDashboard();
    else if(a==='exportChat')window.exportChat('md');
    else if(a==='toggleExportMenu')window.toggleExportMenu();
    else if(a==='exportMd')window.exportMd();
    else if(a==='exportJson')window.exportJson();
    else if(a==='exportServerMd')window.exportServerMd();
    else if(a==='exportServerJson')window.exportServerJson();
    else if(a==='importChat')window.importChat();
    else if(a==='pwaInstall')window.pwaInstall();
    else if(a==='pwaDismiss')window.pwaDismiss();
    else if(a==='toggleThinking')window.toggleThinking();
    else if(a==='toggleMic')window.toggleMic();
    else if(a==='stopGen'){window._cancelGeneration();var _sb4=document.getElementById('stop-btn');var _sb5=document.getElementById('send-btn');if(_sb4)_sb4.style.display='none';if(_sb5)_sb5.style.display='flex'}
    else if(a==='queueMsg'){var _qi=document.getElementById('input');var _qm=_qi?_qi.value.trim():'';if(!_qm){if(window._msgQueue&&window._msgQueue.length>0){if(confirm((t('queue-clear')||'Queue has ')+window._msgQueue.length+(t('queue-clear2')||' messages. Clear?'))){window._msgQueue=[];var _qb0=document.getElementById('queue-btn');if(_qb0)_qb0.textContent='📥'}}else{window._toast&&window._toast(t('queue-empty')||'Type a message first')}return}if(!window._msgQueue)window._msgQueue=[];window._msgQueue.push(_qm);_qi.value='';_qi.style.height='auto';var _qb=document.getElementById('queue-btn');if(_qb)_qb.textContent='📥'+window._msgQueue.length;window._toast&&window._toast((_lang==='ko'?'큐에 추가됨':'Queued')+' ('+window._msgQueue.length+')')}
    else if(a==='clearFile')window.clearFile();
    else if(a==='toggleTools'){var tl=document.getElementById('tools-list');tl.style.display=tl.style.display==='none'?'block':'none'}
    else if(a==='tool-run'){var treq=el.getAttribute('data-tool-req');if(treq){var kr2=_lang==='ko';var reqMap={
      google:{title:kr2?'🔗 Google OAuth 연동 필요':'🔗 Google OAuth Required',
        msg:kr2?'이 도구는 Google 계정 연동이 필요합니다.\n\n설정 방법:\n1. Settings → Google Integration\n2. Google Cloud Console에서 OAuth Client ID 생성\n3. Client ID와 Secret 입력\n4. "Connect Google Account" 클릭\n\n연동 후 Gmail, Calendar 도구를 사용할 수 있습니다.':'This tool requires Google account connection.\n\nSetup:\n1. Settings → Google Integration\n2. Create OAuth Client ID at Google Cloud Console\n3. Enter Client ID and Secret\n4. Click "Connect Google Account"\n\nAfter connecting, Gmail and Calendar tools will work.'},
      brave:{title:kr2?'🔑 Brave API 키 필요':'🔑 Brave API Key Required',
        msg:kr2?'이 도구는 Brave Search API 키가 필요합니다.\n\n설정 방법:\n1. https://brave.com/search/api/ 에서 API 키 발급\n2. Settings → Model 탭 → Brave API Key 입력\n\n입력 후 웹 검색, 이미지 검색, 뉴스 검색을 사용할 수 있습니다.':'This tool requires a Brave Search API key.\n\nSetup:\n1. Get an API key at https://brave.com/search/api/\n2. Settings → Model tab → Enter Brave API Key\n\nAfter setup, web search, image search, and news search will work.'},
      openai:{title:kr2?'🔑 OpenAI API 키 필요':'🔑 OpenAI API Key Required',
        msg:kr2?'이 도구는 OpenAI API 키가 필요합니다.\n\n설정 방법:\n1. https://platform.openai.com/api-keys 에서 키 발급\n2. Settings → Model 탭 → OpenAI API Key 입력\n\n입력 후 이미지 생성(DALL-E), 음성 변환(TTS/STT) 등을 사용할 수 있습니다.':'This tool requires an OpenAI API key.\n\nSetup:\n1. Get a key at https://platform.openai.com/api-keys\n2. Settings → Model tab → Enter OpenAI API Key\n\nAfter setup, image generation (DALL-E), TTS/STT will work.'},
      browser:{title:kr2?'🌐 브라우저 설정 필요':'🌐 Browser Setup Required',
        msg:kr2?'이 도구는 Playwright가 필요합니다.\n\n설정 방법:\n1. pip install salmalm[browser]\n2. playwright install chromium\n\n설치 후 AI가 웹 브라우징, 스크린샷, 폼 입력, 페이지 조작을 자동으로 수행할 수 있습니다.':'This tool requires Playwright.\n\nSetup:\n1. pip install salmalm[browser]\n2. playwright install chromium\n\nOnce installed, the AI can browse the web, take screenshots, fill forms, and interact with pages.'}
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
    else if(a==='save-telegram-token'){window.saveKey('telegram_token','sk-telegram-token');setTimeout(window._checkTgStatus,1000)}
    else if(a==='save-telegram-owner')window.saveKey('telegram_owner_id','sk-telegram-owner');
    else if(a==='save-discord-token'){window.saveKey('discord_token','sk-discord-token');setTimeout(window._checkDcStatus,1000)}
    else if(a==='save-discord-guild')window.saveKey('discord_guild_id','sk-discord-guild');
    else if(a==='saveEngineSettings'){
      var payload={
        dynamic_tools:true,
        planning:!!document.getElementById('eng-planning').checked,
        reflection:!!document.getElementById('eng-reflection').checked,
        compaction_threshold:parseInt(document.getElementById('eng-compaction').value)||30000,
        max_tool_iterations:parseInt(document.getElementById('eng-max-tool-iter').value)||15,
        cache_ttl:parseInt(document.getElementById('eng-cache-ttl').value)||3600,
        batch_api:!!document.getElementById('eng-batch-api').checked,
        file_presummary:!!document.getElementById('eng-file-presummary').checked,
        early_stop:!!document.getElementById('eng-early-stop').checked,
        cost_cap:document.getElementById('eng-cost-cap').value.trim(),
        temperature_chat:parseFloat(document.getElementById('eng-temp-chat').value)||0.7,
        temperature_tool:parseFloat(document.getElementById('eng-temp-tool').value)||0.3,
        max_tokens_chat:parseInt(document.getElementById('eng-max-tokens-chat').value)||512,
        max_tokens_code:parseInt(document.getElementById('eng-max-tokens-code').value)||4096
      };
      fetch('/api/engine/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})
        .then(function(r){return r.json()}).then(function(d){
          var re=document.getElementById('eng-save-result');
          if(re)re.innerHTML='<span style="color:#4ade80">✅ Saved</span>';
          setTimeout(function(){if(re)re.innerHTML=''},3000);
        }).catch(function(e){var re=document.getElementById('eng-save-result');if(re)re.innerHTML='<span style="color:#f87171">❌ '+e.message+'</span>'})
    }
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
      if(typeof window.setModel==='function'){
        window.setModel(model);
        setTimeout(function(){if(typeof window._loadModelRouter==='function')window._loadModelRouter()},300);
      }
    }
    else if(a==='resetCooldowns'){
      el.textContent='⏳...';
      fetch('/api/cooldowns/reset',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok,'X-Requested-With':'XMLHttpRequest'},body:'{}'})
      .then(function(r){return r.json()}).then(function(d){
        if(d.ok){el.textContent='✅';setTimeout(function(){if(typeof window._loadModelRouter==='function')window._loadModelRouter()},500)}
        else{el.textContent='❌'}
      }).catch(function(){el.textContent='❌'});
    }
    else if(a==='toggleFeatCat'){el.parentElement.classList.toggle('open')}
    else if(a==='fillCommand'){var inp=document.getElementById('input');inp.value=el.getAttribute('data-cmd');inp.focus()}
    else if(a==='toggleUser'){var uid=parseInt(el.getAttribute('data-uid'));var en=el.getAttribute('data-enabled')==='true';window.toggleUser(uid,en)}
    else if(a==='deleteUser'){window.deleteUser(el.getAttribute('data-username'))}
    else if(a==='saveOllama'){var u=document.getElementById('s-ollama-url').value;var k=document.getElementById('s-ollama-key')?document.getElementById('s-ollama-key').value:'';fetch('/api/vault',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'set',key:'ollama_url',value:u})}).then(function(){if(k){return fetch('/api/vault',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'set',key:'ollama_api_key',value:k})})}}).then(function(){addMsg('assistant','✅ Local LLM config saved');if(typeof window._loadModelRouter==='function')window._loadModelRouter()})}
    else if(a==='autoOptimizeRouting'){
      var st=document.getElementById('route-status');if(st)st.textContent='⏳...';
      fetch('/api/routing/optimize',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},body:'{}'}).then(function(r){return r.json()}).then(function(d){
        if(d.ok&&d.config){
          var kr=document.documentElement.lang==='kr';
          // Update dropdowns
          ['simple','moderate','complex'].forEach(function(t){
            var sel=document.getElementById('route-'+t);
            if(sel&&d.config[t]){sel.value=d.config[t]}
          });
          // Build summary text
          var parts=[];
          if(d.summary){
            ['simple','moderate','complex'].forEach(function(t){
              var s=d.summary[t];if(s){
                var label=t==='simple'?(kr?'간단':'Simple'):t==='moderate'?(kr?'보통':'Moderate'):(kr?'복잡':'Complex');
                parts.push(label+': '+s.name+' ($'+s.cost_input+'/'+s.cost_output+')');
              }
            });
          }
          if(st)st.innerHTML='✅ '+(kr?'최적화 완료! ':'Optimized! ')+parts.join(' · ');
          setTimeout(function(){if(st)st.textContent=''},5000);
        }else{if(st)st.textContent='❌ '+(d.error||'Failed')}
      }).catch(function(e){if(st)st.textContent='❌ '+e})
    }
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
  /* Temperature & max-tokens slider live label update (querySelectorAll for duplicate EN/KR ids) */
  function _updateAll(sel,txt){document.querySelectorAll(sel).forEach(function(el){el.textContent=txt;});}
  document.addEventListener('input',function(e){
    if(e.target.id==='eng-temp-chat')_updateAll('#eng-temp-chat-val,[data-label="eng-temp-chat-val"]',e.target.value);
    if(e.target.id==='eng-temp-tool')_updateAll('#eng-temp-tool-val,[data-label="eng-temp-tool-val"]',e.target.value);
    if(e.target.id==='eng-max-tokens-chat')_updateAll('#eng-max-tokens-chat-val,[data-label="eng-max-tokens-chat-val"]',e.target.value==='0'?'Auto (동적)':e.target.value);
    if(e.target.id==='eng-max-tokens-code')_updateAll('#eng-max-tokens-code-val,[data-label="eng-max-tokens-code-val"]',e.target.value==='0'?'Auto (동적)':e.target.value);
  });
  document.addEventListener('keydown',function(e){
    if(e.key!=='Enter')return;
    var el=e.target.closest('[data-enter-action]');if(!el)return;
    var a=el.getAttribute('data-enter-action');
    if(a==='go'&&typeof go==='function')go();
    else if(a==='unlock'&&typeof unlock==='function')unlock();
  });

