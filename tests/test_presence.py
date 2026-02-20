"""Tests for presence module."""
import sys
import os
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from salmalm.features.presence import (
    PresenceManager, PresenceEntry,
    ACTIVE_THRESHOLD, IDLE_THRESHOLD, DEFAULT_TTL,
)


class TestPresenceEntry(unittest.TestCase):
    def test_create_entry(self):
        e = PresenceEntry('inst1', host='localhost', ip='127.0.0.1', mode='web')
        self.assertEqual(e.instance_id, 'inst1')
        self.assertEqual(e.host, 'localhost')
        self.assertEqual(e.state, 'active')
        self.assertFalse(e.is_expired)

    def test_state_active(self):
        e = PresenceEntry('inst1')
        self.assertEqual(e.state, 'active')

    def test_state_idle(self):
        e = PresenceEntry('inst1')
        e.last_activity = time.time() - (ACTIVE_THRESHOLD + 10)
        self.assertEqual(e.state, 'idle')

    def test_state_stale(self):
        e = PresenceEntry('inst1')
        e.last_activity = time.time() - (IDLE_THRESHOLD + 10)
        self.assertEqual(e.state, 'stale')

    def test_is_expired(self):
        e = PresenceEntry('inst1')
        e.last_activity = time.time() - (DEFAULT_TTL + 10)
        self.assertTrue(e.is_expired)

    def test_touch(self):
        e = PresenceEntry('inst1', mode='web')
        old_time = e.last_activity
        time.sleep(0.01)
        e.touch(mode='api')
        self.assertGreater(e.last_activity, old_time)
        self.assertEqual(e.mode, 'api')

    def test_to_dict(self):
        e = PresenceEntry('inst1', host='h', ip='1.2.3.4', mode='ws')
        d = e.to_dict()
        self.assertEqual(d['instanceId'], 'inst1')
        self.assertEqual(d['host'], 'h')
        self.assertEqual(d['ip'], '1.2.3.4')
        self.assertEqual(d['mode'], 'ws')
        self.assertIn('state', d)
        self.assertIn('lastActivity', d)
        self.assertIn('connectedAt', d)


class TestPresenceManager(unittest.TestCase):
    def setUp(self):
        self.pm = PresenceManager(ttl=300, max_entries=5)

    def test_register(self):
        e = self.pm.register('inst1', host='h1')
        self.assertEqual(e.instance_id, 'inst1')
        self.assertEqual(self.pm.count(), 1)

    def test_register_dedup(self):
        self.pm.register('inst1')
        self.pm.register('inst1')
        self.assertEqual(self.pm.count(), 1)

    def test_heartbeat(self):
        self.pm.register('inst1')
        e = self.pm.heartbeat('inst1', mode='api')
        self.assertIsNotNone(e)
        self.assertEqual(e.mode, 'api')

    def test_heartbeat_unknown(self):
        result = self.pm.heartbeat('nonexistent')
        self.assertIsNone(result)

    def test_unregister(self):
        self.pm.register('inst1')
        self.assertTrue(self.pm.unregister('inst1'))
        self.assertEqual(self.pm.count(), 0)
        self.assertFalse(self.pm.unregister('inst1'))

    def test_list_all(self):
        self.pm.register('a')
        self.pm.register('b')
        entries = self.pm.list_all()
        self.assertEqual(len(entries), 2)
        ids = {e['instanceId'] for e in entries}
        self.assertEqual(ids, {'a', 'b'})

    def test_max_entries_eviction(self):
        for i in range(6):
            self.pm.register(f'inst{i}')
        self.assertLessEqual(self.pm.count(), 5)

    def test_ttl_expiry(self):
        self.pm.register('inst1')
        self.pm._entries['inst1'].last_activity = time.time() - 400
        self.assertEqual(self.pm.count(), 0)  # evicted on count()

    def test_count_by_state(self):
        self.pm.register('active1')
        self.pm.register('idle1')
        self.pm._entries['idle1'].last_activity = time.time() - (ACTIVE_THRESHOLD + 5)
        counts = self.pm.count_by_state()
        self.assertEqual(counts['active'], 1)
        self.assertEqual(counts['idle'], 1)

    def test_clear(self):
        self.pm.register('a')
        self.pm.register('b')
        self.pm.clear()
        self.assertEqual(self.pm.count(), 0)

    def test_get_existing(self):
        self.pm.register('inst1')
        e = self.pm.get('inst1')
        self.assertIsNotNone(e)

    def test_get_expired(self):
        self.pm.register('inst1')
        self.pm._entries['inst1'].last_activity = time.time() - 400
        e = self.pm.get('inst1')
        self.assertIsNone(e)


if __name__ == '__main__':
    unittest.main()
