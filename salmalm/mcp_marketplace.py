# Backward-compatibility shim — real module is salmalm.features.mcp_marketplace
import warnings as _w

_w.warn("mcp_marketplace is a shim; use salmalm.features.mcp_marketplace directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys

_real = _importlib.import_module("salmalm.features.mcp_marketplace")
_sys.modules[__name__] = _real
