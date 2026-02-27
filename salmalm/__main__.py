"""Allow running salmalm as: python -m salmalm or `salmalm` CLI."""

from __future__ import annotations

import asyncio
import os


def main() -> None:
    """CLI entry point — always routes through bootstrap.run_server()."""
    from salmalm.cli import setup_workdir, dispatch_cli

    try:
        setup_workdir()
    except PermissionError as _pe:
        import sys as _sys
        print(f"❌ 권한 오류: 작업 디렉터리를 생성할 수 없습니다.\n"
              f"   {_pe}\n"
              f"   HOME 또는 DATA 경로의 쓰기 권한을 확인하세요.", file=_sys.stderr)
        _sys.exit(1)

    from salmalm import init_logging

    init_logging()

    if dispatch_cli():
        return

    # Ensure DATA_DIR has required folders
    from salmalm.constants import DATA_DIR

    for d in ("memory", "workspace", "uploads", "plugins"):
        os.makedirs(DATA_DIR / d, exist_ok=True)

    from salmalm.bootstrap import run_server

    try:
        asyncio.run(run_server())
    except RuntimeError as e:
        if "running event loop" in str(e):
            # An event loop is already running (e.g. Jupyter / nest_asyncio context).
            # get_event_loop() is deprecated in 3.12+ when no current loop is set;
            # use asyncio.get_running_loop() to grab the live loop safely.
            import asyncio as _asyncio
            loop = _asyncio.get_running_loop()
            loop.run_until_complete(run_server())
        else:
            raise


if __name__ == "__main__":
    main()
