#!/usr/bin/env python3
"""Bump SalmAlm version in all source-of-truth locations.

Usage: python scripts/bump_version.py 0.17.0
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = [
    (ROOT / "pyproject.toml", re.compile(r'^(version\s*=\s*")[^"]+(")', re.M)),
    (ROOT / "salmalm" / "__init__.py", re.compile(r"(__version__\s*=\s*')[^']+(')")),
]


def bump(version: str) -> None:
    if not re.match(r"^\d+\.\d+\.\d+([a-z]\d+)?$", version):
        print(f"Invalid version: {version}", file=sys.stderr)
        sys.exit(1)
    for path, pattern in TARGETS:
        text = path.read_text()
        new_text, n = pattern.subn(rf"\g<1>{version}\2", text)
        if n == 0:
            print(f"WARNING: no match in {path}", file=sys.stderr)
        else:
            path.write_text(new_text)
            print(f"  {path.relative_to(ROOT)}: {n} replacement(s)")
    print(f"\n✅ Version bumped to {version}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/bump_version.py <version>", file=sys.stderr)
        sys.exit(1)
    bump(sys.argv[1])
