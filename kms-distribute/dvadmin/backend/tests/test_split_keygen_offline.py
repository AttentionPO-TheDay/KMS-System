# -*- coding: utf-8 -*-
"""Fresh-process actual pqkds models/services on SQLite :memory: ONLY.

Reuse the repository offline fixture's CoreModel audit-base shim, not business
model/service mocks. No application.settings, app ready, live DB, network or
native crypto needed. SQLite proves constraints/atomic rollback, not MySQL locks.
Audit capture/persistence uses the actual middleware AST with a fake log sink.
"""
import ast
import base64
import importlib
import json
import os
import sys
import types
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
# This existing fixture refuses configured settings and creates only :memory: tables.
import pqkds.test_fabric_bindings_offline as fixture
from django.conf import settings
from django.db import connection, IntegrityError, transaction
from django.http import JsonResponse
from django.test import RequestFactory
from django.utils import timezone
from pqkds import api_contract as C
from pqkds import keygen_issuance as K
from pqkds import node_key_registry as R
from pqkds.models import KeyGenerationAuthorization as Auth, KeyGenerationIssuance as Issuance
from pqkds.models import Node, NodeLongTermKey

if connection.settings_dict['NAME'] != ':memory:':
    raise RuntimeError('Refusing any non-memory database')
with connection.schema_editor() as editor:
    editor.create_model(Issuance)
    editor.create_model(Auth)


class SplitKeygenTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'KMS_SPLIT_KEYGEN_ENABLED': 'true',
                                          'KMS_CHAIN_WRITES_ENABLED': 'false'}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        if connection.settings_dict['NAME'] != ':memory:':
            raise RuntimeError('Refusing non-memory test cleanup')
        with connection.cursor() as cursor:
            for model in (Auth, Issuance, fixture.ChainKeyBinding, NodeLongTermKey, Node):
                cursor.execute('DELETE FROM ' + model._meta.db_table)
        self.node = Node.objects.create(node_id='split-node', name='Offline',
                                       ip_address='127.0.0.1', port=1, sys_user_id=102,
                                       status='active', key_device_id='a' * 32)
        self.binding = dict(userId='102', nodeId='split-node', bindingKind='DEVICE',
                            deviceFingerprint='a' * 32, demoSessionId='', demoRevision='')
        self.pk = base64.b64encode(bytes(800)).decode('ascii')

    def issue(self, **kwargs):
        return K.issue_contribution(self.node, self.binding, algorithm=kwargs.pop('algorithm', 'KYBER'),
                                    key_id=kwargs.pop('key_id', 'split-key'),
                                    key_version=kwargs.pop('key_version', 1),
                                    variant=kwargs.pop('variant', '512'), **kwargs)

    def generation(self, issued):
        return dict(schemeId=issued['generationScheme'], schemeVersion=1,
                    generationIssuanceId=issued['generationIssuanceId'],
                    authorizationTicketId=issued['authorizationTicketId'])

    def register(self, issued, **kwargs):
        return R.register_public_key(self.node, algorithm=kwargs.pop('algorithm', 'KYBER'),
            public_key=kwargs.pop('public_key', self.pk), key_id=kwargs.pop('key_id', 'split-key'),
            key_version=kwargs.pop('key_version', 1), security_level=kwargs.pop('security_level', '512'),
            generation=kwargs.pop('generation', self.generation(issued)),
            generation_binding=kwargs.pop('generation_binding', self.binding), **kwargs)

    def denied(self, code, operation):
        with self.assertRaises(C.ContractError) as raised:
            operation()
        self.assertEqual(raised.exception.code, code)

    def test_issue_register_public_provenance_and_32_byte_entropy(self):
        issued = self.issue()
        self.assertEqual(len(base64.b64decode(issued['share'], validate=True)), 32)
        self.assertEqual(set(issued['context']), set(C.SPLIT_CONTEXT_FIELDS))
        self.assertEqual(issued['context']['schemeVersion'], '1')
        self.assertRegex(issued['expiresAt'], r'[+-]\d\d:\d\d$')
        row = self.register(issued)
        self.assertEqual(Auth.objects.get(pk=issued['authorizationTicketId']).status, 'BOUND')
        self.assertEqual(Issuance.objects.get(pk=issued['generationIssuanceId']).status, 'BOUND')
        self.node.refresh_from_db()
        self.assertEqual(self.node.kyber_public_key, row.public_key)
        self.assertEqual(row.generation_context, issued['context'])
        public = json.dumps(K.public_generation_payload(row))
        stored = json.dumps(list(Issuance.objects.values()) + list(Auth.objects.values()), default=str)
        self.assertNotIn(issued['share'], public + stored)
        self.assertNotIn('share', {f.name for f in Issuance._meta.fields})
        self.assertEqual(K.public_generation_payload(row)['generation'], self.generation(issued))

    def test_rollout_flag_defaults_disabled(self):
        os.environ.pop('KMS_SPLIT_KEYGEN_ENABLED')
        self.denied(C.ERR_KEYGEN_POLICY_DISABLED, self.issue)
        self.assertEqual(Issuance.objects.count(), 0)

    def test_new_registration_missing_metadata_and_unknown_scheme_denied(self):
        self.denied(C.ERR_KEYGEN_GENERATION_REQUIRED, lambda: R.register_public_key(
            self.node, algorithm='KYBER', public_key=self.pk, key_id='pending-old'))
        issued = self.issue()
        gen = self.generation(issued)
        gen['schemeId'] = 'KMS_SPLIT_UNKNOWN'
        self.denied(C.ERR_KEYGEN_SCHEME_INVALID, lambda: self.register(issued, generation=gen))
        self.assertEqual(NodeLongTermKey.objects.count(), 0)

    def test_historical_exact_missing_metadata_retry_preserves_unrecorded_source(self):
        os.environ['KMS_SPLIT_KEYGEN_ENABLED'] = 'false'
        old = R.register_public_key(self.node, algorithm='KYBER', public_key=self.pk,
                                    key_id='old', security_level='512')
        os.environ['KMS_SPLIT_KEYGEN_ENABLED'] = 'true'
        retry = R.register_public_key(self.node, algorithm='KYBER', public_key=self.pk, key_id='old')
        self.assertEqual(retry.pk, old.pk)
        self.assertEqual(retry.generation_scheme, '')
        self.assertIsNone(K.public_generation_payload(retry)['generation'])

    def test_expired_authorization_renews_same_origin_same_pk_without_secret(self):
        issued = self.issue()
        Auth.objects.filter(pk=issued['authorizationTicketId']).update(
            expires_at=timezone.now() - timedelta(seconds=1))
        self.denied(C.ERR_KEYGEN_AUTHORIZATION_EXPIRED, lambda: self.register(issued))
        self.assertEqual(NodeLongTermKey.objects.count(), 0)
        with patch.object(K.secrets, 'token_bytes', side_effect=AssertionError('renew generated secret')):
            renewed = K.renew_authorization(self.node, self.binding,
                generation_issuance_id=issued['generationIssuanceId'], public_key=bytes(800).hex())
        self.assertNotIn('share', renewed)
        self.assertEqual(renewed['generationIssuanceId'], issued['generationIssuanceId'])
        self.assertNotEqual(renewed['authorizationTicketId'], issued['authorizationTicketId'])
        self.denied(C.ERR_KEYGEN_AUTHORIZATION_SUPERSEDED, lambda: self.register(issued))
        issued['authorizationTicketId'] = renewed['authorizationTicketId']
        row = self.register(issued)
        self.assertEqual(row.generation_issuance_id, renewed['generationIssuanceId'])
        self.assertEqual(Issuance.objects.count(), 1)

    def test_renewal_prebound_pk_cannot_change_or_abandon(self):
        issued = self.issue()
        K.renew_authorization(self.node, self.binding,
            generation_issuance_id=issued['generationIssuanceId'], public_key=bytes(800).hex())
        self.denied(C.ERR_KEYGEN_PUBLIC_KEY_CONFLICT, lambda: K.renew_authorization(
            self.node, self.binding, generation_issuance_id=issued['generationIssuanceId'],
            public_key=(b'\x01' * 800).hex()))
        self.denied(C.ERR_KEYGEN_ISSUANCE_CONFLICT, lambda: self.issue(
            abandon_generation_issuance_id=issued['generationIssuanceId']))

    def test_expired_bound_exact_retry_and_revoked_retry_do_not_reactivate(self):
        issued = self.issue()
        row = self.register(issued)
        Auth.objects.filter(pk=issued['authorizationTicketId']).update(
            expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.register(issued).pk, row.pk)
        R.revoke_public_key(row)
        retried = self.register(issued)
        self.assertEqual(retried.status, C.KEY_STATUS_REVOKED)
        self.node.refresh_from_db()
        self.assertEqual(self.node.kyber_public_key, '')

    def test_deleted_bound_row_cannot_recreate_or_demote_current_key(self):
        first = self.issue()
        old = self.register(first)
        second = self.issue(key_id='other-key')
        current = self.register(second, key_id='other-key', public_key=base64.b64encode(b'\x01' * 800).decode())
        NodeLongTermKey.objects.filter(pk=old.pk).delete()
        self.denied(C.ERR_KEYGEN_PUBLIC_KEY_CONFLICT, lambda: self.register(first))
        current.refresh_from_db()
        self.assertEqual(current.status, C.KEY_STATUS_ACTIVE)
        self.assertEqual(NodeLongTermKey.objects.count(), 1)
        self.node.refresh_from_db()
        self.assertEqual(self.node.kyber_public_key, current.public_key)

    def test_wrong_user_device_demo_revision_and_session(self):
        issued = self.issue()
        for field, value in [('userId', '999'), ('nodeId', 'other'),
                             ('deviceFingerprint', 'b' * 32), ('bindingKind', 'DEMO'),
                             ('demoRevision', '1'), ('demoSessionId', 'different')]:
            with self.subTest(field=field):
                binding = dict(self.binding, **{field: value})
                self.denied(C.ERR_KEYGEN_CONTEXT_MISMATCH,
                            lambda: self.register(issued, generation_binding=binding))
        self.assertEqual(Auth.objects.get(pk=issued['authorizationTicketId']).status, 'ISSUED')

    def test_fresh_locked_node_disable_account_and_device_fence(self):
        issued = self.issue()
        for change in [dict(status='disabled'), dict(sys_user_id=999), dict(key_device_id='b' * 32)]:
            with self.subTest(change=change):
                Node.objects.filter(pk=self.node.pk).update(**change)
                self.denied(C.ERR_KEYGEN_CONTEXT_MISMATCH, lambda: K.renew_authorization(
                    self.node, self.binding, generation_issuance_id=issued['generationIssuanceId'],
                    public_key=bytes(800).hex()))
                self.denied(C.ERR_KEYGEN_CONTEXT_MISMATCH, lambda: self.register(issued))
                Node.objects.filter(pk=self.node.pk).update(status='active', sys_user_id=102,
                                                            key_device_id='a' * 32)
        self.assertEqual(NodeLongTermKey.objects.count(), 0)

    def test_wrong_keyref_variant_version_and_ticket_replay(self):
        issued = self.issue()
        for change in [dict(key_id='different'), dict(key_version=2), dict(security_level='768')]:
            with self.subTest(change=change):
                self.denied(C.ERR_KEYGEN_CONTEXT_MISMATCH, lambda: self.register(issued, **change))
        other = self.issue(key_id='other')
        gen = dict(self.generation(issued), authorizationTicketId=other['authorizationTicketId'])
        self.denied(C.ERR_KEYGEN_CONTEXT_MISMATCH, lambda: self.register(issued, generation=gen))

    def test_bound_public_key_conflict_rejected(self):
        issued = self.issue()
        self.register(issued)
        self.denied(C.ERR_KEY_VERSION_MISMATCH, lambda: self.register(
            issued, public_key=base64.b64encode(b'\x01' * 800).decode()))
        self.denied(C.ERR_KEYGEN_PUBLIC_KEY_CONFLICT, lambda: K.renew_authorization(
            self.node, self.binding, generation_issuance_id=issued['generationIssuanceId'],
            public_key=(b'\x01' * 800).hex()))

    def test_atomic_consumption_rolls_back_when_registry_write_fails(self):
        issued = self.issue()
        with patch.object(R, '_write_node_column', side_effect=RuntimeError('injected write failure')):
            with self.assertRaises(RuntimeError):
                self.register(issued)
        self.assertEqual(NodeLongTermKey.objects.count(), 0)
        self.assertEqual(Auth.objects.get(pk=issued['authorizationTicketId']).status, 'ISSUED')
        self.assertEqual(Issuance.objects.get(pk=issued['generationIssuanceId']).public_key_hash, '')

    def test_explicit_abandon_response_loss_and_public_recovery_listing(self):
        first = self.issue()
        self.denied(C.ERR_KEYGEN_ISSUANCE_CONFLICT, self.issue)
        listing = K.list_issuances(self.node, self.binding)
        self.assertEqual(listing['issuances'][0]['generationIssuanceId'], first['generationIssuanceId'])
        self.assertNotIn('share', json.dumps(listing))
        second = self.issue(abandon_generation_issuance_id=first['generationIssuanceId'])
        self.assertNotEqual(first['share'], second['share'])
        self.assertEqual(Issuance.objects.get(pk=first['generationIssuanceId']).status, 'ABANDONED')
        self.assertEqual(Auth.objects.get(pk=first['authorizationTicketId']).status, 'SUPERSEDED')
        self.denied(C.ERR_KEYGEN_AUTHORIZATION_SUPERSEDED, lambda: self.register(first))
        self.register(second)

    def test_mysql_compatible_unique_current_slots_exist_and_reject_duplicates(self):
        issued = self.issue()
        original = Issuance.objects.get(pk=issued['generationIssuanceId'])
        with self.assertRaises(IntegrityError), transaction.atomic():
            Issuance.objects.create(generation_issuance_id='duplicate', node=self.node, algorithm='KYBER',
                                    key_id='split-key', key_version=1, context=original.context)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Auth.objects.create(authorization_ticket_id='duplicate', issuance=original,
                                expires_at=timezone.now() + timedelta(minutes=1))
        self.assertTrue(all(c.condition is None for m in (Issuance, Auth) for c in m._meta.constraints))

    def test_falcon_canonical_encoding_and_context_parameter_set(self):
        issued = self.issue(algorithm='FALCON')
        compact = (b'\x09' + bytes(896)).hex()
        spaced = ' '.join(compact[i:i + 2] for i in range(0, len(compact), 2))
        self.denied(C.ERR_KEYGEN_CONTEXT_MISMATCH,
                    lambda: self.register(issued, algorithm='FALCON', public_key=spaced))
        row = self.register(issued, algorithm='FALCON', public_key=compact)
        self.assertEqual(row.public_key_hash, Issuance.objects.get(pk=row.generation_issuance_id).public_key_hash)

    def test_recursive_secret_and_unknown_nested_generation_denied(self):
        for payload in [{'metadata': {'localSecret': 'marker'}}, {'x': [{'seed': 'marker'}]},
                        {'generation': {'kgc_share': 'marker'}}]:
            self.denied(C.ERR_INVALID_PARAMETER, lambda: K.reject_private_fields(payload))
        issued = self.issue()
        gen = dict(self.generation(issued), metadata={'arbitrary': 'marker'})
        self.denied(C.ERR_KEYGEN_SCHEME_INVALID, lambda: self.register(issued, generation=gen))

    def test_nonloopback_https_required_and_host_forwarded_spoof_denied(self):
        factory = RequestFactory()
        request = factory.post('/api/pqkds/node-self/keygen/issuances/', HTTP_HOST='localhost',
                               REMOTE_ADDR='198.51.100.2', HTTP_X_FORWARDED_PROTO='https')
        with self.settings_hosts():
            self.denied(C.ERR_KEYGEN_HTTPS_REQUIRED, lambda: K.require_confidential_transport(request))
            K.require_confidential_transport(factory.post('/', secure=True, HTTP_HOST='example.test'))
            K.require_confidential_transport(factory.post('/', HTTP_HOST='localhost', REMOTE_ADDR='127.0.0.1'))

    def settings_hosts(self):
        from django.test import override_settings
        return override_settings(ALLOWED_HOSTS=['localhost', 'example.test'])


class AuditBoundaryTests(unittest.TestCase):
    def test_actual_middleware_capture_and_log_sink_never_receive_rejected_secrets(self):
        from django.utils.deprecation import MiddlewareMixin
        # Imports irrelevant to this test are replaced; actual class/helper AST executes unchanged.
        tree = ast.parse((BACKEND / 'dvadmin/utils/middleware.py').read_text(encoding='utf-8'))
        module = ast.Module(body=[n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))],
                            type_ignores=[])
        sink = Mock()
        sink.objects.update_or_create.return_value = (types.SimpleNamespace(request_modular='public-key'), True)
        class AnonymousUser:
            pass
        namespace = dict(json=json, re=importlib.import_module('re'), uuid=importlib.import_module('uuid'),
                         settings=types.SimpleNamespace(API_LOG_ENABLE=True, API_LOG_METHODS='ALL', API_MODEL_MAP={}),
                         MiddlewareMixin=MiddlewareMixin, OperationLog=sink, AnonymousUser=AnonymousUser,
                         get_request_ip=lambda r: '127.0.0.1', get_request_path=lambda r: r.path,
                         get_request_user=lambda r: AnonymousUser(), get_os=lambda r: 'offline',
                         get_browser=lambda r: 'offline', get_verbose_name=lambda q: 'offline')
        util = ast.parse((BACKEND / 'dvadmin/utils/request_util.py').read_text(encoding='utf-8'))
        helper = ast.Module(body=[n for n in util.body if isinstance(n, ast.FunctionDef)
                                  and n.name == 'get_request_data'], type_ignores=[])
        exec(compile(helper, 'actual_request_util', 'exec'), namespace)
        exec(compile(module, 'actual_audit_middleware', 'exec'), namespace)
        middleware = namespace['ApiLoggingMiddleware'](lambda r: None)
        factory = RequestFactory()
        marker = 'REJECTED_PRIVATE_MARKER'
        for path in ['issuances/', 'authorizations/', '../keys/']:
            path = '/api/pqkds/node-self/keygen/' + path if path != '../keys/' else '/api/pqkds/node-self/keys/'
            for body in [json.dumps({'algorithm': 'KYBER', 'keyId': 'public-id', 'share': marker,
                                    'nested': [{'seed': marker, 'localSecret': marker}],
                                    'generation': {'schemeId': 'KMS_SPLIT_KEM_V1', 'schemeVersion': 1,
                                                   'metadata': {'secret': marker}}}),
                         json.dumps([{'share': marker}]), 'malformed=' + marker]:
                with self.subTest(path=path, body_kind=body[:1]):
                    request = factory.post(path, data=body, content_type='application/json')
                    request.user, request.session = AnonymousUser(), {}
                    middleware.process_request(request)
                    self.assertNotIn(marker, json.dumps(request.request_data))
                    self.assertEqual(request.body.decode(), body)  # View still rejects the ORIGINAL request.
                    response = JsonResponse({'code': 400, 'msg': marker,
                                             'data': {'error_code': 'INVALID_PARAMETER', 'share': marker}})
                    middleware.process_response(request, response)
                    defaults = sink.objects.update_or_create.call_args.kwargs['defaults']
                    self.assertNotIn(marker, json.dumps(defaults, default=str))
                    self.assertEqual(defaults['response_code'], 400)
                    self.assertEqual(defaults['json_result']['error_code'], 'INVALID_PARAMETER')


if __name__ == '__main__':
    unittest.main(verbosity=2)
