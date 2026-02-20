# Backward-compatibility shim — real module is salmalm.security.exec_approvals
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.security.exec_approvals")
_sys.modules[__name__] = _real
