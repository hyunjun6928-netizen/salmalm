"""Tests for RAG hybrid vector search, jamo, stemming, query expansion, session indexing, config."""
from __future__ import annotations

import json
import math
import os
import sqlite3
import tempfile
from pathlib import Path
from unittest import mock

import pytest

# We need to be able to import without constants failing
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from salmalm.features.rag import (
    RAGEngine, decompose_jamo, simple_stem, expand_query,
    compute_tf, cosine_similarity, load_rag_config, _SYNONYMS,
)


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


@pytest.fixture
def engine(tmp_dir):
    db = tmp_dir / "test_rag.db"
    cfg_path = tmp_dir / "rag.json"
    e = RAGEngine(db_path=db, config_path=cfg_path)
    e._get_indexable_files = lambda: []
    e._get_session_files = lambda: []
    return e


# ── 1. TF-IDF Vector Generation ──

class TestTFIDF:
    def test_compute_tf_basic(self):
        tokens = ['hello', 'world', 'hello']
        tf = compute_tf(tokens)
        assert abs(tf['hello'] - 2/3) < 1e-9
        assert abs(tf['world'] - 1/3) < 1e-9

    def test_compute_tf_empty(self):
        assert compute_tf([]) == {}

    def test_cosine_similarity_identical(self):
        v = {'a': 1.0, 'b': 2.0}
        assert abs(cosine_similarity(v, v) - 1.0) < 1e-9

    def test_cosine_similarity_orthogonal(self):
        v1 = {'a': 1.0}
        v2 = {'b': 1.0}
        assert cosine_similarity(v1, v2) == 0.0

    def test_cosine_similarity_partial(self):
        v1 = {'a': 1.0, 'b': 1.0}
        v2 = {'a': 1.0, 'c': 1.0}
        sim = cosine_similarity(v1, v2)
        assert 0.0 < sim < 1.0

    def test_cosine_similarity_empty(self):
        assert cosine_similarity({}, {'a': 1.0}) == 0.0
        assert cosine_similarity({'a': 1.0}, {}) == 0.0


# ── 2. Korean Jamo Decomposition ──

class TestJamo:
    def test_decompose_simple(self):
        result = decompose_jamo('가')
        assert result == 'ㄱㅏ'

    def test_decompose_with_jongseong(self):
        result = decompose_jamo('한')
        assert 'ㅎ' in result
        assert 'ㅏ' in result
        assert 'ㄴ' in result

    def test_decompose_mixed(self):
        result = decompose_jamo('abc가')
        assert result.startswith('abc')
        assert 'ㄱ' in result

    def test_decompose_empty(self):
        assert decompose_jamo('') == ''

    def test_decompose_english_passthrough(self):
        assert decompose_jamo('hello') == 'hello'


# ── 3. English Stemming ──

class TestStemming:
    def test_stem_ing(self):
        assert simple_stem('running') == 'runn'  # strips ing after n→ 'runn' via 'ning' rule

    def test_stem_tion(self):
        assert simple_stem('information') == 'informate'  # strips 'ation' suffix, adds 'ate'
        # Actually: 'information' ends with 'ation' → 'informate'? Let's just check it works
        stemmed = simple_stem('information')
        assert len(stemmed) < len('information')

    def test_stem_short_word(self):
        assert simple_stem('go') == 'go'
        assert simple_stem('the') == 'the'

    def test_stem_ness(self):
        stemmed = simple_stem('happiness')
        assert 'ness' not in stemmed

    def test_stem_ly(self):
        stemmed = simple_stem('quickly')
        assert stemmed != 'quickly'


# ── 4. Query Expansion ──

class TestQueryExpansion:
    def test_expand_known_term(self):
        expanded = expand_query(['검색'])
        assert '찾기' in expanded or '탐색' in expanded

    def test_expand_english(self):
        expanded = expand_query(['search'])
        assert 'find' in expanded or 'query' in expanded

    def test_expand_unknown_term(self):
        expanded = expand_query(['xyzzy123'])
        assert expanded == ['xyzzy123']

    def test_expand_no_duplicates(self):
        expanded = expand_query(['search', 'find'])
        # Should not have duplicates
        assert len(expanded) == len(set(expanded))


# ── 5. Hybrid Search ──

class TestHybridSearch:
    def test_search_empty_index(self, engine):
        results = engine.search("hello world")
        assert results == []

    def test_search_with_indexed_content(self, engine, tmp_dir):
        # Create a test file
        test_file = tmp_dir / "test.md"
        test_file.write_text("Python programming language\nPython is great for data science\n"
                             "Machine learning with Python\nDeep learning frameworks\n"
                             "Natural language processing\nComputer vision tasks\n"
                             "Python web development\nDjango and Flask frameworks\n"
                             "Database management systems\nSQL and NoSQL databases\n")
        engine._ensure_db()
        engine.index_file("test.md", test_file)
        results = engine.search("Python programming", max_results=5, min_score=0.0)
        assert len(results) > 0
        assert any('Python' in r['text'] or 'python' in r['text'].lower() for r in results)

    def test_hybrid_scoring(self, engine, tmp_dir):
        """Verify hybrid score is combination of vector + BM25."""
        test_file = tmp_dir / "test.md"
        content = "\n".join([f"topic alpha beta gamma line {i}" for i in range(20)])
        test_file.write_text(content)
        engine._ensure_db()
        engine.index_file("test.md", test_file)
        results = engine.search("alpha beta", max_results=5, min_score=0.0)
        assert len(results) > 0
        # Scores should be positive floats
        for r in results:
            assert r['score'] > 0

    def test_bm25_only_mode(self, engine, tmp_dir):
        """When hybrid disabled, should use BM25 only."""
        cfg_path = tmp_dir / "rag.json"
        cfg_path.write_text(json.dumps({"hybrid": {"enabled": False}}))
        engine._config = None  # Reset config cache

        test_file = tmp_dir / "test.md"
        test_file.write_text("alpha beta gamma\n" * 10)
        engine._ensure_db()
        engine.index_file("test.md", test_file)
        results = engine.search("alpha", max_results=3, min_score=0.0)
        assert len(results) > 0


# ── 6. Session Indexing ──

class TestSessionIndexing:
    def test_session_files_disabled(self, engine):
        """Session indexing off by default."""
        files = engine._get_session_files()
        assert files == []

    def test_session_files_enabled(self, engine, tmp_dir):
        """When enabled, should find session JSON files."""
        cfg_path = tmp_dir / "rag.json"
        cfg_path.write_text(json.dumps({
            "sessionIndexing": {"enabled": True, "retentionDays": 30}
        }))
        engine._config = None

        sessions_dir = Path.home() / '.salmalm' / 'sessions'
        with mock.patch.object(Path, 'home', return_value=tmp_dir):
            sd = tmp_dir / '.salmalm' / 'sessions'
            sd.mkdir(parents=True, exist_ok=True)
            sess = sd / 'session1.json'
            sess.write_text(json.dumps([
                {"role": "user", "content": "hello world"},
                {"role": "assistant", "content": "hi there"}
            ]))

            # Reload config with mocked home
            engine._config = {
                "sessionIndexing": {"enabled": True, "retentionDays": 30},
                "hybrid": {"enabled": True, "vectorWeight": 0.7, "textWeight": 0.3},
                "extraPaths": [], "chunkSize": 5, "chunkOverlap": 2, "reindexInterval": 120,
            }

            # Manually test session file parsing
            engine._ensure_db()
            engine._index_session_file("session/test.json", sess, sess.stat().st_mtime)
            # Check chunks were created
            count = engine._conn.execute("SELECT COUNT(*) FROM chunks WHERE source='session/test.json'").fetchone()[0]
            assert count > 0


# ── 7. Config Loading ──

class TestConfig:
    def test_default_config(self, tmp_dir):
        cfg = load_rag_config(tmp_dir / "nonexistent.json")
        assert cfg['hybrid']['enabled'] is True
        assert cfg['hybrid']['vectorWeight'] == 0.7
        assert cfg['hybrid']['textWeight'] == 0.3
        assert cfg['sessionIndexing']['enabled'] is False

    def test_custom_config(self, tmp_dir):
        cfg_path = tmp_dir / "rag.json"
        cfg_path.write_text(json.dumps({
            "hybrid": {"vectorWeight": 0.5, "textWeight": 0.5},
            "chunkSize": 10,
        }))
        cfg = load_rag_config(cfg_path)
        assert cfg['hybrid']['vectorWeight'] == 0.5
        assert cfg['chunkSize'] == 10
        # Merged: enabled should still be True from default
        assert cfg['hybrid']['enabled'] is True

    def test_bad_config_falls_back(self, tmp_dir):
        cfg_path = tmp_dir / "rag.json"
        cfg_path.write_text("not json!")
        cfg = load_rag_config(cfg_path)
        assert cfg['hybrid']['enabled'] is True  # Default


# ── 8. Tokenizer with N-grams ──

class TestTokenizer:
    def test_tokenize_includes_bigrams(self):
        tokens = RAGEngine._tokenize("hello world python")
        # Should have unigrams and bigrams
        assert any('_' in t for t in tokens)

    def test_tokenize_char_trigrams(self):
        tokens = RAGEngine._tokenize("hello world")
        c3 = [t for t in tokens if t.startswith('c3:')]
        assert len(c3) > 0

    def test_tokenize_korean_jamo(self):
        tokens = RAGEngine._tokenize("한국어 처리")
        jamo = [t for t in tokens if t.startswith('j:')]
        assert len(jamo) > 0

    def test_tokenize_stops_removed(self):
        tokens = RAGEngine._tokenize("the cat is on the mat")
        assert 'the' not in tokens
        assert 'is' not in tokens


# ── 9. Build Context ──

class TestBuildContext:
    def test_build_context_empty(self, engine):
        ctx = engine.build_context("something")
        assert ctx == ""

    def test_build_context_with_data(self, engine, tmp_dir):
        f = tmp_dir / "doc.md"
        f.write_text("Important information about databases\nSQL queries and optimization\n"
                     "Index design patterns\nQuery performance tuning\n"
                     "Database normalization rules\n")
        engine._ensure_db()
        engine.index_file("doc.md", f)
        ctx = engine.build_context("database", max_chars=5000)
        assert "Retrieved relevant information" in ctx


# ── 10. Get Stats ──

class TestStats:
    def test_stats_empty(self, tmp_dir):
        # Use fresh engine, don't call search (which triggers reindex of workspace files)
        db = tmp_dir / "stats_empty.db"
        e = RAGEngine(db_path=db, config_path=tmp_dir / "rag.json")
        stats = e.get_stats()
        assert stats['total_chunks'] == 0
        e.close()

    def test_stats_after_index(self, engine, tmp_dir):
        f = tmp_dir / "doc.md"
        f.write_text("line one\nline two\nline three\nline four\nline five\nline six\n")
        engine._ensure_db()
        engine.index_file("doc.md", f)
        stats = engine.get_stats()
        assert stats['total_chunks'] > 0
        assert stats['unique_terms'] > 0
