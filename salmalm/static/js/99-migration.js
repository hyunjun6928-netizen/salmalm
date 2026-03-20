  /* --- Agent Migration (에이전트 이동) --- */
  window.exportAgent=function(){
    var s=document.getElementById('exp-sessions').checked?'1':'0';
    var d=document.getElementById('exp-data').checked?'1':'0';
    var v=document.getElementById('exp-vault').checked?'1':'0';
    window.open('/api/agent/export?sessions='+s+'&data='+d+'&vault='+v,'_blank');
  };
  window.quickSyncExport=function(){
    fetch('/api/agent/sync',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},body:JSON.stringify({action:'export'})})
    .then(function(r){return r.json()}).then(function(d){
      if(d.ok){var blob=new Blob([JSON.stringify(d.data,null,2)],{type:'application/json'});var a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='salmalm-quick-sync.json';a.click()}
    });
  };
  var _importZipData=null;
  var dropzone=document.getElementById('import-dropzone');
  if(dropzone){
    dropzone.addEventListener('dragover',function(e){e.preventDefault();dropzone.style.borderColor='var(--accent)'});
    dropzone.addEventListener('dragleave',function(){dropzone.style.borderColor='var(--border)'});
    dropzone.addEventListener('drop',function(e){e.preventDefault();dropzone.style.borderColor='var(--border)';if(e.dataTransfer.files[0])_handleImportFile(e.dataTransfer.files[0])});
  }
  var impInput=document.getElementById('import-file-input');
  if(impInput)impInput.addEventListener('change',function(){if(this.files[0])_handleImportFile(this.files[0]);this.value=''});
  function _handleImportFile(file){
    if(!file.name.endsWith('.zip')){document.getElementById('import-result').textContent='❌ Please select a ZIP file';return}
    var reader=new FileReader();
    reader.onload=function(){
      _importZipData=reader.result;
      document.getElementById('import-btn').disabled=false;
      /* Preview */
      var fd=new FormData();fd.append('file',file);
      fetch('/api/agent/import/preview',{method:'POST',headers:{'X-Session-Token':_tok},body:fd})
      .then(function(r){return r.json()}).then(function(d){
        var prev=document.getElementById('import-preview');
        if(d.ok){
          var m=d.manifest||{};
          prev.innerHTML='<strong>'+file.name+'</strong> ('+Math.round(d.size_bytes/1024)+'KB)<br>'+
            'Agent: '+(m.agent_name||'?')+' · v'+(m.version||'?')+'<br>'+
            'Sections: '+(d.sections||[]).join(', ')+'<br>'+
            'Files: '+d.file_count;
          prev.style.display='block';
        }else{prev.textContent='⚠️ '+(d.error||'Preview failed');prev.style.display='block'}
      }).catch(function(){});
    };
    reader.readAsArrayBuffer(file);
  }
  window.importAgent=function(){
    if(!_importZipData)return;
    var mode=document.getElementById('import-mode').value;
    var blob=new Blob([_importZipData],{type:'application/zip'});
    var fd=new FormData();fd.append('file',blob,'agent-export.zip');fd.append('conflict_mode',mode);
    document.getElementById('import-result').textContent='⏳ Importing...';
    fetch('/api/agent/import',{method:'POST',headers:{'X-Session-Token':_tok},body:fd})
    .then(function(r){return r.json()}).then(function(d){
      var res=document.getElementById('import-result');
      if(d.ok){res.innerHTML='✅ Imported: '+(d.imported||[]).join(', ')+(d.warnings&&d.warnings.length?' <br>⚠️ '+d.warnings.join('; '):'')}
      else{res.textContent='❌ '+(d.errors||[]).join('; ')||(d.error||'Import failed')}
      _importZipData=null;document.getElementById('import-btn').disabled=true;
    }).catch(function(e){document.getElementById('import-result').textContent='❌ '+e});
  };

  /* PWA Service Worker — register for offline cache + install prompt */
  if('serviceWorker' in navigator){
    navigator.serviceWorker.register('/sw.js').catch(function(e){console.warn('SW:',e)});
  }
  /* PWA Install Prompt */
  var _deferredInstall=null;
  window.addEventListener('beforeinstallprompt',function(e){
    e.preventDefault();_deferredInstall=e;
    var btn=document.getElementById('pwa-install-btn');
    if(btn)btn.style.display='inline-flex';
  });
  window.installPWA=function(){
    if(!_deferredInstall)return;
    _deferredInstall.prompt();
    _deferredInstall.userChoice.then(function(){_deferredInstall=null;
      var btn=document.getElementById('pwa-install-btn');if(btn)btn.style.display='none';
    });
  };

  /* ── Logs Tab ── */
  var _logAutoTimer=null;
  /* ── Cron Panel ── */
  window._loadCron=function(){
    var c=document.getElementById('cron-table');if(!c)return;
    c.innerHTML='Loading...';
    fetch('/api/cron',{headers:{'X-Session-Token':_tok}}).then(function(r){return r.json()}).then(function(d){
      var jobs=d.jobs||[];var kr=_lang==='ko';
      if(!jobs.length){c.innerHTML='<div style="padding:24px;text-align:center;color:var(--text2);border:1px dashed var(--border);border-radius:10px">'+(kr?'크론 작업 없음 — 위의 ➕ 버튼으로 추가하세요':'No cron jobs — click ➕ above to add one')+'</div>';return}
      var h='<div style="border:1px solid var(--border);border-radius:10px;overflow:hidden">';
      h+='<div style="display:grid;grid-template-columns:1fr 1fr auto auto auto auto;background:var(--bg3);font-weight:600;font-size:12px">';
      h+='<div style="padding:10px 14px">'+(kr?'이름':'Name')+'</div><div style="padding:10px 14px">'+(kr?'프롬프트':'Prompt')+'</div><div style="padding:10px 14px">'+(kr?'간격':'Interval')+'</div><div style="padding:10px 14px">'+(kr?'실행 횟수':'Runs')+'</div><div style="padding:10px 14px">'+(kr?'상태':'Status')+'</div><div style="padding:10px 14px"></div></div>';
      jobs.forEach(function(j){
        var sched=j.schedule||{};var interval=j.interval||(sched.seconds?_fmtInterval(sched.seconds):(sched.expr||'—'));
        var promptPreview=(j.prompt||'').slice(0,60)+((j.prompt||'').length>60?'…':'');
        h+='<div style="display:grid;grid-template-columns:1fr 1fr auto auto auto auto;font-size:13px;border-top:1px solid var(--border)">';
        h+='<div style="padding:10px 14px;font-weight:500">'+j.name+'</div>';
        h+='<div style="padding:10px 14px;color:var(--text2);font-size:12px" title="'+(j.prompt||'')+'">'+promptPreview+'</div>';
        h+='<div style="padding:10px 14px;color:var(--text2)">'+interval+'</div>';
        h+='<div style="padding:10px 14px;color:var(--text2)">'+j.run_count+'</div>';
        h+='<div style="padding:10px 14px"><button data-action="toggleCronJob" data-cron-id="'+j.id+'" style="background:none;border:none;cursor:pointer;font-size:13px">'+(j.enabled?'🟢 '+(kr?'활성':'On'):'🔴 '+(kr?'비활성':'Off'))+'</button></div>';
        h+='<div style="padding:10px 14px;display:flex;gap:4px"><button data-action="runCronJob" data-cron-id="'+j.id+'" style="background:none;border:none;cursor:pointer;font-size:14px" title="Run Now">▶️</button><button data-action="deleteCronJob" data-cron-id="'+j.id+'" style="background:none;border:none;cursor:pointer;font-size:14px" title="Delete">🗑️</button></div>';
        h+='</div>';
      });
      h+='</div>';
      c.innerHTML=h;
    }).catch(function(e){c.innerHTML='Error: '+e.message});
  };
  function _fmtInterval(s){if(s<60)return s+'s';if(s<3600)return Math.round(s/60)+'m';if(s<86400)return Math.round(s/3600)+'h';return Math.round(s/86400)+'d'}
  /* Cron preset buttons */
  document.querySelectorAll('.cron-preset').forEach(function(btn){
    btn.addEventListener('click',function(){
      var s=parseInt(this.getAttribute('data-seconds'));
      document.getElementById('cron-interval').value=s;
      document.querySelectorAll('.cron-preset').forEach(function(b){b.style.background='var(--bg3)';b.style.color='var(--text)'});
      this.style.background='var(--accent)';this.style.color='#fff';
    });
  });
  window._saveCron=function(){
    var name=document.getElementById('cron-name').value.trim()||'untitled';
    var interval=parseInt(document.getElementById('cron-interval').value)||3600;
    var prompt=document.getElementById('cron-prompt').value.trim();
    var cronModeOnce=document.getElementById('cron-mode-once');
    var runAt=(cronModeOnce&&cronModeOnce.checked)?document.getElementById('cron-at').value||'':'';
    if(!prompt){alert(_lang==='ko'?'프롬프트를 입력하세요':'Enter a prompt');return}
    var payload={name:name,interval:interval,prompt:prompt};
    if(runAt)payload.run_at=runAt;
    fetch('/api/cron/add',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},
      body:JSON.stringify(payload)
    }).then(function(r){return r.json()}).then(function(d){
      if(d.ok){document.getElementById('cron-add-form').style.display='none';window._loadCron()}
      else alert(d.error||'Failed');
    });
  };

  /* ── Memory Panel ── */
  window._loadMemory=function(){
    var fl=document.getElementById('mem-file-list');if(!fl)return;
    fl.innerHTML='<div style="padding:12px;color:var(--text2);font-size:12px">Loading...</div>';
    fetch('/api/memory/files',{headers:{'X-Session-Token':_tok}}).then(function(r){return r.json()}).then(function(d){
      var files=d.files||[];var kr=_lang==='ko';
      if(!files.length){fl.innerHTML='<div style="padding:16px;color:var(--text2);font-size:12px">'+(kr?'메모리 파일 없음':'No memory files')+'</div>';return}
      var h='';
      files.forEach(function(f){
        var icon=f.name.endsWith('.json')?'📦':f.name.endsWith('.md')?'📝':'📄';
        var sz=f.size>1024?(f.size/1024).toFixed(1)+'KB':f.size+'B';
        h+='<div class="nav-item" data-action="memRead" data-mem-path="'+f.path+'" style="padding:10px 14px;border-bottom:1px solid var(--border);cursor:pointer;display:flex;justify-content:space-between;font-size:13px"><span>'+icon+' '+f.name+'</span><span style="color:var(--text2);font-size:11px">'+sz+'</span></div>';
      });
      fl.innerHTML=h;
    }).catch(function(e){fl.innerHTML='Error: '+e.message});
  };
  window._readMemFile=function(path){
    var mc=document.getElementById('mem-file-content');if(!mc)return;
    mc.innerHTML='<div style="color:var(--text2)">Loading...</div>';
    fetch('/api/memory/read?file='+encodeURIComponent(path),{headers:{'X-Session-Token':_tok}}).then(function(r){return r.json()}).then(function(d){
      if(d.error){mc.innerHTML='<div style="color:#f87171">'+d.error+'</div>';return}
      var ext=path.split('.').pop();
      var h='<div style="margin-bottom:8px;font-weight:600;font-size:13px">'+path+' <span style="color:var(--text2);font-weight:400;font-size:11px">'+(d.size/1024).toFixed(1)+'KB</span></div>';
      h+='<pre style="background:var(--bg);padding:12px;border-radius:8px;font-size:12px;line-height:1.6;white-space:pre-wrap;word-break:break-all;max-height:400px;overflow-y:auto">'+d.content.replace(/</g,'&lt;')+'</pre>';
      mc.innerHTML=h;
    }).catch(function(e){mc.innerHTML='Error: '+e.message});
  };

  /* ── Sessions Panel ── */
  window._loadSessions=function(){
    var container=document.getElementById('sessions-table');if(!container)return;
    container.innerHTML='Loading...';
    fetch('/api/sessions',{headers:{'X-Session-Token':_tok}}).then(function(r){return r.json()}).then(function(d){
      var sessions=d.sessions||[];var kr=_lang==='ko';
      var q=(document.getElementById('sess-search')||{}).value||'';
      var ql=q.toLowerCase();
      if(ql)sessions=sessions.filter(function(s){return(s.title||'').toLowerCase().indexOf(ql)>=0||s.id.toLowerCase().indexOf(ql)>=0});
      if(!sessions.length){container.innerHTML='<div style="padding:20px;text-align:center;color:var(--text2)">'+(kr?'세션 없음':'No sessions')+'</div>';return}
      var h='<div style="display:grid;grid-template-columns:1fr auto auto auto;gap:0;border:1px solid var(--border);border-radius:10px;overflow:hidden">';
      h+='<div style="padding:10px 14px;font-weight:600;font-size:12px;background:var(--bg3);border-bottom:1px solid var(--border)">'+(kr?'제목':'Title')+'</div>';
      h+='<div style="padding:10px 14px;font-weight:600;font-size:12px;background:var(--bg3);border-bottom:1px solid var(--border)">'+(kr?'메시지':'Msgs')+'</div>';
      h+='<div style="padding:10px 14px;font-weight:600;font-size:12px;background:var(--bg3);border-bottom:1px solid var(--border)">'+(kr?'마지막 활동':'Last Active')+'</div>';
      h+='<div style="padding:10px 14px;font-weight:600;font-size:12px;background:var(--bg3);border-bottom:1px solid var(--border)"></div>';
      sessions.forEach(function(s){
        var title=(s.title||s.id).substring(0,50);
        var ago=s.updated_at?_timeAgo(s.updated_at):'—';
        var isBranch=s.parent_session_id?'🔀 ':'';
        h+='<div style="padding:8px 14px;font-size:13px;border-bottom:1px solid var(--border);cursor:pointer;display:flex;align-items:center" data-action="sess-open" data-sid="'+s.id+'">'+isBranch+title+'</div>';
        h+='<div style="padding:8px 14px;font-size:12px;border-bottom:1px solid var(--border);color:var(--text2);text-align:center">'+(s.messages||0)+'</div>';
        h+='<div style="padding:8px 14px;font-size:12px;border-bottom:1px solid var(--border);color:var(--text2)">'+ago+'</div>';
        h+='<div style="padding:8px 14px;font-size:12px;border-bottom:1px solid var(--border);text-align:center"><button data-action="sess-delete" data-sid="'+s.id+'" style="background:none;border:none;cursor:pointer;font-size:14px" title="Delete">🗑️</button></div>';
      });
      h+='</div>';
      h+='<div style="margin-top:8px;font-size:12px;color:var(--text2)">'+(kr?'총 '+sessions.length+'개 세션':sessions.length+' sessions')+'</div>';
      container.innerHTML=h;
    }).catch(function(e){container.innerHTML='Error: '+e.message});
  };
  function _timeAgo(dt){
    var d=new Date(dt);var now=new Date();var diff=Math.floor((now-d)/1000);
    if(diff<60)return diff+'s';if(diff<3600)return Math.floor(diff/60)+'m';
    if(diff<86400)return Math.floor(diff/3600)+'h';return Math.floor(diff/86400)+'d';
  }
  if(document.getElementById('sess-search'))document.getElementById('sess-search').addEventListener('input',function(){window._loadSessions()});

  /* ── Channels Panel ── */
  /* ── Docs Panel ── */
  var _docsData=[
    {catKr:'슬래시 커맨드',catEn:'Slash Commands',items:[
      {cmd:'/help',en:'Show all commands',kr:'모든 명령어 표시',detailEn:'Displays a list of all available slash commands and built-in tools.',detailKr:'사용 가능한 모든 슬래시 커맨드와 내장 도구 목록을 표시합니다.'},
      {cmd:'/status',en:'Session status (model, tokens, cost)',kr:'세션 상태 (모델, 토큰, 비용)',detailEn:'Shows current session info: active model, token count, estimated cost, thinking mode.',detailKr:'현재 세션 정보를 표시합니다: 활성 모델, 토큰 수, 예상 비용, 사고 모드.'},
      {cmd:'/model <name>',en:'Switch AI model',kr:'AI 모델 전환',detailEn:'Switch models: opus, sonnet, haiku, gpt, grok, gemini, auto. "auto" enables smart 3-tier routing.',detailKr:'모델 전환: opus, sonnet, haiku, gpt, grok, gemini, auto. "auto"는 3단계 스마트 라우팅.'},
      {cmd:'/think [level]',en:'Extended thinking (low/medium/high/xhigh)',kr:'확장 사고 (low/medium/high/xhigh)',detailEn:'Enables deep reasoning. "low" ~1K tokens, "medium" ~5K, "high" ~20K, "xhigh" max budget.',detailKr:'심층 추론 활성화. "low" ~1K, "medium" ~5K, "high" ~20K, "xhigh" 최대 예산.'},
      {cmd:'/context',en:'Token count breakdown',kr:'토큰 수 분석',detailEn:'Shows system prompt, history, tools, and remaining context window in tokens.',detailKr:'시스템 프롬프트, 히스토리, 도구, 남은 컨텍스트 윈도우를 토큰 단위로 표시.'},
      {cmd:'/usage',en:'Token and cost tracking',kr:'토큰 및 비용 추적',detailEn:'Cumulative token usage and cost across sessions. /usage daily, /usage monthly also available.',detailKr:'세션별 누적 토큰 사용량과 비용. /usage daily, /usage monthly도 가능.'},
      {cmd:'/clear',en:'Clear current session',kr:'현재 세션 초기화',detailEn:'Removes all messages from the current session.',detailKr:'현재 세션의 모든 메시지를 제거합니다.'},
      {cmd:'/prune',en:'Aggressive context trim',kr:'컨텍스트 적극 정리',detailEn:'Manually triggers aggressive context pruning to reduce token usage.',detailKr:'토큰 사용량을 줄이기 위해 적극적 컨텍스트 정리를 실행합니다.'},
      {cmd:'/tools',en:'List all tools',kr:'전체 도구 목록',detailEn:'Shows all 62+ built-in tools with descriptions.',detailKr:'62개+ 내장 도구의 전체 목록과 설명을 표시합니다.'},
      {cmd:'/soul',en:'View/edit AI personality',kr:'AI 성격 확인/편집',detailEn:'View or edit the SOUL.md personality file. /soul reset to restore default.',detailKr:'SOUL.md 성격 파일을 확인하거나 편집합니다. /soul reset으로 기본값 복원.'},
      {cmd:'/compare <query>',en:'Compare two model responses',kr:'두 모델 응답 비교',detailEn:'Get responses from two different models for the same query.',detailKr:'같은 질문에 대해 두 모델의 응답을 받습니다.'},
      {cmd:'/subagents',en:'Sub-agent management',kr:'서브에이전트 관리',detailEn:'spawn <task>, list, stop <id>, steer <id> <msg>, log <id>, collect. Background AI workers.',detailKr:'spawn <작업>, list, stop <id>, steer <id> <메시지>, log <id>, collect. 백그라운드 AI 워커.'},
      {cmd:'/export',en:'Export session data',kr:'세션 데이터 내보내기',detailEn:'Export current session as JSON or Markdown.',detailKr:'현재 세션을 JSON 또는 Markdown으로 내보냅니다.'},
      {cmd:'/security',en:'Security status',kr:'보안 상태',detailEn:'Shows vault status, bind address, exec restrictions, active tokens.',detailKr:'금고 상태, 바인드 주소, exec 제한, 활성 토큰을 표시합니다.'},
      {cmd:'/plugins',en:'Plugin management',kr:'플러그인 관리',detailEn:'List, enable, disable plugins from the plugins/ directory.',detailKr:'plugins/ 디렉토리의 플러그인 목록 확인, 활성화, 비활성화.'},
      {cmd:'/evolve',en:'Auto-generated prompt rules',kr:'자동 생성 프롬프트 규칙',detailEn:'View/manage rules the AI learns from your conversations (max 20, FIFO).',detailKr:'AI가 대화에서 학습한 규칙 확인/관리 (최대 20개, FIFO).'},
      {cmd:'/mood',en:'Mood-aware mode',kr:'감정 인식 모드',detailEn:'Toggle emotional state detection. AI adapts tone based on your mood.',detailKr:'감정 상태 감지 토글. AI가 기분에 따라 톤을 조정합니다.'},
      {cmd:'/tts <text>',en:'Text to speech',kr:'텍스트 음성 변환',detailEn:'Convert text to speech audio.',detailKr:'텍스트를 음성으로 변환합니다.'},
      {cmd:'/debug',en:'System diagnostics',kr:'시스템 진단',detailEn:'Shows system info, active sessions, model status, error log.',detailKr:'시스템 정보, 활성 세션, 모델 상태, 에러 로그를 표시합니다.'},
      {cmd:'/compact',en:'Compress conversation context',kr:'대화 컨텍스트 압축',detailEn:'Summarizes conversation history to reduce tokens. Auto-triggered at 80K, manual anytime.',detailKr:'대화 기록을 요약하여 토큰을 줄입니다. 80K에서 자동 실행, 수동도 가능.'},
      {cmd:'/persona <name>',en:'Switch persona',kr:'페르소나 전환',detailEn:'Switch AI personality. Custom personas loaded from SOUL.md.',detailKr:'AI 성격 변경. 커스텀 페르소나는 SOUL.md에서 로드.'},
      {cmd:'/branch',en:'Branch conversation',kr:'대화 분기',detailEn:'Create a new branch from current point to explore alternatives.',detailKr:'현재 지점에서 새 분기를 만들어 대안을 탐색합니다.'},
      {cmd:'/rollback [n]',en:'Rollback last n messages',kr:'마지막 n개 메시지 롤백',detailEn:'Remove last n message pairs. Default n=1.',detailKr:'마지막 n개 메시지 쌍을 제거합니다. 기본 n=1.'},
      {cmd:'/new',en:'New session',kr:'새 세션',detailEn:'Start a fresh conversation session.',detailKr:'새 대화 세션을 시작합니다.'},
      {cmd:'/vault',en:'Encrypted vault',kr:'암호화 금고',detailEn:'Manage secrets: /vault set|get|list|delete. AES-256-GCM encrypted.',detailKr:'비밀 관리: /vault set|get|list|delete. AES-256-GCM 암호화.'},
      {cmd:'/bash <cmd>',en:'Run shell command',kr:'셸 명령 실행',detailEn:'Execute shell command with approval system. Dangerous flags blocked per-command.',detailKr:'승인 시스템으로 셸 명령 실행. 명령별 위험 플래그 차단.'},
      {cmd:'/shadow',en:'Shadow mode',kr:'섀도우 모드',detailEn:'AI silently learns your style. Toggle: /shadow on|off|status. Can reply as you when away.',detailKr:'AI가 소통 스타일을 조용히 학습. 토글: /shadow on|off|status. 부재 시 대리 응답 가능.'},
      {cmd:'/deadman',en:'Dead man\'s switch',kr:'데드맨 스위치',detailEn:'Auto-actions after N days inactive: /deadman set <days> <action>. Cancel: /deadman off.',detailKr:'N일간 비활성 시 자동 조치: /deadman set <일수> <조치>. 취소: /deadman off.'},
      {cmd:'/capsule',en:'Time capsule',kr:'타임캡슐',detailEn:'Message to future self: /capsule 7d Remember this. Delivered after specified time.',detailKr:'미래의 나에게: /capsule 7d 이것 기억해. 지정 시간 후 전달.'},
      {cmd:'/split',en:'A/B split response',kr:'A/B 분할 응답',detailEn:'Get two model responses to the same question side-by-side.',detailKr:'같은 질문에 두 모델 응답을 나란히 비교합니다.'},
      {cmd:'/life',en:'Life dashboard',kr:'라이프 대시보드',detailEn:'Unified view: expenses, habits, calendar, mood, routines.',detailKr:'통합 뷰: 지출, 습관, 캘린더, 감정, 루틴.'},
      {cmd:'/workflow',en:'Workflow engine',kr:'워크플로우 엔진',detailEn:'Multi-step AI workflows: /workflow create|add|run. Supports conditions and loops.',detailKr:'다단계 AI 워크플로우: /workflow create|add|run. 조건/루프 지원.'},
      {cmd:'/a2a',en:'Agent-to-agent',kr:'에이전트 간 통신',detailEn:'HMAC-SHA256 signed messages between SalmAlm instances.',detailKr:'SalmAlm 인스턴스 간 HMAC-SHA256 서명 메시지.'},
      {cmd:'/queue',en:'Message queue (5 modes)',kr:'메시지 큐 (5가지 모드)',detailEn:'Queue management: /queue status|mode|clear|modes. Modes: collect, steer, followup, steer-backlog, interrupt.',detailKr:'큐 관리: /queue status|mode|clear|modes. 모드: collect, steer, followup, steer-backlog, interrupt.'},
      {cmd:'/mcp',en:'MCP marketplace',kr:'MCP 마켓플레이스',detailEn:'Model Context Protocol: /mcp install|list|catalog|remove|status|search.',detailKr:'Model Context Protocol: /mcp install|list|catalog|remove|status|search.'},
      {cmd:'/screen',en:'Browser/screen capture',kr:'브라우저/화면 캡처',detailEn:'Screen automation: /screen [watch|history|search]. Requires pip install salmalm[browser].',detailKr:'화면 자동화: /screen [watch|history|search]. pip install salmalm[browser] 필요.'},
      {cmd:'/cron',en:'Scheduled tasks',kr:'예약 작업',detailEn:'Schedule recurring AI tasks via Web UI → Cron panel. Standard cron syntax.',detailKr:'웹 UI → 크론 패널에서 반복 AI 작업 예약. 표준 크론 문법.'},
      {cmd:'/remind <time> <msg>',en:'Set reminder',kr:'리마인더 설정',detailEn:'Schedule reminders: /remind 30m check email, /remind 2h meeting.',detailKr:'리마인더 예약: /remind 30m 이메일 확인, /remind 2h 회의.'},
      {cmd:'/config',en:'Configuration',kr:'설정 관리',detailEn:'View/modify config: /config show|get|set|unset.',detailKr:'설정 확인/변경: /config show|get|set|unset.'},
      {cmd:'/oauth',en:'OAuth setup',kr:'OAuth 설정',detailEn:'OAuth2 for Gmail/Calendar: /oauth setup|status|revoke|refresh.',detailKr:'Gmail/캘린더용 OAuth2: /oauth setup|status|revoke|refresh.'},
      {cmd:'/whoami',en:'Current user info',kr:'현재 사용자 정보',detailEn:'Shows user ID, session ID, auth status.',detailKr:'사용자 ID, 세션 ID, 인증 상태 표시.'},
      {cmd:'/approve',en:'Approve exec commands',kr:'실행 명령 승인',detailEn:'Review and approve/reject pending shell commands.',detailKr:'대기 중인 셸 명령을 검토하고 승인/거부합니다.'},
    ]},
    {catKr:'단축키',catEn:'Keyboard Shortcuts',items:[
      {cmd:'Enter',en:'Send message',kr:'메시지 전송',detailEn:'Sends the current message.',detailKr:'현재 메시지를 전송합니다.'},
      {cmd:'Shift+Enter',en:'New line',kr:'줄바꿈',detailEn:'Inserts a line break without sending.',detailKr:'전송 없이 줄바꿈을 삽입합니다.'},
      {cmd:'Ctrl+K',en:'Search conversations',kr:'대화 검색',detailEn:'Search messages across all sessions.',detailKr:'모든 세션에서 메시지를 검색합니다.'},
      {cmd:'Ctrl+/',en:'Command palette',kr:'명령 팔레트',detailEn:'Quick access to any slash command.',detailKr:'슬래시 커맨드에 빠르게 접근합니다.'},
      {cmd:'Ctrl+V',en:'Paste image/file',kr:'이미지/파일 붙여넣기',detailEn:'Paste image from clipboard for vision analysis.',detailKr:'클립보드 이미지를 붙여넣어 비전 분석합니다.'},
      {cmd:'Esc',en:'Close modal',kr:'모달 닫기',detailEn:'Closes any open modal and returns to chat.',detailKr:'열린 모달을 닫고 채팅으로 돌아갑니다.'},
    ]},
    {catKr:'핵심 기능',catEn:'Core Features',items:[
      {cmd:'Auto Routing',en:'3-tier model routing (simple/moderate/complex)',kr:'3단계 모델 라우팅 (간단/보통/복잡)',detailEn:'Automatically selects the best model per query: Haiku for simple, Sonnet for moderate, Opus/GPT-5 for complex tasks. Saves 83% on API costs.',detailKr:'질문별 최적 모델 자동 선택: 간단→Haiku, 보통→Sonnet, 복잡→Opus/GPT-5. API 비용 83% 절감.'},
      {cmd:'Memory',en:'2-layer memory with auto-recall',kr:'2계층 메모리 + 자동 회상',detailEn:'MEMORY.md (long-term) + daily logs. AI searches memory before each response and injects relevant context.',detailKr:'MEMORY.md (장기) + 일별 로그. AI가 매 응답 전 메모리를 검색하여 관련 컨텍스트를 주입합니다.'},
      {cmd:'Vault',en:'AES-256-GCM encrypted storage',kr:'AES-256-GCM 암호화 저장소',detailEn:'All API keys and secrets encrypted with PBKDF2-200K + AES-256-GCM. Auto-unlock on localhost.',detailKr:'모든 API 키와 비밀이 PBKDF2-200K + AES-256-GCM으로 암호화. localhost에서 자동 잠금해제.'},
      {cmd:'Cron',en:'Scheduled AI tasks',kr:'예약 AI 작업',detailEn:'Schedule recurring tasks via Web UI → Cron panel. Tasks run in isolated sessions.',detailKr:'웹 UI → 크론 패널에서 반복 작업 예약. 작업은 격리된 세션에서 실행.'},
      {cmd:'Multi-file Upload',en:'Upload multiple files at once',kr:'여러 파일 한번에 업로드',detailEn:'Click clip button multiple times, drag-drop, or Shift-select. Images get vision analysis.',detailKr:'클립 버튼 반복 클릭, 드래그 앤 드롭, Shift 선택. 이미지는 비전 분석.'},
      {cmd:'Message Queue',en:'Messages queue during AI response',kr:'AI 응답 중 메시지 큐',detailEn:'Send messages while AI is responding — they queue and send automatically after response completes. No more interruptions.',detailKr:'AI 응답 중에도 메시지 전송 가능 — 응답 완료 후 자동 전송. 중단 없음.'},
    ]},
    {catKr:'독자적 기능',catEn:'Unique Features',items:[
      {cmd:'Self-Evolving Prompt',en:'AI auto-generates prompt rules from conversations (max 20)',kr:'대화에서 프롬프트 규칙 자동 생성 (최대 20개)',detailEn:'The AI observes your preferences and patterns over time, auto-creating system prompt rules (max 20, FIFO) that align responses with your style. View: /evolve list.',detailKr:'AI가 선호와 패턴을 관찰하여 시스템 프롬프트 규칙을 자동 생성합니다 (최대 20개, FIFO). 확인: /evolve list.'},
      {cmd:'Dead Man\'s Switch',en:'Automated actions if owner goes inactive',kr:'소유자 비활성 시 자동 조치',detailEn:'If you don\'t interact for N days, pre-set actions auto-execute: emails, status updates, cleanup scripts. A digital safety net.',detailKr:'N일간 상호작용 없으면 미리 설정된 조치 자동 실행: 이메일, 상태 업데이트, 정리 스크립트. 디지털 안전망.'},
      {cmd:'Shadow Mode',en:'AI learns your style, replies as you when away',kr:'스타일 학습, 부재 시 대리 응답',detailEn:'In Shadow Mode, the AI reads messages without responding, building a profile of your communication style. When away, it can reply as you.',detailKr:'섀도우 모드에서 AI가 응답 없이 메시지를 읽으며 소통 스타일 프로필을 구축합니다. 부재 시 대리 응답 가능.'},
      {cmd:'Life Dashboard',en:'Unified personal dashboard',kr:'통합 개인 대시보드',detailEn:'/life shows everything: expense totals, habit streaks, upcoming events, mood history, routine progress.',detailKr:'/life로 모든 것 표시: 지출 합계, 습관 연속 기록, 예정 이벤트, 감정 이력, 루틴 진행률.'},
      {cmd:'Mood-Aware',en:'Emotional state detection and tone adaptation',kr:'감정 상태 감지 및 톤 적응',detailEn:'Uses NLP signals to estimate emotional state. Adjusts tone: gentler when frustrated, celebratory when excited.',detailKr:'NLP 신호로 감정 상태 추정. 톤 조정: 좌절 시 부드럽게, 흥분 시 축하 톤.'},
      {cmd:'A/B Split',en:'Two model responses side-by-side',kr:'두 모델 응답 나란히 비교',detailEn:'One question, two answers from different models simultaneously. Compare reasoning and writing styles.',detailKr:'하나의 질문으로 두 모델 답변을 동시에 받아 비교합니다.'},
      {cmd:'Time Capsule',en:'Encrypted messages to future self',kr:'미래의 나에게 암호화 메시지',detailEn:'Write a message, set delivery date. Stored encrypted, delivered as chat notification when time comes.',detailKr:'메시지 작성, 전달 날짜 설정. 암호화 저장, 시간이 되면 채팅 알림으로 전달.'},
      {cmd:'Thought Stream',en:'Private journaling with mood tracking',kr:'감정 추적 포함 개인 일기',detailEn:'Private timeline with timestamps, mood scores, hashtags. Search by #tag or date. All local, never sent to AI providers.',detailKr:'타임스탬프, 감정 점수, 해시태그가 포함된 개인 타임라인. #태그나 날짜로 검색. 모두 로컬 저장.'},
      {cmd:'Agent-to-Agent',en:'HMAC-signed inter-instance communication',kr:'HMAC 서명된 인스턴스 간 통신',detailEn:'Connect multiple SalmAlm instances. Messages authenticated with HMAC-SHA256. Use: home ↔ work server.',detailKr:'여러 SalmAlm 인스턴스 연결. HMAC-SHA256으로 메시지 인증. 활용: 집 ↔ 직장 서버.'},
      {cmd:'Workflow Engine',en:'Multi-step AI workflows with conditions/loops',kr:'조건/루프 포함 다단계 AI 워크플로우',detailEn:'Create complex pipelines: /workflow create, add steps, run. Steps can include tool calls, conditions, and loops.',detailKr:'복잡한 파이프라인 생성: /workflow create, 단계 추가, 실행. 도구 호출, 조건, 루프 포함 가능.'},
    ]},
  ];
  window._renderDocs=function(q){
    var c=document.getElementById('docs-content');if(!c)return;
    var kr=_lang==='ko';var ql=q.toLowerCase();var h='';
    _docsData.forEach(function(sec){
      var catTitle=kr?sec.catKr:sec.catEn;
      var items=sec.items;
      if(ql)items=items.filter(function(i){return i.cmd.toLowerCase().indexOf(ql)>=0||(kr?i.kr:i.en).toLowerCase().indexOf(ql)>=0||i.en.toLowerCase().indexOf(ql)>=0||i.kr.indexOf(ql)>=0||(i.detailEn||'').toLowerCase().indexOf(ql)>=0||(i.detailKr||'').indexOf(ql)>=0});
      if(!items.length)return;
      h+='<div style="margin-bottom:20px"><h3 style="margin-bottom:10px;font-size:15px">'+catTitle+'</h3>';
      h+='<div style="border:1px solid var(--border);border-radius:10px;overflow:hidden">';
      items.forEach(function(i,idx){
        var bg=idx%2===0?'var(--bg)':'var(--bg3)';
        var detail=kr?(i.detailKr||''):(i.detailEn||'');
        var hasDetail=!!detail;
        h+='<div data-action="toggleDocDetail" style="padding:10px 14px;background:'+bg+';border-bottom:1px solid var(--border);'+(hasDetail?'cursor:pointer;':'')+'">';
        h+='<div style="display:flex;gap:16px;align-items:baseline">';
        h+='<code style="font-size:13px;font-weight:600;white-space:nowrap;min-width:180px;color:var(--accent2)">'+i.cmd+'</code>';
        h+='<span style="font-size:13px;color:var(--text);flex:1">'+(kr?i.kr:i.en)+'</span>';
        if(hasDetail)h+='<span style="font-size:11px;color:var(--text2);transition:transform 0.2s" class="doc-chevron">▶</span>';
        h+='</div>';
        if(hasDetail)h+='<div class="doc-detail" style="display:none;margin-top:8px;padding:10px 12px;font-size:12.5px;line-height:1.6;color:var(--text2);background:var(--bg2);border-radius:8px;border-left:3px solid var(--accent)">'+detail+'</div>';
        h+='</div>';
      });
      h+='</div></div>';
    });
    if(!h)h='<div style="padding:20px;text-align:center;color:var(--text2)">'+(kr?'검색 결과 없음':'No results')+'</div>';
    c.innerHTML=h;
  };
  if(document.getElementById('docs-search'))document.getElementById('docs-search').addEventListener('input',function(){window._renderDocs(this.value)});
  /* Pre-render docs so content is ready when panel opens */
  try{window._renderDocs('')}catch(e){console.warn('Docs pre-render:',e)}

  /* ── Debug Tab ── */
  var _debugAutoTimer=null;
  window._loadDebug=function(){
    var panel=document.getElementById('debug-panel');if(!panel)return;
    panel.innerHTML='<div style="grid-column:1/-1;color:var(--text2);font-size:12px">Loading...</div>';
    fetch('/api/debug',{headers:{'X-Session-Token':_tok}}).then(function(r){return r.json()}).then(function(d){
      var kr=_lang==='ko';
      function card(icon,title,rows){
        var h='<div style="background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:14px"><div style="font-weight:600;margin-bottom:10px;font-size:13px">'+icon+' '+title+'</div>';
        rows.forEach(function(r){h+='<div style="display:flex;justify-content:space-between;font-size:12px;padding:3px 0;border-bottom:1px solid var(--border)"><span style="color:var(--text2)">'+r[0]+'</span><span style="font-weight:500">'+r[1]+'</span></div>'});
        return h+'</div>';
      }
      var dot=function(ok){return ok?'🟢':'🔴'};
      // System
      var sysRows=[[kr?'Python':'Python',(d.python||'?').split(' ')[0]],[kr?'플랫폼':'Platform',d.platform||'?'],[kr?'PID':'PID',d.pid||'?'],[kr?'메모리':'Memory',(d.memory_mb||0)+'MB'],[kr?'GC (0/1/2)':'GC (0/1/2)',d.gc?(d.gc.gen0+'/'+d.gc.gen1+'/'+d.gc.gen2):'?']];
      // Engine
      var m=d.metrics||{};
      var engRows=[[kr?'활성 요청':'Active Requests',d.active_requests],[kr?'종료 중':'Shutting Down',d.shutting_down?'⚠️ Yes':'No'],[kr?'총 요청':'Total Requests',m.requests||0],[kr?'도구 호출':'Tool Calls',m.tool_calls||0],[kr?'에러':'Errors',m.errors||0],[kr?'캐시 히트':'Cache Hits',m.cache_hits||0]];
      // Session
      var sessRows=[[kr?'메시지 수':'Messages',d.session.messages],[kr?'컨텍스트 크기':'Context Size',(d.session.context_chars/1024).toFixed(1)+'KB']];
      // Tools
      var toolRows=[[kr?'등록된 도구':'Registered',d.tools.registered],[kr?'동적 도구':'Dynamic',d.tools.dynamic]];
      // Providers
      var provRows=[];
      for(var pn in d.providers){provRows.push([pn,dot(d.providers[pn])+' '+(d.providers[pn]?(kr?'연결됨':'Connected'):(kr?'키 없음':'No key'))])}
      provRows.push([kr?'Vault':'Vault',dot(d.vault_unlocked)+' '+(d.vault_unlocked?(kr?'열림':'Unlocked'):(kr?'잠김':'Locked'))]);
      panel.innerHTML=card('🖥️',kr?'시스템':'System',sysRows)+card('⚡',kr?'엔진':'Engine',engRows)+card('💬',kr?'세션 (web)':'Session (web)',sessRows)+card('🔧',kr?'도구':'Tools',toolRows)+card('🔑',kr?'프로바이더':'Providers',provRows);
    }).catch(function(e){panel.innerHTML='<div style="grid-column:1/-1;color:#f87171">Error: '+e.message+'</div>'});
  };
  document.getElementById('debug-auto-refresh').addEventListener('change',function(){
    if(this.checked){window._loadDebug();_debugAutoTimer=setInterval(window._loadDebug,3000)}
    else{clearInterval(_debugAutoTimer);_debugAutoTimer=null}
  });

  window._loadLogs=function(){
    var level=document.getElementById('log-level').value;
    var lines=document.getElementById('log-lines').value;
    var viewer=document.getElementById('log-viewer');
    viewer.textContent='Loading...';
    fetch('/api/logs?lines='+lines+'&level='+level,{headers:{'X-Session-Token':_tok}})
    .then(function(r){return r.json()}).then(function(d){
      var logs=d.logs||[];
      if(!logs.length){viewer.textContent='No logs found.';return}
      var html='';
      logs.forEach(function(ln){
        var cls='';
        if(ln.indexOf('[ERROR]')!==-1)cls='color:#f87171;font-weight:600';
        else if(ln.indexOf('[WARNING]')!==-1)cls='color:#fbbf24';
        else if(ln.indexOf('[INFO]')!==-1)cls='color:var(--text2)';
        html+='<div style="'+cls+';padding:1px 0;border-bottom:1px solid var(--border)">'+ln.replace(/</g,'&lt;').replace(/>/g,'&gt;')+'</div>';
      });
      viewer.innerHTML=html;
      viewer.scrollTop=viewer.scrollHeight;
    }).catch(function(e){viewer.textContent='Error: '+e.message});
  };
  document.getElementById('log-auto-refresh').addEventListener('change',function(){
    if(this.checked){_logAutoTimer=setInterval(window._loadLogs,5000)}
    else{clearInterval(_logAutoTimer);_logAutoTimer=null}
  });

  /* ── Model Router Tab (v2) ── */
