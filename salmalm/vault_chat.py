# Backward-compatibility shim — real module is salmalm.features.vault_chat
import warnings as _w
_w.warn("vault_chat is a shim; use salmalm.features.vault_chat directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.features.vault_chat")
_sys.modules[__name__] = _real
