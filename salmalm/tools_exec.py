# Backward-compatibility shim — real module is salmalm.tools.tools_exec
import importlib as _importlib, sys as _sys
_real = _importlib.import_module("salmalm.tools.tools_exec")
_sys.modules[__name__] = _real
