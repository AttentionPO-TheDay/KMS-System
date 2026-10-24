"""Disposable Docker MySQL only. Never loads production settings or credentials."""
import hashlib
import os
from pathlib import Path
import sys
import threading
import time
import types
import unittest
from concurrent.futures import ThreadPoolExecutor

host = os.getenv('EXTERNAL_SSCL_TEST_MYSQL_HOST', '')
if not host.startswith('kms-external-sscl-test-db-') or os.getenv('EXTERNAL_SSCL_DISPOSABLE_TEST') != '1':
    raise SystemExit('Run via tools/verify_external_sscl_mysql.py; refuses existing databases')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pymysql
pymysql.install_as_MySQLdb()
from django.apps import AppConfig
from django.conf import settings
from django.db import models


class TestConfig(AppConfig):
    name = 'pqkds'
    default_auto_field = 'django.db.models.BigAutoField'


settings.configure(SECRET_KEY='disposable-test-only', USE_TZ=False,
                   INSTALLED_APPS=[__name__ + '.TestConfig'], DEFAULT_AUTO_FIELD='django.db.models.BigAutoField',
                   DATABASES={'default': {'ENGINE': 'django.db.backends.mysql', 'NAME': 'external_sscl_test',
                              'HOST': host, 'USER': 'root', 'PASSWORD': 'offline-only-not-production',
                              'OPTIONS': {'isolation_level': 'read committed'}}})
module = types.ModuleType('dvadmin.utils.models')
def resolve(name):
    if name != 'CoreModel': raise AttributeError(name)
    class CoreModel(models.Model):
        id = models.BigAutoField(primary_key=True)
        create_datetime = models.DateTimeField(auto_now_add=True, null=True)
        update_datetime = models.DateTimeField(auto_now=True, null=True)
        class Meta: abstract = True
    module.CoreModel = CoreModel
    return CoreModel
module.__getattr__, module.table_prefix = resolve, 'dvadmin_'
sys.modules['dvadmin.utils.models'] = module
import django
django.setup()
from django.db import connection, connections
for attempt in range(60):
    try:
        connection.ensure_connection()
        break
    except Exception:
        if attempt == 59: raise
        time.sleep(.5)
from cryptography.fernet import Fernet
from pqkds import external_sscl as service
from pqkds.models import BlockchainConfig, Node, NodeLongTermKey, ChainKeyBinding, DidSdkHandoff, NodeKeyInspection, NodeKeyDidRecord, ExternalNodeActivation
from pqkds.sm2_crypto import SM2Crypto, SM2_N
with connection.schema_editor() as editor:
    for model in (BlockchainConfig, Node, NodeLongTermKey, ChainKeyBinding, DidSdkHandoff, NodeKeyInspection, NodeKeyDidRecord):
        editor.create_model(model)
# Exercise the actual 0039 operations over a pre-existing node schema and row.
old = Node.objects.create(node_id='preexisting-full-node', name='保留的旧节点', ip_address='127.0.0.1', port=1)
with connection.schema_editor() as editor:
    editor.remove_field(Node, Node._meta.get_field('initialization_profile'))
from django.db.migrations.state import ProjectState
from django.apps import apps
import importlib
state = ProjectState.from_apps(apps)
state.remove_model('pqkds', 'externalnodeactivation')
state.remove_field('pqkds', 'node', 'initialization_profile')
migration = importlib.import_module('pqkds.migrations.0039_external_sscl_activation').Migration
for migration_name in ('0039_external_sscl_activation', '0040_external_sm2_profile'):
    migration = importlib.import_module('pqkds.migrations.' + migration_name).Migration
    for operation in migration.operations:
        after = state.clone()
        operation.state_forwards('pqkds', after)
        with connection.schema_editor() as editor:
            operation.database_forwards('pqkds', editor, state, after)
        state = after
    if migration_name == '0039_external_sscl_activation':
        legacy = Node.objects.create(node_id='preexisting-sscl-node', name='保留的SSCL节点',
                                     initialization_profile='EXTERNAL_SSCL', ip_address='127.0.0.1', port=1)
old.refresh_from_db()
assert old.initialization_profile == 'FULL'
legacy.refresh_from_db()
assert legacy.initialization_profile == 'EXTERNAL_SSCL'
with connection.cursor() as cursor:
    cursor.execute('DELETE FROM ' + Node._meta.db_table + ' WHERE id IN (%s, %s)', [old.pk, legacy.pk])
print('MySQL: actual migrations 0039/0040 preserve FULL and EXTERNAL_SSCL nodes')
os.environ.update(FABRIC_DID_NODE_KEYGEN_ENABLED='true', FABRIC_DID_CHAIN_ID='offline', INTERNAL_TOKEN='offline-only', KMS_CHAIN_BACKEND='legacy', KMS_CHAIN_WRITES_ENABLED='false', KMS_NODE_FISCO_ENABLED='false')


class FakeBridge:
    def __init__(self): self.calls, self.plans, self.lock = [], {}, threading.Lock()
    def prepare_sys_pid(self, request):
        digest = hashlib.sha256(str(request).encode()).hexdigest()
        data = dict(provider='FABRIC_DID', chainId='offline', requestId=str(request), sysPid=(digest * 3)[:182], txId=digest, did='did:offline:' + digest, status='PREPARED', submitted=False)
        with self.lock:
            self.calls.append('prepare')
            self.plans[data['sysPid']] = data
        return dict(data)
    def submit_sys_pid(self, pid):
        assert not connection.in_atomic_block
        assert NodeKeyDidRecord.objects.get(sys_pid=pid).submit_started
        with self.lock: self.calls.append('submit')
        return dict(self.plans[pid], status='CONFIRMED', transactionValid=True, metadataMatches=True)
    def verify_sys_pid(self, pid):
        with self.lock: self.calls.append('verify')
        return dict(self.plans[pid], status='CONFIRMED', transactionValid=True, metadataMatches=True)
    def close(self): pass


class MysqlConcurrencyTests(unittest.TestCase):
    def setUp(self):
        with connection.cursor() as cursor:
            for model in (ExternalNodeActivation, NodeKeyDidRecord, ChainKeyBinding, NodeLongTermKey, Node):
                cursor.execute('DELETE FROM ' + model._meta.db_table)

    def test_parallel_sm2_activation_and_retries(self):
        self.check_parallel_activation('SM2')

    def test_parallel_legacy_sscl_activation_and_retries(self):
        self.check_parallel_activation('SSCL')

    def check_parallel_activation(self, algorithm):
        cipher, bridge = Fernet(Fernet.generate_key()), FakeBridge()
        counter, mutex = [], threading.Lock()
        def generator(identity, ua):
            with mutex: counter.append(identity)
            time.sleep(.2)
            f = lambda x: (7 + 3 * x + 2 * x * x) % SM2_N
            return dict(identity=identity, ua=ua, xIndex=[format(x, '064x') for x in range(1, 11)], yIndex=[format(f(x), '064x') for x in range(1, 11)], SSCLKey='04' + format(11, '064x') + format(f(11), '064x'), PPub=SM2Crypto.public_key_of(format(13, '064x')))
        barrier = threading.Barrier(8)
        def worker(_):
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                return service.activate('parallel-client', '并发待激活节点', cipher, algorithm=algorithm, generator=generator, did_factory=lambda: bridge)
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=8) as pool: first = list(pool.map(worker, range(8)))
        final, status = service.activate('parallel-client', '并发待激活节点', cipher, algorithm=algorithm, generator=generator, did_factory=lambda: bridge)
        self.assertEqual(status, 200)
        self.assertTrue(final['didConfirmed'])
        with ThreadPoolExecutor(max_workers=8) as pool: retries = list(pool.map(worker, range(8)))
        self.assertEqual(len(counter), 0 if algorithm == 'SM2' else 1)
        self.assertEqual(Node.objects.count(), 1)
        self.assertEqual(NodeLongTermKey.objects.count(), 1)
        self.assertEqual(ExternalNodeActivation.objects.count(), 1)
        self.assertEqual(NodeKeyDidRecord.objects.count(), 1)
        self.assertEqual(bridge.calls.count('prepare'), 1)
        self.assertEqual(bridge.calls.count('submit'), 1)
        for data, code in first + retries:
            self.assertIn(code, (200, 202))
            if data['publicKey']: self.assertEqual(data['publicKey'], final['publicKey'])
            if data['sysPid']: self.assertEqual(data['sysPid'], final['sysPid'])
        self.assertEqual(final['algorithm'], algorithm)
        self.assertEqual(final['initializationProfile'], 'EXTERNAL_' + algorithm)
        print('MySQL: 8 concurrent ' + algorithm + ' first requests + 8 retries; one key, one SysPid, one submit')
        data = service.query('parallel-client', sys_pid=final['sysPid'])
        self.assertEqual(data, final)
        original = service.unseal(cipher, ExternalNodeActivation.objects.get())
        material = service.private_key('parallel-client', cipher, sys_pid=final['sysPid'])
        expected = {'privateKey': original['privateKey'], 'curve': 'sm2p256v1'} if algorithm == 'SM2' else {k: original[k] for k in ('privateKey', 'domainPublicKey')}
        self.assertEqual(material, expected)
        if algorithm == 'SM2':
            self.assertEqual(SM2Crypto.public_key_of(material['privateKey']), final['publicKey'])
        # Default MySQL text comparisons ignore case; authorization must not.
        self.assertTrue(ExternalNodeActivation.objects.filter(client_id='PARALLEL-CLIENT').exists())
        for client, pid in (('PARALLEL-CLIENT', final['sysPid']), ('other-client', final['sysPid']),
                            ('parallel-client', '0' * 182)):
            with self.assertRaises(service.ActivationError) as caught:
                service.query(client, sys_pid=pid)
            self.assertEqual(caught.exception.status, 404)
            with self.assertRaises(service.ActivationError) as caught:
                service.private_key(client, cipher, sys_pid=pid)
            self.assertEqual(caught.exception.status, 404)
        self.assertEqual(len(counter), 0 if algorithm == 'SM2' else 1)
        self.assertEqual(bridge.calls.count('submit'), 1)
        print('MySQL: SysPid lookup, original private export and exact platform isolation pass under case-insensitive collation')


if __name__ == '__main__': unittest.main()
