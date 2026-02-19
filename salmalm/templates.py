"""SalmAlm HTML templates — separated for readability."""
from .constants import VERSION

WEB_HTML = '''<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SalmAlm — Personal AI Gateway</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#0b0d14;--bg2:#12141f;--bg3:#1a1d2b;--border:#252838;--text:#d4d4dc;--text2:#8889a0;
--accent:#7c5cfc;--accent2:#9b7dff;--accent-dim:rgba(124,92,252,0.12);--green:#34d399;--red:#f87171;
--user-bg:linear-gradient(135deg,#6d5cfc,#8b5cf6);--bot-bg:#161928;--yellow:#fbbf24;--blue:#60a5fa}
[data-theme="light"]{--bg:#f8f9fc;--bg2:#ffffff;--bg3:#f0f1f5;--border:#e2e4ea;--text:#1e293b;--text2:#64748b;
--accent:#6d5cfc;--accent2:#7c5cfc;--accent-dim:rgba(109,92,252,0.08);--green:#059669;--red:#dc2626;
--user-bg:linear-gradient(135deg,#6d5cfc,#8b5cf6);--bot-bg:#f7f7fb;--yellow:#d97706;--blue:#2563eb}
*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%;font-family:'Inter',system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--text)}
body{display:grid;grid-template-rows:auto 1fr auto;grid-template-columns:260px 1fr;grid-template-areas:"side head" "side chat" "side input"}

/* SIDEBAR */
#sidebar{grid-area:side;background:var(--bg2);border-right:1px solid var(--border);display:flex;flex-direction:column;padding:0}
.side-header{padding:20px;border-bottom:1px solid var(--border)}
.side-header h1{font-size:20px;font-weight:600;display:flex;align-items:center;gap:8px}
.side-header h1 .icon{font-size:24px}
.side-header .tagline{font-size:11px;color:var(--text2);margin-top:4px;letter-spacing:0.5px;text-transform:uppercase}
.side-nav{flex:1;padding:12px;overflow-y:auto}
.nav-section{font-size:10px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;padding:12px 8px 6px;font-weight:600}
.nav-item{padding:10px 12px;border-radius:8px;cursor:pointer;font-size:13px;color:var(--text2);display:flex;align-items:center;gap:10px;transition:all 0.15s}
.nav-item:hover{background:var(--accent-dim);color:var(--text)}
.nav-item.active{background:var(--accent-dim);color:var(--accent2);font-weight:500}
.nav-item .badge{margin-left:auto;background:var(--accent);color:#fff;font-size:10px;padding:2px 7px;border-radius:10px;font-weight:600}
.side-footer{padding:16px;border-top:1px solid var(--border);font-size:11px;color:var(--text2)}
.side-footer .status{display:flex;align-items:center;gap:6px;margin-bottom:6px}
.side-footer .dot{width:8px;height:8px;border-radius:50%;background:var(--green);display:inline-block}

/* HEADER */
#header{grid-area:head;padding:14px 24px;background:var(--bg2);border-bottom:1px solid var(--border);display:flex;align-items:center;gap:16px}
#header .title{font-size:15px;font-weight:500}
#header .model-badge{font-size:11px;padding:4px 10px;border-radius:6px;background:var(--accent-dim);color:var(--accent2);font-weight:500}
#header .spacer{flex:1}
#header .cost{font-size:12px;color:var(--text2)}
#header .cost b{color:var(--green);font-weight:600}
#new-chat-btn{background:var(--accent-dim);color:var(--accent2);border:none;padding:6px 14px;border-radius:8px;font-size:12px;cursor:pointer;font-weight:500;transition:all 0.15s}
#new-chat-btn:hover{background:var(--accent);color:#fff}

/* CHAT */
#chat{grid-area:chat;overflow-y:auto;padding:24px;display:flex;flex-direction:column;gap:16px;scroll-behavior:smooth}
#chat::-webkit-scrollbar{width:6px}
#chat::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
.msg-row{display:flex;gap:12px;max-width:90%;animation:fadeIn 0.2s ease}
.msg-row.user{align-self:flex-end;flex-direction:row-reverse}
.msg-row.assistant{align-self:flex-start}
.avatar{width:32px;height:32px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0}
.msg-row.user .avatar{background:var(--user-bg)}
.msg-row.assistant .avatar{background:var(--bg3);border:1px solid var(--border)}
.bubble{padding:12px 16px;border-radius:16px;font-size:14px;line-height:1.7;white-space:pre-wrap;word-break:break-word}
.msg-row.user .bubble{background:var(--user-bg);color:#fff;border-bottom-right-radius:4px}
.msg-row.assistant .bubble{background:var(--bot-bg);border:1px solid var(--border);border-bottom-left-radius:4px}
.bubble code{background:rgba(255,255,255,0.08);padding:2px 6px;border-radius:4px;font-size:13px;font-family:'SF Mono',monospace}
.bubble pre{background:rgba(0,0,0,0.3);padding:12px;border-radius:8px;overflow-x:auto;margin:8px 0;font-size:13px;border:1px solid var(--border)}
.bubble pre code{background:none;padding:0;font-size:13px}
/* Syntax highlight keywords */
.bubble pre .kw{color:#c792ea}.bubble pre .str{color:#c3e88d}.bubble pre .num{color:#f78c6c}.bubble pre .cmt{color:#546e7a;font-style:italic}
/* Drag highlight */
.input-area.drag-over{border:2px dashed var(--accent);background:var(--accent-dim);transition:all 0.2s}
/* Scroll to bottom button */
#scroll-bottom{position:fixed;bottom:100px;right:24px;width:40px;height:40px;border-radius:50%;background:var(--bg3);border:1px solid var(--border);color:var(--text2);font-size:18px;cursor:pointer;display:none;align-items:center;justify-content:center;z-index:50;transition:opacity 0.2s}
#scroll-bottom:hover{background:var(--accent-dim);color:var(--accent2)}
/* Message actions */
.msg-actions{opacity:0;transition:opacity 0.15s;display:inline-flex;gap:4px;margin-left:8px}
.msg-row:hover .msg-actions{opacity:1}
.msg-actions span{cursor:pointer;font-size:12px;padding:2px 4px;border-radius:4px}
.msg-actions span:hover{background:var(--accent-dim)}
.bubble pre code{background:none;padding:0}
.meta{font-size:11px;color:var(--text2);margin-top:4px;display:flex;gap:8px;align-items:center}
.msg-row.user .meta{justify-content:flex-end}
.typing-indicator{display:flex;gap:4px;padding:8px 0}
.typing-indicator span{width:7px;height:7px;border-radius:50%;background:var(--text2);animation:bounce 1.4s infinite ease-in-out}
.typing-indicator span:nth-child(2){animation-delay:0.2s}
.typing-indicator span:nth-child(3){animation-delay:0.4s}
@keyframes bounce{0%,80%,100%{transform:scale(0.6)}40%{transform:scale(1)}}
@keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}

/* INPUT */
#input-area{grid-area:input;padding:16px 24px;background:var(--bg2);border-top:1px solid var(--border)}
.input-box{display:flex;gap:8px;align-items:flex-end;background:var(--bg);border:1px solid var(--border);border-radius:12px;padding:8px 12px;transition:border-color 0.2s}
.input-box:focus-within{border-color:var(--accent)}
#input{flex:1;padding:6px 0;border:none;background:transparent;color:var(--text);font-size:14px;font-family:inherit;outline:none;resize:none;max-height:150px;line-height:1.5}
#send-btn{width:36px;height:36px;border-radius:10px;border:none;background:var(--accent);color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all 0.15s;flex-shrink:0}
#send-btn:hover{background:var(--accent2);transform:scale(1.05)}
#send-btn:disabled{opacity:0.3;cursor:not-allowed;transform:none}
#send-btn svg{width:18px;height:18px}
.input-hint{font-size:11px;color:var(--text2);margin-top:6px;text-align:center}

/* SETTINGS PANEL */
#settings{display:none;grid-area:chat;overflow-y:auto;padding:24px}
.settings-card{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:20px;margin-bottom:16px}
.settings-card h3{font-size:14px;font-weight:600;margin-bottom:12px;color:var(--accent2)}
.settings-card label{font-size:12px;color:var(--text2);display:block;margin-bottom:4px}
.settings-card input,.settings-card select{width:100%;padding:8px 12px;border-radius:8px;border:1px solid var(--border);background:var(--bg);color:var(--text);font-size:13px;margin-bottom:12px}
.settings-card .btn{padding:8px 16px;border-radius:8px;border:none;background:var(--accent);color:#fff;cursor:pointer;font-size:13px}

/* TOOL CALL DISPLAY */
.tool-call{background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:8px 12px;margin:6px 0;font-size:12px;font-family:'SF Mono',monospace}
.tool-call .tool-name{color:var(--accent2);font-weight:600}
.tool-call .tool-result{color:var(--text2);margin-top:4px;max-height:120px;overflow-y:auto}

/* COPY BUTTON */
.copy-btn{position:absolute;top:6px;right:6px;background:var(--bg3);border:1px solid var(--border);color:var(--text2);padding:3px 8px;border-radius:4px;font-size:10px;cursor:pointer;opacity:0;transition:opacity 0.15s}
.bubble:hover .copy-btn{opacity:1}
.bubble{position:relative}
.bubble pre{position:relative}

/* STATS BAR */
#stats-bar{display:flex;gap:16px;padding:6px 12px;background:var(--bg);border-radius:8px;margin-top:8px;font-size:11px;color:var(--text2)}
#stats-bar .stat{display:flex;align-items:center;gap:4px}
#stats-bar .stat-val{color:var(--accent2);font-weight:600}

/* THEME TOGGLE */
#theme-toggle{background:none;border:1px solid var(--border);color:var(--text2);padding:4px 10px;border-radius:6px;cursor:pointer;font-size:14px;transition:all 0.15s}
#theme-toggle:hover{border-color:var(--accent);color:var(--text)}

/* MOBILE MENU BUTTON */
#mobile-menu-btn{display:none;background:none;border:none;color:var(--text);font-size:20px;cursor:pointer;padding:4px}

/* MOBILE */
@media(max-width:768px){
  body{grid-template-columns:1fr;grid-template-areas:"head" "chat" "input"}
  #sidebar{display:none;position:fixed;top:0;left:0;width:280px;height:100%;z-index:1000;box-shadow:4px 0 24px rgba(0,0,0,0.4)}
  #sidebar.open{display:flex}
  #mobile-menu-btn{display:block}
  .msg-row{max-width:95%}
  #chat{padding:12px}
  #input-area{padding:10px 12px}
  .input-hint{display:none}
  #header{padding:10px 12px}
  .side-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:999}
  .side-overlay.open{display:block}
}
</style></head><body>

<div id="sidebar">
  <div class="side-header">
    <h1><span class="icon">😈</span> SalmAlm</h1>
    <div class="tagline">Personal AI Gateway</div>
  </div>
  <div class="side-nav">
    <div class="nav-section" data-i18n="sec-channels">Channels</div>
    <div class="nav-item active" onclick="showChat()">💬 Web Chat</div>
    <div class="nav-item" id="tg-status">📡 Telegram <span class="badge">ON</span></div>
    <div class="nav-section" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'block':'none'" style="cursor:pointer">🛠️ Tools (30) ▾</div>
    <div id="tools-list">
    <div class="nav-item" onclick="quickCmd('/help')">🔧 exec · file · search</div>
    <div class="nav-item" onclick="quickCmd('Check system status')">🖥️ System Monitor</div>
    <div class="nav-item" onclick="quickCmd('Show memory files')">🧠 Memory</div>
    <div class="nav-item" onclick="quickCmd('Show cost report')">💰 Cost Tracker</div>
    <div class="nav-item" onclick="quickCmd('Show cron jobs')">⏰ Cron Manager</div>
    <div class="nav-item" onclick="quickCmd('Calculate 1+1 in Python')">🐍 Python Exec</div>
    <div class="nav-item" onclick="quickCmd('Generate image: a cat in galaxy')">🎨 Image Gen</div>
    <div class="nav-item" onclick="quickCmd('Convert to speech: Hello world')">🔊 TTS</div>
    </div>
    <div class="nav-section" data-i18n="sec-admin">Admin</div>
    <div class="nav-item" onclick="showSettings()"data-i18n="nav-settings">⚙️ Settings</div>
    <div class="nav-item" onclick="showUsage()">📊 Usage</div>
  </div>
  <div class="side-footer">
    <div class="status"><span class="dot"></span> Running</div>
    <div>v''' + VERSION + ''' · AES-256-GCM</div>
  </div>
</div>

<div class="side-overlay" id="side-overlay" onclick="toggleSidebar()"></div>

<div id="header">
  <button id="mobile-menu-btn" onclick="toggleSidebar()">☰</button>
  <div class="title">💬 Web Chat</div>
  <div class="model-badge" id="model-badge">auto routing</div>
  <div class="spacer"></div>
  <div class="cost">Cost: <b id="cost-display">$0.0000</b></div>
  <button id="theme-toggle" onclick="toggleTheme()" title="Toggle theme">🌙</button>
  <button id="export-btn" onclick="window.exportChat('md')" title="Export chat" style="background:var(--accent-dim);color:var(--accent2);border:none;padding:6px 14px;border-radius:8px;font-size:12px;cursor:pointer"data-i18n="btn-export">📥 Export</button>
  <button id="new-chat-btn" onclick="window.newChat()" title="New Chat">🗑️ New Chat</button>
</div>

<div id="chat"></div>

<div id="settings">
  <div class="settings-card">
    <h3 data-i18n="h-lang">🌐 Language</h3>
    <select id="s-lang" onchange="setLang(this.value)" style="width:200px">
      <option value="en">English</option>
      <option value="ko">한국어</option>
    </select>
  </div>
  <div class="settings-card">
    <h3 data-i18n="h-model">🤖 Model Settings</h3>
    <labeldata-i18n="lbl-model">Default Model</label>
    <select id="s-model" onchange="setModel(this.value)">
      <optgroup label="🔄 Auto">
        <option value="auto">Auto Routing (Recommended)</option>
      </optgroup>
      <optgroup label="🟣 Anthropic">
        <option value="anthropic/claude-opus-4-6">Claude Opus 4.6 💎</option>
        <option value="anthropic/claude-sonnet-4-20250514">Claude Sonnet 4</option>
        <option value="anthropic/claude-haiku-3.5-20241022">Claude Haiku 3.5 ⚡</option>
      </optgroup>
      <optgroup label="🟢 OpenAI">
        <option value="openai/gpt-5.3-codex">GPT-5.3 Codex</option>
        <option value="openai/gpt-5.1-codex">GPT-5.1 Codex</option>
        <option value="openai/gpt-4.1">GPT-4.1</option>
        <option value="openai/gpt-4.1-mini">GPT-4.1 Mini ⚡</option>
        <option value="openai/gpt-4.1-nano">GPT-4.1 Nano 💨</option>
        <option value="openai/o3">o3 🧠</option>
        <option value="openai/o3-mini">o3-mini</option>
        <option value="openai/o4-mini">o4-mini</option>
      </optgroup>
      <optgroup label="🔵 xAI">
        <option value="xai/grok-4">Grok 4</option>
        <option value="xai/grok-3">Grok 3</option>
        <option value="xai/grok-3-mini">Grok 3 Mini ⚡</option>
      </optgroup>
      <optgroup label="🟡 Google">
        <option value="google/gemini-3-pro-preview">Gemini 3 Pro</option>
        <option value="google/gemini-3-flash-preview">Gemini 3 Flash ⚡</option>
      </optgroup>
      <optgroup label="🔷 OpenRouter">
        <option value="deepseek/deepseek-r1">DeepSeek R1 🧠</option>
        <option value="deepseek/deepseek-chat">DeepSeek Chat</option>
        <option value="meta-llama/llama-4-maverick">Llama 4 Maverick</option>
        <option value="meta-llama/llama-4-scout">Llama 4 Scout ⚡</option>
      </optgroup>
      <optgroup label="🦙 Ollama (Local)">
        <option value="ollama/llama3.3">Llama 3.3</option>
        <option value="ollama/qwen3">Qwen 3</option>
        <option value="ollama/gemma3">Gemma 3</option>
      </optgroup>
    </select>
    <label style="margin-top:8px"data-i18n="lbl-ollama">Ollama URL (Local LLM)</label>
    <input id="s-ollama-url" type="text" placeholder="http://localhost:11434/v1" style="width:100%;padding:8px;border-radius:6px;border:1px solid var(--border);background:var(--bg);color:var(--text);font-size:13px">
    <button onclick="fetch('/api/vault',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'set',key:'ollama_url',value:document.getElementById('s-ollama-url').value})}).then(function(){alert('Saved')})" style="margin-top:4px;padding:6px 12px;border-radius:6px;border:none;background:var(--accent);color:#fff;cursor:pointer;font-size:12px"data-i18n="btn-save-ollama">Save Ollama URL</button>
  </div>
  <div class="settings-card">
    <h3 data-i18n="h-keys">🔑 API Key Management</h3>
    <labeldata-i18n="lbl-anthropic">Anthropic API Key</label>
    <div style="display:flex;gap:6px"><input id="sk-anthropic" type="password" placeholder="sk-ant-..."><button class="btn" onclick="saveKey('anthropic_api_key','sk-anthropic')">Save</button><button class="btn" style="background:var(--bg3);color:var(--text2)" onclick="testKey('anthropic')">Test</button></div>
    <labeldata-i18n="lbl-openai">OpenAI API Key</label>
    <div style="display:flex;gap:6px"><input id="sk-openai" type="password" placeholder="sk-..."><button class="btn" onclick="saveKey('openai_api_key','sk-openai')">Save</button><button class="btn" style="background:var(--bg3);color:var(--text2)" onclick="testKey('openai')">Test</button></div>
    <labeldata-i18n="lbl-xai">xAI API Key (Grok)</label>
    <div style="display:flex;gap:6px"><input id="sk-xai" type="password" placeholder="xai-..."><button class="btn" onclick="saveKey('xai_api_key','sk-xai')">Save</button><button class="btn" style="background:var(--bg3);color:var(--text2)" onclick="testKey('xai')">Test</button></div>
    <labeldata-i18n="lbl-google">Google API Key (Gemini)</label>
    <div style="display:flex;gap:6px"><input id="sk-google" type="password" placeholder="AIza..."><button class="btn" onclick="saveKey('google_api_key','sk-google')">Save</button><button class="btn" style="background:var(--bg3);color:var(--text2)" onclick="testKey('google')">Test</button></div>
    <labeldata-i18n="lbl-brave">Brave Search API Key</label>
    <div style="display:flex;gap:6px"><input id="sk-brave" type="password" placeholder="BSA..."><button class="btn" onclick="saveKey('brave_api_key','sk-brave')">Save</button></div>
    <div id="key-test-result" style="margin-top:8px;font-size:12px"></div>
    <div id="vault-keys" style="margin-top:12px"></div>
  </div>
  <div class="settings-card" id="usage-card">
    <h3data-i18n="h-usage">📊 Token Usage</h3>
    <div id="usage-detail"></div>
  </div>
  <div class="settings-card">
    <h3 data-i18n="h-update">🔄 Update</h3>
    <div style="display:flex;gap:8px;align-items:center">
      <span id="update-ver" style="font-size:13px;color:var(--text2)">Current: v<span id="cur-ver"></span></span>
      <button class="btn" style="background:var(--bg3);color:var(--text2)" onclick="checkUpdate()"data-i18n="btn-check">Check for Updates</button>
      <button class="btn" id="do-update-btn" style="display:none" onclick="doUpdate()">⬆️ Update</button>
    </div>
    <div id="update-result" style="margin-top:8px;font-size:12px"></div>
  </div>
</div>

<div id="input-area">
  <div class="input-box">
    <textarea id="input" rows="1" placeholder="Type a message..." data-i18n="input-ph"></textarea>
    <button id="send-btn">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 2L11 13"/><path d="M22 2L15 22L11 13L2 9L22 2Z"/></svg>
    </button>
  </div>
  <div id="file-preview" style="display:none;padding:8px 0">
    <div style="display:flex;align-items:center;gap:8px;padding:8px 12px;background:var(--bg3);border-radius:8px;font-size:12px;color:var(--text2)">
      <span id="file-icon">📎</span>
      <span id="file-name" style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"></span>
      <span id="file-size"></span>
      <button onclick="clearFile()" style="background:none;border:none;color:var(--red);cursor:pointer;font-size:14px">✕</button>
    </div>
    <img id="img-preview" style="display:none;max-height:120px;border-radius:8px;margin-top:8px">
  </div>
  <div class="input-hint">Enter to send · Shift+Enter newline · Ctrl+V paste · Drag&Drop files</div>
</div>

<script>
(function(){
  const chat=document.getElementById('chat'),input=document.getElementById('input'),
    btn=document.getElementById('send-btn'),costEl=document.getElementById('cost-display'),
    modelBadge=document.getElementById('model-badge'),settingsEl=document.getElementById('settings'),
    filePrev=document.getElementById('file-preview'),fileIconEl=document.getElementById('file-icon'),
    fileNameEl=document.getElementById('file-name'),fileSizeEl=document.getElementById('file-size'),
    imgPrev=document.getElementById('img-preview'),inputArea=document.getElementById('input-area');
  let _tok=sessionStorage.getItem('tok')||'',pendingFile=null;

  /* --- Restore chat history --- */
  (function(){
    var hist=JSON.parse(localStorage.getItem('salm_chat')||'[]');
    if(hist.length){window._restoring=true;hist.forEach(function(m){addMsg(m.role,m.text,m.model)});window._restoring=false}
  })();

  /* --- Export chat --- */
  window.exportChat=function(fmt){
    var hist=JSON.parse(localStorage.getItem('salm_chat')||'[]');
    if(!hist.length){alert('No chat to export.');return}
    var content='';
    if(fmt==='json'){
      content=JSON.stringify(hist,null,2);
      var blob=new Blob([content],{type:'application/json'});
      var a=document.createElement('a');a.href=URL.createObjectURL(blob);
      a.download='salmalm_chat_'+new Date().toISOString().slice(0,10)+'.json';a.click();
    }else{
      hist.forEach(function(m){
        var role=m.role==='user'?'👤 User':'😈 SalmAlm';
        content+=role+'\\n'+m.text+'\\n\\n---\\n\\n';
      });
      var blob=new Blob([content],{type:'text/markdown'});
      var a=document.createElement('a');a.href=URL.createObjectURL(blob);
      a.download='salmalm_chat_'+new Date().toISOString().slice(0,10)+'.md';a.click();
    }
  };

  /* --- New chat --- */
  window.newChat=function(){
    if(!confirm('Delete chat history and start a new conversation?'))return;
    localStorage.removeItem('salm_chat');
    chat.innerHTML='';
    fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},
      body:JSON.stringify({message:'/clear',session:'web'})}).catch(function(){});
    addMsg('system','😈 New conversation started.');
  };

  /* --- Theme --- */
  var _theme=localStorage.getItem('salm_theme')||'dark';
  if(_theme==='light')document.documentElement.setAttribute('data-theme','light');
  window.toggleTheme=function(){
    _theme=_theme==='dark'?'light':'dark';
    document.documentElement.setAttribute('data-theme',_theme==='light'?'light':'');
    localStorage.setItem('salm_theme',_theme);
    var btn=document.getElementById('theme-toggle');
    btn.textContent=_theme==='dark'?'🌙':'☀️';
  };
  document.getElementById('theme-toggle').textContent=_theme==='dark'?'🌙':'☀️';

  /* --- Sidebar toggle (mobile) --- */
  window.toggleSidebar=function(){
    var sb=document.getElementById('sidebar'),ov=document.getElementById('side-overlay');
    sb.classList.toggle('open');ov.classList.toggle('open');
  };

  /* --- Quick command from sidebar --- */
  window.quickCmd=function(msg){
    input.value=msg;doSend();
    /* close sidebar on mobile */
    var sb=document.getElementById('sidebar');if(sb.classList.contains('open'))toggleSidebar();
  };

  /* --- Helpers --- */
  var _copyId=0;
  function escHtml(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
  function renderMd(t){
    if(t.startsWith('<img ')||t.startsWith('<audio '))return t;
    /* Extract code blocks first, escape everything else, then restore */
    var codeBlocks=[];
    t=t.replace(/```(\\w+)?\\n?([\\s\\S]*?)```/g,function(_,lang,code){
      _copyId++;var id='cp'+_copyId;
      var safe='<pre style="position:relative"><button class="copy-btn" onclick="copyCode(&quot;'+id+'&quot;)" id="btn'+id+'">📋 Copy</button><code id="'+id+'">'+(lang?'/* '+lang+' */\\n':'')+escHtml(code)+'</code></pre>';
      codeBlocks.push(safe);return '%%CODEBLOCK'+(codeBlocks.length-1)+'%%';
    });
    /* Escape remaining HTML to prevent XSS */
    t=escHtml(t);
    /* Restore code blocks */
    for(var ci=0;ci<codeBlocks.length;ci++){t=t.replace('%%CODEBLOCK'+ci+'%%',codeBlocks[ci])}
    t=t.replace(/`([^`]+)`/g,function(_,c){return '<code>'+c+'</code>'});
    t=t.replace(/\\*\\*([^*]+)\\*\\*/g,'<strong>$1</strong>');
    t=t.replace(/\\*([^*]+)\\*/g,'<em>$1</em>');
    /* Tables */
    t=t.replace(/^\\|(.+)\\|\\s*$/gm,function(_,row){
      var cells=row.split('|').map(function(c){return c.trim()});
      if(cells.every(function(c){return /^[-:]+$/.test(c)}))return '';
      return '<tr>'+cells.map(function(c){return '<td style="padding:4px 8px;border:1px solid var(--border)">'+c+'</td>'}).join('')+'</tr>';
    });
    t=t.replace(/((<tr>.*?<[/]tr>\\s*)+)/g,'<table style="border-collapse:collapse;margin:8px 0;font-size:13px">$1<\/table>');
    t=t.replace(/^### (.+)$/gm,'<h4 style="margin:8px 0 4px;font-size:13px;color:var(--accent2)">$1</h4>');
    t=t.replace(/^## (.+)$/gm,'<h3 style="margin:10px 0 6px;font-size:14px;color:var(--accent2)">$1</h3>');
    t=t.replace(/^# (.+)$/gm,'<h2 style="margin:12px 0 8px;font-size:16px;color:var(--accent2)">$1</h2>');
    t=t.replace(/^[•\\-] (.+)$/gm,'<div style="padding-left:16px;position:relative"><span style="position:absolute;left:4px">•</span>$1</div>');
    t=t.replace(/^(\\d+)\\. (.+)$/gm,'<div style="padding-left:16px">$1. $2</div>');
    t=t.replace(/\[([^\]]+)\]\(([^)]+)\)/g,'<a href="$2" target="_blank" style="color:var(--accent2);text-decoration:underline">$1<\/a>');
    t=t.replace(/uploads[/]([\w.-]+[.](png|jpg|jpeg|gif|webp))/gi,'<img src="/uploads/$1" style="max-width:400px;max-height:400px;border-radius:8px;display:block;margin:8px 0;cursor:pointer" alt="$1" onclick="window.open(this.src)">');
    t=t.replace(/uploads[/]([\w.-]+[.](mp3|wav|ogg))/gi,'<audio controls src="/uploads/$1" style="display:block;margin:8px 0"><\/audio> 🔊 $1');
    t=t.replace(/\\n/g,'<br>');
    return t;
  }
  window.copyCode=function(id){
    var el=document.getElementById(id);if(!el)return;
    navigator.clipboard.writeText(el.textContent).then(function(){
      var btn=document.getElementById('btn'+id);btn.textContent='✅ Copied';
      setTimeout(function(){btn.textContent='📋 Copy'},1500);
    });
  };
  function addMsg(role,text,model){
    const row=document.createElement('div');row.className='msg-row '+role;
    const av=document.createElement('div');av.className='avatar';
    av.textContent=role==='user'?'👤':'😈';
    const wrap=document.createElement('div');
    const bubble=document.createElement('div');bubble.className='bubble';
    bubble.innerHTML=renderMd(text);
    wrap.appendChild(bubble);
    var meta_parts=[];
    if(model)meta_parts.push(model);
    meta_parts.push(new Date().toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit'}));
    var mt=document.createElement('div');mt.className='meta';mt.textContent=meta_parts.join(' · ');
    if(role==='assistant'&&text){
      var regenBtn=document.createElement('span');
      regenBtn.textContent=' 🔄';regenBtn.style.cursor='pointer';regenBtn.title='Regenerate';
      regenBtn.onclick=function(){
        var hist=JSON.parse(localStorage.getItem('salm_chat')||'[]');
        /* Find last user message */
        for(var i=hist.length-1;i>=0;i--){if(hist[i].role==='user'){
          /* Remove this assistant msg and resend */
          hist.splice(i+1);localStorage.setItem('salm_chat',JSON.stringify(hist));
          row.remove();input.value=hist[i].text||'';doSend();break;
        }}
      };
      mt.appendChild(regenBtn);
    }
    wrap.appendChild(mt);
    row.appendChild(av);row.appendChild(wrap);
    chat.appendChild(row);chat.scrollTop=999999;
    if(!window._restoring){
      var hist=JSON.parse(localStorage.getItem('salm_chat')||'[]');
      hist.push({role:role,text:text,model:model||null});
      if(hist.length>200)hist=hist.slice(-200);
      localStorage.setItem('salm_chat',JSON.stringify(hist));
    }
  }
  function addTyping(){
    const row=document.createElement('div');row.className='msg-row assistant';row.id='typing-row';
    const av=document.createElement('div');av.className='avatar';av.textContent='😈';
    const wrap=document.createElement('div');
    const b=document.createElement('div');b.className='bubble';
    b.innerHTML='<div class="typing-indicator"><span></span><span></span><span></span></div>';
    wrap.appendChild(b);row.appendChild(av);row.appendChild(wrap);
    chat.appendChild(row);chat.scrollTop=999999;
  }

  /* --- File handling --- */
  window.setFile=function(file){
    pendingFile=file;
    const isImg=file.type.startsWith('image/');
    fileIconEl.textContent=isImg?'🖼️':'📎';
    fileNameEl.textContent=file.name;
    fileSizeEl.textContent=(file.size/1024).toFixed(1)+'KB';
    filePrev.style.display='block';
    if(isImg){const r=new FileReader();r.onload=function(e){imgPrev.src=e.target.result;imgPrev.style.display='block'};r.readAsDataURL(file)}
    else{imgPrev.style.display='none'}
    input.focus();
  };
  window.clearFile=function(){pendingFile=null;filePrev.style.display='none';imgPrev.style.display='none'};

  /* --- Ctrl+V --- */
  document.addEventListener('paste',function(e){
    var items=e.clipboardData&&e.clipboardData.items;if(!items)return;
    for(var i=0;i<items.length;i++){
      if(items[i].kind==='file'){e.preventDefault();var f=items[i].getAsFile();if(f)window.setFile(f);return}
    }
  });

  /* --- Drag & drop --- */
  inputArea.addEventListener('dragenter',function(e){e.preventDefault();e.stopPropagation();inputArea.style.outline='2px solid var(--accent)'});
  inputArea.addEventListener('dragover',function(e){e.preventDefault();e.stopPropagation()});
  inputArea.addEventListener('dragleave',function(e){e.preventDefault();inputArea.style.outline=''});
  inputArea.addEventListener('drop',function(e){e.preventDefault();e.stopPropagation();inputArea.style.outline='';
    var f=e.dataTransfer&&e.dataTransfer.files&&e.dataTransfer.files[0];if(f)window.setFile(f)});

  /* --- Send --- */
  async function doSend(){
    var t=input.value.trim();
    if(!t&&!pendingFile)return;
    input.value='';input.style.height='auto';btn.disabled=true;

    var fileMsg='';var imgData=null;var imgMime=null;
    if(pendingFile){
      var isImg=pendingFile.type.startsWith('image/');
      if(isImg){
        var reader=new FileReader();
        var previewUrl=await new Promise(function(res){reader.onload=function(){res(reader.result)};reader.readAsDataURL(pendingFile)});
        addMsg('user','<img src="'+previewUrl+'" style="max-width:300px;max-height:300px;border-radius:8px;display:block;margin:4px 0" alt="'+pendingFile.name+'">');
      }else{addMsg('user','[📎 '+pendingFile.name+' Uploading...]')}
      var fd=new FormData();fd.append('file',pendingFile);
      try{
        var ur=await fetch('/api/upload',{method:'POST',body:fd});
        var ud=await ur.json();
        if(ud.ok){fileMsg=ud.info;if(ud.image_base64){imgData=ud.image_base64;imgMime=ud.image_mime}}
        else addMsg('assistant','❌ Upload failed: '+(ud.error||''));
      }catch(ue){addMsg('assistant','❌ Upload error: '+ue.message)}
      window.clearFile();
    }

    var msg=(fileMsg?fileMsg+'\\n':'')+t;
    if(t)addMsg('user',t);
    if(!msg){btn.disabled=false;return}

    addTyping();
    var _sendStart=Date.now();
    var chatBody={message:msg,session:'web'};
    if(imgData){chatBody.image_base64=imgData;chatBody.image_mime=imgMime}
    try{
      var useStream=true;
      try{
        var r=await fetch('/api/chat/stream',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},
          body:JSON.stringify(chatBody)});
        if(!r.ok||!r.body){throw new Error('stream unavailable')}
        var reader=r.body.getReader();var decoder=new TextDecoder();var buf='';var gotDone=false;
        var typingEl=document.getElementById('typing-row');
        while(true){
          var chunk=await reader.read();
          if(chunk.done)break;
          buf+=decoder.decode(chunk.value,{stream:true});
          var evts=buf.split('\\n\\n');buf=evts.pop();
          for(var i=0;i<evts.length;i++){
            var evt=evts[i];
            var em=evt.match(/^event: (\\w+)\\ndata: (.+)$/m);
            if(!em)continue;
            var etype=em[1],edata=JSON.parse(em[2]);
            if(etype==='status'){
              if(typingEl){var tb=typingEl.querySelector('.bubble');if(tb)tb.innerHTML='<div class="typing-indicator"><span></span><span></span><span></span></div> '+edata.text}
            }else if(etype==='tool'){
              if(typingEl){var tb2=typingEl.querySelector('.bubble');if(tb2)tb2.innerHTML='<div class="typing-indicator"><span></span><span></span><span></span></div> 🔧 '+edata.name+'...'}
            }else if(etype==='done'){
              gotDone=true;
              if(typingEl)typingEl.remove();
              var _secs=((Date.now()-_sendStart)/1000).toFixed(1);
              addMsg('assistant',edata.response||'',(edata.model||'')+' · ⏱️'+_secs+'s');
              fetch('/api/status').then(function(r2){return r2.json()}).then(function(s){costEl.textContent='$'+s.usage.total_cost.toFixed(4)});
            }
          }
        }
        if(!gotDone)throw new Error('stream incomplete');
        if(document.getElementById('typing-row'))document.getElementById('typing-row').remove();
      }catch(streamErr){
        /* Fallback to regular /api/chat */
        console.warn('Stream failed, falling back:',streamErr);
        var typRow=document.getElementById('typing-row');
        if(typRow){var tb3=typRow.querySelector('.bubble');if(tb3)tb3.innerHTML='<div class="typing-indicator"><span></span><span></span><span></span></div> Processing...'}
        var r2=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},
          body:JSON.stringify(chatBody)});
        var d=await r2.json();
        if(document.getElementById('typing-row'))document.getElementById('typing-row').remove();
        var _secs2=((Date.now()-_sendStart)/1000).toFixed(1);
        if(d.response)addMsg('assistant',d.response,(d.model||'')+' · ⏱️'+_secs2+'s');
        else if(d.error)addMsg('assistant','❌ '+d.error);
        fetch('/api/status').then(function(r3){return r3.json()}).then(function(s){costEl.textContent='$'+s.usage.total_cost.toFixed(4)});
      }
    }catch(se){var tr2=document.getElementById('typing-row');if(tr2)tr2.remove();addMsg('assistant','❌ Error: '+se.message)}
    finally{btn.disabled=false;input.focus()}
  }
  window.doSend=doSend;

  /* --- Key handler --- */
  input.addEventListener('keydown',function(e){
    if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();doSend()}
  });
  input.addEventListener('input',function(){input.style.height='auto';input.style.height=Math.min(input.scrollHeight,150)+'px'});
  btn.addEventListener('click',function(){doSend()});

  /* --- i18n --- */
  var _i18n={
    en:{
      'nav-chat':'💬 Chat','nav-settings':'⚙️ Settings',
      'h-model':'🤖 Model Settings','h-keys':'🔑 API Key Management','h-update':'🔄 Update','h-lang':'🌐 Language',
      'lbl-model':'Default Model','lbl-ollama':'Ollama URL',
      'btn-save':'Save','btn-test':'Test','btn-check':'Check for Updates','btn-update':'⬆️ Update',
      'btn-export':'📥 Export','btn-send':'Send',
      'lbl-anthropic':'Anthropic API Key','lbl-openai':'OpenAI API Key',
      'lbl-xai':'xAI API Key (Grok)','lbl-google':'Google API Key (Gemini)','lbl-brave':'Brave Search API Key',
      'welcome-title':'Welcome to SalmAlm','welcome-sub':'Your personal AI gateway',
      'input-ph':'Type a message...',
      'usage-input':'Input','usage-output':'Output','usage-cost':'Cost','usage-uptime':'Uptime',
      'h-vault':'🗝️ Stored Keys','h-usage':'📊 Usage',
      'update-uptodate':'✅ You are up to date','update-checking':'⏳ Checking PyPI...',
      'update-new':'🆕 New version','update-available':'available!','update-download':'⬇️ Download',
      'update-installing':'Running pip install --upgrade salmalm...',
      'nav-webchat':'Web Chat','nav-sysmon':'System Monitor','nav-memory':'Memory',
      'nav-cost':'Cost Tracker','nav-cron':'Cron Manager','nav-python':'Python Exec',
      'nav-image':'Image Gen','nav-tts':'TTS',
      'btn-save-ollama':'Save Ollama URL','btn-newchat':'🗨 New Chat',
      'sec-channels':'Channels','sec-admin':'Admin',
    },
    ko:{
      'nav-chat':'💬 채팅','nav-settings':'⚙️ 설정',
      'h-model':'🤖 모델 설정','h-keys':'🔑 API 키 관리','h-update':'🔄 업데이트','h-lang':'🌐 언어',
      'lbl-model':'기본 모델','lbl-ollama':'Ollama URL',
      'btn-save':'저장','btn-test':'테스트','btn-check':'업데이트 확인','btn-update':'⬆️ 업데이트',
      'btn-export':'📥 내보내기','btn-send':'전송',
      'lbl-anthropic':'Anthropic API 키','lbl-openai':'OpenAI API 키',
      'lbl-xai':'xAI API 키 (Grok)','lbl-google':'Google API 키 (Gemini)','lbl-brave':'Brave Search API 키',
      'welcome-title':'삶앎에 오신 것을 환영합니다','welcome-sub':'나만의 AI 게이트웨이',
      'input-ph':'메시지를 입력하세요...',
      'usage-input':'입력','usage-output':'출력','usage-cost':'비용','usage-uptime':'가동시간',
      'h-vault':'🗝️ 저장된 키','h-usage':'📊 사용량',
      'update-uptodate':'✅ 최신 버전입니다','update-checking':'⏳ PyPI 확인 중...',
      'update-new':'🆕 새 버전','update-available':'사용 가능!','update-download':'⬇️ 다운로드',
      'update-installing':'pip install --upgrade salmalm 실행 중...',
      'nav-webchat':'웹 채팅','nav-sysmon':'시스템 모니터','nav-memory':'메모리',
      'nav-cost':'비용 추적','nav-cron':'크론 관리','nav-python':'Python 실행',
      'nav-image':'이미지 생성','nav-tts':'음성 합성',
      'btn-save-ollama':'Ollama URL 저장','btn-newchat':'🗨 새 대화',
      'sec-channels':'채널','sec-admin':'관리',
    }
  };
  var _lang=localStorage.getItem('salmalm-lang')||'en';
  function t(k){return (_i18n[_lang]||_i18n.en)[k]||(_i18n.en[k]||k)}
  function applyLang(){
    document.querySelectorAll('[data-i18n]').forEach(function(el){
      var k=el.getAttribute('data-i18n');
      if(el.tagName==='INPUT'||el.tagName==='TEXTAREA')el.placeholder=t(k);
      else el.textContent=t(k);
    });
    // Translate Save/Test buttons by content matching
    document.querySelectorAll('button').forEach(function(btn){
      var txt=btn.textContent.trim();
      if(txt==='Save'||txt==='저장')btn.textContent=t('btn-save');
      else if(txt==='Test'||txt==='테스트')btn.textContent=t('btn-test');
    });
    var sel=document.getElementById('s-lang');
    if(sel)sel.value=_lang;
  }
  window.setLang=function(v){_lang=v;localStorage.setItem('salmalm-lang',v);applyLang()};
  /* --- Settings --- */
  window.showChat=function(){settingsEl.style.display='none';chat.style.display='flex';inputArea.style.display='block'};
  window.showSettings=function(){chat.style.display='none';inputArea.style.display='none';settingsEl.style.display='block';
    fetch('/api/vault',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'keys'})})
      .then(function(r){return r.json()}).then(function(d){
        document.getElementById('vault-keys').innerHTML=d.keys.map(function(k){return '<div style="padding:4px 0;font-size:13px;color:var(--text2)">🔑 '+k+'</div>'}).join('')});
    fetch('/api/status').then(function(r){return r.json()}).then(function(d){
      var u=d.usage,h='<div style="font-size:13px;line-height:2">📥 Input: '+u.total_input.toLocaleString()+' tokens<br>📤 Output: '+u.total_output.toLocaleString()+' tokens<br>💰 Cost: $'+u.total_cost.toFixed(4)+'<br>⏱️ Uptime: '+u.elapsed_hours+'h</div>';
      if(u.by_model){h+='<div style="margin-top:12px;font-size:12px">';for(var m in u.by_model){var v=u.by_model[m];h+='<div style="padding:4px 0;color:var(--text2)">'+m+': '+v.calls+'calls · $'+v.cost.toFixed(4)+'</div>'}h+='</div>'}
      document.getElementById('usage-detail').innerHTML=h});
  };
  window.showUsage=window.showSettings;
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
    var re=document.getElementById('update-result');
    var btn=document.getElementById('do-update-btn');
    btn.disabled=true;btn.textContent='⏳ Installing...';
    re.innerHTML='<span style="color:var(--text2)">Running pip install --upgrade salmalm... (up to 30s)</span>';
    fetch('/api/do-update',{method:'POST'}).then(function(r){return r.json()}).then(function(d){
      if(d.ok){re.innerHTML='<span style="color:#4ade80">✅ v'+d.version+' Installed! Please restart the server.</span>';
        var rb=document.createElement('button');rb.className='btn';rb.style.marginTop='8px';rb.textContent='🔄 Restart Now';
        rb.onclick=function(){fetch('/api/restart',{method:'POST'});setTimeout(function(){location.reload()},3000)};re.appendChild(rb);
      }else{re.innerHTML='<span style="color:#f87171">❌ Failed: '+d.error+'</span>'}
      btn.disabled=false;btn.textContent='⬆️ Update'})
    .catch(function(e){re.innerHTML='<span style="color:#f87171">❌ '+e.message+'</span>';btn.disabled=false;btn.textContent='⬆️ Update'})};
  window.saveKey=function(vaultKey,inputId){
    var v=document.getElementById(inputId).value.trim();
    if(!v){alert('Please enter a key');return}
    fetch('/api/vault',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({action:'set',key:vaultKey,value:v})})
    .then(function(r){return r.json()}).then(function(d){
      var re=document.getElementById('key-test-result');
      re.innerHTML='<span style="color:#4ade80">✅ '+vaultKey+' Saved</span>';
      document.getElementById(inputId).value='';
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
  window.setModel=function(m){modelBadge.textContent=m==='auto'?'auto routing':m.split('/').pop();
    fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:'/model '+(m==='auto'?'auto':m),session:'web'})})};

  /* --- Drag highlight --- */
  var ia=document.getElementById('input-area');
  ia.addEventListener('dragenter',function(e){e.preventDefault();ia.classList.add('drag-over')});
  ia.addEventListener('dragover',function(e){e.preventDefault()});
  ia.addEventListener('dragleave',function(){ia.classList.remove('drag-over')});
  ia.addEventListener('drop',function(e){e.preventDefault();ia.classList.remove('drag-over');
    var files=e.dataTransfer.files;if(files.length>0){window.setFile(files[0])}});

  /* --- Scroll to bottom button --- */
  var scrollBtn=document.createElement('button');scrollBtn.id='scroll-bottom';scrollBtn.textContent='↓';
  document.body.appendChild(scrollBtn);
  chat.addEventListener('scroll',function(){
    var atBottom=chat.scrollHeight-chat.scrollTop-chat.clientHeight<100;
    scrollBtn.style.display=atBottom?'none':'flex';
  });
  scrollBtn.addEventListener('click',function(){chat.scrollTop=chat.scrollHeight});

  /* --- Basic syntax highlight for code blocks --- */
  function highlightCode(){
    document.querySelectorAll('.bubble pre code').forEach(function(el){
      if(el.dataset.hl)return;el.dataset.hl='1';
      var h=el.innerHTML;
      h=h.replace(/(\/\/.*$|#.*$|\/\*[\s\S]*?\*\/)/gm,'<span class="cmt">$1</span>');
      h=h.replace(/(&quot;[^&]*?&quot;|"[^"]*?"|'[^']*?')/g,'<span class="str">$1</span>');
      h=h.replace(/\b(\d+\.?\d*)\b/g,'<span class="num">$1</span>');
      h=h.replace(/\b(function|const|let|var|if|else|for|while|return|import|from|class|def|try|except|async|await|yield|with|raise)\b/g,'<span class="kw">$1</span>');
      el.innerHTML=h;
    });
  }
  var _hlObs=new MutationObserver(highlightCode);
  _hlObs.observe(chat,{childList:true,subtree:true});

  /* --- Keyboard shortcuts --- */
  document.addEventListener('keydown',function(e){
    if(e.ctrlKey&&e.key==='/'){e.preventDefault();input.focus()}
    if(e.key==='Escape'&&settingsEl.style.display==='block')showChat();
  });

  /* --- Welcome (only if no history) --- */
  if(!JSON.parse(localStorage.getItem('salm_chat')||'[]').length){
    addMsg('assistant','😈 Welcome to SalmAlm!\\n\\nUse on Telegram and Web simultaneously.\\nCtrl+V paste image · Drag&Drop · Enter to send\\nType /help for commands','system');
  }
  input.focus();

  /* --- Restore model preference from server --- */
  fetch('/api/status').then(r=>r.json()).then(d=>{
    if(d.model&&d.model!=='auto'){
      var sel=document.getElementById('s-model');
      if(sel){sel.value=d.model;modelBadge.textContent=d.model.split('/').pop()}
    }
  }).catch(()=>{});

  /* --- Notification polling (30s) --- */
  setInterval(async()=>{
    if(!_tok)return;
    try{
      var r=await fetch('/api/notifications',{headers:{'X-Session-Token':_tok}});
      if(!r.ok)return;
      var d=await r.json();
      if(d.notifications&&d.notifications.length){
        d.notifications.forEach(n=>addMsg('assistant',n.text,'notification'));
      }
    }catch(e){}
  },30000);
  applyLang();
})();
</script></body></html>'''


ONBOARDING_HTML = '''<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SalmAlm — Setup Wizard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,sans-serif;background:#0f1117;color:#e0e0e0;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
.wizard{background:#1a1d27;padding:40px;border-radius:16px;border:1px solid #2a2d37;max-width:520px;width:100%}
h1{color:#a78bfa;margin-bottom:4px;font-size:24px}
.sub{color:#888;font-size:13px;margin-bottom:32px}
.step{margin-bottom:20px}
.step label{display:block;font-size:13px;color:#aaa;margin-bottom:6px;font-weight:500}
.step input{width:100%;padding:10px 12px;border-radius:8px;border:1px solid #333;background:#0f1117;color:#e0e0e0;font-size:14px;font-family:monospace}
.step input:focus{border-color:#7c5cfc;outline:none}
.step .hint{font-size:11px;color:#666;margin-top:4px}
.required::after{content:" *";color:#f87171}
.divider{border-top:1px solid #2a2d37;margin:24px 0}
button{width:100%;padding:14px;border-radius:8px;border:none;background:#4f46e5;color:#fff;font-size:16px;cursor:pointer;font-weight:500;margin-top:8px}
button:hover{background:#4338ca}
button:disabled{opacity:0.5;cursor:not-allowed}
.skip{text-align:center;margin-top:16px}
.skip a{color:#666;font-size:13px;cursor:pointer;text-decoration:underline}
.skip a:hover{color:#aaa}
.result{margin-top:16px;padding:12px;border-radius:8px;font-size:14px;display:none}
.result.ok{background:#0f2a1f;border:1px solid #34d399;color:#34d399;display:block}
.result.err{background:#2a0f0f;border:1px solid #f87171;color:#f87171;display:block}
.progress{display:flex;gap:8px;margin-bottom:24px}
.progress .dot{width:10px;height:10px;border-radius:50%;background:#333}
.progress .dot.active{background:#7c5cfc}
.progress .dot.done{background:#34d399}
</style></head><body>
<div class="wizard">
<h1>😈 SalmAlm Setup Wizard</h1>
<p class="sub">You need at least 1 API key to use the AI Gateway</p>
<div class="progress"><div class="dot done"></div><div class="dot active"></div><div class="dot"></div></div>

<div class="step">
<label class="required">Anthropic API Key (Claude)</label>
<input type="password" id="anthropic" placeholder="sk-ant-...">
<div class="hint">Recommended. <a href="https://console.anthropic.com/settings/keys" target="_blank" style="color:#7c5cfc">Get Key →</a></div>
</div>
<div class="step">
<label>OpenAI API Key (GPT)</label>
<input type="password" id="openai" placeholder="sk-...">
<div class="hint"><a href="https://platform.openai.com/api-keys" target="_blank" style="color:#7c5cfc">Get Key →</a></div>
</div>
<div class="step">
<labeldata-i18n="lbl-xai">xAI API Key (Grok)</label>
<input type="password" id="xai" placeholder="xai-...">
</div>
<div class="step">
<labeldata-i18n="lbl-google">Google API Key (Gemini)</label>
<input type="password" id="google" placeholder="AIza...">
</div>
<div class="divider"></div>
<div class="step">
<label>Brave Search API Key (Web Search)</label>
<input type="password" id="brave" placeholder="BSA...">
<div class="hint">Optional. <a href="https://brave.com/search/api/" target="_blank" style="color:#7c5cfc">Get Free Key →</a></div>
</div>
<div class="divider"></div>
<div class="step">
<label>🎮 Discord Bot Token (Optional)</label>
<input type="password" id="discord" placeholder="MTIz...">
<div class="hint">Optional. <a href="https://discord.com/developers/applications" target="_blank" style="color:#7c5cfc">Create Bot →</a> MESSAGE CONTENT intent required</div>
</div>
<div class="divider"></div>
<div class="step">
<label>🦙 Ollama (Local LLM — No API key needed)</label>
<input type="text" id="ollama" placeholder="http://localhost:11434/v1" value="">
<div class="hint">If Ollama is installed, enter URL. Free without API keys! <a href="https://ollama.com" target="_blank" style="color:#7c5cfc">Install →</a></div>
</div>

<button id="btn" onclick="save()">Save & Test</button>
<div class="result" id="result"></div>
<div class="skip"><a onclick="location.reload()">Skip (configure later)</a></div>
</div>
<script>
async function save(){
  const btn=document.getElementById('btn');
  btn.disabled=true; btn.textContent='Testing...';
  const body={};
  ['anthropic','openai','xai','google','brave'].forEach(k=>{
    const v=document.getElementById(k).value.trim();
    if(v) body[k+'_api_key']=v;
  });
  const dc=document.getElementById('discord').value.trim();
  if(dc) body.discord_token=dc;
  const ollama=document.getElementById('ollama').value.trim();
  if(ollama) body.ollama_url=ollama;
  if(!Object.keys(body).length){
    show('Enter at least 1 API key or Ollama URL','err');
    btn.disabled=false; btn.textContent='Save & Test'; return;
  }
  try{
    const r=await fetch('/api/onboarding',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const d=await r.json();
    if(d.ok){
      const isTestFail=d.test_result&&d.test_result.includes('fail');
      show(d.test_result+' ('+d.saved.join(', ')+' Saved)',isTestFail?'err':'ok');
      if(!isTestFail){btn.textContent='✅ Done! Redirecting in 3s...';setTimeout(()=>location.reload(),3000);}
      else{btn.textContent='⚠️ Saved (verify key)';btn.disabled=false;}
    }else{show(d.error,'err');btn.disabled=false;btn.textContent='Save & Test';}
  }catch(e){show('Network error: '+e,'err');btn.disabled=false;btn.textContent='Save & Test';}
}
function show(msg,type){const el=document.getElementById('result');el.textContent=msg;el.className='result '+type;}
</script></body></html>'''


UNLOCK_HTML = '''<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SalmAlm — Unlock</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,sans-serif;background:#0f1117;color:#e0e0e0;height:100vh;display:flex;align-items:center;justify-content:center}
.card{background:#1a1d27;padding:40px;border-radius:16px;border:1px solid #2a2d37;text-align:center;min-width:320px}
h1{color:#a78bfa;margin-bottom:8px}
p{color:#888;margin-bottom:24px;font-size:14px}
input{width:100%;padding:12px;border-radius:8px;border:1px solid #333;background:#0f1117;color:#e0e0e0;font-size:16px;margin-bottom:16px;text-align:center}
button{width:100%;padding:12px;border-radius:8px;border:none;background:#4f46e5;color:#fff;font-size:16px;cursor:pointer}
button:hover{background:#4338ca}
.error{color:#ef4444;margin-top:12px;font-size:14px;display:none}
</style></head><body>
<div class="card">
<h1>😈 SalmAlm</h1>
<p>Personal AI Gateway v''' + VERSION + '''</p>
<input type="password" id="pw" placeholder="Master password" onkeydown="if(event.key==='Enter')unlock()">
<button onclick="unlock()">Unlock</button>
<div class="error" id="err"></div>
<div style="margin-top:24px;font-size:13px;color:#999;line-height:1.8;text-align:left;max-width:400px">
<p style="color:#bbb;font-weight:600;margin-bottom:8px">🔑 처음이신가요?</p>
<p>서버를 시작할 때 설정한 마스터 비밀번호를 입력하세요.</p>
<p style="margin-top:12px;color:#bbb;font-weight:600">비밀번호를 모르겠다면:</p>
<p>서버를 실행한 <b>cmd/터미널 창</b>을 확인하세요.<br>아래와 같이 비밀번호가 표시되어 있습니다:</p>
<code style="display:block;background:#252838;padding:8px 12px;border-radius:6px;font-size:12px;color:#7c83ff;margin:8px 0">Password: salmalm_local</code>
<p style="margin-top:12px;color:#bbb;font-weight:600">비밀번호를 잊으셨다면:</p>
<p>vault를 초기화하고 다시 시작하세요:</p>
<code style="display:block;background:#252838;padding:6px 10px;border-radius:4px;font-size:11px;color:#aaa;margin:4px 0">del %USERPROFILE%\\.salmalm\\vault.enc</code>
<span style="font-size:11px;color:#666">(Linux/Mac: rm ~/.salmalm/vault.enc)</span>
</div>
</div>
<script>
async function unlock(){
  const pw=document.getElementById('pw').value;
  const r=await fetch('/api/unlock',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:pw})});
  const d=await r.json();
  if(d.ok){sessionStorage.setItem('tok',d.token||'');location.reload()}
  else{const e=document.getElementById('err');e.textContent=d.error;e.style.display='block'}
}
</script></body></html>'''
