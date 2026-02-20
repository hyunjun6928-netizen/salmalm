# Backward-compatibility shim — real module is salmalm.core.llm_loop
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.core.llm_loop")
_sys.modules[__name__] = _real
