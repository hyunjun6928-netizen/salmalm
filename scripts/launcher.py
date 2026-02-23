#!/usr/bin/env python3
"""SalmAlm Desktop Launcher — for PyInstaller one-file builds.

Build:
    pip install pyinstaller
    pyinstaller --onefile --windowed --name SalmAlm --icon=salmalm/static/favicon.ico scripts/launcher.py

This creates a single executable that:
1. Starts the SalmAlm server
2. Opens the browser automatically
3. Shows a system tray icon (if pystray available)
4. Keeps running until the user quits
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import webbrowser


PORT = int(os.environ.get("SALMALM_PORT", 18800))
URL = f"http://127.0.0.1:{PORT}"


def _find_python() -> str:
    """Find the Python executable."""
    for candidate in [sys.executable, "python3", "python"]:
        try:
            r = subprocess.run([candidate, "--version"], capture_output=True, timeout=5)
            if r.returncode == 0:
                return candidate
        except Exception:
            continue
    return "python3"


def _check_installed() -> bool:
    """Check if salmalm is installed."""
    python = _find_python()
    r = subprocess.run(
        [python, "-c", "import salmalm; print(salmalm.__version__)"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return r.returncode == 0


def _install_salmalm() -> bool:
    """Install salmalm via pip."""
    python = _find_python()
    print("📦 Installing SalmAlm...")
    r = subprocess.run(
        [python, "-m", "pip", "install", "salmalm", "--quiet"],
        timeout=120,
    )
    return r.returncode == 0


def _wait_for_server(timeout: int = 30) -> bool:
    """Wait for the server to start."""
    import urllib.request
    import urllib.error

    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(URL, timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def _run_tray(proc: subprocess.Popen) -> None:
    """Run system tray icon (optional, requires pystray)."""
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        # No tray support — just wait
        proc.wait()
        return

    # Create a simple icon
    img = Image.new("RGB", (64, 64), "#6366f1")
    draw = ImageDraw.Draw(img)
    draw.text((16, 16), "S", fill="white")

    def _quit(icon, item):
        proc.terminate()
        icon.stop()

    def _open_browser(icon, item):
        webbrowser.open(URL)

    menu = pystray.Menu(
        pystray.MenuItem("Open SalmAlm", _open_browser, default=True),
        pystray.MenuItem("Quit", _quit),
    )
    icon = pystray.Icon("SalmAlm", img, "SalmAlm AI", menu)
    icon.run()


def main() -> None:
    """Launch SalmAlm server + browser + tray."""
    print("😈 SalmAlm Desktop Launcher\n")

    if not _check_installed():
        if not _install_salmalm():
            print("❌ Failed to install SalmAlm. Please run: pip install salmalm")
            input("Press Enter to exit...")
            return

    python = _find_python()
    print(f"🚀 Starting SalmAlm server on {URL}...")

    proc = subprocess.Popen(
        [python, "-m", "salmalm"],
        env={**os.environ, "SALMALM_PORT": str(PORT)},
    )

    # Wait for server, then open browser
    def _open_when_ready():
        if _wait_for_server():
            webbrowser.open(URL)
            print(f"✅ SalmAlm is running at {URL}")
        else:
            print("⚠️ Server took too long to start. Open manually:", URL)

    threading.Thread(target=_open_when_ready, daemon=True).start()

    # Try tray icon, fallback to simple wait
    try:
        _run_tray(proc)
    except KeyboardInterrupt:
        proc.terminate()
    except Exception:
        try:
            proc.wait()
        except KeyboardInterrupt:
            proc.terminate()


if __name__ == "__main__":
    main()
