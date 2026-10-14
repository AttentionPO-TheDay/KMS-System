"""Real pagination on SQLite :memory:, never production databases or business keys."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pqkds.test_fabric_bindings_offline as fixture
from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from pqkds.models import (Node, NodeLongTermKey, SessionKey, PreDistributedKey,
    FalconKeyPair, KeyDistributionLog, DistributionBatch, ChainKeyBinding)
from pqkds import admin_data_views as A


class AdminDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert connection.settings_dict['NAME'] == ':memory:'
        with connection.schema_editor() as editor:
            for model in (SessionKey, PreDistributedKey, FalconKeyPair, KeyDistributionLog, DistributionBatch):
                editor.create_model(model)
        cls.source = Node.objects.create(node_id='TEST_ONLY_SOURCE', domain_id='A', name='Test', ip_address='127.0.0.1', port=1)
        cls.target = Node.objects.create(node_id='TEST_ONLY_TARGET', domain_id='B', name='Test', ip_address='127.0.0.1', port=2)
        NodeLongTermKey.objects.bulk_create([NodeLongTermKey(node=cls.source,algorithm='SM2',key_id=f'TEST_ONLY_{i}',
            key_version=1,status='ACTIVE',public_key='DO_NOT_RETURN_PUBLIC_MATRIX') for i in range(321)])
        SessionKey.objects.bulk_create([SessionKey(node1=cls.source,node2=cls.target,session_id=f'TEST_SESSION_{i}',
            session_type='gm_sm2',status='established',encrypted_session_key='NEVER_RETURN_SECRET',expires_at='2030-01-01') for i in range(321)])
        PreDistributedKey.objects.bulk_create([PreDistributedKey(node1=cls.source,node2=cls.target,pool_id='TEST_POOL',
            key_index=i,algorithm='gm_sm2',wrapping_algorithm='gm_sm2',status='READY',encrypted_key_data='NEVER_RETURN_CIPHERTEXT',expires_at='2030-01-01') for i in range(321)])
        KeyDistributionLog.objects.bulk_create([KeyDistributionLog(node=cls.source,action='pool_consume',success=True,
            details=json.dumps(dict(batchId=f'TEST_BATCH_{i:04}',peerNodeCode=cls.target.node_id,algorithm='gm_sm2',keyHash='NEVER_RETURN_HASH')))
            for i in range(601)])
        # Authoritative batch overrides audit with the same ID; not counted twice.
        DistributionBatch.objects.create(batch_id='TEST_BATCH_0000',user_id=1,wrapping_algorithm='gm_sm2',status='partial',distribution_type='cross')
        with connection.cursor() as cursor:
            cursor.execute("ATTACH DATABASE ':memory:' AS kms")
            cursor.execute('CREATE TABLE kms.keymanage (key_id INTEGER PRIMARY KEY, user_name TEXT, encryt_name TEXT, key_name TEXT, key_domain TEXT, version INTEGER, status TEXT, chain_status TEXT, chain_hash TEXT, block_height INTEGER, cre_time TEXT)')
            cursor.executemany('INSERT INTO kms.keymanage VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)', [
                (i,'acceptance_user','SSCL','acceptance-load','acceptance',1,'0','0','',None,'2026-10-13 20:00:00') for i in range(1,322)])
            cursor.execute("INSERT INTO kms.keymanage VALUES (999,'admin','SSCL','not-test','business',1,'0','0','',NULL,'2026-10-13 20:00:00')")

    def test_keys_pool_sessions_real_pages_beyond_old_caps(self):
        for reader in (A.node_keys, A.pool_records, A.session_records):
            with CaptureQueriesContext(connection) as queries:
                result = reader({'page':'16','pageSize':'20'})
            self.assertEqual(result['total'],321)
            self.assertEqual((result['page'],len(result['items'])),(16,20))
            self.assertTrue(any('LIMIT 20 OFFSET 300' in q['sql'] for q in queries))
            self.assertNotIn('NEVER_RETURN',json.dumps(result))
            self.assertNotIn('DO_NOT_RETURN_PUBLIC_MATRIX',json.dumps(result))
        last=A.node_keys({'page':'999','pageSize':'20'})
        self.assertEqual((last['page'],len(last['items'])),(17,1))

    def test_filters_and_zero_results(self):
        self.assertEqual(A.node_keys({'q':'not-a-real-key'})['total'],0)
        self.assertEqual(A.node_keys({'status':'REVOKED'})['total'],0)
        self.assertEqual(A.session_records({'node':self.target.node_id})['total'],321)
        self.assertEqual(A.pool_records({'status':'READY','algorithm':'gm_sm2'})['total'],321)
        self.assertEqual(A.node_keys({'from':'2099-01-01'})['total'],0)

    def test_chain_metadata_is_verified_not_inferred_from_active(self):
        key=NodeLongTermKey.objects.first()
        ChainKeyBinding.objects.create(node=self.source,long_term_key=key,provider='FISCO',node_id_snapshot=self.source.node_id,
            algorithm=key.algorithm,key_id=key.key_id,key_version=1,key_ref='TEST_ONLY',event_type='REGISTERED',key_status='REGISTERED',
            sequence=1,event_id='TEST_ONLY_CHAIN',metadata='{}',metadata_digest='x',status='CONFIRMED',tx_id='TEST_ONLY_TX',
            block_height=19,transaction_valid=True,metadata_matches=True)
        record=A.node_keys({'q':key.key_id})['items'][0]
        self.assertTrue(record['chainBinding']['transactionValid'])
        self.assertEqual(record['chainBinding']['blockHeight'],19)

    def test_acceptance_is_paged_and_fenced_from_business_records(self):
        result=A.acceptance_records({'page':'16','pageSize':'20'})
        self.assertEqual(result['total'],321)
        self.assertEqual(len(result['items']),20)
        self.assertTrue(all(r['userName']=='acceptance_user' for r in result['items']))
        self.assertEqual(A.acceptance_records({'q':"' OR 1=1 --"})['total'],0)

    def test_distribution_all_batches_deduplicated_beyond_500(self):
        result=A.distribution_records({'page':'30','pageSize':'20'})
        self.assertEqual(result['total'],601)
        self.assertEqual(len(result['items']),20)
        self.assertEqual(result['summary']['byStatus'],{'partial':1,'success':600})
        self.assertEqual(result['summary']['byRange'],{'cross':601})
        self.assertNotIn('NEVER_RETURN_HASH',json.dumps(result))
        self.assertEqual(A.distribution_records({'status':'partial'})['total'],1)
        self.assertEqual(A.distribution_records({'node':self.target.node_id})['total'],600)
        self.assertEqual(A.distribution_records({'range':'same'})['total'],0)

    def request(self,params,identity=None):
        request=RequestFactory().get('/api/pqkds/security-monitor/records/',params)
        request.kms_identity=identity or dict(entryMode='DEMO',principalType='ADMIN',roleLevel=0)
        return request

    def test_admin_gate_and_safe_errors(self):
        from pqkds.demo_context import _check_scope
        admin = dict(entryMode='DEMO', principalType='ADMIN', roleLevel=0)
        request = self.request({'section': 'keys'}, admin)
        request.path = '/api/pqkds/security-monitor/records/'
        self.assertIsNone(_check_scope(request, admin))
        request.method = 'POST'
        self.assertEqual(_check_scope(request, admin).status_code, 403)
        request.method = 'GET'
        self.assertEqual(_check_scope(request, dict(principalType='NODE', userId=1)).status_code, 403)
        response=A.admin_data_records(self.request({'section':'keys'},dict(entryMode='DEMO',principalType='NODE',roleLevel=0)))
        self.assertEqual(response.status_code,403)
        for params in ({'section':'invalid'},{'section':'keys','page':'bad'},{'section':'keys','from':'bad'}):
            self.assertEqual(A.admin_data_records(self.request(params)).status_code,400)
        with patch.dict(A.READERS,{'keys':lambda _:1/0}):
            response=A.admin_data_records(self.request({'section':'keys'}))
            self.assertEqual(response.status_code,503)
            self.assertIsNone(json.loads(response.content)['data'])


if __name__=='__main__':unittest.main(verbosity=2)
