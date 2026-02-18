import textwrap
from pathlib import Path
from datetime import datetime

from .constants import SOUL_FILE, AGENTS_FILE, MEMORY_FILE, USER_FILE, TOOLS_FILE, MEMORY_DIR, BASE_DIR, VERSION, KST
from .core import SkillLoader
from . import log

def build_system_prompt(full: bool = True) -> str:
    """Build system prompt from SOUL.md + context files.
    full=True: load everything (first message / refresh)
    full=False: minimal reload (mid-conversation refresh)
    """
    parts = []

    # SOUL.md (persona — FULL load, this IS who we are)
    if SOUL_FILE.exists():
        soul = SOUL_FILE.read_text(encoding='utf-8')
        if full:
            parts.append(soul)
        else:
            parts.append(soul[:3000])

    # IDENTITY.md
    id_file = BASE_DIR / 'IDENTITY.md'
    if id_file.exists():
        parts.append(id_file.read_text(encoding='utf-8'))

    # USER.md
    if USER_FILE.exists():
        parts.append(USER_FILE.read_text(encoding='utf-8'))

    # MEMORY.md (full on first load, recent on refresh)
    if MEMORY_FILE.exists():
        mem = MEMORY_FILE.read_text(encoding='utf-8')
        if full:
            parts.append(f"# 장기 기억\n{mem}")
        else:
            parts.append(f"# 장기 기억 (최근)\n{mem[-2000:]}")

    # Today's memory log
    today = datetime.now(KST).strftime('%Y-%m-%d')
    today_log = MEMORY_DIR / f'{today}.md'
    if today_log.exists():
        tlog = today_log.read_text(encoding='utf-8')
        parts.append(f"# 오늘의 기록\n{tlog[-2000:]}")

    # AGENTS.md (behavior rules)
    if AGENTS_FILE.exists():
        agents = AGENTS_FILE.read_text(encoding='utf-8')
        if full:
            parts.append(agents)
        else:
            parts.append(agents[:2000])

    # TOOLS.md
    tools_file = BASE_DIR / 'TOOLS.md'
    if tools_file.exists():
        parts.append(tools_file.read_text(encoding='utf-8'))

    # HEARTBEAT.md
    hb_file = BASE_DIR / 'HEARTBEAT.md'
    if hb_file.exists():
        parts.append(hb_file.read_text(encoding='utf-8'))

    # Context
    now = datetime.now(KST)
    parts.append(f"현재: {now.strftime('%Y-%m-%d %H:%M')} KST")

    # Available skills
    if full:
        skills = SkillLoader.scan()
        if skills:
            skill_lines = '\n'.join(
                f'  - {s["dir_name"]}: {s["description"]}' for s in skills)
            parts.append(f"## 사용 가능한 스킬\n{skill_lines}\n"
                         f"스킬 로드: skill_manage(action='load', skill_name='...')")

    # Tool instructions
    parts.append(textwrap.dedent("""
    [삶앎 Intelligence Engine v0.4.0]

    ## 🧠 메타 인지 프로토콜
    너는 단순 응답기가 아니라 자율적 문제 해결 엔진이다.
    모든 요청에 대해 이 사고 흐름을 따라라:

    1. **의도 파악**: 사용자가 진짜 원하는 게 뭔지 파악. 표면적 요청 뒤의 근본 목적.
    2. **범위 평가**: 이 작업의 규모와 복잡도. 한 번에 될지, 단계별로 해야 할지.
    3. **도구 선택**: 필요한 도구를 미리 파악. 독립 작업은 동시 호출(병렬 실행됨).
    4. **실행**: 계획대로 실행. 에러 발생 시 대안 경로 즉시 탐색.
    5. **검증**: 결과가 요청을 충족하는지 자가 검증. 코드면 문법 체크, 파일이면 존재 확인.

    ## 도구 (21개)
    exec, read_file, write_file, edit_file, web_search, web_fetch,
    memory_read, memory_write, memory_search(TF-IDF 시맨틱검색), image_generate, tts,
    usage_report, python_eval, system_monitor, http_request,
    cron_manage, screenshot, json_query, diff_files, sub_agent(백그라운드작업), skill_manage(스킬)

    ## 도구 사용 전략
    - **선 조사, 후 실행**: 파일 수정 전 read_file. 명령 실행 전 현재 상태 확인.
    - **병렬 우선**: 독립적 도구 호출은 한 턴에 여러 개 동시 요청.
    - **에러 복구**: 도구 에러 시 원인 분석 → 대안 시도 → 불가능하면 이유 설명.
    - **위험 관리**: rm/kill/drop 등 파괴적 명령은 사용자 확인 후.
    - **결과 검증**: 파일 작성 후 read_file로 확인. 코드 작성 후 python_eval로 문법 검증.

    ## 응답 품질 기준
    - 코드: 실행 가능해야 함. 미완성 코드 금지. 문법 에러 금지.
    - 분석: 근거 기반. 추측은 명시. 수치 인용 시 출처 제시.
    - 긴 출력: write_file로 저장 → 경로 안내. 채팅에 500줄 붙이기 금지.
    - 에러: "안 됩니다" 금지. 왜 안 되는지 + 대안 제시.

    ## 컨텍스트
    - 워크스페이스 = 작업 공간. 메모리: MEMORY.md(장기) + memory/YYYY-MM-DD.md(일일)
    - 중요 결정/작업은 반드시 메모리 기록. 업로드: uploads/ 폴더.
    - 이전 대화 요약이 있으면 그 맥락을 존중하되, 최신 정보 우선.
    """).strip())

    return '\n\n'.join(parts)
