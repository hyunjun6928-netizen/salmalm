"""Tests for structured LLM output (LLMTask)."""
import json
import pytest
from salmalm.llm_task import _validate_schema, _extract_json, LLMTask


def test_validate_basic_types():
    assert _validate_schema('hello', {'type': 'string'}) == []
    assert _validate_schema(42, {'type': 'integer'}) == []
    assert _validate_schema(3.14, {'type': 'number'}) == []
    assert _validate_schema(True, {'type': 'boolean'}) == []
    assert len(_validate_schema('hello', {'type': 'integer'})) > 0


def test_validate_object_required():
    schema = {'type': 'object', 'required': ['name', 'age'],
              'properties': {'name': {'type': 'string'}, 'age': {'type': 'integer'}}}
    assert _validate_schema({'name': 'test', 'age': 10}, schema) == []
    errors = _validate_schema({'name': 'test'}, schema)
    assert any('age' in e for e in errors)


def test_validate_array():
    schema = {'type': 'array', 'items': {'type': 'string'}}
    assert _validate_schema(['a', 'b'], schema) == []
    errors = _validate_schema(['a', 123], schema)
    assert len(errors) > 0


def test_validate_enum():
    schema = {'type': 'string', 'enum': ['a', 'b', 'c']}
    assert _validate_schema('a', schema) == []
    assert len(_validate_schema('d', schema)) > 0


def test_validate_min_max():
    schema = {'type': 'integer', 'minimum': 0, 'maximum': 100}
    assert _validate_schema(50, schema) == []
    assert len(_validate_schema(-1, schema)) > 0
    assert len(_validate_schema(101, schema)) > 0


def test_extract_json_code_fence():
    text = 'Here is the result:\n```json\n{"key": "value"}\n```\nDone.'
    assert _extract_json(text) == '{"key": "value"}'


def test_extract_json_raw():
    text = '{"key": "value"}'
    assert _extract_json(text) == '{"key": "value"}'


def test_extract_json_with_prefix():
    text = 'Sure, here you go: {"key": "value"}'
    result = _extract_json(text)
    assert json.loads(result) == {"key": "value"}
