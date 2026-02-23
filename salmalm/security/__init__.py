# Subpackage proxy for backward compatibility
import importlib as _importlib
import sys as _sys
import types as _types

_real_mod = None
_SUBMODULES = {"security", "crypto", "exec_approvals", "sandbox", "container"}


def _get_real():
    """Get real."""
    global _real_mod
    if _real_mod is None:
        _real_mod = _importlib.import_module("salmalm.security.security")
    return _real_mod


class _PkgProxy(_types.ModuleType):
    def __getattr__(self, name):
        return getattr(_get_real(), name)

    def __setattr__(self, name, value):
        if name.startswith("_") or name in _SUBMODULES:
            super().__setattr__(name, value)
        else:
            setattr(_get_real(), name, value)

    def __delattr__(self, name):
        delattr(_get_real(), name)


_proxy = _PkgProxy(__name__)
_proxy.__path__ = __path__
_proxy.__file__ = __file__
_proxy.__package__ = __package__
_proxy.__spec__ = __spec__
_sys.modules[__name__] = _proxy
