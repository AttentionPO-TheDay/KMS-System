"""In-memory isolation regression. Native TrapGen material, no business writes."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pqkds.test_fabric_bindings_offline as fixture
from pqkds.models import Node, NodeLongTermKey
from pqkds import node_key_registry as registry, wrappers
from pqkds.api_contract import NODE_PUBLIC_KEY_COLUMN


class FalconIsolationTests(unittest.TestCase):
    def test_encryption_is_not_a_signing_mirror_and_wrapper_reads_registry(self):
        self.assertNotIn('FALCON_CL_V1', NODE_PUBLIC_KEY_COLUMN)
        node = Node.objects.create(node_id='isolated-falcon', name='Test', ip_address='127.0.0.1', port=1,
                                   falcon_sign_public_key='signing', falcon_public_key='legacy-signing')
        registry._write_node_column(node, 'FALCON_CL_V1', 'encryption')
        node.refresh_from_db()
        self.assertEqual(node.falcon_sign_public_key, 'signing')
        self.assertEqual(node.falcon_public_key, 'legacy-signing')
        key = NodeLongTermKey.objects.create(node=node, algorithm='FALCON_CL_V1', key_id='enc',
                                            key_version=1, status='ACTIVE', public_key='registry-encryption')
        # Revoke the signing mirror. Independent encryption must remain available.
        registry._write_node_column(node, 'FALCON', '')
        with patch.object(wrappers, 'wrap_with_public_key', return_value=('envelope', 'hash')) as wrap:
            self.assertEqual(wrappers.wrap_for_node(bytes(range(16)), node, 'falcon_cl_v1'), ('envelope', 'hash'))
            self.assertEqual(wrap.call_args.args[1], 'registry-encryption')
        key.status = 'REVOKED'
        key.save()
        with self.assertRaises(wrappers.WrapperError):
            wrappers.wrap_for_node(bytes(range(16)), node, 'falcon_cl_v1')


if __name__ == '__main__':
    unittest.main()
