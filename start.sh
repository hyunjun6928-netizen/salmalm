#!/bin/bash
# 삶앎 (SalmAlm) 시작 스크립트
cd "$(dirname "$0")"
export SALMALM_VAULT_PW="salmalm_$(hostname)_2026"
export SALMALM_PORT=18800
echo "😈 삶앎 시작..."
exec python3 server.py
