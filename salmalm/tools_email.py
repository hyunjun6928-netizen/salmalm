# Backward-compatibility shim — real module is salmalm.tools.tools_email
import importlib as _importlib, sys as _sys
_real = _importlib.import_module("salmalm.tools.tools_email")
_sys.modules[__name__] = _real
