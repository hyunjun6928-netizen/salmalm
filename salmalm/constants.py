"""SalmAlm constants — paths, costs, thresholds."""

from datetime import timedelta, timezone
from pathlib import Path

from salmalm import __version__ as VERSION  # Single source of truth

APP_NAME = "SalmAlm"
KST = timezone(timedelta(hours=9))

# Paths
# BASE_DIR = code/resource root (package directory)
# DATA_DIR = runtime data root (user data: DB, vault, memory, logs)
#   Priority: $SALMALM_HOME > ~/SalmAlm
import os as _os

BASE_DIR = Path(__file__).parent.resolve()  # salmalm/ package dir
DATA_DIR = Path(_os.environ.get("SALMALM_HOME", "") or Path.home() / "SalmAlm")
MEMORY_DIR = DATA_DIR / "memory"
WORKSPACE_DIR = DATA_DIR
SOUL_FILE = DATA_DIR / "soul.md"
AGENTS_FILE = DATA_DIR / "agents.md"
MEMORY_FILE = DATA_DIR / "memory.md"
USER_FILE = DATA_DIR / "user.md"
TOOLS_FILE = DATA_DIR / "tools.md"
VAULT_FILE = DATA_DIR / ".vault.enc"
AUDIT_DB = DATA_DIR / "audit.db"
MEMORY_DB = DATA_DIR / "memory.db"
CACHE_DB = DATA_DIR / "cache.db"
LOG_FILE = DATA_DIR / "salmalm.log"

# Security
VAULT_VERSION = b"\x03"
PBKDF2_ITER = 200_000
SESSION_TIMEOUT = 3600 * 8
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION = 60
# ── Exec Allowlist Tiers ──────────────────────────────────────
# Tier 1 (BASIC): Always allowed — read-only utils, dev tools, file ops, system info
_EXEC_TIER_BASIC = {
    # Core utils (read-only / safe)
    "ls",
    "cat",
    "head",
    "tail",
    "wc",
    "sort",
    "uniq",
    "grep",
    "sed",
    "which",
    "file",
    "stat",
    "du",
    "df",
    "echo",
    "printf",
    "date",
    "tr",
    "cut",
    "tee",
    "diff",
    "patch",
    "env",
    "pwd",
    "whoami",
    "uname",
    "hostname",
    "id",
    "dirname",
    "basename",
    "realpath",
    "readlink",
    "md5sum",
    "sha256sum",
    "base64",
    "xxd",
    "hexdump",
    "yes",
    "true",
    "false",
    # Dev tools (read-only / query only)
    "git",
    "gh",
    # Guarded commands — allowed but with subcommand/flag restrictions (see EXEC_ARG_BLOCKLIST)
    "awk",
    "find",
    "xargs",
    "tar",
    # File ops (safe)
    "cp",
    "mv",
    "mkdir",
    "touch",
    "ln",
    "gzip",
    "gunzip",
    "zip",
    "unzip",
    # Text processing
    "jq",
    "yq",
    "csvtool",
    # System info
    "ps",
    "top",
    "htop",
    "free",
    "uptime",
    "lsof",
    "nproc",
    "lscpu",
    "lsblk",
}

# Tier 2 (NETWORK): Network diagnostics — requires SALMALM_EXEC_NETWORK=1
_EXEC_TIER_NETWORK = {
    "ping",
    "dig",
    "nslookup",
    "host",
    "traceroute",
    "ss",
    "ip",
}

# Tier 3 (DATABASE): DB clients — requires SALMALM_EXEC_DATABASE=1
_EXEC_TIER_DATABASE = {
    "sqlite3",
    "psql",
    "mysql",
}


def _build_exec_allowlist() -> set:
    """Build effective allowlist from tiers + env vars."""
    allowed = set(_EXEC_TIER_BASIC)
    if _os.environ.get("SALMALM_EXEC_NETWORK", "1") == "1":
        allowed |= _EXEC_TIER_NETWORK
    if _os.environ.get("SALMALM_EXEC_DATABASE", "1") == "1":
        allowed |= _EXEC_TIER_DATABASE
    return allowed


EXEC_ALLOWLIST = _build_exec_allowlist()
# Per-command dangerous argument/flag blocklist — blocks code execution vectors
EXEC_ARG_BLOCKLIST: dict = {
    "awk": {"-f", "--file"},
    "find": {"-exec", "-execdir", "-delete", "-ok", "-okdir"},
    "xargs": {"-I", "--replace", "-i"},
    "tar": {"--to-command", "--checkpoint-action", "--use-compress-program"},
    "git": {"clone", "pull", "push", "fetch", "remote", "submodule", "hook"},
    "sed": {"-i", "--in-place"},
}
# Pattern blocklist for inline code execution in awk/sed
EXEC_INLINE_CODE_PATTERNS = [
    r"\bawk\b[^|;]*\bsystem\s*\(",  # awk '{ system("...") }'
    r"\bawk\b[^|;]*\bgetline\b",  # awk getline can read arbitrary files/commands
    r'\bawk\b[^|;]*"\s*\|',  # awk print | "cmd"
]
# Elevated commands: allowed but logged with warning (can run arbitrary code)
# Interpreters (python/node/deno/bun) removed — use python_eval tool instead.
# They bypass allowlist by executing arbitrary code via -c, -m, file args, stdin.
EXEC_ELEVATED = {
    # Build tools: can execute arbitrary code via Makefiles, build scripts, hooks
    "cargo",
    "rustc",
    "go",
    "java",
    "javac",
    "gcc",
    "g++",
    "make",
    "cmake",
    "docker",
    "kubectl",
    "terraform",
    "pip",
    "pip3",
    "npm",
    "npx",  # install hooks can run arbitrary code
}
# Interpreters: blocked from exec entirely (use python_eval / dedicated tools)
EXEC_BLOCKED_INTERPRETERS = {
    "python",
    "python3",
    "python3.10",
    "python3.11",
    "python3.12",
    "python3.13",
    "python3.14",
    "node",
    "deno",
    "bun",
    "ruby",
    "perl",
    "lua",
    "php",
    "bash",
    "sh",
    "zsh",
    "fish",
    "dash",
    "csh",
    "tcsh",
    "ksh",
}
EXEC_BLOCKLIST = {
    "rm",
    "rmdir",
    "mkfs",
    "dd",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    "init",
    "systemctl",
    "useradd",
    "userdel",
    "passwd",
    "chown",
    "chmod",
    "mount",
    "umount",
    "fdisk",
    "parted",
    "iptables",
    "nft",
    "su",
    "sudo",
    "doas",
    "kill",
    "pkill",
    "killall",
}
EXEC_BLOCKLIST_PATTERNS = [
    r"[;&|`]\s*(rm|dd|mkfs|shutdown|reboot|halt|sudo|su)\b",  # chained dangerous cmds
    r"\$\(",  # command substitution (any)
    r"`[^`]*`",  # backtick substitution (any, including empty)
    r">\s*/dev/sd",  # write to raw device
    r">\s*/etc/",  # overwrite system config
    r"/proc/sysrq",  # sysrq trigger
    r"<\(",  # process substitution
    r"\beval\b",  # eval bypass
    r"\bsource\b",  # source bypass
]
PROTECTED_FILES = {".vault.enc", "audit.db", "auth.db", "server.py", ".clipboard.json"}

# LLM
DEFAULT_MAX_TOKENS = 4096
COMPACTION_THRESHOLD = 30000
CACHE_TTL = int(_os.environ.get("SALMALM_CACHE_TTL", "3600"))

# Intent classification thresholds
INTENT_SHORT_MSG = 500  # messages shorter than this → simpler model
INTENT_COMPLEX_MSG = 1500  # messages longer than this → complex model
INTENT_CONTEXT_DEPTH = 40  # conversation turns threshold for complexity bump
REFLECT_SNIPPET_LEN = 500  # max chars of user message in reflection prompt

# Token cost estimates (per 1M tokens, USD)
MODEL_COSTS = {
    # Anthropic
    "claude-opus-4-6": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4": {"input": 3.0, "output": 15.0},
    "claude-haiku-3.5": {"input": 0.80, "output": 4.0},
    # OpenAI
    "gpt-5.3-codex": {"input": 2.0, "output": 8.0},
    "gpt-5.1-codex": {"input": 1.5, "output": 6.0},
    "gpt-4.1": {"input": 2.0, "output": 8.0},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
    "o3": {"input": 10.0, "output": 40.0},
    "o3-mini": {"input": 1.10, "output": 4.40},
    "o4-mini": {"input": 1.10, "output": 4.40},
    # xAI
    "grok-4": {"input": 3.0, "output": 15.0},
    "grok-3": {"input": 3.0, "output": 15.0},
    "grok-3-mini": {"input": 0.30, "output": 0.50},
    # Google
    "gemini-3-pro-preview": {"input": 1.25, "output": 10.0},
    "gemini-3-flash-preview": {"input": 0.15, "output": 0.60},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.0},
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    # DeepSeek (via OpenRouter)
    "deepseek-r1": {"input": 0.55, "output": 2.19},
    "deepseek-chat": {"input": 0.27, "output": 1.10},
    # Meta (via OpenRouter)
    "llama-4-maverick": {"input": 0.20, "output": 0.60},
    "llama-4-scout": {"input": 0.15, "output": 0.40},
}

# ============================================================
# Model Registry — single source of truth for all model references
# ============================================================
MODELS = {
    # Anthropic
    "opus": "anthropic/claude-opus-4-6",
    "sonnet": "anthropic/claude-sonnet-4-20250514",
    "haiku": "anthropic/claude-haiku-3.5-20241022",
    # OpenAI
    "gpt5.3": "openai/gpt-5.3-codex",
    "gpt5.1": "openai/gpt-5.1-codex",
    "gpt4.1": "openai/gpt-4.1",
    "gpt4.1mini": "openai/gpt-4.1-mini",
    "gpt4.1nano": "openai/gpt-4.1-nano",
    "o3": "openai/o3",
    "o4mini": "openai/o4-mini",
    # xAI
    "grok4": "xai/grok-4",
    "grok3": "xai/grok-3",
    "grok3mini": "xai/grok-3-mini",
    # Google
    "gemini3pro": "google/gemini-3-pro-preview",
    "gemini3flash": "google/gemini-3-flash-preview",
    "gemini2.5pro": "google/gemini-2.5-pro",
    "gemini2.5flash": "google/gemini-2.5-flash",
    # DeepSeek (via OpenRouter)
    "deepseek-r1": "openrouter/deepseek/deepseek-r1",
    "deepseek-chat": "openrouter/deepseek/deepseek-chat",
    # Meta (via OpenRouter)
    "maverick": "openrouter/meta-llama/llama-4-maverick",
    "scout": "openrouter/meta-llama/llama-4-scout",
}

# Tier-based model routing pools (cheapest → most capable)
# Ollama models included for users running local LLMs
MODEL_TIERS = {
    1: [
        MODELS["gemini3flash"],
        MODELS["gpt4.1nano"],
        MODELS["gpt4.1mini"],
        MODELS["grok3mini"],
        "ollama/llama3.2",
        "ollama/qwen3",
    ],
    2: [
        MODELS["sonnet"],
        MODELS["gpt5.3"],
        MODELS["grok4"],
        MODELS["gemini3pro"],
        MODELS["gpt4.1"],
        MODELS["gpt5.1"],
        "ollama/llama3.3",
        "ollama/qwen3",
    ],
    3: [MODELS["opus"], MODELS["o3"], MODELS["sonnet"], MODELS["gpt5.1"], MODELS["grok4"], "ollama/llama3.3"],
}

# Fallback models per provider (cheapest reliable model)
FALLBACK_MODELS = {
    "anthropic": "claude-sonnet-4-20250514",
    "xai": "grok-4",
    "google": "gemini-3-flash-preview",
}

# API validation test models (lightweight, for key testing)
TEST_MODELS = {
    "anthropic": "claude-3-5-haiku-20241022",
    "openai": "gpt-4.1-nano",
    "xai": "grok-3-mini",
    "google": "gemini-2.0-flash",
}

# User-facing model aliases (for /model command)
MODEL_ALIASES = {
    "claude": MODELS["sonnet"],
    "sonnet": MODELS["sonnet"],
    "opus": MODELS["opus"],
    "haiku": MODELS["haiku"],
    "gpt": MODELS["gpt5.3"],
    "gpt5": MODELS["gpt5.3"],
    "gpt5.1": MODELS["gpt5.1"],
    "gpt4.1": MODELS["gpt4.1"],
    "4.1mini": MODELS["gpt4.1mini"],
    "4.1nano": MODELS["gpt4.1nano"],
    "o3": MODELS["o3"],
    "o4mini": MODELS["o4mini"],
    "grok": MODELS["grok4"],
    "grok4": MODELS["grok4"],
    "grok3": MODELS["grok3"],
    "grok3mini": MODELS["grok3mini"],
    "gemini": MODELS["gemini3pro"],
    "flash": MODELS["gemini3flash"],
    "deepseek": MODELS["deepseek-r1"],
    "maverick": MODELS["maverick"],
    "scout": MODELS["scout"],
    "llama": "ollama/llama3.3",
    "llama3.2": "ollama/llama3.2",
    "llama3.3": "ollama/llama3.3",
    "qwen": "ollama/qwen3",
    "qwen3": "ollama/qwen3",
}

# Model for /commands processing (cheap + capable)
COMMAND_MODEL = MODELS["opus"]

# Model routing thresholds
SIMPLE_QUERY_MAX_CHARS = 200  # short queries → cheap model
COMPLEX_INDICATORS = [
    "code",
    "analyze",
    "security",
    "optimize",
    "design",
    "implement",
    "build",
    "refactor",
    "debug",
    "architecture",
    "migration",
    "server",
    "deploy",
    "bug",
    "fix",
    "write",
    "develop",
    "test",
    "audit",
    "compare",
    "convert",
    "automate",
]
TOOL_HINT_KEYWORDS = ["file", "exec", "run", "search", "web", "image", "memory", "system", "cron", "screenshot"]

# ── Model name corrections (deprecated → current API IDs) ──
# Single source of truth for model ID fixes. Used by model_selection.fix_model_name().
MODEL_NAME_FIXES: dict = {
    "claude-haiku-3.5-20241022": "claude-3-5-haiku-20241022",
    "anthropic/claude-haiku-3.5-20241022": "anthropic/claude-3-5-haiku-20241022",
    "claude-3-5-haiku-20241022": "claude-3-5-haiku-20241022",
    "claude-sonnet-4-20250514": "claude-sonnet-4-6",
    "anthropic/claude-sonnet-4-20250514": "anthropic/claude-sonnet-4-6",
    "gpt-5.3-codex": "gpt-5.2-codex",
    "openai/gpt-5.3-codex": "openai/gpt-5.2-codex",
    "grok-4": "grok-4-0709",
    "xai/grok-4": "xai/grok-4-0709",
}
