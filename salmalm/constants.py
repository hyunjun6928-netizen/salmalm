"""SalmAlm constants — paths, costs, thresholds."""

from datetime import timedelta, timezone

try:
    from importlib.metadata import version as _pkg_version
    VERSION = _pkg_version("salmalm")
except Exception:
    VERSION = "0.0.0-dev"

APP_NAME = "SalmAlm"
KST = timezone(timedelta(hours=9))

# Paths
# BASE_DIR = code/resource root (package directory)
# DATA_DIR = runtime data root (user data: DB, vault, memory, logs)
#   Priority: $SALMALM_HOME > ~/SalmAlm
import os as _os
import importlib as _importlib
from salmalm.config import limits as _limits
from salmalm.config import models as _models
from salmalm.config import paths as _paths

_importlib.reload(_paths)
_importlib.reload(_limits)

AGENTS_FILE = _paths.AGENTS_FILE
AUDIT_DB = _paths.AUDIT_DB
BASE_DIR = _paths.BASE_DIR
CACHE_DB = _paths.CACHE_DB
DATA_DIR = _paths.DATA_DIR
LOG_FILE = _paths.LOG_FILE
MEMORY_DB = _paths.MEMORY_DB
MEMORY_DIR = _paths.MEMORY_DIR
MEMORY_FILE = _paths.MEMORY_FILE
SOUL_FILE = _paths.SOUL_FILE
TOOLS_FILE = _paths.TOOLS_FILE
USER_FILE = _paths.USER_FILE
VAULT_FILE = _paths.VAULT_FILE
WORKSPACE_DIR = _paths.WORKSPACE_DIR

# Security
VAULT_VERSION = b"\x03"
PBKDF2_ITER = 600_000  # OWASP 2023 recommendation for PBKDF2-HMAC-SHA256
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


def _build_exec_allowlist() -> frozenset:
    """Build effective allowlist from tiers + env vars. Returns frozenset (immutable)."""
    allowed = set(_EXEC_TIER_BASIC)
    # Tier 2/3 default OFF (opt-in): set env var to "1" to enable.
    # Security: network/database tools should not be available unless explicitly requested.
    if _os.environ.get("SALMALM_EXEC_NETWORK", "0") == "1":
        allowed |= _EXEC_TIER_NETWORK
    if _os.environ.get("SALMALM_EXEC_DATABASE", "0") == "1":
        allowed |= _EXEC_TIER_DATABASE
    return frozenset(allowed)  # Immutable — built once at import time


EXEC_ALLOWLIST: frozenset = _build_exec_allowlist()
# Per-command dangerous argument/flag blocklist — blocks code execution vectors
EXEC_ARG_BLOCKLIST: dict = {
    "awk": {"-f", "--file"},
    "find": {"-exec", "-execdir", "-delete", "-ok", "-okdir"},
    "xargs": {"-I", "--replace", "-i"},
    "tar": {"--to-command", "--checkpoint-action", "--use-compress-program"},
    # "hook"/"submodule" blocked: direct hook/submodule manipulation is too risky.
    # commit/push/pull/clone are allowed via EXEC_GIT_SAFE_OVERRIDES (auto --no-verify injection).
    "git": {"submodule", "hook", "am"},
    "sed": {"-i", "--in-place"},
}
# Git safe-override flags: automatically injected when these subcommands are used.
# This allows normal git workflow while preventing hook execution (security boundary).
EXEC_GIT_SAFE_OVERRIDES: dict = {
    "commit": ["--no-verify"],           # skip pre-commit / commit-msg hooks
    "push": ["--no-verify"],             # skip pre-push hooks
    "pull": ["--no-verify"],             # skip post-merge hooks
    "clone": ["--config", "core.hooksPath=/dev/null"],  # disable all hooks in clone
    "rebase": ["--no-exec"],             # prevent --exec arbitrary command injection
    "merge": ["--no-verify"],            # skip pre-merge hooks
    "fetch": [],                         # safe as-is
    "remote": [],                        # safe as-is
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
    r"`[^`]+`",  # backtick substitution — requires at least 1 char inside (empty backticks are harmless)
    r">\s*/dev/sd",  # write to raw device
    r">\s*/etc/",  # overwrite system config
    r"/proc/sysrq",  # sysrq trigger
    r"<\(",  # process substitution
    r"\beval\b",  # eval bypass
    r"\bsource\b",  # source bypass
]
PROTECTED_FILES = {".vault.enc", "audit.db", "auth.db", "server.py", ".clipboard.json"}

# LLM
CACHE_TTL = _limits.CACHE_TTL
COMPACTION_THRESHOLD = _limits.COMPACTION_THRESHOLD
DEFAULT_MAX_TOKENS = _limits.DEFAULT_MAX_TOKENS
INTENT_COMPLEX_MSG = _limits.INTENT_COMPLEX_MSG
INTENT_CONTEXT_DEPTH = _limits.INTENT_CONTEXT_DEPTH
INTENT_SHORT_MSG = _limits.INTENT_SHORT_MSG
REFLECT_SNIPPET_LEN = _limits.REFLECT_SNIPPET_LEN

# Token cost estimates (per 1M tokens, USD)
MODEL_COSTS = {
    # Anthropic
    "claude-opus-4-6": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-sonnet-4": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
    # OpenAI
    "gpt-5.2": {"input": 2.0, "output": 8.0},
    "gpt-5.2-codex": {"input": 2.0, "output": 8.0},
    "gpt-5": {"input": 2.0, "output": 8.0},
    "gpt-5-mini": {"input": 0.40, "output": 1.60},
    "gpt-5-nano": {"input": 0.10, "output": 0.40},
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
    "gemini-3.1-pro": {"input": 1.25, "output": 10.0},
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
FALLBACK_MODELS = _models.FALLBACK_MODELS
MODEL_ALIASES = _models.MODEL_ALIASES
MODELS = _models.MODELS
THINKING_BUDGET_MAP = _models.THINKING_BUDGET_MAP

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
        MODELS["gpt5.2"],
        MODELS["grok4"],
        MODELS["gemini3pro"],
        MODELS["gpt4.1"],
        MODELS["gpt5.1"],
        "ollama/llama3.3",
        "ollama/qwen3",
    ],
    3: [MODELS["opus"], MODELS["o3"], MODELS["sonnet"], MODELS["gpt5.1"], MODELS["grok4"], "ollama/llama3.3"],
}

# API validation test models (lightweight, for key testing)
TEST_MODELS = {
    "anthropic": "claude-haiku-4-5-20251001",
    "openai": "gpt-4.1-nano",
    "xai": "grok-3-mini",
    "google": "gemini-2.0-flash",
}

# Model for /commands processing (fast + capable; sonnet is the right balance)
COMMAND_MODEL = MODELS["sonnet"]

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

# ── Well-known model IDs used across the codebase (MED-15) ──
MODEL_GPT_IMAGE = "gpt-image-1"
MODEL_GPT_4_1_NANO = "gpt-4.1-nano"
MODEL_CLAUDE_SONNET = "claude-sonnet-4-6"
MODEL_CLAUDE_HAIKU = "claude-haiku-4-5-20251001"
MODEL_GPT_4_1_NANO_OPENAI = "gpt-4.1-nano"  # bare name, no provider prefix
MODEL_GEMINI_FLASH = "google/gemini-2.5-flash"
MODEL_GEMINI_2_FLASH = "gemini-2.0-flash"

# ── Model fallback chains for retry logic ──
MODEL_FALLBACKS = {
    "anthropic/claude-opus-4-6": [
        "anthropic/claude-sonnet-4-6",
        "anthropic/claude-haiku-4-5-20251001",
        "google/gemini-2.5-pro",
        "openai/gpt-4.1",
    ],
    "anthropic/claude-sonnet-4-6": [
        "anthropic/claude-haiku-4-5-20251001",
        "anthropic/claude-opus-4-6",
        "google/gemini-2.5-flash",
        "openai/gpt-4.1-mini",
    ],
    "anthropic/claude-haiku-4-5-20251001": [
        "anthropic/claude-sonnet-4-6",
        "google/gemini-2.0-flash",
        "openai/gpt-4.1-mini",
    ],
    "openai/gpt-5.2": ["openai/gpt-4.1", "anthropic/claude-sonnet-4-6", "google/gemini-2.5-pro"],
    "openai/gpt-4.1": ["openai/gpt-4.1-mini", "anthropic/claude-sonnet-4-6", "google/gemini-2.5-flash"],
    "openai/gpt-4.1-mini": ["openai/gpt-4.1", "google/gemini-2.0-flash", "anthropic/claude-haiku-4-5-20251001"],
    "google/gemini-2.5-pro": ["google/gemini-2.5-flash", "google/gemini-2.0-flash", "anthropic/claude-sonnet-4-6"],
    "google/gemini-2.5-flash": [
        "google/gemini-2.0-flash",
        "google/gemini-2.5-pro",
        "anthropic/claude-haiku-4-5-20251001",
    ],
    "google/gemini-2.0-flash": ["google/gemini-2.5-flash", "anthropic/claude-haiku-4-5-20251001"],
    "google/gemini-3-pro-preview": [
        "google/gemini-2.5-pro",
        "google/gemini-3-flash-preview",
        "anthropic/claude-sonnet-4-6",
    ],
    "google/gemini-3-flash-preview": [
        "google/gemini-2.0-flash",
        "google/gemini-2.5-flash",
        "anthropic/claude-haiku-4-5-20251001",
    ],
    "xai/grok-4": ["xai/grok-3", "anthropic/claude-sonnet-4-6", "google/gemini-2.5-pro"],
    "xai/grok-3": ["xai/grok-4", "anthropic/claude-sonnet-4-6", "google/gemini-2.5-flash"],
}

# ── Model name corrections (deprecated → current API IDs) ──
# Single source of truth for model ID fixes. Used by model_selection.fix_model_name().
MODEL_NAME_FIXES: dict = {
    "claude-haiku-3.5-20241022": "claude-haiku-4-5-20251001",
    "anthropic/claude-haiku-3.5-20241022": "anthropic/claude-haiku-4-5-20251001",
    "claude-haiku-4-5-20251001": "claude-haiku-4-5-20251001",
    "claude-sonnet-4-20250514": "claude-sonnet-4-6",
    "anthropic/claude-sonnet-4-20250514": "anthropic/claude-sonnet-4-6",
    "gpt-5.3-codex": "gpt-5.2-codex",
    "openai/gpt-5.3-codex": "openai/gpt-5.2-codex",
    "grok-4": "grok-4-0709",
    "xai/grok-4": "xai/grok-4-0709",
}
