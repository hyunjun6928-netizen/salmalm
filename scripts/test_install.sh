#!/bin/bash
# Test fresh install in isolated venv
# Usage: ./scripts/test_install.sh
set -e

cd "$(dirname "$0")/.."
echo "🔨 Building..."
python3 scripts/bundle_js.py
python3 -m build

VERSION=$(python3 -c "from salmalm import __version__; print(__version__)")
VENV="/tmp/salmalm-test-venv"

echo "🧪 Creating fresh venv at $VENV..."
rm -rf "$VENV"
python3 -m venv "$VENV"

echo "📦 Installing salmalm v${VERSION} from local wheel..."
"$VENV/bin/pip" install --quiet dist/salmalm-${VERSION}-py3-none-any.whl

echo "✅ Installed. Testing import..."
"$VENV/bin/python" -c "from salmalm import __version__; print(f'salmalm v{__version__} OK')"

echo ""
echo "🚀 To test run:"
echo "  $VENV/bin/salmalm"
echo ""
echo "🧹 To cleanup:"
echo "  rm -rf $VENV"
