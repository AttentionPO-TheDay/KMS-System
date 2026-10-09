# -*- coding: utf-8 -*-
"""独立进程离线测试：python pqkds/test_fabric_bindings_offline.py。

不读取 application.settings、不运行生产 AppConfig.ready、不连接 MySQL；只在 :memory:
建四张真实 pqkds 模型表。CoreModel 的审计基类替身省去 auth/system app，业务模型、
登记事务、约束和 worker 使用真实代码。SQLite 不证明 MySQL 并发锁语义。
"""
import importlib
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from django.apps import AppConfig
from django.conf import settings


class OfflinePqkdsConfig(AppConfig):
    name = 'pqkds'
    default_auto_field = 'django.db.models.BigAutoField'


def bootstrap():
    if settings.configured:
        raise unittest.SkipTest('Standalone :memory: test requires a fresh process; never uses configured databases')
    settings.configure(
        SECRET_KEY='offline-not-a-server', USE_TZ=False, TIME_ZONE='Asia/Shanghai',
        INSTALLED_APPS=[__name__ + '.OfflinePqkdsConfig'],
        DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
        DEFAULT_AUTO_FIELD='django.db.models.BigAutoField',
    )
    from django.db import models
    # App population imports pqkds.models after this replacement is installed.
    module = types.ModuleType('dvadmin.utils.models')
    def resolve(name):
        if name != 'CoreModel':
            raise AttributeError(name)
        class CoreModel(models.Model):
            id = models.BigAutoField(primary_key=True)
            create_datetime = models.DateTimeField(auto_now_add=True, null=True)
            update_datetime = models.DateTimeField(auto_now=True, null=True)
            class Meta:
                abstract = True
        module.CoreModel = CoreModel
        return CoreModel
    module.__getattr__ = resolve
    module.table_prefix = 'dvadmin_'
    sys.modules['dvadmin.utils.models'] = module
    import django
    django.setup()
    from django.db import connection
    from pqkds.models import BlockchainConfig, Node, NodeLongTermKey, ChainKeyBinding
    with connection.schema_editor() as editor:
        for model in (BlockchainConfig, Node, NodeLongTermKey, ChainKeyBinding):
            editor.create_model(model)


bootstrap()

from django.core.exceptions import ImproperlyConfigured
from django.db import connection, IntegrityError, transaction
from django.utils import timezone
from pqkds import chain_backend as backend
from pqkds import chain_binding_service as service
from pqkds import node_key_registry as registry
from pqkds.fabric_did_client import BindingError, FabricDidClient
from pqkds.models import ChainKeyBinding, Node, NodeLongTermKey


ENV = {
    'KMS_CHAIN_BACKEND': 'fabric-did', 'FABRIC_DID_CHAIN_ID': 'offline-channel',
    'FABRIC_DID_NAMESPACE': 'kms-key-binding-v1', 'FABRIC_DID_ENABLED': 'true',
    'FABRIC_DID_WRITE_ENABLED': 'true', 'INTERNAL_TOKEN': 'mock-internal-token',
}


class MockBridge:
    def __init__(self, submit_timeout=False, verify_pending=False):
        self.calls = []
        self.submit_timeout = submit_timeout
        self.verify_pending = verify_pending
        self.closed = False

    def status(self):
        self.calls.append('status')
        return dict(provider='FABRIC_DID', chainId='offline-channel', configured=True,
                    enabled=True, writeEnabled=True, status='READY')

    def prepare(self, binding):
        self.calls.append('prepare')
        return dict(binding, did='did:mock:node', txId='original-tx', nonce='original-nonce')

    def submit(self, binding, prepared):
        self.calls.append('submit')
        row = ChainKeyBinding.objects.get(event_id=binding['eventId'])
        assert not connection.in_atomic_block
        assert row.tx_id == prepared['txId'] and row.nonce == prepared['nonce']
        assert row.submit_started and row.status == 'PENDING_VERIFICATION'
        if self.submit_timeout:
            raise BindingError('BRIDGE_TIMEOUT')
        return {'status': 'SUBMITTED'}

    def verify(self, row):
        self.calls.append(('verify', row.tx_id))
        return dict(provider=row.provider, chainId=row.chain_id, did=row.did, txId=row.tx_id,
                    metadataDigest=row.metadata_digest, transactionValid=True,
                    metadataMatches=not self.verify_pending,
                    status='PENDING_VERIFICATION' if self.verify_pending else 'CONFIRMED')

    def close(self):
        self.closed = True


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, ENV, clear=True)
        self.env.start()
        # 删除只针对本脚本 :memory: 测试表，不走生产软删除/关联清理逻辑。
        if connection.settings_dict['NAME'] != ':memory:':
            raise RuntimeError('Refusing non-memory database')
        with connection.cursor() as cursor:
            for table in ('dvadmin_pqkds_chain_key_bindings', 'dvadmin_pqkds_node_long_term_keys', 'dvadmin_pqkds_nodes'):
                cursor.execute('DELETE FROM ' + table)
        self.node = Node.objects.create(node_id='节点-offline', name='Offline', ip_address='127.0.0.1', port=1234)

    def tearDown(self):
        self.env.stop()

    def key(self, **kwargs):
        return registry.register_public_key(self.node, algorithm=kwargs.pop('algorithm', 'SM2'),
                                            public_key=kwargs.pop('public_key', '04abcdef'),
                                            key_id=kwargs.pop('key_id', 'logical-key'), **kwargs)

    def test_default_legacy_and_unknown_config(self):
        os.environ.pop('KMS_CHAIN_BACKEND')
        self.assertFalse(backend.is_fabric_did())
        self.key()
        self.assertEqual(ChainKeyBinding.objects.count(), 0)
        os.environ['KMS_CHAIN_BACKEND'] = 'typo'
        with self.assertRaises(ImproperlyConfigured):
            self.key(key_id='bad-config')
        self.assertEqual(NodeLongTermKey.objects.count(), 1)
        os.environ['KMS_CHAIN_BACKEND'] = 'fabric-did'
        with self.assertRaises(backend.NoLegacyWrite):
            backend.require_legacy_backend('constructor')

    def test_four_algorithms_canonical_public_snapshot(self):
        for algorithm in ('SM2', 'SSCL', 'KYBER', 'FALCON'):
            key = self.key(algorithm=algorithm, public_key='YWJjZA==' if algorithm == 'KYBER' else '04abcdef')
            row = key.chain_bindings.get()
            metadata = json.loads(row.metadata)
            self.assertEqual(metadata['keyId'], key.key_id)
            self.assertEqual(metadata['keyVersion'], 1)
            self.assertEqual(metadata['algorithm'], algorithm)
            self.assertEqual(metadata['publicKey'], key.public_key)
            self.assertEqual(metadata['publicKeyHash'], registry.hash_public_key(key.public_key))
            self.assertEqual(metadata['eventType'], 'REGISTERED')
            self.assertEqual(row.metadata, service.canonical_json(metadata))
            self.assertIn('节点-offline', row.metadata)
            self.assertNotIn('device', row.metadata)
            self.assertNotIn('private', row.metadata.lower())
            self.assertNotIn('sm4', row.metadata.lower())
            self.assertEqual(row.metadata_digest, service.digest_metadata(row.metadata))
        self.assertEqual(list(ChainKeyBinding.objects.order_by('sequence').values_list('sequence', flat=True)), [1, 2, 3, 4])

    def test_idempotent_registration_and_rotation_revoke(self):
        key = self.key()
        first_event = key.chain_bindings.get().event_id
        self.assertEqual(self.key().pk, key.pk)
        self.assertEqual(self.key(key_id='').pk, key.pk)
        self.assertEqual(ChainKeyBinding.objects.count(), 1)
        rotated = registry.rotate_public_key(self.node, algorithm='SM2', public_key='04new', key_id=key.key_id, key_version=2)
        self.assertEqual(ChainKeyBinding.objects.count(), 3)
        rows = list(ChainKeyBinding.objects.order_by('sequence'))
        self.assertEqual(rows[0].event_id, first_event)
        self.assertEqual(json.loads(rows[1].metadata)['status'], 'RETIRED')
        self.assertEqual(json.loads(rows[2].metadata)['status'], 'ACTIVE')
        registry.rotate_public_key(self.node, algorithm='SM2', public_key='04new', key_id=key.key_id, key_version=2)
        self.assertEqual(ChainKeyBinding.objects.count(), 3)
        registry.revoke_public_key(rotated)
        registry.revoke_public_key(rotated)
        self.assertEqual(ChainKeyBinding.objects.count(), 4)
        self.node.refresh_from_db()
        self.assertEqual(self.node.gm_public_key, '')
        self.assertEqual(json.loads(ChainKeyBinding.objects.latest('sequence').metadata)['status'], 'REVOKED')

    def test_outer_rollback_removes_key_and_job(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.key()
                raise RuntimeError('abort registration')
        self.assertEqual(NodeLongTermKey.objects.count(), 0)
        self.assertEqual(ChainKeyBinding.objects.count(), 0)
        self.node.refresh_from_db()
        self.assertEqual(self.node.gm_public_key, '')

    def test_outbox_failure_rolls_back_business(self):
        with patch.object(registry, 'enqueue_binding', side_effect=RuntimeError('outbox failed')):
            with self.assertRaises(RuntimeError):
                self.key()
        self.assertEqual(NodeLongTermKey.objects.count(), 0)
        self.node.refresh_from_db()
        self.assertEqual(self.node.gm_public_key, '')

    def test_deleted_key_keeps_snapshot_but_pending_job_never_publishes(self):
        key = self.key()
        row = key.chain_bindings.get()
        snapshot = row.metadata
        key.delete()
        row.refresh_from_db()
        self.assertIsNone(row.long_term_key_id)
        self.assertEqual(row.metadata, snapshot)
        factory = Mock(side_effect=AssertionError('deleted source must not publish'))
        self.assertEqual(service.process_binding(row.pk, factory), 'BLOCKED')
        row.refresh_from_db()
        self.assertEqual((row.status, row.last_error), ('FAILED', 'SOURCE_DELETED'))
        factory.assert_not_called()

    def test_deleted_key_ref_cannot_be_reused_as_another_binding(self):
        key = self.key()
        row = key.chain_bindings.get()
        key.delete()
        with self.assertRaises(BindingError) as error:
            self.key(public_key='04different')
        self.assertEqual(error.exception.code, 'BINDING_IDEMPOTENCY_CONFLICT')
        self.assertEqual(NodeLongTermKey.objects.count(), 0)
        row.refresh_from_db()
        self.assertEqual(json.loads(row.metadata)['publicKey'], '04abcdef')

    def test_deleted_key_preserves_confirmed_historical_evidence(self):
        key = self.key()
        row = key.chain_bindings.get()
        row.status = 'CONFIRMED'
        row.transaction_valid = row.metadata_matches = True
        row.save()
        key.delete()
        row.refresh_from_db()
        self.assertEqual(row.status, 'CONFIRMED')
        self.assertIsNone(row.long_term_key_id)
        factory = Mock()
        self.assertEqual(service.process_binding(row.pk, factory), 'BLOCKED')
        factory.assert_not_called()

    def test_node_delete_keeps_binding_snapshot_and_closes_orphan(self):
        key = self.key()
        row = key.chain_bindings.get()
        from django.db.models.deletion import get_candidate_relations_to_delete
        present = set(connection.introspection.table_names())
        # 只排除未在本测试四表 schema 建立的旧会话等关系；新表的真实 SET_NULL
        # 和 NodeLongTermKey CASCADE 均交给 Django Collector，不用手写数据模拟。
        def supported_relations(options):
            return [relation for relation in get_candidate_relations_to_delete(options)
                    if relation.related_model._meta.db_table in present]
        with patch('django.db.models.deletion.get_candidate_relations_to_delete', supported_relations):
            self.node.delete()
        row.refresh_from_db()
        self.assertIsNone(row.node_id)
        self.assertIsNone(row.long_term_key_id)
        self.assertEqual(row.node_id_snapshot, '节点-offline')
        factory = Mock()
        self.assertEqual(service.process_binding(row.pk, factory), 'BLOCKED')
        factory.assert_not_called()
        row.refresh_from_db()
        self.assertEqual(row.last_error, 'SOURCE_DELETED')

    def test_unique_constraint_rejects_duplicate_event(self):
        row = self.key().chain_bindings.get()
        row.pk = None
        row.event_id = 'different-event-id'
        row.sequence += 1
        with self.assertRaises(IntegrityError), transaction.atomic():
            row.save(force_insert=True)
        self.assertEqual(ChainKeyBinding.objects.count(), 1)

    def test_missing_config_never_constructs_http_client(self):
        os.environ['FABRIC_DID_ENABLED'] = 'false'
        key = self.key()
        row = key.chain_bindings.get()
        factory = Mock(side_effect=AssertionError('network constructor called'))
        self.assertEqual(row.status, 'NOT_CONFIGURED')
        self.assertEqual(service.process_binding(row.pk, factory), 'NOT_CONFIGURED')
        factory.assert_not_called()
        key.refresh_from_db()
        self.assertEqual(key.status, 'ACTIVE')

    def test_happy_worker_commits_prepared_identity_before_submit(self):
        row = self.key().chain_bindings.get()
        client = MockBridge()
        self.assertEqual(service.process_binding(row.pk, lambda: client), 'CONFIRMED')
        row.refresh_from_db()
        self.assertEqual((row.tx_id, row.nonce), ('original-tx', 'original-nonce'))
        self.assertTrue(row.transaction_valid and row.metadata_matches)
        self.assertTrue(client.closed)
        self.assertEqual(service.process_binding(row.pk, lambda: client), 'BLOCKED')
        self.assertEqual(client.calls.count('submit'), 1)

    def test_submit_timeout_checks_original_tx_without_resubmit(self):
        row = self.key().chain_bindings.get()
        first = MockBridge(submit_timeout=True, verify_pending=True)
        self.assertEqual(service.process_binding(row.pk, lambda: first), 'PENDING_VERIFICATION')
        second = MockBridge()
        self.assertEqual(service.process_binding(row.pk, lambda: second), 'CONFIRMED')
        self.assertEqual(first.calls.count('submit'), 1)
        self.assertNotIn('submit', second.calls)
        self.assertNotIn('prepare', second.calls)
        self.assertIn(('verify', 'original-tx'), second.calls)

    def test_no_newer_projection_before_prior_confirmation(self):
        first = self.key().chain_bindings.get()
        key = registry.rotate_public_key(self.node, algorithm='SM2', public_key='new', key_id='logical-key', key_version=2)
        newest = key.chain_bindings.get()
        factory = Mock(side_effect=AssertionError('out-of-order request'))
        self.assertEqual(service.process_binding(newest.pk, factory), 'BLOCKED')
        factory.assert_not_called()
        ChainKeyBinding.objects.filter(pk=first.pk).update(status='FAILED')
        self.assertEqual(service.process_binding(newest.pk, factory), 'BLOCKED')

    def test_confirmation_rejects_all_mismatches_and_truthy_strings(self):
        row = self.key().chain_bindings.get()
        row.did, row.tx_id = 'did:original', 'tx:original'
        data = MockBridge().verify(row)
        self.assertTrue(service.verification_confirmed(row, data))
        for field in ('provider', 'chainId', 'did', 'txId', 'metadataDigest'):
            with self.assertRaises(BindingError):
                service.verification_confirmed(row, dict(data, **{field: 'mismatch'}))
        for field in ('transactionValid', 'metadataMatches'):
            self.assertFalse(service.verification_confirmed(row, dict(data, **{field: 'true'})))
            self.assertFalse(service.verification_confirmed(row, dict(data, **{field: False})))

    def test_prepare_mismatch_does_not_submit(self):
        row = self.key().chain_bindings.get()
        bridge = MockBridge()
        bridge.prepare = lambda binding: dict(binding, did='did:mock', txId='tx', nonce='nonce', metadata='tampered')
        self.assertEqual(service.process_binding(row.pk, lambda: bridge), 'FAILED')
        self.assertNotIn('submit', bridge.calls)

    def test_readonly_prepare_timeout_retries_allocation_without_duplicate_submit(self):
        row = self.key().chain_bindings.get()
        metadata = row.metadata
        event_id = row.event_id
        bridge = MockBridge()
        bridge.prepare = Mock(side_effect=BindingError('BRIDGE_TIMEOUT'))
        self.assertEqual(service.process_binding(row.pk, lambda: bridge), 'PENDING_VERIFICATION')
        self.assertNotIn('submit', bridge.calls)
        bridge2 = MockBridge()
        self.assertEqual(service.process_binding(row.pk, lambda: bridge2), 'CONFIRMED')
        self.assertEqual(bridge2.calls.count('prepare'), 1)
        self.assertEqual(bridge2.calls.count('submit'), 1)
        row.refresh_from_db()
        self.assertEqual((row.metadata, row.event_id), (metadata, event_id))

    def test_prepared_crash_resume_submits_original_durable_plan_once(self):
        row = self.key().chain_bindings.get()
        original_persist = service._persist
        def crash_after_prepared(binding, **values):
            original_persist(binding, **values)
            if values.get('status') == 'PREPARED':
                raise RuntimeError('simulated crash after durable prepare')
        first = MockBridge()
        with patch.object(service, '_persist', side_effect=crash_after_prepared):
            with self.assertRaises(RuntimeError):
                service.process_binding(row.pk, lambda: first)
        row.refresh_from_db()
        self.assertEqual(row.status, 'PREPARED')
        self.assertFalse(row.submit_started)
        self.assertNotIn('submit', first.calls)
        before = (row.tx_id, row.nonce, row.did, row.metadata)
        second = MockBridge()
        verify = second.verify
        second.verify = lambda binding: dict(verify(binding), status='CONFIRMED' if 'submit' in second.calls else 'PENDING_VERIFICATION')
        self.assertEqual(service.process_binding(row.pk, lambda: second), 'CONFIRMED')
        self.assertEqual(second.calls.count('submit'), 1)
        self.assertNotIn('prepare', second.calls)
        row.refresh_from_db()
        self.assertEqual((row.tx_id, row.nonce, row.did, row.metadata), before)
        self.assertTrue(row.submit_started)
        self.assertEqual(service.process_binding(row.pk, lambda: second), 'BLOCKED')
        self.assertEqual(second.calls.count('submit'), 1)

    def test_crash_after_submit_started_before_http_is_verify_only(self):
        row = self.key().chain_bindings.get()
        original_persist = service._persist
        def crash_after_submit_marker(binding, **values):
            original_persist(binding, **values)
            if values.get('submit_started') is True:
                raise RuntimeError('simulated crash before submit HTTP')
        first = MockBridge()
        with patch.object(service, '_persist', side_effect=crash_after_submit_marker):
            with self.assertRaises(RuntimeError):
                service.process_binding(row.pk, lambda: first)
        row.refresh_from_db()
        self.assertTrue(row.submit_started)
        self.assertNotIn('submit', first.calls)
        second = MockBridge(verify_pending=True)
        self.assertEqual(service.process_binding(row.pk, lambda: second), 'PENDING_VERIFICATION')
        self.assertNotIn('prepare', second.calls)
        self.assertNotIn('submit', second.calls)
        self.assertIn(('verify', row.tx_id), second.calls)

    def test_prepared_original_plan_cannot_submit_after_write_disabled(self):
        row = self.key().chain_bindings.get()
        prepared = service.validate_prepared(row, MockBridge().prepare(service.bridge_binding(row)))
        ChainKeyBinding.objects.filter(pk=row.pk).update(status='PREPARED', did=prepared['did'], tx_id=prepared['txId'], nonce=prepared['nonce'])
        os.environ['FABRIC_DID_WRITE_ENABLED'] = 'false'
        client = MockBridge()
        self.assertEqual(service.process_binding(row.pk, lambda: client), 'NOT_CONFIGURED')
        self.assertNotIn('submit', client.calls)
        row.refresh_from_db()
        self.assertFalse(row.submit_started)
        os.environ['FABRIC_DID_WRITE_ENABLED'] = 'true'
        self.assertEqual(service.process_binding(row.pk, lambda: client), 'CONFIRMED')
        self.assertEqual(client.calls.count('submit'), 1)
        self.assertNotIn('prepare', client.calls)

    def test_changed_chain_config_does_not_relabel_evidence(self):
        row = self.key().chain_bindings.get()
        os.environ['FABRIC_DID_CHAIN_ID'] = 'other-channel'
        factory = Mock(side_effect=AssertionError('network called'))
        self.assertEqual(service.process_binding(row.pk, factory), 'NOT_CONFIGURED')
        row.refresh_from_db()
        self.assertEqual(row.chain_id, 'offline-channel')
        self.assertNotEqual(service.get_binding_status(row.long_term_key)['status'], 'CONFIRMED')

    def test_lease_blocks_second_worker_and_fences_stale_update(self):
        row = self.key().chain_bindings.get()
        first = service._claim(row.pk)
        self.assertIsNone(service._claim(row.pk))
        ChainKeyBinding.objects.filter(pk=row.pk).update(lease_until=timezone.now())
        second = service._claim(row.pk)
        self.assertNotEqual(first.lease_token, second.lease_token)
        with self.assertRaises(BindingError):
            service._persist(first, status='CONFIRMED')

    def test_http_auth_timeouts_no_redirect_and_redaction(self):
        client = FabricDidClient()
        response = Mock(status_code=200)
        response.json.return_value = {'code': 200, 'data': {'status': 'NOT_CONFIGURED'}}
        with patch.object(client.session, 'request', return_value=response) as request:
            client.status()
        kwargs = request.call_args.kwargs
        self.assertEqual(kwargs['headers'], {'X-Internal-Token': ENV['INTERNAL_TOKEN']})
        self.assertEqual(kwargs['timeout'], (3, 10))
        self.assertFalse(kwargs['allow_redirects'])
        self.assertFalse(client.session.trust_env)
        response.json.return_value = {'code': 500, 'msg': 'PRIVATE KEY token secret'}
        with patch.object(client.session, 'request', return_value=response):
            with self.assertRaises(BindingError) as error:
                client.status()
        self.assertEqual(str(error.exception), 'BRIDGE_REJECTED')
        client.close()

    def test_exact_selector_alias_and_legacy_status_have_no_fabric_side_effects(self):
        os.environ['KMS_CHAIN_BACKEND'] = 'legacy'
        factory = Mock(side_effect=AssertionError('legacy must not call Bridge'))
        self.assertEqual(backend.get_chain_backend(), 'legacy')
        self.assertEqual(service.get_backend_status(factory)['status'], 'LEGACY')
        factory.assert_not_called()
        os.environ['KMS_CHAIN_BACKEND'] = 'fabric-did'
        self.assertEqual(backend.get_chain_backend(), 'fabric-did')

    def test_backend_status_local_disabled_missing_config_never_contacts_bridge(self):
        factory = Mock(side_effect=AssertionError('disabled/missing config called network'))
        os.environ['FABRIC_DID_ENABLED'] = 'false'
        self.assertEqual(service.get_backend_status(factory)['status'], 'DISABLED')
        os.environ['FABRIC_DID_ENABLED'] = 'true'
        os.environ['FABRIC_DID_CHAIN_ID'] = ''
        status = service.get_backend_status(factory)
        self.assertEqual(status['status'], 'NOT_CONFIGURED')
        self.assertEqual(status['missingFields'], ['FABRIC_DID_CHAIN_ID'])
        os.environ['FABRIC_DID_CHAIN_ID'] = 'offline-channel'
        os.environ['INTERNAL_TOKEN'] = ''
        self.assertEqual(service.get_backend_status(factory)['missingFields'], ['INTERNAL_TOKEN'])
        factory.assert_not_called()

    def test_backend_status_only_exposes_safe_diagnostic_fields(self):
        client = MockBridge()
        client.status = lambda: dict(provider='FABRIC_DID', chainId='offline-channel', enabled=True,
                                    configured=False, writeEnabled=False, status='NOT_CONFIGURED',
                                    missingFields=['FABRIC_DID_PROPERTIES_FILE', 'certificatePath', '/secret/key.pem', ENV['INTERNAL_TOKEN']],
                                    privateKey='never-expose', msg='never-expose', sdkResult='never-expose')
        status = service.get_backend_status(lambda: client)
        self.assertEqual(status['status'], 'NOT_CONFIGURED')
        self.assertEqual(status['missingFields'], ['FABRIC_DID_PROPERTIES_FILE', 'certificatePath'])
        self.assertFalse(status['networkChecked'])
        self.assertNotIn('never-expose', json.dumps(status))
        self.assertNotIn(ENV['INTERNAL_TOKEN'], json.dumps(status))
        self.assertTrue(client.closed)

    def test_backend_status_rejects_wrong_chain_and_reports_unavailable(self):
        client = MockBridge()
        client.status = lambda: dict(provider='FABRIC_DID', chainId='wrong-chain', status='READY')
        status = service.get_backend_status(lambda: client)
        self.assertEqual(status['status'], 'UNAVAILABLE')
        self.assertFalse(status['configured'])
        self.assertEqual(status['lastError'], 'BRIDGE_CHAIN_IDENTITY_MISMATCH')

    def test_backend_status_readonly_is_not_reported_write_ready(self):
        os.environ['FABRIC_DID_WRITE_ENABLED'] = 'false'
        status = service.get_backend_status(MockBridge)
        self.assertEqual(status['status'], 'READY_READ_ONLY')
        self.assertFalse(status['writeEnabled'])
        self.assertTrue(status['configured'])
        self.assertFalse(status['networkChecked'])

    def test_binding_status_getter_never_contacts_bridge_or_creates_jobs(self):
        key = self.key()
        with patch('pqkds.fabric_did_client.requests.Session', side_effect=AssertionError('getter contacted network')):
            displayed = service.get_binding_status(key)
        self.assertEqual(displayed['status'], 'PENDING')
        self.assertEqual(ChainKeyBinding.objects.count(), 1)

    def test_retired_key_getter_uses_retirement_event_not_old_active_confirmation(self):
        key = self.key()
        original = key.chain_bindings.get()
        self.assertEqual(service.process_binding(original.pk, MockBridge), 'CONFIRMED')
        public_key = key.public_key
        rotated = registry.rotate_public_key(self.node, algorithm='SM2', public_key='new', key_id=key.key_id, key_version=2)
        key.refresh_from_db()
        displayed = service.get_binding_status(key)
        self.assertEqual(displayed['status'], 'PENDING')
        self.assertEqual(displayed['boundKeyStatus'], 'RETIRED')
        self.assertEqual(displayed['currentKeyStatus'], 'RETIRED')
        self.assertTrue(displayed['statusMatchesCurrentKey'])
        self.assertEqual(key.public_key, public_key)
        original.refresh_from_db()
        self.assertEqual(original.status, 'CONFIRMED')
        self.assertEqual(json.loads(original.metadata)['status'], 'ACTIVE')
        self.assertEqual(service.get_binding_status(rotated)['boundKeyStatus'], 'ACTIVE')

    def test_historical_confirmation_does_not_claim_changed_key_status_confirmed(self):
        key = self.key()
        row = key.chain_bindings.get()
        self.assertEqual(service.process_binding(row.pk, MockBridge), 'CONFIRMED')
        # 模拟历史外部路径漏记退休任务；诊断也必须承认旧证据与当前状态不同。
        NodeLongTermKey.objects.filter(pk=key.pk).update(status='RETIRED', active_slot=None)
        key.refresh_from_db()
        displayed = service.get_binding_status(key)
        self.assertEqual(displayed['status'], 'STALE_BINDING')
        self.assertEqual(displayed['evidenceStatus'], 'CONFIRMED')
        self.assertEqual(displayed['boundKeyStatus'], 'ACTIVE')
        self.assertEqual(displayed['currentKeyStatus'], 'RETIRED')
        self.assertFalse(displayed['statusMatchesCurrentKey'])

    def test_namespace_changed_never_relabels_old_confirmed_evidence(self):
        key = self.key()
        row = key.chain_bindings.get()
        self.assertEqual(service.process_binding(row.pk, MockBridge), 'CONFIRMED')
        os.environ['FABRIC_DID_NAMESPACE'] = 'other-app'
        displayed = service.get_binding_status(key)
        self.assertEqual(displayed['status'], 'NOT_REGISTERED')
        self.assertEqual(displayed['namespace'], 'other-app')
        row.refresh_from_db()
        self.assertEqual(row.namespace, 'kms-key-binding-v1')
        self.assertEqual(row.status, 'CONFIRMED')
        os.environ['FABRIC_DID_NAMESPACE'] = 'kms-key-binding-v1'
        self.assertEqual(service.get_binding_status(key)['status'], 'CONFIRMED')

    def test_namespace_changed_worker_does_not_submit_old_scope(self):
        key = self.key()
        row = key.chain_bindings.get()
        os.environ['FABRIC_DID_NAMESPACE'] = 'other-app'
        factory = Mock(side_effect=AssertionError('wrong-namespace network call'))
        self.assertEqual(service.process_binding(row.pk, factory), 'NOT_CONFIGURED')
        factory.assert_not_called()
        row.refresh_from_db()
        self.assertEqual(row.last_error, 'NAMESPACE_CONFIGURATION_CHANGED')
        self.assertEqual(row.namespace, 'kms-key-binding-v1')
        rotated = registry.rotate_public_key(self.node, algorithm='SM2', public_key='new', key_id=key.key_id, key_version=2)
        original = service.process_binding
        with patch.object(service, 'process_binding', side_effect=lambda pk: original(pk, MockBridge)):
            self.assertEqual(service.process_pending_bindings(limit=10), {'NOT_CONFIGURED': 1, 'CONFIRMED': 2})
        self.assertEqual(service.get_binding_status(rotated)['namespace'], 'other-app')

    def test_namespace_is_part_of_database_idempotency_scope(self):
        key = self.key()
        first = key.chain_bindings.get()
        os.environ['FABRIC_DID_NAMESPACE'] = 'other-app'
        with transaction.atomic():
            second = service.enqueue_binding(key, 'REGISTERED')
            retry = service.enqueue_binding(key, 'REGISTERED')
        self.assertEqual(retry.pk, second.pk)
        self.assertNotEqual(first.pk, second.pk)
        self.assertNotEqual(first.event_id, second.event_id)
        self.assertEqual(second.namespace, 'other-app')
        self.assertEqual(json.loads(second.metadata)['namespace'], 'other-app')
        self.assertEqual(ChainKeyBinding.objects.count(), 2)

    def test_legacy_binding_getter_never_queries_unapplied_new_table(self):
        key = self.key()
        os.environ['KMS_CHAIN_BACKEND'] = 'legacy'
        with patch.object(ChainKeyBinding.objects, 'filter', side_effect=AssertionError('legacy queried new binding table')):
            self.assertEqual(service.get_binding_status(key)['status'], 'LEGACY')

    def test_pending_worker_drains_ordered_events_in_one_explicit_pass(self):
        key = self.key()
        registry.rotate_public_key(self.node, algorithm='SM2', public_key='new', key_id=key.key_id, key_version=2)
        original = service.process_binding
        with patch.object(service, 'process_binding', side_effect=lambda pk: original(pk, MockBridge)):
            self.assertEqual(service.process_pending_bindings(limit=10), {'CONFIRMED': 3})
        self.assertEqual(ChainKeyBinding.objects.filter(status='CONFIRMED').count(), 3)

    def test_failed_node_does_not_starve_other_node_at_small_limit(self):
        key = self.key()
        first = key.chain_bindings.get()
        registry.rotate_public_key(self.node, algorithm='SM2', public_key='new', key_id=key.key_id, key_version=2)
        ChainKeyBinding.objects.filter(pk=first.pk).update(status='FAILED')
        other = Node.objects.create(node_id='other-offline', name='Other', ip_address='127.0.0.1', port=5678)
        row = registry.register_public_key(other, algorithm='SM2', public_key='other', key_id='other-key').chain_bindings.get()
        original = service.process_binding
        with patch.object(service, 'process_binding', side_effect=lambda pk: original(pk, MockBridge)):
            self.assertEqual(service.process_pending_bindings(limit=1), {'CONFIRMED': 1})
        row.refresh_from_db()
        self.assertEqual(row.status, 'CONFIRMED')

    def test_new_chain_jobs_do_not_claim_old_empty_chain_evidence_confirmed(self):
        os.environ['FABRIC_DID_CHAIN_ID'] = ''
        key = self.key()
        old = key.chain_bindings.get()
        os.environ['FABRIC_DID_CHAIN_ID'] = 'offline-channel'
        rotated = registry.rotate_public_key(self.node, algorithm='SM2', public_key='new', key_id=key.key_id, key_version=2)
        original = service.process_binding
        with patch.object(service, 'process_binding', side_effect=lambda pk: original(pk, MockBridge)):
            self.assertEqual(service.process_pending_bindings(limit=10), {'NOT_CONFIGURED': 1, 'CONFIRMED': 2})
        old.refresh_from_db()
        self.assertEqual(old.chain_id, '')
        self.assertEqual(old.status, 'NOT_CONFIGURED')
        self.assertEqual(service.get_binding_status(rotated)['chainId'], 'offline-channel')

    def test_explicit_command_refuses_legacy_and_bad_limit(self):
        from django.core.management import call_command, CommandError
        from io import StringIO
        os.environ['KMS_CHAIN_BACKEND'] = 'legacy'
        with self.assertRaises(CommandError):
            call_command('process_chain_bindings', stdout=StringIO())
        os.environ['KMS_CHAIN_BACKEND'] = 'fabric-did'
        with self.assertRaises(CommandError):
            call_command('process_chain_bindings', limit=0, stdout=StringIO())

    def test_multiple_rotations_keep_each_retired_version_snapshot(self):
        first = self.key()
        second = registry.rotate_public_key(self.node, algorithm='SM2', public_key='second', key_id=first.key_id, key_version=2)
        registry.rotate_public_key(self.node, algorithm='SM2', public_key='third', key_id=first.key_id, key_version=3)
        snapshots = list(second.chain_bindings.order_by('sequence').values_list('key_status', flat=True))
        self.assertEqual(snapshots, ['ACTIVE', 'RETIRED'])
        self.assertEqual(ChainKeyBinding.objects.count(), 5)

    def test_failed_chain_verification_is_terminal_not_false_pending(self):
        key = self.key()
        row = key.chain_bindings.get()
        client = MockBridge()
        original = client.verify
        client.verify = lambda binding: dict(original(binding), status='FAILED', transactionValid=False)
        self.assertEqual(service.process_binding(row.pk, lambda: client), 'FAILED')
        row.refresh_from_db()
        self.assertFalse(row.transaction_valid)
        key.refresh_from_db()
        self.assertEqual(key.status, 'ACTIVE')

    def test_readonly_can_verify_original_tx_but_cannot_submit(self):
        row = self.key().chain_bindings.get()
        self.assertEqual(service.process_binding(row.pk, lambda: MockBridge(verify_pending=True)), 'PENDING_VERIFICATION')
        os.environ['FABRIC_DID_WRITE_ENABLED'] = 'false'
        client = MockBridge()
        client.status = lambda: dict(provider='FABRIC_DID', chainId='offline-channel', enabled=True, configured=True,
                                     writeEnabled=False, status='READY_READ_ONLY')
        self.assertEqual(service.process_binding(row.pk, lambda: client), 'CONFIRMED')
        self.assertNotIn('submit', client.calls)

    def test_status_timeout_is_retryable_without_losing_unprepared_job(self):
        row = self.key().chain_bindings.get()
        client = MockBridge()
        client.status = Mock(side_effect=BindingError('BRIDGE_TIMEOUT'))
        self.assertEqual(service.process_binding(row.pk, lambda: client), 'PENDING')
        self.assertEqual(service.process_binding(row.pk, lambda: MockBridge()), 'CONFIRMED')

    def test_real_localhost_http_drives_registry_outbox_and_confirmation(self):
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from threading import Thread
        received = []
        prepared = {}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def reply(self, data):
                body = json.dumps({'code': 200, 'msg': 'ok', 'data': data}, ensure_ascii=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def do_GET(self):
                received.append(('GET', self.path, self.headers.get('X-Internal-Token')))
                self.reply(dict(provider='FABRIC_DID', chainId='offline-channel', enabled=True, configured=True,
                                writeEnabled=True, status='READY'))
            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
                received.append(('POST', self.path, self.headers.get('X-Internal-Token'), data))
                if self.path.endswith('/prepare'):
                    metadata = service.canonical_json(data)
                    prepared.update(provider='FABRIC_DID', chainId='offline-channel', metadata=metadata,
                                    metadataDigest=service.digest_metadata(metadata), txId='a' * 64, nonce='b' * 48,
                                    did='did:offline:binding:' + service.digest_metadata(metadata))
                    self.reply(prepared)
                elif self.path.endswith('/submit'):
                    self.reply(dict(prepared, status='PENDING_VERIFICATION'))
                elif self.path.endswith('/verify'):
                    self.reply(dict(prepared, status='CONFIRMED', transactionValid=True, metadataMatches=True))
        server = HTTPServer(('127.0.0.1', 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            os.environ['FABRIC_DID_BRIDGE_URL'] = f'http://127.0.0.1:{server.server_port}/internal/fabric-did'
            key = self.key()
            row = key.chain_bindings.get()
            self.assertEqual(service.process_binding(row.pk), 'CONFIRMED')
            displayed = service.get_binding_status(key)
            self.assertEqual(displayed['txId'], 'a' * 64)
            self.assertEqual(displayed['status'], 'CONFIRMED')
            backend_status = service.get_backend_status()
            self.assertEqual(backend_status['status'], 'READY')
            self.assertFalse(backend_status['networkChecked'])
            self.assertEqual([entry[1].rsplit('/', 1)[-1] for entry in received], ['status', 'prepare', 'submit', 'verify', 'status'])
            self.assertTrue(all(entry[2] == ENV['INTERNAL_TOKEN'] for entry in received))
            self.assertEqual(received[1][3], json.loads(row.metadata))
            self.assertEqual(received[2][3]['binding'], received[1][3])
            self.assertEqual(received[2][3]['nonce'], 'b' * 48)
            self.assertEqual(received[3][3]['expectedMetadata'], row.metadata)
            self.assertEqual(received[3][3]['txId'], 'a' * 64)
            # 同一个真实 HTTP 驱动再恢复一次已持久化、但从未取得提交机会的计划。
            resumed_key = self.key(algorithm='SSCL', key_id='prepared-other', public_key='other-public')
            resumed = resumed_key.chain_bindings.get()
            prepared.clear()
            prepared.update(provider=resumed.provider, chainId=resumed.chain_id,
                            metadata=resumed.metadata, metadataDigest=resumed.metadata_digest,
                            did='did:offline:binding:' + resumed.metadata_digest, txId='c' * 64, nonce='d' * 48)
            ChainKeyBinding.objects.filter(pk=resumed.pk).update(
                status='PREPARED', did=prepared['did'], tx_id=prepared['txId'], nonce=prepared['nonce'],
            )
            offset = len(received)
            self.assertEqual(service.process_binding(resumed.pk), 'CONFIRMED')
            recovery = received[offset:]
            self.assertEqual([entry[1].rsplit('/', 1)[-1] for entry in recovery], ['status', 'submit', 'verify'])
            self.assertEqual(recovery[1][3]['txId'], 'c' * 64)
            self.assertEqual(recovery[1][3]['nonce'], 'd' * 48)
            self.assertEqual(recovery[1][3]['binding'], json.loads(resumed.metadata))
            self.assertEqual(recovery[2][3]['expectedMetadata'], resumed.metadata)
            self.assertEqual(recovery[2][3]['txId'], 'c' * 64)
            self.assertEqual(service.get_binding_status(resumed_key)['status'], 'CONFIRMED')
            self.assertEqual(service.process_binding(resumed.pk), 'BLOCKED')
            self.assertEqual(len(received), offset + 3)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_new_model_migration_matches_runtime_fields(self):
        migration = importlib.import_module('pqkds.migrations.0026_chain_key_binding').Migration
        operation = migration.operations[0]
        self.assertEqual(operation.name, 'ChainKeyBinding')
        runtime = {field.name: field.deconstruct()[1:] for field in ChainKeyBinding._meta.local_fields}
        stored = {name: field.deconstruct()[1:] for name, field in operation.fields}
        self.assertEqual(runtime, stored)
        self.assertEqual(operation.options['db_table'], ChainKeyBinding._meta.db_table)
        self.assertEqual(operation.options['constraints'], ChainKeyBinding._meta.constraints)
        self.assertEqual(operation.options['indexes'], ChainKeyBinding._meta.indexes)


if __name__ == '__main__':
    unittest.main(verbosity=2)
