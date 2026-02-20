# Backward-compatibility shim — real module is salmalm.web.templates
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.web.templates")
_sys.modules[__name__] = _real
