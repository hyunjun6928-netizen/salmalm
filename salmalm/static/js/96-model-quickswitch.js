/* --- Model Badge Quick-Switch ---
 * Click model badge → popup with recently used models + "All models" link
 * Tracks last 3 used models in localStorage
 */
(function(){
  var _KEY = 'salm_recent_models';
  var _MAX = 3;
  var _popup = null;

  /* ── localStorage helpers ── */
  function _getRecent() {
    try { return JSON.parse(localStorage.getItem(_KEY) || '[]'); }
    catch(e) { return []; }
  }

  function _pushRecent(model) {
    if (!model || model === 'auto routing' || model.startsWith('Auto →') || model === 'auto') return;
    // Normalize: strip provider prefix for storage key but store full model name
    var recent = _getRecent().filter(function(m) { return m !== model; });
    recent.unshift(model);
    try { localStorage.setItem(_KEY, JSON.stringify(recent.slice(0, _MAX))); }
    catch(e) {}
  }

  /* ── Toast notification ── */
  function _toast(msg) {
    var el = document.createElement('div');
    el.style.cssText = [
      'position:fixed',
      'bottom:90px',
      'left:50%',
      'transform:translateX(-50%)',
      'background:var(--panel,#222)',
      'border:1px solid var(--border,#333)',
      'border-radius:8px',
      'padding:8px 18px',
      'font-size:13px',
      'z-index:10001',
      'pointer-events:none',
      'color:var(--text,#fff)',
      'transition:opacity 0.3s',
      'white-space:nowrap',
    ].join(';');
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(function() {
      el.style.opacity = '0';
      setTimeout(function() { el.remove(); }, 320);
    }, 1600);
  }

  /* ── Model switch API call ── */
  function _switchModel(model, badge) {
    var hdr = {
      'Content-Type': 'application/json',
      'X-Session-Token': (typeof _tok !== 'undefined' ? _tok : ''),
    };
    if (typeof _currentSession !== 'undefined' && _currentSession) {
      hdr['X-Session-Id'] = _currentSession;
    }
    fetch('/api/model/switch', {
      method: 'POST',
      headers: hdr,
      body: JSON.stringify({model: model}),
    })
    .then(function(r) { return r.json(); })
    .then(function() {
      var short = model.split('/').pop();
      if (badge) badge.textContent = short;
      _pushRecent(short);
      _toast('✅ ' + short);
      _hide();
    })
    .catch(function(e) {
      console.warn('[QuickSwitch] model switch failed:', e);
      _toast('❌ Failed');
    });
  }

  /* ── Open model router tab ── */
  function _openModelRouter() {
    _hide();
    // Try clicking the model-router settings tab
    var mrTab = document.querySelector('[data-settings-tab="model-router"]');
    if (mrTab) {
      // Ensure settings panel is visible first
      var settingsPanel = document.getElementById('settings');
      if (settingsPanel && settingsPanel.style.display === 'none') {
        var settingsBtn = document.getElementById('settings-btn') ||
                          document.querySelector('[data-action="openSettings"]') ||
                          document.querySelector('[onclick*="showSettings"]');
        if (settingsBtn) settingsBtn.click();
        setTimeout(function() { mrTab.click(); }, 120);
      } else {
        mrTab.click();
      }
    } else {
      // Fallback: open settings
      if (typeof window.showSettings === 'function') window.showSettings();
    }
  }

  /* ── Popup UI ── */
  function _hide() {
    if (_popup) { _popup.remove(); _popup = null; }
  }

  function _show(badge) {
    _hide();
    var recent = _getRecent();

    var popup = document.createElement('div');
    popup.id = 'model-qs-popup';
    popup.style.cssText = [
      'position:absolute',
      'z-index:9998',
      'background:var(--panel,#1e1e1e)',
      'border:1px solid var(--border,#333)',
      'border-radius:10px',
      'box-shadow:0 4px 24px rgba(0,0,0,0.5)',
      'padding:6px',
      'min-width:210px',
      'top:calc(100% + 6px)',
      'right:0',
    ].join(';');

    var kr = (typeof _lang !== 'undefined' && _lang === 'ko');

    /* Header */
    var hdr = document.createElement('div');
    hdr.style.cssText = 'font-size:10px;color:var(--text2,#888);padding:4px 8px 6px;text-transform:uppercase;letter-spacing:0.06em;user-select:none';
    hdr.textContent = kr ? '최근 모델' : 'Recent Models';
    popup.appendChild(hdr);

    if (recent.length === 0) {
      var empty = document.createElement('div');
      empty.style.cssText = 'font-size:12px;color:var(--text2,#888);padding:6px 10px';
      empty.textContent = kr ? '아직 사용한 모델이 없습니다' : 'No recent models yet';
      popup.appendChild(empty);
    } else {
      recent.forEach(function(model) {
        var row = document.createElement('div');
        row.style.cssText = 'display:flex;align-items:center;gap:8px;padding:8px 10px;border-radius:7px;cursor:pointer;font-size:13px;color:var(--text,#fff);transition:background 0.08s';
        var dot = document.createElement('span');
        dot.style.cssText = 'width:7px;height:7px;border-radius:50%;background:var(--accent,#7c9fff);flex-shrink:0';
        var name = document.createElement('span');
        name.style.cssText = 'flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap';
        name.textContent = model.split('/').pop();
        name.title = model;
        row.appendChild(dot);
        row.appendChild(name);
        row.addEventListener('mouseenter', function() { row.style.background = 'var(--accent-dim,rgba(99,140,255,0.18))'; });
        row.addEventListener('mouseleave', function() { row.style.background = ''; });
        row.addEventListener('mousedown', function(e) { e.preventDefault(); _switchModel(model, badge); });
        popup.appendChild(row);
      });
    }

    /* Divider */
    var sep = document.createElement('div');
    sep.style.cssText = 'height:1px;background:var(--border,#333);margin:4px 0';
    popup.appendChild(sep);

    /* "All models" button */
    var more = document.createElement('div');
    more.style.cssText = 'display:flex;align-items:center;gap:8px;padding:7px 10px;border-radius:7px;cursor:pointer;font-size:12px;color:var(--text2,#888);transition:background 0.08s';
    more.innerHTML = '⚙️&nbsp;' + (kr ? '모든 모델 보기' : 'All models…');
    more.addEventListener('mouseenter', function() { more.style.background = 'var(--accent-dim,rgba(99,140,255,0.18))'; });
    more.addEventListener('mouseleave', function() { more.style.background = ''; });
    more.addEventListener('mousedown', function(e) { e.preventDefault(); _openModelRouter(); });
    popup.appendChild(more);

    /* Position relative to badge */
    badge.style.position = badge.style.position || 'relative';
    badge.appendChild(popup);
    _popup = popup;
  }

  /* ── Bootstrap ── */
  document.addEventListener('DOMContentLoaded', function() {
    var badge = document.getElementById('model-badge');
    if (!badge) return;

    badge.style.cursor = 'pointer';
    badge.title = (typeof _lang !== 'undefined' && _lang === 'ko')
      ? '클릭: 최근 모델 빠른 전환'
      : 'Click: recent model quick-switch';

    /* Click: toggle popup */
    badge.addEventListener('click', function(e) {
      e.stopPropagation();
      if (_popup) { _hide(); return; }
      _show(badge);
    });

    /* Click outside → close */
    document.addEventListener('click', function(e) {
      if (_popup && !badge.contains(e.target)) { _hide(); }
    });

    /* Track model changes via MutationObserver → auto-push to recent */
    var obs = new MutationObserver(function() {
      var text = badge.textContent.trim();
      // Push the new model if it looks like a real model name
      if (text && text !== 'auto routing' && !text.startsWith('Auto →') && text.length > 2) {
        _pushRecent(text);
      }
    });
    obs.observe(badge, {childList: true, subtree: true, characterData: true});
  });
})();
