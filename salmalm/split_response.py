# Backward-compatibility shim — real module is salmalm.features.split_response
import warnings as _w

_w.warn("split_response is a shim; use salmalm.features.split_response directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys

_real = _importlib.import_module("salmalm.features.split_response")
_sys.modules[__name__] = _real
