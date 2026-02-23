"""Screen capture and Computer Use module.

stdlib-only. Uses platform-native screenshot tools via subprocess.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional
from salmalm.constants import DATA_DIR

log = logging.getLogger(__name__)

_CONFIG_DIR = DATA_DIR
_HISTORY_DIR = _CONFIG_DIR / "screen_history"
_SCREEN_CONFIG_PATH = _CONFIG_DIR / "screen_config.json"

DEFAULT_CONFIG = {
    "enabled": True,
    "captureIntervalMinutes": 5,
    "maxHistory": 100,
    "ocrEnabled": True,
    "visionFallback": True,
}


def _ensure_dirs():
    """Ensure dirs."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _HISTORY_DIR.mkdir(parents=True, exist_ok=True)


class ScreenCapture:
    """Platform-aware screen capture using native tools."""

    def capture_screen(self) -> Optional[bytes]:
        """Capture screen and return PNG bytes."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            if sys.platform == "darwin":
                return self._capture_macos(tmp_path)
            elif sys.platform == "win32":
                return self._capture_windows(tmp_path)
            elif sys.platform.startswith("linux"):
                return self._capture_linux(tmp_path)
            else:
                log.warning(f"Unsupported platform for screen capture: {sys.platform}")
                return None
        except Exception as e:
            log.error(f"Screen capture failed: {e}")
            return None
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    @staticmethod
    def _capture_macos(tmp_path: str) -> Optional[bytes]:
        """Capture macos."""
        result = subprocess.run(
            ["screencapture", "-x", tmp_path],
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0 and os.path.exists(tmp_path):
            return Path(tmp_path).read_bytes()
        return None

    @staticmethod
    def _capture_windows(tmp_path: str) -> Optional[bytes]:
        """Capture windows."""
        ps_script = f'''
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$screen = [System.Windows.Forms.Screen]::PrimaryScreen
$bounds = $screen.Bounds
$bitmap = New-Object System.Drawing.Bitmap($bounds.Width, $bounds.Height)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$bitmap.Save("{tmp_path}")
$graphics.Dispose()
$bitmap.Dispose()
'''
        result = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True,
            timeout=15,
        )
        if result.returncode == 0 and os.path.exists(tmp_path):
            return Path(tmp_path).read_bytes()
        return None

    @staticmethod
    def _capture_linux(tmp_path: str) -> Optional[bytes]:
        # Try multiple tools
        """Capture linux."""
        tools = [
            (["gnome-screenshot", "-f", tmp_path], "gnome-screenshot"),
            (["scrot", tmp_path], "scrot"),
            (["import", "-window", "root", tmp_path], "import"),
        ]
        for cmd, name in tools:
            if shutil.which(cmd[0]):
                try:
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        timeout=10,
                    )
                    if result.returncode == 0 and os.path.exists(tmp_path):
                        return Path(tmp_path).read_bytes()
                except Exception as e:  # noqa: broad-except
                    log.debug(f"Suppressed: {e}")
        log.warning("No screen capture tool found on Linux (tried gnome-screenshot, scrot, import)")
        return None

    @staticmethod
    def ocr_image(image_path: str) -> Optional[str]:
        """Run OCR on image using tesseract if available."""
        if not shutil.which("tesseract"):
            return None
        try:
            result = subprocess.run(
                ["tesseract", image_path, "stdout"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            log.warning(f"OCR failed: {e}")
        return None

    @staticmethod
    def image_to_base64(png_bytes: bytes) -> str:
        """Image to base64."""
        return base64.b64encode(png_bytes).decode()

    def capture_and_analyze(self, llm_func=None) -> str:
        """Capture screen and optionally analyze with LLM Vision."""
        png = self.capture_screen()
        if not png:
            return "❌ Screen capture failed. No supported tool found."

        # Try OCR first
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(png)
            tmp_path = tmp.name

        try:
            ocr_text = self.ocr_image(tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        if ocr_text:
            return f"📸 **Screen capture** (OCR):\n```\n{ocr_text[:3000]}\n```"

        # Fallback to base64 for LLM Vision
        b64 = self.image_to_base64(png)
        if llm_func:
            try:
                return llm_func(b64, "image/png")
            except Exception as e:
                return f"📸 Screen captured ({len(png)} bytes). Vision analysis failed: {e}"

        return f"📸 Screen captured ({len(png)} bytes). No OCR or Vision available."


class ScreenHistory:
    """Manages periodic capture history (Rewind-style)."""

    def __init__(self) -> None:
        """Init  ."""
        self._config = self._load_config()
        self._watcher_thread: Optional[threading.Thread] = None
        self._watching = False

    def _load_config(self) -> dict:
        """Load config."""
        from salmalm.config_manager import ConfigManager

        return ConfigManager.load("screen_config", defaults=DEFAULT_CONFIG)

    def _save_config(self):
        """Save config."""
        from salmalm.config_manager import ConfigManager

        _ensure_dirs()
        ConfigManager.save("screen_config", self._config)

    def save_capture(self, png_bytes: bytes, ocr_text: str = "") -> str:
        """Save a capture to history."""
        _ensure_dirs()
        ts = int(time.time())
        filename = f"screen_{ts}.png"
        filepath = _HISTORY_DIR / filename
        filepath.write_bytes(png_bytes)

        # Save metadata
        meta_path = _HISTORY_DIR / f"screen_{ts}.json"
        meta = {
            "timestamp": ts,
            "filename": filename,
            "size": len(png_bytes),
            "ocr_text": ocr_text,
        }
        meta_path.write_text(json.dumps(meta))

        # Prune old captures
        self._prune()
        return str(filepath)

    def _prune(self):
        """Remove oldest captures beyond maxHistory."""
        max_hist = self._config.get("maxHistory", 100)
        pngs = sorted(_HISTORY_DIR.glob("screen_*.png"))
        while len(pngs) > max_hist:
            old = pngs.pop(0)
            old.unlink(missing_ok=True)
            meta = old.with_suffix(".json")
            if meta.exists():
                meta.unlink(missing_ok=True)

    def get_history(self, n: int = 5) -> List[Dict]:
        """Get most recent N captures."""
        _ensure_dirs()
        metas = sorted(_HISTORY_DIR.glob("screen_*.json"), reverse=True)[:n]
        result = []
        for mp in metas:
            try:
                result.append(json.loads(mp.read_text()))
            except Exception as e:  # noqa: broad-except
                log.debug(f"Suppressed: {e}")
        return result

    def search(self, query: str) -> List[Dict]:
        """Search captures by OCR text."""
        _ensure_dirs()
        query_lower = query.lower()
        results = []
        for mp in sorted(_HISTORY_DIR.glob("screen_*.json"), reverse=True):
            try:
                meta = json.loads(mp.read_text())
                if query_lower in meta.get("ocr_text", "").lower():
                    results.append(meta)
                    if len(results) >= 20:
                        break
            except Exception as e:  # noqa: broad-except
                log.debug(f"Suppressed: {e}")
        return results

    def start_watching(self) -> None:
        """Start periodic capture."""
        if self._watching:
            return
        self._watching = True
        interval = self._config.get("captureIntervalMinutes", 5) * 60
        capturer = ScreenCapture()

        def _loop():
            """Loop."""
            while self._watching:
                try:
                    png = capturer.capture_screen()
                    if png:
                        ocr = ""
                        if self._config.get("ocrEnabled"):
                            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                                tmp.write(png)
                                tmp_path = tmp.name
                            try:
                                ocr = capturer.ocr_image(tmp_path) or ""
                            finally:
                                os.unlink(tmp_path)
                        self.save_capture(png, ocr)
                except Exception as e:
                    log.error(f"Periodic capture error: {e}")
                time.sleep(interval)

        self._watcher_thread = threading.Thread(target=_loop, daemon=True)
        self._watcher_thread.start()

    def stop_watching(self) -> None:
        """Stop watching."""
        self._watching = False


class ScreenManager:
    """High-level interface for /screen commands."""

    def __init__(self) -> None:
        """Init  ."""
        self.capturer = ScreenCapture()
        self.history_mgr = ScreenHistory()

    def capture(self, llm_func=None) -> str:
        """Capture."""
        return self.capturer.capture_and_analyze(llm_func)

    def watch(self, toggle: str) -> str:
        """Watch."""
        if toggle == "on":
            self.history_mgr.start_watching()
            interval = self.history_mgr._config.get("captureIntervalMinutes", 5)
            return f"👁️ Screen watching started (every {interval}min)."
        elif toggle == "off":
            self.history_mgr.stop_watching()
            return "👁️ Screen watching stopped."
        return "❓ Usage: /screen watch on|off"

    def history(self, n: int = 5) -> str:
        """History."""
        entries = self.history_mgr.get_history(n)
        if not entries:
            return "📸 No screen captures in history."
        lines = [f"📸 **Recent {len(entries)} captures:**"]
        for e in entries:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(e["timestamp"]))
            size_kb = e.get("size", 0) // 1024
            ocr_preview = (e.get("ocr_text", "") or "")[:80]
            lines.append(f"  • {ts} ({size_kb}KB) {ocr_preview}")
        return "\n".join(lines)

    def search(self, query: str) -> str:
        """Search."""
        if not query:
            return "❓ Usage: /screen search <query>"
        results = self.history_mgr.search(query)
        if not results:
            return f'🔍 No captures matching "{query}".'
        lines = [f'🔍 **{len(results)} matches for "{query}":**']
        for e in results:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(e["timestamp"]))
            lines.append(f"  • {ts}: {(e.get('ocr_text', '') or '')[:100]}")
        return "\n".join(lines)


# Singleton
screen_manager = ScreenManager()
