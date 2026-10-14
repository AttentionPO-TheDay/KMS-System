"""Logical-key generation/rotation regression, isolated SQLite only."""
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pqkds.test_fabric_bindings_offline as fixture
from django.db import connection
from django.utils import timezone
from pqkds.models import ChainKeyBinding, Node, NodeLongTermKey
from pqkds.node_workbench import summary
from pqkds import node_key_registry as registry
from pqkds import api_contract as C


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        assert connection.settings_dict['NAME'] == ':memory:'
        with connection.cursor() as cursor:
            for model in (ChainKeyBinding, NodeLongTermKey, Node):
                cursor.execute('DELETE FROM ' + model._meta.db_table)
        self.env = patch.dict('os.environ', {'KMS_CHAIN_BACKEND': 'legacy',
            'KMS_NODE_FISCO_ENABLED': 'false', 'KMS_SPLIT_KEYGEN_ENABLED': 'false'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.node = Node.objects.create(node_id='workbench-node', name='Test', ip_address='127.0.0.1', port=1)

    def register(self, key_id):
        return registry.register_public_key(self.node, algorithm='SM2', public_key='04' + key_id.encode().hex(), key_id=key_id)

    def test_initialization_and_generation_share_total_rotation_keeps_id(self):
        initial = self.register('init-key')
        self.assertEqual(summary(self.node)['total'], 1)
        new = self.register('new-key')
        self.assertNotEqual(initial.key_id, new.key_id)
        self.assertEqual(new.key_version, 1)
        self.assertEqual(summary(self.node)['total'], 2)
        updated = registry.rotate_public_key(self.node, algorithm='SM2', public_key='04abcd', key_id=new.key_id, key_version=2)
        self.assertEqual(updated.key_id, new.key_id)
        result = summary(self.node)
        self.assertEqual(result['total'], 2)
        self.assertEqual(result['versionTotal'], 3)
        self.assertEqual(result['active'], 1)
        self.assertEqual(sum(day['count'] for day in result['trend']), 2)
        self.assertEqual(result['algorithms']['SM2'], 2)
        registry.register_public_key(self.node, algorithm='SM2', public_key='04abcd', key_id=new.key_id, key_version=2)
        self.assertEqual(summary(self.node)['versionTotal'], 3, 'registration retry is idempotent')

    def test_new_key_cannot_start_at_version_two_or_reuse_existing_id(self):
        self.register('init-key')
        for key_id in ('new-key', 'init-key'):
            with self.assertRaises(C.ContractError):
                registry.register_public_key(self.node, algorithm='SM2', public_key='04ffff', key_id=key_id, key_version=2)
        self.assertEqual(summary(self.node)['total'], 1)

    def test_all_records_counted_beyond_200_and_other_node_excluded(self):
        for index in range(301):
            NodeLongTermKey.objects.create(node=self.node, algorithm='SM2', key_id=f'key-{index}',
                key_version=1, status='RETIRED', public_key='04abcd')
        other = Node.objects.create(node_id='other', name='Other', ip_address='127.0.0.1', port=2)
        NodeLongTermKey.objects.create(node=other, algorithm='SM2', key_id='other-key', status='ACTIVE')
        result = summary(self.node)
        self.assertEqual(result['total'], 301)
        self.assertEqual(result['statuses']['RETIRED'], 301)
        self.assertEqual(result['chain']['unregistered'], 301)
        self.assertEqual(result['active'], 0)

    def test_rotation_does_not_move_old_generation_into_recent_trend(self):
        initial = self.register('old-key')
        NodeLongTermKey.objects.filter(pk=initial.pk).update(create_datetime=timezone.now() - timedelta(days=30))
        registry.rotate_public_key(self.node, algorithm='SM2', public_key='04abcd', key_id='old-key', key_version=2)
        self.assertEqual(sum(day['count'] for day in summary(self.node)['trend']), 0)

    def test_chain_scope_confirmation_and_materials_excluded(self):
        key = self.register('evidence-key')
        common = dict(node=self.node, long_term_key=key, node_id_snapshot=self.node.node_id,
            algorithm='SM2', key_id=key.key_id, key_version=1, key_ref='node/test',
            event_type='REGISTERED', key_status='REGISTERED', metadata='SECRET_SENTINEL', metadata_digest='digest')
        binding = ChainKeyBinding.objects.create(**common, provider='FISCO', chain_id='fisco:group-1:',
            namespace='kms-node-fisco-v1', event_id='event-1', sequence=1,
            status='CONFIRMED', transaction_valid=True, metadata_matches=True)
        ChainKeyBinding.objects.create(**common, provider='FISCO', chain_id='old-contract',
            namespace='kms-node-fisco-v1', event_id='event-2', sequence=2, status='FAILED')
        result = summary(self.node)
        self.assertEqual(result['chain']['confirmed'], 1)
        binding.metadata_matches = False
        binding.save()
        self.assertEqual(summary(self.node)['chain']['pending'], 1)
        self.assertNotIn('SECRET_SENTINEL', str(result))
        self.assertNotIn('publicKey', result['currentKeys'][0])

    def test_empty_registry_and_expired_key(self):
        result = summary(self.node)
        self.assertEqual(result['total'], 0)
        self.assertEqual(len(result['trend']), 7)
        key = self.register('expired-key')
        NodeLongTermKey.objects.filter(pk=key.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        result = summary(self.node)
        self.assertEqual(result['active'], 0)
        self.assertEqual(result['statuses']['EXPIRED'], 1)


if __name__ == '__main__':
    unittest.main()
