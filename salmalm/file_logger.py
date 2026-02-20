# Backward-compatibility shim — real module is salmalm.utils.file_logger
import warnings as _w; _w.warn("file_logger is a shim; use salmalm.utils.file_logger directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.utils.file_logger")
_sys.modules[__name__] = _real
