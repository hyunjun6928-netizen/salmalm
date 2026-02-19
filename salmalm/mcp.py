# Backward-compatibility shim — real module is salmalm.features.mcp
import importlib as _importlib, sys as _sys
_real = _importlib.import_module("salmalm.features.mcp")
_sys.modules[__name__] = _real
