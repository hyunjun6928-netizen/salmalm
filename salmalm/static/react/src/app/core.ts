// @ts-nocheck -- legacy vanilla JS, types resolved at runtime
import { chat, input, btn, costEl, modelBadge, settingsEl, filePrev, fileIconEl, fileNameEl, fileSizeEl, imgPrev, inputArea, _tok, pendingFile, pendingFiles, _currentSession, _sessionCache, _isAutoRouting } from './globals';

// CSRF: monkey-patch fetch to add X-Requested-With on same-origin /api/ requests
const _origFetch = window.fetch;
window.fetch = function(url: any, opts: any) {
  opts = opts || {};
  const u = typeof url === 'string' ? url : (url && url.url) || '';
  if (u.startsWith('/api/')) {
    opts.headers = opts.headers || {};
    if (opts.headers instanceof Headers) { opts.headers.set('X-Requested-With', 'SalmAlm'); }
    else { opts.headers['X-Requested-With'] = 'SalmAlm'; }
  }
  return _origFetch.call(window, url, opts);
};
