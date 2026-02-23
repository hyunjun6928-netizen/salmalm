# Subpackage proxy for backward compatibility
from salmalm.utils.shim import install_shim as _install_shim

_install_shim(
    __name__,
    "salmalm.tools.tools",
    {
        "tools", "tool_handlers", "tool_registry",
        "tools_agent", "tools_brave", "tools_browser", "tools_calendar",
        "tools_common", "tools_email", "tools_exec", "tools_file",
        "tools_google", "tools_media", "tools_memory", "tools_misc",
        "tools_patch", "tools_personal", "tools_reaction", "tools_reminder",
        "tools_system", "tools_util", "tools_web",
    },
)
