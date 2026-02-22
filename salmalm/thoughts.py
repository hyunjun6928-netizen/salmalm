# Backward-compatibility shim — real module is salmalm.features.thoughts
import warnings as _w

_w.warn("thoughts is a shim; use salmalm.features.thoughts directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys

_real = _importlib.import_module("salmalm.features.thoughts")
_sys.modules[__name__] = _real
