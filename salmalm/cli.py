"""CLI argument parsing for SalmAlm."""
from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)


def _ensure_windows_shortcut():
    """Create a .bat launcher on Desktop (works everywhere, no PowerShell needed)."""
    try:
        desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
        if not os.path.isdir(desktop):
            # Try Windows-specific Desktop path
            desktop = os.path.join(os.environ.get('USERPROFILE', os.path.expanduser('~')), 'Desktop')
        if not os.path.isdir(desktop):
            return

        bat_path = os.path.join(desktop, 'SalmAlm.bat')
        if os.path.exists(bat_path):
            return  # Already created

        python_exe = sys.executable
        bat_content = f'''@echo off
title SalmAlm - Personal AI Gateway
echo Starting SalmAlm...
"{python_exe}" -m salmalm
pause
'''
        with open(bat_path, 'w', encoding='utf-8') as f:
            f.write(bat_content)
        logger.info("[PIN] Created SalmAlm.bat on Desktop -- double-click to start!")
    except Exception as e:
        logger.warning(f"Could not create desktop shortcut: {e}")


def _run_update():
    """Self-update via pip."""
    import subprocess as _sp
    if sys.stdin.isatty() and '--yes' not in sys.argv:
        confirm = input("This will run 'pip install --upgrade salmalm'. Continue? [y/N] ")
        if confirm.strip().lower() not in ('y', 'yes'):
            print("Cancelled.")
            sys.exit(0)
    logger.info("[UP] Updating SalmAlm...")
    result = _sp.run(
        [sys.executable, '-m', 'pip', 'install', '--upgrade', '--no-cache-dir',
         '--force-reinstall', 'salmalm'],
        capture_output=False)
    if result.returncode == 0:
        logger.info("Updated! Run 'salmalm' or 'python -m salmalm' to start.")
    else:
        logger.error("Update failed. Try manually: pip install --upgrade salmalm")
    sys.exit(result.returncode)


def _run_node_mode():
    """Run as a lightweight node that registers with a gateway."""
    import http.server

    # Parse args: --node --gateway http://host:18800 --port 18810 --name mynode --token secret
    args = sys.argv[1:]
    gateway_url = 'http://127.0.0.1:18800'
    port = 18810
    name = os.environ.get('HOSTNAME', 'node-1')
    token = ''

    i = 0
    while i < len(args):
        if args[i] == '--gateway' and i + 1 < len(args):
            gateway_url = args[i + 1]
            i += 2
        elif args[i] == '--port' and i + 1 < len(args):
            port = int(args[i + 1])
            i += 2
        elif args[i] == '--name' and i + 1 < len(args):
            name = args[i + 1]
            i += 2
        elif args[i] == '--token' and i + 1 < len(args):
            token = args[i + 1]
            i += 2
        else:
            i += 1

    from salmalm.constants import VERSION
    from salmalm.web import WebHandler
    from salmalm.nodes import NodeAgent

    # Ensure working dirs
    for d in ('memory', 'workspace', 'uploads', 'plugins'):
        os.makedirs(d, exist_ok=True)

    node_id = f'{name}-{port}'
    agent = NodeAgent(gateway_url, node_id, token=token, name=name)

    # Register with gateway
    result = agent.register()
    if 'error' in result:
        logger.warning(f"Gateway registration failed: {result['error']}")
        logger.warning(f"Starting standalone anyway on :{port}")

    # Start heartbeat
    agent.start_heartbeat(interval=30)

    # Start HTTP server for tool execution
    _default_bind = '0.0.0.0' if 'microsoft' in os.uname().release.lower() else '127.0.0.1'
    bind_addr = os.environ.get('SALMALM_BIND', _default_bind)
    server = http.server.ThreadingHTTPServer((bind_addr, port), WebHandler)
    logger.info(
        f"+==============================================+\n"
        f"|  [NET] SalmAlm Node v{VERSION:<27s}|\n"
        f"|  Name: {name:<37s}|\n"
        f"|  Port: {port:<37s}|\n"
        f"|  Gateway: {gateway_url:<34s}|\n"
        f"+==============================================+"
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        agent.stop()
        server.shutdown()
        logger.info("[NET] Node stopped.")


def setup_workdir():
    """Set working directory and load .env.

    Respects SALMALM_HOME env var; falls back to ~/SalmAlm.
    """
    if not getattr(sys, 'frozen', False):
        work_dir = os.environ.get('SALMALM_HOME', '') or os.path.join(os.path.expanduser('~'), 'SalmAlm')
        os.makedirs(work_dir, exist_ok=True)
        os.chdir(work_dir)

    # Load .env file if present (simple key=value parser, no dependency)
    env_file = os.path.join(os.getcwd(), '.env')
    if os.path.isfile(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, _, v = line.partition('=')
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and v:
                    os.environ.setdefault(k, v)
        logger.info("Loaded .env file")

    # Windows: create desktop shortcut on first run
    if sys.platform == 'win32' and not getattr(sys, 'frozen', False):
        _ensure_windows_shortcut()


def dispatch_cli() -> bool:
    """Handle CLI flags. Returns True if a flag was handled (caller should exit)."""
    if '--update' in sys.argv or 'update' in sys.argv[1:2]:
        _run_update()
        return True
    if '--shortcut' in sys.argv:
        if sys.platform == 'win32':
            _ensure_windows_shortcut()
        else:
            logger.info("Desktop shortcuts are Windows-only.")
        sys.exit(0)
    if '--version' in sys.argv or '-v' in sys.argv:
        from salmalm.constants import VERSION
        logger.info(f'SalmAlm v{VERSION}')
        sys.exit(0)
    if '--node' in sys.argv:
        _run_node_mode()
        return True
    if 'tray' in sys.argv[1:2] or '--tray' in sys.argv:
        from salmalm.tray import run_tray
        port = int(os.environ.get('SALMALM_PORT', 18800))
        run_tray(port)
        return True
    return False
