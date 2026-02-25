// Shared DOM references and mutable state
export const chat = document.getElementById('chat') as HTMLElement;
export const input = document.getElementById('input') as HTMLTextAreaElement;
export const btn = document.getElementById('send-btn') as HTMLButtonElement;
export const costEl = document.getElementById('cost-display') as HTMLElement;
export const modelBadge = document.getElementById('model-badge') as HTMLElement;
export const settingsEl = document.getElementById('settings') as HTMLElement;
export const filePrev = document.getElementById('file-preview') as HTMLElement;
export const fileIconEl = document.getElementById('file-icon') as HTMLElement;
export const fileNameEl = document.getElementById('file-name') as HTMLElement;
export const fileSizeEl = document.getElementById('file-size') as HTMLElement;
export const imgPrev = document.getElementById('img-preview') as HTMLElement;
export const inputArea = document.getElementById('input-area') as HTMLElement;

export let _tok: string = sessionStorage.getItem('tok') || '';
export let pendingFile: File | null = null;
export let pendingFiles: File[] = [];
export let _currentSession: string = localStorage.getItem('salm_active_session') || 'web';
export let _sessionCache: Record<string, any> = {};
export let _isAutoRouting: boolean = true;

export function set_tok(v: string) { _tok = v; }
export function set_pendingFile(v: File | null) { pendingFile = v; }
export function set_pendingFiles(v: File[]) { pendingFiles = v; }
export function set_currentSession(v: string) { _currentSession = v; }
export function set_sessionCache(v: Record<string, any>) { _sessionCache = v; }
export function set_isAutoRouting(v: boolean) { _isAutoRouting = v; }

// ─── Cross-module function proxies ───────────────────────────────────────────
// These delegate to window.fnName at call time, breaking circular import deps.
// Home modules register: window.addMsg = addMsg, window.t = t, etc.
// All callers import from here so only ONE name exists per function in the bundle.
export function addMsg(...args: any[]): void { (window as any).addMsg?.(...args); }
export function t(k: string): string { return (window as any).t?.(k) ?? k; }
export function loadSessionList(): void { (window as any).loadSessionList?.(); }
export function doSend(): void { (window as any).doSend?.(); }
export function _hideAll(): void { (window as any)._hideAll?.(); }
export function applyLang(): void { (window as any).applyLang?.(); }
export function renderFeatures(): void { (window as any).renderFeatures?.(); }
export function _closeAllModals(): void { (window as any)._closeAllModals?.(); }
export function _closeCmdPalette(): void { (window as any)._closeCmdPalette?.(); }
export function _closeSearchModal(): void { (window as any)._closeSearchModal?.(); }
export function _storageKey(sid: string): string { return (window as any)._storageKey?.(sid) ?? ('salm_chat_' + sid); }
