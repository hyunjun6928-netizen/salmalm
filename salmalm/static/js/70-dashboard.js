  var _dashMode='tokens';
  window.showDashboard=function(){
    _hideAll();dashView.style.display='block';
    /* Set default date range to today */
    var today=new Date().toISOString().slice(0,10);
    if(!document.getElementById('dash-from').value){document.getElementById('dash-from').value=today;document.getElementById('dash-to').value=today}
    window._refreshDash();
    var sb=document.getElementById('sidebar');if(sb&&sb.classList.contains('open'))toggleSidebar();
  };
  window._refreshDash=function(){
    var dc=document.getElementById('dashboard-content');dc.innerHTML='<p style="color:var(--text2)">Loading...</p>';
    var hdr={'X-Session-Token':_tok};
    Promise.all([
      fetch('/api/dashboard',{headers:hdr}).then(function(r){return r.json()}),
      fetch('/api/usage/daily',{headers:hdr}).then(function(r){return r.json()})
    ]).then(function(arr){
      var d=arr[0],daily=(arr[1].report||[]);
      var u=d.usage||{};var kr=_lang==='ko';var mode=_dashMode;
      var totalCost=(u.total_cost||0).toFixed(4);
      var totalTokens=(u.total_input||0)+(u.total_output||0);
      var totalCalls=0;var bm=u.by_model||{};
      for(var k in bm)totalCalls+=bm[k].calls||0;
      var uptime=(u.elapsed_hours||0).toFixed(1);
      var sessions=d.sessions||[];
      var totalMsgs=0;sessions.forEach(function(s){totalMsgs+=s.messages||0});
      var h='';
      /* Summary cards */
      h+='<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:20px">';
      var cards=[
        ['💰',kr?'총 비용':'Total Cost','$'+totalCost],
        ['📡',kr?'API 호출':'API Calls',totalCalls],
        ['🔤',kr?'총 토큰':'Total Tokens',totalTokens.toLocaleString()],
        ['💬',kr?'세션':'Sessions',sessions.length],
        ['📝',kr?'메시지':'Messages',totalMsgs],
        ['⏱️',kr?'가동 시간':'Uptime',uptime+'h']
      ];
      cards.forEach(function(c){h+='<div style="background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:14px"><div style="font-size:11px;color:var(--text2);text-transform:uppercase">'+c[0]+' '+c[1]+'</div><div style="font-size:24px;font-weight:700;color:var(--accent);margin-top:4px">'+c[2]+'</div></div>'});
      h+='</div>';
      /* Activity by Time (CSS bar chart) */
      if(daily.length){
        var byDay={};daily.forEach(function(r){
          if(!byDay[r.date])byDay[r.date]={tokens:0,cost:0,calls:0};
          byDay[r.date].tokens+=(r.input_tokens||0)+(r.output_tokens||0);
          byDay[r.date].cost+=r.cost||0;
          byDay[r.date].calls+=r.calls||0;
        });
        var days=Object.keys(byDay).sort();
        var maxVal=0;days.forEach(function(d2){var v=mode==='tokens'?byDay[d2].tokens:byDay[d2].cost;if(v>maxVal)maxVal=v});
        var totalFiltered=0;days.forEach(function(d2){totalFiltered+=mode==='tokens'?byDay[d2].tokens:byDay[d2].cost});
        h+='<div style="background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:16px">';
        h+='<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px"><div><span style="font-weight:600">'+(kr?'시간별 활동':'Activity by Time')+'</span><br><span style="font-size:11px;color:var(--text2)">'+(kr?'일별 추이':'Daily trend')+'</span></div>';
        h+='<div style="font-size:20px;font-weight:700;color:var(--accent)">'+(mode==='tokens'?totalFiltered.toLocaleString()+' tokens':'$'+totalFiltered.toFixed(4))+'</div></div>';
        h+='<div style="display:flex;align-items:flex-end;gap:3px;height:120px;padding:0 4px">';
        days.forEach(function(d2){
          var v=mode==='tokens'?byDay[d2].tokens:byDay[d2].cost;
          var pct=maxVal?Math.max((v/maxVal)*100,2):2;
          var lbl=d2.slice(5);/* MM-DD */
          var tip=d2+': '+(mode==='tokens'?v.toLocaleString()+' tokens':'$'+v.toFixed(4))+' ('+byDay[d2].calls+' calls)';
          h+='<div style="flex:1;display:flex;flex-direction:column;align-items:center" title="'+tip+'"><div style="width:100%;background:var(--accent);border-radius:4px 4px 0 0;height:'+pct+'%;min-height:2px;opacity:0.8"></div><div style="font-size:9px;color:var(--text2);margin-top:4px;white-space:nowrap">'+lbl+'</div></div>';
        });
        h+='</div></div>';
      }
      /* Daily Usage table */
      if(daily.length){
        h+='<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">';
        /* Left: Daily breakdown */
        h+='<div style="background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:16px">';
        h+='<h3 style="font-size:13px;margin-bottom:12px">'+(kr?'일별 사용량':'Daily Usage')+'</h3>';
        var byDayArr=Object.keys(byDay).sort().reverse();
        h+='<table style="width:100%;font-size:12px;border-collapse:collapse">';
        h+='<tr style="color:var(--text2)"><th style="text-align:left;padding:6px">'+(kr?'날짜':'Date')+'</th><th style="text-align:right;padding:6px">'+(kr?'토큰':'Tokens')+'</th><th style="text-align:right;padding:6px">'+(kr?'호출':'Calls')+'</th><th style="text-align:right;padding:6px">'+(kr?'비용':'Cost')+'</th></tr>';
        byDayArr.forEach(function(d2){var v=byDay[d2];h+='<tr style="border-top:1px solid var(--border)"><td style="padding:6px">'+d2+'</td><td style="text-align:right;padding:6px">'+v.tokens.toLocaleString()+'</td><td style="text-align:right;padding:6px">'+v.calls+'</td><td style="text-align:right;padding:6px;color:var(--accent)">$'+v.cost.toFixed(4)+'</td></tr>'});
        h+='</table></div>';
        /* Right: Model breakdown */
        h+='<div style="background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:16px">';
        h+='<h3 style="font-size:13px;margin-bottom:12px">🤖 '+(kr?'모델별':'By Model')+'</h3>';
        if(Object.keys(bm).length){
          h+='<table style="width:100%;font-size:12px;border-collapse:collapse">';
          h+='<tr style="color:var(--text2)"><th style="text-align:left;padding:6px">'+(kr?'모델':'Model')+'</th><th style="text-align:right;padding:6px">'+(kr?'호출':'Calls')+'</th><th style="text-align:right;padding:6px">'+(kr?'비용':'Cost')+'</th></tr>';
          for(var m in bm){var v2=bm[m];h+='<tr style="border-top:1px solid var(--border)"><td style="padding:6px;font-weight:500">'+m+'</td><td style="text-align:right;padding:6px">'+v2.calls+'</td><td style="text-align:right;padding:6px;color:var(--accent)">$'+v2.cost.toFixed(4)+'</td></tr>'}
          h+='</table>';
        }else{h+='<div style="color:var(--text2);font-size:12px">'+(kr?'데이터 없음':'No data')+'</div>'}
        h+='</div></div>';
      }else{
        h+='<div style="background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:24px;text-align:center;color:var(--text2);margin-bottom:16px">'+(kr?'아직 사용 데이터가 없습니다':'No usage data yet')+'</div>';
      }
      dc.innerHTML=h;
    }).catch(function(e){dc.innerHTML='<p style="color:#f87171">Failed to load: '+e.message+'</p>'});
  };
  window.changePw=function(){
    var o=document.getElementById('pw-old').value,n=document.getElementById('pw-new').value,c=document.getElementById('pw-confirm').value;
    var re=document.getElementById('pw-result');
    if(!o||!n){re.innerHTML='<span style="color:#f87171">'+t('pw-enter-current')+'</span>';return}
    if(n!==c){re.innerHTML='<span style="color:#f87171">'+t('pw-mismatch')+'</span>';return}
    if(n.length<4){re.innerHTML='<span style="color:#f87171">'+t('pw-min4')+'</span>';return}
    fetch('/api/vault',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'change_password',old_password:o,new_password:n})}).then(function(r){return r.json()}).then(function(d){
      if(d.ok){re.innerHTML='<span style="color:#4ade80">'+t('pw-changed')+'</span>';document.getElementById('pw-old').value='';document.getElementById('pw-new').value='';document.getElementById('pw-confirm').value=''}
      else{re.innerHTML='<span style="color:#f87171">'+t('pw-fail')+' '+(d.error||'')+'</span>'}
    }).catch(function(e){re.innerHTML='<span style="color:#f87171">❌ '+e.message+'</span>'})};
  window.removePw=function(){
    var o=document.getElementById('pw-old').value;var re=document.getElementById('pw-result');
    if(!o){re.innerHTML='<span style="color:#f87171">'+t('pw-enter-current')+'</span>';return}
    fetch('/api/vault',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'change_password',old_password:o,new_password:''})}).then(function(r){return r.json()}).then(function(d){
      if(d.ok){re.innerHTML='<span style="color:#4ade80">✅ '+t('pw-remove')+'</span>';document.getElementById('pw-old').value='';document.getElementById('pw-section-change').style.display='none';document.getElementById('pw-section-set').style.display='block'}
      else{re.innerHTML='<span style="color:#f87171">'+t('pw-fail')+' '+(d.error||'')+'</span>'}}).catch(function(e){re.innerHTML='<span style="color:#f87171">❌ '+e.message+'</span>'})};
  window.setPw=function(){
    var n=document.getElementById('pw-set-new').value,c=document.getElementById('pw-set-confirm').value;var re=document.getElementById('pw-result');
    if(!n){re.innerHTML='<span style="color:#f87171">'+t('pw-enter-current')+'</span>';return}
    if(n.length<4){re.innerHTML='<span style="color:#f87171">'+t('pw-min4')+'</span>';return}
    if(n!==c){re.innerHTML='<span style="color:#f87171">'+t('pw-mismatch')+'</span>';return}
    fetch('/api/vault',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'change_password',old_password:'',new_password:n})}).then(function(r){return r.json()}).then(function(d){
      if(d.ok){re.innerHTML='<span style="color:#4ade80">'+t('pw-changed')+'</span>';document.getElementById('pw-set-new').value='';document.getElementById('pw-set-confirm').value='';document.getElementById('pw-section-set').style.display='none';document.getElementById('pw-section-change').style.display='block'}
      else{re.innerHTML='<span style="color:#f87171">'+t('pw-fail')+' '+(d.error||'')+'</span>'}}).catch(function(e){re.innerHTML='<span style="color:#f87171">❌ '+e.message+'</span>'})};
  window.checkUpdate=function(){
    var re=document.getElementById('update-result');
    re.innerHTML='<span style="color:var(--text2)">⏳ Checking PyPI...</span>';
    fetch('/api/check-update').then(function(r){return r.json()}).then(function(d){
      document.getElementById('cur-ver').textContent=d.current;
      if(d.latest&&d.latest!==d.current){
        if(d.exe){
          re.innerHTML='<span style="color:#fbbf24">🆕 New version v'+d.latest+' available!</span> <a href="'+d.download_url+'" target="_blank" style="color:#60a5fa">⬇️ Download</a>';
        }else{
          re.innerHTML='<span style="color:#fbbf24">🆕 New version v'+d.latest+' available!</span>';
          document.getElementById('do-update-btn').style.display='inline-block';
        }
      }else{re.innerHTML='<span style="color:#4ade80">✅ You are up to date (v'+d.current+')</span>';
        document.getElementById('do-update-btn').style.display='none'}
    }).catch(function(e){re.innerHTML='<span style="color:#f87171">❌ Check failed: '+e.message+'</span>'})};
  window.doUpdate=function(){
    /* Works from both dashboard (with update-result/do-update-btn) and banner */
    var re=document.getElementById('update-result');
    var btn=document.getElementById('do-update-btn');
    var bannerBtn=document.querySelector('#update-banner button');
    /* Update UI for whichever context we're in */
    if(btn){btn.disabled=true;btn.textContent='⏳ Installing...';}
    if(bannerBtn){bannerBtn.disabled=true;bannerBtn.textContent='⏳ Installing...';}
    if(re)re.innerHTML='<span style="color:var(--text2)">Running pip install --upgrade salmalm... (up to 30s)</span>';
    fetch('/api/do-update',{method:'POST'}).then(function(r){return r.json()}).then(function(d){
      if(d.ok){
        var msg='✅ v'+d.version+' installed! Restart to apply.';
        if(re){re.innerHTML='<span style="color:#4ade80">'+msg+'</span>';
          var rb=document.createElement('button');rb.className='btn';rb.style.marginTop='8px';rb.textContent='🔄 Restart Now';
          rb.onclick=function(){fetch('/api/restart',{method:'POST'});window._waitForServerThenReload&&_waitForServerThenReload()||setTimeout(function(){location.reload()},5000)};re.appendChild(rb);
        }
        if(bannerBtn){bannerBtn.textContent='🔄 Restart';bannerBtn.disabled=false;
          bannerBtn.onclick=function(){fetch('/api/restart',{method:'POST'});bannerBtn.textContent='Restarting...';bannerBtn.disabled=true;window._waitForServerThenReload?_waitForServerThenReload():setTimeout(function(){location.reload()},5000)};
        }
      }else{
        var errMsg='❌ '+(d.error||'Update failed');
        if(re)re.innerHTML='<span style="color:#f87171">'+errMsg+'</span>';
        if(bannerBtn){bannerBtn.textContent='❌ Failed';setTimeout(function(){bannerBtn.textContent='Update Now';bannerBtn.disabled=false},3000);}
      }
      if(btn){btn.disabled=false;btn.textContent='⬆️ Update';}
    }).catch(function(e){
      var errMsg='❌ '+e.message;
      if(re)re.innerHTML='<span style="color:#f87171">'+errMsg+'</span>';
      if(btn){btn.disabled=false;btn.textContent='⬆️ Update';}
      if(bannerBtn){bannerBtn.textContent='❌ Error';setTimeout(function(){bannerBtn.textContent='Update Now';bannerBtn.disabled=false},3000);}
    });};
  window.saveKey=function(vaultKey,inputId){
    var v=document.getElementById(inputId).value.trim();
    if(!v){addMsg('assistant','Please enter a key');return}
    fetch('/api/vault',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({action:'set',key:vaultKey,value:v})})
    .then(function(r){return r.json()}).then(function(d){
      var re=document.getElementById('key-test-result');
      re.innerHTML='<span style="color:#4ade80">✅ '+vaultKey+' Saved</span>';
      document.getElementById(inputId).value='';
      // Update global configured keys + re-apply vault UI (saved badge + delete btn)
      if(!window._configuredKeys)window._configuredKeys=[];
      if(window._configuredKeys.indexOf(vaultKey)<0)window._configuredKeys.push(vaultKey);
      if(typeof window._applyVaultKeys==='function')window._applyVaultKeys(window._configuredKeys);
      else if(typeof _renderToolsList==='function')_renderToolsList(document.getElementById('tools-search')?document.getElementById('tools-search').value:'');
      // Auto-optimize routing when an LLM provider key is saved
      var llmKeys=['anthropic_api_key','openai_api_key','xai_api_key','google_api_key'];
      if(llmKeys.indexOf(vaultKey)!==-1){
        fetch('/api/routing/optimize',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},body:'{}'})
        .then(function(r){return r.json()}).then(function(od){
          if(od.ok){
            var kr=document.documentElement.lang==='kr';
            re.innerHTML+='<br><span style="color:#22d3ee">⚡ '+(kr?'라우팅 자동 최적화됨':'Routing auto-optimized')+'</span>';
          }
        }).catch(function(){});
      }
      window.showSettings()})};
  window.testKey=function(provider){
    var re=document.getElementById('key-test-result');
    re.innerHTML='<span style="color:var(--text2)">⏳ '+provider+' Testing...</span>';
    fetch('/api/test-key',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({provider:provider})})
    .then(function(r){return r.json()}).then(function(d){
      re.innerHTML=d.ok?'<span style="color:#4ade80">'+d.result+'</span>':'<span style="color:#f87171">'+d.result+'</span>'})
    .catch(function(e){re.innerHTML='<span style="color:#f87171">❌ Error: '+e.message+'</span>'})
  };
  /* Telegram/Discord connection status */
  window._checkTgStatus=function(){
    var el=document.getElementById('tg-conn-status');if(!el)return;
    fetch('/api/channels').then(function(r){return r.json()}).then(function(d){
      if(d.telegram){el.innerHTML='🟢 <span data-i18n="tg-connected">Connected</span>';el.style.color='#4ade80'}
      else{el.innerHTML='⚪ <span data-i18n="tg-disconnected">Not connected</span>';el.style.color='var(--text2)'}
    }).catch(function(){})};
  window._checkDcStatus=function(){
    var el=document.getElementById('dc-conn-status');if(!el)return;
    fetch('/api/channels').then(function(r){return r.json()}).then(function(d){
      if(d.discord){el.innerHTML='🟢 <span data-i18n="dc-connected">Connected</span>';el.style.color='#4ade80'}
      else{el.innerHTML='⚪ <span data-i18n="dc-disconnected">Not connected</span>';el.style.color='var(--text2)'}
    }).catch(function(){})};
  window.googleConnect=function(){
    var re=document.getElementById('google-result');
    re.innerHTML='<span style="color:var(--text2)">⏳ Checking credentials...</span>';
    fetch('/api/vault',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({action:'get',key:'google_client_id'})})
    .then(function(r){return r.json()}).then(function(d){
      if(!d.value){re.innerHTML='<span style="color:#f87171">'+t('google-no-client-id')+'</span>';return}
      re.innerHTML='<span style="color:#4ade80">'+t('google-redirecting')+'</span>';
      window.open('/api/google/auth','_blank','width=500,height=600')})
    .catch(function(e){re.innerHTML='<span style="color:#f87171">❌ '+e.message+'</span>'})
  };
  window.googleDisconnect=function(){
    var re=document.getElementById('google-result');
    if(!confirm(t('google-confirm-disconnect')))return;
    Promise.all([
      fetch('/api/vault',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'delete',key:'google_refresh_token'})}),
      fetch('/api/vault',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'delete',key:'google_access_token'})})
    ]).then(function(){
      re.innerHTML='<span style="color:#4ade80">'+t('google-disconnected')+'</span>';
      document.getElementById('google-status').innerHTML='<span style="color:var(--text2)">'+t('google-not-connected')+'</span>';
    }).catch(function(e){re.innerHTML='<span style="color:#f87171">❌ '+e.message+'</span>'})
  };
  window.checkGoogleStatus=function(){
    var st=document.getElementById('google-status');
    if(!st)return;
    fetch('/api/vault',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({action:'get',key:'google_refresh_token'})})
    .then(function(r){return r.json()}).then(function(d){
      if(d.value){st.innerHTML='<span style="color:#4ade80">'+t('google-connected')+'</span>'}
      else{st.innerHTML='<span style="color:var(--text2)">'+t('google-not-connected')+'</span>'}
    }).catch(function(){st.innerHTML=''})
  };
  window.setModel=function(m){
    _isAutoRouting=(m==='auto');
    modelBadge.textContent=m==='auto'?'auto routing':m.split('/').pop();
    /* Immediately update UI (optimistic) */
    var cn=document.getElementById('mr-current-name');
    if(cn)cn.textContent=m==='auto'?'🔄 Auto Routing':m;
    var sel=document.getElementById('s-model');
    if(sel)sel.value=m;
    var hint=document.getElementById('mr-routing-hint');
    if(hint){hint.style.display=m==='auto'?'none':'block'}
    /* Then persist to server, reload after server confirms */
    fetch('/api/model/switch',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},body:JSON.stringify({model:m,session:_currentSession})})
    .then(function(r){return r.json()}).then(function(d){
      /* Re-update from server response to ensure consistency */
      var eff=d.current_model||m;
      if(cn)cn.textContent=eff==='auto'?'🔄 Auto Routing':eff;
      _isAutoRouting=(eff==='auto');
      modelBadge.textContent=eff==='auto'?'auto routing':eff.split('/').pop();
      if(sel)sel.value=eff;
      if(hint){hint.style.display=eff==='auto'?'none':'block'}
      /* Reload model cards to sync highlight */
      if(typeof window._loadModelRouter==='function')window._loadModelRouter();
    });
  };
