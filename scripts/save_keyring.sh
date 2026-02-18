#!/bin/bash
# Save vault password to OS keyring
# Usage: ./scripts/save_keyring.sh

echo -n "Enter vault password to save: "
read -s PW
echo

if command -v secret-tool &>/dev/null; then
    echo "$PW" | secret-tool store --label="삶앎 Vault" service salmalm type vault
    echo "✅ Saved to GNOME Keyring"
elif command -v security &>/dev/null; then
    security add-generic-password -s salmalm -a vault -w "$PW" -U
    echo "✅ Saved to macOS Keychain"
else
    echo "❌ No keyring tool found (need secret-tool or security)"
    echo "💡 Use .env file instead: echo 'SALMALM_VAULT_PW=your_password' > .env"
    exit 1
fi
