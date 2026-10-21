"""Actual registration/view/storage flow on SQLite :memory:; no ledger writes."""
import ast
import hashlib
import json
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
import pqkds.test_fabric_bindings_offline as fixture
from django.db import connection
from django.http import JsonResponse
from django.test import RequestFactory
from pqkds import api_contract as C
from pqkds import node_key_did as service
from pqkds import node_key_registry as registry
from pqkds.fabric_did_client import BindingError
from pqkds.models import Node, NodeKeyDidRecord, NodeLongTermKey
from pqkds.node_key_payloads import long_term_key_payload

with connection.schema_editor() as editor:
    editor.create_model(NodeKeyDidRecord)

ENV = {'FABRIC_DID_NODE_KEYGEN_ENABLED': 'true', 'FABRIC_DID_CHAIN_ID': 'offline',
       'INTERNAL_TOKEN': 'offline-only', 'KMS_CHAIN_BACKEND': 'legacy',
       'KMS_CHAIN_WRITES_ENABLED': 'false'}


class Bridge:
    def __init__(self):
        self.calls, self.plans, self.failures = [], {}, {}

    def prepare_sys_pid(self, request_id):
        self.calls.append(('prepare', str(request_id)))
        self.fail('prepare')
        seed = hashlib.sha256(str(request_id).encode()).hexdigest()
        row = dict(provider='FABRIC_DID', chainId='offline', requestId=str(request_id),
                   sysPid=(seed * 3)[:182], txId=seed, did='did:offline:' + seed,
                   status='PREPARED', submitted=False)
        self.plans[row['sysPid']] = row
        return dict(row)

    def fail(self, operation):
        if operation in self.failures:
            raise BindingError(self.failures.pop(operation))

    def submit_sys_pid(self, sys_pid):
        self.calls.append(('submit', sys_pid))
        record = NodeKeyDidRecord.objects.get(sys_pid=sys_pid)
        assert record.submit_started and not connection.in_atomic_block
        self.fail('submit')
        return self.confirm(sys_pid)

    def verify_sys_pid(self, sys_pid):
        self.calls.append(('verify', sys_pid))
        self.fail('verify')
        return self.confirm(sys_pid)

    def confirm(self, sys_pid):
        return dict(self.plans[sys_pid], status='CONFIRMED', transactionValid=True, metadataMatches=True)

    def close(self):
        pass


class DidTests(unittest.TestCase):
    def setUp(self):
        if connection.settings_dict['NAME'] != ':memory:':
            raise RuntimeError('Refusing non-memory database')
        with connection.cursor() as cursor:
            for model in (NodeKeyDidRecord, fixture.ChainKeyBinding, NodeLongTermKey, Node):
                cursor.execute('DELETE FROM ' + model._meta.db_table)
        self.env = patch.dict(os.environ, ENV, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.node = Node.objects.create(node_id='A', name='A', status='active', ip_address='127.0.0.1', port=1, sys_user_id=102)
        self.bridge = Bridge()
        self.factory = lambda: self.bridge

    def key(self, key_id='browser-key'):
        return registry.register_public_key(self.node, algorithm='SSCL', public_key='04aabbcc', key_id=key_id)

    def test_same_key_is_idempotent_and_other_generation_gets_distinct_syspid(self):
        key = self.key()
        one = service.register(key, self.factory)
        self.assertEqual(one['status'], 'CONFIRMED')
        self.assertEqual(service.register(key, self.factory)['sysPid'], one['sysPid'])
        self.assertEqual(len(self.bridge.calls), 2)
        two = service.register(self.key('another-key'), self.factory)
        self.assertNotEqual(one['sysPid'], two['sysPid'])
        self.assertNotEqual(one['requestId'], two['requestId'])
        self.assertEqual(long_term_key_payload(key)['sysPid'], one['sysPid'])
        self.assertNotIn('nonce', json.dumps(one))

    def test_prepare_timeout_retries_same_persisted_request(self):
        key = self.key()
        self.bridge.failures['prepare'] = 'BRIDGE_TIMEOUT'
        first = service.register(key, self.factory)
        self.assertEqual(first['status'], 'PREPARE_FAILED')
        self.assertFalse(first['sysPid'])
        self.assertEqual(service.register(key, self.factory)['requestId'], first['requestId'])
        self.assertEqual(self.bridge.calls[0], self.bridge.calls[1])

    def test_submission_timeout_keeps_identifier_and_only_verifies_original(self):
        self.bridge.failures['submit'] = 'BRIDGE_TIMEOUT'
        key = self.key()
        first = service.register(key, self.factory)
        self.assertEqual(first['status'], 'PENDING_VERIFICATION')
        self.assertIsNone(first['transactionValid'])
        second = service.register(key, self.factory)
        self.assertEqual(first['sysPid'], second['sysPid'])
        self.assertEqual(first['txId'], second['txId'])
        self.assertEqual(second['status'], 'CONFIRMED')
        self.assertEqual([op for op, _ in self.bridge.calls], ['prepare', 'submit', 'verify'])

    def test_incomplete_or_foreign_confirmation_never_passes(self):
        for case in ('identity', 'missing_flags'):
            with self.subTest(case=case):
                bridge = Bridge()
                original = bridge.submit_sys_pid
                def wrong(sys_pid):
                    data = original(sys_pid)
                    data.update({'txId': 'f' * 64} if case == 'identity' else {'metadataMatches': None})
                    return data
                bridge.submit_sys_pid = wrong
                result = service.register(self.key(case), lambda: bridge)
                self.assertEqual(result['status'], 'PENDING_VERIFICATION')
                self.assertIsNone(result['transactionValid'])

    def test_concurrent_request_does_not_allocate_again(self):
        key = self.key()
        from datetime import timedelta
        from django.utils import timezone
        record = NodeKeyDidRecord.objects.create(key=key, lease_token='busy', lease_expires_at=timezone.now() + timedelta(seconds=60))
        result = service.register(key, self.factory)
        self.assertEqual(result['requestId'], str(record.request_id))
        self.assertFalse(self.bridge.calls)

    def view_namespace(self):
        tree = ast.parse((BACKEND / 'pqkds/node_self_views.py').read_text(encoding='utf-8-sig'))
        names = {'node_self_keys', '_as_bool', '_public_status', '_ok', '_error'}
        selected = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        for item in selected:
            item.decorator_list = []
        def store(_self, algorithm, public_key, *args, **kwargs):
            key = registry.register_public_key(self.node, algorithm=algorithm, public_key=public_key,
                                               key_id=kwargs['key_id'], key_version=kwargs['key_version'])
            return dict(success=True, key_pk=key.pk, algorithm=key.algorithm, key_id=key.key_id,
                        key_version=key.key_version, status=key.status)
        namespace = dict(__name__='pqkds.offline_browser_views', __package__='pqkds', json=json,
                         JsonResponse=JsonResponse, C=C, Node=Node, NodeLongTermKey=NodeLongTermKey,
                         NodeService=type('Service', (), {'__init__': lambda self, node_id: None, 'store_node_public_key': store}),
                         _find_node=lambda identity: self.node,
                         _node_payload=lambda node, context: {'nodeId': node.node_id},
                         _long_term_keys_payload=lambda node: [long_term_key_payload(k) for k in NodeLongTermKey.objects.filter(node=node)])
        exec(compile(ast.Module(body=selected, type_ignores=[]), 'actual_browser_registration', 'exec'), namespace)
        return namespace

    def test_actual_registration_view_returns_syspid_and_get_restores_it(self):
        ns = self.view_namespace()
        request = RequestFactory().post('/node-self/keys/', json.dumps(dict(
            algorithm='SSCL', publicKey='04aabbcc', keyId='from-ui', keyVersion=1, didOnchain=True)), content_type='application/json')
        with patch.object(service, 'FabricDidClient', self.factory):
            response = ns['node_self_keys'](request, {'userId': 102})
        body = json.loads(response.content)
        self.assertEqual(body['code'], 200)
        self.assertEqual(body['data']['didOnchain']['status'], 'CONFIRMED')
        self.assertTrue(body['data']['sysPid'])
        reread = ns['node_self_keys'](RequestFactory().get('/node-self/keys/'), {'userId': 102})
        self.assertEqual(json.loads(reread.content)['data']['keys'][0]['sysPid'], body['data']['sysPid'])

    def test_nonpage_registration_does_not_submit(self):
        ns = self.view_namespace()
        request = RequestFactory().post('/', json.dumps(dict(algorithm='SSCL', publicKey='04aabbcc', keyId='init', keyVersion=1)), content_type='application/json')
        factory = Mock(side_effect=AssertionError('Initialization must not submit'))
        with patch.object(service, 'FabricDidClient', factory):
            response = ns['node_self_keys'](request, {'userId': 102})
        self.assertEqual(json.loads(response.content)['code'], 200)
        self.assertEqual(NodeKeyDidRecord.objects.count(), 0)

    def test_query_is_scoped_to_node_and_never_submits(self):
        self.bridge.failures['submit'] = 'BRIDGE_TIMEOUT'
        first = service.register(self.key(), self.factory)
        ns = self.view_namespace()
        shim = types.ModuleType('pqkds.node_self_views')
        for name in ('_find_node', '_ok', '_error', '_public_status'):
            setattr(shim, name, ns[name])
        tree = ast.parse((BACKEND / 'pqkds/node_key_did_views.py').read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef))
        fn.decorator_list = []
        query_ns = dict(__name__='pqkds.offline_query', __package__='pqkds', service=service,
                        NodeKeyDidRecord=NodeKeyDidRecord, NodeLongTermKey=NodeLongTermKey, re=__import__('re'), json=json)
        exec(compile(ast.Module(body=[fn], type_ignores=[]), 'actual_query', 'exec'), query_ns)
        request = RequestFactory().get('/', {'sysPid': first['sysPid']})
        with patch.dict(sys.modules, {'pqkds.node_self_views': shim}), patch.object(service, 'FabricDidClient', self.factory):
            result = query_ns['node_self_key_did'](request, {'userId': 102})
            self.assertEqual(json.loads(result.content)['data']['status'], 'CONFIRMED')
            foreign = Node.objects.create(node_id='B', name='B', status='active', ip_address='127.0.0.1', port=2)
            shim._find_node = lambda identity: foreign
            result = query_ns['node_self_key_did'](request, {'userId': 103})
            self.assertEqual(json.loads(result.content)['code'], 404)
        self.assertEqual([op for op, _ in self.bridge.calls], ['prepare', 'submit', 'verify'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
