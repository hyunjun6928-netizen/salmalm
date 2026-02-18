"""삶앎 Web UI — HTML + WebHandler."""
import asyncio, gzip, http.server, json, os, re, secrets, time
from pathlib import Path
from typing import Optional

from .constants import *
from .crypto import vault, log
from .core import get_usage_report, router, audit_log
from .auth import auth_manager, rate_limiter, extract_auth, RateLimitExceeded
from .logging_ext import request_logger, set_correlation_id

# ============================================================
WEB_HTML = '''<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>삶앎 — Personal AI Gateway</title>
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
    <h1><span class="icon">😈</span> 삶앎</h1>
    <div class="tagline">Personal AI Gateway</div>
  </div>
  <div class="side-nav">
    <div class="nav-section">채널</div>
    <div class="nav-item active" onclick="showChat()">💬 웹 챗</div>
    <div class="nav-item" id="tg-status">📡 텔레그램 <span class="badge">ON</span></div>
    <div class="nav-section" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'block':'none'" style="cursor:pointer">🛠️ 도구 (19개) ▾</div>
    <div id="tools-list">
    <div class="nav-item" onclick="quickCmd('/help')">🔧 exec · 파일 · 검색</div>
    <div class="nav-item" onclick="quickCmd('시스템 상태를 확인해줘')">🖥️ 시스템 모니터</div>
    <div class="nav-item" onclick="quickCmd('메모리 파일 목록을 보여줘')">🧠 메모리</div>
    <div class="nav-item" onclick="quickCmd('오늘의 비용 리포트를 보여줘')">💰 비용 추적</div>
    <div class="nav-item" onclick="quickCmd('크론 작업 목록을 보여줘')">⏰ 크론 관리</div>
    <div class="nav-item" onclick="quickCmd('Python으로 1+1 계산해줘')">🐍 Python 실행</div>
    <div class="nav-item" onclick="quickCmd('이미지를 생성해줘: 은하수 배경의 고양이')">🎨 이미지 생성</div>
    <div class="nav-item" onclick="quickCmd('이 문장을 음성으로 변환해줘: 안녕하세요')">🔊 TTS</div>
    </div>
    <div class="nav-section">관리</div>
    <div class="nav-item" onclick="showSettings()">⚙️ 설정</div>
    <div class="nav-item" onclick="showUsage()">📊 사용량</div>
  </div>
  <div class="side-footer">
    <div class="status"><span class="dot"></span> 가동 중</div>
    <div>v''' + VERSION + ''' · AES-256-GCM</div>
  </div>
</div>

<div class="side-overlay" id="side-overlay" onclick="toggleSidebar()"></div>

<div id="header">
  <button id="mobile-menu-btn" onclick="toggleSidebar()">☰</button>
  <div class="title">💬 웹 챗</div>
  <div class="model-badge" id="model-badge">auto routing</div>
  <div class="spacer"></div>
  <div class="cost">비용: <b id="cost-display">$0.0000</b></div>
  <button id="theme-toggle" onclick="toggleTheme()" title="테마 전환">🌙</button>
  <button id="export-btn" onclick="window.exportChat('md')" title="대화 내보내기" style="background:var(--accent-dim);color:var(--accent2);border:none;padding:6px 14px;border-radius:8px;font-size:12px;cursor:pointer">📥 내보내기</button>
  <button id="new-chat-btn" onclick="window.newChat()" title="새 대화">🗑️ 새 대화</button>
</div>

<div id="chat"></div>

<div id="settings">
  <div class="settings-card">
    <h3>🤖 모델 설정</h3>
    <label>기본 모델</label>
    <select id="s-model" onchange="setModel(this.value)">
      <optgroup label="🔄 자동">
        <option value="auto">자동 라우팅 (추천)</option>
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
      <optgroup label="🦙 Ollama (로컬)">
        <option value="ollama/llama3.3">Llama 3.3</option>
        <option value="ollama/qwen3">Qwen 3</option>
        <option value="ollama/gemma3">Gemma 3</option>
      </optgroup>
    </select>
    <label style="margin-top:8px">Ollama URL (로컬 LLM)</label>
    <input id="s-ollama-url" type="text" placeholder="http://localhost:11434/v1" style="width:100%;padding:8px;border-radius:6px;border:1px solid var(--border);background:var(--bg);color:var(--text);font-size:13px">
    <button onclick="fetch('/api/vault',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'set',key:'ollama_url',value:document.getElementById('s-ollama-url').value})}).then(function(){alert('저장됨')})" style="margin-top:4px;padding:6px 12px;border-radius:6px;border:none;background:var(--accent);color:#fff;cursor:pointer;font-size:12px">Ollama URL 저장</button>
  </div>
  <div class="settings-card">
    <h3>🔐 Vault 키 관리</h3>
    <div id="vault-keys"></div>
  </div>
  <div class="settings-card" id="usage-card">
    <h3>📊 토큰 사용량</h3>
    <div id="usage-detail"></div>
  </div>
</div>

<div id="input-area">
  <div class="input-box">
    <textarea id="input" rows="1" placeholder="메시지를 입력하세요..."></textarea>
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
  <div class="input-hint">Enter 전송 · Shift+Enter 줄바꿈 · Ctrl+V 이미지/파일 · 드래그앤드롭 가능</div>
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
    if(!hist.length){alert('내보낼 대화가 없습니다.');return}
    var content='';
    if(fmt==='json'){
      content=JSON.stringify(hist,null,2);
      var blob=new Blob([content],{type:'application/json'});
      var a=document.createElement('a');a.href=URL.createObjectURL(blob);
      a.download='salmalm_chat_'+new Date().toISOString().slice(0,10)+'.json';a.click();
    }else{
      hist.forEach(function(m){
        var role=m.role==='user'?'👤 사용자':'😈 삶앎';
        content+=role+'\\n'+m.text+'\\n\\n---\\n\\n';
      });
      var blob=new Blob([content],{type:'text/markdown'});
      var a=document.createElement('a');a.href=URL.createObjectURL(blob);
      a.download='salmalm_chat_'+new Date().toISOString().slice(0,10)+'.md';a.click();
    }
  };

  /* --- New chat --- */
  window.newChat=function(){
    if(!confirm('대화 기록을 삭제하고 새 대화를 시작할까요?'))return;
    localStorage.removeItem('salm_chat');
    chat.innerHTML='';
    fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},
      body:JSON.stringify({message:'/clear',session:'web'})}).catch(function(){});
    addMsg('system','😈 새 대화가 시작되었습니다.');
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
      var safe='<pre style="position:relative"><button class="copy-btn" onclick="copyCode(&quot;'+id+'&quot;)" id="btn'+id+'">📋 복사</button><code id="'+id+'">'+(lang?'/* '+lang+' */\\n':'')+escHtml(code)+'</code></pre>';
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
      var btn=document.getElementById('btn'+id);btn.textContent='✅ 복사됨';
      setTimeout(function(){btn.textContent='📋 복사'},1500);
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
      regenBtn.textContent=' 🔄';regenBtn.style.cursor='pointer';regenBtn.title='재생성';
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
      }else{addMsg('user','[📎 '+pendingFile.name+' 업로드 중...]')}
      var fd=new FormData();fd.append('file',pendingFile);
      try{
        var ur=await fetch('/api/upload',{method:'POST',body:fd});
        var ud=await ur.json();
        if(ud.ok){fileMsg=ud.info;if(ud.image_base64){imgData=ud.image_base64;imgMime=ud.image_mime}}
        else addMsg('assistant','❌ 업로드 실패: '+(ud.error||''));
      }catch(ue){addMsg('assistant','❌ 업로드 오류: '+ue.message)}
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
              addMsg('assistant',edata.response||'',(edata.model||'')+' · ⏱️'+_secs+'초');
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
        if(typRow){var tb3=typRow.querySelector('.bubble');if(tb3)tb3.innerHTML='<div class="typing-indicator"><span></span><span></span><span></span></div> 처리 중...'}
        var r2=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},
          body:JSON.stringify(chatBody)});
        var d=await r2.json();
        if(document.getElementById('typing-row'))document.getElementById('typing-row').remove();
        var _secs2=((Date.now()-_sendStart)/1000).toFixed(1);
        if(d.response)addMsg('assistant',d.response,(d.model||'')+' · ⏱️'+_secs2+'초');
        else if(d.error)addMsg('assistant','❌ '+d.error);
        fetch('/api/status').then(function(r3){return r3.json()}).then(function(s){costEl.textContent='$'+s.usage.total_cost.toFixed(4)});
      }
    }catch(se){var tr2=document.getElementById('typing-row');if(tr2)tr2.remove();addMsg('assistant','❌ 오류: '+se.message)}
    btn.disabled=false;input.focus();
  }
  window.doSend=doSend;

  /* --- Key handler --- */
  input.addEventListener('keydown',function(e){
    if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();doSend()}
  });
  input.addEventListener('input',function(){input.style.height='auto';input.style.height=Math.min(input.scrollHeight,150)+'px'});
  btn.addEventListener('click',function(){doSend()});

  /* --- Settings --- */
  window.showChat=function(){settingsEl.style.display='none';chat.style.display='flex';inputArea.style.display='block'};
  window.showSettings=function(){chat.style.display='none';inputArea.style.display='none';settingsEl.style.display='block';
    fetch('/api/vault',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'keys'})})
      .then(function(r){return r.json()}).then(function(d){
        document.getElementById('vault-keys').innerHTML=d.keys.map(function(k){return '<div style="padding:4px 0;font-size:13px;color:var(--text2)">🔑 '+k+'</div>'}).join('')});
    fetch('/api/status').then(function(r){return r.json()}).then(function(d){
      var u=d.usage,h='<div style="font-size:13px;line-height:2">📥 입력: '+u.total_input.toLocaleString()+' 토큰<br>📤 출력: '+u.total_output.toLocaleString()+' 토큰<br>💰 비용: $'+u.total_cost.toFixed(4)+'<br>⏱️ 가동: '+u.elapsed_hours+'시간</div>';
      if(u.by_model){h+='<div style="margin-top:12px;font-size:12px">';for(var m in u.by_model){var v=u.by_model[m];h+='<div style="padding:4px 0;color:var(--text2)">'+m+': '+v.calls+'회 · $'+v.cost.toFixed(4)+'</div>'}h+='</div>'}
      document.getElementById('usage-detail').innerHTML=h});
  };
  window.showUsage=window.showSettings;
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
    addMsg('assistant','😈 삶앎에 오신 걸 환영합니다!\\n\\n텔레그램과 웹에서 동시에 사용 가능합니다.\\nCtrl+V 이미지 붙여넣기 · 드래그앤드롭 · Enter 전송\\n/help로 명령어 확인','system');
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
})();
</script></body></html>'''


class WebHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for web UI and API."""

    def log_message(self, format, *args):
        pass  # Suppress default logging

    # Allowed origins for CORS (same-host only)
    _ALLOWED_ORIGINS = {
        'http://127.0.0.1:18800', 'http://localhost:18800',
        'http://127.0.0.1:18801', 'http://localhost:18801',
        'https://127.0.0.1:18800', 'https://localhost:18800',
    }

    def _cors(self):
        origin = self.headers.get('Origin', '')
        if origin in self._ALLOWED_ORIGINS:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
        # No Origin header (same-origin requests, curl, etc) → no CORS headers needed
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-API-Key')

    def _maybe_gzip(self, body: bytes) -> bytes:
        """Compress body if client accepts gzip and body is large enough."""
        if len(body) < 1024:
            return body
        ae = self.headers.get('Accept-Encoding', '')
        if 'gzip' not in ae:
            return body
        import gzip as _gzip
        compressed = _gzip.compress(body, compresslevel=6)
        if len(compressed) < len(body):
            self.send_header('Content-Encoding', 'gzip')
            return compressed
        return body

    def _json(self, data: dict, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self._cors()
        body = self._maybe_gzip(body)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, content: str):
        body = content.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        body = self._maybe_gzip(body)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # Public endpoints (no auth required)
    _PUBLIC_PATHS = {
        '/', '/index.html', '/api/status', '/api/health', '/api/unlock',
        '/api/auth/login', '/api/onboarding', '/docs',
    }

    def _require_auth(self, min_role: str = 'user') -> Optional[dict]:
        """Check auth for protected endpoints. Returns user dict or sends 401 and returns None.
        If vault is locked, also rejects (403)."""
        path = self.path.split('?')[0]
        if path in self._PUBLIC_PATHS or path.startswith('/uploads/'):
            return {'username': 'public', 'role': 'public', 'id': 0}  # skip auth for public endpoints

        # Try token/api-key auth first
        user = extract_auth(dict(self.headers))
        if user:
            role_rank = {'admin': 3, 'user': 2, 'readonly': 1}
            if role_rank.get(user.get('role', ''), 0) >= role_rank.get(min_role, 2):
                return user
            self._json({'error': 'Insufficient permissions'}, 403)
            return None

        # Fallback: if request is from loopback AND vault is unlocked, allow (single-user local mode)
        ip = self._get_client_ip()
        if ip in ('127.0.0.1', '::1', 'localhost') and vault.is_unlocked:
            return {'username': 'local', 'role': 'admin', 'id': 0}

        self._json({'error': 'Authentication required'}, 401)
        return None

    def _get_client_ip(self) -> str:
        """Get client IP. Only trusts X-Forwarded-For if SALMALM_TRUST_PROXY is set."""
        if os.environ.get('SALMALM_TRUST_PROXY'):
            xff = self.headers.get('X-Forwarded-For')
            if xff:
                return xff.split(',')[0].strip()
        return self.client_address[0] if self.client_address else '?'

    def _check_rate_limit(self) -> bool:
        """Check rate limit. Returns True if OK, sends 429 if exceeded."""
        ip = self._get_client_ip()
        user = extract_auth(dict(self.headers))
        role = user.get('role', 'anonymous') if user else 'anonymous'
        key = user.get('username', ip) if user else ip
        try:
            rate_limiter.check(key, role)
            return True
        except RateLimitExceeded as e:
            self.send_response(429)
            self.send_header('Retry-After', str(int(e.retry_after)))
            self._cors()
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'Rate limit exceeded',
                                         'retry_after': e.retry_after}).encode())
            return False

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
        self.end_headers()

    def do_GET(self):
        _start = time.time()
        import uuid
        set_correlation_id(str(uuid.uuid4())[:8])

        if self.path.startswith('/api/') and not self._check_rate_limit():
            return

        try:
            self._do_get_inner()
        except Exception as e:
            log.error(f"GET {self.path} error: {e}")
            self._json({'error': 'Internal server error'}, 500)
        finally:
            duration = (time.time() - _start) * 1000
            request_logger.log_request('GET', self.path.split('?')[0],
                                        ip=self._get_client_ip(),
                                        duration_ms=duration)

    def _needs_onboarding(self) -> bool:
        """Check if first-run onboarding is needed (no API keys configured)."""
        if not vault.is_unlocked:
            return False
        providers = ['anthropic_api_key', 'openai_api_key', 'xai_api_key', 'google_api_key']
        return not any(vault.get(k) for k in providers)

    def _do_get_inner(self):
        if self.path == '/' or self.path == '/index.html':
            if not vault.is_unlocked:
                self._html(UNLOCK_HTML)
            elif self._needs_onboarding():
                self._html(ONBOARDING_HTML)
            else:
                self._html(WEB_HTML)
        elif self.path == '/api/notifications':
            from .core import _sessions
            web_session = _sessions.get('web')
            notifications = []
            if web_session and hasattr(web_session, '_notifications'):
                notifications = web_session._notifications
                web_session._notifications = []  # clear after read
            self._json({'notifications': notifications})
        elif self.path == '/api/dashboard':
            # Dashboard data: sessions, costs, tools, cron jobs
            from .core import _sessions, _llm_cron, PluginLoader, SubAgent
            sessions_info = [
                {'id': s.id, 'messages': len(s.messages),
                 'last_active': s.last_active, 'created': s.created}
                for s in _sessions.values()
            ]
            cron_jobs = _llm_cron.list_jobs() if _llm_cron else []
            plugins = [{'name': n, 'tools': len(p['tools'])}
                       for n, p in PluginLoader._plugins.items()]
            subagents = SubAgent.list_agents()
            usage = get_usage_report()
            # Cost by hour (from audit)
            cost_timeline = []
            try:
                import sqlite3 as _sq
                _conn = _sq.connect(str(AUDIT_DB))
                cur = _conn.execute(
                    "SELECT substr(ts,1,13) as hour, COUNT(*) as cnt "
                    "FROM audit_log WHERE event='tool_exec' "
                    "GROUP BY hour ORDER BY hour DESC LIMIT 24")
                cost_timeline = [{'hour': r[0], 'count': r[1]} for r in cur.fetchall()]
                _conn.close()
            except Exception:
                pass
            self._json({
                'sessions': sessions_info,
                'usage': usage,
                'cron_jobs': cron_jobs,
                'plugins': plugins,
                'subagents': subagents,
                'cost_timeline': cost_timeline
            })
        elif self.path == '/api/cron':
            from .core import _llm_cron
            self._json({'jobs': _llm_cron.list_jobs() if _llm_cron else []})
        elif self.path == '/api/plugins':
            from .core import PluginLoader
            tools = PluginLoader.get_all_tools()
            plugins = [{'name': n, 'tools': len(p['tools']), 'path': p['path']}
                       for n, p in PluginLoader._plugins.items()]
            self._json({'plugins': plugins, 'total_tools': len(tools)})
        elif self.path == '/api/mcp':
            from .mcp import mcp_manager
            servers = mcp_manager.list_servers()
            all_tools = mcp_manager.get_all_tools()
            self._json({'servers': servers, 'total_tools': len(all_tools)})
        elif self.path == '/api/rag':
            from .rag import rag_engine
            self._json(rag_engine.get_stats())
        elif self.path.startswith('/api/rag/search'):
            from .rag import rag_engine
            import urllib.parse
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            query = params.get('q', [''])[0]
            if not query:
                self._json({'error': 'Missing q parameter'}, 400)
            else:
                results = rag_engine.search(query, max_results=int(params.get('n', ['5'])[0]))
                self._json({'query': query, 'results': results})
        elif self.path == '/api/ws/status':
            from .ws import ws_server
            self._json({
                'running': ws_server._running,
                'clients': ws_server.client_count,
                'port': ws_server.port,
            })
        elif self.path == '/api/health':
            from .stability import health_monitor
            self._json(health_monitor.check_health())
        elif self.path == '/api/nodes':
            from .nodes import node_manager
            self._json({'nodes': node_manager.list_nodes()})
        elif self.path == '/api/status':
            self._json({'app': APP_NAME, 'version': VERSION,
                        'unlocked': vault.is_unlocked,
                        'usage': get_usage_report(),
                        'model': router.force_model or 'auto'})
        elif self.path == '/api/metrics':
            self._json(request_logger.get_metrics())
        elif self.path == '/api/cert':
            from .tls import get_cert_info
            self._json(get_cert_info())
        elif self.path == '/api/auth/users':
            user = extract_auth(dict(self.headers))
            if not user or user.get('role') != 'admin':
                self._json({'error': 'Admin access required'}, 403)
            else:
                self._json({'users': auth_manager.list_users()})
        elif self.path == '/docs':
            from .docs import generate_api_docs_html
            self._html(generate_api_docs_html())
        elif self.path.startswith('/uploads/'):
            # Serve uploaded files (images, audio)
            fname = self.path.split('/uploads/')[-1]
            fpath = WORKSPACE_DIR / 'uploads' / fname
            if not fpath.exists():
                self.send_error(404)
                return
            mime_map = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                        '.gif': 'image/gif', '.webp': 'image/webp', '.mp3': 'audio/mpeg',
                        '.wav': 'audio/wav', '.ogg': 'audio/ogg'}
            ext = fpath.suffix.lower()
            mime = mime_map.get(ext, 'application/octet-stream')
            # ETag caching for static uploads
            stat = fpath.stat()
            etag = f'"{int(stat.st_mtime)}-{stat.st_size}"'
            if self.headers.get('If-None-Match') == etag:
                self.send_response(304)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(stat.st_size))
            self.send_header('ETag', etag)
            self.send_header('Cache-Control', 'public, max-age=86400')
            self.end_headers()
            self.wfile.write(fpath.read_bytes())
        else:
            self.send_error(404)

    def do_POST(self):
        _start = time.time()
        import uuid
        set_correlation_id(str(uuid.uuid4())[:8])

        if self.path.startswith('/api/') and not self._check_rate_limit():
            return

        try:
            self._do_post_inner()
        except Exception as e:
            log.error(f"POST {self.path} error: {e}")
            self._json({'error': 'Internal server error'}, 500)
        finally:
            duration = (time.time() - _start) * 1000
            request_logger.log_request('POST', self.path,
                                        ip=self._get_client_ip(),
                                        duration_ms=duration)

    def _do_post_inner(self):
        from .engine import process_message
        length = int(self.headers.get('Content-Length', 0))
        # Don't parse multipart as JSON
        if self.path == '/api/upload':
            body = {}
        else:
            body = json.loads(self.rfile.read(length)) if length else {}

        if self.path == '/api/auth/login':
            username = body.get('username', '')
            password = body.get('password', '')
            user = auth_manager.authenticate(username, password)
            if user:
                token = auth_manager.create_token(user)
                self._json({'ok': True, 'token': token, 'user': user})
            else:
                self._json({'error': 'Invalid credentials'}, 401)
            return

        if self.path == '/api/auth/register':
            requester = extract_auth(dict(self.headers))
            if not requester or requester.get('role') != 'admin':
                self._json({'error': 'Admin access required'}, 403)
                return
            try:
                user = auth_manager.create_user(
                    body.get('username', ''), body.get('password', ''),
                    body.get('role', 'user'))
                self._json({'ok': True, 'user': user})
            except ValueError as e:
                self._json({'error': str(e)}, 400)
            return

        if self.path == '/api/unlock':
            password = body.get('password', '')
            if VAULT_FILE.exists():
                ok = vault.unlock(password)
            else:
                vault.create(password)
                ok = True
            if ok:
                audit_log('unlock', 'vault unlocked')
                token = secrets.token_hex(32)
                self._json({'ok': True, 'token': token})
            else:
                audit_log('unlock_fail', 'wrong password')
                self._json({'ok': False, 'error': '비밀번호 틀림'}, 401)

        elif self.path in ('/api/chat', '/api/chat/stream'):
            if not vault.is_unlocked:
                self._json({'error': 'Vault locked'}, 403)
                return
            message = body.get('message', '')
            session_id = body.get('session', 'web')
            image_b64 = body.get('image_base64')
            image_mime = body.get('image_mime', 'image/png')
            use_stream = self.path.endswith('/stream')

            if use_stream:
                # SSE streaming response
                self.send_response(200)
                self._cors()
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Connection', 'keep-alive')
                self.end_headers()

                def send_sse(event, data):
                    try:
                        payload = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                        self.wfile.write(payload.encode())
                        self.wfile.flush()
                    except Exception:
                        pass

                send_sse('status', {'text': '🤔 생각 중...'})
                try:
                    loop = asyncio.new_event_loop()
                    response = loop.run_until_complete(
                        process_message(session_id, message,
                                        image_data=(image_b64, image_mime) if image_b64 else None,
                                        on_tool=lambda name, args: send_sse('tool', {'name': name, 'args': str(args)[:200]}))
                    )
                    loop.close()
                except Exception as e:
                    log.error(f"SSE process_message error: {e}")
                    response = f'❌ 내부 오류: {type(e).__name__}'
                send_sse('done', {'response': response, 'model': router.force_model or 'auto'})
                try:
                    self.wfile.write(b"event: close\ndata: {}\n\n")
                    self.wfile.flush()
                except Exception:
                    pass
            else:
                try:
                    loop = asyncio.new_event_loop()
                    response = loop.run_until_complete(
                        process_message(session_id, message,
                                        image_data=(image_b64, image_mime) if image_b64 else None)
                    )
                    loop.close()
                except Exception as e:
                    log.error(f"Chat process_message error: {e}")
                    response = f'❌ 내부 오류: {type(e).__name__}'
                self._json({'response': response, 'model': router.force_model or 'auto'})

        elif self.path == '/api/vault':
            if not vault.is_unlocked:
                self._json({'error': 'Vault locked'}, 403)
                return
            # Vault ops require admin
            user = extract_auth(dict(self.headers))
            ip = self._get_client_ip()
            if not user and ip not in ('127.0.0.1', '::1', 'localhost'):
                self._json({'error': 'Admin access required'}, 403)
                return
            action = body.get('action')
            if action == 'set':
                vault.set(body['key'], body['value'])
                self._json({'ok': True})
            elif action == 'get':
                val = vault.get(body['key'])
                self._json({'value': val})
            elif action == 'keys':
                self._json({'keys': vault.keys()})
            elif action == 'delete':
                vault.delete(body['key'])
                self._json({'ok': True})
            else:
                self._json({'error': 'Unknown action'}, 400)

        elif self.path == '/api/upload':
            if not vault.is_unlocked:
                self._json({'error': 'Vault locked'}, 403)
                return
            # Parse multipart form data
            content_type = self.headers.get('Content-Type', '')
            if 'multipart/form-data' not in content_type:
                self._json({'error': 'multipart required'}, 400)
                return
            try:
                boundary = content_type.split('boundary=')[1].strip()
                raw = self.rfile.read(length)
                # Simple multipart parser
                parts = raw.split(f'--{boundary}'.encode())
                for part in parts:
                    if b'filename="' not in part:
                        continue
                    # Extract filename
                    header_end = part.find(b'\r\n\r\n')
                    if header_end < 0:
                        continue
                    header = part[:header_end].decode('utf-8', errors='replace')
                    fname_match = re.search(r'filename="([^"]+)"', header)
                    if not fname_match:
                        continue
                    fname = Path(fname_match.group(1)).name  # basename only (prevent path traversal)
                    # Reject suspicious filenames
                    if not fname or '..' in fname or not re.match(r'^[\w.\- ]+$', fname):
                        self._json({'error': 'Invalid filename'}, 400)
                        return
                    file_data = part[header_end+4:]
                    # Remove trailing \r\n--
                    if file_data.endswith(b'\r\n'):
                        file_data = file_data[:-2]
                    if file_data.endswith(b'--'):
                        file_data = file_data[:-2]
                    if file_data.endswith(b'\r\n'):
                        file_data = file_data[:-2]
                    # Size limit: 50MB
                    if len(file_data) > 50 * 1024 * 1024:
                        self._json({'error': 'File too large (max 50MB)'}, 413)
                        return
                    # Save
                    save_dir = WORKSPACE_DIR / 'uploads'
                    save_dir.mkdir(exist_ok=True)
                    save_path = save_dir / fname
                    save_path.write_bytes(file_data)
                    size_kb = len(file_data) / 1024
                    is_image = any(fname.lower().endswith(ext) for ext in ('.png','.jpg','.jpeg','.gif','.webp','.bmp'))
                    is_text = any(fname.lower().endswith(ext) for ext in ('.txt','.md','.py','.js','.json','.csv','.log','.html','.css','.sh','.bat','.yaml','.yml','.xml','.sql'))
                    info = f'[{"🖼️ 이미지" if is_image else "📎 파일"} 업로드: uploads/{fname} ({size_kb:.1f}KB)]'
                    if is_text:
                        try:
                            preview = file_data.decode('utf-8', errors='replace')[:3000]
                            info += f'\n[파일 내용]\n{preview}'
                        except Exception:
                            pass
                    log.info(f"📤 Web upload: {fname} ({size_kb:.1f}KB)")
                    audit_log('web_upload', fname)
                    resp = {'ok': True, 'filename': fname, 'size': len(file_data),
                                'info': info, 'is_image': is_image}
                    if is_image:
                        import base64
                        ext = fname.rsplit('.', 1)[-1].lower()
                        mime = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
                                'gif': 'image/gif', 'webp': 'image/webp', 'bmp': 'image/bmp'}.get(ext, 'image/png')
                        resp['image_base64'] = base64.b64encode(file_data).decode()
                        resp['image_mime'] = mime
                    self._json(resp)
                    return
                self._json({'error': 'No file found'}, 400)
            except Exception as e:
                log.error(f"Upload error: {e}")
                self._json({'error': str(e)[:200]}, 500)
                return

        elif self.path == '/api/onboarding':
            if not vault.is_unlocked:
                self._json({'error': 'Vault locked'}, 403)
                return
            # Save all provided API keys
            saved = []
            for key in ('anthropic_api_key', 'openai_api_key', 'xai_api_key',
                        'google_api_key', 'brave_api_key'):
                val = body.get(key, '').strip()
                if val:
                    vault.set(key, val)
                    saved.append(key.replace('_api_key', ''))
            # Test the first available key
            test_result = None
            if body.get('anthropic_api_key'):
                try:
                    from .llm import _http_post
                    resp = _http_post(
                        'https://api.anthropic.com/v1/messages',
                        {'x-api-key': body['anthropic_api_key'],
                         'content-type': 'application/json',
                         'anthropic-version': '2023-06-01'},
                        {'model': 'claude-haiku-3.5-20241022', 'max_tokens': 10,
                         'messages': [{'role': 'user', 'content': 'ping'}]},
                        timeout=15
                    )
                    test_result = '✅ Anthropic API 연결 성공!'
                except Exception as e:
                    test_result = f'⚠️ Anthropic 테스트 실패: {str(e)[:100]}'
            elif body.get('openai_api_key'):
                try:
                    from .llm import _http_post
                    resp = _http_post(
                        'https://api.openai.com/v1/chat/completions',
                        {'Authorization': f'Bearer {body["openai_api_key"]}',
                         'Content-Type': 'application/json'},
                        {'model': 'gpt-4.1-nano', 'max_tokens': 10,
                         'messages': [{'role': 'user', 'content': 'ping'}]},
                        timeout=15
                    )
                    test_result = '✅ OpenAI API 연결 성공!'
                except Exception as e:
                    test_result = f'⚠️ OpenAI 테스트 실패: {str(e)[:100]}'
            audit_log('onboarding', f'keys: {", ".join(saved)}')
            self._json({'ok': True, 'saved': saved,
                        'test_result': test_result or '키가 저장되었습니다.'})
            return

        elif self.path == '/api/config/telegram':
            if not vault.is_unlocked:
                self._json({'error': 'Vault locked'}, 403)
                return
            vault.set('telegram_token', body.get('token', ''))
            vault.set('telegram_owner_id', body.get('owner_id', ''))
            self._json({'ok': True, 'message': 'Telegram 설정 저장. 재시작 필요.'})

        else:
            self._json({'error': 'Not found'}, 404)


ONBOARDING_HTML = '''<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>삶앎 — 설정 마법사</title>
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
<h1>😈 삶앎 설정 마법사</h1>
<p class="sub">AI Gateway를 사용하려면 최소 1개의 API 키가 필요합니다</p>
<div class="progress"><div class="dot done"></div><div class="dot active"></div><div class="dot"></div></div>

<div class="step">
<label class="required">Anthropic API Key (Claude)</label>
<input type="password" id="anthropic" placeholder="sk-ant-...">
<div class="hint">가장 추천. <a href="https://console.anthropic.com/settings/keys" target="_blank" style="color:#7c5cfc">발급하기 →</a></div>
</div>
<div class="step">
<label>OpenAI API Key (GPT)</label>
<input type="password" id="openai" placeholder="sk-...">
<div class="hint"><a href="https://platform.openai.com/api-keys" target="_blank" style="color:#7c5cfc">발급하기 →</a></div>
</div>
<div class="step">
<label>xAI API Key (Grok)</label>
<input type="password" id="xai" placeholder="xai-...">
</div>
<div class="step">
<label>Google API Key (Gemini)</label>
<input type="password" id="google" placeholder="AIza...">
</div>
<div class="divider"></div>
<div class="step">
<label>Brave Search API Key (웹 검색용)</label>
<input type="password" id="brave" placeholder="BSA...">
<div class="hint">선택사항. <a href="https://brave.com/search/api/" target="_blank" style="color:#7c5cfc">무료 발급 →</a></div>
</div>

<button id="btn" onclick="save()">저장 & 테스트</button>
<div class="result" id="result"></div>
<div class="skip"><a onclick="location.reload()">건너뛰기 (나중에 설정)</a></div>
</div>
<script>
async function save(){
  const btn=document.getElementById('btn');
  btn.disabled=true; btn.textContent='테스트 중...';
  const body={};
  ['anthropic','openai','xai','google','brave'].forEach(k=>{
    const v=document.getElementById(k).value.trim();
    if(v) body[k+'_api_key']=v;
  });
  if(!Object.keys(body).length){
    show('최소 1개의 API 키를 입력하세요','err');
    btn.disabled=false; btn.textContent='저장 & 테스트'; return;
  }
  try{
    const r=await fetch('/api/onboarding',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const d=await r.json();
    if(d.ok){
      show(d.test_result+' ('+d.saved.join(', ')+' 저장됨)','ok');
      btn.textContent='✅ 완료! 3초 후 이동...';
      setTimeout(()=>location.reload(),3000);
    }else{show(d.error,'err');btn.disabled=false;btn.textContent='저장 & 테스트';}
  }catch(e){show('네트워크 오류: '+e,'err');btn.disabled=false;btn.textContent='저장 & 테스트';}
}
function show(msg,type){const el=document.getElementById('result');el.textContent=msg;el.className='result '+type;}
</script></body></html>'''

UNLOCK_HTML = '''<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>삶앎 — Unlock</title>
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
<h1>😈 삶앎</h1>
<p>Personal AI Gateway v''' + VERSION + '''</p>
<input type="password" id="pw" placeholder="마스터 비밀번호" onkeydown="if(event.key==='Enter')unlock()">
<button onclick="unlock()">잠금 해제</button>
<div class="error" id="err"></div>
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


