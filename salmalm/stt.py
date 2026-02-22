# Backward-compatibility shim — real module is salmalm.features.stt
import warnings as _w

_w.warn("stt is a shim; use salmalm.features.stt directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys

_real = _importlib.import_module("salmalm.features.stt")
_sys.modules[__name__] = _real
