# Backward-compatibility shim — real module is salmalm.core.llm_task
import warnings as _w
_w.warn("llm_task is a shim; use salmalm.core.llm_task directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.core.llm_task")
_sys.modules[__name__] = _real
