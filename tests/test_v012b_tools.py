"""Tests for v0.12.1 additional tools: weather, rss, translate, qr_code + enhanced time parsing."""
import json
import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestWeatherTool(unittest.TestCase):
    """Test weather tool handler."""

    def test_missing_location(self):
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('weather', {'location': ''})
        self.assertIn('required', result)

    @patch('urllib.request.urlopen')
    def test_weather_short(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'Seoul: \xe2\x9b\x85 +5\xc2\xb0C 45% \xe2\x86\x92 10km/h'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('weather', {'location': 'Seoul', 'format': 'short'})
        self.assertIn('Seoul', result)

    @patch('urllib.request.urlopen')
    def test_weather_full_json(self, mock_urlopen):
        mock_data = {
            'current_condition': [{'temp_C': '5', 'FeelsLikeC': '2', 'humidity': '45',
                'weatherDesc': [{'value': 'Cloudy'}], 'windspeedKmph': '10',
                'winddir16Point': 'NW', 'uvIndex': '2', 'precipMM': '0', 'visibility': '10'}],
            'nearest_area': [{'areaName': [{'value': 'Seoul'}], 'country': [{'value': 'Korea'}]}],
            'weather': [{'date': '2026-02-20', 'maxtempC': '8', 'mintempC': '1',
                'hourly': [{'weatherDesc': [{'value': 'Sunny'}]}]}]
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_data).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('weather', {'location': 'Seoul', 'format': 'full'})
        self.assertIn('Seoul', result)
        self.assertIn('5°C', result)


class TestTranslateTool(unittest.TestCase):
    """Test translate tool handler."""

    def test_missing_args(self):
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('translate', {'text': '', 'target': 'en'})
        self.assertIn('required', result)

    def test_missing_target(self):
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('translate', {'text': 'hello', 'target': ''})
        self.assertIn('required', result)

    @patch('urllib.request.urlopen')
    def test_translate_ko_en(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps([[['Hello', '안녕하세요']], None, 'ko']).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('translate', {'text': '안녕하세요', 'target': 'en'})
        self.assertIn('Hello', result)


class TestRSSReaderTool(unittest.TestCase):
    """Test rss_reader tool handler."""

    def test_list_empty(self):
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('rss_reader', {'action': 'list'})
        self.assertTrue('feed' in result.lower() or 'Feed' in result)

    def test_subscribe(self):
        from salmalm.tools.tool_handlers import execute_tool, _feeds_file
        result = execute_tool('rss_reader', {
            'action': 'subscribe', 'url': 'https://example.com/rss', 'name': '_test_feed'})
        self.assertIn('Subscribed', result)
        # Cleanup
        execute_tool('rss_reader', {'action': 'unsubscribe', 'name': '_test_feed'})

    def test_unsubscribe_nonexistent(self):
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('rss_reader', {'action': 'unsubscribe', 'name': '_fake_feed_xyz'})
        self.assertIn('not found', result)

    def test_fetch_no_url_no_feeds(self):
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('rss_reader', {'action': 'fetch'})
        self.assertTrue('No' in result or 'error' in result.lower() or 'feed' in result.lower())

    @patch('urllib.request.urlopen')
    def test_parse_rss(self, mock_urlopen):
        from salmalm.tools.tool_handlers import _parse_rss
        xml = '''<?xml version="1.0"?>
        <rss version="2.0"><channel><title>Test</title>
        <item><title>Article 1</title><link>https://example.com/1</link>
        <pubDate>Thu, 20 Feb 2026</pubDate><description>Summary here</description></item>
        </channel></rss>'''
        articles = _parse_rss(xml)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]['title'], 'Article 1')

    @patch('urllib.request.urlopen')
    def test_parse_atom(self, mock_urlopen):
        from salmalm.tools.tool_handlers import _parse_rss
        xml = '''<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
        <entry><title>Atom Article</title>
        <link href="https://example.com/atom1"/>
        <published>2026-02-20T10:00:00Z</published>
        <summary>Atom summary</summary></entry>
        </feed>'''
        articles = _parse_rss(xml)
        self.assertEqual(len(articles), 1)
        self.assertIn('Atom', articles[0]['title'])


class TestQRCodeTool(unittest.TestCase):
    """Test qr_code tool handler."""

    def test_missing_data(self):
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('qr_code', {'data': ''})
        self.assertIn('required', result)

    @patch('urllib.request.urlopen')
    def test_generate_svg(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'<svg>mock qr</svg>'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        from salmalm.tools.tool_handlers import execute_tool
        result = execute_tool('qr_code', {'data': 'https://example.com', 'format': 'svg'})
        self.assertIn('QR code saved', result)


class TestEnhancedTimeParsing(unittest.TestCase):
    """Test enhanced natural language time parsing."""

    def test_korean_tomorrow(self):
        from salmalm.tools.tool_handlers import _parse_relative_time
        result = _parse_relative_time('내일 오후 3시')
        expected_day = (datetime.now() + timedelta(days=1)).day
        self.assertEqual(result.day, expected_day)
        self.assertEqual(result.hour, 15)

    def test_korean_tomorrow_morning(self):
        from salmalm.tools.tool_handlers import _parse_relative_time
        result = _parse_relative_time('내일 아침')
        expected_day = (datetime.now() + timedelta(days=1)).day
        self.assertEqual(result.day, expected_day)
        self.assertEqual(result.hour, 8)

    def test_korean_today_evening(self):
        from salmalm.tools.tool_handlers import _parse_relative_time
        result = _parse_relative_time('오늘 저녁 7시')
        self.assertEqual(result.day, datetime.now().day)
        self.assertEqual(result.hour, 19)

    def test_korean_day_after_tomorrow(self):
        from salmalm.tools.tool_handlers import _parse_relative_time
        result = _parse_relative_time('모레')
        expected_day = (datetime.now() + timedelta(days=2)).day
        self.assertEqual(result.day, expected_day)

    def test_korean_am_pm(self):
        from salmalm.tools.tool_handlers import _parse_relative_time
        result = _parse_relative_time('오전 10시 30분')
        self.assertEqual(result.hour, 10)
        self.assertEqual(result.minute, 30)

    def test_english_tomorrow_3pm(self):
        from salmalm.tools.tool_handlers import _parse_relative_time
        result = _parse_relative_time('tomorrow 3pm')
        expected_day = (datetime.now() + timedelta(days=1)).day
        self.assertEqual(result.day, expected_day)
        self.assertEqual(result.hour, 15)

    def test_relative_still_works(self):
        from salmalm.tools.tool_handlers import _parse_relative_time
        result = _parse_relative_time('45m')
        self.assertGreater(result, datetime.now() + timedelta(minutes=44))

    def test_iso_still_works(self):
        from salmalm.tools.tool_handlers import _parse_relative_time
        result = _parse_relative_time('2026-03-01T10:00:00')
        self.assertEqual(result.year, 2026)
        self.assertEqual(result.month, 3)


class TestToolCount(unittest.TestCase):
    """Verify updated tool count."""

    def test_tool_count(self):
        from salmalm.tools import TOOL_DEFINITIONS
        self.assertGreaterEqual(len(TOOL_DEFINITIONS), 43, "Should have at least 43 tools")

    def test_new_tools_present(self):
        from salmalm.tools import TOOL_DEFINITIONS
        names = {t['name'] for t in TOOL_DEFINITIONS}
        expected = {'weather', 'rss_reader', 'translate', 'qr_code'}
        self.assertTrue(expected.issubset(names), f'Missing: {expected - names}')


if __name__ == '__main__':
    unittest.main()
