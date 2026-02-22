"""Sandbox exec tool handler. / 샌드박스 실행 도구 핸들러."""

from salmalm.tools.tool_registry import register


@register("sandbox_exec")
def handle_sandbox_exec(args: dict) -> str:
    """Execute a command in OS-native sandbox. / OS 기본 샌드박스에서 명령 실행."""
    from salmalm.security.sandbox import sandbox_exec

    command = args.get("command", "")
    if not command:
        return "❌ command is required / command를 입력하세요"

    timeout = min(args.get("timeout", 30), 120)
    allow_network = args.get("allow_network", False)
    memory_mb = min(args.get("memory_mb", 512), 2048)

    result = sandbox_exec(
        command,
        timeout=timeout,
        allow_network=allow_network,
        memory_mb=memory_mb,
    )

    output = result.get("stdout", "") or "(no output)"
    if result.get("stderr"):
        output += f"\n[stderr]: {result['stderr']}"
    if result["exit_code"] != 0:
        output += f"\n[exit code]: {result['exit_code']}"
    output += f"\n[sandbox: {result['method']} ({result['sandbox_level']})]"
    return output
