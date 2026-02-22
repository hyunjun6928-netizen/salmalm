# Backward-compatibility shim — real module is salmalm.features.doctor
import warnings as _w

_w.warn("doctor is a shim; use salmalm.features.doctor directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys

_real = _importlib.import_module("salmalm.features.doctor")
_sys.modules[__name__] = _real
