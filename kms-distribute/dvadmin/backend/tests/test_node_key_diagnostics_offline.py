"""Real models/queries/handlers in independent SQLite memory; no production writes."""
import ast
import hashlib
import json
import sys
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pqkds.test_fabric_bindings_offline as fixture
from django.db import connection
from django.db.models import Count, Q
from django.http import JsonResponse
from django.test import RequestFactory
from django.utils import timezone
from pqkds import api_contract as C
from pqkds.models import Node, NodeLongTermKey, PreDistributedKey, SessionKey

with connection.schema_editor() as editor:
    editor.create_model(SessionKey)
    editor.create_model(PreDistributedKey)

path = Path(__file__).resolve().parents[1] / 'pqkds/node_key_diagnostics.py'
definitions = [item for item in ast.parse(path.read_text(encoding='utf-8')).body if isinstance(item, ast.FunctionDef)]
for item in definitions:
    item.decorator_list = []
env = dict(Node=Node, NodeLongTermKey=NodeLongTermKey, PreDistributedKey=PreDistributedKey,
           SessionKey=SessionKey, Count=Count, Q=Q, JsonResponse=JsonResponse, timezone=timezone,
           hashlib=hashlib, C=C)
exec(compile(ast.Module(body=definitions, type_ignores=[]), str(path), 'exec'), env)


class DiagnosticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = Node.objects.create(node_id='diagnostic-owner', name='Owner', sys_user_id=71,
            ip_address='127.0.0.1', port=71, kyber_public_key='real-test-public')
        cls.peer = Node.objects.create(node_id='diagnostic-peer', name='Peer', sys_user_id=72,
            ip_address='127.0.0.1', port=72)
        cls.key = NodeLongTermKey.objects.create(node=cls.node, key_id='diagnostic-KYBER', key_version=1,
            algorithm='KYBER', status='ACTIVE', active_slot='KYBER', public_key='real-test-public',
            public_key_hash=hashlib.sha256(b'real-test-public').hexdigest())
        cls.factory = RequestFactory()

    def call(self, operation, params=None, user=71):
        request = self.factory.get('/node-self/key-' + operation + '/', params or {'keyId': self.key.key_id})
        response = env['node_key_' + operation](request, {'userId': user})
        return response.status_code, json.loads(response.content)

    def test_string_key_health_and_no_mutation(self):
        before = list(NodeLongTermKey.objects.values())
        status, body = self.call('health')
        self.assertEqual(status, 200)
        self.assertEqual(body['data']['health'], 'OK')
        self.assertEqual(body['data']['keyId'], self.key.key_id)
        self.assertEqual(body['data']['findings'], [])
        self.assertEqual(before, list(NodeLongTermKey.objects.values()))
        self.assertNotIn('real-test-public', json.dumps(body))

    def test_detects_hash_drift_without_revoking(self):
        NodeLongTermKey.objects.filter(pk=self.key.pk).update(public_key_hash='0' * 64)
        try:
            status, body = self.call('health')
            self.assertEqual(status, 200)
            self.assertEqual(body['data']['health'], 'SUSPICIOUS')
            self.assertEqual(body['data']['findings'][0]['rule'], 'PUBLIC_KEY_HASH_MISMATCH')
            self.assertEqual(NodeLongTermKey.objects.get(pk=self.key.pk).status, 'ACTIVE')
        finally:
            NodeLongTermKey.objects.filter(pk=self.key.pk).update(public_key_hash=self.key.public_key_hash)

    def test_owner_boundary_missing_and_bad_version(self):
        for operation in ['health', 'analysis']:
            self.assertEqual(self.call(operation, user=72)[0], 404)
            self.assertEqual(self.call(operation, user=999)[0], 403)
            self.assertEqual(self.call(operation, {'keyId': 'missing'})[0], 404)
            self.assertEqual(self.call(operation, {'keyId': self.key.key_id, 'version': 'nan'})[0], 400)
            self.assertEqual(self.call(operation, {'keyId': self.key.key_id, 'version': '-1'})[0], 400)

    def test_expiry_and_history_do_not_change_current_key(self):
        NodeLongTermKey.objects.filter(pk=self.key.pk).update(expires_at=timezone.now() - timedelta(days=1))
        try:
            status, body = self.call('health')
            self.assertEqual(status, 200)
            self.assertIn('KEY_EXPIRED', [row['rule'] for row in body['data']['findings']])
            self.assertEqual(NodeLongTermKey.objects.get(pk=self.key.pk).status, 'ACTIVE')
        finally:
            NodeLongTermKey.objects.filter(pk=self.key.pk).update(expires_at=None)
        history = NodeLongTermKey.objects.create(node=self.node, key_id='history-KYBER', key_version=1,
            algorithm='KYBER', status='RETIRED', public_key='old-public',
            public_key_hash=hashlib.sha256(b'old-public').hexdigest())
        status, body = self.call('health', {'keyId': history.key_id})
        self.assertEqual(status, 200)
        self.assertEqual(body['data']['findings'], [])

    def test_experimental_encryption_has_no_signing_mirror(self):
        key = NodeLongTermKey.objects.create(node=self.node, key_id='diagnostic-FALCON_CL_V1', key_version=1,
            algorithm='FALCON_CL_V1', status='ACTIVE', active_slot='FALCON_CL_V1', public_key='cl-public',
            public_key_hash=hashlib.sha256(b'cl-public').hexdigest())
        status, body = self.call('health', {'keyId': key.key_id})
        self.assertEqual(status, 200)
        self.assertEqual(body['data']['findings'], [])
        self.assertNotIn('生产公钥与登记记录一致', body['data']['observations'])

    def test_analysis_real_references_and_no_unrelated_records(self):
        expiry = timezone.now() + timedelta(days=1)
        session = SessionKey.objects.create(session_id='diagnostic-session', node1=self.peer, node2=self.node,
            expires_at=expiry, recipient_key_id=self.key.key_id, recipient_key_version=1,
            encrypted_session_key='secret-never-return', key_exchange_data='secret-never-return')
        PreDistributedKey.objects.create(pool_id='diagnostic-pool', node1=self.peer, node2=self.node,
            key_index=1, expires_at=expiry, long_term_key_id=self.key.key_id, long_term_key_version=1,
            status='READY', recipient_type='pool', encrypted_key_data='secret-never-return', key_hash='h')
        other = Node.objects.create(node_id='unrelated', name='Unrelated', ip_address='127.0.0.1', port=73)
        SessionKey.objects.create(session_id='not-owner-session', node1=other, node2=self.peer,
            expires_at=expiry, recipient_key_id=self.key.key_id, recipient_key_version=1)
        status, body = self.call('analysis')
        self.assertEqual(status, 200)
        result = body['data']
        self.assertEqual(result['operationTrails'][0]['session_id'], session.session_id)
        self.assertEqual(len(result['operationTrails']), 1)
        self.assertEqual(result['affectedPoolItems'][0]['item_count'], 1)
        self.assertEqual(result['affectedNodes'][0]['node_id'], self.peer.node_id)
        self.assertNotIn('secret-never-return', json.dumps(body))
        self.assertEqual(self.call('analysis', {'keyId': self.key.key_id, 'version': '2'})[0], 404)


if __name__ == '__main__':
    unittest.main()
