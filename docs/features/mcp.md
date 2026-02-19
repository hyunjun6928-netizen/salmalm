# MCP Integration
# MCP 통합

## Overview / 개요

SalmAlm implements the Model Context Protocol (MCP) as both server and client, enabling interoperability with other AI tools.

SalmAlm은 MCP(Model Context Protocol)를 서버와 클라이언트 모두로 구현하여 다른 AI 도구와의 상호 운용성을 제공합니다.

## MCP Server / MCP 서버

SalmAlm exposes its tools via JSON-RPC 2.0 stdio transport.

SalmAlm은 JSON-RPC 2.0 stdio 트랜스포트를 통해 도구를 노출합니다.

- `tools/list` — list available tools / 사용 가능한 도구 목록
- `tools/call` — execute a tool / 도구 실행
- `resources/list` — list resources / 리소스 목록
- `prompts/list` — list prompt templates / 프롬프트 템플릿 목록

## MCP Marketplace / MCP 마켓플레이스

Install and manage MCP servers from the marketplace:

마켓플레이스에서 MCP 서버를 설치하고 관리하세요:

```
/mcp catalog
/mcp install <server-name>
/mcp list
/mcp remove <server-name>
/mcp status
```
