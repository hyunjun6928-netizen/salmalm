#!/bin/bash
# 삶앎 (SalmAlm) 시작 스크립트
cd "$(dirname "$0")"

# Vault password: set SALMALM_VAULT_PW in .env or environment
# If not set, will prompt at http://127.0.0.1:18800
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

export SALMALM_PORT="${SALMALM_PORT:-18800}"
echo "😈 삶앎 시작..."
exec python3 server.py
