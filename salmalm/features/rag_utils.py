"""RAG utility functions: tokenization, stemming, similarity."""

import json
import math
from typing import Dict, List, Optional
from pathlib import Path
import logging

log = logging.getLogger(__name__)

# ── Korean Jamo Decomposition ──
_CHO = list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")
_JUNG = list("ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ")
_JONG = [""] + list("ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ")

from salmalm.constants import DATA_DIR  # noqa: E402

_DEFAULT_CONFIG = {
    "hybrid": {"enabled": True, "vectorWeight": 0.7, "textWeight": 0.3},
    "sessionIndexing": {"enabled": False, "retentionDays": 30},
    "extraPaths": [],
    "chunkSize": 5,
    "chunkOverlap": 2,
    "reindexInterval": 120,
}

CHUNK_SIZE = 5

CHUNK_OVERLAP = 2

MAX_CHUNK_CHARS = 1500

_SYNONYMS: Dict[str, List[str]] = {
    # Korean
    "검색": ["찾기", "탐색", "서치"],
    "파일": ["문서", "파일"],
    "설정": ["설정", "세팅", "구성", "환경설정"],
    "삭제": ["제거", "지우기"],
    "추가": ["생성", "만들기", "등록"],
    "수정": ["변경", "편집", "업데이트"],
    "저장": ["보관", "세이브"],
    "실행": ["구동", "런", "시작"],
    "오류": ["에러", "버그", "문제"],
    "메모리": ["기억", "메모"],
    "사용자": ["유저", "사용자"],
    "서버": ["서버", "호스트"],
    "데이터": ["정보", "자료"],
    "데이터베이스": ["디비", "DB", "데이터베이스"],
    # English
    "search": ["find", "lookup", "query"],
    "file": ["document", "doc"],
    "config": ["configuration", "settings", "setup"],
    "delete": ["remove", "erase"],
    "create": ["add", "make", "new"],
    "update": ["modify", "edit", "change"],
    "save": ["store", "persist"],
    "run": ["execute", "start", "launch"],
    "error": ["bug", "issue", "problem", "fail"],
    "memory": ["recall", "remember"],
    "user": ["person", "account"],
    "server": ["host", "backend"],
    "data": ["info", "information"],
    "database": ["db", "datastore"],
}

# Build reverse lookup
_SYNONYM_REVERSE: Dict[str, List[str]] = {}
for _key, _vals in _SYNONYMS.items():
    for _v in _vals:
        _vl = _v.lower()
        if _vl not in _SYNONYM_REVERSE:
            _SYNONYM_REVERSE[_vl] = []
        _SYNONYM_REVERSE[_vl].append(_key.lower())
    _kl = _key.lower()
    if _kl not in _SYNONYM_REVERSE:
        _SYNONYM_REVERSE[_kl] = []
    _SYNONYM_REVERSE[_kl].extend(v.lower() for v in _vals)


def decompose_jamo(text: str) -> str:
    """Decompose Korean syllables into jamo (초성/중성/종성)."""
    result = []
    for ch in text:
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3:
            offset = code - 0xAC00
            cho = offset // (21 * 28)
            jung = (offset % (21 * 28)) // 28
            jong = offset % 28
            result.append(_CHO[cho])
            result.append(_JUNG[jung])
            if jong:
                result.append(_JONG[jong])
        else:
            result.append(ch)
    return "".join(result)


def simple_stem(word: str) -> str:
    """Simple English suffix stripping."""
    if len(word) <= 3:
        return word
    # Order matters: try longest suffixes first
    for suffix, replacement in [
        ("ational", "ate"),
        ("tional", "tion"),
        ("enci", "ence"),
        ("anci", "ance"),
        ("izer", "ize"),
        ("isation", "ize"),
        ("ization", "ize"),
        ("ation", "ate"),
        ("fulness", "ful"),
        ("ousness", "ous"),
        ("iveness", "ive"),
        ("ement", ""),
        ("ment", ""),
        ("ness", ""),
        ("ible", ""),
        ("able", ""),
        ("ling", ""),
        ("ying", "y"),
        ("ting", "t"),
        ("ning", "n"),
        ("ring", "r"),
        ("ies", "y"),
        ("ing", ""),
        ("ely", ""),
        ("ally", "al"),
        ("ity", ""),
        ("ous", ""),
        ("ive", ""),
        ("ful", ""),
        ("less", ""),
        ("ion", ""),
        ("ers", ""),
        ("ed", ""),
        ("es", ""),
        ("ly", ""),
        ("er", ""),
        ("s", ""),
    ]:
        if word.endswith(suffix) and len(word) - len(suffix) + len(replacement) >= 3:
            return word[: -len(suffix)] + replacement
    return word


def expand_query(tokens: List[str]) -> List[str]:
    """Expand query tokens with synonyms."""
    expanded = list(tokens)
    seen = set(t.lower() for t in tokens)
    for t in tokens:
        tl = t.lower()
        # Direct lookup
        if tl in _SYNONYMS:
            for syn in _SYNONYMS[tl]:
                sl = syn.lower()
                if sl not in seen:
                    expanded.append(sl)
                    seen.add(sl)
        # Reverse lookup
        if tl in _SYNONYM_REVERSE:
            for syn in _SYNONYM_REVERSE[tl]:
                if syn not in seen:
                    expanded.append(syn)
                    seen.add(syn)
    return expanded


def load_rag_config(config_path: Optional[Path] = None) -> dict:
    """Load rag.json config, falling back to defaults."""
    path = config_path or DATA_DIR / "rag.json"
    config = dict(_DEFAULT_CONFIG)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            # Merge top-level keys
            for k, v in user_cfg.items():
                if k in config and isinstance(config[k], dict) and isinstance(v, dict):
                    merged = dict(config[k])
                    merged.update(v)
                    config[k] = merged
                else:
                    config[k] = v
        except Exception as e:
            log.warning(f"RAG config load error: {e}")
    return config


def compute_tf(tokens: List[str]) -> Dict[str, float]:
    """Compute term frequency vector (normalized)."""
    if not tokens:
        return {}
    counts: Dict[str, int] = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    n = len(tokens)
    return {t: c / n for t, c in counts.items()}


def cosine_similarity(v1: Dict[str, float], v2: Dict[str, float]) -> float:
    """Cosine similarity between two sparse vectors (dict-based)."""
    if not v1 or not v2:
        return 0.0
    # Dot product - iterate over smaller dict
    if len(v1) > len(v2):
        v1, v2 = v2, v1
    dot = 0.0
    for k, val in v1.items():
        if k in v2:
            dot += val * v2[k]
    if dot == 0.0:
        return 0.0
    norm1 = math.sqrt(sum(v * v for v in v1.values()))
    norm2 = math.sqrt(sum(v * v for v in v2.values()))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (norm1 * norm2)
