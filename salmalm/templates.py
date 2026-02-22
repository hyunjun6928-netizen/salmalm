# Backward-compatibility shim — real module is salmalm.web.templates
import warnings as _w

_w.warn("templates is a shim; use salmalm.web.templates directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys

_real = _importlib.import_module("salmalm.web.templates")
_sys.modules[__name__] = _real
