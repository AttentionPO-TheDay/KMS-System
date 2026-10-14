"""Real registry/outbox in isolated SQLite memory. No SDK, server or private key."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pqkds.test_fabric_bindings_offline as fixture
from django.db import connection, transaction
from django.utils import timezone
from pqkds.models import Node, NodeLongTermKey, ChainKeyBinding
from pqkds import node_key_registry as registry, node_fisco_evidence as service

ENV = {'KMS_CHAIN_BACKEND': 'legacy', 'KMS_CHAIN_WRITES_ENABLED': 'false',
       'KMS_NODE_FISCO_ENABLED': 'true', 'KMS_NODE_FISCO_CONTRACT_ADDRESS': '0x' + '1' * 40}


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, ENV, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        assert connection.settings_dict['NAME'] == ':memory:'
        with connection.cursor() as cursor:
            for table in ('dvadmin_pqkds_chain_key_bindings', 'dvadmin_pqkds_node_long_term_keys', 'dvadmin_pqkds_nodes'):
                cursor.execute('DELETE FROM ' + table)
        self.node = Node.objects.create(node_id='TEST_ONLY_FISCO', name='Test', ip_address='127.0.0.1', port=1)

    def key(self, algorithm='SM2', key_id='test', public='04abcd', version=1):
        return registry.register_public_key(self.node, algorithm=algorithm, key_id=key_id,
                                           key_version=version, public_key=public)

    def test_all_algorithms_enqueue_atomic_public_snapshots(self):
        # SM2/SSCL exercise actual registry transaction. PQ provenance has independent tests.
        for algorithm in ('SM2', 'SSCL'):
            key = self.key(algorithm, algorithm)
            self.assertEqual(ChainKeyBinding.objects.get(long_term_key=key).status, 'PENDING')
        for algorithm in ('KYBER', 'FALCON', 'FALCON_CL_V1'):
            public = 'x' * 5592568 if algorithm == 'FALCON_CL_V1' else '04ef'
            key = NodeLongTermKey.objects.create(node=self.node, algorithm=algorithm, key_id=algorithm,
                public_key=public, public_key_hash=service.hashlib.sha256(public.encode()).hexdigest(), status='ACTIVE')
            with transaction.atomic():
                row = service.enqueue(key)
            payload = service.json.loads(row.metadata)
            self.assertLessEqual(len(payload['publicMaterial'].encode()), 8192)
            self.assertEqual(set(payload), {'nodeId','algorithm','keyId','keyVersion','publicKeyHash','publicMaterial'})
            self.assertNotIn('private', row.metadata)
        self.assertEqual(ChainKeyBinding.objects.count(), 5)

    def test_new_key_is_v1_not_rotation_and_outbox_is_idempotent(self):
        first = self.key(key_id='first')
        second = self.key(key_id='second', public='04cdef')
        self.assertEqual(second.key_version, 1)
        first.refresh_from_db()
        self.assertEqual(first.status, 'RETIRED')
        self.key(key_id='second', public='04cdef')
        self.assertEqual(ChainKeyBinding.objects.count(), 2)

    def test_registration_rollback_removes_outbox(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.key()
                raise RuntimeError('TEST_ONLY_ROLLBACK')
        self.assertFalse(ChainKeyBinding.objects.exists())

    def test_pause_does_not_initialize_another_chain(self):
        with patch.dict(os.environ, {'KMS_NODE_FISCO_ENABLED': 'false'}):
            self.key()
            self.assertFalse(service.process_one(api=lambda *_: self.fail('network')))
        self.assertFalse(ChainKeyBinding.objects.exists())

    def test_receipt_loss_retries_same_persisted_signed_transaction(self):
        key = self.key()
        tx = '0x' + '2' * 64
        calls = []
        fail = [True]
        def api(operation, payload):
            calls.append((operation, dict(payload)))
            if operation == 'prepare':
                return dict(status='PREPARED', txId=tx, signedTransaction='aabb')
            row = ChainKeyBinding.objects.get(long_term_key=key)
            self.assertEqual(row.tx_id, tx)
            self.assertEqual(row.nonce, 'aabb')
            if operation == 'receipt':
                return dict(status='PENDING_VERIFICATION', txId=tx)
            if fail[0]:
                fail[0] = False
                raise TimeoutError('TEST_ONLY_LOST_RESPONSE')
            return dict(status='CONFIRMED', txId=tx, blockHeight='0x10')
        service.process_one(api)
        row = ChainKeyBinding.objects.get(long_term_key=key)
        self.assertEqual(row.status, 'PENDING_VERIFICATION')
        ChainKeyBinding.objects.filter(pk=row.pk).update(lease_until=timezone.now())
        service.process_one(api)
        self.assertEqual([op for op, _ in calls].count('prepare'), 1)
        self.assertEqual([data['signedTransaction'] for op, data in calls if op == 'submit'], ['aabb', 'aabb'])
        result = service.status(key)
        self.assertEqual(result['status'], 'CONFIRMED')
        self.assertTrue(result['transactionValid'])
        self.assertEqual(result['blockHeight'], 16)

    def test_failed_receipt_never_reports_confirmed(self):
        key = self.key()
        tx = '0x' + '3' * 64
        def api(operation, payload):
            return dict(status='PREPARED', txId=tx, signedTransaction='aabb') if operation == 'prepare' else dict(status='FAILED', txId=tx, lastError='FISCO_RECEIPT_FAILED')
        service.process_one(api)
        result = service.status(key)
        self.assertEqual(result['status'], 'FAILED')
        self.assertFalse(result['transactionValid'])
        self.assertFalse(service.process_one(api))


if __name__ == '__main__':
    unittest.main()
