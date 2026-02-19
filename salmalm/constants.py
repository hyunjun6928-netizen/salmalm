"""SalmAlm constants — paths, costs, thresholds."""
from datetime import timedelta, timezone
from pathlib import Path

VERSION = "0.11.3"
APP_NAME = "SalmAlm"
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
    # Dev tools (safe)
    'git', 'gh', 'cargo', 'rustc', 'go', 'java', 'javac', 'gcc', 'g++', 'make',
    'cmake', 'pip', 'pip3', 'npm', 'npx',
    # Network (read-only)
    'ping', 'dig', 'nslookup', 'host', 'traceroute', 'ss', 'ip',
    # curl/wget removed: SSRF bypass risk (use web_fetch/http_request tools instead)
    # File ops (safe)
    'cp', 'mv', 'mkdir', 'touch', 'ln', 'tar', 'gzip', 'gunzip', 'zip', 'unzip',
    # Text
    'jq', 'yq', 'csvtool', 'sqlite3', 'psql', 'mysql',
    # System info
    'ps', 'top', 'htop', 'free', 'uptime', 'lsof', 'nproc', 'lscpu', 'lsblk',
}
# Elevated commands: allowed but logged with warning (can run arbitrary code)
EXEC_ELEVATED = {
    'python3', 'python', 'node', 'deno', 'bun',
    'docker', 'kubectl', 'terraform',
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

# Intent classification thresholds
INTENT_SHORT_MSG = 500       # messages shorter than this → simpler model
INTENT_COMPLEX_MSG = 1500    # messages longer than this → complex model
INTENT_CONTEXT_DEPTH = 40    # conversation turns threshold for complexity bump
REFLECT_SNIPPET_LEN = 500    # max chars of user message in reflection prompt

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

# ============================================================
# Model Registry — single source of truth for all model references
# ============================================================
MODELS = {
    # Anthropic
    'opus': 'anthropic/claude-opus-4-6',
    'sonnet': 'anthropic/claude-sonnet-4-20250514',
    'haiku': 'anthropic/claude-haiku-3.5-20241022',
    # OpenAI
    'gpt5.3': 'openai/gpt-5.3-codex',
    'gpt5.1': 'openai/gpt-5.1-codex',
    'gpt4.1': 'openai/gpt-4.1',
    'gpt4.1mini': 'openai/gpt-4.1-mini',
    'gpt4.1nano': 'openai/gpt-4.1-nano',
    'o3': 'openai/o3',
    'o4mini': 'openai/o4-mini',
    # xAI
    'grok4': 'xai/grok-4',
    'grok3': 'xai/grok-3',
    'grok3mini': 'xai/grok-3-mini',
    # Google
    'gemini3pro': 'google/gemini-3-pro-preview',
    'gemini3flash': 'google/gemini-3-flash-preview',
    'gemini2.5pro': 'google/gemini-2.5-pro',
    'gemini2.5flash': 'google/gemini-2.5-flash',
    # DeepSeek (via OpenRouter)
    'deepseek-r1': 'openrouter/deepseek/deepseek-r1',
    'deepseek-chat': 'openrouter/deepseek/deepseek-chat',
    # Meta (via OpenRouter)
    'maverick': 'openrouter/meta-llama/llama-4-maverick',
    'scout': 'openrouter/meta-llama/llama-4-scout',
}

# Tier-based model routing pools (cheapest → most capable)
# Ollama models included for users running local LLMs
MODEL_TIERS = {
    1: [MODELS['gemini3flash'], MODELS['gpt4.1nano'], MODELS['gpt4.1mini'], MODELS['grok3mini'],
        'ollama/llama3.2', 'ollama/qwen3'],
    2: [MODELS['sonnet'], MODELS['gpt5.3'], MODELS['grok4'], MODELS['gemini3pro'], MODELS['gpt4.1'], MODELS['gpt5.1'],
        'ollama/llama3.3', 'ollama/qwen3'],
    3: [MODELS['opus'], MODELS['o3'], MODELS['sonnet'], MODELS['gpt5.1'], MODELS['grok4'],
        'ollama/llama3.3'],
}

# Fallback models per provider (cheapest reliable model)
FALLBACK_MODELS = {
    'anthropic': 'claude-sonnet-4-20250514',
    'xai': 'grok-4',
    'google': 'gemini-3-flash-preview',
}

# API validation test models (lightweight, for key testing)
TEST_MODELS = {
    'anthropic': 'claude-haiku-4-5-20250414',
    'openai': 'gpt-4.1-nano',
    'xai': 'grok-3-mini',
    'google': 'gemini-2.0-flash',
}

# User-facing model aliases (for /model command)
MODEL_ALIASES = {
    'claude': MODELS['sonnet'], 'sonnet': MODELS['sonnet'],
    'opus': MODELS['opus'], 'haiku': MODELS['haiku'],
    'gpt': MODELS['gpt5.3'], 'gpt5': MODELS['gpt5.3'],
    'gpt5.1': MODELS['gpt5.1'], 'gpt4.1': MODELS['gpt4.1'],
    '4.1mini': MODELS['gpt4.1mini'], '4.1nano': MODELS['gpt4.1nano'],
    'o3': MODELS['o3'], 'o4mini': MODELS['o4mini'],
    'grok': MODELS['grok4'], 'grok4': MODELS['grok4'],
    'grok3': MODELS['grok3'], 'grok3mini': MODELS['grok3mini'],
    'gemini': MODELS['gemini3pro'], 'flash': MODELS['gemini3flash'],
    'deepseek': MODELS['deepseek-r1'], 'maverick': MODELS['maverick'], 'scout': MODELS['scout'],
    'llama': 'ollama/llama3.3', 'llama3.2': 'ollama/llama3.2', 'llama3.3': 'ollama/llama3.3',
    'qwen': 'ollama/qwen3', 'qwen3': 'ollama/qwen3',
}

# Model for /commands processing (cheap + capable)
COMMAND_MODEL = MODELS['opus']

# Model routing thresholds
SIMPLE_QUERY_MAX_CHARS = 200  # short queries → cheap model
COMPLEX_INDICATORS = ['code', 'analyze', 'security', 'optimize', 'design', 'implement',
                       'build', 'refactor', 'debug', 'architecture',
                       'migration', 'server', 'deploy',
                       'bug', 'fix', 'write',
                       'develop', 'test', 'audit',
                       'compare', 'convert', 'automate']
TOOL_HINT_KEYWORDS = ['file', 'exec', 'run', 'search',
                       'web', 'image', 'memory',
                       'system', 'cron', 'screenshot']

