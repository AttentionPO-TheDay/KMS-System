"""Disposable MySQL smoke test. Only connects to the fixed isolated test hostname."""
import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from django.apps import AppConfig
from django.conf import settings


class TestConfig(AppConfig):
    name = 'pqkds'
    default_auto_field = 'django.db.models.BigAutoField'


assert not settings.configured
settings.configure(SECRET_KEY='test-only', USE_TZ=False,
    INSTALLED_APPS=[__name__ + '.TestConfig'], DEFAULT_AUTO_FIELD='django.db.models.BigAutoField',
    DATABASES={'default': {'ENGINE': 'django.db.backends.mysql', 'NAME': 'test_admin_data',
        'HOST': 'kms-admin-data-test-mysql', 'USER': 'root', 'PASSWORD': 'test-only-disposable',
        'OPTIONS': {'charset': 'utf8mb4'}}})
from django.db import models
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
from pqkds.models import BlockchainConfig, Node, SystemParameters, FalconKeyPair, KeyDistributionLog, DistributionBatch
from pqkds import admin_data_views as A

assert connection.settings_dict['HOST'] == 'kms-admin-data-test-mysql'
with connection.schema_editor() as editor:
    for model in (BlockchainConfig, Node, SystemParameters, FalconKeyPair, KeyDistributionLog, DistributionBatch):
        editor.create_model(model)
source = Node.objects.create(node_id='TEST_SOURCE', name='Test', domain_id='A', ip_address='127.0.0.1', port=1)
target = Node.objects.create(node_id='TEST_TARGET', name='Test', domain_id='B', ip_address='127.0.0.1', port=2)
KeyDistributionLog.objects.bulk_create([KeyDistributionLog(node=source, action='pool_consume', success=True,
    details=json.dumps(dict(batchId=f'TEST_BATCH_{i:04}', peerNodeCode=target.node_id, algorithm='gm_sm2')))
    for i in range(601)])
DistributionBatch.objects.create(batch_id='TEST_BATCH_0000', user_id=1, wrapping_algorithm='gm_sm2',
    status='partial', distribution_type='cross')
result = A.distribution_records({'page': '30', 'pageSize': '20'})
assert result['total'] == 601 and len(result['items']) == 20
assert result['summary']['byStatus'] == {'partial': 1, 'success': 600}
assert A.distribution_records({'node': 'TEST_TARGET'})['total'] == 600
assert A.distribution_records({'node': "' OR 1=1 --"})['total'] == 0
# More than GROUP_CONCAT's default 1024 bytes, including a late receiver.
KeyDistributionLog.objects.bulk_create([KeyDistributionLog(node=source, action='pool_consume', success=True,
    details=json.dumps(dict(batchId='TEST_LONG_BATCH', peerNodeCode=f'TEST_RECEIVER_{i:04}')))
    for i in range(100)])
assert A.distribution_records({'node': 'TEST_RECEIVER_0099'})['total'] == 1
with connection.cursor() as cursor:
    cursor.execute('CREATE DATABASE kms')
    cursor.execute('CREATE TABLE kms.keymanage (key_id INT PRIMARY KEY, user_name VARCHAR(64), encryt_name VARCHAR(64), key_name VARCHAR(64), key_domain VARCHAR(64), version INT, status VARCHAR(8), chain_status VARCHAR(8), chain_hash VARCHAR(128), block_height INT, cre_time DATETIME)')
    cursor.executemany('INSERT INTO kms.keymanage VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)', [
        (i, 'acceptance_user', 'SSCL', 'acceptance-load', 'acceptance', 1, '0', '0', '', None, '2026-10-13 20:00:00')
        for i in range(1, 322)])
    cursor.execute("INSERT INTO kms.keymanage VALUES (999,'admin','SSCL','business','business',1,'0','0','',NULL,'2026-10-13 20:00:00')")
result = A.acceptance_records({'page': '16', 'pageSize': '20'})
assert result['total'] == 321 and len(result['items']) == 20
assert A.acceptance_records({'q': "' OR 1=1 --"})['total'] == 0
print('PASS: MySQL 8 JSON aggregation, >500 batch pagination, deduplication, >1024-byte receivers, cross-database acceptance isolation and parameterized filters')
