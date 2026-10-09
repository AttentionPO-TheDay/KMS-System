"""Demo 入口反证：默认关闭、Cookie 不回退、身份/CSRF/租约不可自报。

运行：docker compose run --rm --no-deps dvadmin3-django python tests/test_demo_context.py
只 mock 身份网络与 Redis；不建立/删除业务节点，不修改现有数据。
"""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
import django

django.setup()
from django.test import RequestFactory
from pqkds import demo_context as D


class DemoBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.env = patch.dict(os.environ, {
            'KMS_DEMO_ENABLED': 'true', 'INTERNAL_TOKEN': 'test-internal-only',
            'KMS_DEMO_ALLOWED_HOSTS': '127.0.0.1:8088',
            'KMS_DEMO_ALLOWED_ORIGINS': 'http://127.0.0.1:8088',
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.identity = {'entryMode': 'DEMO', 'principalType': 'ADMIN',
                         'userId': -1, 'userName': 'DEMO_ADMIN', 'roleLevel': 0}

    def request(self, method='GET', **headers):
        base = {'HTTP_HOST': '127.0.0.1:8088', 'HTTP_X_KMS_ENTRY_MODE': 'demo',
                'HTTP_X_KMS_DEMO_GATEWAY': 'test-internal-only',
                'HTTP_X_KMS_DEMO_REVISION': '2', 'HTTP_ORIGIN': 'http://127.0.0.1:8088',
                'HTTP_X_KMS_DEMO_CSRF': 'test-csrf'}
        base.update(headers)
        request = getattr(self.factory, method.lower())('/api/pqkds/admin/node-authorizations/', **base)
        request.COOKIES[D.COOKIE_NAME] = 'opaque-session'
        return request

    def call(self, request, data=None):
        handler = Mock(return_value=D.JsonResponse({'code': 200}))
        with patch.object(D, 'demo_rpc', return_value=data or {'ok': True, **self.identity}) as rpc:
            response = D.DemoContextMiddleware(handler)(request)
        return response, handler, rpc

    def test_off_rejects_even_valid_cookie_and_boundary(self):
        os.environ['KMS_DEMO_ENABLED'] = 'false'
        response, handler, rpc = self.call(self.request())
        self.assertEqual(response.status_code, 404)
        handler.assert_not_called()
        rpc.assert_not_called()

    def test_unmarked_standalone_never_reads_cookie(self):
        response, handler, rpc = self.call(self.request(HTTP_X_KMS_ENTRY_MODE=''))
        self.assertEqual(response.status_code, 200)
        handler.assert_called_once()
        rpc.assert_not_called()

    def test_spoofed_gateway_rejected(self):
        response, handler, _ = self.call(self.request(HTTP_X_KMS_DEMO_GATEWAY='wrong'))
        self.assertEqual(response.status_code, 404)
        handler.assert_not_called()

    def test_host_is_not_sufficient_boundary(self):
        self.assertFalse(D.trusted_demo_request(self.request(HTTP_X_KMS_DEMO_GATEWAY='')))
        self.assertFalse(D.trusted_demo_request(self.request(HTTP_HOST='evil.example')))

    def test_no_demo_cookie_does_not_use_admin_token(self):
        request = self.request(HTTP_AUTHORIZATION='Bearer legacy-admin')
        request.COOKIES.clear()
        response, handler, rpc = self.call(request)
        self.assertEqual(response.status_code, 401)
        handler.assert_not_called()
        rpc.assert_not_called()

    def test_revision_required(self):
        response, handler, _ = self.call(self.request(HTTP_X_KMS_DEMO_REVISION=''))
        self.assertEqual(response.status_code, 401)
        handler.assert_not_called()

    def test_valid_read_projects_authoritative_identity(self):
        request = self.request()
        response, handler, rpc = self.call(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(request.kms_identity['userName'], 'DEMO_ADMIN')
        rpc.assert_called_once_with('introspect', {'sessionId': 'opaque-session', 'revision': 2})

    def test_mutation_requires_origin_and_csrf(self):
        for headers in [{'HTTP_ORIGIN': 'http://evil.example'}, {'HTTP_X_KMS_DEMO_CSRF': ''}]:
            response, handler, rpc = self.call(self.request('POST', **headers))
            self.assertEqual(response.status_code, 409)
            handler.assert_not_called()
            rpc.assert_not_called()

    def test_mutation_requires_actual_lease(self):
        response, handler, _ = self.call(self.request('POST'), {'ok': True, 'identity': self.identity})
        self.assertEqual(response.status_code, 503)
        handler.assert_not_called()

    def test_mutation_releases_lease_after_handler(self):
        request = self.request('POST')
        response, handler, rpc = self.call(request, {'ok': True, 'leaseId': 'lease', 'identity': self.identity})
        self.assertEqual(response.status_code, 200)
        handler.assert_called_once()
        self.assertEqual([c.args[0] for c in rpc.call_args_list],
                         ['lease/acquire', 'lease/validate', 'lease/release'])

    def test_failed_validation_stops_success_response_and_releases(self):
        handler = Mock(return_value=D.JsonResponse({'code': 200}))
        with patch.object(D, 'demo_rpc', side_effect=[
                {'ok': True, 'leaseId': 'lease', 'identity': self.identity},
                D.kms.KmsTokenInvalid('expired'), {'ok': True}]) as rpc:
            response = D.DemoContextMiddleware(handler)(self.request('POST'))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(rpc.call_args_list[-1].args[0], 'lease/release')

    def test_admin_has_no_node(self):
        identity = {**self.identity, 'nodeId': 'Node-A'}
        response, handler, _ = self.call(self.request(), {'ok': True, **identity})
        self.assertEqual(response.status_code, 403)
        handler.assert_not_called()

    def test_unrelated_endpoint_not_opened(self):
        request = self.request()
        request.path = '/api/system/user/'
        response, handler, _ = self.call(request)
        self.assertEqual(response.status_code, 403)
        handler.assert_not_called()

    def test_demo_admin_cannot_reissue_activation(self):
        request = self.request('POST')
        request.path = '/api/pqkds/nodes/Node-A/reissue_activation_code/'
        response, handler, _ = self.call(request, {'ok': True, 'leaseId': 'lease', 'identity': self.identity})
        self.assertEqual(response.status_code, 403)
        handler.assert_not_called()

    def test_node_pool_metadata_read_allowed_but_legacy_work_rejected(self):
        identity = {'entryMode': 'DEMO', 'principalType': 'NODE', 'userId': 42, 'nodeId': 'Node-A'}
        node = Mock(node_id='Node-A')
        request = self.request()
        request.path = '/api/pqkds/key-pool/'
        with patch('pqkds.models.Node.objects.filter') as query, patch('pqkds.node_self_views._public_status', return_value='ACTIVE'):
            query.return_value.first.return_value = node
            self.assertIsNone(D._check_scope(request, identity))
        request.method = 'POST'
        request.path = '/api/pqkds/key-pool/generate/'
        self.assertEqual(D._check_scope(request, identity).status_code, 403)

    def test_internal_lookup_requires_internal_secret_and_enable(self):
        request = self.factory.get('/internal/demo/node/', {'nodeId': 'Node-A'})
        self.assertEqual(D.internal_node_context(request).status_code, 403)
        request.META['HTTP_X_INTERNAL_TOKEN'] = 'test-internal-only'
        request.GET = request.GET.copy()
        request.GET['nodeId'] = '../bad'
        self.assertEqual(D.internal_node_context(request).status_code, 400)


if __name__ == '__main__':
    unittest.main(verbosity=2)
