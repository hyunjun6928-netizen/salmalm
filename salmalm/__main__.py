"""Allow running salmalm as: python -m salmalm or `salmalm` CLI."""
from __future__ import annotations

import os
import sys


def main() -> None:
    """CLI entry point — start the salmalm server."""
    from salmalm.cli import setup_workdir, dispatch_cli
    setup_workdir()

    if dispatch_cli():
        return

    # Ensure working directory has required folders
    for d in ('memory', 'workspace', 'uploads', 'plugins'):
        os.makedirs(d, exist_ok=True)

    # Try to find server.py (development mode)
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    dev_server = os.path.join(os.path.dirname(pkg_dir), 'server.py')

    if os.path.exists(dev_server):
        # Development: run server.py directly
        import runpy
        os.chdir(os.path.dirname(dev_server))
        if os.path.dirname(dev_server) not in sys.path:
            sys.path.insert(0, os.path.dirname(dev_server))
        runpy.run_path(dev_server, run_name='__main__')
    else:
        # pip install mode: import and run directly
        import asyncio
        from salmalm.bootstrap import run_server
        asyncio.run(run_server())


if __name__ == '__main__':
    main()
