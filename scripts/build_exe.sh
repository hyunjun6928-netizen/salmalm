#!/bin/bash
# Build SalmAlm desktop executable
# Requirements: pip install pyinstaller

set -e

echo "📦 Building SalmAlm desktop app..."

cd "$(dirname "$0")/.."

# Install build deps
pip install pyinstaller --quiet

# Build
pyinstaller \
    --onefile \
    --windowed \
    --name SalmAlm \
    --add-data "salmalm/static:salmalm/static" \
    --hidden-import salmalm \
    scripts/launcher.py

echo ""
echo "✅ Build complete!"
echo "   Output: dist/SalmAlm"
echo "   (Windows: dist/SalmAlm.exe)"
echo ""
echo "📋 Distribution:"
echo "   1. Share the single file — users just double-click it"
echo "   2. No Python installation needed on their machine"
