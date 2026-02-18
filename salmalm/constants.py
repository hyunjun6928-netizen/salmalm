"""삶앎 constants — paths, costs, thresholds."""
from datetime import timedelta, timezone
from pathlib import Path

VERSION = "0.8.2"
APP_NAME = "삶앎 (SalmAlm)"
KST = timezone(timedelta(hours=9))

# Paths — resolved relative to project root (parent of salmalm/)
BASE_DIR = Path(__file__).parent.parent.resolve()
MEMORY_DIR = BASE_DIR / "memory"
WORKSPACE_DIR = BASE_DIR
SOUL_FILE = BASE_DIR / "SOUL.md"
AGENTS_FILE = BASE_DIR / "AGENTS.md"
MEMORY_FILE = BASE_DIR / "MEMORY.md"
USER_FILE = BASE_DIR / "USER.md"
TOOLS_FILE = BASE_DIR / "TOOLS.md"
VAULT_FILE = BASE_DIR / ".vault.enc"
AUDIT_DB = BASE_DIR / "audit.db"
MEMORY_DB = BASE_DIR / "memory.db"
CACHE_DB = BASE_DIR / "cache.db"
LOG_FILE = BASE_DIR / "salmalm.log"

# Security
VAULT_VERSION = b'\x03'
PBKDF2_ITER = 200_000
SESSION_TIMEOUT = 3600 * 8
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION = 60
EXEC_ALLOWLIST = {
    # Core utils
    'ls', 'cat', 'head', 'tail', 'wc', 'sort', 'uniq', 'grep', 'awk', 'sed',
    'find', 'which', 'file', 'stat', 'du', 'df', 'echo', 'printf', 'date',
    'tr', 'cut', 'tee', 'xargs', 'diff', 'patch', 'env', 'pwd', 'whoami',
    'uname', 'hostname', 'id', 'dirname', 'basename', 'realpath', 'readlink',
    'md5sum', 'sha256sum', 'base64', 'xxd', 'hexdump', 'yes', 'true', 'false',
    # Dev tools
    'python3', 'python', 'pip', 'pip3', 'node', 'npm', 'npx', 'deno', 'bun',
    'git', 'gh', 'cargo', 'rustc', 'go', 'java', 'javac', 'gcc', 'g++', 'make',
    'cmake', 'docker', 'kubectl', 'terraform',
    # Network (read-only)
    'curl', 'wget', 'ping', 'dig', 'nslookup', 'host', 'traceroute', 'ss', 'ip',
    # File ops (safe)
    'cp', 'mv', 'mkdir', 'touch', 'ln', 'tar', 'gzip', 'gunzip', 'zip', 'unzip',
    # Text
    'jq', 'yq', 'csvtool', 'sqlite3', 'psql', 'mysql',
    # System info
    'ps', 'top', 'htop', 'free', 'uptime', 'lsof', 'nproc', 'lscpu', 'lsblk',
}
EXEC_BLOCKLIST = {
    'rm', 'rmdir', 'mkfs', 'dd', 'shutdown', 'reboot', 'halt', 'poweroff',
    'init', 'systemctl', 'useradd', 'userdel', 'passwd', 'chown', 'chmod',
    'mount', 'umount', 'fdisk', 'parted', 'iptables', 'nft',
    'su', 'sudo', 'doas', 'kill', 'pkill', 'killall',
}
EXEC_BLOCKLIST_PATTERNS = [
    r'[;&|`]\s*(rm|dd|mkfs|shutdown|reboot|halt|sudo|su)\b',  # chained dangerous cmds
    r'\$\(.*\)',       # command substitution
    r'`[^`]+`',        # backtick substitution
    r'>\s*/dev/sd',    # write to raw device
    r'>\s*/etc/',      # overwrite system config
    r'/proc/sysrq',    # sysrq trigger
]
PROTECTED_FILES = {'.vault.enc', 'audit.db', 'auth.db', 'server.py', '.clipboard.json'}

# LLM
DEFAULT_MAX_TOKENS = 4096
COMPACTION_THRESHOLD = 60000
CACHE_TTL = 3600

# Token cost estimates (per 1M tokens, USD)
MODEL_COSTS = {
    # Anthropic
    'claude-opus-4-6': {'input': 15.0, 'output': 75.0},
    'claude-sonnet-4': {'input': 3.0, 'output': 15.0},
    'claude-haiku-3.5': {'input': 0.80, 'output': 4.0},
    # OpenAI
    'gpt-5.3-codex': {'input': 2.0, 'output': 8.0},
    'gpt-5.1-codex': {'input': 1.5, 'output': 6.0},
    'gpt-4.1': {'input': 2.0, 'output': 8.0},
    'gpt-4.1-mini': {'input': 0.40, 'output': 1.60},
    'gpt-4.1-nano': {'input': 0.10, 'output': 0.40},
    'o3': {'input': 10.0, 'output': 40.0},
    'o3-mini': {'input': 1.10, 'output': 4.40},
    'o4-mini': {'input': 1.10, 'output': 4.40},
    # xAI
    'grok-4': {'input': 3.0, 'output': 15.0},
    'grok-3': {'input': 3.0, 'output': 15.0},
    'grok-3-mini': {'input': 0.30, 'output': 0.50},
    # Google
    'gemini-3-pro-preview': {'input': 1.25, 'output': 10.0},
    'gemini-3-flash-preview': {'input': 0.15, 'output': 0.60},
    'gemini-2.5-pro': {'input': 1.25, 'output': 10.0},
    'gemini-2.5-flash': {'input': 0.15, 'output': 0.60},
    # DeepSeek (via OpenRouter)
    'deepseek-r1': {'input': 0.55, 'output': 2.19},
    'deepseek-chat': {'input': 0.27, 'output': 1.10},
    # Meta (via OpenRouter)
    'llama-4-maverick': {'input': 0.20, 'output': 0.60},
    'llama-4-scout': {'input': 0.15, 'output': 0.40},
}

# Model routing thresholds
SIMPLE_QUERY_MAX_CHARS = 200  # short queries → cheap model
COMPLEX_INDICATORS = ['코드', '분석', '보안', '최적화', '설계', '구현',
                       'code', 'analyze', 'security', 'build', 'implement',
                       'refactor', '디버그', 'debug', '아키텍처', '리팩토링',
                       '마이그레이션', 'migration', '서버', 'server', '배포', 'deploy',
                       '버그', 'bug', '수정', 'fix', '작성', 'write', '만들어',
                       '개발', 'develop', '테스트', 'test', '검증', 'audit',
                       '비교', 'compare', '변환', 'convert', '자동화', 'automate']
TOOL_HINT_KEYWORDS = ['파일', 'file', '실행', 'exec', 'run', '검색', 'search',
                       '웹', 'web', '이미지', 'image', '메모리', 'memory',
                       '시스템', 'system', '크론', 'cron', '스크린샷', 'screenshot']

