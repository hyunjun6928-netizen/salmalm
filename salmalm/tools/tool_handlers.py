"""SalmAlm tool handlers — delegates to tool_registry + re-exports shared utilities.

Shared utilities live in tools_common.py (single source of truth).
This module re-exports them for backward compatibility.
"""

import os
import subprocess
import re
import time
import json
import secrets
import urllib.request
import base64
import threading  # noqa: F401
from pathlib import Path

from salmalm.constants import (  # noqa: F401
    EXEC_ALLOWLIST,
    EXEC_BLOCKLIST,
    EXEC_BLOCKLIST_PATTERNS,
    EXEC_ELEVATED,  # noqa: F401
    EXEC_BLOCKED_INTERPRETERS,
    PROTECTED_FILES,
    WORKSPACE_DIR,
    VERSION,
    KST,
    MEMORY_FILE,
    MEMORY_DIR,
    AUDIT_DB,
)
from salmalm.security.crypto import vault, log
from salmalm.core import audit_log
from salmalm.core.llm import _http_post

# Re-export shared utilities from canonical location (tools_common.py)
from salmalm.tools.tools_common import (  # noqa: F401
    _is_safe_command,
    _resolve_path,
    _is_private_url,
    _is_subpath,
)

# Re-export symbols that tests and other modules import from here
from salmalm.tools.tools_misc import (  # noqa: F401 — re-export for tests and other modules
    _reminders,
    _reminder_lock,
    _send_notification_impl,
    _parse_relative_time,
    _parse_rss,
    _workflows_file,
    _feeds_file,
)

# clipboard lock (used by tools_util.py)
_clipboard_lock = threading.Lock()
telegram_bot = None


# ── Main Entry Point (thin shim) ────────────────────────────


def execute_tool(name: str, args: dict) -> str:
    """Execute a tool — delegates to tool_registry.

    Edge cases:
    - Path traversal (.. in paths): rejected
    - Environment variable injection ($VAR in args): sanitized
    - All exceptions caught and returned as error strings
    """
    # Path traversal prevention — primary: resolve + subpath check; secondary: string filter
    from salmalm.constants import WORKSPACE_DIR, DATA_DIR

    _allowed_roots = (str(WORKSPACE_DIR), str(DATA_DIR), "/tmp")
    for key in ("path", "file_path", "image_path", "audio_path", "file1", "file2"):
        val = args.get(key, "")
        if not isinstance(val, str) or not val:
            continue
        # Quick string filter (secondary defense)
        if ".." in val:
            return f'❌ Path traversal blocked: ".." not allowed in {key} / 경로 탈출 차단'
        # Primary defense: resolve symlinks and check against allowed roots
        try:
            from pathlib import Path as _P

            resolved = str(_P(val).resolve())
            # Also resolve relative to WORKSPACE_DIR
            if not _P(val).is_absolute():
                resolved = str((WORKSPACE_DIR / val).resolve())
            in_allowed = any(resolved.startswith(root) for root in _allowed_roots)
            # Home read requires opt-in
            home_read_ok = os.environ.get("SALMALM_ALLOW_HOME_READ") and resolved.startswith(str(_P.home()))
            if not in_allowed and not home_read_ok:
                # Write-capable tools: always block outside allowed roots
                # (prevents creating files in arbitrary locations)
                _WRITE_TOOLS = {
                    "write_file", "create_file", "append_file", "save_file",
                    "move_file", "copy_file", "rename_file", "patch_file",
                    "download_file", "write_note", "save_note",
                }
                is_write = name in _WRITE_TOOLS
                if is_write or _P(resolved).exists() or _P(val).exists():
                    return f"❌ Path outside allowed directories: {key}={val} / 허용 디렉토리 외부 경로 차단: denied"
                # For non-existent read paths outside allowed dirs, still block
                # absolute paths that clearly target sensitive dirs
                _sensitive = (
                    "/etc/",
                    "/var/",
                    "/root/",
                    "/proc/",
                    "/sys/",
                    "/boot/",
                    "/dev/",
                    "C:\\Windows",
                    "C:\\System",
                )
                if any(resolved.startswith(s) or val.startswith(s) for s in _sensitive):
                    return f"❌ Access denied: {key}={val} / 접근 거부: 보호된 시스템 경로"
        except Exception:
            pass  # Let downstream handlers deal with invalid paths

    # Environment variable injection prevention
    for key, val in args.items():
        if isinstance(val, str) and re.search(r"\$\{?\w+\}?", val):
            # Allow $HOME-style only in non-sensitive contexts
            if key in ("command",):
                continue  # exec tool handles its own safety
            args[key] = re.sub(r"\$\{?\w+\}?", "", val)

    _audit_args_raw = json.dumps(args, ensure_ascii=False)[:300]
    try:
        from salmalm.security.redact import scrub_secrets

        _audit_args = scrub_secrets(_audit_args_raw)
    except Exception:
        _audit_args = _audit_args_raw
    _session_id = args.pop("_session_id", "")  # Injected by engine
    audit_log(
        "tool_exec",
        f"{name}: {_audit_args}",
        session_id=_session_id,
        detail_dict={"tool": name, "args_preview": _audit_args},
    )

    # Tool tier enforcement is handled by tool_registry.execute_tool()
    # via _authenticated arg (injected by engine from session state).

    # Try remote node dispatch first (if gateway has registered nodes)
    try:
        from salmalm.features.nodes import gateway

        if gateway._nodes:
            result = gateway.dispatch_auto(name, args)
            if result and "error" not in result:
                return result.get("result", str(result))  # type: ignore[no-any-return]
    except Exception:
        pass  # Fall through to local execution

    from salmalm.tools.tool_registry import execute_tool as _registry_execute

    return _registry_execute(name, args)


# ── Legacy Bridge (for tools_media.py) ──────────────────────


def _legacy_execute(name: str, args: dict) -> str:
    """Legacy tool execution — used by tools_media.py for not-yet-extracted tools."""
    return _execute_inner(name, args)


def _execute_inner(name: str, args: dict) -> str:
    """Inner dispatch — ONLY media tools that tools_media.py delegates back here."""
    try:
        if name == "image_generate":
            prompt = args["prompt"]
            provider = args.get("provider", "xai")
            size = args.get("size", "1024x1024")
            save_dir = WORKSPACE_DIR / "uploads"
            save_dir.mkdir(exist_ok=True)
            fname = f"gen_{int(time.time())}.png"
            save_path = save_dir / fname

            if provider == "xai":
                api_key = vault.get("xai_api_key")
                if not api_key:
                    return "❌ xAI API key not found"
                resp = _http_post(
                    "https://api.x.ai/v1/images/generations",
                    {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    {"model": "aurora", "prompt": prompt, "n": 1, "size": size, "response_format": "b64_json"},
                )
                import base64 as b64mod

                img_data = b64mod.b64decode(resp["data"][0]["b64_json"])
                save_path.write_bytes(img_data)
            else:
                api_key = vault.get("openai_api_key")
                if not api_key:
                    return "❌ OpenAI API key not found"
                resp = _http_post(
                    "https://api.openai.com/v1/images/generations",
                    {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    {"model": "gpt-image-1", "prompt": prompt, "n": 1, "size": size, "output_format": "b64_json"},
                )
                import base64 as b64mod

                img_data = b64mod.b64decode(resp["data"][0]["b64_json"])
                save_path.write_bytes(img_data)

            size_kb = len(img_data) / 1024
            log.info(f"[ART] Image generated: {fname} ({size_kb:.1f}KB)")
            return f"✅ Image generated: uploads/{fname} ({size_kb:.1f}KB)\nPrompt: {prompt}"

        elif name == "image_analyze":
            image_path = args["image_path"]
            question = args.get("question", "Describe this image in detail.")
            import base64 as b64mod

            if image_path.startswith("http://") or image_path.startswith("https://"):
                image_url = image_path
                content_parts = [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": question},
                ]
            else:
                img_path = Path(image_path)
                if not img_path.is_absolute():
                    img_path = WORKSPACE_DIR / img_path
                if not img_path.exists():
                    return f"❌ Image not found: {image_path}"
                ext = img_path.suffix.lower()
                mime_map = {
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".gif": "image/gif",
                    ".webp": "image/webp",
                }
                mime = mime_map.get(ext, "image/png")
                img_b64 = b64mod.b64encode(img_path.read_bytes()).decode()
                content_parts = [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_b64}"}},
                    {"type": "text", "text": question},
                ]
            api_key = vault.get("openai_api_key")
            if api_key:
                resp = _http_post(
                    "https://api.openai.com/v1/chat/completions",
                    {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    {
                        "model": "gpt-4.1-nano",
                        "messages": [{"role": "user", "content": content_parts}],
                        "max_tokens": 1000,
                    },
                )
                return resp["choices"][0]["message"]["content"]  # type: ignore[no-any-return]
            api_key = vault.get("anthropic_api_key")
            if api_key:
                img_source = content_parts[0]["image_url"]["url"]
                if img_source.startswith("data:"):
                    media_type = img_source.split(";")[0].split(":")[1]
                    data = img_source.split(",")[1]
                    img_block = {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}}
                else:
                    img_block = {"type": "image", "source": {"type": "url", "url": img_source}}
                resp = _http_post(
                    "https://api.anthropic.com/v1/messages",
                    {"x-api-key": api_key, "Content-Type": "application/json", "anthropic-version": "2023-06-01"},
                    {
                        "model": "claude-sonnet-4-6",
                        "max_tokens": 1000,
                        "messages": [{"role": "user", "content": [img_block, {"type": "text", "text": question}]}],
                    },
                )
                return resp["content"][0]["text"]  # type: ignore[no-any-return]
            return "❌ No vision API key found (need OpenAI or Anthropic)"

        elif name == "tts":
            text = args["text"]
            voice = args.get("voice", "nova")
            api_key = vault.get("openai_api_key")
            if not api_key:
                return "❌ OpenAI API key not found"
            save_dir = WORKSPACE_DIR / "uploads"
            save_dir.mkdir(exist_ok=True)
            fname = f"tts_{int(time.time())}.mp3"
            save_path = save_dir / fname
            data = json.dumps({"model": "tts-1", "input": text, "voice": voice}).encode()
            req = urllib.request.Request(
                "https://api.openai.com/v1/audio/speech",
                data=data,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                audio = resp.read()
            save_path.write_bytes(audio)
            size_kb = len(audio) / 1024
            log.info(f"[AUDIO] TTS generated: {fname} ({size_kb:.1f}KB)")
            return f"✅ TTS generated: uploads/{fname} ({size_kb:.1f}KB)\nText: {text[:100]}"

        elif name == "stt":
            api_key = vault.get("openai_api_key")
            if not api_key:
                return "❌ OpenAI API key not found"
            audio_path = args.get("audio_path", "")
            audio_b64 = args.get("audio_base64", "")
            lang = args.get("language", "ko")
            if audio_path:
                fpath = Path(audio_path).expanduser()
                if not fpath.exists():
                    return f"❌ File not found: {audio_path}"
                audio_data = fpath.read_bytes()
                fname = fpath.name
            elif audio_b64:
                audio_data = base64.b64decode(audio_b64)
                fname = "audio.webm"
            else:
                return "❌ Provide audio_path or audio_base64"
            boundary = secrets.token_hex(16)
            body = b""
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{fname}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()
            body += audio_data
            body += f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="model"\r\n\r\nwhisper-1'.encode()
            body += f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="language"\r\n\r\n{lang}'.encode()
            body += f"\r\n--{boundary}--\r\n".encode()
            req = urllib.request.Request(
                "https://api.openai.com/v1/audio/transcriptions",
                data=body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
            text = result.get("text", "")
            log.info(f"[MIC] STT transcribed: {len(text)} chars")
            return f"🎤 Transcription:\n{text}"

        elif name == "screenshot":
            region = args.get("region", "full")
            fname = f"screenshot_{int(time.time())}.png"
            fpath = WORKSPACE_DIR / "uploads" / fname
            fpath.parent.mkdir(exist_ok=True)
            try:
                cmd = (
                    ["import", "-window", "root", str(fpath)]
                    if region == "full"
                    else ["import", "-crop", region, "-window", "root", str(fpath)]
                )
                try:
                    if region == "full":
                        subprocess.run(["scrot", str(fpath)], timeout=10, check=True)
                    else:
                        subprocess.run(["scrot", "-a", region, str(fpath)], timeout=10, check=True)
                except FileNotFoundError:
                    subprocess.run(cmd, timeout=10, check=True)
                size_kb = fpath.stat().st_size / 1024
                return f"✅ Screenshot saved: uploads/{fname} ({size_kb:.1f}KB)"
            except Exception as e:
                return f"❌ Screenshot failed: {e}"

        elif name == "tts_generate":
            return _handle_tts_generate(args)

        else:
            return f"❌ Unknown legacy tool: {name}"

    except PermissionError as e:
        return f"❌ Permission denied: {e}"
    except Exception as e:
        log.error(f"Tool error ({name}): {e}")
        return f"❌ Tool error: {str(e)[:200]}"


def _handle_tts_generate(args: dict) -> str:
    """TTS generation handler — Google TTS (free) or OpenAI TTS."""
    text = args.get("text", "")
    if not text:
        return "❌ text is required"
    provider = args.get("provider", "google")
    language = args.get("language", "ko-KR")
    output_path = args.get("output", "")

    if not output_path:
        fname = f"tts_{secrets.token_hex(4)}.mp3"
        output_dir = WORKSPACE_DIR / "tts_output"
        output_dir.mkdir(exist_ok=True)
        output_path = str(output_dir / fname)

    import urllib.parse

    if provider == "google":
        chunks = []
        while text:
            chunk = text[:200]
            text = text[200:]
            chunks.append(chunk)

        audio_data = b""
        for chunk in chunks:
            encoded = urllib.parse.quote(chunk)
            url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={encoded}&tl={language}&client=tw-ob"
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": "https://translate.google.com/",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    audio_data += resp.read()
            except Exception as e:
                return f"❌ Google TTS failed: {e}"

        Path(output_path).write_bytes(audio_data)
        return f"🔊 TTS generated: {output_path} ({len(audio_data)} bytes, {len(chunks)} chunks)"

    elif provider == "openai":
        api_key = vault.get("openai_api_key") or ""
        if not api_key:
            return "❌ OpenAI API key not configured in vault"
        voice = args.get("voice", "alloy")
        body = json.dumps({"model": "tts-1", "input": text[:4096], "voice": voice}).encode()
        req = urllib.request.Request(
            "https://api.openai.com/v1/audio/speech",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                audio = resp.read()
            Path(output_path).write_bytes(audio)
            return f"🔊 TTS generated: {output_path} ({len(audio)} bytes, voice={voice})"
        except Exception as e:
            return f"❌ OpenAI TTS failed: {e}"

    return f"❌ Unknown TTS provider: {provider}"
