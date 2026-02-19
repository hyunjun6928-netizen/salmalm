# Backward-compatibility shim — real module is salmalm.tools.tool_handlers
import importlib as _importlib, sys as _sys
_real = _importlib.import_module("salmalm.tools.tool_handlers")
_sys.modules[__name__] = _real
