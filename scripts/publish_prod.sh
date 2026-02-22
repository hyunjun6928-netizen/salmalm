#!/bin/bash
# Publish to real PyPI (production release)
# Usage: ./scripts/publish_prod.sh
set -e

BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH" != "main" ]; then
    echo "❌ Must be on 'main' branch to publish to PyPI. Current: $BRANCH"
    exit 1
fi

echo "🔨 Building..."
cd "$(dirname "$0")/.."
python3 scripts/bundle_js.py
python3 -m build

VERSION=$(python3 -c "from salmalm import __version__; print(__version__)")
echo "📦 Uploading v${VERSION} to PyPI..."
python3 -m twine upload dist/salmalm-${VERSION}*

echo "✅ v${VERSION} published to PyPI"
