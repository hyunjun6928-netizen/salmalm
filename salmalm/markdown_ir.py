# Backward-compatibility shim — real module is salmalm.utils.markdown_ir
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.utils.markdown_ir")
_sys.modules[__name__] = _real
