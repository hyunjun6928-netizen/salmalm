# Backward-compatibility shim — real module is salmalm.features.rag
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.features.rag")
_sys.modules[__name__] = _real
