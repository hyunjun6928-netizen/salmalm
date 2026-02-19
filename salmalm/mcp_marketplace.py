# Backward-compatibility shim — real module is salmalm.features.mcp_marketplace
import importlib as _importlib, sys as _sys
_real = _importlib.import_module("salmalm.features.mcp_marketplace")
_sys.modules[__name__] = _real
