# 특갤 홍보글 — OAuth 편

## 제목
pip install 한줄로 Claude/GPT OAuth 인증 되는 AI 비서 만들었다

## 본문

전에 삶앎(SalmAlm) 올렸던 사람임
셀프호스팅 AI 게이트웨이인데, 이번에 OAuth 지원 추가됨

보통 AI API 쓰려면 API 키를 직접 관리해야 하잖음
키 유출되면 요금 폭탄 맞고... 환경변수에 넣어도 찝찝하고

삶앎은 두 가지 방식 다 지원함:

**1. 일반 방식 (API 키)**
- 설정 마법사에서 키 붙여넣기 → 끝
- AES-256-GCM 암호화 볼트에 저장 (PBKDF2 200K iterations)
- 메모리에 API 키 남으면 자동 스크러빙

**2. OAuth 방식 (키 없이 인증)**
```
/oauth setup anthropic
→ 브라우저에서 Anthropic 로그인
→ 토큰 자동 발급 + 볼트에 암호화 저장
→ 만료되면 자동 갱신 (refresh token)
```

OpenAI도 동일하게 가능

**OAuth의 장점:**
- API 키가 아예 없으니 유출 자체가 불가능
- 토큰 만료 시 자동 갱신
- 권한 범위(scope) 제한 가능
- 언제든 /oauth revoke로 즉시 철회


**그 외 보안:**
- 볼트: PBKDF2-200K + AES-256-GCM (cryptography 패키지 설치 시)
- 없으면 HMAC-CTR 폴백
- 로컬호스트 바인딩 기본 (외부 노출 차단)
- SSRF 방어, CSRF 보호, CSP, 감사 로그
- 보안 테스트 150개+


**설치:**
```
pipx install salmalm
salmalm --open
```

GitHub: https://github.com/hyunjun6928-netizen/salmalm
PyPI: https://pypi.org/project/salmalm/

혼자 바이브코딩으로 만들었음
Python 192파일 / 52,760줄 / 테스트 1,879개 / 도구 62개 / stdlib only

질문이나 피드백 환영
