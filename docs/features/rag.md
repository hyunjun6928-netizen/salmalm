# RAG & Knowledge Base
# RAG 및 지식 베이스

## Overview / 개요

SalmAlm includes a built-in RAG (Retrieval-Augmented Generation) system with vector search for long-term knowledge storage.

SalmAlm은 장기 지식 저장을 위한 벡터 검색 기능을 갖춘 내장 RAG(검색 증강 생성) 시스템을 포함합니다.

## Features / 기능

- **Vector embeddings** stored in SQLite (`rag.db`) / SQLite에 벡터 임베딩 저장
- **Semantic search** across all stored documents / 모든 저장 문서에 대한 시맨틱 검색
- **Auto-indexing** of notes and saved links / 메모 및 저장 링크 자동 인덱싱
- **File indexing** via `file_index` tool / `file_index` 도구를 통한 파일 인덱싱

## Usage / 사용법

The AI automatically uses RAG search when it needs context from your knowledge base.

AI는 지식 베이스의 컨텍스트가 필요할 때 자동으로 RAG 검색을 사용합니다.

Tools: `rag_search`, `memory_write`, `memory_search`, `note`, `save_link`
