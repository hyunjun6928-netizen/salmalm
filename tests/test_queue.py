"""Tests for message queue feature."""
import unittest
from salmalm.features.queue import MessageQueue, get_queue, set_queue_mode, queue_status, QueueMode


class TestMessageQueue(unittest.TestCase):
    def test_collect_mode(self):
        q = MessageQueue(mode='collect')
        q.is_processing = True
        r1 = q.enqueue('msg1')
        self.assertEqual(r1['action'], 'queued')
        r2 = q.enqueue('msg2')
        self.assertEqual(r2['position'], 2)
        msgs = q.drain()
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0].text, 'msg1')

    def test_steer_mode(self):
        q = MessageQueue(mode='steer')
        q.is_processing = True
        q.enqueue('msg1')
        q.enqueue('msg2')
        msgs = q.drain()
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].text, 'msg2')

    def test_followup_mode(self):
        q = MessageQueue(mode='followup')
        q.is_processing = True
        q.enqueue('msg1')
        q.enqueue('msg2')
        ctx = q.drain_as_context()
        self.assertIn('[follow-up] msg1', ctx)
        self.assertIn('[follow-up] msg2', ctx)

    def test_steer_backlog(self):
        q = MessageQueue(mode='steer-backlog')
        q.is_processing = True
        q.enqueue('msg1')
        q.enqueue('msg2')  # msg1 goes to backlog
        msgs = q.drain()
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].text, 'msg2')
        bl = q.get_backlog()
        self.assertEqual(len(bl), 1)
        self.assertEqual(bl[0].text, 'msg1')

    def test_interrupt_mode(self):
        q = MessageQueue(mode='interrupt')
        q.is_processing = True
        r = q.enqueue('urgent')
        self.assertEqual(r['action'], 'interrupt')
        self.assertTrue(q.cancel_requested)

    def test_not_processing_returns_process(self):
        q = MessageQueue(mode='collect')
        r = q.enqueue('msg')
        self.assertEqual(r['action'], 'process')

    def test_mode_change(self):
        q = MessageQueue(mode='collect')
        q.mode = 'steer'
        self.assertEqual(q.mode, 'steer')

    def test_invalid_mode(self):
        with self.assertRaises(ValueError):
            MessageQueue(mode='invalid')

    def test_clear(self):
        q = MessageQueue(mode='collect')
        q.is_processing = True
        q.enqueue('msg')
        q.clear()
        self.assertEqual(q.pending_count, 0)

    def test_status(self):
        q = MessageQueue(mode='collect')
        st = q.status()
        self.assertEqual(st['mode'], 'collect')
        self.assertEqual(st['pending'], 0)

    def test_global_get_queue(self):
        q1 = get_queue('test-session')
        q2 = get_queue('test-session')
        self.assertIs(q1, q2)

    def test_set_queue_mode_global(self):
        result = set_queue_mode('test-mode-session', 'steer')
        self.assertIn('steer', result)

    def test_queue_status_global(self):
        st = queue_status('test-status-session')
        self.assertIn('mode', st)


if __name__ == '__main__':
    unittest.main()
