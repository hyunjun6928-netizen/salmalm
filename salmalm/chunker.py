# Backward-compatibility shim — real module is salmalm.utils.chunker
import warnings as _w
_w.warn("chunker is a shim; use salmalm.utils.chunker directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.utils.chunker")
_sys.modules[__name__] = _real
