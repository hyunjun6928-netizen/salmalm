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
def handle_system_monitor(args: dict) -> str:
    detail = args.get("detail", "overview")
    lines = []
    try:
        if detail in ("overview", "cpu"):
            cpu_count = os.cpu_count() or 1
            try:
                load = os.getloadavg()
                lines.append(
                    f"🖥️ CPU: {cpu_count}cores, load: {load[0]:.2f} / {load[1]:.2f} / {load[2]:.2f} (1/5/15min)"
                )
            except (OSError, AttributeError):
                lines.append(f"🖥️ CPU: {cpu_count}cores")
        if detail in ("overview", "memory"):
            try:
                mem = subprocess.run(["free", "-h"], capture_output=True, text=True, timeout=5)
                if mem.stdout:
                    for l in mem.stdout.strip().split("\n"):  # noqa: E741
                        lines.append(f"💾 {l}")
            except (FileNotFoundError, OSError):
                pass
        if detail in ("overview", "disk"):
            try:
                disk = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=5)
                if disk.stdout:
                    for l in disk.stdout.strip().split("\n"):  # noqa: E741
                        lines.append(f"💿 {l}")
            except (FileNotFoundError, OSError):
                pass
        if detail in ("overview", "network"):
            try:
                net = subprocess.run(["ss", "-s"], capture_output=True, text=True, timeout=5)
                if net.stdout:
                    lines.append("🌐 Network:")
                    for l in net.stdout.strip().split("\n")[:5]:  # noqa: E741
                        lines.append(f"   {l}")
            except (FileNotFoundError, OSError):
                pass
        if detail == "processes":
            try:
                ps = subprocess.run(["ps", "aux", "--sort=-rss"], capture_output=True, text=True, timeout=5)
            except (FileNotFoundError, OSError):
                ps = None
            if ps and ps.stdout:
                for l in ps.stdout.strip().split("\n")[:20]:  # noqa: E741
                    lines.append(l)
        if detail in ("overview",):
            try:
                uptime = subprocess.run(["uptime", "-p"], capture_output=True, text=True, timeout=5)
                if uptime.stdout:
                    lines.append(f"⏱️ Uptime: {uptime.stdout.strip()}")
            except (FileNotFoundError, OSError):
                pass
            mem_mb = 0
            if _resource_mod:
                mem_mb = _resource_mod.getrusage(_resource_mod.RUSAGE_SELF).ru_maxrss / 1024
            lines.append(f"🐍 SalmAlm memory: {mem_mb:.1f}MB")
            lines.append(f"📂 Sessions: {len(_sessions)}")
    except Exception as e:
        lines.append(f"❌ Monitor error: {e}")
    return "\n".join(lines) or "No info"


@register("health_check")
def handle_health_check(args: dict) -> str:
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
