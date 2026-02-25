# 특갤 홍보글 초안

## 제목
pip install 한줄로 AI 비서 셀프호스팅하는거 만들었다

## 본문

바이브코딩으로 개인 AI 게이트웨이 만들었음

이름: 삶앎 (SalmAlm)
삶(Life) + 앎(Knowledge) = 삶앎

pipx install salmalm 치면 끝임
(pipx 없으면 pip install pipx 먼저)
Docker 필요없고 Node.js 필요없음
걍 파이썬만 있으면 됨

salmalm 실행하면 http://localhost:18800 에서 웹UI 뜨고
설정 마법사에서 API키 넣으면 바로 쓸 수 있음


**뭘 할 수 있냐면**

- Claude, GPT, Gemini, Grok, Ollama 다 지원
- 질문 복잡도에 따라 모델 자동 선택 (간단한건 Haiku, 복잡한건 Opus)
- API 비용 83% 절감 (하루 $7 → $1.2)
- 도구 62개 내장 (웹검색, 파일관리, 셸, 이미지생성, 브라우저자동화 등)
- 메모리 시스템 (대화 기억함, 자동으로 관련 기억 불러옴)
- 서브에이전트 (백그라운드 AI 워커 생성)
- 확장 사고 (4단계)
- 텔레그램/디스코드 봇 연동
- 타임캡슐, 데드맨스위치, 섀도우모드 등 ㅋㅋ


**남들이 안 만드는 기능도 넣었음**

- 데드맨 스위치: 며칠간 안 쓰면 자동으로 이메일 보내거나 명령 실행
- 섀도우 모드: AI가 내 말투 학습해서 내가 없을 때 대리 응답
- 자기진화 프롬프트: 대화하면서 AI가 알아서 성격 규칙 만듦
- A/B 분할 응답: 같은 질문에 두 모델 답변 나란히 비교
- 라이프 대시보드: 지출, 습관, 감정, 루틴 통합 관리


**스펙**

- Python 파일 192개 / 52,760줄
- 테스트 1,908개 통과
- 도구 62개
- stdlib만 사용 (외부 의존성 0)
- MIT 라이선스


GitHub: https://github.com/hyunjun6928-netizen/salmalm
PyPI: https://pypi.org/project/salmalm/

혼자 만들었고 바이브코딩 비중 높음
관심있으면 써보고 피드백 주면 감사

```
pipx install salmalm
salmalm --open
```
