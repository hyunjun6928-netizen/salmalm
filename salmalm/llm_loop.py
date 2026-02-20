# Backward-compatibility shim — real module is salmalm.core.llm_loop
import warnings as _w; _w.warn("llm_loop is a shim; use salmalm.core.llm_loop directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.core.llm_loop")
_sys.modules[__name__] = _real
