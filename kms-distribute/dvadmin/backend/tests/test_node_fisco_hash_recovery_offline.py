"""Standalone recovery script on isolated in-memory SQLite, no real chain writes."""
import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pqkds.test_fabric_bindings_offline as fixture
from django.db import connection
from pqkds.models import Node, ChainKeyBinding
from pqkds.node_key_registry import register_public_key

spec = importlib.util.spec_from_file_location('recover_hash', '/tmp/recover-node-fisco-hash.py')
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'KMS_CHAIN_BACKEND': 'legacy', 'KMS_NODE_FISCO_ENABLED': 'true',
            'KMS_NODE_FISCO_CONTRACT_ADDRESS': '0x' + '1' * 40}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        assert connection.settings_dict['NAME'] == ':memory:'
        with connection.cursor() as cursor:
            for table in ('dvadmin_pqkds_chain_key_bindings', 'dvadmin_pqkds_node_long_term_keys', 'dvadmin_pqkds_nodes'):
                cursor.execute('DELETE FROM ' + table)
        node = Node.objects.create(node_id='TEST_ONLY_RECOVERY', name='Test', ip_address='127.0.0.1', port=1)
        key = register_public_key(node, algorithm='SM2', key_id='test', key_version=1, public_key='04abcd')
        self.key = key
        self.row = ChainKeyBinding.objects.get(long_term_key=key)
        self.row.status = 'FAILED'
        self.row.last_error = 'FISCO_RESPONSE_IDENTITY_MISMATCH'
        self.row.tx_id = '0x' + '2' * 64
        self.row.nonce = '0xaabb'
        self.row.submit_started = True
        self.row.save()

    def api(self, operation, payload):
        self.assertEqual(operation, 'receipt')
        self.assertNotIn('signedTransaction', payload)
        ref = f"node/{payload['nodeId']}/{payload['algorithm']}/{payload['keyId']}/{payload['keyVersion']}"
        return dict(status='CONFIRMED', chainId=self.row.chain_id, txId=payload['txId'],
            publicKeyHash=payload['publicKeyHash'], blockHeight='0x10',
            chainKeyId=str(int(recovery.hashlib.sha256(ref.encode()).hexdigest(),16) | (1<<255)))

    def test_apply_repairs_hash_only_after_receipt_validation_preserving_keys_and_signed_bytes(self):
        report = recovery.recover_one(self.row, True, self.api)
        self.assertTrue(report['applied'])
        self.row.refresh_from_db(); self.key.refresh_from_db()
        self.assertEqual(self.row.status, 'CONFIRMED')
        self.assertEqual(self.row.block_height, 16)
        self.assertTrue(self.row.transaction_valid and self.row.metadata_matches)
        self.assertNotEqual(self.row.tx_id, '0x' + '2' * 64)
        self.assertEqual(self.row.nonce, '0xaabb')
        self.assertEqual(self.key.key_version, 1)
        self.assertEqual(self.key.public_key, '04abcd')

    def test_read_only_mode_does_not_change_database(self):
        recovery.recover_one(self.row, False, self.api)
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, 'FAILED')

    def test_pending_and_failed_receipts_do_not_change_database(self):
        for outcome in ('PENDING_VERIFICATION', 'FAILED'):
            def api(op, payload):
                result = self.api(op, payload); result['status'] = outcome; return result
            report = recovery.recover_one(self.row, True, api)
            self.assertFalse(report['applied'])
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, 'FAILED')

    def test_wrong_identity_or_height_cannot_confirm(self):
        for field, value in (('chainId', 'wrong'), ('txId', 'wrong'), ('publicKeyHash', 'wrong'),
                             ('chainKeyId', 'wrong'), ('blockHeight', '0x0')):
            def api(op, payload):
                result = self.api(op, payload); result[field] = value; return result
            with self.assertRaises(ValueError): recovery.recover_one(self.row, True, api)
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, 'FAILED')

    def test_changed_row_is_not_overwritten(self):
        def api(op, payload):
            result = self.api(op, payload)
            ChainKeyBinding.objects.filter(pk=self.row.pk).update(status='PENDING')
            return result
        with self.assertRaises(ValueError): recovery.recover_one(self.row, True, api)
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, 'PENDING')


if __name__ == '__main__': unittest.main()
