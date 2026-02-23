"""Workflow Engine — multi-step automation pipelines with variable substitution.

Workflows are JSON files stored in ~/.salmalm/workflows/.
Supports: variable substitution, conditionals, parallel steps, error handling,
triggers (cron, manual, webhook, event).
"""

from salmalm.security.crypto import log
import json
import re
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from salmalm.constants import KST, DATA_DIR
WORKFLOWS_DIR = DATA_DIR / "workflows"
WORKFLOW_LOG_DIR = WORKFLOWS_DIR / "logs"


def _ensure_dirs():
    """Ensure dirs."""
    WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
    WORKFLOW_LOG_DIR.mkdir(parents=True, exist_ok=True)


# ── Variable Substitution ────────────────────────────────────

_VAR_RE = re.compile(r"\{\{(\w+)\.(\w+)\}\}")


def _substitute(template: str, context: Dict[str, Any]) -> str:
    """Replace {{step_id.field}} with values from context."""

    def _repl(m):
        """Repl."""
        step_id, field = m.group(1), m.group(2)
        step_data = context.get(step_id, {})
        if isinstance(step_data, dict):
            return str(step_data.get(field, m.group(0)))
        return str(step_data)

    return _VAR_RE.sub(_repl, template)


def _substitute_params(params: dict, context: Dict[str, Any]) -> dict:
    """Deep-substitute all string values in params dict."""
    result = {}
    for k, v in params.items():
        if isinstance(v, str):
            result[k] = _substitute(v, context)
        elif isinstance(v, dict):
            result[k] = _substitute_params(v, context)
        else:
            result[k] = v
    return result


# ── Condition Evaluation ─────────────────────────────────────


def _eval_condition(cond: str, context: Dict[str, Any]) -> bool:
    """Evaluate simple condition like '{{step.count}} > 0'."""
    resolved = _substitute(cond, context)
    try:
        # Only allow simple comparisons
        resolved = resolved.strip()
        for op in [">=", "<=", "!=", "==", ">", "<"]:
            if op in resolved:
                parts = resolved.split(op, 1)
                left = _to_num(parts[0].strip())
                right = _to_num(parts[1].strip())
                if op == ">":
                    return left > right
                if op == "<":
                    return left < right
                if op == ">=":
                    return left >= right
                if op == "<=":
                    return left <= right
                if op == "==":
                    return left == right
                if op == "!=":
                    return left != right
        return bool(resolved)
    except Exception as e:  # noqa: broad-except
        return False


def _to_num(s: str):
    """To num."""
    try:
        return float(s)
    except (ValueError, TypeError):
        return s


# ── Step Execution ───────────────────────────────────────────


class StepResult:
    def __init__(self, step_id: str, success: bool, result: Any = None, error: str = "") -> None:
        """Init  ."""
        self.step_id = step_id
        self.success = success
        self.result = result
        self.error = error

    def to_dict(self) -> dict:
        """To dict."""
        return {"step_id": self.step_id, "success": self.success, "result": self.result, "error": self.error}


class WorkflowEngine:
    """Execute multi-step workflows with variable substitution."""

    def __init__(self, tool_executor=None) -> None:
        """Init  ."""
        _ensure_dirs()
        self._tool_executor = tool_executor  # callable(tool_name, params) -> result
        self._lock = threading.Lock()

    # ── Workflow CRUD ────────────────────────────────────────

    def list_workflows(self) -> List[dict]:
        """List workflows."""
        _ensure_dirs()
        workflows = []
        for f in WORKFLOWS_DIR.glob("*.json"):
            if f.name == "logs":
                continue
            try:
                with open(f) as fh:
                    wf = json.load(fh)
                    workflows.append(
                        {
                            "name": wf.get("name", f.stem),
                            "trigger": wf.get("trigger", {}),
                            "steps": len(wf.get("steps", [])),
                        }
                    )
            except Exception as e:  # noqa: broad-except
                log.debug(f"Suppressed: {e}")
        return workflows

    def get_workflow(self, name: str) -> Optional[dict]:
        """Get workflow."""
        path = WORKFLOWS_DIR / f"{name}.json"
        if not path.exists():
            return None
        with open(path) as f:
            return json.load(f)

    def save_workflow(self, workflow: dict) -> str:
        """Save workflow."""
        _ensure_dirs()
        name = workflow.get("name", "")
        if not name:
            return "❌ workflow name is required"
        path = WORKFLOWS_DIR / f"{name}.json"
        with open(path, "w") as f:
            json.dump(workflow, f, ensure_ascii=False, indent=2)
        return f"✅ 워크플로우 저장됨: {name}"

    def delete_workflow(self, name: str) -> str:
        """Delete workflow."""
        path = WORKFLOWS_DIR / f"{name}.json"
        if not path.exists():
            return f"❌ 워크플로우 없음: {name}"
        path.unlink()
        return f"🗑️ 워크플로우 삭제됨: {name}"

    # ── Execution ────────────────────────────────────────────

    def run(self, name: str) -> dict:
        """Run."""
        wf = self.get_workflow(name)
        if not wf:
            return {"success": False, "error": f"Workflow not found: {name}"}
        return self.execute(wf)

    def execute(self, workflow: dict) -> dict:
        """Execute."""
        steps = workflow.get("steps", [])
        on_error = workflow.get("on_error", "stop")
        context: Dict[str, Any] = {}
        results: List[dict] = []
        started = datetime.now(KST).isoformat()

        for step in steps:
            # Handle parallel steps
            if "parallel" in step:
                parallel_results = self._run_parallel(step["parallel"], context)
                for pr in parallel_results:
                    context[pr["step_id"]] = {"result": pr.get("result", ""), "count": 1 if pr["success"] else 0}
                    results.append(pr)
                continue

            step_id = step.get("id", f"step_{len(results)}")
            # Check condition
            cond = step.get("if")
            if cond and not _eval_condition(cond, context):
                results.append({"step_id": step_id, "success": True, "result": "skipped (condition false)"})
                context[step_id] = {"result": "skipped", "count": 0}
                continue

            sr = self._execute_step(step, context)
            results.append(sr.to_dict())
            context[step_id] = {"result": sr.result or "", "count": 1 if sr.success else 0}

            if not sr.success:
                if on_error == "stop":
                    break
                elif on_error == "retry":
                    sr2 = self._execute_step(step, context)
                    results.append(sr2.to_dict())
                    context[step_id] = {"result": sr2.result or "", "count": 1 if sr2.success else 0}
                    if not sr2.success and on_error == "stop":
                        break

        run_result = {
            "workflow": workflow.get("name", "unnamed"),
            "success": all(r.get("success", False) for r in results),
            "started": started,
            "finished": datetime.now(KST).isoformat(),
            "results": results,
        }
        self._log_run(workflow.get("name", "unnamed"), run_result)
        return run_result

    def _execute_step(self, step: dict, context: Dict[str, Any]) -> StepResult:
        """Execute step."""
        step_id = step.get("id", "unknown")
        tool = step.get("tool", "")
        params = _substitute_params(step.get("params", {}), context)

        if not self._tool_executor:
            return StepResult(step_id, False, error="No tool executor configured")
        try:
            result = self._tool_executor(tool, params)
            return StepResult(step_id, True, result=result)
        except Exception as e:
            return StepResult(step_id, False, error=str(e))

    def _run_parallel(self, steps: list, context: Dict[str, Any]) -> List[dict]:
        """Run parallel."""
        results = []
        threads = []
        result_map = {}

        def _run(s):
            """Run."""
            sr = self._execute_step(s, context)
            result_map[s.get("id", "unknown")] = sr.to_dict()

        for s in steps:
            t = threading.Thread(target=_run, args=(s,))
            threads.append(t)
            t.start()
        for t in threads:
            t.join(timeout=30)
        for s in steps:
            sid = s.get("id", "unknown")
            results.append(result_map.get(sid, {"step_id": sid, "success": False, "error": "timeout"}))
        return results

    # ── Logging ──────────────────────────────────────────────

    def _log_run(self, name: str, result: dict):
        """Log run."""
        try:
            _ensure_dirs()
            log_path = WORKFLOW_LOG_DIR / f"{name}.jsonl"
            with open(log_path, "a") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
        except Exception as e:  # noqa: broad-except
            log.debug(f"Suppressed: {e}")

    def get_logs(self, name: str, limit: int = 10) -> List[dict]:
        """Get logs."""
        log_path = WORKFLOW_LOG_DIR / f"{name}.jsonl"
        if not log_path.exists():
            return []
        lines = log_path.read_text().strip().split("\n")
        results = []
        for line in lines[-limit:]:
            try:
                results.append(json.loads(line))
            except Exception as e:  # noqa: broad-except
                log.debug(f"Suppressed: {e}")
        return results

    # ── Presets ──────────────────────────────────────────────

    def get_presets(self) -> List[dict]:
        """Get presets."""
        return [
            {
                "name": "morning_briefing",
                "description": "아침 이메일+캘린더+날씨 종합",
                "trigger": {"type": "cron", "schedule": "0 8 * * *"},
                "steps": [
                    {"id": "cal", "tool": "calendar_list", "params": {"period": "today"}},
                    {"id": "brief", "tool": "send_message", "params": {"message": "☀️ 오늘 일정:\n{{cal.result}}"}},
                ],
                "on_error": "skip",
            },
            {
                "name": "expense_report",
                "description": "월말 가계부 리포트 생성",
                "trigger": {"type": "cron", "schedule": "0 20 L * *"},
                "steps": [
                    {"id": "expenses", "tool": "expense", "params": {"action": "list", "period": "month"}},
                    {
                        "id": "report",
                        "tool": "send_message",
                        "params": {"message": "💰 월간 리포트:\n{{expenses.result}}"},
                    },
                ],
                "on_error": "stop",
            },
            {
                "name": "backup_memories",
                "description": "주간 메모리 파일 백업",
                "trigger": {"type": "cron", "schedule": "0 2 * * 0"},
                "steps": [
                    {
                        "id": "backup",
                        "tool": "exec",
                        "params": {"command": "tar czf ~/.salmalm/backup_$(date +%Y%m%d).tar.gz ~/.salmalm/memory/"},
                    },
                ],
                "on_error": "stop",
            },
        ]

    def install_preset(self, name: str) -> str:
        """Install preset."""
        for p in self.get_presets():
            if p["name"] == name:
                return self.save_workflow(p)
        return f"❌ 프리셋 없음: {name}"


# ── Chat Command Handler ─────────────────────────────────────


def handle_workflow_command(text: str) -> str:
    """Handle workflow command."""
    engine = WorkflowEngine()
    parts = text.strip().split(None, 2)
    sub = parts[1] if len(parts) > 1 else "list"

    if sub == "list":
        wfs = engine.list_workflows()
        if not wfs:
            return "📋 등록된 워크플로우가 없습니다."
        lines = ["📋 **워크플로우 목록**"]
        for w in wfs:
            lines.append(f"  • **{w['name']}** — {w['steps']}단계, 트리거: {w['trigger'].get('type', 'manual')}")
        return "\n".join(lines)

    if sub == "run":
        name = parts[2] if len(parts) > 2 else ""
        if not name:
            return "❌ 사용법: /workflow run <name>"
        result = engine.run(name)
        if result.get("success"):
            return f'✅ 워크플로우 "{name}" 실행 완료'
        return f'❌ 워크플로우 "{name}" 실행 실패: {result.get("error", "")}'

    if sub == "delete":
        name = parts[2] if len(parts) > 2 else ""
        if not name:
            return "❌ 사용법: /workflow delete <name>"
        return engine.delete_workflow(name)

    if sub == "log":
        name = parts[2] if len(parts) > 2 else ""
        if not name:
            return "❌ 사용법: /workflow log <name>"
        logs = engine.get_logs(name)
        if not logs:
            return f'📜 "{name}" 실행 이력 없음'
        lines = [f'📜 **"{name}" 실행 이력** ({len(logs)}건)']
        for lg in logs[-5:]:
            status = "✅" if lg.get("success") else "❌"
            lines.append(f"  {status} {lg.get('started', '?')} → {lg.get('finished', '?')}")
        return "\n".join(lines)

    if sub == "presets":
        presets = engine.get_presets()
        lines = ["📦 **워크플로우 프리셋**"]
        for p in presets:
            lines.append(f"  • **{p['name']}** — {p['description']}")
        lines.append("\n설치: /workflow install <name>")
        return "\n".join(lines)

    if sub == "install":
        name = parts[2] if len(parts) > 2 else ""
        if not name:
            return "❌ 사용법: /workflow install <name>"
        return engine.install_preset(name)

    return "❓ 사용법: /workflow [list|run|delete|log|presets|install] [name]"
