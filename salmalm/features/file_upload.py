"""Enhanced File Upload (파일 업로드 강화) — Open WebUI style."""

from __future__ import annotations

import json
import re
from typing import Tuple

ALLOWED_UPLOAD_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp",
    "pdf",
    "txt",
    "csv",
    "json",
    "md",
    "py",
    "js",
    "ts",
    "html",
    "css",
    "sh",
    "yaml",
    "yml",
    "xml",
    "sql",
    "log",
    "bat",
}


def validate_upload(filename: str, size_bytes: int) -> Tuple[bool, str]:
    """Validate upload."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        return False, f"File type .{ext} not allowed. Allowed: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}"
    if size_bytes > 50 * 1024 * 1024:
        return False, "File too large (max 50MB)"
    if size_bytes == 0:
        return False, "Empty file"
    return True, ""


def extract_pdf_text(data: bytes) -> str:
    """Extract pdf text."""
    import zlib

    text_parts = []

    i = 0
    while i < len(data):
        stream_start = data.find(b"stream\r\n", i)
        if stream_start == -1:
            stream_start = data.find(b"stream\n", i)
        if stream_start == -1:
            break

        stream_start += (
            len(b"stream\r\n") if data[stream_start : stream_start + 8] == b"stream\r\n" else len(b"stream\n")
        )
        stream_end = data.find(b"endstream", stream_start)
        if stream_end == -1:
            break

        stream_data = data[stream_start:stream_end]

        try:
            decompressed = zlib.decompress(stream_data)
        except Exception as e:  # noqa: broad-except
            decompressed = stream_data

        text_blocks = re.findall(rb"BT\s*(.*?)\s*ET", decompressed, re.DOTALL)
        for block in text_blocks:
            for match in re.finditer(rb"\(([^)]*)\)\s*Tj", block):
                text_parts.append(match.group(1).decode("latin-1", errors="replace"))
            for match in re.finditer(rb"\[(.*?)\]\s*TJ", block):
                inner = match.group(1)
                for text_match in re.finditer(rb"\(([^)]*)\)", inner):
                    text_parts.append(text_match.group(1).decode("latin-1", errors="replace"))

        i = stream_end + 9

    result = " ".join(text_parts)
    result = result.replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t")
    result = re.sub(r"\\(\d{3})", lambda m: chr(int(m.group(1), 8)), result)
    return result.strip() if result.strip() else "[PDF text extraction returned no text / PDF 텍스트 추출 실패]"


def process_uploaded_file(filename: str, data: bytes) -> str:
    """Process uploaded file."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "pdf":
        text = extract_pdf_text(data)
        return f"📄 **{filename}** ({len(data) / 1024:.1f}KB)\n```\n{text[:10000]}\n```"

    if ext in ("txt", "md", "log", "sh", "bat", "sql"):
        text = data.decode("utf-8", errors="replace")[:10000]
        return f"📄 **{filename}** ({len(data) / 1024:.1f}KB)\n```\n{text}\n```"

    if ext in ("py", "js", "ts", "html", "css", "yaml", "yml", "xml"):
        text = data.decode("utf-8", errors="replace")[:10000]
        return f"📄 **{filename}** ({len(data) / 1024:.1f}KB)\n```{ext}\n{text}\n```"

    if ext == "csv":
        text = data.decode("utf-8", errors="replace")
        lines = text.split("\n")[:100]
        preview = "\n".join(lines)
        return f"📊 **{filename}** ({len(data) / 1024:.1f}KB, {len(text.split(chr(10)))} rows)\n```csv\n{preview}\n```"

    if ext == "json":
        text = data.decode("utf-8", errors="replace")
        try:
            parsed = json.loads(text)
            pretty = json.dumps(parsed, indent=2, ensure_ascii=False)[:10000]
            return f"📋 **{filename}** ({len(data) / 1024:.1f}KB)\n```json\n{pretty}\n```"
        except json.JSONDecodeError:
            return f"📋 **{filename}** ({len(data) / 1024:.1f}KB)\n```json\n{text[:10000]}\n```"

    return f"📎 **{filename}** ({len(data) / 1024:.1f}KB) — binary file, content not displayed."
