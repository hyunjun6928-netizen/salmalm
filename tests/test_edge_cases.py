"""Tests for edge_cases module — features from LibreChat, Open WebUI, LobeChat, BIG-AGI."""
import json
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestAbortController(unittest.TestCase):
    """Test abort generation (생성 중지)."""

    def test_abort_flow(self):
        from salmalm.features.edge_cases import AbortController
        ac = AbortController()
        self.assertFalse(ac.is_aborted('s1'))
        ac.set_abort('s1')
        self.assertTrue(ac.is_aborted('s1'))
        ac.clear('s1')
        self.assertFalse(ac.is_aborted('s1'))

    def test_partial_response(self):
        from salmalm.features.edge_cases import AbortController
        ac = AbortController()
        ac.save_partial('s1', 'Hello wor')
        self.assertEqual(ac.get_partial('s1'), 'Hello wor')
        self.assertIsNone(ac.get_partial('s1'))  # cleared after get

    def test_multiple_sessions(self):
        from salmalm.features.edge_cases import AbortController
        ac = AbortController()
        ac.set_abort('a')
        ac.set_abort('b')
        self.assertTrue(ac.is_aborted('a'))
        self.assertTrue(ac.is_aborted('b'))
        ac.clear('a')
        self.assertFalse(ac.is_aborted('a'))
        self.assertTrue(ac.is_aborted('b'))


class TestPromptVariables(unittest.TestCase):
    """Test system prompt variable substitution (시스템 프롬프트 변수)."""

    def test_basic_substitution(self):
        from salmalm.features.edge_cases import substitute_prompt_variables
        result = substitute_prompt_variables(
            'Today is {{date}}, session {{session}}',
            session_id='test-123')
        self.assertNotIn('{{date}}', result)
        self.assertIn('test-123', result)
        self.assertNotIn('{{session}}', result)

    def test_all_variables(self):
        from salmalm.features.edge_cases import substitute_prompt_variables
        template = '{{date}} {{time}} {{user}} {{model}} {{session}} {{version}} {{weekday}} {{weekday_kr}}'
        result = substitute_prompt_variables(template, session_id='s', model='opus', user='bob')
        self.assertNotIn('{{', result)

    def test_no_variables(self):
        from salmalm.features.edge_cases import substitute_prompt_variables
        text = 'Hello world, no vars here'
        self.assertEqual(substitute_prompt_variables(text), text)


class TestSmartPaste(unittest.TestCase):
    """Test smart paste detection (스마트 붙여넣기)."""

    def test_url_detection(self):
        from salmalm.features.edge_cases import detect_paste_type
        result = detect_paste_type('https://example.com/page')
        self.assertEqual(result['type'], 'url')
        self.assertEqual(result['suggestion'], 'fetch_content')

    def test_code_detection_python(self):
        from salmalm.features.edge_cases import detect_paste_type
        code = 'def hello():\n    print("hello world")'
        result = detect_paste_type(code)
        self.assertEqual(result['type'], 'code')
        self.assertEqual(result['language'], 'python')

    def test_json_detection(self):
        from salmalm.features.edge_cases import detect_paste_type
        result = detect_paste_type('{"key": "value", "num": 42}')
        self.assertEqual(result['type'], 'code')
        self.assertEqual(result['language'], 'json')

    def test_plain_text(self):
        from salmalm.features.edge_cases import detect_paste_type
        result = detect_paste_type('Hello, this is a normal message')
        self.assertEqual(result['type'], 'text')
        self.assertIsNone(result['suggestion'])


class TestFileUpload(unittest.TestCase):
    """Test enhanced file upload (파일 업로드 강화)."""

    def test_validate_allowed(self):
        from salmalm.features.edge_cases import validate_upload
        ok, err = validate_upload('test.py', 1000)
        self.assertTrue(ok)

    def test_validate_blocked(self):
        from salmalm.features.edge_cases import validate_upload
        ok, err = validate_upload('test.exe', 1000)
        self.assertFalse(ok)
        self.assertIn('not allowed', err)

    def test_validate_too_large(self):
        from salmalm.features.edge_cases import validate_upload
        ok, err = validate_upload('test.txt', 60 * 1024 * 1024)
        self.assertFalse(ok)
        self.assertIn('too large', err)

    def test_validate_empty(self):
        from salmalm.features.edge_cases import validate_upload
        ok, err = validate_upload('test.txt', 0)
        self.assertFalse(ok)

    def test_process_txt(self):
        from salmalm.features.edge_cases import process_uploaded_file
        result = process_uploaded_file('hello.txt', b'Hello world content')
        self.assertIn('hello.txt', result)
        self.assertIn('Hello world content', result)

    def test_process_json(self):
        from salmalm.features.edge_cases import process_uploaded_file
        data = json.dumps({'key': 'value'}).encode()
        result = process_uploaded_file('data.json', data)
        self.assertIn('data.json', result)
        self.assertIn('key', result)

    def test_process_csv(self):
        from salmalm.features.edge_cases import process_uploaded_file
        csv_data = b'name,age\nAlice,30\nBob,25'
        result = process_uploaded_file('data.csv', csv_data)
        self.assertIn('data.csv', result)
        self.assertIn('Alice', result)

    def test_process_python(self):
        from salmalm.features.edge_cases import process_uploaded_file
        result = process_uploaded_file('script.py', b'print("hello")')
        self.assertIn('```py', result)

    def test_process_pdf_empty(self):
        from salmalm.features.edge_cases import extract_pdf_text
        result = extract_pdf_text(b'not a real pdf')
        self.assertIn('PDF', result)  # Should return error message


class TestSummaryCard(unittest.TestCase):
    """Test conversation summary card (대화 요약 카드)."""

    def test_no_summary_for_short(self):
        from salmalm.features.edge_cases import get_summary_card
        # New session with < 3 messages should return None
        result = get_summary_card('nonexistent_session_xyz')
        self.assertIsNone(result)


class TestAllowedExtensions(unittest.TestCase):
    """Test allowed upload extensions list."""

    def test_all_specified_types(self):
        from salmalm.features.edge_cases import ALLOWED_UPLOAD_EXTENSIONS
        expected = {'png', 'jpg', 'gif', 'webp', 'pdf', 'txt', 'csv', 'json', 'md', 'py', 'js'}
        for ext in expected:
            self.assertIn(ext, ALLOWED_UPLOAD_EXTENSIONS, f'{ext} should be allowed')


if __name__ == '__main__':
    unittest.main()
