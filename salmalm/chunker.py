# Backward-compatibility shim — real module is salmalm.utils.chunker
import importlib as _importlib, sys as _sys
_real = _importlib.import_module("salmalm.utils.chunker")
_sys.modules[__name__] = _real
