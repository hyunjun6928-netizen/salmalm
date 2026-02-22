# Backward-compatibility shim — real module is salmalm.utils.queue
import warnings as _w

_w.warn("queue is a shim; use salmalm.utils.queue directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys

_real = _importlib.import_module("salmalm.utils.queue")
_sys.modules[__name__] = _real
