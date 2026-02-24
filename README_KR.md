<div align="center">

# 😈 삶앎 (SalmAlm)

### AI 비서, pip 한 줄이면 끝

[![PyPI](https://img.shields.io/pypi/v/salmalm)](https://pypi.org/project/salmalm/)
[![Python](https://img.shields.io/badge/python-3.10%E2%80%933.14-blue)](https://pypi.org/project/salmalm/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-1%2C879%20passed-brightgreen)]()
[![Tools](https://img.shields.io/badge/tools-62-blueviolet)]()

**[English README](README.md)**

</div>

---

## 삶앎이 뭔가요?

**셀프호스팅 AI 비서**입니다. 웹 UI, 텔레그램/디스코드 봇, 62개 도구, 메모리 시스템, 서브에이전트, 멀티 모델 라우팅을 하나의 Python 패키지로 제공합니다.

Docker 없이. Node.js 없이. 설정 파일 없이.

```bash
pip install salmalm
python3 -m salmalm
# → http://localhost:18800
```

첫 실행 시 **설정 마법사**가 뜹니다 — API 키 붙여넣기 → 모델 선택 → 끝!

---

## ⚡ 5분 퀵스타트

```bash
# 1. 설치
pip install salmalm

# 2. 실행
python3 -m salmalm --open

# 3. 브라우저에서 설정 마법사 → API 키 입력 → 대화 시작!
```

**자연어로 말하면 됩니다.** 62개 도구를 AI가 알아서 선택합니다.

```
"오늘 날씨 어때?"          → 웹 검색 + 답변
"이 코드 리뷰해줘"         → 파일 분석
"/help"                    → 전체 명령어
```

---

## 왜 삶앎?

| 기능 | 삶앎 | ChatGPT | OpenClaw | Open WebUI |
|---|:---:|:---:|:---:|:---:|
| 설치 | `pip install` | N/A | npm+설정 | Docker |
| 멀티 모델 자동 라우팅 | ✅ | ❌ | ✅ | ✅ |
| 메모리 (2계층+자동회상) | ✅ | ❌ | ✅ | ❌ |
| 서브에이전트 | ✅ | ❌ | ✅ | ❌ |
| 확장 사고 (4단계) | ✅ | ❌ | ✅ | ❌ |
| 암호화 볼트 | ✅ | N/A | ❌ | ❌ |
| 텔레그램+디스코드 | ✅ | ❌ | ✅ | ❌ |
| 로컬 LLM (Ollama) | ✅ | ❌ | ✅ | ✅ |
| 외부 의존성 제로* | ✅ | N/A | ❌ | ❌ |
| 비용 최적화 (83% 절감) | ✅ | ❌ | ❌ | ❌ |

*\*stdlib만 사용; vault 암호화용 `cryptography`는 선택*

---

## 🎯 주요 기능

### AI 엔진
- **3단계 자동 라우팅** — 간단→Haiku, 보통→Sonnet, 복잡→Opus/GPT-5
- **확장 사고** — 4단계 (low/medium/high/xhigh)
- **5단계 컨텍스트 압축** — 긴 대화도 맥락 유지
- **티어 모멘텀** — 복잡한 작업 중 모델 다운그레이드 방지

### 메모리
- **2계층** — MEMORY.md (장기) + memory/날짜.md (일별)
- **자동 회상** — 매 응답 전 관련 기억 검색·주입
- **자동 큐레이션** — 중요한 일별 메모를 장기 기억으로 승격
- **TF-IDF RAG** — 전 파일 코사인 유사도 검색

### 서브에이전트
- 독립 세션으로 백그라운드 AI 작업자 생성
- 에이전트별 사고 레벨, 라벨, 중간 조종 가능
- 완료 시 자동 알림 (WebSocket + 텔레그램)

### 62개 도구
셸 실행, 파일 관리, 웹 검색, Python 실행(옵트인), 이미지 생성, TTS, 브라우저 자동화(Playwright), 크론 작업, 시스템 모니터 등

### 웹 UI
- SSE 스트리밍 + 실시간 사고 과정 표시
- 멀티 파일 업로드 (드래그, 붙여넣기, 클립 버튼)
- 세션 관리 (분기, 롤백, 검색)
- 다크/라이트 테마, 한국어/영어 전환
- PWA 설치 가능

### 채널
- **웹** — `localhost:18800`
- **텔레그램** — 폴링 + 웹훅
- **디스코드** — 봇 + 스레드 지원

---

## 💰 비용 최적화

| 기법 | 효과 |
|---|---|
| 3단계 자동 라우팅 | 간단→$1/M, 복잡→$3/M |
| 동적 도구 로딩 | 62 → 0-12개/요청 |
| 도구 스키마 압축 | 91% 토큰 절감 |
| 의도 기반 max_tokens | 대화 512, 코드 4096 |

**하루 $7 → $1.2 (100회 호출 기준, 83% 절감)**

---

## 🔒 보안

위험한 기능은 **기본 OFF**:
- 네트워크 바인딩: `127.0.0.1` (외부 노출 차단)
- 셸 연산자: 차단
- Python eval: 비활성

SSRF 방어, CSRF 보호, CSP, 감사 로그, 메모리 스크러빙, 150+ 보안 테스트.

---

## 📊 코드베이스

| 항목 | 값 |
|---|---|
| Python 파일 | 192개 |
| 코드 라인 | ~52,760 |
| 도구 | 62개 |
| 테스트 | 1,879 통과 |
| 최대 순환복잡도 | ≤20 |

---

## 📄 라이선스

[MIT](LICENSE)

---

<div align="center">

**삶앎** = 삶(Life) + 앎(Knowledge)

*당신의 삶을, AI가 이해합니다.*

</div>
