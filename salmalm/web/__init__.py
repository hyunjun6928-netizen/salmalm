# Subpackage proxy for backward compatibility
from salmalm.utils.shim import install_shim as _install_shim

_install_shim(
    __name__,
    "salmalm.web.web",
    {"web", "auth", "oauth", "templates", "ws"},
)
