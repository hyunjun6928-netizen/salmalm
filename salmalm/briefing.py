# Backward-compatibility shim — real module is salmalm.features.briefing
import warnings as _w

_w.warn("briefing is a shim; use salmalm.features.briefing directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys

_real = _importlib.import_module("salmalm.features.briefing")
_sys.modules[__name__] = _real
