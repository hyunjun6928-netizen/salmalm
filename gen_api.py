#!/usr/bin/env python3
"""Generate API documentation from SalmAlm module docstrings.

SalmAlm 모듈 docstring에서 API 문서를 자동 생성합니다.

Usage:
    python docs/gen_api.py [--output docs/api/generated.md]
"""
import ast
import os
import sys
from pathlib import Path

SALMALM_ROOT = Path(__file__).resolve().parent.parent / "salmalm"
OUTPUT_DIR = Path(__file__).resolve().parent / "api"

# Subpackages to document / 문서화할 서브패키지
PACKAGES = {
    "core": "Core — Engine, LLM, Session / 코어 — 엔진, LLM, 세션",
    "tools": "Tools — 58+ Built-in Tools / 도구 — 58개 이상 내장 도구",
    "features": "Features — Commands, RAG, MCP / 기능 — 명령어, RAG, MCP",
    "channels": "Channels — Telegram, Discord / 채널 — 텔레그램, 디스코드",
    "security": "Security — Crypto, Sandbox / 보안 — 암호화, 샌드박스",
    "utils": "Utils — HTTP, Queue, Retry / 유틸리티 — HTTP, 큐, 재시도",
    "web": "Web — Server, WebSocket, OAuth / 웹 — 서버, 웹소켓, OAuth",
}


def extract_module_info(filepath: Path) -> dict:
    """Extract docstring, classes, and functions from a Python file."""
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        return {"docstring": None, "classes": [], "functions": []}

    docstring = ast.get_docstring(tree)
    classes = []
    functions = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            cls_doc = ast.get_docstring(node)
            methods = []
            for item in ast.iter_child_nodes(node):
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not item.name.startswith("_"):
                        args = [a.arg for a in item.args.args if a.arg != "self"]
                        methods.append({
                            "name": item.name,
                            "args": args,
                            "docstring": ast.get_docstring(item),
                            "is_async": isinstance(item, ast.AsyncFunctionDef),
                        })
            classes.append({
                "name": node.name,
                "docstring": cls_doc,
                "methods": methods,
            })
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                args = [a.arg for a in node.args.args if a.arg != "self"]
                functions.append({
                    "name": node.name,
                    "args": args,
                    "docstring": ast.get_docstring(node),
                    "is_async": isinstance(node, ast.AsyncFunctionDef),
                })

    return {"docstring": docstring, "classes": classes, "functions": functions}


def generate_module_md(module_path: str, info: dict) -> str:
    """Generate markdown for a single module."""
    lines = [f"### `{module_path}`", ""]
    if info["docstring"]:
        lines.append(f"> {info['docstring'].split(chr(10))[0]}")
        lines.append("")

    for cls in info["classes"]:
        prefix = "class"
        lines.append(f"#### `{prefix} {cls['name']}`")
        if cls["docstring"]:
            lines.append(f"> {cls['docstring'].split(chr(10))[0]}")
        lines.append("")
        for m in cls["methods"][:10]:  # limit to 10 methods
            async_prefix = "async " if m["is_async"] else ""
            args_str = ", ".join(m["args"][:5])
            lines.append(f"- `{async_prefix}{m['name']}({args_str})`")
            if m["docstring"]:
                lines.append(f"  — {m['docstring'].split(chr(10))[0]}")
        lines.append("")

    for fn in info["functions"][:15]:  # limit
        async_prefix = "async " if fn["is_async"] else ""
        args_str = ", ".join(fn["args"][:5])
        lines.append(f"- `{async_prefix}{fn['name']}({args_str})`")
        if fn["docstring"]:
            lines.append(f"  — {fn['docstring'].split(chr(10))[0]}")
    lines.append("")
    return "\n".join(lines)


def main():
    output_path = OUTPUT_DIR / "generated.md"
    if len(sys.argv) > 2 and sys.argv[1] == "--output":
        output_path = Path(sys.argv[2])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sections = ["# Auto-Generated API Reference", "# 자동 생성 API 레퍼런스", "",
                 "Generated from source docstrings. Run `python docs/gen_api.py` to update.",
                 "소스 docstring에서 생성됨. `python docs/gen_api.py`를 실행하여 업데이트.", ""]

    for pkg, desc in PACKAGES.items():
        pkg_dir = SALMALM_ROOT / pkg
        if not pkg_dir.is_dir():
            continue
        sections.append(f"## {pkg}/ — {desc}")
        sections.append("")

        for py_file in sorted(pkg_dir.glob("*.py")):
            if py_file.name == "__pycache__":
                continue
            module_path = f"salmalm.{pkg}.{py_file.stem}"
            info = extract_module_info(py_file)
            if info["classes"] or info["functions"] or info["docstring"]:
                sections.append(generate_module_md(module_path, info))

    # Also scan top-level modules / 최상위 모듈도 스캔
    sections.append("## salmalm/ — Top-level Modules / 최상위 모듈")
    sections.append("")
    for py_file in sorted(SALMALM_ROOT.glob("*.py")):
        if py_file.name.startswith("__"):
            continue
        module_path = f"salmalm.{py_file.stem}"
        info = extract_module_info(py_file)
        if info["classes"] or info["functions"]:
            sections.append(generate_module_md(module_path, info))

    content = "\n".join(sections)
    output_path.write_text(content, encoding="utf-8")
    print(f"✅ Generated {output_path} ({len(content)} bytes)")
    print(f"   Packages scanned: {len(PACKAGES)}")


if __name__ == "__main__":
    main()
