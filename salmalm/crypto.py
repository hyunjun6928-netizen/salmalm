# Backward-compatibility shim — real module is salmalm.security.crypto
import warnings as _w
_w.warn("crypto is a shim; use salmalm.security.crypto directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.security.crypto")
_sys.modules[__name__] = _real
