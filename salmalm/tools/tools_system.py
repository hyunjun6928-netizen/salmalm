"""System tools: system_monitor, health_check."""

import os
import subprocess
from salmalm.tools.tool_registry import register
from salmalm.core import _sessions

try:
    import resource as _resource_mod
except ImportError:
    _resource_mod = None


@register("system_monitor")
def _collect_cpu() -> list:
    """Collect CPU info."""
    cpu_count = os.cpu_count() or 1
    try:
        load = os.getloadavg()
        return [f"🖥️ CPU: {cpu_count}cores, load: {load[0]:.2f} / {load[1]:.2f} / {load[2]:.2f} (1/5/15min)"]
    except (OSError, AttributeError):
        return [f"🖥️ CPU: {cpu_count}cores"]


def _collect_cmd(cmd: list, prefix: str, max_lines: int = 99) -> list:
    """Run a command and return prefixed output lines."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.stdout:
            return [f"{prefix} {l}" for l in result.stdout.strip().split("\n")[:max_lines]]
    except (FileNotFoundError, OSError):
        pass
    return []


def _collect_salmalm_stats() -> list:
    """Collect SalmAlm process stats."""
    lines = _collect_cmd(["uptime", "-p"], "⏱️ Uptime:")
    mem_mb = _resource_mod.getrusage(_resource_mod.RUSAGE_SELF).ru_maxrss / 1024 if _resource_mod else 0
    lines.append(f"🐍 SalmAlm memory: {mem_mb:.1f}MB")
    lines.append(f"📂 Sessions: {len(_sessions)}")
    return lines


_MONITOR_COLLECTORS = {
    "cpu": _collect_cpu,
    "memory": lambda: _collect_cmd(["free", "-h"], "💾"),
    "disk": lambda: _collect_cmd(["df", "-h", "/"], "💿"),
    "network": lambda: (
        (["🌐 Network:"] + _collect_cmd(["ss", "-s"], "  ", 5)) if _collect_cmd(["ss", "-s"], "", 1) else []
    ),
}


def handle_system_monitor(args: dict) -> str:
    """Handle system monitor."""
    detail = args.get("detail", "overview")
    lines = []
    try:
        if detail == "processes":
            lines.extend(_collect_cmd(["ps", "aux", "--sort=-rss"], "", 20))
        elif detail in _MONITOR_COLLECTORS:
            lines.extend(_MONITOR_COLLECTORS[detail]())
        else:  # overview
            for collector in _MONITOR_COLLECTORS.values():
                lines.extend(collector())
            lines.extend(_collect_salmalm_stats())
    except Exception as e:
        lines.append(f"❌ Monitor error: {e}")
    return "\n".join(lines) or "No info"


@register("health_check")
def handle_health_check(args: dict) -> str:
    """Handle health check."""
    from salmalm.features.stability import health_monitor

    action = args.get("action", "check")
    if action == "check":
        report = health_monitor.check_health()
        lines = [f"🏥 **System status: {report['status'].upper()}**", f"⏱️ Uptime: {report['uptime_human']}"]
        sys_info = report.get("system", {})
        if sys_info.get("memory_mb"):
            lines.append(f"💾 Memory: {sys_info['memory_mb']}MB")
        if sys_info.get("disk_free_mb"):
            lines.append(f"💿 Disk: {sys_info['disk_free_mb']}MB free ({sys_info.get('disk_pct', 0)}% used)")
        lines.append(f"🧵 Threads: {sys_info.get('threads', '?')}")
        lines.append("")
        for comp, status in report["components"].items():
            icon = "✅" if status.get("status") == "ok" else "⚠️" if status.get("status") != "error" else "❌"
            lines.append(f"  {icon} {comp}: {status.get('status', '?')}")
        return "\n".join(lines)
    elif action == "selftest":
        result = health_monitor.startup_selftest()
        lines = [f"🧪 **Self-test: {result['passed']}/{result['total']}**"]
        for mod, status in result["modules"].items():
            icon = "✅" if status == "ok" else "❌"
            lines.append(f"  {icon} {mod}: {status}")
        return "\n".join(lines)
    elif action == "recover":
        import asyncio

        try:
            _loop = asyncio.get_running_loop()  # noqa: F841
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(1) as pool:
                recovered = pool.submit(lambda: asyncio.run(health_monitor.auto_recover())).result(timeout=30)
        except RuntimeError:
            recovered = asyncio.run(health_monitor.auto_recover())
        if recovered:
            return f"🔧 Recovery completed: {', '.join(recovered)}"
        return "🔧 No components need recovery (all OK)"
    return f"❌ Unknown action: {action}"
