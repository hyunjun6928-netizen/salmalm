  /* --- Model Router Tab --- */
  /* Model pricing data (per 1M tokens: input/output) */
  var _MODEL_PRICES={
    'claude-opus-4-6':{i:5,o:25},'claude-sonnet-4-6':{i:3,o:15},'claude-haiku-4-5-20251001':{i:1,o:5},
    'gpt-5.2-codex':{i:2,o:8},'gpt-5.1-codex':{i:1.5,o:6},'gpt-4.1':{i:2,o:8},'gpt-4.1-mini':{i:0.4,o:1.6},'gpt-4.1-nano':{i:0.1,o:0.4},
    'o3':{i:10,o:40},'o3-mini':{i:1.1,o:4.4},'o4-mini':{i:1.1,o:4.4},
    'grok-4-0709':{i:3,o:15},'grok-3':{i:3,o:15},'grok-3-mini':{i:0.3,o:0.5},
    'gemini-3-pro-preview':{i:1.25,o:10},'gemini-3-flash-preview':{i:0.15,o:0.6},'gemini-2.5-pro':{i:1.25,o:10},'gemini-2.5-flash':{i:0.15,o:0.6}
  };
  function _getPrice(modelId){
    var short=modelId.split('/').pop();
    return _MODEL_PRICES[short]||null;
  }
  window._loadModelRouter=function(){
    var hdr={'X-Session-Token':_tok,'X-Session-Id':_currentSession};
    fetch('/api/llm-router/providers',{headers:hdr}).then(function(r){return r.json()}).then(function(d){
      var cur=d.current_model||'auto';
      document.getElementById('mr-current-name').textContent=cur==='auto'?'🔄 Auto Routing':cur;
      var hint=document.getElementById('mr-routing-hint');if(hint){hint.style.display=cur==='auto'?'none':'block'}
      /* Update s-model dropdown */
      var sel=document.getElementById('s-model');
      if(sel){
        sel.innerHTML='<option value="auto">🔄 Auto Routing</option>';
        d.providers.forEach(function(p){
          p.models.forEach(function(m){
            var opt=document.createElement('option');opt.value=m.full;opt.textContent=m.name;
            if(cur===m.full)opt.selected=true;
            sel.appendChild(opt);
          });
        });
        if(cur==='auto')sel.value='auto';
      }
      /* Provider grid */
      var gridEl=document.getElementById('mr-provider-grid');
      var kr=_lang==='ko';
      var provIcons={anthropic:'🟣',openai:'🟢',xai:'🔵',google:'🟡',openrouter:'🔷',ollama:'🦙'};
      var h='';
      d.providers.forEach(function(p){
        var icon=provIcons[p.name]||'📦';
        var status=p.available?'<span style="color:var(--green,#4ade80)">●</span>':'<span style="color:var(--red,#f87171)">●</span>';
        h+='<div style="border:1px solid var(--border);border-radius:12px;padding:14px;background:var(--bg)">';
        h+='<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">';
        h+='<span style="font-size:18px">'+icon+'</span>';
        var displayName=p.name==='ollama'?(kr?'로컬 LLM':'Local LLM'):p.name.charAt(0).toUpperCase()+p.name.slice(1);
        h+='<span style="font-weight:600;font-size:14px">'+displayName+'</span>';
        h+=status;
        var statusText=p.available?(kr?'연결됨':'Connected'):((p.name==='ollama')?(kr?'오프라인':'Offline'):(kr?'키 없음':'No key'));
        h+='<span style="font-size:11px;color:var(--text2);margin-left:auto">'+statusText+'</span>';
        h+='</div>';
        p.models.forEach(function(m){
          var isActive=cur&&(cur===m.full||cur===m.name);
          var price=_getPrice(m.full);
          var priceStr=price?'$'+price.i+' / $'+price.o:'';
          h+='<div data-action="switchModel" data-model="'+m.full+'" style="display:flex;align-items:center;gap:8px;padding:8px 10px;border-radius:8px;cursor:pointer;margin-bottom:4px;border:1px solid '+(isActive?'var(--accent)':'transparent')+';background:'+(isActive?'var(--accent-dim)':'transparent')+';transition:all 0.12s"'+(p.available?'':' class="disabled-model"')+'>';
          h+='<div style="flex:1"><div style="font-size:13px;font-weight:500;color:'+(isActive?'var(--accent2)':'var(--text)')+'">'+m.name+(isActive?' ●':'')+'</div>';
          if(priceStr)h+='<div style="font-size:10px;color:var(--text2)">'+priceStr+' '+(kr?'/ 1M 토큰':'/ 1M tok')+'</div>';
          h+='</div></div>';
        });
        if(!p.models||!p.models.length){
          h+='<div style="font-size:12px;color:var(--text2);padding:6px 10px">'+(kr?'모델이 없습니다':'No models available')+'</div>';
        }
        h+='</div>';
      });
      gridEl.innerHTML=h;
    }).catch(function(e){
      document.getElementById('mr-provider-grid').innerHTML='<div style="color:var(--red)">Failed to load: '+e+'</div>';
    });
  };
