#!/usr/bin/env python3
"""SalmAlm dev server — thin wrapper around bootstrap.run_server().

For development only. Production: `salmalm` or `python -m salmalm`.
"""
import asyncio
import os
import sys

# Ensure package is importable when running from repo root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from salmalm.cli import setup_workdir
setup_workdir()

from salmalm import init_logging
init_logging()

from salmalm.bootstrap import run_server
asyncio.run(run_server())
