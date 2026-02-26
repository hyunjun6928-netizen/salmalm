"""Shared subpackage proxy shim for backward compatibility.

Reduces duplicate boilerplate across security/, web/, tools/ __init__.py.
"""

import importlib
import sys
import types
import warnings


def install_shim(package_name: str, real_module: str, submodules: set) -> None:
    """Install a lazy-loading proxy module for backward compat imports.

    Args:
        package_name: The package being shimmed (e.g. 'salmalm.security')
        real_module: The actual module to delegate to (e.g. 'salmalm.security.security')
        submodules: Set of submodule names that should not be proxied
    """
    _real_mod = None

    def _get_real():
        nonlocal _real_mod
        if _real_mod is None:
            _real_mod = importlib.import_module(real_module)
        return _real_mod

    short_name = package_name.rsplit(".", 1)[-1]
    _warned = [False]

    def _warn_once():
        if not _warned[0]:
            _warned[0] = True
            warnings.warn(
                f"{short_name} is a shim; use {real_module} directly",
                DeprecationWarning,
                stacklevel=4,
            )

    class _PkgProxy(types.ModuleType):
        def __getattr__(self, name: str):
            # Only warn when actually proxying attribute access to the real module
            # (not for submodule imports like salmalm.web.auth which are legitimate)
            if not name.startswith("_") and name not in submodules:
                _warn_once()
            return getattr(_get_real(), name)

        def __setattr__(self, name: str, value: str):
            if name.startswith("_") or name in submodules:
                super().__setattr__(name, value)
            else:
                setattr(_get_real(), name, value)

        def __delattr__(self, name: str):
            delattr(_get_real(), name)

    old = sys.modules[package_name]
    proxy = _PkgProxy(package_name)
    proxy.__path__ = old.__path__
    proxy.__package__ = old.__package__
    proxy.__file__ = old.__file__
    proxy.__loader__ = old.__loader__
    proxy.__spec__ = old.__spec__
    sys.modules[package_name] = proxy
    # NOTE: warning is now deferred to first actual shim access,
    # not emitted on import of legitimate submodules (e.g. salmalm.web.auth).
