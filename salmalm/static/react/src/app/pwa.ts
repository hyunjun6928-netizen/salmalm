import { _currentSession, _isAutoRouting, _sessionCache, _tok, applyLang, btn, chat, costEl, fileIconEl, fileNameEl, filePrev, fileSizeEl, imgPrev, input, inputArea, modelBadge, pendingFile, pendingFiles, set_currentSession, set_isAutoRouting, set_pendingFile, set_pendingFiles, set_sessionCache, set_tok, settingsEl, t } from './globals';

  /* --- PWA Install Prompt --- */
  var _deferredPrompt=null;
  var _pwaBanner=document.createElement('div');_pwaBanner.id='pwa-install';
  _pwaBanner.innerHTML='<span>😈 '+t('pwa-install-text')+'</span><button class="install-btn" data-action="pwaInstall">'+t('pwa-install-btn')+'</button><button class="dismiss-btn" data-action="pwaDismiss">'+t('pwa-dismiss')+'</button>';
  document.body.appendChild(_pwaBanner);
  window.addEventListener('beforeinstallprompt',function(e){e.preventDefault();_deferredPrompt=e;if(!localStorage.getItem('pwa-dismissed'))_pwaBanner.classList.add('show')});
  window.pwaInstall=function(){if(_deferredPrompt){_deferredPrompt.prompt();_deferredPrompt.userChoice.then(function(){_deferredPrompt=null;_pwaBanner.classList.remove('show')})}};
  window.pwaDismiss=function(){_pwaBanner.classList.remove('show');localStorage.setItem('pwa-dismissed','1')};

  applyLang();

  /* --- Toast notification --- */
  window._toast=function(msg,ms){ms=ms||2000;var d=document.createElement('div');d.textContent=msg;d.style.cssText='position:fixed;bottom:80px;left:50%;transform:translateX(-50%);background:var(--bg3);color:var(--text);padding:8px 20px;border-radius:10px;font-size:13px;z-index:9999;box-shadow:0 2px 12px rgba(0,0,0,0.2);opacity:0;transition:opacity 0.2s';document.body.appendChild(d);requestAnimationFrame(function(){d.style.opacity='1'});setTimeout(function(){d.style.opacity='0';setTimeout(function(){d.remove()},300)},ms)};

