"""Chunked production upload against real SQLite constraints, without live keys or services."""
import json
import logging
import os
import re
import sys
import types
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_pool_sender_material_offline import fixture, production_function
from django.db import connection, IntegrityError, transaction
from django.utils import timezone
from pqkds import api_contract as C
from pqkds import node_key_registry as registry
from pqkds.models import LatticePreparation, Node, NodeLongTermKey, PreDistributedKey, SessionKey


class PoolUploadChunkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert connection.settings_dict['NAME'] == ':memory:'
        with connection.schema_editor() as editor:
            editor.create_model(LatticePreparation)
            editor.create_model(SessionKey)
            editor.create_model(PreDistributedKey)
        cls.sender = Node.objects.create(node_id='chunk-sender', name='A', ip_address='127.0.0.1', port=1)
        cls.receiver = Node.objects.create(node_id='chunk-receiver', name='B', ip_address='127.0.0.2', port=2)
        cls.endpoint = staticmethod(production_function('node_self_views.py', 'node_pool_preallocate', {
            'Node': Node, 'C': C, 'json': json, 'timezone': timezone,
            'IntegrityError': IntegrityError, 'transaction': transaction,
            'MAX_POOL_ITEMS_PER_BATCH': 200, '_POOL_ID_RE': re.compile(r'^pool_[0-9a-f]{16,32}$'),
            '_SHA256_RE': re.compile(r'^[0-9a-f]{64}$'),
            '_find_node': lambda _identity: cls.sender,
            '_as_future_expiry': lambda _value: timezone.now() + timedelta(hours=1),
            '_write_pool_log': lambda *_args, **_kwargs: None,
            '_ok': lambda data, **kwargs: data,
            '_error': lambda message, *args, **kwargs: {'error': message},
            'logger': logging.getLogger('offline'),
        }))

    def setUp(self):
        # Only cryptography and external lattice preparation are isolated. ORM inserts,
        # savepoints, the endpoint body and the pool/index unique constraint are real.
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM ' + connection.ops.quote_name(PreDistributedKey._meta.db_table))
        signature = types.ModuleType('pqkds.envelope_signature')
        signature.verify_node_envelope = lambda envelope, sig, public: sig == 'valid'
        registry = types.ModuleType('pqkds.node_key_registry')
        key = types.SimpleNamespace(key_id='receiver-kyber', key_version=1, public_key='test-public')
        registry.require_usable_key = lambda *_args: key
        registry.require_key_version = lambda *_args, **_kwargs: key
        distribution = types.ModuleType('pqkds.distribution_service')
        distribution.authorized_node_ids = lambda _user: [self.receiver.pk]
        pool = types.ModuleType('pqkds.key_pool_service')
        pool.KeyPoolService = object
        lattice = types.ModuleType('pqkds.lattice_preallocation')
        lattice.protect_pool_rows = lambda rows, receiver: {'verified': len(rows)}
        self.modules = patch.dict(sys.modules, {
            'pqkds.envelope_signature': signature, 'pqkds.node_key_registry': registry,
            'pqkds.distribution_service': distribution, 'pqkds.key_pool_service': pool,
            'pqkds.lattice_preallocation': lattice,
        })
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def upload(self, start=0, count=200, pool='pool_1234567890abcdef', omit_start=False, invalid=()):
        items = [{
            'envelope': {'batch_id': pool, 'sender_node_id': self.sender.node_id,
                         'receiver_node_id': self.receiver.node_id,
                         'recipient_key_id': 'receiver-kyber', 'recipient_key_version': 1},
            'signature': 'invalid' if i in invalid else 'valid',
            'keyHash': format(i, '064x'),
        } for i in range(count)]
        payload = {'targetNodeCode': self.receiver.node_id, 'poolId': pool, 'items': items,
                   'falconKeyId': 'sender-falcon', 'falconKeyVersion': 1}
        if not omit_start:
            payload['startIndex'] = start
        return self.endpoint(types.SimpleNamespace(body=json.dumps(payload).encode()), {'userId': 1})

    def test_1000_and_2000_items_have_unique_global_indices(self):
        for count in (1000, 2000):
            pool = 'pool_' + format(count, '016x')
            with self.subTest(count=count):
                for start in range(0, count, 200):
                    result = self.upload(start, pool=pool)
                    self.assertEqual(result['generated'], 200)
                    self.assertEqual(result['failed'], [])
                    self.assertEqual(result['startIndex'], start)
                rows = PreDistributedKey.objects.filter(pool_id=pool).order_by('key_index')
                self.assertEqual(list(rows.values_list('key_index', flat=True)), list(range(count)))

    def test_retry_does_not_duplicate_and_failures_keep_chunk_local_indices(self):
        self.upload(400)
        retry = self.upload(400)
        self.assertEqual(retry['generated'], 0)
        self.assertEqual([x['index'] for x in retry['failed']], list(range(200)))
        self.assertTrue(all(x['errorCode'] == 'DUPLICATE_ITEM' for x in retry['failed']))
        self.assertEqual(PreDistributedKey.objects.count(), 200)
        # A partially overlapping upload reports the first 100 local positions,
        # then admits new indices 600..699 without rolling back the whole request.
        overlap = self.upload(500)
        self.assertEqual(overlap['generated'], 100)
        self.assertEqual([x['index'] for x in overlap['failed']], list(range(100)))
        self.assertEqual(PreDistributedKey.objects.count(), 300)

    def test_legacy_single_chunk_and_separate_pools_remain_compatible(self):
        self.assertEqual(self.upload(count=100, omit_start=True)['generated'], 100)
        self.assertEqual(self.upload(count=100, pool='pool_abcdef1234567890')['generated'], 100)
        self.assertEqual(PreDistributedKey.objects.count(), 200)

    def test_out_of_order_chunks_and_short_tail_keep_their_requested_positions(self):
        for start, count in [(400, 1), (200, 200), (0, 200)]:
            self.assertEqual(self.upload(start, count)['generated'], count)
        self.assertEqual(list(PreDistributedKey.objects.order_by('key_index').values_list('key_index', flat=True)), list(range(401)))

    def test_bad_start_index_or_overflow_is_rejected_before_insert(self):
        for start in [-1, True, False, None, '200', 1.5, 2147483647, 10**30, [], {}]:
            with self.subTest(start=start):
                self.assertIn('error', self.upload(start, count=2))
                self.assertEqual(PreDistributedKey.objects.count(), 0)
        self.assertEqual(self.upload(2147483647, count=1)['generated'], 1)

    def test_invalid_signature_stays_rejected_and_missing_position_can_be_retried(self):
        result = self.upload(200, count=3, invalid=(1,))
        self.assertEqual(result['generated'], 2)
        self.assertEqual(result['failed'][0]['index'], 1)
        self.assertEqual(result['failed'][0]['errorCode'], C.ERR_SIGNATURE_INVALID)
        retry = self.upload(200, count=3)
        self.assertEqual(retry['generated'], 1)
        self.assertEqual([x['index'] for x in retry['failed']], [0, 2])
        self.assertEqual(list(PreDistributedKey.objects.order_by('key_index').values_list('key_index', flat=True)), [200, 201, 202])


class OtherKeyIdentityTests(unittest.TestCase):
    def test_four_algorithm_versions_cross_200_and_exact_retries_stay_idempotent(self):
        # Exercise actual registry transactions and identity constraints for the other
        # key paths, independently from chunk-local pool numbering; no network worker.
        with patch.dict(os.environ, {**fixture.ENV, 'KMS_CHAIN_WRITES_ENABLED': 'false'}, clear=True):
            node = Node.objects.create(node_id='version-test', name='Versions', ip_address='127.0.0.3', port=3)
            for algorithm in ('SM2', 'SSCL', 'KYBER', 'FALCON'):
                with self.subTest(algorithm=algorithm):
                    key_id = 'version-check-' + algorithm
                    first = registry.register_public_key(node, algorithm=algorithm,
                        key_id=key_id, key_version=1, public_key=f'{algorithm}-public-1')
                    for version in range(2, 206):
                        latest = registry.rotate_public_key(node, algorithm=algorithm,
                            key_id=key_id, key_version=version, public_key=f'{algorithm}-public-{version}')
                    again = registry.rotate_public_key(node, algorithm=algorithm,
                        key_id=key_id, key_version=205, public_key=f'{algorithm}-public-205')
                    historical = registry.rotate_public_key(node, algorithm=algorithm,
                        key_id=key_id, key_version=1, public_key=f'{algorithm}-public-1')
                    self.assertEqual((again.pk, historical.pk), (latest.pk, first.pk))
                    rows = NodeLongTermKey.objects.filter(node=node, algorithm=algorithm)
                    self.assertEqual(list(rows.order_by('key_version').values_list('key_version', flat=True)), list(range(1, 206)))
                    self.assertEqual(list(rows.filter(status='ACTIVE').values_list('key_version', flat=True)), [205])


if __name__ == '__main__':
    unittest.main(verbosity=2)
