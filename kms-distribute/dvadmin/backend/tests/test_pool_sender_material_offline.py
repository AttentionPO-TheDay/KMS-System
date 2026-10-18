"""Real production methods against isolated SQLite; no server settings or network."""
import ast
import __future__
import hashlib
import json
import logging
import re
import sys
import types
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pqkds.test_fabric_bindings_offline as fixture
from django.db import connection, models, transaction
from django.utils import timezone
from pqkds import api_contract as C
from pqkds.models import Node, PreDistributedKey, SessionKey


def production_function(filename, name, context, class_name=None):
    tree = ast.parse((ROOT / 'pqkds' / filename).read_text(encoding='utf-8'))
    scope = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == class_name).body if class_name else tree.body
    method = next(item for item in scope if isinstance(item, ast.FunctionDef) and item.name == name)
    method.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    context = {**context, '__package__': 'pqkds'}
    exec(compile(module, filename, 'exec', flags=__future__.annotations.compiler_flag), context)
    return context[name]


class SenderMaterialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert connection.settings_dict['NAME'] == ':memory:'
        with connection.schema_editor() as editor:
            editor.create_model(SessionKey)
            editor.create_model(PreDistributedKey)
        cls.a = Node.objects.create(node_id='sender-test', name='A', ip_address='127.0.0.1', port=1)
        cls.b = Node.objects.create(node_id='receiver-test', name='B', ip_address='127.0.0.2', port=2)
        cls.c = Node.objects.create(node_id='outsider-test', name='C', ip_address='127.0.0.3', port=3)
        owner = types.SimpleNamespace(POOL_STATUS_READY_VALUES=('READY', 'unused'))
        cls.consume = staticmethod(production_function('key_pool_service.py', 'consume_key', {
            'PreDistributedKey': PreDistributedKey, 'KeyPoolService': owner, 'timezone': timezone,
            'models': models, 'transaction': transaction, 'C': C, 'logger': logging.getLogger('offline'),
        }, 'KeyPoolService'))

    def setUp(self):
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM ' + connection.ops.quote_name(PreDistributedKey._meta.db_table))

    def item(self, pool, key_hash, **values):
        return PreDistributedKey.objects.create(node1=self.b, node2=self.a, pool_id=pool, key_index=0,
            algorithm='kyber_kem', status=values.get('status', 'READY'), key_hash=key_hash,
            expires_at=values.get('expires_at', timezone.now() + timedelta(hours=1)))

    def test_targeted_resource_skips_legacy_and_cannot_be_consumed_twice(self):
        old = self.item('old-lost-material', 'a' * 64)
        new = self.item('saved-local-material', 'b' * 64)
        result = self.consume(self.a.node_id, self.b.node_id, 'kyber_kem', pool_id=new.pool_id, key_hash=new.key_hash)
        self.assertTrue(result['success'])
        self.assertEqual(result['key_id'], new.pk)
        old.refresh_from_db()
        self.assertEqual(old.status, 'READY')
        again = self.consume(self.a.node_id, self.b.node_id, 'kyber_kem', pool_id=new.pool_id, key_hash=new.key_hash)
        self.assertFalse(again['success'])

    def test_wrong_hash_pair_expiry_and_revocation_cannot_fall_back(self):
        item = self.item('exact', 'b' * 64)
        for sender, receiver, key_hash in [(self.a, self.b, 'c' * 64), (self.c, self.b, item.key_hash)]:
            self.assertFalse(self.consume(sender.node_id, receiver.node_id, 'kyber_kem', pool_id=item.pool_id, key_hash=key_hash)['success'])
        for state in ('REVOKED', 'CONSUMED'):
            PreDistributedKey.objects.filter(pk=item.pk).update(status=state)
            self.assertFalse(self.consume(self.a.node_id, self.b.node_id, 'kyber_kem', pool_id=item.pool_id, key_hash=item.key_hash)['success'])
        PreDistributedKey.objects.filter(pk=item.pk).update(status='READY', expires_at=timezone.now() - timedelta(hours=1))
        self.assertFalse(self.consume(self.a.node_id, self.b.node_id, 'kyber_kem', pool_id=item.pool_id, key_hash=item.key_hash)['success'])

    def test_legacy_callers_without_selection_still_work(self):
        self.item('compatible', 'd' * 64)
        self.assertTrue(self.consume(self.a.node_id, self.b.node_id, 'kyber_kem')['success'])

    def test_service_forwards_exact_selection_without_changing_legacy_calls(self):
        calls = []
        class StopAfterSelection(Exception):
            pass
        def selected(*args, **kwargs):
            calls.append(kwargs)
            raise StopAfterSelection()
        service = production_function('pool_consume_service.py', 'consume_pool_item', {
            'C': C, 'PoolConsumeError': RuntimeError, 'transaction': transaction,
            '_receiver_registry_key': lambda *_args: object(),
            'KeyPoolService': types.SimpleNamespace(consume_key=selected),
        })
        for selection in ({}, {'pool_id': 'chosen', 'key_hash': 'e' * 64}):
            with self.assertRaises(StopAfterSelection):
                service(sender=self.a, receiver=self.b, batch_id='offline', protection_algorithm='KYBER', **selection)
            self.assertEqual(calls[-1], selection)

    def test_falcon_canonical_legacy_empty_and_fingerprint_precedence(self):
        readiness = production_function('serializers.py', 'get_falcon_key_ready', {}, 'NodeListSerializer')
        details = production_function('views.py', 'keys', {
            'hashlib': hashlib, 'SuccessResponse': lambda data, **kw: data,
            'ErrorResponse': lambda **kw: self.fail(str(kw)),
        }, 'NodeViewSet')
        for canonical, legacy in [('new-sign-public', ''), ('', 'legacy-public'), ('new-sign-public', 'legacy-public'), ('', '')]:
            node = Node(node_id='read-only', falcon_sign_public_key=canonical, falcon_public_key=legacy)
            self.assertEqual(readiness(None, node), bool(canonical or legacy))
            result = details(types.SimpleNamespace(get_object=lambda: node), None)
            self.assertEqual(result['falcon_key_ready'], bool(canonical or legacy))
            expected = hashlib.sha256((canonical or legacy).encode()).hexdigest()[:32] if canonical or legacy else ''
            self.assertEqual(result['falcon_public_key_fingerprint'], expected)
            self.assertNotIn('falcon_public_key', result)

    def test_endpoint_validates_selection_and_keeps_real_response_secret_free(self):
        calls = []
        class PoolError(Exception):
            pass
        pool = types.ModuleType('pqkds.pool_consume_service')
        pool.PoolConsumeError = PoolError
        def consume(**kwargs):
            calls.append(kwargs)
            return {'item': types.SimpleNamespace(pk=1, pool_id='chosen', key_index=0, key_hash='e' * 64,
                expires_at=timezone.now() + timedelta(hours=1)), 'recipient_key': types.SimpleNamespace(pk=1, key_id='recipient', key_version=1),
                'session_id': 'isolated-session', 'remaining': 1, 'envelope': {}}
        pool.consume_pool_item = consume
        distribution = types.ModuleType('pqkds.distribution_service')
        distribution.authorized_node_ids = lambda _user: [self.b.pk]
        distribution.record_distribution_chain_event = lambda *_args: 'offline-evidence'
        endpoint = production_function('node_self_views.py', 'node_pool_consume', {
            'Node': Node, 'C': C, 'json': json, 're': re, '_DIST_BATCH_RE': re.compile(r'^dist-\d{14}-[0-9a-f]{8}$'),
            '_find_node': lambda _identity: self.a, '_write_pool_log': lambda *_a, **_kw: None,
            '_ok': lambda data, **kw: data, '_error': lambda message, *a, **kw: {'error': message},
            'logger': logging.getLogger('offline'),
        })
        base = {'peerNodeCode': self.b.node_id, 'batchId': 'dist-20261015000000-1234abcd'}
        with patch.dict(sys.modules, {'pqkds.pool_consume_service': pool, 'pqkds.distribution_service': distribution}):
            for invalid in [{'poolId': 'chosen'}, {'keyHash': 'e' * 64}, {'poolId': [], 'keyHash': 'e' * 64}, {'poolId': 'chosen', 'keyHash': 'bad'}]:
                response = endpoint(types.SimpleNamespace(body=json.dumps({**base, **invalid}).encode()), {'userId': 1})
                self.assertIn('error', response)
            self.assertEqual(calls, [])
            response = endpoint(types.SimpleNamespace(body=json.dumps({**base, 'poolId': 'chosen', 'keyHash': 'e' * 64}).encode()), {'userId': 1})
            self.assertEqual(calls[-1]['pool_id'], 'chosen')
            self.assertEqual(calls[-1]['key_hash'], 'e' * 64)
            self.assertEqual(response['poolId'], 'chosen')
            self.assertNotIn('keyHex', response)


if __name__ == '__main__':
    unittest.main(verbosity=2)
