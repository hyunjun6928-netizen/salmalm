import subprocess
import sys
import os
import re
import time
import json
import traceback
import uuid
import urllib.request
import base64
import mimetypes
try:
    import resource as _resource_mod
except ImportError:
    _resource_mod = None  # Windows
import difflib
import threading
from datetime import datetime

from pathlib import Path
from typing import Dict

from .constants import (EXEC_ALLOWLIST, EXEC_BLOCKLIST, EXEC_BLOCKLIST_PATTERNS, PROTECTED_FILES,
                        WORKSPACE_DIR, VERSION, KST, MEMORY_FILE, MEMORY_DIR, AUDIT_DB)
from .crypto import vault, log
from .core import (audit_log, get_usage_report, _tfidf, SubAgent, SkillLoader,
                   _sessions, get_session, _tg_bot)
from .llm import _http_post, _http_get

# Global telegram bot reference (set during startup)
telegram_bot = None

# clipboard race condition 방지용 lock
_clipboard_lock = threading.Lock()

TOOL_DEFINITIONS = [
    {
        'name': 'exec',
        'description': '셸 명령어를 실행합니다. 위험한 명령은 차단됩니다.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'command': {'type': 'string', 'description': '실행할 셸 명령어'},
                'timeout': {'type': 'integer', 'description': '타임아웃(초)', 'default': 30}
            },
            'required': ['command']
        }
    },
    {
        'name': 'read_file',
        'description': '파일 내용을 읽습니다.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': '파일 경로'},
                'offset': {'type': 'integer', 'description': '시작 줄 번호 (1-based)'},
                'limit': {'type': 'integer', 'description': '읽을 줄 수'}
            },
            'required': ['path']
        }
    },
    {
        'name': 'write_file',
        'description': '파일에 내용을 씁니다. 없으면 생성합니다.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': '파일 경로'},
                'content': {'type': 'string', 'description': '파일 내용'}
            },
            'required': ['path', 'content']
        }
    },
    {
        'name': 'edit_file',
        'description': '파일에서 특정 텍스트를 찾아 교체합니다.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': '파일 경로'},
                'old_text': {'type': 'string', 'description': '찾을 텍스트'},
                'new_text': {'type': 'string', 'description': '바꿀 텍스트'}
            },
            'required': ['path', 'old_text', 'new_text']
        }
    },
    {
        'name': 'web_search',
        'description': '웹 검색을 수행합니다.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'query': {'type': 'string', 'description': '검색 쿼리'},
                'count': {'type': 'integer', 'description': '결과 수', 'default': 5}
            },
            'required': ['query']
        }
    },
    {
        'name': 'web_fetch',
        'description': 'URL에서 내용을 가져옵니다.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'url': {'type': 'string', 'description': 'URL'},
                'max_chars': {'type': 'integer', 'description': '최대 글자 수', 'default': 10000}
            },
            'required': ['url']
        }
    },
    {
        'name': 'memory_read',
        'description': 'MEMORY.md 또는 memory/ 파일을 읽습니다.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'file': {'type': 'string', 'description': '파일명 (예: MEMORY.md, 2026-02-18.md)'}
            },
            'required': ['file']
        }
    },
    {
        'name': 'memory_write',
        'description': 'MEMORY.md 또는 memory/ 파일에 씁니다.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'file': {'type': 'string', 'description': '파일명'},
                'content': {'type': 'string', 'description': '내용'}
            },
            'required': ['file', 'content']
        }
    },
    {
        'name': 'usage_report',
        'description': '현재 세션의 토큰 사용량과 비용을 보여줍니다.',
        'input_schema': {'type': 'object', 'properties': {}}
    },
    {
        'name': 'memory_search',
        'description': 'MEMORY.md와 memory/*.md 파일에서 키워드로 관련 내용을 검색합니다.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'query': {'type': 'string', 'description': '검색할 키워드 또는 문장'},
                'max_results': {'type': 'integer', 'description': '최대 결과 수', 'default': 5}
            },
            'required': ['query']
        }
    },
    {
        'name': 'image_generate',
        'description': '이미지를 생성합니다. xAI Aurora 또는 OpenAI DALL-E를 사용합니다.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'prompt': {'type': 'string', 'description': '이미지 생성 프롬프트 (영어 권장)'},
                'provider': {'type': 'string', 'description': 'xai 또는 openai', 'default': 'xai'},
                'size': {'type': 'string', 'description': '이미지 크기', 'default': '1024x1024'}
            },
            'required': ['prompt']
        }
    },
    {
        'name': 'tts',
        'description': '텍스트를 음성으로 변환합니다 (OpenAI TTS).',
        'input_schema': {
            'type': 'object',
            'properties': {
                'text': {'type': 'string', 'description': '변환할 텍스트'},
                'voice': {'type': 'string', 'description': 'alloy, echo, fable, onyx, nova, shimmer', 'default': 'nova'}
            },
            'required': ['text']
        }
    },
    {
        'name': 'python_eval',
        'description': 'Python 코드를 실행합니다. 수학 계산, 데이터 처리, 분석에 유용합니다. exec()로 실행 후 _result 변수에 담긴 값을 반환합니다.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'code': {'type': 'string', 'description': '실행할 Python 코드. 결과를 _result 변수에 할당하세요.'},
                'timeout': {'type': 'integer', 'description': '타임아웃(초)', 'default': 15}
            },
            'required': ['code']
        }
    },
    {
        'name': 'system_monitor',
        'description': '시스템 상태를 모니터링합니다 (CPU, 메모리, 디스크, 프로세스).',
        'input_schema': {
            'type': 'object',
            'properties': {
                'detail': {'type': 'string', 'description': 'overview(전체), cpu, memory, disk, processes, network 중 택1', 'default': 'overview'}
            },
            'required': []
        }
    },
    {
        'name': 'http_request',
        'description': 'HTTP 요청을 보냅니다 (GET/POST/PUT/DELETE). API 호출에 유용합니다.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'method': {'type': 'string', 'description': 'GET, POST, PUT, DELETE', 'default': 'GET'},
                'url': {'type': 'string', 'description': '요청 URL'},
                'headers': {'type': 'object', 'description': '요청 헤더 (JSON)'},
                'body': {'type': 'string', 'description': '요청 바디 (POST/PUT용)'},
                'timeout': {'type': 'integer', 'description': '타임아웃(초)', 'default': 15}
            },
            'required': ['url']
        }
    },
    {
        'name': 'screenshot',
        'description': '현재 화면을 스크린샷으로 캡처합니다. 디버깅이나 기록용으로 유용합니다.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'region': {'type': 'string', 'description': 'full(전체화면) 또는 WxH+X+Y (영역 지정)', 'default': 'full'}
            },
            'required': []
        }
    },
    {
        'name': 'json_query',
        'description': 'JSON 데이터를 jq 스타일로 쿼리합니다. API 응답 파싱, 설정 파일 분석에 유용합니다.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'data': {'type': 'string', 'description': 'JSON 문자열 또는 파일 경로'},
                'query': {'type': 'string', 'description': 'jq 필터 표현식 (예: .items[].name)'},
                'from_file': {'type': 'boolean', 'description': 'data가 파일 경로인 경우 true', 'default': False}
            },
            'required': ['data', 'query']
        }
    },
    {
        'name': 'diff_files',
        'description': '두 파일 또는 두 텍스트의 차이를 비교합니다.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'file1': {'type': 'string', 'description': '첫 번째 파일 경로 또는 텍스트'},
                'file2': {'type': 'string', 'description': '두 번째 파일 경로 또는 텍스트'},
                'context_lines': {'type': 'integer', 'description': '컨텍스트 줄 수', 'default': 3}
            },
            'required': ['file1', 'file2']
        }
    },
    {
        'name': 'sub_agent',
        'description': '백그라운드에서 장시간 작업을 실행합니다. 즉시 반환되고 완료 시 텔레그램으로 알림.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'description': 'spawn(생성), list(목록), result(결과)', 'enum': ['spawn', 'list', 'result']},
                'task': {'type': 'string', 'description': '실행할 작업 설명 (spawn용)'},
                'model': {'type': 'string', 'description': '사용할 모델 (optional)'},
                'agent_id': {'type': 'string', 'description': '에이전트 ID (result용)'}
            },
            'required': ['action']
        }
    },
    {
        'name': 'skill_manage',
        'description': '스킬을 조회하고 로드합니다. skills/ 폴더의 SKILL.md 기반 특화 지침.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'description': 'list(목록), load(로드), match(자동매칭)', 'enum': ['list', 'load', 'match']},
                'skill_name': {'type': 'string', 'description': '스킬 디렉토리명 (load용)'},
                'query': {'type': 'string', 'description': '매칭할 쿼리 (match용)'}
            },
            'required': ['action']
        }
    },
    {
        'name': 'clipboard',
        'description': '텍스트 클립보드. 세션 간 빠른 복사/붙여넣기/목록 조회. 최대 50개 슬롯.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'description': 'copy(저장), paste(읽기), list(목록), clear(전체삭제)', 'enum': ['copy', 'paste', 'list', 'clear']},
                'slot': {'type': 'string', 'description': '슬롯 이름 (기본: default)'},
                'content': {'type': 'string', 'description': '저장할 텍스트 (copy용)'}
            },
            'required': ['action']
        }
    },
    {
        'name': 'hash_text',
        'description': '텍스트 해싱(SHA256/MD5/SHA1) 또는 랜덤 비밀번호/UUID/토큰 생성.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'description': 'hash(해싱), password(비밀번호생성), uuid(UUID생성), token(랜덤토큰)', 'enum': ['hash', 'password', 'uuid', 'token']},
                'text': {'type': 'string', 'description': '해싱할 텍스트 (hash용)'},
                'algorithm': {'type': 'string', 'description': 'sha256, md5, sha1, sha512, sha384 (기본: sha256)'},
                'length': {'type': 'integer', 'description': '비밀번호/토큰 길이 (기본: 16)'}
            },
            'required': ['action']
        }
    },
    {
        'name': 'regex_test',
        'description': '정규표현식을 테스트합니다. 패턴 매칭, 치환, 추출을 수행합니다.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'pattern': {'type': 'string', 'description': '정규표현식 패턴'},
                'text': {'type': 'string', 'description': '대상 텍스트'},
                'action': {'type': 'string', 'description': 'match(전체매칭), find(모두찾기), replace(치환), split(분할)', 'enum': ['match', 'find', 'replace', 'split']},
                'replacement': {'type': 'string', 'description': '치환할 텍스트 (replace용)'},
                'flags': {'type': 'string', 'description': '플래그: i(대소문자무시), m(멀티라인), s(dotall)'}
            },
            'required': ['pattern', 'text']
        }
    },
    {
        'name': 'cron_manage',
        'description': '스케줄 작업 관리. 매일/매시간/특정 시간에 LLM 작업을 자동 실행합니다.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'description': 'list(목록), add(추가), remove(삭제), toggle(활성/비활성)', 'enum': ['list', 'add', 'remove', 'toggle']},
                'name': {'type': 'string', 'description': '작업 이름 (add용)'},
                'prompt': {'type': 'string', 'description': 'LLM에 보낼 프롬프트 (add용)'},
                'schedule': {'type': 'object', 'description': '스케줄: {"kind":"cron","expr":"0 6 * * *"} 또는 {"kind":"every","seconds":3600} 또는 {"kind":"at","time":"ISO8601"}'},
                'model': {'type': 'string', 'description': '사용할 모델 (선택, 기본: 현재 설정)'},
                'job_id': {'type': 'string', 'description': '작업 ID (remove/toggle용)'}
            },
            'required': ['action']
        }
    },
    {
        'name': 'plugin_manage',
        'description': '플러그인 관리. plugins/ 폴더의 .py 파일을 자동 로드하여 도구를 확장합니다.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'description': 'list(목록), reload(재로드)', 'enum': ['list', 'reload']}
            },
            'required': ['action']
        }
    },
    {
        'name': 'mcp_manage',
        'description': 'MCP (Model Context Protocol) 서버 관리. 외부 MCP 서버에 연결하여 도구를 가져옵니다.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'description': 'list(목록), add(추가), remove(삭제), tools(전체 도구 목록)', 'enum': ['list', 'add', 'remove', 'tools']},
                'name': {'type': 'string', 'description': '서버 이름 (add/remove용)'},
                'command': {'type': 'string', 'description': '서버 실행 명령어 (add용, 공백으로 분리)'},
                'env': {'type': 'object', 'description': '환경 변수 (add용, 선택)'},
            },
            'required': ['action']
        }
    },
    {
        'name': 'rag_search',
        'description': '로컬 RAG (BM25) 검색. MEMORY.md, memory/, uploads/ 등에서 관련 정보를 찾습니다.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'query': {'type': 'string', 'description': '검색 쿼리'},
                'max_results': {'type': 'integer', 'description': '최대 결과 수 (기본 5)', 'default': 5},
            },
            'required': ['query']
        }
    },
    {
        'name': 'browser',
        'description': '브라우저 자동화. Chrome CDP로 페이지 탐색, 스크린샷, JS 실행, 텍스트 추출 등.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'description': 'navigate/screenshot/text/html/evaluate/click/type/tabs/pdf/status', 'enum': ['navigate', 'screenshot', 'text', 'html', 'evaluate', 'click', 'type', 'tabs', 'pdf', 'status', 'connect', 'console']},
                'url': {'type': 'string', 'description': 'URL (navigate용)'},
                'selector': {'type': 'string', 'description': 'CSS selector (click/type용)'},
                'expression': {'type': 'string', 'description': 'JavaScript 코드 (evaluate용)'},
                'text': {'type': 'string', 'description': '입력 텍스트 (type용)'},
            },
            'required': ['action']
        }
    },
    {
        'name': 'node_manage',
        'description': '원격 노드 관리. SSH/HTTP로 원격 서버 명령 실행, 상태 확인, 파일 전송.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'description': 'list/add/remove/run/status/upload/wake', 'enum': ['list', 'add', 'remove', 'run', 'status', 'upload', 'wake']},
                'name': {'type': 'string', 'description': '노드 이름'},
                'command': {'type': 'string', 'description': '실행할 명령어 (run용)'},
                'host': {'type': 'string', 'description': '호스트 주소 (add용)'},
                'user': {'type': 'string', 'description': 'SSH 사용자 (기본: root)'},
                'port': {'type': 'integer', 'description': 'SSH 포트 (기본: 22)'},
                'key': {'type': 'string', 'description': 'SSH 키 경로'},
                'type': {'type': 'string', 'description': '노드 타입: ssh/http'},
                'url': {'type': 'string', 'description': 'HTTP 에이전트 URL (add type=http용)'},
                'mac': {'type': 'string', 'description': 'MAC 주소 (wake용)'},
            },
            'required': ['action']
        }
    },
    {
        'name': 'health_check',
        'description': '시스템 건강 상태 확인. 모든 컴포넌트 상태, 메모리, 디스크, 에러율 등 종합 진단.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'description': 'check(종합진단)/selftest(모듈테스트)/recover(자동복구)', 'enum': ['check', 'selftest', 'recover'], 'default': 'check'},
            },
        }
    },
]


def _is_safe_command(cmd: str) -> tuple[bool, str]:
    """Check if command is safe to execute (allowlist + blocklist double defense)."""
    first_word = cmd.strip().split()[0].split('/')[-1] if cmd.strip() else ''
    if not first_word:
        return False, 'Empty command'
    # Blocklist takes priority (even if somehow in allowlist)
    if first_word in EXEC_BLOCKLIST:
        return False, f'Blocked command: {first_word}'
    for pattern in EXEC_BLOCKLIST_PATTERNS:
        if re.search(pattern, cmd):
            return False, f'Blocked pattern: {pattern}'
    # Allowlist check — unknown commands blocked
    if first_word not in EXEC_ALLOWLIST:
        return False, f'Command not in allowlist: {first_word} (not in EXEC_ALLOWLIST)'
    return True, ''


def _resolve_path(path: str, writing: bool = False) -> Path:
    """Resolve path, preventing traversal outside allowed directories.

    Read: workspace + home directory
    Write: workspace only (stricter)
    """
    p = Path(path)
    if not p.is_absolute():
        p = WORKSPACE_DIR / p
    p = p.resolve()

    if writing:
        # Write operations: workspace only
        try:
            p.relative_to(WORKSPACE_DIR.resolve())
        except ValueError:
            raise PermissionError(f'쓰기 불가 (workspace 외부): {p}')
    else:
        # Read operations: workspace + home
        allowed = [WORKSPACE_DIR.resolve(), Path.home().resolve()]
        if not any(_is_subpath(p, a) for a in allowed):
            raise PermissionError(f'접근 불가: {p}')

    if writing and p.name in PROTECTED_FILES:
        raise PermissionError(f'보호된 파일: {p.name}')
    return p


def _is_subpath(path: Path, parent: Path) -> bool:
    """Check if path is under parent (safe, no startswith tricks)."""
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def execute_tool(name: str, args: dict) -> str:
    """Execute a tool and return result string."""
    audit_log('tool_exec', f'{name}: {json.dumps(args, ensure_ascii=False)[:200]}')
    try:
        if name == 'exec':
            cmd = args.get('command', '')
            safe, reason = _is_safe_command(cmd)
            if not safe:
                return f'❌ {reason}'
            timeout = min(args.get('timeout', 30), 120)
            try:
                # Use shell=False by default (safer), shell=True only for pipes/redirects
                import shlex
                needs_shell = any(c in cmd for c in ['|', '>', '<', '&&', '||', ';', '`', '$(' ])
                if needs_shell:
                    run_args = {'args': cmd, 'shell': True}
                else:
                    try:
                        run_args = {'args': shlex.split(cmd), 'shell': False}
                    except ValueError:
                        run_args = {'args': cmd, 'shell': True}
                result = subprocess.run(
                    **run_args, capture_output=True, text=True,
                    timeout=timeout, cwd=str(WORKSPACE_DIR)
                )
                output = result.stdout[-5000:] if result.stdout else ''
                if result.stderr:
                    output += f'\n[stderr]: {result.stderr[-2000:]}'
                if result.returncode != 0:
                    output += f'\n[exit code]: {result.returncode}'
                return output or '(no output)'
            except subprocess.TimeoutExpired:
                return f'❌ Timeout ({timeout}s)'

        elif name == 'read_file':
            p = _resolve_path(args['path'])
            if not p.exists():
                return f'❌ File not found: {p}'
            text = p.read_text(encoding='utf-8', errors='replace')
            lines = text.splitlines()
            offset = args.get('offset', 1) - 1
            limit = args.get('limit', len(lines))
            selected = lines[offset:offset + limit]
            return '\n'.join(selected)[:50000]

        elif name == 'write_file':
            p = _resolve_path(args['path'], writing=True)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(args['content'], encoding='utf-8')
            return f'✅ {p} ({len(args["content"])} chars)'

        elif name == 'edit_file':
            p = _resolve_path(args['path'], writing=True)
            text = p.read_text(encoding='utf-8')
            if args['old_text'] not in text:
                return f'❌ Text not found'
            text = text.replace(args['old_text'], args['new_text'], 1)
            p.write_text(text, encoding='utf-8')
            return f'✅ File edited: {p}'

        elif name == 'web_search':
            api_key = vault.get('brave_api_key')
            if not api_key:
                return '❌ Brave Search API key not found'
            query = urllib.parse.quote(args['query'])
            count = min(args.get('count', 5), 10)
            resp = _http_get(
                f'https://api.search.brave.com/res/v1/web/search?q={query}&count={count}',
                {'Accept': 'application/json', 'X-Subscription-Token': api_key}
            )
            results = []
            for r in resp.get('web', {}).get('results', [])[:count]:
                results.append(f"**{r['title']}**\n{r['url']}\n{r.get('description', '')}\n")
            return '\n'.join(results) or 'No results'

        elif name == 'web_fetch':
            url = args['url']
            max_chars = args.get('max_chars', 10000)
            # SSRF protection: block internal/private IPs
            from urllib.parse import urlparse
            _host = urlparse(url).hostname or ''
            _blocked = ('localhost', '127.', '10.', '192.168.', '172.16.',
                        '172.17.', '172.18.', '172.19.', '172.2', '172.30.', '172.31.',
                        '169.254.', '0.0.0.0', '::1', 'metadata.google', '169.254.169.254')
            if any(_host.startswith(b) or _host == b for b in _blocked):
                return f'❌ Internal network access blocked: {_host}'
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (SalmAlm/0.1)'
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode('utf-8', errors='replace')
            # HTML to text using html.parser (robust, no regex fragility)
            from html.parser import HTMLParser

            class _TextExtractor(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self._parts: list = []
                    self._skip = False
                    self._skip_tags = {'script', 'style', 'noscript', 'svg'}

                def handle_starttag(self, tag, attrs):
                    if tag.lower() in self._skip_tags:
                        self._skip = True
                    elif tag.lower() in ('br', 'p', 'div', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'tr'):
                        self._parts.append('\n')

                def handle_endtag(self, tag):
                    if tag.lower() in self._skip_tags:
                        self._skip = False

                def handle_data(self, data):
                    if not self._skip:
                        self._parts.append(data)

                def get_text(self) -> str:
                    return re.sub(r'\n{3,}', '\n\n', ''.join(self._parts)).strip()

            extractor = _TextExtractor()
            extractor.feed(raw)
            return extractor.get_text()[:max_chars]

        elif name == 'memory_read':
            fname = args['file']
            if fname == 'MEMORY.md':
                p = MEMORY_FILE
            else:
                p = MEMORY_DIR / fname
            if not p.exists():
                return f'❌ File not found: {fname}'
            return p.read_text(encoding='utf-8')[:30000]

        elif name == 'memory_write':
            fname = args['file']
            if fname == 'MEMORY.md':
                p = MEMORY_FILE
            else:
                p = MEMORY_DIR / fname
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(args['content'], encoding='utf-8')
            return f'✅ {fname} saved'

        elif name == 'usage_report':
            report = get_usage_report()
            lines = [f"📊 삶앎 사용량 리포트",
                     f"⏱️ 가동: {report['elapsed_hours']}시간",
                     f"📥 입력: {report['total_input']:,} 토큰",
                     f"📤 출력: {report['total_output']:,} 토큰",
                     f"💰 총 비용: ${report['total_cost']:.4f}", ""]
            for m, d in report.get('by_model', {}).items():
                lines.append(f"  {m}: {d['calls']}회, ${d['cost']:.4f}")
            return '\n'.join(lines)

        elif name == 'memory_search':
            query = args['query']
            max_results = args.get('max_results', 5)
            # Use TF-IDF semantic search
            results = _tfidf.search(query, max_results)
            if not results:
                return f'No results for: "{query}"'
            out = []
            for score, label, lineno, snippet in results:
                out.append(f'📍 {label}#{lineno} (similarity:{score:.3f})\n{snippet}\n')
            return '\n'.join(out)

        elif name == 'sub_agent':
            action = args.get('action', 'list')
            if action == 'spawn':
                task = args.get('task', '')
                if not task:
                    return '❌ Task is required'
                model = args.get('model')
                agent_id = SubAgent.spawn(task, model=model)
                return f'🤖 Sub-agent spawned: [{agent_id}]\nTask: {task[:100]}\nWill notify on completion.'
            elif action == 'list':
                agents = SubAgent.list_agents()
                if not agents:
                    return '📋 No running sub-agents.'
                lines = []
                for a in agents:
                    icon = '🟢' if a['status'] == 'running' else '✅' if a['status'] == 'completed' else '❌'
                    lines.append(f'{icon} [{a["id"]}] {a["task"]} — {a["status"]}')
                return '\n'.join(lines)
            elif action == 'result':
                agent_id = args.get('agent_id', '')
                info = SubAgent.get_result(agent_id)
                if 'error' in info:
                    return f'❌ {info["error"]}'
                status = info['status']
                if status == 'running':
                    return f'⏳ [{agent_id}] Still running.\nStarted: {info["started"]}'
                result = info.get('result', '(결과 없음)')
                return f'{"✅" if status == "completed" else "❌"} [{agent_id}] {status}\nStarted: {info["started"]}\nFinished: {info["completed"]}\n\n{result[:3000]}'
            return f'❌ Unknown action: {action}'

        elif name == 'skill_manage':
            action = args.get('action', 'list')
            if action == 'list':
                skills = SkillLoader.scan()
                if not skills:
                    return '📚 No skills registered.\nCreate a skill directory in skills/ and add SKILL.md.'
                lines = []
                for s in skills:
                    lines.append(f'📚 **{s["name"]}** ({s["dir_name"]})\n   {s["description"]}\n   크기: {s["size"]}자')
                return '\n'.join(lines)
            elif action == 'load':
                skill_name = args.get('skill_name', '')
                content = SkillLoader.load(skill_name)
                if not content:
                    return f'❌ Skill "{skill_name}" not found'
                return f'📚 Skill loaded: {skill_name}\n\n{content[:5000]}'
            elif action == 'match':
                query = args.get('query', '')
                content = SkillLoader.match(query)
                if not content:
                    return 'No matching skill found.'
                return f'📚 Auto-matched skill:\n\n{content[:5000]}'
            return f'❌ Unknown action: {action}'

        elif name == 'image_generate':
            prompt = args['prompt']
            provider = args.get('provider', 'xai')
            size = args.get('size', '1024x1024')
            save_dir = WORKSPACE_DIR / 'uploads'
            save_dir.mkdir(exist_ok=True)
            fname = f"gen_{int(time.time())}.png"
            save_path = save_dir / fname

            if provider == 'xai':
                api_key = vault.get('xai_api_key')
                if not api_key:
                    return '❌ xAI API key not found'
                resp = _http_post(
                    'https://api.x.ai/v1/images/generations',
                    {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                    {'model': 'aurora', 'prompt': prompt, 'n': 1, 'size': size,
                     'response_format': 'b64_json'}
                )
                import base64 as b64mod
                img_data = b64mod.b64decode(resp['data'][0]['b64_json'])
                save_path.write_bytes(img_data)
            else:
                api_key = vault.get('openai_api_key')
                if not api_key:
                    return '❌ OpenAI API key not found'
                resp = _http_post(
                    'https://api.openai.com/v1/images/generations',
                    {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                    {'model': 'gpt-image-1', 'prompt': prompt, 'n': 1, 'size': size,
                     'output_format': 'b64_json'}
                )
                import base64 as b64mod
                img_data = b64mod.b64decode(resp['data'][0]['b64_json'])
                save_path.write_bytes(img_data)

            size_kb = len(img_data) / 1024
            log.info(f"🎨 Image generated: {fname} ({size_kb:.1f}KB)")
            return f'✅ 이미지 생성 Finished: uploads/{fname} ({size_kb:.1f}KB)\nPrompt: {prompt}'

        elif name == 'tts':
            text = args['text']
            voice = args.get('voice', 'nova')
            api_key = vault.get('openai_api_key')
            if not api_key:
                return '❌ OpenAI API key not found'
            save_dir = WORKSPACE_DIR / 'uploads'
            save_dir.mkdir(exist_ok=True)
            fname = f"tts_{int(time.time())}.mp3"
            save_path = save_dir / fname
            data = json.dumps({'model': 'tts-1', 'input': text, 'voice': voice}).encode()
            req = urllib.request.Request(
                'https://api.openai.com/v1/audio/speech',
                data=data,
                headers={'Authorization': f'Bearer {api_key}',
                         'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                audio = resp.read()
            save_path.write_bytes(audio)
            size_kb = len(audio) / 1024
            log.info(f"🔊 TTS generated: {fname} ({size_kb:.1f}KB)")
            return f'✅ 음성 생성 Finished: uploads/{fname} ({size_kb:.1f}KB)\nText: {text[:100]}'

        elif name == 'python_eval':
            code = args.get('code', '')
            timeout_sec = min(args.get('timeout', 15), 30)
            # Block dangerous patterns in code
            _EVAL_BLOCKLIST = [
                'import os', 'import sys', 'import subprocess', 'import shutil',
                '__import__', 'eval(', 'exec(', 'compile(', 'open(',
                'os.system', 'os.popen', 'os.exec', 'os.spawn', 'os.remove', 'os.unlink',
                'shutil.rmtree', 'pathlib', '.vault', 'audit.db', 'auth.db',
                'import socket', 'import http', 'import urllib', 'import requests',
            ]
            code_lower = code.lower().replace(' ', '')
            for blocked in _EVAL_BLOCKLIST:
                if blocked.lower().replace(' ', '') in code_lower:
                    return f'❌ Security blocked: `{blocked}` not allowed. python_eval is for computation only.'
            # Execute in isolated subprocess (no network, limited imports)
            wrapper = f'''
import json, math, re, statistics, collections, itertools, functools, datetime, hashlib, base64, random, string, textwrap, csv, io
_result = None
try:
    exec({repr(code)})
except Exception as e:
    _result = f"Error: {{type(e).__name__}}: {{e}}"
if _result is not None:
    print(json.dumps({{"result": str(_result)[:10000]}}))
else:
    print(json.dumps({{"result": "(no _result set)"}}))
'''
            # Resource limits (Linux only — graceful no-op on Windows/macOS)
            def _set_limits():
                try:
                    import resource
                    resource.setrlimit(resource.RLIMIT_CPU, (timeout_sec, timeout_sec))
                    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))  # 512MB
                    resource.setrlimit(resource.RLIMIT_NOFILE, (50, 50))  # fd limit
                    resource.setrlimit(resource.RLIMIT_NPROC, (10, 10))  # fork bomb prevention
                    resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))  # 10MB file write limit
                except Exception:
                    pass  # Windows or unsupported

            try:
                result = subprocess.run(
                    [sys.executable, '-c', wrapper],
                    capture_output=True, text=True,
                    timeout=timeout_sec, cwd=str(WORKSPACE_DIR),
                    preexec_fn=_set_limits
                )
                if result.returncode == 0 and result.stdout.strip():
                    try:
                        data = json.loads(result.stdout.strip())
                        output = data.get('result', result.stdout)
                    except json.JSONDecodeError:
                        output = result.stdout[-5000:]
                else:
                    output = result.stdout[-3000:] if result.stdout else ''
                if result.stderr:
                    output += f'\n[stderr]: {result.stderr[-2000:]}'
                return output or '(no output)'
            except subprocess.TimeoutExpired:
                return f'❌ Python execution timeout ({timeout_sec}s)'

        elif name == 'system_monitor':
            detail = args.get('detail', 'overview')
            lines = []
            try:
                if detail in ('overview', 'cpu'):
                    load = os.getloadavg()
                    cpu_count = os.cpu_count() or 1
                    lines.append(f'🖥️ CPU: {cpu_count}코어, 부하: {load[0]:.2f} / {load[1]:.2f} / {load[2]:.2f} (1/5/15분)')
                if detail in ('overview', 'memory'):
                    mem = subprocess.run(['free', '-h'], capture_output=True, text=True, timeout=5)
                    if mem.stdout:
                        for l in mem.stdout.strip().split('\n'):
                            lines.append(f'💾 {l}')
                if detail in ('overview', 'disk'):
                    disk = subprocess.run(['df', '-h', '/'], capture_output=True, text=True, timeout=5)
                    if disk.stdout:
                        for l in disk.stdout.strip().split('\n'):
                            lines.append(f'💿 {l}')
                if detail in ('overview', 'network'):
                    # Quick network check
                    net = subprocess.run(['ss', '-s'], capture_output=True, text=True, timeout=5)
                    if net.stdout:
                        lines.append(f'🌐 네트워크:')
                        for l in net.stdout.strip().split('\n')[:5]:
                            lines.append(f'   {l}')
                if detail == 'processes':
                    ps = subprocess.run(['ps', 'aux', '--sort=-rss'], capture_output=True, text=True, timeout=5)
                    if ps.stdout:
                        for l in ps.stdout.strip().split('\n')[:20]:
                            lines.append(l)
                if detail in ('overview',):
                    uptime = subprocess.run(['uptime', '-p'], capture_output=True, text=True, timeout=5)
                    if uptime.stdout:
                        lines.append(f'⏱️ 가동시간: {uptime.stdout.strip()}')
                    # Python process info
                    mem_mb = 0
                    if _resource_mod:
                        mem_mb = _resource_mod.getrusage(_resource_mod.RUSAGE_SELF).ru_maxrss / 1024
                    lines.append(f'🐍 삶앎 메모리: {mem_mb:.1f}MB')
                    lines.append(f'📂 세션 수: {len(_sessions)}')
            except Exception as e:
                lines.append(f'❌ 모니터링 오류: {e}')
            return '\n'.join(lines) or '정보 없음'

        elif name == 'http_request':
            method = args.get('method', 'GET').upper()
            url = args.get('url', '')
            headers = args.get('headers', {})
            body_str = args.get('body', '')
            timeout_sec = min(args.get('timeout', 15), 60)
            if not url:
                return '❌ URL이 필요합니다'
            # SSRF protection: block internal/private IPs
            from urllib.parse import urlparse
            _host = urlparse(url).hostname or ''
            _blocked = ('localhost', '127.', '10.', '192.168.', '172.16.',
                        '172.17.', '172.18.', '172.19.', '172.2', '172.30.', '172.31.',
                        '169.254.', '0.0.0.0', '::1', 'metadata.google', '169.254.169.254')
            if any(_host.startswith(b) or _host == b for b in _blocked):
                return f'❌ Internal network access blocked: {_host}'
            headers.setdefault('User-Agent', f'SalmAlm/{VERSION}')
            data = body_str.encode('utf-8') if body_str else None
            try:
                req = urllib.request.Request(url, data=data, headers=headers, method=method)
                with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                    status = resp.status
                    resp_headers = dict(resp.headers)
                    raw = resp.read()
                # Try JSON
                try:
                    body_json = json.loads(raw)
                    body_out = json.dumps(body_json, ensure_ascii=False, indent=2)[:8000]
                except (json.JSONDecodeError, UnicodeDecodeError):
                    body_out = raw.decode('utf-8', errors='replace')[:8000]
                header_str = '\n'.join(f'  {k}: {v}' for k, v in list(resp_headers.items())[:10])
                return f'HTTP {status}\n헤더:\n{header_str}\n\n바디:\n{body_out}'
            except urllib.error.HTTPError as e:
                body = e.read().decode('utf-8', errors='replace')[:3000]
                return f'HTTP {e.code} {e.reason}\n{body}'
            except Exception as e:
                return f'❌ 요청 오류: {e}'

        elif name == 'screenshot':
            region = args.get('region', 'full')
            fname = f'screenshot_{int(time.time())}.png'
            fpath = WORKSPACE_DIR / 'uploads' / fname
            fpath.parent.mkdir(exist_ok=True)
            try:
                cmd = ['import', '-window', 'root', str(fpath)] if region == 'full' else ['import', '-crop', region, '-window', 'root', str(fpath)]
                # Try scrot first (more common)
                try:
                    if region == 'full':
                        subprocess.run(['scrot', str(fpath)], timeout=10, check=True)
                    else:
                        subprocess.run(['scrot', '-a', region, str(fpath)], timeout=10, check=True)
                except FileNotFoundError:
                    subprocess.run(cmd, timeout=10, check=True)
                size_kb = fpath.stat().st_size / 1024
                return f'✅ 스크린샷 저장: uploads/{fname} ({size_kb:.1f}KB)'
            except Exception as e:
                return f'❌ 스크린샷 실패: {e}'

        elif name == 'json_query':
            data_str = args.get('data', '')
            query = args.get('query', '.')
            from_file = args.get('from_file', False)
            if from_file:
                fpath = _resolve_path(data_str)
                data_str = fpath.read_text(encoding='utf-8', errors='replace')
            try:
                result = subprocess.run(
                    ['jq', query],
                    input=data_str, capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    return result.stdout[:8000] or '(empty)'
                return f'❌ jq 오류: {result.stderr[:500]}'
            except FileNotFoundError:
                # jq not installed, try Python fallback
                data = json.loads(data_str)
                # Simple dot notation query
                parts = query.strip('.').split('.')
                current = data
                for p in parts:
                    if not p:
                        continue
                    if p.endswith('[]'):
                        p = p[:-2]
                        if p:
                            current = current[p]
                        if isinstance(current, list):
                            current = current
                    elif p.isdigit():
                        current = current[int(p)]
                    else:
                        current = current[p]
                return json.dumps(current, ensure_ascii=False, indent=2)[:8000]

        elif name == 'diff_files':
            f1 = args.get('file1', '')
            f2 = args.get('file2', '')
            ctx = args.get('context_lines', 3)
            import difflib
            # If paths exist, read them
            try:
                p1 = _resolve_path(f1)
                text1 = p1.read_text(encoding='utf-8', errors='replace').splitlines()
                label1 = f1
            except Exception:
                text1 = f1.splitlines()
                label1 = 'text1'
            try:
                p2 = _resolve_path(f2)
                text2 = p2.read_text(encoding='utf-8', errors='replace').splitlines()
                label2 = f2
            except Exception:
                text2 = f2.splitlines()
                label2 = 'text2'
            diff = list(difflib.unified_diff(text1, text2, fromfile=label1, tofile=label2, n=ctx))
            if not diff:
                return '✅ 두 파일/텍스트가 동일합니다.'
            return '\n'.join(diff[:300])

        elif name == 'clipboard':
            action = args.get('action', 'list')
            slot = args.get('slot', 'default')
            
            # 슬롯 이름 길이 제한 (100자)
            if len(slot) > 100:
                return '❌ 슬롯 이름은 100자 이내로 제한됩니다'
            
            clip_file = WORKSPACE_DIR / '.clipboard.json'
            
            with _clipboard_lock:  # race condition 방지
                try:
                    clips = json.loads(clip_file.read_text()) if clip_file.exists() else {}
                except Exception:
                    clips = {}

                if action == 'copy':
                    content = args.get('content', '')
                    if not content:
                        return '❌ content가 필요합니다'
                    if len(clips) >= 50 and slot not in clips:
                        return '❌ 클립보드 슬롯 최대 50개 초과'
                    clips[slot] = {
                        'content': content[:50000],
                        'created': datetime.now(KST).isoformat(),
                        'size': len(content[:50000])  # 저장된 실제 크기
                    }
                    clip_file.write_text(json.dumps(clips, ensure_ascii=False, indent=2))
                    return f'📋 [{slot}] saved ({len(content[:50000])}자)'

                elif action == 'paste':
                    if slot not in clips:
                        return f'❌ 슬롯 [{slot}] 없음. 저장된 슬롯: {", ".join(clips.keys()) or "없음"}'
                    return clips[slot]['content']

                elif action == 'list':
                    if not clips:
                        return '📋 클립보드가 비어있습니다.'
                    lines = ['📋 클립보드 목록:']
                    for slot_name, data in clips.items():
                        preview = data['content'][:60].replace('\n', ' ')
                        if len(data['content']) > 60:
                            preview += "..."
                        lines.append(f'  [{slot_name}] {data["size"]}자 — "{preview}"')
                    return '\n'.join(lines)

                elif action == 'clear':
                    clip_file.write_text('{}')
                    return '🗑️ 클립보드 전체 삭제 완료'

                return f'❌ Unknown action: {action}'

        elif name == 'hash_text':
            import hashlib, secrets, string
            action = args.get('action', 'hash')

            if action == 'hash':
                text = args.get('text', '')
                if not text:
                    return '❌ text가 필요합니다'
                algo = args.get('algorithm', 'sha256')
                algos = {'sha256': hashlib.sha256, 'md5': hashlib.md5, 'sha1': hashlib.sha1,
                         'sha512': hashlib.sha512, 'sha384': hashlib.sha384}
                if algo not in algos:
                    return f'❌ 지원 알고리즘: {", ".join(algos.keys())}'
                h = algos[algo](text.encode('utf-8')).hexdigest()
                return f'🔐 {algo.upper()}: {h}'  # 민감정보 노출 방지

            elif action == 'password':
                length = max(8, min(args.get('length', 16), 128))  # 최소 8자 강제
                charset = string.ascii_letters + string.digits + '!@#$%^&*'
                pw = ''.join(secrets.choice(charset) for _ in range(length))
                return f'🔑 비밀번호 ({length}자): {pw}'

            elif action == 'uuid':
                import uuid as _uuid_mod
                return f'🆔 UUID: {_uuid_mod.uuid4()}'

            elif action == 'token':
                length = min(args.get('length', 32), 256)
                token = secrets.token_hex((length + 1) // 2)[:length]  # 홀수 길이 정확 처리
                return f'🎫 토큰 ({len(token)}자): {token}'

            return f'❌ Unknown action: {action}'

        elif name == 'regex_test':
            pattern = args.get('pattern', '')
            text = args.get('text', '')
            action = args.get('action', 'find')
            flags_str = args.get('flags', '')

            # Parse flags
            flags = 0
            if 'i' in flags_str:
                flags |= re.IGNORECASE
            if 'm' in flags_str:
                flags |= re.MULTILINE
            if 's' in flags_str:
                flags |= re.DOTALL

            try:
                compiled = re.compile(pattern, flags)
            except re.error as e:
                return f'❌ 정규표현식 오류: {e}'

            # ReDoS 방어 - subprocess로 격리 (cross-platform)
            def _run_regex():
                if action == 'match':
                    m = compiled.fullmatch(text)
                    if m:
                        groups = m.groups()
                        gdict = m.groupdict()
                        result = f'✅ 전체 매칭 성공: "{m.group()}"'
                        if groups:
                            result += f'\n그룹: {groups}'
                        if gdict:
                            result += f'\n명명 그룹: {gdict}'
                        return result
                    return '❌ 매칭 실패'

                elif action == 'find':
                    matches = compiled.findall(text)
                    if not matches:
                        return '❌ 매칭 결과 없음'
                    lines = [f'🔍 {len(matches)}개 발견:']
                    for i, m in enumerate(matches[:50], 1):
                        lines.append(f'  {i}. {m}')
                    if len(matches) > 50:
                        lines.append(f'  ... 외 {len(matches)-50}개')
                    return '\n'.join(lines)

                elif action == 'replace':
                    replacement = args.get('replacement', '')
                    result = compiled.sub(replacement, text)
                    return f'🔄 치환 결과:\n{result[:5000]}'

                elif action == 'split':
                    parts = compiled.split(text)
                    lines = [f'✂️ {len(parts)}개로 분할:']
                    for i, p in enumerate(parts[:50], 1):
                        preview = p[:100]
                        if len(p) > 100:
                            preview += "..."
                        lines.append(f'  {i}. "{preview}"')
                    return '\n'.join(lines)

                return f'❌ Unknown action: {action}'

            # Run with timeout using threading
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                try:
                    future = pool.submit(_run_regex)
                    return future.result(timeout=5)
                except concurrent.futures.TimeoutError:
                    return '❌ 정규식 실행 시간 초과 (5초)'

        elif name == 'cron_manage':
            from .core import _llm_cron
            if not _llm_cron:
                return '❌ LLM 크론 매니저가 초기화되지 않았습니다'
            action = args.get('action', 'list')
            if action == 'list':
                jobs = _llm_cron.list_jobs()
                if not jobs:
                    return '⏰ 등록된 스케줄 작업이 없습니다.'
                lines = ['⏰ **스케줄 작업 목록:**']
                for j in jobs:
                    status = '✅' if j['enabled'] else '⏸️'
                    lines.append(f"{status} [{j['id']}] {j['name']} — {j['schedule']} (실행 {j['run_count']}회)")
                return '\n'.join(lines)
            elif action == 'add':
                name_ = args.get('name', '무제')
                prompt = args.get('prompt', '')
                schedule = args.get('schedule', {})
                if not prompt:
                    return '❌ prompt가 필요합니다'
                if not schedule:
                    return '❌ schedule이 필요합니다 (kind: cron/every/at)'
                model = args.get('model')
                job = _llm_cron.add_job(name_, schedule, prompt, model=model)
                return f"⏰ 스케줄 작업 등록: [{job['id']}] {name_}"
            elif action == 'remove':
                job_id = args.get('job_id', '')
                if _llm_cron.remove_job(job_id):
                    return f'⏰ 작업 삭제: {job_id}'
                return f'❌ 작업 없음: {job_id}'
            elif action == 'toggle':
                job_id = args.get('job_id', '')
                for j in _llm_cron.jobs:
                    if j['id'] == job_id:
                        j['enabled'] = not j['enabled']
                        _llm_cron.save_jobs()
                        return f"⏰ {j['name']}: {'활성화' if j['enabled'] else '비활성화'}"
                return f'❌ 작업 없음: {job_id}'
            return f'❌ Unknown action: {action}'

        elif name == 'plugin_manage':
            from .core import PluginLoader
            action = args.get('action', 'list')
            if action == 'list':
                tools = PluginLoader.get_all_tools()
                plugins = PluginLoader._plugins
                if not plugins:
                    return '🔌 로드된 플러그인이 없습니다. plugins/ 폴더에 .py 파일을 추가하세요.'
                lines = ['🔌 **플러그인 목록:**']
                for name_, info in plugins.items():
                    lines.append(f"  📦 {name_} — {len(info['tools'])}개 도구 ({info['path']})")
                    for t in info['tools']:
                        lines.append(f"    🔧 {t['name']}: {t['description'][:60]}")
                return '\n'.join(lines)
            elif action == 'reload':
                count = PluginLoader.reload()
                return f'🔌 플러그인 리로드: {count}개 도구 로드됨'
            return f'❌ Unknown action: {action}'

        elif name == 'browser':
            import asyncio
            from .browser import browser

            def _run_async(coro):
                """Safely run async coroutine from sync context (ThreadPool)."""
                try:
                    loop = asyncio.get_running_loop()
                    # Already in async context — use new thread with new loop
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(1) as pool:
                        return pool.submit(lambda: asyncio.run(coro)).result(timeout=30)
                except RuntimeError:
                    # No running loop — safe to use asyncio.run
                    return asyncio.run(coro)

            action = args.get('action', 'status')
            if action == 'status':
                return json.dumps(browser.get_status(), ensure_ascii=False)
            elif action == 'connect':
                ok = _run_async(browser.connect())
                return '🌐 브라우저 연결 성공' if ok else '❌ 연결 실패. Chrome --remote-debugging-port=9222 확인'
            elif action == 'navigate':
                url = args.get('url', '')
                if not url:
                    return '❌ url이 필요합니다'
                result = _run_async(browser.navigate(url))
                return f'🌐 이동: {url}\n{json.dumps(result, ensure_ascii=False)}'
            elif action == 'text':
                text = _run_async(browser.get_text())
                return text[:5000] if text else '(빈 페이지 또는 미연결)'
            elif action == 'html':
                html = _run_async(browser.get_html())
                return html[:8000] if html else '(빈 페이지 또는 미연결)'
            elif action == 'screenshot':
                b64 = _run_async(browser.screenshot())
                if b64:
                    import base64 as b64mod
                    save_dir = WORKSPACE_DIR / 'uploads'
                    save_dir.mkdir(exist_ok=True)
                    fname = f'screenshot_{int(time.time())}.png'
                    (save_dir / fname).write_bytes(b64mod.b64decode(b64))
                    return f'📸 스크린샷 저장: uploads/{fname} ({len(b64)//1024}KB base64)'
                return '❌ 스크린샷 실패 (미연결?)'
            elif action == 'evaluate':
                expr = args.get('expression', '')
                if not expr:
                    return '❌ expression이 필요합니다'
                result = _run_async(browser.evaluate(expr))
                return json.dumps(result, ensure_ascii=False, default=str)[:5000]
            elif action == 'click':
                sel = args.get('selector', '')
                ok = _run_async(browser.click(sel))
                return f'✅ 클릭: {sel}' if ok else f'❌ 요소 못 찾음: {sel}'
            elif action == 'type':
                sel = args.get('selector', '')
                text = args.get('text', '')
                ok = _run_async(browser.type_text(sel, text))
                return f'✅ 입력: {sel}' if ok else f'❌ 요소 못 찾음: {sel}'
            elif action == 'tabs':
                tabs = _run_async(browser.get_tabs())
                return json.dumps(tabs, ensure_ascii=False)
            elif action == 'console':
                logs = browser.get_console_logs(limit=30)
                return '\n'.join(logs) if logs else '(콘솔 로그 없음)'
            elif action == 'pdf':
                b64 = _run_async(browser.pdf())
                if b64:
                    import base64 as b64mod
                    save_dir = WORKSPACE_DIR / 'uploads'
                    save_dir.mkdir(exist_ok=True)
                    fname = f'page_{int(time.time())}.pdf'
                    (save_dir / fname).write_bytes(b64mod.b64decode(b64))
                    return f'📄 PDF 저장: uploads/{fname}'
                return '❌ PDF 생성 실패'
            return f'❌ Unknown action: {action}'

        elif name == 'node_manage':
            from .nodes import node_manager
            action = args.get('action', 'list')
            if action == 'list':
                nodes = node_manager.list_nodes()
                if not nodes:
                    return '📡 등록된 노드 없음. node_manage(action="add", name="...", host="...") 로 추가'
                lines = ['📡 **노드 목록:**']
                for n in nodes:
                    lines.append(f"  {'🔗' if n['type']=='ssh' else '🌐'} {n['name']} ({n.get('host', n.get('url', '?'))})")
                return '\n'.join(lines)
            elif action == 'add':
                nname = args.get('name', '')
                ntype = args.get('type', 'ssh')
                if not nname:
                    return '❌ name이 필요합니다'
                if ntype == 'ssh':
                    host = args.get('host', '')
                    if not host:
                        return '❌ host가 필요합니다'
                    node_manager.add_ssh_node(nname, host, user=args.get('user', 'root'),
                                              port=args.get('port', 22), key=args.get('key'))
                    return f'📡 SSH 노드 추가: {nname}'
                elif ntype == 'http':
                    url = args.get('url', '')
                    if not url:
                        return '❌ url이 필요합니다'
                    node_manager.add_http_node(nname, url)
                    return f'📡 HTTP 노드 추가: {nname}'
                return f'❌ 알 수 없는 type: {ntype}'
            elif action == 'remove':
                nname = args.get('name', '')
                if node_manager.remove_node(nname):
                    return f'📡 노드 제거: {nname}'
                return f'❌ 노드 없음: {nname}'
            elif action == 'run':
                nname = args.get('name', '')
                cmd = args.get('command', '')
                if not nname or not cmd:
                    return '❌ name과 command가 필요합니다'
                result = node_manager.run_on(nname, cmd)
                return json.dumps(result, ensure_ascii=False)[:5000]
            elif action == 'status':
                nname = args.get('name')
                if nname:
                    node = node_manager.get_node(nname)
                    if not node:
                        return f'❌ 노드 없음: {nname}'
                    return json.dumps(node.status(), ensure_ascii=False)[:3000]
                return json.dumps(node_manager.status_all(), ensure_ascii=False)[:5000]
            elif action == 'wake':
                mac = args.get('mac', '')
                if not mac:
                    return '❌ mac이 필요합니다'
                result = node_manager.wake_on_lan(mac)
                return json.dumps(result, ensure_ascii=False)
            return f'❌ Unknown action: {action}'

        elif name == 'health_check':
            from .stability import health_monitor
            action = args.get('action', 'check')
            if action == 'check':
                report = health_monitor.check_health()
                lines = [f"🏥 **시스템 상태: {report['status'].upper()}**",
                         f"⏱️ 가동시간: {report['uptime_human']}"]
                sys_info = report.get('system', {})
                if sys_info.get('memory_mb'):
                    lines.append(f"💾 메모리: {sys_info['memory_mb']}MB")
                if sys_info.get('disk_free_mb'):
                    lines.append(f"💿 디스크: {sys_info['disk_free_mb']}MB 여유 ({sys_info.get('disk_pct',0)}% 사용)")
                lines.append(f"🧵 스레드: {sys_info.get('threads', '?')}")
                lines.append("")
                for comp, status in report['components'].items():
                    icon = '✅' if status.get('status') == 'ok' else '⚠️' if status.get('status') != 'error' else '❌'
                    lines.append(f"  {icon} {comp}: {status.get('status', '?')}")
                return '\n'.join(lines)
            elif action == 'selftest':
                result = health_monitor.startup_selftest()
                lines = [f"🧪 **셀프테스트: {result['passed']}/{result['total']}**"]
                for mod, status in result['modules'].items():
                    icon = '✅' if status == 'ok' else '❌'
                    lines.append(f"  {icon} {mod}: {status}")
                return '\n'.join(lines)
            elif action == 'recover':
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(1) as pool:
                        recovered = pool.submit(lambda: asyncio.run(health_monitor.auto_recover())).result(timeout=30)
                except RuntimeError:
                    recovered = asyncio.run(health_monitor.auto_recover())
                if recovered:
                    return f'🔧 복구 Finished: {", ".join(recovered)}'
                return '🔧 복구할 컴포넌트 없음 (모두 정상)'
            return f'❌ Unknown action: {action}'

        elif name == 'mcp_manage':
            from .mcp import mcp_manager
            action = args.get('action', 'list')
            if action == 'list':
                servers = mcp_manager.list_servers()
                if not servers:
                    return '🔌 연결된 MCP 서버 없음. mcp_manage(action="add", name="...", command="...") 로 추가하세요.'
                lines = ['🔌 **MCP 서버 목록:**']
                for s in servers:
                    status = '🟢' if s['connected'] else '🔴'
                    lines.append(f"  {status} {s['name']} — {s['tools']}개 도구 ({' '.join(s['command'])})")
                return '\n'.join(lines)
            elif action == 'add':
                sname = args.get('name', '')
                cmd_str = args.get('command', '')
                if not sname or not cmd_str:
                    return '❌ name과 command가 필요합니다'
                cmd_list = cmd_str.split()
                env = args.get('env', {})
                ok = mcp_manager.add_server(sname, cmd_list, env=env)
                if ok:
                    mcp_manager.save_config()
                    tools_count = len([t for t in mcp_manager.get_all_tools() if t.get('_mcp_server') == sname])
                    return f'🔌 MCP 서버 추가 성공: {sname} ({tools_count}개 도구)'
                return f'❌ MCP 서버 연결 실패: {sname}'
            elif action == 'remove':
                sname = args.get('name', '')
                mcp_manager.remove_server(sname)
                mcp_manager.save_config()
                return f'🔌 MCP 서버 제거: {sname}'
            elif action == 'tools':
                all_mcp = mcp_manager.get_all_tools()
                if not all_mcp:
                    return '🔌 MCP 도구 없음 (서버가 연결되어 있지 않음)'
                lines = [f'🔌 **MCP 도구 ({len(all_mcp)}개):**']
                for t in all_mcp:
                    lines.append(f"  🔧 {t['name']}: {t['description'][:80]}")
                return '\n'.join(lines)
            return f'❌ Unknown action: {action}'

        elif name == 'rag_search':
            from .rag import rag_engine
            query = args.get('query', '')
            if not query:
                return '❌ query가 필요합니다'
            max_results = args.get('max_results', 5)
            results = rag_engine.search(query, max_results=max_results)
            if not results:
                return f'🔍 "{query}" 검색 결과 없음'
            lines = [f'🔍 **"{query}" 검색 결과 ({len(results)}건):**']
            for r in results:
                lines.append(f"\n📄 **{r['source']}** (L{r['line']}, score: {r['score']})")
                lines.append(r['text'][:300])
            stats = rag_engine.get_stats()
            lines.append(f"\n📊 인덱스: {stats['total_chunks']}청크, {stats['unique_terms']}단어, {stats['db_size_kb']}KB")
            return '\n'.join(lines)

        else:
            # Try plugin tools as fallback
            from .core import PluginLoader
            result = PluginLoader.execute(name, args)
            if result is not None:
                return result
            # Try MCP tools as last fallback
            if name.startswith('mcp_'):
                from .mcp import mcp_manager
                mcp_result = mcp_manager.call_tool(name, args)
                if mcp_result is not None:
                    return mcp_result
            return f'❌ 알 수 없는 도구: {name}'

    except PermissionError as e:
        return f'❌ 권한 거부: {e}'
    except Exception as e:
        log.error(f"Tool error ({name}): {e}")
        return f'❌ 도구 오류: {str(e)[:200]}'
