"""Tests for Life Dashboard."""
import json
import os
import sys
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestLifeDashboard(unittest.TestCase):

    def _make_dashboard(self):
        from salmalm.features.dashboard_life import LifeDashboard
        return LifeDashboard()

    def test_generate_dashboard_keys(self):
        d = self._make_dashboard()
        result = d.generate_dashboard()
        for key in ('finance', 'calendar', 'tasks', 'habits', 'thoughts',
                     'mood', 'productivity', 'links', 'generated_at'):
            self.assertIn(key, result)

    def test_finance_summary_empty(self):
        d = self._make_dashboard()
        fin = d._get_finance_summary()
        self.assertIn('total_expense', fin)
        self.assertIn('by_category', fin)
        self.assertIsInstance(fin['by_category'], dict)

    def test_pomodoro_stats_structure(self):
        d = self._make_dashboard()
        stats = d._get_pomodoro_stats()
        self.assertIn('total', stats)
        self.assertIn('completed', stats)
        self.assertIn('rate', stats)

    def test_text_summary_full(self):
        d = self._make_dashboard()
        text = d.text_summary()
        self.assertIn('Life Dashboard', text)

    def test_text_summary_finance(self):
        d = self._make_dashboard()
        text = d.text_summary('finance')
        self.assertTrue('재정' in text or '지출' in text or '💰' in text)

    def test_text_summary_week(self):
        d = self._make_dashboard()
        text = d.text_summary('week')
        self.assertIn('주간', text)

    def test_render_html(self):
        d = self._make_dashboard()
        html = d.render_html()
        self.assertIn('<!DOCTYPE html>', html)
        self.assertIn('Life Dashboard', html)
        self.assertIn('setTimeout', html)  # auto-refresh

    def test_render_html_responsive(self):
        d = self._make_dashboard()
        html = d.render_html()
        self.assertIn('viewport', html)
        self.assertIn('grid', html)

    def test_recent_thoughts_returns_list(self):
        d = self._make_dashboard()
        result = d._get_recent_thoughts()
        self.assertIsInstance(result, list)

    def test_saved_links_returns_list(self):
        d = self._make_dashboard()
        result = d._get_saved_links()
        self.assertIsInstance(result, list)


class TestProactiveDigest(unittest.TestCase):

    def test_morning_digest(self):
        from salmalm.features.dashboard_life import ProactiveDigest
        digest = ProactiveDigest()
        text = digest.morning_digest()
        self.assertIn('아침', text)

    def test_evening_digest(self):
        from salmalm.features.dashboard_life import ProactiveDigest
        digest = ProactiveDigest()
        text = digest.evening_digest()
        self.assertIn('하루', text)

    def test_should_send_morning(self):
        from salmalm.features.dashboard_life import ProactiveDigest
        digest = ProactiveDigest()
        self.assertEqual(digest.should_send(8), 'morning')

    def test_should_send_evening(self):
        from salmalm.features.dashboard_life import ProactiveDigest
        digest = ProactiveDigest()
        self.assertEqual(digest.should_send(20), 'evening')

    def test_should_send_none(self):
        from salmalm.features.dashboard_life import ProactiveDigest
        digest = ProactiveDigest()
        self.assertIsNone(digest.should_send(12))


if __name__ == '__main__':
    unittest.main()
