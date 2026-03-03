import { useState, useEffect, useCallback, useRef, CSSProperties } from 'react';

// ── Types ─────────────────────────────────────────────────────────────────────

interface Message {
  role: 'user' | 'assistant' | 'tool';
  content: string;
  name?: string;
  tool_calls?: { name: string; arguments: unknown }[];
}

interface SubTask {
  task_id: string;
  label: string;
  description: string;
  model: string | null;
  thinking_level: string | null;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'killed';
  result: string;
  error: string;
  elapsed_s: number;
  turns_used: number;
  tokens_used: number;
  created_at: number;
  completed_at: number;
  messages?: Message[];
}

// ── Static model list (kept in sync with /api/routing available_models) ──────
const MODEL_OPTIONS = [
  { value: '', label: '⚡ auto (recommended)' },
  { value: 'sonnet',        label: '🌟 sonnet' },
  { value: 'haiku',         label: '🐦 haiku (fast)' },
  { value: 'opus',          label: '🏔️ opus (best)' },
  { value: 'gemini3flash',  label: '✨ gemini3flash (fast)' },
  { value: 'gemini3pro',    label: '✨ gemini3pro' },
  { value: 'gemini2.5flash',label: '✨ gemini2.5flash' },
  { value: 'gpt4.1',        label: '🤖 gpt4.1' },
  { value: 'gpt4.1mini',    label: '🤖 gpt4.1mini' },
  { value: 'grok4',         label: '𝕏 grok4' },
  { value: 'grok3',         label: '𝕏 grok3' },
];

// ── Auth helpers ──────────────────────────────────────────────────────────────

function getToken(): string {
  return (
    localStorage.getItem('salmalm_token') ||
    localStorage.getItem('auth_token') ||
    sessionStorage.getItem('salmalm_token') ||
    ''
  );
}
function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { 'Content-Type': 'application/json', Authorization: `Bearer ${t}` }
           : { 'Content-Type': 'application/json' };
}

// ── Utils ─────────────────────────────────────────────────────────────────────

function fmtElapsed(s: number): string {
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
}

function statusDot(status: SubTask['status']): string {
  return { running: '🟡', completed: '🟢', failed: '🔴', killed: '⚫', pending: '⚪' }[status] ?? '⚪';
}

// ── Palette (inherits CSS vars from host page) ───────────────────────────────

const C = {
  bg: 'var(--bg)',
  bg2: 'var(--bg2)',
  bg3: 'var(--bg3, #1a1a2e)',
  border: 'var(--border)',
  accent: 'var(--accent)',
  text: 'var(--text)',
  text2: 'var(--text2)',
  green: '#4caf50',
  red: '#f44336',
  yellow: '#ffc107',
};

const S: Record<string, CSSProperties> = {
  root: { display: 'flex', height: '100%', fontFamily: "'Inter','Segoe UI',system-ui,sans-serif", fontSize: 14, color: C.text, background: C.bg, overflow: 'hidden' },
  // Left pane
  left: { width: 340, minWidth: 280, display: 'flex', flexDirection: 'column', borderRight: `1px solid ${C.border}`, background: C.bg },
  header: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 14px', borderBottom: `1px solid ${C.border}` },
  title: { margin: 0, fontSize: 15, fontWeight: 700 },
  spawnForm: { padding: '12px 14px', borderBottom: `1px solid ${C.border}`, background: C.bg2, display: 'flex', flexDirection: 'column', gap: 8 },
  textarea: { width: '100%', background: C.bg, border: `1px solid ${C.border}`, borderRadius: 6, color: C.text, padding: '7px 10px', fontSize: 13, resize: 'vertical', minHeight: 64, boxSizing: 'border-box', outline: 'none' },
  row: { display: 'flex', gap: 8 },
  input: { flex: 1, background: C.bg, border: `1px solid ${C.border}`, borderRadius: 6, color: C.text, padding: '5px 9px', fontSize: 12, outline: 'none' },
  btn: { background: C.accent, border: 'none', color: '#fff', borderRadius: 6, padding: '6px 14px', fontSize: 13, fontWeight: 600, cursor: 'pointer' },
  btnSm: { background: 'transparent', border: `1px solid ${C.border}`, color: C.text2, borderRadius: 6, padding: '4px 10px', fontSize: 12, cursor: 'pointer' },
  taskList: { flex: 1, overflowY: 'auto', padding: '8px 0' },
  taskCard: { padding: '10px 14px', cursor: 'pointer', borderBottom: `1px solid ${C.border}`, transition: 'background .12s' },
  taskCardActive: { background: C.bg2 },
  taskTop: { display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 },
  taskLabel: { fontWeight: 600, fontSize: 13, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  taskMeta: { fontSize: 11, color: C.text2 },
  steerBar: { display: 'flex', gap: 6, marginTop: 7 },
  steerInput: { flex: 1, background: C.bg, border: `1px solid ${C.border}`, borderRadius: 6, color: C.text, padding: '4px 8px', fontSize: 12, outline: 'none' },
  steerBtn: { background: C.accent, border: 'none', color: '#fff', borderRadius: 6, padding: '4px 10px', fontSize: 12, cursor: 'pointer' },
  // Right pane
  right: { flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' },
  rightHeader: { padding: '12px 16px', borderBottom: `1px solid ${C.border}`, display: 'flex', alignItems: 'center', gap: 10 },
  rightTitle: { margin: 0, fontSize: 14, fontWeight: 600, flex: 1 },
  historyPane: { flex: 1, overflowY: 'auto', padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 10 },
  msgBubble: { borderRadius: 8, padding: '8px 12px', fontSize: 13, lineHeight: 1.5, maxWidth: '90%', wordBreak: 'break-word', whiteSpace: 'pre-wrap' },
  msgUser: { background: C.accent, color: '#fff', alignSelf: 'flex-end' },
  msgAssistant: { background: C.bg2, alignSelf: 'flex-start' },
  msgTool: { background: C.bg3, color: C.text2, alignSelf: 'flex-start', fontFamily: 'monospace', fontSize: 12 },
  resultBox: { margin: '12px 16px', padding: '12px', background: C.bg2, borderRadius: 8, border: `1px solid ${C.border}`, fontSize: 13, lineHeight: 1.6, whiteSpace: 'pre-wrap', wordBreak: 'break-word' },
  emptyRight: { flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: C.text2, fontSize: 13 },
  // Toast
  toast: { position: 'fixed', bottom: 20, right: 20, background: C.accent, color: '#fff', padding: '10px 18px', borderRadius: 8, fontSize: 13, fontWeight: 600, zIndex: 9999, boxShadow: '0 4px 12px rgba(0,0,0,.3)' },
};

// ── AgentPanel component ──────────────────────────────────────────────────────

export default function AgentPanel() {
  const [tasks, setTasks] = useState<SubTask[]>([]);
  const [selected, setSelected] = useState<SubTask | null>(null);
  const [detailTask, setDetailTask] = useState<SubTask | null>(null);
  const [desc, setDesc] = useState('');
  const [label, setLabel] = useState('');
  const [model, setModel] = useState('');
  const [spawning, setSpawning] = useState(false);
  const [steerInputs, setSteerInputs] = useState<Record<string, string>>({});
  const [toast, setToast] = useState('');
  const historyRef = useRef<HTMLDivElement>(null);

  // ── Fetch list ───────────────────────────────────────────────────────────

  const fetchTasks = useCallback(async () => {
    try {
      const res = await fetch('/api/subagents', { headers: authHeaders() });
      if (!res.ok) return;
      const data = await res.json();
      setTasks(data.tasks || []);
    } catch { /* ignore */ }
  }, []);

  // ── Fetch detail (with messages) ─────────────────────────────────────────

  const fetchDetail = useCallback(async (task_id: string) => {
    try {
      const res = await fetch(`/api/subagents/${task_id}`, { headers: authHeaders() });
      if (!res.ok) return;
      const data = await res.json();
      setDetailTask(data.task || null);
    } catch { /* ignore */ }
  }, []);

  // ── Auto-refresh ─────────────────────────────────────────────────────────

  useEffect(() => {
    fetchTasks();
    const id = setInterval(() => {
      fetchTasks();
      if (selected && selected.status === 'running') fetchDetail(selected.task_id);
    }, 2500);
    return () => clearInterval(id);
  }, [fetchTasks, fetchDetail, selected]);

  // Re-fetch detail when selected changes
  useEffect(() => {
    if (selected) fetchDetail(selected.task_id);
  }, [selected, fetchDetail]);

  // Scroll history to bottom
  useEffect(() => {
    if (historyRef.current) {
      historyRef.current.scrollTop = historyRef.current.scrollHeight;
    }
  }, [detailTask?.messages?.length]);

  // WS subagent_done listener
  useEffect(() => {
    const handleMsg = (e: MessageEvent) => {
      try {
        const d = typeof e.data === 'string' ? JSON.parse(e.data) : e.data;
        if (d.type === 'subagent_done') {
          fetchTasks();
          const t = d.task as SubTask;
          showToast(`${t.status === 'completed' ? '✅' : '❌'} Sub-agent "${t.label}" ${t.status}`);
          if (selected?.task_id === t.task_id) fetchDetail(t.task_id);
        }
      } catch { /* ignore */ }
    };
    // Attach to existing WS if available
    const ws = (window as Record<string, unknown>)._ws as WebSocket | undefined;
    if (ws) ws.addEventListener('message', handleMsg);
    return () => { if (ws) ws.removeEventListener('message', handleMsg); };
  }, [fetchTasks, fetchDetail, selected]);

  // ── Spawn ────────────────────────────────────────────────────────────────

  const handleSpawn = async () => {
    if (!desc.trim()) return;
    setSpawning(true);
    try {
      const res = await fetch('/api/subagents', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ description: desc.trim(), label: label.trim() || undefined, model: model.trim() || undefined }),
      });
      const data = await res.json();
      if (data.task) {
        setDesc(''); setLabel(''); setModel('');
        await fetchTasks();
        setSelected(data.task);
      }
    } finally {
      setSpawning(false);
    }
  };

  // ── Kill ─────────────────────────────────────────────────────────────────

  const handleKill = async (task_id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    await fetch(`/api/subagents/${task_id}/kill`, { method: 'POST', headers: authHeaders(), body: '{}' });
    fetchTasks();
  };

  // ── Steer ────────────────────────────────────────────────────────────────

  const handleSteer = async (task_id: string) => {
    const msg = (steerInputs[task_id] || '').trim();
    if (!msg) return;
    const res = await fetch(`/api/subagents/${task_id}/steer`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ message: msg }),
    });
    const data = await res.json();
    showToast(data.result?.slice(0, 80) || '📡 Steered');
    setSteerInputs(p => ({ ...p, [task_id]: '' }));
    if (selected?.task_id === task_id) setTimeout(() => fetchDetail(task_id), 1000);
  };

  // ── Clear ────────────────────────────────────────────────────────────────

  const handleClear = async () => {
    const res = await fetch('/api/subagents/clear', { method: 'POST', headers: authHeaders(), body: '{}' });
    const data = await res.json();
    showToast(`🗑️ Removed ${data.removed} completed tasks`);
    if (selected && ['completed','failed','killed'].includes(selected.status)) setSelected(null);
    fetchTasks();
  };

  // ── Toast ────────────────────────────────────────────────────────────────

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(''), 3500);
  };

  // ── Select task ──────────────────────────────────────────────────────────

  const handleSelect = (task: SubTask) => {
    setSelected(task);
    fetchDetail(task.task_id);
  };

  // ── Render ───────────────────────────────────────────────────────────────

  const displayTask = detailTask && selected && detailTask.task_id === selected.task_id ? detailTask : selected;
  const runningCount = tasks.filter(t => t.status === 'running').length;

  return (
    <div style={S.root}>
      {/* ── Left pane ── */}
      <div style={S.left}>
        {/* Header */}
        <div style={S.header}>
          <h3 style={S.title}>🤖 Sub-agents {runningCount > 0 && <span style={{ fontSize: 12, background: C.yellow, color: '#000', borderRadius: 10, padding: '1px 7px', marginLeft: 6 }}>{runningCount}</span>}</h3>
          <div style={{ display: 'flex', gap: 6 }}>
            <button style={S.btnSm} onClick={handleClear}>🗑️</button>
            <button style={S.btnSm} onClick={fetchTasks}>↻</button>
          </div>
        </div>

        {/* Spawn form */}
        <div style={S.spawnForm}>
          <textarea
            style={S.textarea}
            placeholder="Task description…"
            value={desc}
            onChange={e => setDesc(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && e.metaKey) handleSpawn(); }}
          />
          <div style={S.row}>
            <input style={S.input} placeholder="Label (optional)" value={label} onChange={e => setLabel(e.target.value)} />
            <select
              style={{ ...S.input, maxWidth: 160, cursor: 'pointer' }}
              value={model}
              onChange={e => setModel(e.target.value)}
            >
              {MODEL_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
          <button style={{ ...S.btn, opacity: spawning ? .6 : 1 }} onClick={handleSpawn} disabled={spawning || !desc.trim()}>
            {spawning ? '⏳ Spawning…' : '⚡ Spawn'}
          </button>
        </div>

        {/* Task list */}
        <div style={S.taskList}>
          {tasks.length === 0 && (
            <div style={{ padding: '20px', textAlign: 'center', color: C.text2, fontSize: 13 }}>No tasks yet</div>
          )}
          {tasks.map(task => {
            const isActive = selected?.task_id === task.task_id;
            return (
              <div
                key={task.task_id}
                style={{ ...S.taskCard, ...(isActive ? S.taskCardActive : {}) }}
                onClick={() => handleSelect(task)}
              >
                <div style={S.taskTop}>
                  <span>{statusDot(task.status)}</span>
                  <span style={S.taskLabel}>{task.label}</span>
                  {task.status === 'running' && (
                    <button style={{ ...S.btnSm, padding: '2px 7px', fontSize: 11, color: C.red }} onClick={e => handleKill(task.task_id, e)}>✕</button>
                  )}
                </div>
                <div style={S.taskMeta}>
                  {task.task_id} · {fmtElapsed(task.elapsed_s)}
                  {task.turns_used > 0 && ` · ${task.turns_used} turns`}
                  {task.model && ` · ${task.model.split('/').pop()}`}
                </div>
                {/* Steer bar for running tasks */}
                {task.status === 'running' && (
                  <div style={S.steerBar} onClick={e => e.stopPropagation()}>
                    <input
                      style={S.steerInput}
                      placeholder="Steer message…"
                      value={steerInputs[task.task_id] || ''}
                      onChange={e => setSteerInputs(p => ({ ...p, [task.task_id]: e.target.value }))}
                      onKeyDown={e => { if (e.key === 'Enter') handleSteer(task.task_id); }}
                    />
                    <button style={S.steerBtn} onClick={() => handleSteer(task.task_id)}>📡</button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Right pane ── */}
      <div style={S.right}>
        {!displayTask ? (
          <div style={S.emptyRight}>Select a task to view history</div>
        ) : (
          <>
            <div style={S.rightHeader}>
              <span>{statusDot(displayTask.status)}</span>
              <h4 style={S.rightTitle}>{displayTask.label}</h4>
              <span style={{ fontSize: 12, color: C.text2 }}>{fmtElapsed(displayTask.elapsed_s)} · {displayTask.turns_used} turns</span>
              {displayTask.model && <span style={{ fontSize: 11, color: C.text2, background: C.bg2, padding: '2px 7px', borderRadius: 10 }}>{displayTask.model.split('/').pop()}</span>}
            </div>

            <div style={S.historyPane} ref={historyRef}>
              {/* Show messages if available */}
              {displayTask.messages && displayTask.messages.length > 0 ? (
                displayTask.messages.map((msg, i) => (
                  <MessageBubble key={i} msg={msg} />
                ))
              ) : (
                <>
                  {/* Fallback: show description + result */}
                  <div style={{ ...S.msgBubble, ...S.msgUser }}>{displayTask.description}</div>
                  {displayTask.status === 'running' && (
                    <div style={{ ...S.msgBubble, ...S.msgAssistant, color: C.text2 }}>
                      <Spinner /> Working…
                    </div>
                  )}
                </>
              )}
              {displayTask.status === 'running' && (
                <div style={{ ...S.msgBubble, ...S.msgAssistant, color: C.text2 }}>
                  <Spinner /> Thinking…
                </div>
              )}
            </div>

            {/* Result box */}
            {displayTask.status === 'completed' && displayTask.result && (
              <div style={S.resultBox}>
                <div style={{ fontSize: 11, color: C.text2, marginBottom: 6, fontWeight: 600 }}>✅ RESULT</div>
                {displayTask.result}
              </div>
            )}
            {displayTask.status === 'failed' && displayTask.error && (
              <div style={{ ...S.resultBox, borderColor: C.red, color: C.red }}>
                <div style={{ fontSize: 11, marginBottom: 6, fontWeight: 600 }}>❌ ERROR</div>
                {displayTask.error}
              </div>
            )}
          </>
        )}
      </div>

      {/* Toast */}
      {toast && <div style={S.toast}>{toast}</div>}
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function MessageBubble({ msg }: { msg: Message }) {
  if (msg.role === 'user') {
    return <div style={{ ...S.msgBubble, ...S.msgUser }}>{msg.content}</div>;
  }
  if (msg.role === 'tool') {
    return (
      <div style={{ ...S.msgBubble, ...S.msgTool }}>
        🔧 {msg.name || 'tool'}: {msg.content?.slice(0, 300)}{(msg.content?.length ?? 0) > 300 ? '…' : ''}
      </div>
    );
  }
  // assistant
  if (msg.tool_calls && msg.tool_calls.length > 0) {
    return (
      <div style={{ ...S.msgBubble, ...S.msgAssistant }}>
        {msg.content && <div style={{ marginBottom: 6 }}>{msg.content}</div>}
        {msg.tool_calls.map((tc, i) => (
          <div key={i} style={{ fontSize: 12, color: C.text2, fontFamily: 'monospace' }}>
            ⚡ {tc.name}({typeof tc.arguments === 'object' ? JSON.stringify(tc.arguments).slice(0, 80) : String(tc.arguments).slice(0, 80)})
          </div>
        ))}
      </div>
    );
  }
  return <div style={{ ...S.msgBubble, ...S.msgAssistant }}>{msg.content}</div>;
}

function Spinner() {
  return <span style={{ display: 'inline-block', animation: 'spin 1s linear infinite', marginRight: 6 }}>⏳</span>;
}
