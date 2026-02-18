"""Allow running salmalm as: python -m salmalm or `salmalm` CLI."""
from __future__ import annotations

import os
import sys
import runpy


def main() -> None:
    """CLI entry point."""
    # Find server.py relative to this package
    pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    server_py = os.path.join(pkg_root, 'server.py')

    if not os.path.exists(server_py):
        # Installed via pip — server.py is in package data
        server_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'server.py')

    os.chdir(pkg_root)
    if pkg_root not in sys.path:
        sys.path.insert(0, pkg_root)

    runpy.run_path(server_py, run_name='__main__')


if __name__ == '__main__':
    main()
