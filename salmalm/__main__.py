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
            # An event loop is already running (e.g. Jupyter / nest_asyncio).
            # run_until_complete() on an already-running loop raises RuntimeError again.
            # Use nest_asyncio if available, otherwise create a new thread with its own loop.
            try:
                import nest_asyncio as _nest
                _nest.apply()
                import asyncio as _asyncio
                _asyncio.get_event_loop().run_until_complete(run_server())
            except ImportError:
                import threading as _threading
                import asyncio as _asyncio
                _exc_holder = []
                def _run():
                    loop = _asyncio.new_event_loop()
                    _asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(run_server())
                    except Exception as _e:
                        _exc_holder.append(_e)
                    finally:
                        loop.close()
                t = _threading.Thread(target=_run, daemon=True)
                t.start()
                t.join()
                if _exc_holder:
                    raise _exc_holder[0]
        else:
            raise


if __name__ == "__main__":
    main()
