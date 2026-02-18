#!/usr/bin/env python3
"""삶앎 초기 설정 — Vault에 API 키 + 텔레그램 설정 저장"""
import getpass, json, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from server import vault, VAULT_FILE, _init_audit_db

_init_audit_db()

print("😈 삶앎 (SalmAlm) 초기 설정\n")

# Vault password
if VAULT_FILE.exists():
    pw = getpass.getpass("마스터 비밀번호 (기존): ")
    if not vault.unlock(pw):
        print("❌ 비밀번호 틀림")
        sys.exit(1)
    print("🔓 Vault 잠금 해제\n")
else:
    pw = getpass.getpass("마스터 비밀번호 (신규 설정): ")
    pw2 = getpass.getpass("비밀번호 확인: ")
    if pw != pw2:
        print("❌ 비밀번호 불일치")
        sys.exit(1)
    vault.create(pw)
    print("🔐 Vault 생성 완료\n")

def ask(prompt, current=None):
    default = f" [{current}]" if current else ""
    val = input(f"{prompt}{default}: ").strip()
    return val if val else current

# Telegram
print("📡 텔레그램 설정")
tg_token = ask("  봇 토큰 (@BotFather)", vault.get('telegram_token'))
tg_owner = ask("  Owner ID (니 텔레그램 숫자 ID)", vault.get('telegram_owner_id'))
if tg_token: vault.set('telegram_token', tg_token)
if tg_owner: vault.set('telegram_owner_id', tg_owner)

# LLM API Keys
print("\n🤖 LLM API 키 (빈칸=스킵)")
providers = [
    ('anthropic_api_key', 'Anthropic (Claude)'),
    ('openai_api_key', 'OpenAI (GPT)'),
    ('xai_api_key', 'xAI (Grok)'),
    ('google_api_key', 'Google (Gemini)'),
]
for key, name in providers:
    current = vault.get(key)
    masked = f"{'*'*8}...{current[-4:]}" if current else None
    val = ask(f"  {name}", masked)
    if val and not val.startswith('*'):
        vault.set(key, val)

# Brave Search
print("\n🔍 검색")
brave = ask("  Brave Search API 키", vault.get('brave_api_key'))
if brave and not brave.startswith('*'): vault.set('brave_api_key', brave)

print(f"\n✅ 설정 완료! Vault 키 목록: {vault.keys()}")
print(f"\n🚀 실행: python3 server.py")
print(f"   또는: SALMALM_VAULT_PW='{pw}' python3 server.py  (자동 잠금해제)")
