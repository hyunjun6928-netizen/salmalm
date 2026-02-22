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

  /* PWA Service Worker */
  if('serviceWorker' in navigator){
    /* Unregister any existing SW and clear caches — no offline cache needed */
    navigator.serviceWorker.getRegistrations().then(function(regs){regs.forEach(function(r){r.unregister()})});
    caches.keys().then(function(ks){ks.forEach(function(k){caches.delete(k)})});
  }

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
      h+='<div style="display:grid;grid-template-columns:1fr auto auto auto auto;background:var(--bg3);font-weight:600;font-size:12px">';
      h+='<div style="padding:10px 14px">'+(kr?'이름':'Name')+'</div><div style="padding:10px 14px">'+(kr?'간격':'Interval')+'</div><div style="padding:10px 14px">'+(kr?'실행 횟수':'Runs')+'</div><div style="padding:10px 14px">'+(kr?'상태':'Status')+'</div><div style="padding:10px 14px"></div></div>';
      jobs.forEach(function(j){
        var sched=j.schedule||{};var interval=sched.seconds?_fmtInterval(sched.seconds):(sched.expr||'—');
        h+='<div style="display:grid;grid-template-columns:1fr auto auto auto auto;font-size:13px;border-top:1px solid var(--border)">';
        h+='<div style="padding:10px 14px;font-weight:500">'+j.name+'</div>';
        h+='<div style="padding:10px 14px;color:var(--text2)">'+interval+'</div>';
        h+='<div style="padding:10px 14px;color:var(--text2)">'+j.run_count+'</div>';
        h+='<div style="padding:10px 14px"><button data-action="toggleCronJob" data-cron-id="'+j.id+'" style="background:none;border:none;cursor:pointer;font-size:13px">'+(j.enabled?'🟢 '+(kr?'활성':'On'):'🔴 '+(kr?'비활성':'Off'))+'</button></div>';
        h+='<div style="padding:10px 14px"><button data-action="deleteCronJob" data-cron-id="'+j.id+'" style="background:none;border:none;cursor:pointer;font-size:14px" title="Delete">🗑️</button></div>';
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
    var runAt=document.getElementById('cron-at').value||'';
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
      {cmd:'/help',en:'Show all commands and tools',kr:'모든 명령어와 도구 표시',detailEn:'Displays a complete list of all available slash commands, built-in tools, and unique features. Use this as a quick reference when you forget a command name.',detailKr:'사용 가능한 모든 슬래시 커맨드, 내장 도구, 고유 기능의 전체 목록을 표시합니다. 명령어 이름이 기억나지 않을 때 빠른 참조용으로 사용하세요.'},
      {cmd:'/status',en:'Session status (model, tokens, cost)',kr:'세션 상태 (모델, 토큰, 비용)',detailEn:'Shows current session info: active model, token count (input/output), estimated cost, thinking mode, and persona. Useful for monitoring usage.',detailKr:'현재 세션 정보를 표시합니다: 활성 모델, 토큰 수(입력/출력), 예상 비용, 사고 모드, 페르소나. 사용량 모니터링에 유용합니다.'},
      {cmd:'/model <name>',en:'Switch AI model',kr:'AI 모델 전환',detailEn:'Switch between models: opus, sonnet, haiku, gpt, grok, gemini, auto. "auto" enables smart routing that picks the best model per query complexity. Example: /model opus',detailKr:'모델 전환: opus, sonnet, haiku, gpt, grok, gemini, auto. "auto"는 질문 복잡도에 따라 최적 모델을 자동 선택합니다. 예: /model opus'},
      {cmd:'/compact',en:'Compress conversation context',kr:'대화 컨텍스트 압축',detailEn:'Summarizes the conversation history to reduce token usage. Automatically triggered at 80K tokens, but you can run it manually anytime. Preserves key information while cutting context size by ~70%.',detailKr:'대화 기록을 요약하여 토큰 사용량을 줄입니다. 80K 토큰에서 자동 실행되지만 수동으로도 가능합니다. 핵심 정보를 보존하면서 컨텍스트 크기를 ~70% 줄입니다.'},
      {cmd:'/context',en:'Token count breakdown',kr:'토큰 수 분석',detailEn:'Shows detailed token breakdown: system prompt, conversation history, tool definitions, and available context window. Helps you understand how close you are to the context limit.',detailKr:'상세 토큰 분석: 시스템 프롬프트, 대화 기록, 도구 정의, 사용 가능한 컨텍스트 윈도우. 컨텍스트 한도에 얼마나 가까운지 파악할 수 있습니다.'},
      {cmd:'/usage',en:'Token and cost tracking',kr:'토큰 및 비용 추적',detailEn:'Displays cumulative token usage and cost across all sessions. Shows input/output tokens, cache hits, and estimated USD cost per provider. Resets monthly.',detailKr:'모든 세션의 누적 토큰 사용량과 비용을 표시합니다. 입력/출력 토큰, 캐시 히트, 프로바이더별 예상 USD 비용을 보여줍니다. 월별 초기화.'},
      {cmd:'/think [level]',en:'Extended thinking mode (low/medium/high)',kr:'확장 사고 모드 (low/medium/high)',detailEn:'Enables deep reasoning with configurable budget. "low" uses ~1K thinking tokens, "medium" ~5K, "high" ~20K. The AI shows its reasoning process before answering. Great for complex coding/math.',detailKr:'설정 가능한 예산으로 심층 추론을 활성화합니다. "low" ~1K, "medium" ~5K, "high" ~20K 사고 토큰. AI가 답변 전 추론 과정을 보여줍니다. 복잡한 코딩/수학에 적합.'},
      {cmd:'/persona <name>',en:'Switch persona',kr:'페르소나 전환',detailEn:'Changes the AI personality. Built-in: expert, friend, assistant. Custom personas are loaded from SOUL.md in your data directory. The persona affects tone, formality, and response style.',detailKr:'AI 성격을 변경합니다. 내장: expert, friend, assistant. 커스텀 페르소나는 데이터 디렉토리의 SOUL.md에서 로드됩니다. 톤, 격식, 응답 스타일에 영향을 줍니다.'},
      {cmd:'/branch',en:'Branch conversation',kr:'대화 분기',detailEn:'Creates a new conversation branch from the current point. Useful for exploring alternative directions without losing the original thread. Branches are visible in the Sessions panel.',detailKr:'현재 지점에서 새 대화 분기를 생성합니다. 원래 스레드를 잃지 않고 대안을 탐색할 때 유용합니다. 분기는 세션 패널에서 확인 가능.'},
      {cmd:'/rollback [n]',en:'Rollback last n messages',kr:'마지막 n개 메시지 롤백',detailEn:'Removes the last n message pairs (user + assistant). Default n=1. Useful when the AI misunderstands or you want to rephrase. The messages are permanently deleted from the session.',detailKr:'마지막 n개 메시지 쌍(사용자+AI)을 제거합니다. 기본 n=1. AI가 오해했거나 다시 질문하고 싶을 때 유용합니다. 메시지는 세션에서 영구 삭제됩니다.'},
      {cmd:'/remind <time> <msg>',en:'Set a reminder',kr:'리마인더 설정',detailEn:'Schedule a reminder. Supports natural language: "/remind 30m check email", "/remind 2h meeting", "/remind tomorrow 9am call dentist". Uses the cron system internally.',detailKr:'리마인더를 예약합니다. 자연어 지원: "/remind 30m 이메일 확인", "/remind 2h 회의", "/remind tomorrow 9am 치과 전화". 내부적으로 크론 시스템 사용.'},
      {cmd:'/expense <amount> <desc>',en:'Track an expense',kr:'지출 기록',detailEn:'Log expenses for the Life Dashboard. Example: "/expense 15000 lunch". Amounts are stored with timestamps and categories. View summaries with /life.',detailKr:'라이프 대시보드용 지출을 기록합니다. 예: "/expense 15000 점심". 금액은 타임스탬프와 카테고리와 함께 저장됩니다. /life로 요약 확인.'},
      {cmd:'/pomodoro',en:'Pomodoro timer',kr:'뽀모도로 타이머',detailEn:'Starts a 25-minute focus timer with 5-minute breaks. Tracks your productivity sessions. The AI will notify you when each interval ends.',detailKr:'25분 집중 타이머와 5분 휴식을 시작합니다. 생산성 세션을 추적합니다. 각 구간이 끝나면 AI가 알려줍니다.'},
      {cmd:'/note <text>',en:'Quick note',kr:'빠른 메모',detailEn:'Saves a quick note to your memory directory. Notes are timestamped and searchable. They persist across sessions and can be referenced by the AI.',detailKr:'메모리 디렉토리에 빠른 메모를 저장합니다. 메모는 타임스탬프가 찍히고 검색 가능합니다. 세션 간에 유지되며 AI가 참조할 수 있습니다.'},
      {cmd:'/link <url>',en:'Save a link',kr:'링크 저장',detailEn:'Bookmarks a URL with optional description. Links are stored in your data directory and can be searched or listed later.',detailKr:'URL을 선택적 설명과 함께 북마크합니다. 링크는 데이터 디렉토리에 저장되며 나중에 검색하거나 목록을 볼 수 있습니다.'},
      {cmd:'/routine',en:'Manage daily routines',kr:'일일 루틴 관리',detailEn:'Create, list, and track daily routines (morning workout, journaling, etc.). The AI reminds you of incomplete routines and tracks streaks.',detailKr:'일일 루틴을 생성, 목록 확인, 추적합니다 (아침 운동, 일기 등). AI가 미완료 루틴을 알려주고 연속 기록을 추적합니다.'},
      {cmd:'/shadow',en:'Shadow mode (silent learning)',kr:'섀도우 모드 (무음 학습)',detailEn:'AI silently learns your communication style by analyzing your messages. When activated, it can reply as you when you\'re away. Toggle: /shadow on, /shadow off, /shadow status.',detailKr:'AI가 메시지를 분석하여 당신의 소통 스타일을 조용히 학습합니다. 활성화하면 부재 시 대리 응답이 가능합니다. 토글: /shadow on, /shadow off, /shadow status.'},
      {cmd:'/vault',en:'Encrypted vault operations',kr:'암호화 금고 작업',detailEn:'Manage encrypted secrets: /vault set <key> <value>, /vault get <key>, /vault list, /vault delete <key>. All data encrypted with AES-256-GCM (or HMAC-CTR fallback). API keys are stored here.',detailKr:'암호화된 비밀 관리: /vault set <키> <값>, /vault get <키>, /vault list, /vault delete <키>. 모든 데이터는 AES-256-GCM(또는 HMAC-CTR 폴백)으로 암호화. API 키가 여기에 저장됩니다.'},
      {cmd:'/capsule',en:'Time capsule messages',kr:'타임캡슐 메시지',detailEn:'Write a message to your future self: "/capsule 7d Remember to review this code". The message will be delivered after the specified time. Supports: Nd (days), Nw (weeks), Nm (months).',detailKr:'미래의 나에게 메시지 작성: "/capsule 7d 이 코드 리뷰하기". 지정 시간 후 메시지가 전달됩니다. 지원: Nd(일), Nw(주), Nm(월).'},
      {cmd:'/deadman',en:'Dead man\'s switch',kr:'데드맨 스위치',detailEn:'Configure automated actions if you go inactive: send emails, post messages, or run commands after N days of silence. Setup: /deadman set <days> <action>. Cancel: /deadman off.',detailKr:'비활성 시 자동 조치 설정: N일간 침묵 후 이메일 전송, 메시지 게시, 명령 실행. 설정: /deadman set <일수> <조치>. 취소: /deadman off.'},
      {cmd:'/a2a',en:'Agent-to-agent protocol',kr:'에이전트 간 프로토콜',detailEn:'Send HMAC-SHA256 signed messages between SalmAlm instances. Setup: /a2a register <name> <url> <secret>. Send: /a2a send <name> <message>. Enables multi-agent collaboration.',detailKr:'SalmAlm 인스턴스 간 HMAC-SHA256 서명된 메시지를 전송합니다. 설정: /a2a register <이름> <url> <시크릿>. 전송: /a2a send <이름> <메시지>. 멀티에이전트 협업 가능.'},
      {cmd:'/workflow',en:'Workflow engine',kr:'워크플로우 엔진',detailEn:'Create multi-step AI workflows: /workflow create <name>, /workflow add <name> <step>, /workflow run <name>. Steps can include tool calls, conditions, and loops.',detailKr:'다단계 AI 워크플로우 생성: /workflow create <이름>, /workflow add <이름> <단계>, /workflow run <이름>. 단계에 도구 호출, 조건, 루프 포함 가능.'},
      {cmd:'/mcp',en:'MCP server management',kr:'MCP 서버 관리',detailEn:'Manage Model Context Protocol servers: /mcp list, /mcp add <name> <command>, /mcp remove <name>. Connect to external tool servers following the MCP standard.',detailKr:'Model Context Protocol 서버 관리: /mcp list, /mcp add <이름> <명령>, /mcp remove <이름>. MCP 표준을 따르는 외부 도구 서버에 연결합니다.'},
      {cmd:'/subagents',en:'Sub-agent management',kr:'서브 에이전트 관리',detailEn:'Spawn and manage background AI workers: /subagents spawn <task> [--model opus], /subagents list, /subagents stop <id|#N|all>, /subagents steer <id> <message>, /subagents log <id>, /subagents info <id>, /subagents collect. Sub-agents run independently with isolated sessions, tool access, and auto-notification on completion.',detailKr:'백그라운드 AI 워커 생성 및 관리: /subagents spawn <작업> [--model opus], /subagents list, /subagents stop <id|#N|all>, /subagents steer <id> <메시지>, /subagents log <id>, /subagents info <id>, /subagents collect. 서브에이전트가 격리된 세션에서 독립 실행, 도구 사용, 완료 시 자동 알림.'},
      {cmd:'/evolve',en:'Self-evolving prompt rules',kr:'자기 진화 프롬프트 규칙',detailEn:'View and manage auto-generated prompt rules. The AI learns patterns from your conversations and creates rules (max 20, FIFO). /evolve list, /evolve clear, /evolve remove <n>.',detailKr:'자동 생성된 프롬프트 규칙을 확인하고 관리합니다. AI가 대화 패턴을 학습하여 규칙을 생성합니다 (최대 20개, FIFO). /evolve list, /evolve clear, /evolve remove <n>.'},
      {cmd:'/mood',en:'Mood-aware mode',kr:'감정 인식 모드',detailEn:'Toggle emotional state detection. When active, the AI analyzes your message tone and adapts its response style — more empathetic when stressed, more energetic when excited.',detailKr:'감정 상태 감지를 토글합니다. 활성화 시 AI가 메시지 톤을 분석하여 응답 스타일을 조정합니다 — 스트레스 시 더 공감적, 흥분 시 더 에너지 넘치게.'},
      {cmd:'/split',en:'A/B split response comparison',kr:'A/B 분할 응답 비교',detailEn:'Get two different model responses to the same question side-by-side. Example: "/split What\'s the best programming language?" Useful for comparing perspectives.',detailKr:'같은 질문에 대해 두 모델의 응답을 나란히 비교합니다. 예: "/split 최고의 프로그래밍 언어는?" 다양한 관점 비교에 유용합니다.'},
      {cmd:'/cron',en:'Cron job management',kr:'크론 작업 관리',detailEn:'Schedule recurring AI tasks: /cron add "0 9 * * *" "Check my email", /cron list, /cron delete <id>. Uses standard cron syntax. Tasks run in isolated sessions.',detailKr:'반복 AI 작업 예약: /cron add "0 9 * * *" "이메일 확인", /cron list, /cron delete <id>. 표준 크론 문법 사용. 작업은 격리된 세션에서 실행.'},
      {cmd:'/bash <cmd>',en:'Run shell command',kr:'셸 명령 실행',detailEn:'Execute a shell command directly. Output is captured and displayed. Shell operators (|, >, &&) require SALMALM_ALLOW_SHELL=1 env var. Interpreters (python, node) are blocked — use python_eval tool instead. Dangerous flags are blocked per-command: find -exec, awk system(), tar --to-command, git clone/push, sed -i, xargs -I.',detailKr:'셸 명령을 직접 실행합니다. 출력이 캡처되어 표시됩니다. 셸 연산자(|, >, &&)는 SALMALM_ALLOW_SHELL=1 환경변수 필요. 인터프리터(python, node)는 차단 — python_eval 도구를 대신 사용. 명령별 위험 플래그 차단: find -exec, awk system(), tar --to-command, git clone/push, sed -i, xargs -I.'},
      {cmd:'/screen',en:'Browser control',kr:'브라우저 제어',detailEn:'Browser automation via Playwright: /screen open <url>, /screen click <selector>, /screen type <text>. Setup: pip install salmalm[browser] && playwright install chromium',detailKr:'Playwright 브라우저 자동화: /screen open <url>, /screen click <선택자>, /screen type <텍스트>. 설정: pip install salmalm[browser] && playwright install chromium'},
      {cmd:'/life',en:'Life dashboard',kr:'라이프 대시보드',detailEn:'Unified personal dashboard showing: expense summary, habit streaks, upcoming reminders, mood trends, and routine completion. All data from /expense, /routine, /mood, /remind.',detailKr:'통합 개인 대시보드: 지출 요약, 습관 연속 기록, 예정 리마인더, 감정 추이, 루틴 완료율. /expense, /routine, /mood, /remind의 모든 데이터.'},
      {cmd:'/oauth',en:'OAuth setup',kr:'OAuth 설정',detailEn:'Configure OAuth2 for Gmail and Google Calendar integration. Guides you through the Google Cloud Console setup and stores tokens securely in the vault.',detailKr:'Gmail과 Google 캘린더 연동을 위한 OAuth2 설정. Google Cloud Console 설정 과정을 안내하고 토큰을 금고에 안전하게 저장합니다.'},
      {cmd:'/queue',en:'Message queue management (5 modes)',kr:'메시지 큐 관리 (5가지 모드)',detailEn:'Advanced message processing: /queue batch (collect then process), /queue priority (urgent first), /queue schedule (delayed send), /queue pipeline (chain tools), /queue broadcast (multi-channel).',detailKr:'고급 메시지 처리: /queue batch (수집 후 처리), /queue priority (긴급 우선), /queue schedule (지연 전송), /queue pipeline (도구 체인), /queue broadcast (멀티채널).'},
      {cmd:'/debug',en:'Real-time system diagnostics',kr:'실시간 시스템 진단',detailEn:'Shows 5 diagnostic cards: system info, active sessions, model status, tool usage, and error log. Auto-refreshes.',detailKr:'5개 진단 카드 표시: 시스템 정보, 활성 세션, 모델 상태, 도구 사용량, 에러 로그. 자동 새로고침.'},
      {cmd:'/security',en:'Security status overview',kr:'보안 상태 요약',detailEn:'Shows vault status, bind address, sandbox level, exec restrictions, active tokens, and login lockout state.',detailKr:'금고 상태, 바인드 주소, 샌드박스 레벨, exec 제한, 활성 토큰, 로그인 잠금 상태를 표시합니다.'},
      {cmd:'/plugins',en:'Plugin management',kr:'플러그인 관리',detailEn:'List, enable, disable, or reload plugins. Plugins are auto-discovered from the plugins/ directory.',detailKr:'플러그인 목록 확인, 활성화, 비활성화, 리로드. plugins/ 디렉토리에서 자동 발견됩니다.'},
      {cmd:'/export',en:'Export session data',kr:'세션 데이터 내보내기',detailEn:'Export current session as JSON or Markdown. Useful for backup or sharing conversations.',detailKr:'현재 세션을 JSON 또는 Markdown으로 내보냅니다. 백업이나 대화 공유에 유용합니다.'},
      {cmd:'/config',en:'Configuration management',kr:'설정 관리',detailEn:'View or modify runtime configuration. Shows current env vars, bind address, port, model, and security settings.',detailKr:'런타임 설정을 확인하거나 변경합니다. 현재 환경변수, 바인드 주소, 포트, 모델, 보안 설정을 표시합니다.'},
      {cmd:'/new',en:'Start new session',kr:'새 세션 시작',detailEn:'Creates a fresh conversation session. Previous session is saved and accessible from the Sessions panel.',detailKr:'새 대화 세션을 생성합니다. 이전 세션은 저장되어 세션 패널에서 접근할 수 있습니다.'},
      {cmd:'/clear',en:'Clear current session',kr:'현재 세션 초기화',detailEn:'Removes all messages from the current session. The session itself is preserved but emptied.',detailKr:'현재 세션의 모든 메시지를 제거합니다. 세션 자체는 유지되지만 비워집니다.'},
      {cmd:'/tools',en:'List available tools',kr:'사용 가능한 도구 목록',detailEn:'Shows all 66 built-in tools with descriptions. Includes dynamic and plugin tools if registered.',detailKr:'66개 내장 도구의 전체 목록과 설명을 표시합니다. 동적 등록/플러그인 도구도 포함됩니다.'},
      {cmd:'/health',en:'System health check',kr:'시스템 건강 점검',detailEn:'Quick overview of system health: CPU, memory, disk, uptime, and active connections.',detailKr:'시스템 건강 요약: CPU, 메모리, 디스크, 가동시간, 활성 연결.'},
      {cmd:'/prune',en:'Prune context manually',kr:'컨텍스트 수동 정리',detailEn:'Manually triggers context pruning to reduce token usage. More aggressive than /compact.',detailKr:'토큰 사용량을 줄이기 위해 컨텍스트 정리를 수동 실행합니다. /compact보다 적극적입니다.'},
      {cmd:'/approve',en:'Approve pending exec commands',kr:'대기 중인 실행 명령 승인',detailEn:'Review and approve or reject pending shell commands that require user confirmation (elevated commands).',detailKr:'사용자 확인이 필요한 대기 중인 셸 명령(상승된 명령)을 검토하고 승인 또는 거부합니다.'},
      {cmd:'/whoami',en:'Current user info',kr:'현재 사용자 정보',detailEn:'Shows your username, role, session ID, and authentication status.',detailKr:'사용자 이름, 역할, 세션 ID, 인증 상태를 표시합니다.'},
    ]},
    {catKr:'단축키',catEn:'Keyboard Shortcuts',items:[
      {cmd:'Enter',en:'Send message',kr:'메시지 전송',detailEn:'Sends the current message in the input field.',detailKr:'입력 필드의 현재 메시지를 전송합니다.'},
      {cmd:'Shift+Enter',en:'New line',kr:'줄바꿈',detailEn:'Inserts a line break without sending the message.',detailKr:'메시지를 전송하지 않고 줄바꿈을 삽입합니다.'},
      {cmd:'Ctrl+K',en:'Search conversations',kr:'대화 검색',detailEn:'Opens the search modal to find messages across all sessions by keyword.',detailKr:'모든 세션에서 키워드로 메시지를 찾는 검색 모달을 엽니다.'},
      {cmd:'Ctrl+/',en:'Command palette',kr:'명령 팔레트',detailEn:'Opens the command palette for quick access to any slash command without typing it.',detailKr:'슬래시 커맨드에 빠르게 접근할 수 있는 명령 팔레트를 엽니다.'},
      {cmd:'Ctrl+V',en:'Paste image/file',kr:'이미지/파일 붙여넣기',detailEn:'Paste an image from clipboard directly into the chat. Supports PNG, JPEG, GIF, WebP. Images are sent to vision-capable models for analysis.',detailKr:'클립보드의 이미지를 채팅에 직접 붙여넣기. PNG, JPEG, GIF, WebP 지원. 이미지는 비전 모델에 전송되어 분석됩니다.'},
      {cmd:'Esc',en:'Close modal / Back to chat',kr:'모달 닫기 / 채팅으로 돌아가기',detailEn:'Closes any open modal (search, settings, command palette) and returns focus to the chat input.',detailKr:'열린 모달(검색, 설정, 명령 팔레트)을 닫고 채팅 입력에 포커스를 돌려줍니다.'},
    ]},
    {catKr:'고유 기능',catEn:'Unique Features',items:[
      {cmd:'Self-Evolving Prompt',en:'AI auto-generates prompt rules from conversations (max 20)',kr:'대화에서 프롬프트 규칙 자동 생성 (최대 20개)',detailEn:'The AI observes your preferences, corrections, and patterns over time. It automatically creates system prompt rules (max 20, oldest removed first) that make responses better aligned with your style. View with /evolve list.',detailKr:'AI가 시간이 지나며 당신의 선호, 수정, 패턴을 관찰합니다. 응답을 당신의 스타일에 맞추는 시스템 프롬프트 규칙을 자동 생성합니다 (최대 20개, 오래된 것부터 제거). /evolve list로 확인.'},
      {cmd:'Dead Man\'s Switch',en:'Automated actions if owner goes inactive',kr:'소유자 비활성 시 자동 조치',detailEn:'If you don\'t interact with SalmAlm for a configured number of days, it automatically executes pre-set actions: send notification emails, post status updates, or run cleanup scripts. A safety net for digital life.',detailKr:'설정된 일수 동안 SalmAlm과 상호작용하지 않으면 미리 설정된 조치를 자동 실행합니다: 알림 이메일 전송, 상태 업데이트 게시, 정리 스크립트 실행. 디지털 생활의 안전망.'},
      {cmd:'Shadow Mode',en:'AI silently observes without responding',kr:'AI가 응답 없이 조용히 관찰',detailEn:'In Shadow Mode, the AI reads all your messages but doesn\'t respond. Instead, it builds a profile of your communication style — word choice, tone, emoji usage, typical responses. When you\'re away, it can reply as you.',detailKr:'섀도우 모드에서 AI는 모든 메시지를 읽지만 응답하지 않습니다. 대신 소통 스타일 프로필을 구축합니다 — 단어 선택, 톤, 이모지 사용, 전형적인 응답. 부재 시 대리 응답 가능.'},
      {cmd:'Life Dashboard',en:'Unified view of health, finance, habits',kr:'건강, 재정, 습관 통합 뷰',detailEn:'A single /life command shows everything: expense totals and trends, habit completion streaks, upcoming events, mood history, and routine progress. Your personal life at a glance.',detailKr:'/life 하나로 모든 것을 표시: 지출 합계와 추이, 습관 완료 연속 기록, 예정 이벤트, 감정 이력, 루틴 진행률. 한눈에 보는 당신의 삶.'},
      {cmd:'Mood-Aware',en:'Emotional state detection and adaptation',kr:'감정 상태 감지 및 적응',detailEn:'Uses NLP signals (word choice, punctuation, message length) to estimate your current emotional state. Adjusts response tone: more gentle when you seem frustrated, more celebratory when excited, more focused when stressed.',detailKr:'NLP 신호(단어 선택, 구두점, 메시지 길이)로 현재 감정 상태를 추정합니다. 응답 톤 조정: 좌절감 감지 시 더 부드럽게, 흥분 시 더 축하하는 톤, 스트레스 시 더 집중적으로.'},
      {cmd:'Encrypted Vault',en:'AES-256-GCM encrypted secret storage',kr:'AES-256-GCM 암호화 비밀 저장소',detailEn:'All sensitive data (API keys, tokens, personal notes) is encrypted with AES-256-GCM using a PBKDF2-derived key (200K iterations). Without the cryptography package, falls back to HMAC-CTR. Data is useless without your password.',detailKr:'모든 민감 데이터(API 키, 토큰, 개인 메모)가 PBKDF2 유도 키(200K 반복)를 사용한 AES-256-GCM으로 암호화됩니다. cryptography 패키지 없으면 HMAC-CTR로 폴백. 비밀번호 없이는 데이터를 읽을 수 없습니다.'},
      {cmd:'A/B Split Response',en:'Compare two model responses side-by-side',kr:'두 모델 응답을 나란히 비교',detailEn:'Ask one question, get two answers from different models simultaneously. Perfect for comparing reasoning approaches, writing styles, or checking accuracy. Models are selected automatically or you can specify them.',detailKr:'하나의 질문으로 두 모델의 답변을 동시에 받습니다. 추론 방식, 작문 스타일 비교나 정확도 확인에 완벽합니다. 모델은 자동 선택되거나 직접 지정 가능.'},
      {cmd:'Time Capsule',en:'Schedule messages to future self',kr:'미래의 나에게 메시지 예약',detailEn:'Write a message and set a delivery date. The message is stored encrypted and delivered when the time comes — as a chat notification. Great for goals, reflections, or reminders to future-you.',detailKr:'메시지를 작성하고 전달 날짜를 설정합니다. 메시지는 암호화되어 저장되고 시간이 되면 채팅 알림으로 전달됩니다. 목표, 성찰, 미래의 나에게 보내는 리마인더에 적합.'},
      {cmd:'Thought Stream',en:'Private journaling with mood tracking',kr:'감정 추적 포함 개인 일기',detailEn:'A private journaling timeline. Entries are tagged with timestamps, mood scores, and hashtags. Search by #tag or date range. All entries are stored locally and never sent to AI providers.',detailKr:'개인 일기 타임라인. 항목에 타임스탬프, 감정 점수, 해시태그가 태그됩니다. #태그 또는 날짜 범위로 검색. 모든 항목은 로컬에 저장되며 AI 프로바이더에 전송되지 않습니다.'},
      {cmd:'Agent-to-Agent',en:'HMAC-signed inter-agent communication',kr:'HMAC 서명된 에이전트 간 통신',detailEn:'Connect multiple SalmAlm instances for collaboration. Messages are authenticated with HMAC-SHA256 to prevent tampering. Use cases: home server ↔ work server, personal ↔ team assistant.',detailKr:'여러 SalmAlm 인스턴스를 연결하여 협업합니다. 메시지는 HMAC-SHA256으로 인증되어 변조를 방지합니다. 활용: 집 서버 ↔ 직장 서버, 개인 ↔ 팀 어시스턴트.'},
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
      var sysRows=[[kr?'Python':'Python',d.python.split(' ')[0]],[kr?'플랫폼':'Platform',d.platform],[kr?'PID':'PID',d.pid],[kr?'메모리':'Memory',d.memory_mb+'MB'],[kr?'GC (0/1/2)':'GC (0/1/2)',d.gc.gen0+'/'+d.gc.gen1+'/'+d.gc.gen2]];
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
