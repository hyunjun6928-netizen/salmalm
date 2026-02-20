"""Structured LLM output — JSON Schema validated LLM calls.

구조화 LLM 출력 — JSON Schema 검증 기반 LLM 호출.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, List, Optional


def _validate_schema(data: Any, schema: dict) -> List[str]:
    """Minimal JSON Schema validator (stdlib only).

    Supports: type, required, properties, items, enum, minimum, maximum.
    Returns list of error strings (empty = valid).
    """
    errors = []
    s_type = schema.get('type')

    if s_type:
        type_map = {
            'string': str, 'integer': int, 'number': (int, float),
            'boolean': bool, 'array': list, 'object': dict, 'null': type(None),
        }
        expected = type_map.get(s_type)
        if expected and not isinstance(data, expected):
            # int is also valid for 'number'
            if not (s_type == 'number' and isinstance(data, (int, float))):
                errors.append(f'Expected {s_type}, got {type(data).__name__}')
                return errors

    if s_type == 'object' and isinstance(data, dict):
        for req in schema.get('required', []):
            if req not in data:
                errors.append(f'Missing required field: {req}')
        props = schema.get('properties', {})
        for key, prop_schema in props.items():
            if key in data:
                errors.extend(_validate_schema(data[key], prop_schema))

    if s_type == 'array' and isinstance(data, list):
        items_schema = schema.get('items')
        if items_schema:
            for i, item in enumerate(data):
                sub_errors = _validate_schema(item, items_schema)
                errors.extend(f'[{i}].{e}' for e in sub_errors)

    if 'enum' in schema and data not in schema['enum']:
        errors.append(f'Value {data!r} not in enum {schema["enum"]}')

    if 'minimum' in schema and isinstance(data, (int, float)):
        if data < schema['minimum']:
            errors.append(f'Value {data} < minimum {schema["minimum"]}')

    if 'maximum' in schema and isinstance(data, (int, float)):
        if data > schema['maximum']:
            errors.append(f'Value {data} > maximum {schema["maximum"]}')

    return errors


def _extract_json(text: str) -> str:
    """Extract JSON from LLM response (handles markdown code fences)."""
    # Try code fence first
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # Try raw JSON
    text = text.strip()
    # Find first { or [
    for i, c in enumerate(text):
        if c in ('{', '['):
            return text[i:]
    return text


class LLMTask:
    """JSON Schema 검증 기반 구조화 LLM 호출."""

    SYSTEM_PROMPT = (
        "You must respond with ONLY valid JSON. No explanations, no markdown, "
        "no text before or after the JSON. Output a single JSON object or array."
    )

    async def run(
        self,
        prompt: str,
        input_data: Any = None,
        schema: Optional[dict] = None,
        model: Optional[str] = None,
        max_tokens: int = 800,
        timeout: float = 30,
    ) -> dict:
        """LLM에 JSON-only 응답 요청, schema로 검증.

        Returns: {'result': <parsed>, 'raw': <str>, 'errors': [], 'retried': bool}
        """
        from salmalm.core.llm import call_llm

        user_content = prompt
        if input_data is not None:
            user_content += f"\n\nInput data:\n{json.dumps(input_data, ensure_ascii=False)}"

        if schema:
            user_content += f"\n\nRespond according to this JSON Schema:\n{json.dumps(schema, ensure_ascii=False)}"

        messages = [
            {'role': 'system', 'content': self.SYSTEM_PROMPT},
            {'role': 'user', 'content': user_content},
        ]

        kwargs = {'max_tokens': max_tokens}
        if model:
            kwargs['model'] = model

        # First attempt
        result = await asyncio.to_thread(call_llm, messages, **kwargs)
        raw = result.get('content', '')
        parsed, errors = self._parse_and_validate(raw, schema)

        if errors:
            # Retry once with error feedback
            retry_msg = (
                f"Your previous response had errors:\n"
                f"{chr(10).join(errors)}\n\n"
                f"Original response:\n{raw[:500]}\n\n"
                f"Please fix and respond with ONLY valid JSON."
            )
            messages.append({'role': 'assistant', 'content': raw})
            messages.append({'role': 'user', 'content': retry_msg})
            result = await asyncio.to_thread(call_llm, messages, **kwargs)
            raw2 = result.get('content', '')
            parsed2, errors2 = self._parse_and_validate(raw2, schema)
            if not errors2:
                return {'result': parsed2, 'raw': raw2, 'errors': [], 'retried': True}
            return {'result': parsed2 or parsed, 'raw': raw2, 'errors': errors2, 'retried': True}

        return {'result': parsed, 'raw': raw, 'errors': [], 'retried': False}

    def _parse_and_validate(self, raw: str, schema: Optional[dict]) -> tuple:
        """Parse JSON and validate against schema. Returns (parsed, errors)."""
        try:
            json_str = _extract_json(raw)
            parsed = json.loads(json_str)
        except (json.JSONDecodeError, ValueError) as e:
            return None, [f'JSON parse error: {e}']

        if schema:
            errors = _validate_schema(parsed, schema)
            if errors:
                return parsed, errors

        return parsed, []


# Singleton
llm_task = LLMTask()
