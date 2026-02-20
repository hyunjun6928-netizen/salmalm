# Backward-compatibility shim — real module is salmalm.tools.tools_common
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.tools.tools_common")
_sys.modules[__name__] = _real
