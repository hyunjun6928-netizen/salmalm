  /* --- Command Palette (Ctrl+Shift+P) --- */
  var _cmdPalette=document.createElement('div');_cmdPalette.id='cmd-palette';
  _cmdPalette.innerHTML='<input id="cmd-input" type="text" placeholder="'+t('cmd-placeholder')+'" autocomplete="off"><div id="cmd-results"></div>';
  document.body.appendChild(_cmdPalette);
  var _cmdOv=document.createElement('div');_cmdOv.id='cmd-overlay';document.body.appendChild(_cmdOv);
  var _cmdCommands=[
    {icon:'🗨',label:'cmd-new-chat',action:function(){window.newSession()},shortcut:'Ctrl+N'},
    {icon:'📥',label:'cmd-export',action:function(){window.exportChat('md')}},
    {icon:'⚙️',label:'cmd-settings',action:function(){window.showSettings()}},
    {icon:'🔍',label:'cmd-search',action:function(){_openSearchModal()},shortcut:'Ctrl+K'},
    {icon:'🎨',label:'cmd-theme',action:function(){window.toggleTheme()}},
    {icon:'☰',label:'cmd-sidebar',action:function(){window.toggleSidebar()}},
    {icon:'📈',label:'cmd-dashboard',action:function(){window.showDashboard()}},
    {icon:'🤖',label:'/model',action:function(){input.value='/model ';input.focus()},raw:true},
    {icon:'🧠',label:'/thinking',action:function(){window.toggleThinking()},raw:true},
    {icon:'📦',label:'/compact',action:function(){input.value='/compact';doSend()},raw:true},
    {icon:'⏪',label:'/rollback',action:function(){input.value='/rollback';doSend()},raw:true},
    {icon:'🌿',label:'/branch',action:function(){input.value='/branch';doSend()},raw:true},
    {icon:'📜',label:'/soul',action:function(){input.value='/soul';doSend()},raw:true},
    {icon:'🔊',label:'/tts',action:function(){input.value='/tts ';input.focus()},raw:true},
    {icon:'🎤',label:'/voice',action:function(){window.toggleMic()},raw:true},
    {icon:'❓',label:'/help',action:function(){input.value='/help';doSend()},raw:true},
  ];
  var _cmdSel=0;
  function _fuzzyMatch(query,text){query=query.toLowerCase();text=text.toLowerCase();if(!query)return true;var qi=0;for(var ti=0;ti<text.length&&qi<query.length;ti++){if(text[ti]===query[qi])qi++}return qi===query.length}
  function _renderCmdResults(q){
    var el=document.getElementById('cmd-results');
    var filtered=_cmdCommands.filter(function(c){var label=c.raw?c.label:t(c.label);return _fuzzyMatch(q,label)||_fuzzyMatch(q,c.icon+' '+label)});
    _cmdSel=0;
    el.innerHTML=filtered.map(function(c,i){
      var label=c.raw?c.label:t(c.label);
      var sc=c.shortcut?'<span class="cmd-shortcut">'+c.shortcut+'</span>':'';
      return '<div class="cmd-item'+(i===0?' selected':'')+'" data-cmd-idx="'+i+'"><span class="cmd-icon">'+c.icon+'</span><span class="cmd-label">'+label+'</span>'+sc+'</div>';
    }).join('');
    el._filtered=filtered;
  }
  function _openCmdPalette(){_cmdPalette.classList.add('open');_cmdOv.classList.add('open');var ci=document.getElementById('cmd-input');ci.value='';ci.focus();_renderCmdResults('');ci.oninput=function(){_renderCmdResults(ci.value)}}
  function _closeCmdPalette(){_cmdPalette.classList.remove('open');_cmdOv.classList.remove('open')}
  _cmdOv.addEventListener('click',_closeCmdPalette);
  document.addEventListener('keydown',function(e){
    if(!_cmdPalette||!_cmdPalette.classList.contains('open'))return;
    var el=document.getElementById('cmd-results');var filtered=el._filtered||[];
    var items=el.querySelectorAll('.cmd-item');
    if(e.key==='ArrowDown'){e.preventDefault();_cmdSel=Math.min(_cmdSel+1,items.length-1);items.forEach(function(it,i){it.classList.toggle('selected',i===_cmdSel)})}
    else if(e.key==='ArrowUp'){e.preventDefault();_cmdSel=Math.max(_cmdSel-1,0);items.forEach(function(it,i){it.classList.toggle('selected',i===_cmdSel)})}
    else if(e.key==='Enter'){e.preventDefault();if(filtered[_cmdSel]){_closeCmdPalette();filtered[_cmdSel].action()}}
  });
  document.getElementById('cmd-results').addEventListener('click',function(e){
    var item=e.target.closest('.cmd-item');if(!item)return;
    var idx=parseInt(item.getAttribute('data-cmd-idx'));
    var el=document.getElementById('cmd-results');var filtered=el._filtered||[];
    if(filtered[idx]){_closeCmdPalette();filtered[idx].action();}
  });
