# Backward-compatibility shim — real module is salmalm.core.session_manager
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.core.session_manager")
_sys.modules[__name__] = _real
