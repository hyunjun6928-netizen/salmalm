# Use Cases (활용 사례)

## 1. 🤖 텔레그램 AI 비서

스마트폰에서 언제든 AI에게 질문하고, 파일 분석하고, 웹 검색까지.

### 설정

```env
# .env
ANTHROPIC_API_KEY=sk-ant-...
TELEGRAM_TOKEN=123456:ABC...
TELEGRAM_OWNER_ID=7466506107
BRAVE_API_KEY=BSA...
```

```bash
pip install salmalm
python -m salmalm
```

### 할 수 있는 것

- 📝 코드 리뷰 요청 → AI가 분석하고 개선점 제시
- 🔍 "오늘 비트코인 가격" → 웹 검색으로 실시간 답변
- 📄 PDF/이미지 보내기 → 내용 요약
- ⏰ "/cron 매일 9시 뉴스 요약" → 스케줄 작업
- 💾 "/memo 내일 회의 3시" → 메모 저장 + 검색

---

## 2. 💻 로컬 코드 리뷰 봇

GitHub Copilot 대신, 내 코드베이스를 이해하는 AI 비서.

### 설정

```bash
pip install salmalm
python -m salmalm
# 브라우저에서 http://localhost:18800
# API 키 입력
```

### 워크플로우

1. 채팅에서 파일 경로 알려주기:
   ```
   /home/user/project/main.py 파일을 리뷰해줘
   ```

2. AI가 파일을 읽고 분석:
   - 버그 가능성
   - 성능 개선점
   - 보안 이슈
   - 리팩터링 제안

3. RAG로 프로젝트 문서 인덱싱:
   ```
   /rag index /home/user/project/docs/
   ```
   이후 "프로젝트 아키텍처가 뭐야?" 같은 질문에 문서 기반 답변.

---

## 3. 🦙 오프라인 AI (Ollama)

인터넷 없이, API 키 없이, 완전 로컬에서 AI 사용.

### 설정

```bash
# 1. Ollama 설치
curl -fsSL https://ollama.com/install.sh | sh

# 2. 모델 다운로드
ollama pull llama3.2        # 3GB, 일반 대화용
ollama pull codellama:13b   # 7GB, 코딩용
ollama pull mistral         # 4GB, 다목적

# 3. SalmAlm 실행
pip install salmalm
python -m salmalm
# 온보딩에서 Ollama URL: http://localhost:11434/v1
```

### 장점

- 🔒 데이터가 절대 외부로 나가지 않음
- 💰 API 비용 0원
- 🌐 인터넷 불필요
- 🔄 모델 자유롭게 교체 (`/model ollama/llama3.2`)

### 제한

- GPU 없으면 느림 (CPU 추론 가능하지만 10~30초/답변)
- 로컬 모델은 Claude/GPT보다 성능 낮음
- 도구 호출(tool use)은 일부 모델만 지원

---

## 4. 🏢 팀 내부 AI 게이트웨이

Gateway-Node 아키텍처로 팀원들이 공유하는 AI 서버.

### 설정

```bash
# 메인 서버 (게이트웨이)
SALMALM_VAULT_PW=team_secret python -m salmalm --host 0.0.0.0

# 원격 워커 (GPU 서버)
python -m salmalm --node --gateway-url http://gateway:18800
```

### 구조

```
[팀원 브라우저] → [게이트웨이 서버] → [LLM API]
                         ↓
                  [GPU 노드 (Ollama)]
```

- 게이트웨이가 요청을 받고 적절한 노드로 라우팅
- GPU 노드에서 무거운 작업 (로컬 모델, 코드 실행)
- API 키를 게이트웨이에만 저장 (팀원에게 노출 안 됨)
