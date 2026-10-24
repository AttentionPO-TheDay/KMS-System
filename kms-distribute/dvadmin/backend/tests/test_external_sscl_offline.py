"""Real models, transactions, API and SSCL composition on SQLite; fake ledger only."""
import hashlib
import ast
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from datetime import timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import test_node_key_did_offline as fixture
from cryptography.fernet import Fernet
from django.db import connection
from django.test import RequestFactory
from django.utils import timezone
from pqkds import external_sscl as service
from pqkds.external_sscl_views import external_node_activation
from pqkds.models import ExternalNodeActivation, Node, NodeKeyDidRecord, NodeLongTermKey
from pqkds.sm2_crypto import SM2Crypto, SM2_N

with connection.schema_editor() as editor:
    editor.create_model(ExternalNodeActivation)


def share_for(identity, ua):
    # Independent degree-two polynomial: interpolation must recover its constant 7.
    f = lambda x: (7 + 3 * x + 2 * x * x) % SM2_N
    return dict(identity=identity, ua=ua, xIndex=[format(i, '064x') for i in range(1, 11)],
                yIndex=[format(f(i), '064x') for i in range(1, 11)],
                SSCLKey='04' + format(11, '064x') + format(f(11), '064x'),
                PPub=SM2Crypto.public_key_of(format(13, '064x')))


class ExternalTests(unittest.TestCase):
    def setUp(self):
        if connection.settings_dict['NAME'] != ':memory:':
            raise RuntimeError('Refusing non-memory database')
        with connection.cursor() as cursor:
            for model in (ExternalNodeActivation, NodeKeyDidRecord, fixture.fixture.ChainKeyBinding, NodeLongTermKey, Node):
                cursor.execute('DELETE FROM ' + model._meta.db_table)
        self.environment = patch.dict(os.environ, dict(fixture.ENV, KMS_EXTERNAL_SSCL_ENABLED='true'), clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.api_token = 'offline-client-token-that-is-at-least-32-characters'
        self.config = Path(self.temp.name) / 'config.json'
        # Keep the exact Fernet key in configuration; tests never use a production key.
        key = Fernet.generate_key()
        self.cipher = Fernet(key)
        self.config.write_text(json.dumps({'encryptionKey': key.decode(), 'clients': {'platform-a': hashlib.sha256(self.api_token.encode()).hexdigest()}}))
        os.environ['KMS_EXTERNAL_SSCL_CONFIG'] = str(self.config)
        self.generator = Mock(side_effect=share_for)
        self.bridge = fixture.Bridge()

    def activate(self, name='待激活节点一', client='platform-a'):
        return service.activate(client, name, self.cipher, algorithm='SSCL', generator=self.generator, did_factory=lambda: self.bridge)

    def activate_sm2(self, name='SM2节点一', client='platform-a'):
        return service.activate(client, name, self.cipher, generator=self.generator, did_factory=lambda: self.bridge)

    def test_default_sm2_key_matches_standard_base_point_and_registers_sm2(self):
        with patch.object(service.secrets, 'randbelow', return_value=0):
            data, status = self.activate_sm2()
        material = service.private_key('platform-a', self.cipher, sys_pid=data['sysPid'])
        self.assertEqual(status, 200)
        self.assertEqual(data['algorithm'], 'SM2')
        self.assertEqual(data['curve'], 'sm2p256v1')
        self.assertEqual(data['initializationProfile'], 'EXTERNAL_SM2')
        self.assertEqual(material, {'privateKey': '0' * 63 + '1', 'curve': 'sm2p256v1'})
        expected = ('0432c4ae2c1f1981195f9904466a39c9948fe30bbff2660be1715a4589334c74c7'
                    'bc3736a2f4f6779c59bdcee36b692153d0a9877cc62a474002df32e52139f0a0')
        self.assertEqual(data['publicKey'], expected)
        row = ExternalNodeActivation.objects.get()
        self.assertEqual(row.key.algorithm, 'SM2')
        self.assertEqual(row.node.gm_public_key, expected)
        self.assertFalse(row.node.sscl_public_key)
        self.assertNotIn(material['privateKey'], row.encrypted_material)
        self.assertNotIn('domainPublicKey', material)
        self.generator.assert_not_called()

    def test_sm2_public_private_pair_encrypts_and_decrypts_protocol_message(self):
        data, _ = self.activate_sm2()
        material = service.private_key('platform-a', self.cipher, sys_pid=data['sysPid'])
        message = 'SM2协议互通验证'.encode('utf-8')
        envelope = SM2Crypto.encrypt(data['publicKey'], message)
        self.assertEqual(SM2Crypto.decrypt(material['privateKey'], envelope), message)
        self.generator.assert_not_called()

    def test_sm2_retry_and_sys_pid_lookup_preserve_original_pair_and_transaction(self):
        one, _ = self.activate_sm2()
        private = service.private_key('platform-a', self.cipher, name=one['nodeName'])
        two, _ = self.activate_sm2()
        self.assertEqual(one, two)
        self.assertEqual(service.query('platform-a', sys_pid=one['sysPid']), one)
        self.assertEqual(service.private_key('platform-a', self.cipher, sys_pid=one['sysPid']), private)
        self.assertEqual(NodeLongTermKey.objects.count(), 1)
        self.assertEqual([op for op, _ in self.bridge.calls], ['prepare', 'submit'])
        self.generator.assert_not_called()

    def test_same_name_sm2_and_legacy_sscl_keep_distinct_keys_sys_pids_and_hashes(self):
        old, _ = self.activate(name='same-name')
        old_private = service.private_key('platform-a', self.cipher, sys_pid=old['sysPid'])
        new, _ = self.activate_sm2(name='same-name')
        self.assertNotEqual(old['nodeId'], new['nodeId'])
        self.assertNotEqual(old['keyId'], new['keyId'])
        self.assertNotEqual(old['sysPid'], new['sysPid'])
        self.assertEqual(service.query('platform-a', 'same-name'), new)
        self.assertEqual(service.query('platform-a', 'same-name', algorithm='SSCL'), old)
        self.assertEqual(service.query('platform-a', sys_pid=old['sysPid']), old)
        self.assertEqual(service.private_key('platform-a', self.cipher, sys_pid=old['sysPid']), old_private)
        legacy_hash = hashlib.sha256(json.dumps(['platform-a', 'same-name'], ensure_ascii=False,
                                               separators=(',', ':')).encode('utf-8')).hexdigest()
        self.assertEqual(service.identity_hash('platform-a', 'same-name', 'SSCL'), legacy_hash)
        self.assertEqual(NodeLongTermKey.objects.count(), 2)
        self.generator.assert_called_once()

    def test_explicit_sm2_on_legacy_sys_pid_rejects_algorithm_mismatch(self):
        old, _ = self.activate()
        with self.assertRaises(service.ActivationError) as caught:
            service.query('platform-a', sys_pid=old['sysPid'], algorithm='SM2')
        self.assertEqual(caught.exception.code, 'EXTERNAL_KEY_ALGORITHM_MISMATCH')
        with self.assertRaises(service.ActivationError):
            service.private_key('platform-a', self.cipher, sys_pid=old['sysPid'], algorithm='SM2')

    def test_http_defaults_to_sm2_and_delivers_private_pair(self):
        factory = RequestFactory()
        body = json.dumps({'nodeName': 'default-sm2', 'includePrivateKey': True})
        request = factory.post('/external-api/v1/nodes/activate/', body, content_type='application/json',
                               HTTP_AUTHORIZATION='Bearer ' + self.api_token)
        with patch.object(service, 'issue_partial', self.generator), patch.object(service.node_key_did, 'FabricDidClient', return_value=self.bridge):
            response = external_node_activation(request)
        data = json.loads(response.content)['data']
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['algorithm'], 'SM2')
        self.assertEqual(SM2Crypto.public_key_of(data['privateKey']), data['publicKey'])
        self.assertNotIn('domainPublicKey', data)
        self.generator.assert_not_called()

    def test_invalid_algorithms_and_duplicate_selectors_are_rejected(self):
        factory = RequestFactory()
        for algorithm in ('sm2', 'RSA', '', None, True):
            request = factory.post('/external-api/v1/nodes/activate/', json.dumps({'nodeName': 'invalid', 'algorithm': algorithm}),
                                   content_type='application/json', HTTP_AUTHORIZATION='Bearer ' + self.api_token)
            self.assertEqual(external_node_activation(request).status_code, 400)
        request = factory.get('/external-api/v1/nodes/activate/', {'nodeName': 'invalid', 'algorithm': ['SM2', 'SSCL']},
                              HTTP_AUTHORIZATION='Bearer ' + self.api_token)
        self.assertEqual(external_node_activation(request).status_code, 400)
        self.assertEqual(Node.objects.count(), 0)

    def test_sm2_corrupt_private_material_never_exports_or_regenerates(self):
        data, _ = self.activate_sm2()
        row = ExternalNodeActivation.objects.get()
        original = service.unseal(self.cipher, row)
        for private in ('0' * 64, format(SM2_N - 1, '064x'), format((int(original['privateKey'], 16) + 1) % SM2_N, '064x')):
            row.encrypted_material = service.seal(self.cipher, dict(original, privateKey=private))
            row.save()
            with self.assertRaises(service.ActivationError) as caught:
                service.private_key('platform-a', self.cipher, sys_pid=data['sysPid'])
            self.assertEqual(caught.exception.code, 'EXTERNAL_PRIVATE_MATERIAL_UNAVAILABLE')
        self.assertEqual(NodeLongTermKey.objects.count(), 1)
        self.generator.assert_not_called()

    def test_activation_registers_only_sscl_and_keeps_private_material_encrypted(self):
        data, status = self.activate()
        self.assertEqual(status, 200)
        self.assertEqual(data['nodeStatus'], 'ACTIVE')
        self.assertEqual(data['publicKeyRegistrationStatus'], 'REGISTERED')
        self.assertEqual(data['publicKeyStatus'], 'ACTIVE')
        self.assertEqual(len(data['sysPid']), 182)
        self.assertTrue(data['didConfirmed'])
        self.assertTrue(SM2Crypto.is_valid_public_key(data['publicKey']))
        row = ExternalNodeActivation.objects.get()
        material = service.unseal(self.cipher, row)
        self.assertNotIn(material['privateKey'], row.encrypted_material)
        self.assertNotIn(material['privateKey'], json.dumps(data))
        self.assertNotIn(material['clientSecret'], json.dumps(data))
        self.assertEqual(NodeLongTermKey.objects.count(), 1)
        self.assertEqual(row.node.initialization_profile, 'EXTERNAL_SSCL')
        self.assertFalse(row.node.sscl_private_key)
        self.assertFalse(row.node.kyber_public_key)
        expected = (13 * int(material['privateKey'], 16)) % SM2_N
        self.assertEqual(data['publicKey'], SM2Crypto.public_key_of(format(expected, '064x')))
        self.assertEqual(int(material['privateKey'], 16), (int(material['clientSecret'], 16) + 77) % SM2_N)

    def test_retry_reuses_key_sys_pid_and_transaction_without_another_generation(self):
        one, _ = self.activate()
        two, _ = self.activate()
        self.assertEqual(one, two)
        self.generator.assert_called_once()
        self.assertEqual(len(self.bridge.calls), 2)
        self.assertEqual(Node.objects.count(), 1)

    def test_platforms_and_exact_names_are_isolated(self):
        one, _ = self.activate(name='Node-A')
        two, _ = self.activate(name='Node-A', client='platform-b')
        three, _ = self.activate(name='node-a')
        self.assertEqual(len({one['nodeId'], two['nodeId'], three['nodeId']}), 3)
        with self.assertRaises(service.ActivationError) as caught:
            service.query('other-platform', 'Node-A')
        self.assertEqual(caught.exception.code, 'EXTERNAL_NODE_NOT_FOUND')

    def test_preexisting_browser_node_with_same_display_name_is_not_taken_over(self):
        ordinary = Node.objects.create(node_id='A', name='shared-name', ip_address='127.0.0.1', port=1)
        data, _ = self.activate(name='shared-name')
        ordinary.refresh_from_db()
        self.assertNotEqual(data['nodeId'], ordinary.node_id)
        self.assertEqual(ordinary.initialization_profile, 'FULL')
        self.assertFalse(ordinary.sscl_public_key)

    def test_bridge_submit_timeout_preserves_public_key_and_identifier_then_only_verifies(self):
        self.bridge.failures['submit'] = 'BRIDGE_TIMEOUT'
        one, status = self.activate()
        self.assertEqual(status, 202)
        self.assertEqual(one['publicKeyRegistrationStatus'], 'REGISTERED')
        self.assertFalse(one['didConfirmed'])
        two, status = self.activate()
        self.assertEqual(status, 200)
        self.assertEqual(one['sysPid'], two['sysPid'])
        self.generator.assert_called_once()
        self.assertEqual([op for op, _ in self.bridge.calls], ['prepare', 'submit', 'verify'])

    def test_prepare_timeout_reuses_key_and_persisted_request_id(self):
        self.bridge.failures['prepare'] = 'BRIDGE_TIMEOUT'
        one, status = self.activate()
        self.assertEqual(status, 202)
        self.assertEqual(one['publicKeyRegistrationStatus'], 'REGISTERED')
        self.assertFalse(one['sysPid'])
        two, status = self.activate()
        self.assertEqual(status, 200)
        self.assertEqual(one['keyId'], two['keyId'])
        self.assertEqual(self.bridge.calls[0], self.bridge.calls[1])
        self.generator.assert_called_once()

    def test_failed_generation_retries_same_persisted_secret_not_a_replacement(self):
        self.generator.side_effect = service.ActivationError('SSCL_GENERATOR_UNAVAILABLE', 503)
        with self.assertRaises(service.ActivationError): self.activate()
        row = ExternalNodeActivation.objects.get()
        original = service.unseal(self.cipher, row)['clientSecret']
        self.assertFalse(row.key_id)
        self.assertFalse(row.lease_token)
        self.generator.side_effect = share_for
        data, _ = self.activate()
        row.refresh_from_db()
        self.assertEqual(original, service.unseal(self.cipher, row)['clientSecret'])
        self.assertEqual(data['nodeStatus'], 'ACTIVE')

    def test_concurrent_owner_blocks_second_generation(self):
        row = service._record('platform-a', 'busy', self.cipher, algorithm='SSCL')
        row.lease_token, row.lease_expires_at = 'other-owner', timezone.now() + timedelta(seconds=60)
        row.save()
        data, status = self.activate(name='busy')
        self.assertEqual(status, 202)
        self.assertEqual(data['publicKeyRegistrationStatus'], 'PENDING')
        self.generator.assert_not_called()

    def test_late_generation_cannot_overwrite_a_new_lease_owner(self):
        def stolen(identity, ua):
            ExternalNodeActivation.objects.update(lease_token='new-owner')
            return share_for(identity, ua)
        self.generator.side_effect = stolen
        with self.assertRaises(service.ActivationError) as caught: self.activate()
        self.assertEqual(caught.exception.code, 'EXTERNAL_ACTIVATION_LEASE_EXPIRED')
        self.assertEqual(NodeLongTermKey.objects.count(), 0)
        self.assertEqual(ExternalNodeActivation.objects.get().lease_token, 'new-owner')

    def test_missing_private_material_or_revocation_never_generates_a_new_key(self):
        self.activate()
        with self.assertRaises(service.ActivationError):
            service.activate('platform-a', '待激活节点一', Fernet(Fernet.generate_key()), algorithm='SSCL', generator=self.generator)
        row = ExternalNodeActivation.objects.get()
        row.key.status, row.key.active_slot = 'REVOKED', None
        row.key.save()
        with self.assertRaises(service.ActivationError) as caught: self.activate()
        self.assertEqual(caught.exception.code, 'EXTERNAL_PUBLIC_KEY_INACTIVE')
        self.generator.assert_called_once()

    def test_disabled_node_cannot_be_reactivated_by_retry(self):
        self.activate()
        Node.objects.update(status='disabled')
        with self.assertRaises(service.ActivationError) as caught: self.activate()
        self.assertEqual(caught.exception.code, 'EXTERNAL_NODE_DISABLED')
        self.generator.assert_called_once()

    def test_invalid_names_or_disabled_did_create_nothing(self):
        for name in ('', ' padded', 'line\nbreak', 'a' * 101, None, 12):
            with self.assertRaises(service.ActivationError): self.activate(name=name)
        os.environ['FABRIC_DID_NODE_KEYGEN_ENABLED'] = 'false'
        with self.assertRaises(service.ActivationError): self.activate()
        self.assertEqual(Node.objects.count(), 0)

    def test_http_requires_bearer_and_never_uses_demo_context(self):
        factory = RequestFactory()
        bad = factory.post('/external-api/v1/nodes/activate/', data=json.dumps({'nodeName': 'name'}), content_type='application/json')
        self.assertEqual(external_node_activation(bad).status_code, 401)
        good = factory.post('/external-api/v1/nodes/activate/', data=json.dumps({'nodeName': 'name'}), content_type='application/json', HTTP_AUTHORIZATION='Bearer ' + self.api_token)
        with patch.object(service, 'issue_partial', self.generator), patch.object(service.node_key_did, 'FabricDidClient', return_value=self.bridge):
            response = external_node_activation(good)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(json.loads(response.content)['data']['didConfirmed'])
        self.assertEqual(response['Cache-Control'], 'no-store')

    def test_http_rejects_unknown_fields_before_creating_node(self):
        request = RequestFactory().post('/external-api/v1/nodes/activate/', data=json.dumps({'nodeName': 'name', 'privateKey': 'must-not-be-accepted'}), content_type='application/json', HTTP_AUTHORIZATION='Bearer ' + self.api_token)
        self.assertEqual(external_node_activation(request).status_code, 400)
        self.assertEqual(Node.objects.count(), 0)

    def test_invalid_share_is_rejected_without_registering_a_key(self):
        def invalid(identity, ua):
            data = share_for(identity, ua)
            data['xIndex'][0] = data['xIndex'][1]
            return data
        self.generator.side_effect = invalid
        with self.assertRaises(service.ActivationError): self.activate()
        self.assertEqual(NodeLongTermKey.objects.count(), 0)

    def test_query_preserves_saved_identifier_when_did_feature_is_disabled(self):
        original, _ = self.activate()
        os.environ['FABRIC_DID_NODE_KEYGEN_ENABLED'] = 'false'
        data = service.query('platform-a', '待激活节点一', algorithm='SSCL')
        self.assertEqual(data['sysPid'], original['sysPid'])
        self.assertTrue(data['didConfirmed'])
        self.generator.assert_called_once()

    def test_query_of_pending_transaction_only_verifies_original(self):
        self.bridge.failures['submit'] = 'BRIDGE_TIMEOUT'
        original, _ = self.activate()
        data = service.query('platform-a', '待激活节点一', algorithm='SSCL', did_factory=lambda: self.bridge)
        self.assertEqual(data['sysPid'], original['sysPid'])
        self.assertTrue(data['didConfirmed'])
        self.generator.assert_called_once()
        self.assertEqual([op for op, _ in self.bridge.calls], ['prepare', 'submit', 'verify'])

    def test_sys_pid_query_returns_original_key_and_current_lifecycle_status(self):
        original, _ = self.activate()
        key = NodeLongTermKey.objects.get()
        key.status, key.active_slot = 'REVOKED', None
        key.save()
        data = service.query('platform-a', sys_pid=original['sysPid'])
        self.assertEqual(data['nodeName'], original['nodeName'])
        self.assertEqual(data['publicKey'], original['publicKey'])
        self.assertEqual(data['sysPid'], original['sysPid'])
        self.assertEqual(data['publicKeyRegistrationStatus'], 'REGISTERED')
        self.assertEqual(data['publicKeyStatus'], 'REVOKED')
        self.generator.assert_called_once()
        self.assertEqual([op for op, _ in self.bridge.calls], ['prepare', 'submit'])

    def test_sys_pid_query_rejects_other_platforms_and_unknown_identifiers(self):
        original, _ = self.activate()
        for client, pid in (('platform-b', original['sysPid']), ('PLATFORM-A', original['sysPid']),
                            ('platform-a', '0' * 182)):
            with self.subTest(client=client, sys_pid=pid):
                with self.assertRaises(service.ActivationError) as caught:
                    service.query(client, sys_pid=pid)
                self.assertEqual((caught.exception.code, caught.exception.status), ('EXTERNAL_NODE_NOT_FOUND', 404))
        self.assertEqual(Node.objects.count(), 1)
        self.assertEqual(NodeKeyDidRecord.objects.count(), 1)
        self.generator.assert_called_once()

    def test_sys_pid_query_of_pending_transaction_only_verifies_original(self):
        self.bridge.failures['submit'] = 'BRIDGE_TIMEOUT'
        original, _ = self.activate()
        data = service.query('platform-a', sys_pid=original['sysPid'], did_factory=lambda: self.bridge)
        self.assertEqual(data['sysPid'], original['sysPid'])
        self.assertEqual(data['publicKey'], original['publicKey'])
        self.assertTrue(data['didConfirmed'])
        self.generator.assert_called_once()
        self.assertEqual([op for op, _ in self.bridge.calls], ['prepare', 'submit', 'verify'])

    def test_query_rejects_incomplete_sys_pid_and_ambiguous_selectors(self):
        for value in ('', 'a' * 181, 'a' * 183, 'A' * 182, 'g' * 182, ' ' + 'a' * 182, 123):
            with self.subTest(value=value):
                with self.assertRaises(service.ActivationError) as caught:
                    service.query('platform-a', sys_pid=value)
                self.assertEqual((caught.exception.code, caught.exception.status), ('INVALID_SYS_PID', 400))
        for selector in ({}, {'name': 'node', 'sys_pid': 'a' * 182}):
            with self.assertRaises(service.ActivationError) as caught:
                service.query('platform-a', **selector)
            self.assertEqual(caught.exception.status, 400)
        self.assertEqual(Node.objects.count(), 0)
        self.assertFalse(self.bridge.calls)

    def test_http_get_accepts_sys_pid_without_node_name(self):
        original, _ = self.activate()
        request = RequestFactory().get('/external-api/v1/nodes/activate/', {'sysPid': original['sysPid']},
                                       HTTP_AUTHORIZATION='Bearer ' + self.api_token)
        response = external_node_activation(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)['data'], original)
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.generator.assert_called_once()
        self.assertEqual([op for op, _ in self.bridge.calls], ['prepare', 'submit'])

    def test_http_get_rejects_ambiguous_or_duplicate_query_parameters(self):
        for fields in ({}, {'sysPid': 'a' * 182, 'nodeName': 'name'},
                       {'sysPid': ['a' * 182, 'a' * 182]}, {'nodeName': ['name', 'name']},
                       {'sysPid': 'a' * 182, 'clientId': 'platform-b'}):
            with self.subTest(fields=fields):
                request = RequestFactory().get('/external-api/v1/nodes/activate/', fields,
                                               HTTP_AUTHORIZATION='Bearer ' + self.api_token)
                self.assertEqual(external_node_activation(request).status_code, 400)
        self.assertEqual(Node.objects.count(), 0)

    def test_sys_pid_http_query_requires_original_platform_bearer(self):
        original, _ = self.activate()
        factory = RequestFactory()
        path, fields = '/external-api/v1/nodes/activate/', {'sysPid': original['sysPid']}
        self.assertEqual(external_node_activation(factory.get(path, fields)).status_code, 401)
        config = json.loads(self.config.read_text())
        config['clients']['platform-b'] = hashlib.sha256(b'other-platform-token-at-least-32-characters').hexdigest()
        self.config.write_text(json.dumps(config))
        request = factory.get(path, fields, HTTP_AUTHORIZATION='Bearer other-platform-token-at-least-32-characters')
        self.assertEqual(external_node_activation(request).status_code, 404)
        self.generator.assert_called_once()

    def test_explicit_did_failure_keeps_registered_public_key_and_never_reports_success(self):
        original = self.bridge.submit_sys_pid
        def failed(pid):
            data = original(pid)
            data.update(status='FAILED', transactionValid=False, metadataMatches=False, errorCode='TX_INVALID')
            return data
        self.bridge.submit_sys_pid = failed
        data, status = self.activate()
        self.assertEqual(status, 502)
        self.assertEqual(data['publicKeyRegistrationStatus'], 'REGISTERED')
        self.assertTrue(data['sysPid'])
        self.assertFalse(data['didConfirmed'])

    def test_explicit_private_export_reuses_original_key_and_domain(self):
        original, _ = self.activate()
        exported = service.private_key('platform-a', self.cipher, sys_pid=original['sysPid'])
        material = service.unseal(self.cipher, ExternalNodeActivation.objects.get())
        self.assertEqual(exported, {k: material[k] for k in ('privateKey', 'domainPublicKey')})
        self.assertEqual(exported, service.private_key('platform-a', self.cipher, name=original['nodeName'], algorithm='SSCL'))
        self.assertNotIn('privateKey', service.query('platform-a', sys_pid=original['sysPid']))
        self.assertNotIn('clientSecret', exported)
        self.generator.assert_called_once()
        self.assertEqual([op for op, _ in self.bridge.calls], ['prepare', 'submit'])

    def test_private_export_rejects_other_platform_revoked_and_disabled_nodes(self):
        original, _ = self.activate()
        for client in ('platform-b', 'PLATFORM-A'):
            with self.assertRaises(service.ActivationError) as caught:
                service.private_key(client, self.cipher, sys_pid=original['sysPid'])
            self.assertEqual(caught.exception.status, 404)
        row = ExternalNodeActivation.objects.get()
        row.key.status, row.key.active_slot = 'REVOKED', None
        row.key.save()
        with self.assertRaises(service.ActivationError) as caught:
            service.private_key('platform-a', self.cipher, sys_pid=original['sysPid'])
        self.assertEqual(caught.exception.code, 'EXTERNAL_PUBLIC_KEY_INACTIVE')
        Node.objects.update(status='disabled')
        with self.assertRaises(service.ActivationError) as caught:
            service.private_key('platform-a', self.cipher, sys_pid=original['sysPid'])
        self.assertEqual(caught.exception.code, 'EXTERNAL_NODE_DISABLED')
        self.generator.assert_called_once()

    def test_private_export_rejects_unavailable_or_inconsistent_material(self):
        original, _ = self.activate()
        with self.assertRaises(service.ActivationError):
            service.private_key('platform-a', Fernet(Fernet.generate_key()), sys_pid=original['sysPid'])
        row = ExternalNodeActivation.objects.get()
        material = service.unseal(self.cipher, row)
        for changes in ({'privateKey': '0' * 64}, {'privateKey': '0' * 63 + '1'},
                        {'domainPublicKey': 'bad'}, {'publicKey': 'bad'}):
            row.encrypted_material = service.seal(self.cipher, dict(material, **changes))
            row.save()
            with self.assertRaises(service.ActivationError) as caught:
                service.private_key('platform-a', self.cipher, sys_pid=original['sysPid'])
            self.assertEqual(caught.exception.code, 'EXTERNAL_PRIVATE_MATERIAL_UNAVAILABLE')
        self.generator.assert_called_once()

    def test_http_explicit_activation_returns_private_key_but_get_never_does(self):
        factory = RequestFactory()
        path = '/external-api/v1/nodes/activate/'
        auth = {'HTTP_AUTHORIZATION': 'Bearer ' + self.api_token}
        request = factory.post(path, data=json.dumps({'nodeName': 'new', 'algorithm': 'SSCL', 'includePrivateKey': True}),
                               content_type='application/json', **auth)
        with patch.object(service, 'issue_partial', self.generator), patch.object(service.node_key_did, 'FabricDidClient', return_value=self.bridge):
            response = external_node_activation(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-store')
        data = json.loads(response.content)['data']
        material = service.unseal(self.cipher, ExternalNodeActivation.objects.get())
        self.assertEqual(data['privateKey'], material['privateKey'])
        self.assertEqual(data['domainPublicKey'], material['domainPublicKey'])
        public = external_node_activation(factory.get(path, {'sysPid': data['sysPid']}, **auth))
        self.assertNotIn('privateKey', json.loads(public.content)['data'])
        self.generator.assert_called_once()

    def test_http_sys_pid_export_requires_explicit_flag_and_original_bearer(self):
        original, _ = self.activate()
        factory = RequestFactory()
        path = '/external-api/v1/nodes/activate/'
        body = json.dumps({'sysPid': original['sysPid'], 'includePrivateKey': True})
        self.assertEqual(external_node_activation(factory.post(path, body, content_type='application/json')).status_code, 401)
        request = factory.post(path, body, content_type='application/json', HTTP_AUTHORIZATION='Bearer ' + self.api_token)
        response = external_node_activation(request)
        data = json.loads(response.content)['data']
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['sysPid'], original['sysPid'])
        self.assertEqual(data['publicKey'], original['publicKey'])
        self.assertEqual(len(data['privateKey']), 64)
        self.generator.assert_called_once()
        self.assertEqual([op for op, _ in self.bridge.calls], ['prepare', 'submit'])
        config = json.loads(self.config.read_text())
        other_token = 'other-platform-private-export-token-at-least-32-characters'
        config['clients']['platform-b'] = hashlib.sha256(other_token.encode()).hexdigest()
        self.config.write_text(json.dumps(config))
        foreign = factory.post(path, body, content_type='application/json', HTTP_AUTHORIZATION='Bearer ' + other_token)
        response = external_node_activation(foreign)
        self.assertEqual(response.status_code, 404)
        self.assertNotIn('privateKey', json.loads(response.content)['data'])

    def test_pending_did_does_not_prevent_receiving_original_private_key(self):
        self.bridge.failures['submit'] = 'BRIDGE_TIMEOUT'
        request = RequestFactory().post('/external-api/v1/nodes/activate/',
                    json.dumps({'nodeName': 'pending', 'algorithm': 'SSCL', 'includePrivateKey': True}),
                    content_type='application/json', HTTP_AUTHORIZATION='Bearer ' + self.api_token)
        with patch.object(service, 'issue_partial', self.generator), patch.object(service.node_key_did, 'FabricDidClient', return_value=self.bridge):
            response = external_node_activation(request)
        data = json.loads(response.content)['data']
        self.assertEqual(response.status_code, 202)
        self.assertFalse(data['didConfirmed'])
        self.assertEqual(len(data['privateKey']), 64)
        self.assertEqual(data['publicKeyRegistrationStatus'], 'REGISTERED')
        self.assertEqual([op for op, _ in self.bridge.calls], ['prepare', 'submit'])

    def test_private_export_invalid_requests_create_nothing(self):
        factory = RequestFactory()
        for fields in ({'nodeName': 'name', 'includePrivateKey': 'true'},
                       {'sysPid': 'a' * 182}, {'sysPid': 'a' * 182, 'includePrivateKey': False},
                       {'sysPid': 'a' * 182, 'nodeName': 'name', 'includePrivateKey': True},
                       {'includePrivateKey': True}):
            request = factory.post('/external-api/v1/nodes/activate/', json.dumps(fields),
                                   content_type='application/json', HTTP_AUTHORIZATION='Bearer ' + self.api_token)
            self.assertEqual(external_node_activation(request).status_code, 400)
        self.assertEqual(Node.objects.count(), 0)

    def test_audit_does_not_retain_rejected_private_or_credential_fields(self):
        import re
        import uuid
        source = (Path(__file__).resolve().parents[1] / 'dvadmin/utils/middleware.py').read_text(encoding='utf-8')
        function = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == '_keygen_audit_payload')
        namespace = {'re': re, 'uuid': uuid}
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<actual-audit-helper>', 'exec'), namespace)
        data = namespace['_keygen_audit_payload']('/external-api/v1/nodes/activate/', {'nodeName': '外部节点', 'privateKey': 'must-not-be-logged', 'token': 'must-not-be-logged'})
        self.assertEqual(data, {'redacted': True, 'nodeName': '外部节点'})


if __name__ == '__main__': unittest.main()
