"""Auto-resize images for vision input to reduce token cost.

Attempts PIL first; falls back to sending original if unavailable.
"""
from __future__ import annotations

import base64
import io
from typing import Tuple

MAX_DIMENSION = 1024


def resize_image_b64(b64_data: str, mime: str, max_dim: int = MAX_DIMENSION) -> Tuple[str, str]:
    """Resize a base64-encoded image so its longest side <= max_dim.

    Returns (resized_b64, mime). If PIL is unavailable or image is already
    small enough, returns the original data unchanged.
    """
    try:
        from PIL import Image
    except ImportError:
        return b64_data, mime

    try:
        raw = base64.b64decode(b64_data)
        img = Image.open(io.BytesIO(raw))

        w, h = img.size
        if w <= max_dim and h <= max_dim:
            return b64_data, mime  # Already small enough

        # Calculate new size preserving aspect ratio
        scale = max_dim / max(w, h)
        new_w, new_h = int(w * scale), int(h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)

        # Re-encode
        buf = io.BytesIO()
        out_format = 'JPEG'
        out_mime = 'image/jpeg'
        if mime == 'image/png':
            out_format = 'PNG'
            out_mime = 'image/png'
        elif mime == 'image/webp':
            out_format = 'WEBP'
            out_mime = 'image/webp'

        # Convert RGBA to RGB for JPEG
        if out_format == 'JPEG' and img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')

        img.save(buf, format=out_format, quality=85)
        resized_b64 = base64.b64encode(buf.getvalue()).decode('ascii')
        return resized_b64, out_mime
    except Exception:
        # Any error → return original
        return b64_data, mime
