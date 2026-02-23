"""CLI argument parsing for SalmAlm."""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)


def _ensure_windows_shortcut():
    """Create a .bat launcher on Desktop (works everywhere, no PowerShell needed)."""
    try:
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.isdir(desktop):
            # Try Windows-specific Desktop path
            desktop = os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), "Desktop")
        if not os.path.isdir(desktop):
            return

        bat_path = os.path.join(desktop, "SalmAlm.bat")
        if os.path.exists(bat_path):
            return  # Already created

        python_exe = sys.executable
        bat_content = f'''@echo off
title SalmAlm - Personal AI Gateway
echo Starting SalmAlm...
"{python_exe}" -m salmalm
pause
'''
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(bat_content)
        logger.info("[PIN] Created SalmAlm.bat on Desktop -- double-click to start!")
    except Exception as e:
        logger.warning(f"Could not create desktop shortcut: {e}")


def _install_shortcut():
    """Create a desktop shortcut/launcher for all platforms."""
    if sys.platform == "win32":
        _ensure_windows_shortcut()
        return

    # Detect WSL → create Windows .bat on real Desktop
    is_wsl = "microsoft" in os.uname().release.lower() if hasattr(os, "uname") else False
    if is_wsl:
        # Find Windows username and Desktop path
        try:
            import subprocess as _sp

            win_user = _sp.check_output(["cmd.exe", "/C", "echo", "%USERNAME%"], stderr=_sp.DEVNULL, text=True).strip()
            win_desktop = f"/mnt/c/Users/{win_user}/Desktop"
            if not os.path.isdir(win_desktop):
                # Fallback: try OneDrive Desktop
                win_desktop = f"/mnt/c/Users/{win_user}/OneDrive/Desktop"
            if os.path.isdir(win_desktop):
                bat_path = os.path.join(win_desktop, "SalmAlm.bat")
                bat_content = """@echo off
title SalmAlm
wsl -e bash -lc "salmalm --open"
pause
"""
                with open(bat_path, "w", encoding="utf-8") as f:
                    f.write(bat_content)
                logger.info(f"[PIN] Created {bat_path} — double-click to start SalmAlm from WSL!")
                return
        except Exception as e:
            logger.warning(f"[PIN] WSL shortcut failed: {e}, falling back to Linux .desktop")

    # Linux (.desktop) / macOS (.command)
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    if not os.path.isdir(desktop):
        # Try XDG
        desktop = os.path.join(os.path.expanduser("~"), "デスクトップ")  # JP locale
        if not os.path.isdir(desktop):
            desktop = os.path.expanduser("~/Desktop")
            os.makedirs(desktop, exist_ok=True)

    python_exe = sys.executable

    if sys.platform == "darwin":
        # macOS: .command file
        cmd_path = os.path.join(desktop, "SalmAlm.command")
        with open(cmd_path, "w") as f:
            f.write(f'#!/bin/bash\n"{python_exe}" -m salmalm --open\n')
        os.chmod(cmd_path, 0o755)
        logger.info(f"[PIN] Created {cmd_path} — double-click to start!")
    else:
        # Linux: .desktop file
        desktop_path = os.path.join(desktop, "salmalm.desktop")
        icon_path = os.path.join(os.path.dirname(__file__), "static", "icon.png")
        content = f"""[Desktop Entry]
Type=Application
Name=SalmAlm
Comment=Personal AI Gateway
Exec={python_exe} -m salmalm --open
Icon={icon_path}
Terminal=true
Categories=Utility;
"""
        with open(desktop_path, "w") as f:
            f.write(content)
        os.chmod(desktop_path, 0o755)
        logger.info(f"[PIN] Created {desktop_path} — double-click to start!")


def _run_update():
    """Self-update via pip."""
    import subprocess as _sp

    if sys.stdin.isatty() and "--yes" not in sys.argv:
        confirm = input("This will run 'pip install --upgrade salmalm'. Continue? [y/N] ")
        if confirm.strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            sys.exit(0)
    logger.info("[UP] Updating SalmAlm...")
    result = _sp.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "--no-cache-dir", "--force-reinstall", "salmalm"],
        capture_output=False,
    )
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
    gateway_url = "http://127.0.0.1:18800"
    port = 18810
    name = os.environ.get("HOSTNAME", "node-1")
    token = ""

    i = 0
    while i < len(args):
        if args[i] == "--gateway" and i + 1 < len(args):
            gateway_url = args[i + 1]
            i += 2
        elif args[i] == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
            i += 2
        elif args[i] == "--name" and i + 1 < len(args):
            name = args[i + 1]
            i += 2
        elif args[i] == "--token" and i + 1 < len(args):
            token = args[i + 1]
            i += 2
        else:
            i += 1

    from salmalm.constants import VERSION
    from salmalm.web import WebHandler
    from salmalm.nodes import NodeAgent

    # Ensure working dirs
    for d in ("memory", "workspace", "uploads", "plugins"):
        os.makedirs(d, exist_ok=True)

    node_id = f"{name}-{port}"
    agent = NodeAgent(gateway_url, node_id, token=token, name=name)

    # Register with gateway
    result = agent.register()
    if "error" in result:
        logger.warning(f"Gateway registration failed: {result['error']}")
        logger.warning(f"Starting standalone anyway on :{port}")

    # Start heartbeat
    agent.start_heartbeat(interval=30)

    # Start HTTP server for tool execution
    _default_bind = "0.0.0.0" if "microsoft" in os.uname().release.lower() else "127.0.0.1"
    bind_addr = os.environ.get("SALMALM_BIND", _default_bind)
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
    if not getattr(sys, "frozen", False):
        work_dir = os.environ.get("SALMALM_HOME", "") or os.path.join(os.path.expanduser("~"), "SalmAlm")
        os.makedirs(work_dir, exist_ok=True)
        os.chdir(work_dir)

    # Load .env file if present (simple key=value parser, no dependency)
    env_file = os.path.join(os.getcwd(), ".env")
    if os.path.isfile(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and v:
                    os.environ.setdefault(k, v)
        logger.info("Loaded .env file")

    # Windows: create desktop shortcut on first run
    if sys.platform == "win32" and not getattr(sys, "frozen", False):
        _ensure_windows_shortcut()


def dispatch_cli() -> bool:
    """Handle CLI flags. Returns True if a flag was handled (caller should exit)."""
    if "--update" in sys.argv or "update" in sys.argv[1:2]:
        _run_update()
        return True
    if "--shortcut" in sys.argv:
        _install_shortcut()
        sys.exit(0)
    if "--version" in sys.argv or "-v" in sys.argv:
        from salmalm.constants import VERSION

        logger.info(f"SalmAlm v{VERSION}")
        sys.exit(0)
    if "--node" in sys.argv:
        _run_node_mode()
        return True
    if "tray" in sys.argv[1:2] or "--tray" in sys.argv:
        from salmalm.tray import run_tray

        port = int(os.environ.get("SALMALM_PORT", 18800))
        run_tray(port)
        return True
    if "--open" in sys.argv:
        # Auto-open browser after server starts
        os.environ["SALMALM_OPEN_BROWSER"] = "1"
    if "doctor" in sys.argv[1:2] or "--doctor" in sys.argv:
        _run_doctor()
        return True
    return False


def _run_doctor():
    """Run self-diagnostics and print colorful report."""
    from salmalm.features.doctor import doctor

    print("\n🏥 SalmAlm Doctor\n" + "=" * 40)
    results = doctor.run_all()
    for r in results:
        icon = "✅" if r["status"] == "ok" else "❌"
        fix = " (🔧 fixable)" if r.get("fixable") else ""
        print(f"  {icon} {r['message']}{fix}")
    ok = sum(1 for r in results if r["status"] == "ok")
    total = len(results)
    print(f"\n📊 {ok}/{total} checks passed")
    if ok == total:
        print("🎉 All systems operational!")
    else:
        print("💡 Run 'salmalm doctor --fix' to auto-repair fixable issues")
    if "--fix" in sys.argv:
        fixable = [r for r in results if r.get("fixable") and r.get("issue_id")]
        if fixable:
            print(f"\n🔧 Auto-fixing {len(fixable)} issues...")
            for r in fixable:
                try:
                    doctor.repair(r["issue_id"])
                    print(f"  ✅ Fixed: {r['issue_id']}")
                except Exception as e:
                    print(f"  ❌ Failed: {r['issue_id']} — {e}")
        else:
            print("\n✨ Nothing to fix!")
