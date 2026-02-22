"""Allow running salmalm as: python -m salmalm or `salmalm` CLI."""

from __future__ import annotations

import asyncio
import os


def main() -> None:
    """CLI entry point — always routes through bootstrap.run_server()."""
    from salmalm.cli import setup_workdir, dispatch_cli

    setup_workdir()

    from salmalm import init_logging

    init_logging()

    if dispatch_cli():
        return

    # Ensure DATA_DIR has required folders
    from salmalm.constants import DATA_DIR

    for d in ("memory", "workspace", "uploads", "plugins"):
        os.makedirs(DATA_DIR / d, exist_ok=True)

    from salmalm.bootstrap import run_server

    asyncio.run(run_server())


if __name__ == "__main__":
    main()
