import inspect
import json
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from django.test import RequestFactory
from . import node_self_views as views


class NodeSelfCapabilitiesTests(TestCase):
    def check_denied(self, view, level, body):
        node = SimpleNamespace(permission_level=level, status='ACTIVE')
        request = RequestFactory().post('/node-self/', data=json.dumps(body), content_type='application/json')
        with patch.object(views, '_find_node', return_value=node):
            response = inspect.unwrap(view)(request, {'userId': 1})
        result = json.loads(response.content)
        self.assertEqual(result['code'], 403, result)
        self.assertEqual(result['data']['error_code'], 'NODE_CAPABILITY_REQUIRED', result)

    def test_l1_cannot_generate_register_revoke_or_distribute(self):
        self.check_denied(views.node_self_keygen_issuances, 'L1', {})
        self.check_denied(views.node_self_keys, 'L1', {'algorithm':'SM2','publicKey':'00','keyVersion':1})
        self.check_denied(views.node_self_revoke_key, 'L1', {})
        self.check_denied(views.node_pool_preallocate, 'L1', {})
        self.check_denied(views.node_pool_consume, 'L1', {})

    def test_l2_cannot_rotate_by_omitting_rotate_flag_or_revoke(self):
        for body in [{'algorithm':'SM2','publicKey':'00','keyVersion':2},
                     {'algorithm':'SM2','publicKey':'00','keyVersion':2,'rotate':True}]:
            self.check_denied(views.node_self_keys, 'L2', body)
        self.check_denied(views.node_self_revoke_key, 'L2', {})
        self.check_denied(views.node_self_auto_update, 'L2', {})
