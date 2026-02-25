  /* --- Theme --- */
  var _theme=localStorage.getItem('salm_theme')||'light';
  var _color=localStorage.getItem('salm_color')||'';
  if(_theme==='light')document.documentElement.setAttribute('data-theme','light');
  if(_color)document.documentElement.setAttribute('data-color',_color);
  window.toggleTheme=function(){
    _theme=_theme==='dark'?'light':'dark';
    document.documentElement.setAttribute('data-theme',_theme==='light'?'light':'');
    localStorage.setItem('salm_theme',_theme);
    var btn=document.getElementById('theme-toggle');
    btn.textContent=_theme==='dark'?'🌙':'☀️';
  };
  window.setColor=function(c){
    _color=c;document.documentElement.setAttribute('data-color',c||'');
    localStorage.setItem('salm_color',c||'');
    var dots=document.querySelectorAll('.color-dot');
    dots.forEach(function(d){d.style.outline=d.getAttribute('data-color')===c?'2px solid var(--text)':'none'});
  };
  document.getElementById('theme-toggle').textContent=_theme==='dark'?'🌙':'☀️';
  setTimeout(function(){
    var dots=document.querySelectorAll('.color-dot');dots.forEach(function(d){if(d.getAttribute('data-color')===_color)d.style.outline='2px solid var(--text)'});
    /* Fill Google redirect URI on page load */
    var _rUris=document.querySelectorAll('.google-redirect-uri');var _oauthOrigin=location.origin.replace('127.0.0.1','localhost');_rUris.forEach(function(el){el.textContent=_oauthOrigin+'/api/google/callback'});
  },100);
