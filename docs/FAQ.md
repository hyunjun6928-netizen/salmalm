# FAQ (자주 묻는 질문)

## 설치/실행

### Q: Python 몇 버전 필요해요?
Python 3.9 이상이면 됩니다. 3.12+ 권장.

### Q: pip install 했는데 `salmalm` 명령어가 안 됩니다
PATH에 안 잡힌 경우입니다. `python -m salmalm`으로 실행하세요.

### Q: Windows에서 실행하면 에러가 납니다
cmd에서 실행하세요 (PowerShell 아님). 한글 경로가 있으면 에러날 수 있습니다.
```
python -m salmalm
```

### Q: Docker로 실행하려면?
```bash
git clone https://github.com/hyunjun6928-netizen/salmalm.git
cd salmalm
docker compose up -d
# → http://localhost:18800
```

---

## API 키

### Q: API 키 없이 쓸 수 있나요?
네. Ollama를 설치하면 로컬 LLM으로 API 키 없이 사용 가능합니다.
```bash
ollama pull llama3.2
python -m salmalm
# 온보딩에서 Ollama URL: http://localhost:11434/v1
```

### Q: API 키는 어디서 발급하나요?
| Provider | URL |
|----------|-----|
| Anthropic (Claude) | https://console.anthropic.com/settings/keys |
| OpenAI (GPT) | https://platform.openai.com/api-keys |
| xAI (Grok) | https://console.x.ai |
| Google (Gemini) | https://aistudio.google.com/apikey |
| Brave Search | https://brave.com/search/api/ (무료) |

### Q: API 키는 어디에 저장되나요?
두 가지 방식:
1. **`.env` 파일** — 프로젝트 루트에 평문 저장 (간편)
2. **Vault** — AES-256-GCM 암호화 저장 (보안)

`.env`가 있으면 vault보다 우선합니다.

---

## 비밀번호/Vault

### Q: 비밀번호를 잊어버렸어요
vault 파일을 삭제하면 초기화됩니다:
- **Windows**: `del %USERPROFILE%\.salmalm\vault.enc`
- **Linux/Mac**: `rm ~/.salmalm/vault.enc`

삭제 후 `python -m salmalm` 하면 처음부터 다시 설정합니다.
⚠️ vault에 저장된 API 키도 같이 삭제됩니다. `.env` 파일에 백업하세요.

### Q: 비밀번호 없이 쓰고 싶어요
첫 실행 시 "아니요, 바로 시작" 선택하면 비밀번호 없이 사용됩니다.
이미 설정했다면: Settings → 🔒 마스터 비밀번호 → "비밀번호 해제"

### Q: 비밀번호를 나중에 추가할 수 있나요?
네. Settings → 🔒 마스터 비밀번호 → 새 비밀번호 설정

---

## 모델/사용

### Q: 어떤 모델을 쓰는 게 좋아요?
- **일반 대화**: Claude Sonnet 또는 GPT-4.1 (가성비)
- **복잡한 코딩**: Claude Opus 또는 o3 (최고 성능)
- **빠른 응답**: Gemini Flash 또는 GPT-4.1-nano (저비용)
- **무료**: Ollama + llama3.2 (로컬)

### Q: 모델을 바꾸려면?
웹 UI 좌측 Settings → Model 드롭다운에서 선택하거나,
채팅에서 `/model anthropic/claude-opus-4-6` 입력.

### Q: 비용이 얼마나 드나요?
Settings → Token Usage에서 실시간 확인 가능합니다.
일반 사용 기준 하루 $0.5~$2 정도.

---

## 이미지

### Q: 이미지 생성은 어떻게 하나요?
채팅에서 자연스럽게 요청하면 됩니다: "고양이 그림 그려줘"
DALL-E 또는 xAI Aurora를 사용합니다. OpenAI API 키가 필요합니다.

### Q: 이미지 분석은?
이미지 파일을 업로드하거나 URL을 보내면 `image_analyze` 도구로 분석합니다.
GPT-4o 또는 Claude Vision을 사용합니다.

---

## 문제 해결

### Q: "Connection refused" 에러
서버가 실행 중인지 확인하세요. `python -m salmalm` 후 http://localhost:18800 접속.

### Q: 텔레그램 봇이 응답 안 해요
1. `.env`에 `TELEGRAM_TOKEN`과 `TELEGRAM_OWNER_ID` 설정 확인
2. 다른 프로세스가 같은 봇 토큰으로 polling 중이면 충돌합니다

### Q: 업데이트하려면?
```bash
pip install --upgrade salmalm
python -m salmalm
```
또는 웹 UI Settings → Update → Check for Updates

### Q: 로그는 어디에 있나요?
`~/.salmalm/salmalm.log` (또는 프로젝트 디렉터리의 `salmalm.log`)
