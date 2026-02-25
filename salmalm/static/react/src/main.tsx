import { createRoot } from 'react-dom/client';
import AgentPanel from './AgentPanel';

const mount = () => {
  const el = document.getElementById('agent-panel-root');
  if (el) createRoot(el).render(<AgentPanel />);
};

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', mount);
} else {
  mount();
}
