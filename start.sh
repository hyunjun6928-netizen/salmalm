#!/bin/bash
# 삶앎 (SalmAlm) 시작 스크립트
cd "$(dirname "$0")"

# Priority order for vault password:
# 1. SALMALM_VAULT_PW already set in environment
# 2. .env file
# 3. OS keyring (via Python keyring or secret-tool)
# 4. Interactive prompt at web UI

if [ -z "$SALMALM_VAULT_PW" ] && [ -f .env ]; then
    export $(grep -v '^#' .env | grep -v '^$' | xargs)
fi

# Try OS keyring if still unset
if [ -z "$SALMALM_VAULT_PW" ]; then
    # Linux (GNOME Keyring / KDE Wallet via secret-tool)
    if command -v secret-tool &>/dev/null; then
        PW=$(secret-tool lookup service salmalm type vault 2>/dev/null)
        [ -n "$PW" ] && export SALMALM_VAULT_PW="$PW"
    # macOS Keychain
    elif command -v security &>/dev/null; then
        PW=$(security find-generic-password -s salmalm -a vault -w 2>/dev/null)
        [ -n "$PW" ] && export SALMALM_VAULT_PW="$PW"
    fi
fi

export SALMALM_PORT="${SALMALM_PORT:-18800}"
echo "😈 삶앎 시작..."
exec python3 server.py
