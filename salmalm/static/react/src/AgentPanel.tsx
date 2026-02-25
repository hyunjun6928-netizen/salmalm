import { useState, useEffect, useCallback, CSSProperties } from 'react';

interface Task {
  id: string;
  description: string;
  model: string;
  status: 'pending' | 'running' | 'done' | 'failed' | 'cancelled';
  created_at: number;
  elapsed_ms: number;
  result_preview: string;
  output: string;
}

// Use main app CSS variables so agent panel respects light/dark theme
const colors = {
  bg: 'var(--bg)',
  bgCard: 'var(--bg2)',
  accent: 'var(--accent)',
  accentHover: 'var(--accent2)',
  text: 'var(--text)',
  textMuted: 'var(--text2)',
  success: 'var(--green)',
  error: 'var(--red)',
  border: 'var(--border)',
  danger: 'var(--red)',
  dangerHover: 'var(--red)',
};

const styles: Record<string, CSSProperties> = {
  container: {
    background: colors.bg,
    color: colors.text,
    fontFamily: "'Inter', 'Segoe UI', system-ui, sans-serif",
    fontSize: '14px',
    padding: '16px',
    borderRadius: '8px',
    border: `1px solid ${colors.border}`,
    minWidth: '360px',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: '16px',
  },
  title: {
    margin: 0,
    fontSize: '16px',
    fontWeight: 600,
    color: colors.text,
  },
  refreshBtn: {
    background: 'transparent',
    border: `1px solid ${colors.border}`,
    color: colors.textMuted,
    borderRadius: '6px',
    padding: '4px 10px',
    cursor: 'pointer',
    fontSize: '13px',
    transition: 'color 0.15s, border-color 0.15s',
  },
  form: {
    background: colors.bgCard,
    border: `1px solid ${colors.border}`,
    borderRadius: '8px',
    padding: '12px',
    marginBottom: '16px',
  },
  textarea: {
    width: '100%',
    background: colors.bg,
    border: `1px solid ${colors.border}`,
    borderRadius: '6px',
    color: colors.text,
    padding: '8px 10px',
    fontSize: '13px',
    resize: 'vertical',
    minHeight: '72px',
    boxSizing: 'border-box',
    outline: 'none',
    fontFamily: 'inherit',
  },
  formRow: {
    display: 'flex',
    gap: '8px',
    marginTop: '8px',
    alignItems: 'center',
  },
  select: {
    background: colors.bg,
    border: `1px solid ${colors.border}`,
    borderRadius: '6px',
    color: colors.text,
    padding: '6px 10px',
    fontSize: '13px',
    outline: 'none',
    cursor: 'pointer',
    flex: '0 0 auto',
  },
  spawnBtn: {
    background: colors.accent,
    border: 'none',
    borderRadius: '6px',
    color: 'white',
    padding: '6px 16px',
    fontSize: '13px',
    fontWeight: 600,
    cursor: 'pointer',
    flex: '1',
    transition: 'background 0.15s',
  },
  spawnBtnDisabled: {
    background: 'var(--accent-dim, rgba(99,140,255,0.3))',
    cursor: 'not-allowed',
    opacity: 0.6,
  },
  section: {
    marginBottom: '12px',
  },
  sectionTitle: {
    fontSize: '11px',
    fontWeight: 700,
    textTransform: 'uppercase' as const,
    letterSpacing: '0.08em',
    color: colors.textMuted,
    marginBottom: '8px',
    marginTop: 0,
  },
  taskCard: {
    background: colors.bgCard,
    border: `1px solid ${colors.border}`,
    borderRadius: '6px',
    padding: '10px 12px',
    marginBottom: '6px',
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '6px',
  },
  taskRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '8px',
  },
  taskDesc: {
    color: colors.text,
    fontSize: '13px',
    flex: 1,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  },
  taskMeta: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    flexShrink: 0,
  },
  modelBadge: {
    background: 'var(--accent-dim, rgba(99,140,255,0.15))',
    color: 'var(--accent)',
    borderRadius: '4px',
    padding: '2px 6px',
    fontSize: '11px',
    fontWeight: 600,
    textTransform: 'capitalize' as const,
  },
  elapsed: {
    color: colors.textMuted,
    fontSize: '12px',
    flexShrink: 0,
  },
  spinner: {
    display: 'inline-block',
    width: '14px',
    height: '14px',
    border: `2px solid ${colors.border}`,
    borderTopColor: colors.accent,
    borderRadius: '50%',
    flexShrink: 0,
  },
  killBtn: {
    background: 'transparent',
    border: `1px solid ${colors.danger}`,
    color: colors.error,
    borderRadius: '4px',
    padding: '2px 8px',
    fontSize: '12px',
    cursor: 'pointer',
    flexShrink: 0,
  },
  viewBtn: {
    background: 'transparent',
    border: `1px solid ${colors.border}`,
    color: colors.textMuted,
    borderRadius: '4px',
    padding: '2px 8px',
    fontSize: '12px',
    cursor: 'pointer',
    flexShrink: 0,
  },
  emptyState: {
    color: colors.textMuted,
    fontSize: '13px',
    textAlign: 'center' as const,
    padding: '12px 0',
    fontStyle: 'italic',
  },
  errorMsg: {
    color: colors.error,
    fontSize: '12px',
    marginTop: '6px',
  },
  // Modal
  modalOverlay: {
    position: 'fixed' as const,
    inset: 0,
    background: 'rgba(0,0,0,0.7)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 9999,
  },
  modalBox: {
    background: colors.bgCard,
    border: `1px solid ${colors.border}`,
    borderRadius: '10px',
    width: '90vw',
    maxWidth: '640px',
    maxHeight: '80vh',
    display: 'flex',
    flexDirection: 'column' as const,
    overflow: 'hidden',
  },
  modalHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '12px 16px',
    borderBottom: `1px solid ${colors.border}`,
  },
  modalTitle: {
    color: colors.text,
    fontWeight: 600,
    fontSize: '14px',
    margin: 0,
  },
  modalCloseBtn: {
    background: 'transparent',
    border: 'none',
    color: colors.textMuted,
    fontSize: '18px',
    cursor: 'pointer',
    lineHeight: 1,
    padding: '0 4px',
  },
  modalBody: {
    overflowY: 'auto' as const,
    padding: '16px',
    flex: 1,
  },
  outputPre: {
    background: colors.bg,
    border: `1px solid ${colors.border}`,
    borderRadius: '6px',
    padding: '12px',
    color: colors.text,
    fontSize: '12px',
    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
    whiteSpace: 'pre-wrap' as const,
    wordBreak: 'break-all' as const,
    margin: 0,
    lineHeight: 1.6,
  },
};

function formatElapsed(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  const m = Math.floor(ms / 60000);
  const s = Math.floor((ms % 60000) / 1000);
  return `${m}m ${s}s`;
}

function truncate(str: string, n: number): string {
  return str.length > n ? str.slice(0, n) + '…' : str;
}

function getToken(): string {
  return (window as any)._tok || localStorage.getItem('session_token') || '';
}

function authHeaders() {
  return {
    'Content-Type': 'application/json',
    'X-Session-Token': getToken(),
  };
}

// Spinner with keyframe animation injected once
let spinnerStyleInjected = false;
function ensureSpinnerStyle() {
  if (spinnerStyleInjected) return;
  spinnerStyleInjected = true;
  const s = document.createElement('style');
  s.textContent = `@keyframes _salmalm_spin { to { transform: rotate(360deg); } }`;
  document.head.appendChild(s);
}

interface OutputModalProps {
  task: Task;
  onClose: () => void;
}

function OutputModal({ task, onClose }: OutputModalProps) {
  return (
    <div style={styles.modalOverlay} onClick={onClose}>
      <div style={styles.modalBox} onClick={e => e.stopPropagation()}>
        <div style={styles.modalHeader}>
          <p style={styles.modalTitle}>Task Output — {truncate(task.description, 60)}</p>
          <button style={styles.modalCloseBtn} onClick={onClose}>×</button>
        </div>
        <div style={styles.modalBody}>
          <pre style={styles.outputPre}>{task.output || task.result_preview || '(no output)'}</pre>
        </div>
      </div>
    </div>
  );
}

export default function AgentPanel() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [description, setDescription] = useState('');
  const [model, setModel] = useState('auto');
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const [viewTask, setViewTask] = useState<Task | null>(null);

  useEffect(() => {
    ensureSpinnerStyle();
  }, []);

  const fetchTasks = useCallback(async () => {
    try {
      const res = await fetch('/api/agent/tasks', { headers: authHeaders() });
      if (res.ok) {
        const data = await res.json();
        setTasks(data.tasks ?? []);
      }
    } catch {
      // silently ignore network errors during polling
    }
  }, []);

  useEffect(() => {
    fetchTasks();
    const id = setInterval(fetchTasks, 3000);
    return () => clearInterval(id);
  }, [fetchTasks]);

  const handleSpawn = async () => {
    if (!description.trim()) return;
    setSubmitting(true);
    setSubmitError('');
    try {
      const res = await fetch('/api/agent/task', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ description: description.trim(), model }),
      });
      const data = await res.json();
      if (data.ok) {
        setDescription('');
        await fetchTasks();
      } else {
        setSubmitError(data.error || 'Failed to spawn agent');
      }
    } catch (err: any) {
      setSubmitError(err?.message || 'Network error');
    } finally {
      setSubmitting(false);
    }
  };

  const handleKill = async (id: string) => {
    try {
      await fetch(`/api/agent/task/${id}`, {
        method: 'DELETE',
        headers: authHeaders(),
      });
      await fetchTasks();
    } catch {
      // ignore
    }
  };

  const activeTasks = tasks.filter(t => t.status === 'running' || t.status === 'pending');
  const completedTasks = tasks.filter(t => t.status === 'done' || t.status === 'failed' || t.status === 'cancelled');

  return (
    <div style={styles.container}>
      {/* Header */}
      <div style={styles.header}>
        <h2 style={styles.title}>🤖 Agent Tasks</h2>
        <button style={styles.refreshBtn} onClick={fetchTasks}>↻ Refresh</button>
      </div>

      {/* Create Task Form */}
      <div style={styles.form}>
        <textarea
          style={styles.textarea}
          value={description}
          onChange={e => setDescription(e.target.value)}
          placeholder="Describe what you want the agent to do..."
          rows={3}
          onKeyDown={e => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) handleSpawn();
          }}
        />
        <div style={styles.formRow}>
          <select
            style={styles.select}
            value={model}
            onChange={e => setModel(e.target.value)}
          >
            <option value="auto">auto</option>
            <optgroup label="── Anthropic ──">
              <option value="haiku">haiku</option>
              <option value="sonnet">sonnet</option>
              <option value="opus">opus</option>
            </optgroup>
            <optgroup label="── OpenAI ──">
              <option value="gpt-4o-mini">gpt-4o-mini</option>
              <option value="gpt-4o">gpt-4o</option>
              <option value="gpt">gpt (5.2)</option>
            </optgroup>
            <optgroup label="── Google ──">
              <option value="gemini-2.0-flash">gemini-flash</option>
              <option value="gemini-2.5-pro-preview-03-25">gemini-pro</option>
            </optgroup>
            <optgroup label="── xAI ──">
              <option value="grok-3-mini">grok-mini</option>
              <option value="grok-3">grok-3</option>
            </optgroup>
          </select>
          <button
            style={{ ...styles.spawnBtn, ...(submitting ? styles.spawnBtnDisabled : {}) }}
            disabled={submitting}
            onClick={handleSpawn}
          >
            {submitting ? 'Spawning…' : '⚡ Spawn Agent'}
          </button>
        </div>
        {submitError && <p style={styles.errorMsg}>⚠ {submitError}</p>}
      </div>

      {/* Active Tasks */}
      <div style={styles.section}>
        <p style={styles.sectionTitle}>⚙ Active ({activeTasks.length})</p>
        {activeTasks.length === 0 ? (
          <p style={styles.emptyState}>No active tasks — spawn one above!</p>
        ) : (
          activeTasks.map(task => (
            <div key={task.id} style={styles.taskCard}>
              <div style={styles.taskRow}>
                <span
                  style={{
                    ...styles.spinner,
                    animation: '_salmalm_spin 0.8s linear infinite',
                  }}
                />
                <span style={styles.taskDesc}>{truncate(task.description, 80)}</span>
                <div style={styles.taskMeta}>
                  <span style={styles.modelBadge}>{task.model}</span>
                  <span style={styles.elapsed}>{formatElapsed(task.elapsed_ms)}</span>
                  <button style={styles.killBtn} onClick={() => handleKill(task.id)}>
                    Kill
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Completed Tasks */}
      <div style={styles.section}>
        <p style={styles.sectionTitle}>✓ Completed ({completedTasks.length})</p>
        {completedTasks.length === 0 ? (
          <p style={styles.emptyState}>Completed tasks will appear here.</p>
        ) : (
          completedTasks.map(task => (
            <div key={task.id} style={styles.taskCard}>
              <div style={styles.taskRow}>
                <span style={{ fontSize: '15px', flexShrink: 0 }}>
                  {task.status === 'done' ? '✅' : '❌'}
                </span>
                <span style={styles.taskDesc}>{truncate(task.description, 80)}</span>
                <div style={styles.taskMeta}>
                  <span style={styles.modelBadge}>{task.model}</span>
                  <span style={styles.elapsed}>{formatElapsed(task.elapsed_ms)}</span>
                  <button style={styles.viewBtn} onClick={() => setViewTask(task)}>
                    View Output
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Output Modal */}
      {viewTask && (
        <OutputModal task={viewTask} onClose={() => setViewTask(null)} />
      )}
    </div>
  );
}
