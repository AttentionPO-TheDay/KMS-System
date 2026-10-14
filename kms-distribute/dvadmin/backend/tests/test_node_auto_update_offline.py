"""Isolated in-memory schedules; never rotates production keys."""
import sys
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pqkds.test_fabric_bindings_offline as fixture
from django.db import connection
from django.utils import timezone
from pqkds.models import Node, NodeLongTermKey, NodeKeyAutoUpdate
from pqkds import node_auto_update as service

with connection.schema_editor() as editor:
    editor.create_model(NodeKeyAutoUpdate)


class NodeAutoUpdateTests(unittest.TestCase):
    def setUp(self):
        assert connection.settings_dict['NAME'] == ':memory:'
        with connection.cursor() as cursor:
            for model in (NodeKeyAutoUpdate, NodeLongTermKey, Node):
                cursor.execute('DELETE FROM ' + model._meta.db_table)
        self.node = Node.objects.create(node_id='auto-node', name='Auto',
                                        ip_address='127.0.0.1', port=1, status='active')
        self.key = NodeLongTermKey.objects.create(node=self.node, algorithm='SM2',
            key_id='auto-key', key_version=1, status='ACTIVE', public_key='04abcd')

    def config(self, **changes):
        return service.configure(self.node, dict(algorithm='SM2', keyId='auto-key',
                                                enabled=True, intervalMinutes=1, **changes))

    def due(self):
        NodeKeyAutoUpdate.objects.filter(node=self.node).update(next_run_at=timezone.now() - timedelta(seconds=1))

    def advance(self):
        self.key.status = 'SUPERSEDED'
        self.key.save()
        return NodeLongTermKey.objects.create(node=self.node, algorithm='SM2', key_id='auto-key',
                                              key_version=2, status='ACTIVE', public_key='04ef01')

    def test_interval_is_persisted_and_only_due_job_claimed(self):
        result = self.config()
        self.assertTrue(result['enabled'])
        self.assertEqual(result['intervalMinutes'], 1)
        self.assertIsNone(service.claim(self.node, 'SM2'))
        self.due()
        job = service.claim(self.node, 'SM2')
        self.assertEqual(job['fromVersion'], 1)
        self.assertIsNone(service.claim(self.node, 'SM2'))
        self.assertEqual(NodeLongTermKey.objects.get(pk=self.key.pk).key_version, 1)

    def test_real_registry_version_required_for_success(self):
        self.config()
        self.due()
        job = service.claim(self.node, 'SM2')
        result = service.complete(self.node, dict(algorithm='SM2', leaseToken=job['leaseToken']))
        self.assertEqual(result['lastResult'], 'FAILED')
        self.due()
        job = service.claim(self.node, 'SM2')
        self.advance()
        result = service.complete(self.node, dict(algorithm='SM2', leaseToken=job['leaseToken']))
        self.assertEqual(result['lastResult'], 'SUCCESS')
        self.assertIn('v2', result['lastMessage'])
        self.assertFalse(result['running'])
        self.assertIsNone(service.claim(self.node, 'SM2'))

    def test_lost_response_recovers_without_second_rotation(self):
        self.config()
        self.due()
        service.claim(self.node, 'SM2')
        self.advance()
        NodeKeyAutoUpdate.objects.filter(node=self.node).update(lease_until=timezone.now() - timedelta(seconds=1))
        self.assertIsNone(service.claim(self.node, 'SM2'))
        self.assertEqual(NodeKeyAutoUpdate.objects.get(node=self.node).last_result, 'SUCCESS')

    def test_revoke_stops_schedule_without_generating_replacement(self):
        self.config()
        self.due()
        self.key.status = 'REVOKED'
        self.key.save()
        self.assertIsNone(service.claim(self.node, 'SM2'))
        self.assertFalse(NodeKeyAutoUpdate.objects.get(node=self.node).enabled)
        self.assertEqual(NodeLongTermKey.objects.count(), 1)

    def test_invalid_configuration_and_cross_node_completion_rejected(self):
        for minutes in (0, -1, 525601, True, '1', 1.5):
            with self.assertRaises(ValueError):
                service.configure(self.node, dict(algorithm='SM2', keyId='auto-key', enabled=True, intervalMinutes=minutes))
        other = Node.objects.create(node_id='other', name='Other', ip_address='127.0.0.1', port=2)
        with self.assertRaises(ValueError):
            service.configure(other, dict(algorithm='SM2', keyId='auto-key', enabled=True, intervalMinutes=1))
        self.config()
        self.due()
        job = service.claim(self.node, 'SM2')
        with self.assertRaises(ValueError):
            service.complete(other, dict(algorithm='SM2', leaseToken=job['leaseToken']))

    def test_disable_and_manual_rotation_reschedule(self):
        self.config()
        self.due()
        service.registered(self.node, 'SM2', 'auto-key', 2)
        self.assertIsNone(service.claim(self.node, 'SM2'))
        service.configure(self.node, dict(algorithm='SM2', keyId='auto-key', enabled=False, intervalMinutes=60))
        self.due()
        self.assertIsNone(service.claim(self.node, 'SM2'))

    def test_expired_lease_can_retry_but_stale_completion_cannot(self):
        self.config()
        self.due()
        job = service.claim(self.node, 'SM2')
        NodeKeyAutoUpdate.objects.filter(node=self.node).update(lease_until=timezone.now() - timedelta(seconds=1))
        retry = service.claim(self.node, 'SM2')
        self.assertNotEqual(job['leaseToken'], retry['leaseToken'])
        with self.assertRaises(ValueError):
            service.complete(self.node, dict(algorithm='SM2', leaseToken=job['leaseToken']))


if __name__ == '__main__':
    unittest.main()
