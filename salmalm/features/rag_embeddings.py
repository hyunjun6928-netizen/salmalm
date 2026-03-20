"""Embedding-based vector search using AI provider APIs.

Pure stdlib — uses urllib.request for HTTP calls.
Supports OpenAI, Google, and Anthropic embedding APIs with automatic fallback.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# Provider configurations
_PROVIDERS = ["openai", "google"]  # Anthropic doesn't have a public embedding API

_DIMENSIONS = {
    "openai": 1536,
    "google": 768,
}


def _get_api_key(provider: str) -> Optional[str]:
    """Resolve API key for a provider."""
    try:
        from salmalm.core.llm_router import get_api_key
        return get_api_key(provider)
    except Exception:
        return None


def _embed_openai(texts: List[str], api_key: str) -> List[List[float]]:
    """Call OpenAI embeddings API."""
    body = json.dumps({
        "model": "text-embedding-3-small",
        "input": texts,
    }).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/embeddings",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    # Sort by index to ensure correct order
    items = sorted(data["data"], key=lambda x: x["index"])
    return [item["embedding"] for item in items]


def _embed_google(texts: List[str], api_key: str) -> List[List[float]]:
    """Call Google embeddings API (one at a time — batch not supported in simple endpoint)."""
    results = []
    for text in texts:
        body = json.dumps({
            "content": {"parts": [{"text": text}]},
        }).encode()
        url = f"https://generativelanguage.googleapis.com/v1/models/text-embedding-004:embedContent?key={api_key}"
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        results.append(data["embedding"]["values"])
    return results


_EMBED_FNS = {
    "openai": _embed_openai,
    "google": _embed_google,
}


def get_available_provider() -> Optional[str]:
    """Return first available embedding provider or None."""
    for provider in _PROVIDERS:
        key = _get_api_key(provider)
        if key:
            return provider
    return None


def get_embedding(text: str, provider: Optional[str] = None, conn: Optional[sqlite3.Connection] = None) -> Optional[Tuple[List[float], str]]:
    """Get embedding for text, using cache if available.
    
    Returns (embedding, provider) or None on failure.
    """
    text_hash = hashlib.sha256(text.encode()).hexdigest()[:32]
    
    # Check cache
    if conn:
        try:
            row = conn.execute(
                "SELECT embedding, provider FROM rag_embeddings WHERE chunk_hash=?",
                (text_hash,),
            ).fetchone()
            if row:
                return json.loads(row[0]), row[1]
        except Exception as _e:
            log.debug("[RAG-EMBED] suppressed: %s", _e)

    # Determine provider
    if provider is None:
        provider = get_available_provider()
    if provider is None:
        return None
    
    api_key = _get_api_key(provider)
    if not api_key:
        return None

    try:
        fn = _EMBED_FNS.get(provider)
        if not fn:
            return None
        embeddings = fn([text], api_key)
        if not embeddings:
            return None
        emb = embeddings[0]
        
        # Cache
        if conn:
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO rag_embeddings (chunk_hash, embedding, provider, dimensions) VALUES (?,?,?,?)",
                    (text_hash, json.dumps(emb), provider, len(emb)),
                )
                conn.commit()
            except Exception as _e:
                log.debug("[RAG-EMBED] suppressed: %s", _e)
        
        return emb, provider
    except Exception as e:
        log.debug(f"[RAG] Embedding failed via {provider}: {e}")
        # Try fallback
        for fallback in _PROVIDERS:
            if fallback == provider:
                continue
            fb_key = _get_api_key(fallback)
            if not fb_key:
                continue
            try:
                fn = _EMBED_FNS[fallback]
                embeddings = fn([text], fb_key)
                if embeddings:
                    emb = embeddings[0]
                    if conn:
                        try:
                            conn.execute(
                                "INSERT OR REPLACE INTO rag_embeddings (chunk_hash, embedding, provider, dimensions) VALUES (?,?,?,?)",
                                (text_hash, json.dumps(emb), fallback, len(emb)),
                            )
                            conn.commit()
                        except Exception as _e:
                            log.debug("[RAG-EMBED] suppressed: %s", _e)
                    return emb, fallback
            except Exception:
                continue
        return None


def batch_embed(texts: List[str], provider: Optional[str] = None, conn: Optional[sqlite3.Connection] = None) -> List[Optional[Tuple[List[float], str]]]:
    """Batch embed texts. Returns list of (embedding, provider) or None for failures."""
    if not texts:
        return []

    if provider is None:
        provider = get_available_provider()
    if provider is None:
        return [None] * len(texts)

    api_key = _get_api_key(provider)
    if not api_key:
        return [None] * len(texts)

    # Check cache first
    results: List[Optional[Tuple[List[float], str]]] = [None] * len(texts)
    uncached_indices = []
    uncached_texts = []

    for i, text in enumerate(texts):
        text_hash = hashlib.sha256(text.encode()).hexdigest()[:32]
        if conn:
            try:
                row = conn.execute(
                    "SELECT embedding, provider FROM rag_embeddings WHERE chunk_hash=?",
                    (text_hash,),
                ).fetchone()
                if row:
                    results[i] = (json.loads(row[0]), row[1])
                    continue
            except Exception as _e:
                log.debug("[RAG-EMBED] suppressed: %s", _e)
        uncached_indices.append(i)
        uncached_texts.append(text)

    if not uncached_texts:
        return results

    try:
        fn = _EMBED_FNS.get(provider)
        if not fn:
            return results
        
        # Batch in groups of 100 (OpenAI limit is 2048, but keep reasonable)
        batch_size = 100
        for batch_start in range(0, len(uncached_texts), batch_size):
            batch = uncached_texts[batch_start:batch_start + batch_size]
            batch_idx = uncached_indices[batch_start:batch_start + batch_size]
            
            embeddings = fn(batch, api_key)
            
            for j, (idx, text) in enumerate(zip(batch_idx, batch)):
                if j < len(embeddings):
                    emb = embeddings[j]
                    results[idx] = (emb, provider)
                    # Cache
                    if conn:
                        try:
                            text_hash = hashlib.sha256(text.encode()).hexdigest()[:32]
                            conn.execute(
                                "INSERT OR REPLACE INTO rag_embeddings (chunk_hash, embedding, provider, dimensions) VALUES (?,?,?,?)",
                                (text_hash, json.dumps(emb), provider, len(emb)),
                            )
                        except Exception as _e:
                            log.debug("[RAG-EMBED] suppressed: %s", _e)
            
        if conn:
            try:
                conn.commit()
            except Exception as _e:
                log.debug("[RAG-EMBED] suppressed: %s", _e)
        
        embedded_count = sum(1 for r in results if r is not None)
        log.info(f"[RAG] Embedded {embedded_count} chunks via {provider}")
        
    except Exception as e:
        log.warning(f"[RAG] Batch embedding failed via {provider}: {e}")

    return results


def cosine_similarity_vec(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two dense float vectors. Pure Python."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for i in range(len(a)):
        dot += a[i] * b[i]
        norm_a += a[i] * a[i]
        norm_b += b[i] * b[i]
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a ** 0.5 * norm_b ** 0.5)
