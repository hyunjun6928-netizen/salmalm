  /* --- Settings --- */
  var dashView=document.getElementById('dashboard-view');
  var sessView=document.getElementById('sessions-view');
  /* channels panel removed */
  var docsView=document.getElementById('docs-view');
  var cronView=document.getElementById('cron-view');
  var memView=document.getElementById('memory-view');
  function _hideAll(){settingsEl.style.display='none';dashView.style.display='none';sessView.style.display='none';docsView.style.display='none';cronView.style.display='none';memView.style.display='none';chat.style.display='none';inputArea.style.display='none'}
  window.showChat=function(){_hideAll();chat.style.display='flex';inputArea.style.display='block';chat.scrollTop=chat.scrollHeight};
  window.showSessions=function(){_hideAll();sessView.style.display='block';window._loadSessions()};
  window.showChannels=function(){window.showSettings()};
  window.showDocs=function(){_hideAll();docsView.style.display='block';try{window._renderDocs('')}catch(e){console.error('Docs render error:',e);document.getElementById('docs-content').innerHTML='<p style="color:#f87171">Render error: '+e.message+'</p>'}};
  window.showCron=function(){_hideAll();cronView.style.display='block';window._loadCron()};
  window.showMemory=function(){_hideAll();memView.style.display='block';window._loadMemory()};
  window.showSettings=function(){_hideAll();settingsEl.style.display='block';
    /* Auto-fill Google redirect URI with current origin */
    var _rUri=document.querySelector('.google-redirect-uri');if(_rUri)_rUri.textContent=location.origin+'/api/google/callback';
    /* Load personas */
    if(window.loadPersonas)window.loadPersonas();
    /* Auto-run doctor + usage chart */
    if(window._loadDoctor)window._loadDoctor();
    if(window._loadUsageChart)window._loadUsageChart();
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
      var _autoDefaults=_lang==='ko'
        ?{simple:'Haiku (최저가)',moderate:'Sonnet (균형)',complex:'Sonnet (균형)'}
        :{simple:'Haiku (cheapest)',moderate:'Sonnet (balanced)',complex:'Sonnet (balanced)'};
      ['simple','moderate','complex'].forEach(function(tier){
        var sel=document.getElementById('route-'+tier);
        if(sel){
          sel.innerHTML='<option value="">🔄 Auto — '+_autoDefaults[tier]+'</option>'+opts;
          sel.value=cfg[tier]||'';
        }
      });
    }).catch(function(){});
    /* Load SOUL.md */
    fetch('/api/soul',{headers:{'X-Session-Token':_tok}}).then(function(r){return r.json()}).then(function(d){
      var ed=document.getElementById('soul-editor');if(ed)ed.value=d.content||'';
    }).catch(function(){});
    fetch('/api/vault',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'keys'})})
      .then(function(r){return r.json()}).then(function(d){
        document.getElementById('vault-keys').innerHTML=d.keys.map(function(k){return '<div style="padding:4px 0;font-size:13px;color:var(--text2)">🔑 '+k+'</div>'}).join('');
        /* Show saved indicator on Telegram/Discord fields */
        var _vk=d.keys||[];
        if(_vk.indexOf('telegram_token')>=0){var _ti=document.getElementById('sk-telegram-token');if(_ti)_ti.placeholder='••••••••• (saved)'}
        if(_vk.indexOf('telegram_owner_id')>=0){var _to=document.getElementById('sk-telegram-owner');if(_to)_to.placeholder='••••••••• (saved)'}
        if(_vk.indexOf('discord_token')>=0){var _di=document.getElementById('sk-discord-token');if(_di)_di.placeholder='••••••••• (saved)'}
        if(_vk.indexOf('discord_guild_id')>=0){var _dg=document.getElementById('sk-discord-guild');if(_dg)_dg.placeholder='••••••••• (saved)'}
        if(_vk.indexOf('anthropic_api_key')>=0){var _an=document.getElementById('sk-anthropic');if(_an)_an.placeholder='••••••••• (saved)'}
        if(_vk.indexOf('openai_api_key')>=0){var _oa=document.getElementById('sk-openai');if(_oa)_oa.placeholder='••••••••• (saved)'}
        if(_vk.indexOf('xai_api_key')>=0){var _xa=document.getElementById('sk-xai');if(_xa)_xa.placeholder='••••••••• (saved)'}
        if(_vk.indexOf('google_api_key')>=0){var _ga=document.getElementById('sk-google');if(_ga)_ga.placeholder='••••••••• (saved)'}
        if(_vk.indexOf('brave_api_key')>=0){var _ba=document.getElementById('sk-brave');if(_ba)_ba.placeholder='••••••••• (saved)'}
        if(_vk.indexOf('openrouter_api_key')>=0){var _or=document.getElementById('sk-openrouter');if(_or)_or.placeholder='••••••••• (saved)'}
      });
    if(window.checkGoogleStatus)window.checkGoogleStatus();
    /* Load engine optimization settings */
    fetch('/api/engine/settings').then(function(r){return r.json()}).then(function(d){
      /* dynamic_tools always ON — no toggle needed */
      var pl=document.getElementById('eng-planning');if(pl)pl.checked=!!d.planning;
      var rf=document.getElementById('eng-reflection');if(rf)rf.checked=!!d.reflection;
      var cp=document.getElementById('eng-compaction');if(cp)cp.value=String(d.compaction_threshold||30000);
      var cc=document.getElementById('eng-cost-cap');if(cc)cc.value=d.cost_cap||'';
      var mi=document.getElementById('eng-max-tool-iter');if(mi)mi.value=String(d.max_tool_iterations||15);
      var ct=document.getElementById('eng-cache-ttl');if(ct)ct.value=String(d.cache_ttl||3600);
      var ba=document.getElementById('eng-batch-api');if(ba)ba.checked=!!d.batch_api;
      var fp=document.getElementById('eng-file-presummary');if(fp)fp.checked=!!d.file_presummary;
      var es=document.getElementById('eng-early-stop');if(es)es.checked=!!d.early_stop;
      var tc=document.getElementById('eng-temp-chat');if(tc){tc.value=String(d.temperature_chat!=null?d.temperature_chat:0.7);document.querySelectorAll('#eng-temp-chat-val,[data-label="eng-temp-chat-val"]').forEach(function(el){el.textContent=tc.value;});}
      var tt=document.getElementById('eng-temp-tool');if(tt){tt.value=String(d.temperature_tool!=null?d.temperature_tool:0.3);document.querySelectorAll('#eng-temp-tool-val,[data-label="eng-temp-tool-val"]').forEach(function(el){el.textContent=tt.value;});}
      var mtc=document.getElementById('eng-max-tokens-chat');if(mtc){var _v1=d.max_tokens_chat!=null?d.max_tokens_chat:512;mtc.value=String(_v1);var _t1=_v1===0?'Auto (동적)':String(_v1);document.querySelectorAll('#eng-max-tokens-chat-val,[data-label="eng-max-tokens-chat-val"]').forEach(function(el){el.textContent=_t1;});}
      var mtk=document.getElementById('eng-max-tokens-code');if(mtk){var _v2=d.max_tokens_code!=null?d.max_tokens_code:4096;mtk.value=String(_v2);var _t2=_v2===0?'Auto (동적)':String(_v2);document.querySelectorAll('#eng-max-tokens-code-val,[data-label="eng-max-tokens-code-val"]').forEach(function(el){el.textContent=_t2;});}
    }).catch(function(){});
    if(window._checkTgStatus)window._checkTgStatus();
    if(window._checkDcStatus)window._checkDcStatus();
    fetch('/api/status').then(function(r){return r.json()}).then(function(d){
      var u=d.usage,h='<div style="font-size:13px;line-height:2">📥 Input: '+u.total_input.toLocaleString()+' tokens<br>📤 Output: '+u.total_output.toLocaleString()+' tokens<br>💰 Cost: $'+u.total_cost.toFixed(4)+'<br>⏱️ Uptime: '+u.elapsed_hours+'h</div>';
      if(u.by_model){h+='<div style="margin-top:12px;font-size:12px">';for(var m in u.by_model){var v=u.by_model[m];h+='<div style="padding:4px 0;color:var(--text2)">'+m+': '+v.calls+'calls · $'+v.cost.toFixed(4)+'</div>'}h+='</div>'}
      document.getElementById('usage-detail').innerHTML=h});
  };
  window.showUsage=function(){window.showDashboard()};
