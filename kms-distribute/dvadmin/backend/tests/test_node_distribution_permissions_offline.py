"""Exercise production permission/endpoint code without Django startup or a database."""
import ast
import json
import logging
import runpy
import types
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1] / 'pqkds'
C = types.SimpleNamespace(**runpy.run_path(str(ROOT / 'api_contract.py')))
P = types.SimpleNamespace(**runpy.run_path(str(ROOT / 'node_permission.py')))


def endpoint_functions(context):
    tree = ast.parse((ROOT / 'node_self_views.py').read_text(encoding='utf-8'))
    names = {'_error', '_ok', 'node_self_distributions'}
    functions = [item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name in names]
    for item in functions:
        item.decorator_list = []
    exec(compile(ast.fix_missing_locations(ast.Module(body=functions, type_ignores=[])),
                 'node_self_views.py', 'exec'), context)
    return context['node_self_distributions']


class NodeDistributionPermissionTests(unittest.TestCase):
    def setUp(self):
        self.sender = types.SimpleNamespace(id=5, node_id='A', permission_level='L1')
        self.receiver = types.SimpleNamespace(id=6, node_id='B', name='Node B')
        self.identity = {'userId': 103}
        self.mapping = Mock(return_value=self.sender)
        self.authorization = Mock(return_value=[6])
        key = types.SimpleNamespace(key_id='B-KYBER-test', key_version=1)
        self.service = Mock(return_value={
            'recipient_key': key, 'signing_key': key, 'batch_id': 'test-batch',
            'protection_algorithm': 'KYBER', 'wrapping_algorithm': 'KYBER',
            'key_hash': 'a' * 64, 'session_count': 1, 'chain_hash': '',
            'expires_at': types.SimpleNamespace(isoformat=lambda: '2099-01-01T00:00:00'),
            'signature_verified': True,
        })
        self.node_model = Mock()
        self.node_model.objects.filter.return_value.first.return_value = self.receiver
        self.endpoint = endpoint_functions({
            'json': json, 'C': C, 'Node': self.node_model, '_find_node': self.mapping,
            'JsonResponse': lambda data, **kwargs: data, 'logger': logging.getLogger(__name__),
            'CAP_DISTRIBUTE': P.CAP_DISTRIBUTE, 'require_capability': P.require_capability,
            'NodePermissionError': P.NodePermissionError, 'authorized_node_ids': self.authorization,
            'create_node_distribution': self.service,
        })

    def call(self):
        return self.endpoint(types.SimpleNamespace(body=json.dumps({
            'receiverNodeId': 'B', 'protectionAlgorithm': 'KYBER',
            'recipientKeyId': 'B-KYBER-test', 'recipientKeyVersion': 1,
        }).encode()), self.identity)

    def test_l1_with_communication_authorization_reports_capability_not_binding(self):
        result = self.call()
        self.assertEqual(result['code'], 403)
        self.assertEqual(result['data']['error_code'], C.ERR_NODE_CAPABILITY_REQUIRED)
        self.assertIn('L1', result['msg'])
        self.service.assert_not_called()
        self.assertEqual(C.ERROR_HTTP_STATUS[C.ERR_NODE_CAPABILITY_REQUIRED], 403)
        self.assertIn('节点管理', C.ERROR_HINTS[C.ERR_NODE_CAPABILITY_REQUIRED])

    def test_l2_and_l3_reach_service_with_server_resolved_sender(self):
        for level in ('L2', 'L3'):
            with self.subTest(level=level):
                self.sender.permission_level = level
                self.service.reset_mock()
                self.assertEqual(self.call()['code'], 200)
                self.assertIs(self.service.call_args.args[0], self.sender)
                self.assertIs(self.service.call_args.args[1], self.receiver)
                self.assertEqual(self.service.call_args.kwargs['recipient_key_id'], 'B-KYBER-test')
                self.node_model.objects.filter.assert_called_with(node_id='B')
                self.authorization.assert_called_with(103)

    def test_l2_without_communication_authorization_still_denied(self):
        self.sender.permission_level = 'L2'
        self.authorization.return_value = []
        result = self.call()
        self.assertEqual(result['data']['error_code'], C.ERR_NOT_AUTHORIZED)
        self.service.assert_not_called()

    def test_missing_node_mapping_still_denied(self):
        self.mapping.return_value = None
        result = self.call()
        self.assertEqual(result['data']['error_code'], C.ERR_NOT_AUTHORIZED)
        self.assertIn('未关联', result['msg'])
        self.service.assert_not_called()

    def test_unknown_level_remains_least_privilege(self):
        self.sender.permission_level = 'invalid'
        self.assertEqual(self.call()['data']['error_code'], C.ERR_NODE_CAPABILITY_REQUIRED)
        self.service.assert_not_called()


if __name__ == '__main__':
    unittest.main()
