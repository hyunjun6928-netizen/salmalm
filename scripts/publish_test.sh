#!/bin/bash
# Publish to TestPyPI for staging verification
# Usage: ./scripts/publish_test.sh
set -e

echo "🔨 Building..."
cd "$(dirname "$0")/.."
python3 scripts/bundle_js.py
python3 -m build

VERSION=$(python3 -c "from salmalm import __version__; print(__version__)")
echo "📦 Uploading v${VERSION} to TestPyPI..."
python3 -m twine upload --repository testpypi dist/salmalm-${VERSION}*

echo ""
echo "✅ Done! Install with:"
echo "  pipx install salmalm==${VERSION} --force --pip-args='--no-cache-dir --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/'"
echo ""
echo "  or:"
echo "  pip install salmalm==${VERSION} --no-cache-dir --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/"
