"""Initialization contract, in-memory DB only, no external chain calls."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pqkds.test_fabric_bindings_offline as fixture
from pqkds.models import Node, NodeLongTermKey
from pqkds.node_service import NodeService
from pqkds import distribution_service


class CompleteInitializationTests(unittest.TestCase):
    def service(self, name, status='pending_init'):
        node = Node.objects.create(node_id=name, name=name, ip_address='127.0.0.1', port=1,
                                   status=status, kyber_public_key='kem', gm_public_key='sm2',
                                   sscl_public_key='sscl', falcon_sign_public_key='sign')
        service = NodeService.__new__(NodeService)
        service.node, service.node_id = node, name
        service.upload_service = Mock()
        service.upload_service.upload_node_registration.return_value = {'success': True}
        return service

    @patch('pqkds.keygen_issuance.falcon_cl_enabled', return_value=True)
    def test_enabled_requires_valid_encryption_before_activation(self, _enabled):
        service = self.service('complete-init')
        self.assertFalse(service.initialize_base_keys()['success'])
        service.node.refresh_from_db()
        self.assertEqual(service.node.status, 'pending_init')
        NodeLongTermKey.objects.create(node=service.node, algorithm='FALCON_CL_V1', key_id='enc',
                                       key_version=1, status='ACTIVE', public_key='invalid')
        self.assertFalse(service.initialize_base_keys()['success'])
        with patch('pqkds.falcon_cl_v1.parse_material', return_value={}):
            result = service.initialize_base_keys()
        self.assertTrue(result['success'])
        self.assertEqual(len(result['completed']), 5)

    @patch('pqkds.keygen_issuance.falcon_cl_enabled', return_value=True)
    def test_existing_active_without_encryption_is_not_reset(self, _enabled):
        service = self.service('existing-active', 'active')
        self.assertTrue(service.initialize_base_keys()['already_initialized'])
        service.upload_service.upload_node_registration.assert_not_called()

    @patch('pqkds.keygen_issuance.falcon_cl_enabled', return_value=False)
    def test_disabled_feature_preserves_four_key_initialization(self, _enabled):
        result = self.service('disabled-feature').initialize_base_keys()
        self.assertTrue(result['success'])
        self.assertEqual(len(result['completed']), 4)

    @patch('pqkds.keygen_issuance.falcon_cl_enabled', return_value=True)
    def test_distribution_validates_recipient_encryption_and_sender_signing_only(self, _enabled):
        sender = SimpleNamespace(node_id='sender')
        receiver = SimpleNamespace(node_id='receiver')
        # Stop after version checks, before any envelope/DB write.
        with patch.object(distribution_service, 'require_key_version') as version, \
                patch.object(distribution_service, '_as_batch_id', side_effect=RuntimeError('stop-before-write')):
            with self.assertRaisesRegex(RuntimeError, 'stop-before-write'):
                distribution_service.create_node_distribution(sender, receiver,
                    protection_algorithm='FALCON_CL_V1', recipient_key_id='enc', recipient_key_version=1,
                    batch_id='batch', expires_at=None, envelope={}, signature='sig',
                    falcon_key_id='sign', falcon_key_version=1, key_hash='hash')
        self.assertEqual(version.call_count, 2)
        self.assertEqual(version.call_args_list[0].args, (receiver, 'FALCON_CL_V1', 'enc', 1))
        self.assertEqual(version.call_args_list[1].args, (sender, 'FALCON', 'sign', 1))


if __name__ == '__main__':
    unittest.main()
