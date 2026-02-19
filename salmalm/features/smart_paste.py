"""Smart Paste (스마트 붙여넣기) — BIG-AGI style."""
from __future__ import annotations

import json
import re
from typing import Any, Dict


def detect_paste_type(text: str) -> Dict[str, Any]:
    text = text.strip()

    url_pattern = re.compile(r'^https?://\S+$')
    if url_pattern.match(text):
        return {
            'type': 'url',
            'original': text,
            'suggestion': 'fetch_content',
            'message': '🔗 URL detected. Fetch page content? / URL이 감지되었습니다. 페이지 내용을 가져올까요?'
        }

    lines = text.split('\n')
    urls = [l.strip() for l in lines if url_pattern.match(l.strip())]
    if len(urls) > 1:
        return {
            'type': 'urls',
            'original': text,
            'urls': urls,
            'suggestion': 'fetch_all',
            'message': f'🔗 {len(urls)} URLs detected. / {len(urls)}개의 URL이 감지되었습니다.'
        }

    code_indicators = {
        'python': [r'^\s*(import |from .+ import |def |class |if __name__)', r'print\('],
        'javascript': [r'^\s*(const |let |var |function |import |export |=>)', r'console\.log'],
        'typescript': [r'^\s*(interface |type |const .+:.+= |import .+ from)', r': string|: number|: boolean'],
        'html': [r'<(!DOCTYPE|html|head|body|div|span|script)', r'</\w+>'],
        'css': [r'\{[^}]*:[^}]*;\s*\}', r'\.([\w-]+)\s*\{'],
        'sql': [r'^\s*(SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER)\s', r'\bFROM\b.*\bWHERE\b'],
        'shell': [r'^#!/bin/(ba)?sh', r'^\s*(echo |export |alias |sudo )'],
        'json': [r'^\s*[\[{]', r'"[^"]+"\s*:\s*'],
        'yaml': [r'^\w+:\s*$', r'^\s*-\s+\w+'],
    }

    for lang, patterns in code_indicators.items():
        matches = sum(1 for p in patterns if re.search(p, text, re.MULTILINE | re.IGNORECASE))
        if matches >= 1 and len(text) > 20:
            if lang == 'json':
                try:
                    json.loads(text)
                    return {
                        'type': 'code', 'language': 'json',
                        'original': text,
                        'formatted': f'```json\n{text}\n```',
                        'suggestion': 'wrap_code',
                        'message': '📋 JSON detected. / JSON이 감지되었습니다.'
                    }
                except json.JSONDecodeError:
                    continue
            elif matches >= 1 and any(re.search(p, text, re.MULTILINE) for p in patterns):
                return {
                    'type': 'code', 'language': lang,
                    'original': text,
                    'formatted': f'```{lang}\n{text}\n```',
                    'suggestion': 'wrap_code',
                    'message': f'💻 {lang.title()} code detected. / {lang.title()} 코드가 감지되었습니다.'
                }

    return {
        'type': 'text',
        'original': text,
        'suggestion': None,
        'message': None
    }
