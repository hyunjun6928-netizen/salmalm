/* --- Slash Command Inline Autocomplete ---
 * Discord-style: type "/" as first char → dropdown with matching commands
 * Arrow keys: navigate | Enter/Tab: select | Escape: close
 */
(function(){
  var _CMDS = [
    {cmd:'/help',       en:'Show all commands',             kr:'모든 명령어 표시'},
    {cmd:'/model',      en:'Switch model',                  kr:'모델 변경'},
    {cmd:'/new',        en:'New session',                   kr:'새 세션'},
    {cmd:'/clear',      en:'Clear session',                 kr:'세션 초기화'},
    {cmd:'/reset',      en:'Reset conversation',            kr:'대화 리셋'},
    {cmd:'/status',     en:'Server status',                 kr:'서버 상태'},
    {cmd:'/usage',      en:'Usage stats',                   kr:'사용량 통계'},
    {cmd:'/compact',    en:'Compact context',               kr:'컨텍스트 압축'},
    {cmd:'/think',      en:'Thinking level (off|low|med|high)', kr:'사고 단계 설정'},
    {cmd:'/verbose',    en:'Verbose mode (on|off)',         kr:'상세 출력'},
    {cmd:'/reasoning',  en:'Show reasoning (on|off|stream)',kr:'추론 표시'},
    {cmd:'/vault',      en:'Vault operations',              kr:'보안 저장소'},
    {cmd:'/bash',       en:'Execute shell command',         kr:'셸 명령 실행'},
    {cmd:'/subagents',  en:'Sub-agent management',          kr:'서브 에이전트'},
    {cmd:'/skill',      en:'Run skill',                     kr:'스킬 실행'},
    {cmd:'/workflow',   en:'Workflow management',           kr:'워크플로우'},
    {cmd:'/screen',     en:'Screen capture & analysis',     kr:'화면 캡처'},
    {cmd:'/mcp',        en:'MCP marketplace',               kr:'MCP 마켓플레이스'},
    {cmd:'/persona',    en:'Persona management',            kr:'페르소나 설정'},
    {cmd:'/branch',     en:'Branch conversation',           kr:'대화 분기'},
    {cmd:'/rollback',   en:'Rollback to previous state',    kr:'이전 상태로'},
    {cmd:'/split',      en:'Split response',                kr:'응답 분할'},
    {cmd:'/capsule',    en:'Time capsule',                  kr:'타임캡슐'},
    {cmd:'/life',       en:'Life dashboard',                kr:'생활 대시보드'},
    {cmd:'/evolve',     en:'Self-evolution',                kr:'자체 진화'},
    {cmd:'/whoami',     en:'Current user ID',               kr:'현재 사용자'},
    {cmd:'/commands',   en:'Full command list',             kr:'전체 명령어 목록'},
    {cmd:'/stop',       en:'Stop execution',                kr:'실행 중지'},
    {cmd:'/setup',      en:'Re-run setup wizard',           kr:'설정 마법사'},
    {cmd:'/queue',      en:'Queue status',                  kr:'대기열 상태'},
    {cmd:'/shadow',     en:'Shadow mode',                   kr:'그림자 모드'},
    {cmd:'/context',    en:'Show context info',             kr:'컨텍스트 정보'},
    {cmd:'/whoami',     en:'Who am I',                      kr:'나는 누구'},
    {cmd:'/a2a',        en:'Agent-to-agent',                kr:'에이전트 간 연결'},
    {cmd:'/mood',       en:'Mood info',                     kr:'무드 정보'},
  ];

  var _popup = null;
  var _activeIdx = 0;
  var _visibleCmds = [];

  function _show(matches) {
    _hide();
    if (!matches.length) return;
    _visibleCmds = matches;
    _activeIdx = 0;

    var ia = document.getElementById('input-area');
    if (!ia) return;

    var popup = document.createElement('div');
    popup.id = 'slash-ac';
    popup.style.cssText = [
      'position:absolute',
      'z-index:9999',
      'background:var(--panel,#1e1e1e)',
      'border:1px solid var(--border,#333)',
      'border-radius:10px',
      'box-shadow:0 -4px 24px rgba(0,0,0,0.45)',
      'max-height:280px',
      'overflow-y:auto',
      'min-width:300px',
      'max-width:480px',
      'bottom:calc(100% + 8px)',
      'left:0',
      'padding:4px',
    ].join(';');

    matches.forEach(function(m, i) {
      var row = document.createElement('div');
      row.className = 'slash-ac-row';
      row.dataset.i = i;
      row.style.cssText = 'display:flex;align-items:baseline;gap:10px;padding:8px 12px;cursor:pointer;border-radius:7px;transition:background 0.08s';
      if (i === 0) row.style.background = 'var(--accent-dim,rgba(99,140,255,0.18))';

      var cEl = document.createElement('span');
      cEl.style.cssText = 'font-family:monospace;font-size:13px;font-weight:600;color:var(--accent2,#82aaff);min-width:100px;flex-shrink:0';
      cEl.textContent = m.cmd;

      var dEl = document.createElement('span');
      dEl.style.cssText = 'font-size:12px;color:var(--text2,#888);flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis';
      dEl.textContent = (typeof _lang !== 'undefined' && _lang === 'ko') ? m.kr : m.en;

      row.appendChild(cEl);
      row.appendChild(dEl);

      row.addEventListener('mouseenter', function() { _setActive(i); });
      row.addEventListener('mousedown', function(e) { e.preventDefault(); _select(m.cmd); });
      popup.appendChild(row);
    });

    ia.style.position = ia.style.position || 'relative';
    ia.appendChild(popup);
    _popup = popup;
  }

  function _setActive(idx) {
    if (!_popup) return;
    var rows = _popup.querySelectorAll('.slash-ac-row');
    rows.forEach(function(r, i) {
      r.style.background = (i === idx) ? 'var(--accent-dim,rgba(99,140,255,0.18))' : '';
    });
    _activeIdx = idx;
  }

  function _hide() {
    if (_popup) { _popup.remove(); _popup = null; }
    _visibleCmds = [];
    _activeIdx = 0;
  }

  function _select(cmd) {
    var inp = document.getElementById('input');
    if (!inp) return;
    inp.value = cmd + ' ';
    inp.focus();
    // Move cursor to end
    inp.selectionStart = inp.selectionEnd = inp.value.length;
    _hide();
    // Trigger height resize
    inp.dispatchEvent(new Event('input'));
  }

  function _update(val) {
    // Only show when "/" is the first (non-whitespace) character
    var trimmed = val.trimStart();
    if (!trimmed.startsWith('/')) { _hide(); return; }
    var q = trimmed.slice(1).toLowerCase();
    // Hide once user typed a space after the command (command already entered)
    if (q.includes(' ')) { _hide(); return; }
    var matches = _CMDS.filter(function(c) {
      return q === '' || c.cmd.toLowerCase().startsWith('/' + q);
    });
    // Deduplicate by cmd
    var seen = {};
    matches = matches.filter(function(m) {
      if (seen[m.cmd]) return false;
      seen[m.cmd] = true;
      return true;
    });
    _show(matches.slice(0, 9));
  }

  document.addEventListener('DOMContentLoaded', function() {
    var inp = document.getElementById('input');
    if (!inp) return;

    inp.addEventListener('input', function() {
      _update(inp.value);
    });

    inp.addEventListener('keydown', function(e) {
      if (!_popup) return;
      var rows = _popup.querySelectorAll('.slash-ac-row');
      var len = rows.length;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        _setActive(Math.min(_activeIdx + 1, len - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        _setActive(Math.max(_activeIdx - 1, 0));
      } else if (e.key === 'Tab') {
        // Tab: complete without sending
        if (len > 0) {
          e.preventDefault();
          _select(_visibleCmds[_activeIdx] ? _visibleCmds[_activeIdx].cmd : _visibleCmds[0].cmd);
        }
      } else if (e.key === 'Enter' && !e.shiftKey) {
        // Enter: only intercept if popup is open AND exactly one match
        // (if multiple matches, Enter would normally send — let it)
        if (len === 1) {
          e.preventDefault();
          e.stopImmediatePropagation();
          _select(_visibleCmds[0].cmd);
        } else if (_activeIdx > 0) {
          // User explicitly navigated → select
          e.preventDefault();
          e.stopImmediatePropagation();
          _select(_visibleCmds[_activeIdx].cmd);
        } else {
          _hide();
        }
      } else if (e.key === 'Escape') {
        _hide();
      }
    }, true); // capture phase so we beat the send handler

    inp.addEventListener('blur', function() {
      // Delay to allow mousedown on popup rows
      setTimeout(_hide, 160);
    });
  });
})();
