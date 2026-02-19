"""Tests for Workflow Engine."""
import json
import os
import sys
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from salmalm.workflow import (
    WorkflowEngine, _substitute, _substitute_params, _eval_condition,
    handle_workflow_command, WORKFLOWS_DIR
)


class TestVariableSubstitution(unittest.TestCase):

    def test_simple_substitution(self):
        ctx = {'step1': {'result': 'hello', 'count': 5}}
        self.assertEqual(_substitute('{{step1.result}}', ctx), 'hello')

    def test_multiple_substitutions(self):
        ctx = {'a': {'result': 'X'}, 'b': {'result': 'Y'}}
        self.assertEqual(_substitute('{{a.result}} and {{b.result}}', ctx), 'X and Y')

    def test_missing_var(self):
        self.assertEqual(_substitute('{{missing.result}}', {}), '{{missing.result}}')

    def test_substitute_params(self):
        ctx = {'s1': {'result': 'data'}}
        params = {'msg': 'Got: {{s1.result}}', 'count': 5}
        result = _substitute_params(params, ctx)
        self.assertEqual(result['msg'], 'Got: data')
        self.assertEqual(result['count'], 5)


class TestConditionEval(unittest.TestCase):

    def test_greater_than(self):
        self.assertTrue(_eval_condition('5 > 0', {}))

    def test_less_than(self):
        self.assertFalse(_eval_condition('0 > 5', {}))

    def test_equal(self):
        self.assertTrue(_eval_condition('3 == 3', {}))

    def test_with_substitution(self):
        ctx = {'s': {'count': '10'}}
        self.assertTrue(_eval_condition('{{s.count}} > 0', ctx))


class TestWorkflowEngine(unittest.TestCase):

    def setUp(self):
        self.orig_dir = WORKFLOWS_DIR
        self.tmpdir = tempfile.mkdtemp()
        # Patch WORKFLOWS_DIR
        import salmalm.workflow as wm
        wm.WORKFLOWS_DIR = Path(self.tmpdir)
        wm.WORKFLOW_LOG_DIR = Path(self.tmpdir) / 'logs'
        self.engine = WorkflowEngine(tool_executor=lambda tool, params: f'result_{tool}')

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        import salmalm.workflow as wm
        wm.WORKFLOWS_DIR = self.orig_dir
        wm.WORKFLOW_LOG_DIR = self.orig_dir / 'logs'

    def test_save_and_get(self):
        wf = {'name': 'test1', 'steps': [{'id': 's1', 'tool': 'echo', 'params': {}}]}
        self.engine.save_workflow(wf)
        loaded = self.engine.get_workflow('test1')
        self.assertEqual(loaded['name'], 'test1')

    def test_list_workflows(self):
        self.engine.save_workflow({'name': 'wf1', 'steps': [], 'trigger': {'type': 'manual'}})
        self.engine.save_workflow({'name': 'wf2', 'steps': [{'id': 's'}], 'trigger': {}})
        wfs = self.engine.list_workflows()
        names = [w['name'] for w in wfs]
        self.assertIn('wf1', names)
        self.assertIn('wf2', names)

    def test_delete_workflow(self):
        self.engine.save_workflow({'name': 'del_me', 'steps': []})
        result = self.engine.delete_workflow('del_me')
        self.assertIn('삭제', result)
        self.assertIsNone(self.engine.get_workflow('del_me'))

    def test_execute_simple(self):
        wf = {
            'name': 'simple',
            'steps': [{'id': 's1', 'tool': 'echo', 'params': {'msg': 'hi'}}],
            'on_error': 'stop',
        }
        result = self.engine.execute(wf)
        self.assertTrue(result['success'])
        self.assertEqual(len(result['results']), 1)

    def test_execute_with_condition_false(self):
        wf = {
            'name': 'cond',
            'steps': [
                {'id': 's1', 'tool': 'echo', 'params': {}},
                {'id': 's2', 'tool': 'echo', 'params': {}, 'if': '{{s1.count}} > 5'},
            ],
        }
        result = self.engine.execute(wf)
        self.assertTrue(any('skipped' in str(r.get('result', '')) for r in result['results']))

    def test_execute_error_stop(self):
        def failing_executor(tool, params):
            raise RuntimeError('fail')
        engine = WorkflowEngine(tool_executor=failing_executor)
        wf = {
            'name': 'fail',
            'steps': [{'id': 's1', 'tool': 'x', 'params': {}}, {'id': 's2', 'tool': 'y', 'params': {}}],
            'on_error': 'stop',
        }
        result = engine.execute(wf)
        self.assertFalse(result['success'])
        # Should stop after first failure
        self.assertEqual(len(result['results']), 1)

    def test_get_presets(self):
        presets = self.engine.get_presets()
        self.assertTrue(len(presets) >= 3)
        names = [p['name'] for p in presets]
        self.assertIn('morning_briefing', names)

    def test_install_preset(self):
        result = self.engine.install_preset('morning_briefing')
        self.assertIn('저장', result)

    def test_get_logs_empty(self):
        logs = self.engine.get_logs('nonexistent')
        self.assertEqual(logs, [])

    def test_run_nonexistent(self):
        result = self.engine.run('no_such_workflow')
        self.assertFalse(result['success'])


class TestWorkflowCommands(unittest.TestCase):

    def test_command_list(self):
        result = handle_workflow_command('/workflow list')
        self.assertIsInstance(result, str)

    def test_command_presets(self):
        result = handle_workflow_command('/workflow presets')
        self.assertIn('프리셋', result)


if __name__ == '__main__':
    unittest.main()
