import { chat, input, btn, costEl, modelBadge, settingsEl, filePrev, fileIconEl, fileNameEl, fileSizeEl, imgPrev, inputArea, _tok, pendingFile, pendingFiles, _currentSession, _sessionCache, _isAutoRouting, set_tok, set_pendingFile, set_pendingFiles, set_currentSession, set_sessionCache, set_isAutoRouting } from './globals';

  /* --- Features Guide --- */
  var FEATURE_CATEGORIES=window.FEATURE_CATEGORIES||[];

  function loadFeatures(){renderFeatures('')}
  function renderFeatures(q){
    var el=document.getElementById('features-list');
    var empty=document.getElementById('features-empty');
    var kr=_lang==='ko';
    var ql=q.toLowerCase();
    var html='';var total=0;
    FEATURE_CATEGORIES.forEach(function(cat){
      var items=cat.features.filter(function(f){
        if(!ql)return true;
        return (f.name+(f.name_kr||'')+(f.desc||'')+(f.desc_kr||'')+(f.command||'')).toLowerCase().indexOf(ql)>=0;
      });
      if(!items.length)return;
      total+=items.length;
      var open=ql?'open':'';
      html+='<div class="feat-cat '+open+'"><div class="feat-cat-header" data-action="toggleFeatCat"><span class="arrow">▶</span><span>'+cat.icon+' '+(kr&&cat.title_kr?cat.title_kr:cat.title)+'</span><span style="margin-left:auto;font-size:12px;color:var(--text2)">'+items.length+'</span></div><div class="feat-cat-body">';
      items.forEach(function(f){
        var nm=kr&&f.name_kr?f.name_kr:f.name;
        var ds=kr&&f.desc_kr?f.desc_kr:(f.desc||'');
        html+='<div class="feat-card"><div class="feat-name">'+nm+'</div><div class="feat-desc">'+ds+'</div>';
        if(f.command)html+='<button class="feat-cmd" data-action="fillCommand" data-cmd="'+f.command.replace(/"/g,'&quot;')+'">'+f.command+'</button>';
        html+='</div>';
      });
      html+='</div></div>';
    });
    el.innerHTML=html;
    empty.style.display=total?'none':'block';
  }
  document.getElementById('features-search').addEventListener('input',function(){renderFeatures(this.value)});

