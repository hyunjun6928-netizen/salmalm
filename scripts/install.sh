#!/usr/bin/env bash
# SalmAlm Quick Installer
# Usage: curl -fsSL https://raw.githubusercontent.com/hyunjun6928-netizen/salmalm/main/scripts/install.sh | bash
set -euo pipefail

VENV_DIR="${SALMALM_VENV:-$HOME/.salmalm-env}"
MIN_PYTHON="3.10"
BOLD='\033[1m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BOLD}😈 SalmAlm Installer${NC}"
echo ""

# Find Python 3.10+
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON="$cmd"
            echo -e "  ${GREEN}✓${NC} Found $cmd ($ver)"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo -e "  ${RED}✗${NC} Python 3.10+ required but not found."
    echo "  Install Python: https://www.python.org/downloads/"
    exit 1
fi

# Create venv
if [ -d "$VENV_DIR" ]; then
    echo -e "  ${GREEN}✓${NC} Existing venv: $VENV_DIR"
else
    echo -n "  Creating venv at $VENV_DIR... "
    "$PYTHON" -m venv "$VENV_DIR"
    echo -e "${GREEN}done${NC}"
fi

# Activate and install
source "$VENV_DIR/bin/activate"
echo -n "  Installing salmalm... "
pip install --quiet --upgrade salmalm
echo -e "${GREEN}done${NC}"

# Verify
VER=$(python -c "import salmalm; print(salmalm.__version__)" 2>/dev/null || echo "?")
echo -e "  ${GREEN}✓${NC} SalmAlm v${VER} installed"

# Add to PATH
SALMALM_BIN="$VENV_DIR/bin"
PATH_LINE="export PATH=\"$SALMALM_BIN:\$PATH\""
ADDED_PATH=false

for rcfile in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile"; do
    if [ -f "$rcfile" ]; then
        if ! grep -qF "salmalm-env/bin" "$rcfile" 2>/dev/null; then
            echo "" >> "$rcfile"
            echo "# SalmAlm" >> "$rcfile"
            echo "$PATH_LINE" >> "$rcfile"
            ADDED_PATH=true
        fi
    fi
done

export PATH="$SALMALM_BIN:$PATH"

echo ""
echo -e "${BOLD}${GREEN}✅ Installation complete!${NC}"
echo ""
echo "  Run now:    salmalm"
echo "  Open:       http://127.0.0.1:18800"
if [ "$ADDED_PATH" = true ]; then
    echo ""
    echo "  PATH updated. Restart your terminal or run:"
    echo "    source ~/.bashrc  # or ~/.zshrc"
fi
echo ""
echo -e "  ${BOLD}Tip:${NC} Create a desktop shortcut: salmalm --shortcut"
