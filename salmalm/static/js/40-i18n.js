  /* --- i18n --- */
  var _i18n=window._i18n||{en:{},ko:{}};
  var _lang=localStorage.getItem('salmalm-lang')||(navigator.language&&navigator.language.startsWith('ko')?'ko':'en');
  function t(k){return (_i18n[_lang]||_i18n.en)[k]||(_i18n.en[k]||k)}
  /* Now that t() is defined, restore deferred chat history */
  if(window._pendingRestore){try{window._pendingRestore()}catch(e){console.warn('Chat restore failed:',e);localStorage.removeItem('salm_chat')}delete window._pendingRestore;}
  /* Check for interrupted SSE requests after chat restore */
  if(window._checkPendingRecovery){try{window._checkPendingRecovery()}catch(e){console.warn('Recovery check failed:',e)}}
  /* File input change handler */
  var _fileInput=document.getElementById('file-input-hidden');
  if(_fileInput)_fileInput.addEventListener('change',function(){if(this.files.length>1){window.setFiles(Array.from(this.files))}else if(this.files[0]){window.setFile(this.files[0])}this.value=''});
  /* Tool i18n map: name -> {icon, en, kr, cmd} */
  var _toolI18n={
    apply_patch:{icon:'🩹',en:'Apply Patch',kr:'패치 적용',cmd:'/patch'},
    brave_context:{icon:'🔍',en:'Brave Context',kr:'Brave 컨텍스트',cmd:'Search context with Brave',req:'brave'},
    brave_images:{icon:'🖼️',en:'Brave Images',kr:'Brave 이미지 검색',cmd:'Search images',req:'brave'},
    brave_news:{icon:'📰',en:'Brave News',kr:'Brave 뉴스 검색',cmd:'Search news',req:'brave'},
    brave_search:{icon:'🔎',en:'Brave Search',kr:'Brave 웹 검색',cmd:'Search the web for',req:'brave'},
    briefing:{icon:'📋',en:'Briefing',kr:'브리핑',cmd:'/briefing'},
    browser:{icon:'🌐',en:'Browser',kr:'브라우저 자동화',cmd:'Open browser',req:'browser'},
    calendar_add:{icon:'📅',en:'Add Calendar',kr:'일정 추가',cmd:'Add calendar event',req:'google'},
    calendar_delete:{icon:'🗑️',en:'Delete Calendar',kr:'일정 삭제',cmd:'Delete calendar event',req:'google'},
    calendar_list:{icon:'📆',en:'List Calendar',kr:'일정 목록',cmd:'Show calendar',req:'google'},
    clipboard:{icon:'📋',en:'Clipboard',kr:'클립보드',cmd:'Copy to clipboard'},
    cron_manage:{icon:'⏰',en:'Cron Manager',kr:'크론 관리',cmd:'/cron list'},
    diff_files:{icon:'📊',en:'Diff Files',kr:'파일 비교',cmd:'Compare files'},
    edit_file:{icon:'✏️',en:'Edit File',kr:'파일 편집',cmd:'Edit file'},
    email_inbox:{icon:'📬',en:'Email Inbox',kr:'이메일 수신함',cmd:'Check email inbox',req:'google'},
    email_read:{icon:'📧',en:'Read Email',kr:'이메일 읽기',cmd:'Read email',req:'google'},
    email_search:{icon:'🔍',en:'Search Email',kr:'이메일 검색',cmd:'Search email',req:'google'},
    email_send:{icon:'📤',en:'Send Email',kr:'이메일 발송',cmd:'Send email',req:'google'},
    exec:{icon:'💻',en:'Shell Exec',kr:'셸 실행',cmd:'Run command:'},
    exec_session:{icon:'🖥️',en:'Exec Session',kr:'세션 실행',cmd:'Start exec session'},
    expense:{icon:'💳',en:'Expense',kr:'지출 기록',cmd:'Track expense'},
    file_index:{icon:'📁',en:'File Index',kr:'파일 인덱스',cmd:'Index files'},
    gmail:{icon:'📧',en:'Gmail',kr:'Gmail',cmd:'Check Gmail',req:'google'},
    google_calendar:{icon:'📅',en:'Google Calendar',kr:'구글 캘린더',cmd:'Show Google Calendar',req:'google'},
    hash_text:{icon:'#️⃣',en:'Hash Text',kr:'해시 생성',cmd:'Hash text'},
    health_check:{icon:'🏥',en:'Health Check',kr:'상태 점검',cmd:'/health'},
    http_request:{icon:'🌐',en:'HTTP Request',kr:'HTTP 요청',cmd:'Make HTTP request'},
    image_analyze:{icon:'🔬',en:'Image Analyze',kr:'이미지 분석',cmd:'Analyze image',req:'openai'},
    image_generate:{icon:'🎨',en:'Image Generate',kr:'이미지 생성',cmd:'Generate image:',req:'openai'},
    json_query:{icon:'📦',en:'JSON Query',kr:'JSON 쿼리',cmd:'Query JSON'},
    mcp_manage:{icon:'🔌',en:'MCP Manager',kr:'MCP 관리',cmd:'/mcp list'},
    memory_read:{icon:'🧠',en:'Memory Read',kr:'기억 읽기',cmd:'/memory'},
    memory_search:{icon:'🔍',en:'Memory Search',kr:'기억 검색',cmd:'Search memory for'},
    memory_write:{icon:'📝',en:'Memory Write',kr:'기억 저장',cmd:'Remember this:'},
    node_manage:{icon:'🖧',en:'Node Manager',kr:'노드 관리',cmd:'/node list'},
    note:{icon:'📒',en:'Note',kr:'메모',cmd:'Take note:'},
    notification:{icon:'🔔',en:'Notification',kr:'알림',cmd:'Send notification'},
    plugin_manage:{icon:'🧩',en:'Plugin Manager',kr:'플러그인 관리',cmd:'/plugin list'},
    pomodoro:{icon:'🍅',en:'Pomodoro',kr:'뽀모도로 타이머',cmd:'/pomodoro start'},
    python_eval:{icon:'🐍',en:'Python Exec',kr:'파이썬 실행',cmd:'Calculate in Python:'},
    qr_code:{icon:'📱',en:'QR Code',kr:'QR 코드 생성',cmd:'Generate QR code for'},
    rag_search:{icon:'📚',en:'RAG Search',kr:'RAG 검색',cmd:'Search documents for'},
    read_file:{icon:'📖',en:'Read File',kr:'파일 읽기',cmd:'Read file'},
    regex_test:{icon:'🔤',en:'Regex Test',kr:'정규식 테스트',cmd:'Test regex'},
    reminder:{icon:'⏰',en:'Reminder',kr:'리마인더',cmd:'/remind'},
    routine:{icon:'🔁',en:'Routine',kr:'루틴 관리',cmd:'/routine list'},
    rss_reader:{icon:'📡',en:'RSS Reader',kr:'RSS 리더',cmd:'Read RSS feed'},
    save_link:{icon:'🔗',en:'Save Link',kr:'링크 저장',cmd:'Save link:'},
    screenshot:{icon:'📸',en:'Screenshot',kr:'스크린샷',cmd:'Take screenshot',req:'browser'},
    skill_manage:{icon:'🎓',en:'Skill Manager',kr:'스킬 관리',cmd:'/skill list'},
    stt:{icon:'🎙️',en:'Speech to Text',kr:'음성→텍스트',cmd:'Transcribe audio',req:'openai'},
    sub_agent:{icon:'🤖',en:'Sub Agent',kr:'서브 에이전트',cmd:'/agent list'},
    system_monitor:{icon:'🖥️',en:'System Monitor',kr:'시스템 모니터',cmd:'Check system status'},
    translate:{icon:'🌍',en:'Translate',kr:'번역',cmd:'Translate to Korean:'},
    tts:{icon:'🔊',en:'TTS',kr:'텍스트→음성',cmd:'Convert to speech:',req:'openai'},
    tts_generate:{icon:'🗣️',en:'TTS Generate',kr:'음성 생성',cmd:'Generate speech:',req:'openai'},
    usage_report:{icon:'📊',en:'Usage Report',kr:'사용량 리포트',cmd:'/usage'},
    weather:{icon:'🌤️',en:'Weather',kr:'날씨',cmd:'Check weather in'},
    web_fetch:{icon:'📥',en:'Web Fetch',kr:'웹 페이지 가져오기',cmd:'Fetch URL:'},
    web_search:{icon:'🔎',en:'Web Search',kr:'웹 검색',cmd:'Search the web for'},
    workflow:{icon:'⚙️',en:'Workflow',kr:'워크플로우',cmd:'/workflow list'},
    write_file:{icon:'💾',en:'Write File',kr:'파일 쓰기',cmd:'Write file'},
    ui_control:{icon:'🎛️',en:'UI Control',kr:'UI 제어',cmd:'Change theme to dark'}
  };
  var _allTools=[];
  window._configuredKeys=window._configuredKeys||[];
  /* Load vault keys first, then tool list — so req badges are accurate on first render */
  function _loadToolList(){
    fetch('/api/tools/list',{headers:{'X-Session-Token':_tok}}).then(function(r){return r.json()}).then(function(d){
      _allTools=(d.tools||[]).map(function(t){var m=_toolI18n[t.name];return{name:t.name,icon:m?m.icon:'🔧',en:m?m.en:t.name,kr:m?m.kr:t.name,cmd:m?m.cmd:'',req:m?m.req||'':''}});
      var th=document.getElementById('tools-header');
      if(th)th.textContent='🛠️ '+(_lang==='ko'?'도구':'Tools')+' ('+_allTools.length+') ▾';
      _renderToolsList('');
    }).catch(function(){});
  }
  fetch('/api/vault',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'keys'})})
    .then(function(r){return r.json()}).then(function(d){window._configuredKeys=d.keys||[];_loadToolList();})
    .catch(function(){_loadToolList();});
  /* req → vault key mapping (for configured-key check) */
  var _reqKeyMap={brave:'brave_api_key',openai:'openai_api_key',google:'google_client_id'};
  function _isReqMet(req){
    if(!req)return true;
    if(req==='browser')return false; // playwright — always show badge
    var needed=_reqKeyMap[req];
    if(!needed)return false;
    var ck=window._configuredKeys||[];
    return ck.indexOf(needed)>=0;
  }
  function _renderToolsList(q){
    var c=document.getElementById('tools-items');if(!c)return;
    var ql=q.toLowerCase();
    var filtered=ql?_allTools.filter(function(t){return t.name.toLowerCase().indexOf(ql)>=0||t.en.toLowerCase().indexOf(ql)>=0||t.kr.indexOf(ql)>=0}):_allTools;
    c.innerHTML=filtered.map(function(t){
      var label=_lang==='ko'?t.kr:t.en;
      var needsSetup=t.req&&!_isReqMet(t.req);
      var reqAttr=needsSetup?' data-tool-req="'+t.req+'"':'';
      var reqLabels={google:'Google',brave:'Brave',openai:'OpenAI',browser:'Browser'};
      var reqBadge=needsSetup?' <span style="font-size:9px;color:#f59e0b;margin-left:auto;background:#fef3c7;padding:1px 6px;border-radius:8px">🔗 '+reqLabels[t.req]+'</span>':'';
      return '<div class="nav-item" data-action="tool-run" data-tool-cmd="'+t.cmd.replace(/"/g,'&quot;')+'" data-tool-name="'+t.name+'"'+reqAttr+' title="'+(needsSetup?(_lang==='ko'?'설정 필요: ':'Setup required: ')+reqLabels[t.req]:t.name)+'">'+t.icon+' '+label+reqBadge+'</div>';
    }).join('');
    if(!filtered.length)c.innerHTML='<div style="padding:8px 12px;color:var(--text2);font-size:12px">'+(_lang==='ko'?'검색 결과 없음':'No results')+'</div>';
  }
  document.getElementById('tools-search').addEventListener('input',function(){_renderToolsList(this.value)});
  function applyLang(){
    document.querySelectorAll('[data-i18n]').forEach(function(el){
      var k=el.getAttribute('data-i18n');
      if(el.tagName==='INPUT'||el.tagName==='TEXTAREA')el.placeholder=t(k);
      else el.textContent=t(k);
    });
    document.querySelectorAll('[data-i18n-ph]').forEach(function(el){
      el.placeholder=t(el.getAttribute('data-i18n-ph'));
    });
    // Translate Save/Test buttons by content matching
    document.querySelectorAll('button').forEach(function(btn){
      var txt=btn.textContent.trim();
      if(txt==='Save'||txt==='저장')btn.textContent=t('btn-save');
      else if(txt==='Test'||txt==='테스트')btn.textContent=t('btn-test');
    });
    var sel=document.getElementById('s-lang');
    if(sel)sel.value=_lang;
    /* Toggle Google guide language */
    var _gEn=document.querySelector('.google-guide-en');var _gKr=document.querySelector('.google-guide-kr');
    if(_gEn&&_gKr){_gEn.style.display=_lang==='ko'?'none':'';_gKr.style.display=_lang==='ko'?'':'none'}
    /* Toggle Telegram/Discord guide language */
    var _tEn=document.querySelector('.tg-guide-en');var _tKr=document.querySelector('.tg-guide-kr');
    if(_tEn&&_tKr){_tEn.style.display=_lang==='ko'?'none':'';_tKr.style.display=_lang==='ko'?'':'none'}
    var _dEn=document.querySelector('.dc-guide-en');var _dKr=document.querySelector('.dc-guide-kr');
    if(_dEn&&_dKr){_dEn.style.display=_lang==='ko'?'none':'';_dKr.style.display=_lang==='ko'?'':'none'}
    /* Toggle eng-en / eng-kr spans */
    document.querySelectorAll('.eng-en').forEach(function(el){el.style.display=_lang==='ko'?'none':'inline'});
    document.querySelectorAll('.eng-kr').forEach(function(el){el.style.display=_lang==='ko'?'inline':'none'})
    /* Refresh tools list on lang change */
    var th2=document.getElementById('tools-header');
    if(th2&&_allTools.length)th2.textContent='🛠️ '+(_lang==='ko'?'도구':'Tools')+' ('+_allTools.length+') ▾';
    var ts=document.getElementById('tools-search');
    if(ts){ts.placeholder=_lang==='ko'?'도구 검색...':'Search tools...';_renderToolsList(ts.value)}
  }
  window.setLang=function(v){_lang=v;localStorage.setItem('salmalm-lang',v);applyLang();if(typeof renderFeatures==='function')renderFeatures(document.getElementById('features-search')?document.getElementById('features-search').value:'');};
