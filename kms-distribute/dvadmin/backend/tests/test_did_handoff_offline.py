# -*- coding: utf-8 -*-
"""DID 参数交接离线测试，只使用 SQLite :memory:，不连接 Bridge 或区块链。"""
import hashlib
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
import pqkds.test_fabric_bindings_offline as fixture
from django.db import connection
from pqkds import did_handoff_service as service
from pqkds.models import DidSdkHandoff, Node, NodeLongTermKey


class PreparedBridge:
    def __init__(self):
        self.closed = False

    def prepare_handoff(self, payload):
        metadata = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        digest = hashlib.sha256(metadata.encode('utf-8')).hexdigest()
        return {
            'provider': 'FABRIC_DID', 'chainId': 'handoff-test',
            'did': f'did:offline:kms-key-binding-v1:binding:{digest}',
            'txId': 'a' * 64, 'nonce': 'b' * 48, 'metadata': metadata,
            'metadataDigest': digest, 'binding': payload, 'prepared': True,
            'submitted': False, 'status': 'PREPARED',
        }

    def close(self):
        self.closed = True


class DidHandoffTests(unittest.TestCase):
    def setUp(self):
        if connection.settings_dict['NAME'] != ':memory:':
            raise RuntimeError('Refusing non-memory database')
        with connection.cursor() as cursor:
            for model in (DidSdkHandoff, fixture.ChainKeyBinding, NodeLongTermKey, Node):
                cursor.execute('DELETE FROM ' + model._meta.db_table)
        self.node = Node.objects.create(node_id='handoff-node', name='Handoff',
                                        ip_address='127.0.0.1', port=1, status='active')
        public_key = '04aabbcc'
        self.key = NodeLongTermKey.objects.create(
            node=self.node, key_id='handoff-key', key_version=1, algorithm='SM2',
            status='ACTIVE', active_slot='SM2', public_key=public_key,
            public_key_hash=hashlib.sha256(public_key.encode('utf-8')).hexdigest(),
        )

    def test_records_request_and_optional_prepare_without_submit(self):
        bridge = PreparedBridge()
        env = {
            'KMS_CHAIN_WRITES_ENABLED': 'false', 'KMS_CHAIN_BACKEND': 'legacy',
            'FABRIC_DID_ENABLED': 'true', 'FABRIC_DID_CHAIN_ID': 'handoff-test',
            'FABRIC_DID_NAMESPACE': 'kms-key-binding-v1', 'INTERNAL_TOKEN': 'test-token',
        }
        with patch.dict(os.environ, env, clear=True):
            record = service.create_handoff(
                self.node, algorithm='SM2', key_id='handoff-key', key_version=1,
                requested_by='102', client_factory=lambda: bridge,
            )
        self.assertEqual(record.prepare_status, 'PREPARED')
        self.assertFalse(service.record_payload(record, True)['handoffPackage']['submitted'])
        self.assertFalse(service.record_payload(record, True)['handoffPackage']['sdkContract']['submitInvoked'])
        self.assertEqual(json.loads(record.request_payload)['publicKey'], self.key.public_key)
        self.assertEqual(record.tx_id, 'a' * 64)
        self.assertTrue(bridge.closed)

    def test_missing_bridge_configuration_still_keeps_transferable_request(self):
        factory = Mock(side_effect=AssertionError('unconfigured handoff must not call Bridge'))
        with patch.dict(os.environ, {'FABRIC_DID_ENABLED': 'false'}, clear=True):
            record = service.create_handoff(
                self.node, algorithm='SM2', key_id='handoff-key', key_version=1,
                client_factory=factory,
            )
        self.assertEqual(record.prepare_status, 'NOT_CONFIGURED')
        self.assertEqual(record.last_error, 'DISABLED')
        self.assertTrue(json.loads(record.request_payload)['publicKey'])
        factory.assert_not_called()

    def test_non_active_key_is_rejected_without_record(self):
        self.key.status = 'RETIRED'
        self.key.active_slot = None
        self.key.save(update_fields=['status', 'active_slot'])
        with self.assertRaises(service.HandoffError) as raised:
            service.create_handoff(
                self.node, algorithm='SM2', key_id='handoff-key', key_version=1,
            )
        self.assertEqual(raised.exception.code, 'KEY_NOT_ACTIVE')
        self.assertEqual(DidSdkHandoff.objects.count(), 0)


if __name__ == '__main__':
    unittest.main()
