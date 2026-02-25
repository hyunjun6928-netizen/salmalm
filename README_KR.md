<div align="center">

# 😈 삶앎 (SalmAlm)

### AI 비서, pip 한 줄이면 끝

[![PyPI](https://img.shields.io/pypi/v/salmalm)](https://pypi.org/project/salmalm/)
[![Python](https://img.shields.io/badge/python-3.10%E2%80%933.14-blue)](https://pypi.org/project/salmalm/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-1%2C908%20passed-brightgreen)]()
[![Tools](https://img.shields.io/badge/tools-66-blueviolet)]()

**[English README](README.md)**

</div>

---

## 삶앎이 뭔가요?

**셀프호스팅 AI 비서**입니다. 웹 UI, 텔레그램/디스코드 봇, 66개 도구, 메모리 시스템, 서브에이전트, 멀티 모델 라우팅을 하나의 Python 패키지로 제공합니다.

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
# 1. 설치 (권장)
pipx install salmalm

# 또는 venv로
python3 -m venv ~/.salmalm-env && ~/.salmalm-env/bin/pip install salmalm

# 2. 실행
salmalm --open

# 3. 브라우저에서 설정 마법사 → API 키 입력 → 대화 시작!
```

**자연어로 말하면 됩니다.** 62개 도구를 AI가 알아서 선택합니다.

```
"오늘 날씨 어때?"          → 웹 검색 + 답변
"이 코드 리뷰해줘"         → 파일 분석
"/help"                    → 전체 명령어
```

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

### 독자적 기능

| 기능 | 설명 |
|---|---|
| **자기진화 프롬프트** | 대화에서 성격 규칙을 자동 학습 (최대 20개, FIFO) |
| **데드맨 스위치** | N일간 비활성 시 자동 조치 (이메일, 명령 실행) |
| **섀도우 모드** | 소통 스타일 학습, 부재 시 대리 응답 가능 |
| **라이프 대시보드** | 지출, 습관, 캘린더, 감정, 루틴 통합 뷰 |
| **감정 인식 응답** | NLP 신호로 감정 상태 감지, 톤 자동 조절 |
| **A/B 분할 응답** | 같은 질문에 두 모델 응답 나란히 비교 |
| **타임캡슐** | 미래의 나에게 암호화된 메시지 예약 |
| **사고 스트림** | 해시태그 검색과 감정 추적 포함 개인 일기 |
| **에이전트 간 통신** | HMAC-SHA256 서명된 SalmAlm 인스턴스 간 통신 |
| **워크플로우 엔진** | 조건/루프 포함 다단계 AI 워크플로우 |
| **메시지 큐** | 5가지 모드: collect, steer, followup, steer-backlog, interrupt |
| **MCP 마켓플레이스** | Model Context Protocol 도구 서버 설치/관리 |

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
| 테스트 | 1,908 통과 |
| 최대 순환복잡도 | ≤20 |

---

## 📄 라이선스

[MIT](LICENSE)

---

<div align="center">

**삶앎** = 삶(Life) + 앎(Knowledge)

*당신의 삶을, AI가 이해합니다.*

</div>
