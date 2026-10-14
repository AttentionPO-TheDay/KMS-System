"""Pool pagination against an isolated in-memory database, no business writes."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pqkds.test_fabric_bindings_offline as fixture
from django.db import connection
from django.test.utils import CaptureQueriesContext
from pqkds.models import Node, PreDistributedKey, SessionKey
from pqkds.security_monitor_views import _pool_summary


class PoolPaginationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with connection.schema_editor() as editor:
            editor.create_model(SessionKey)
            editor.create_model(PreDistributedKey)
        node = Node.objects.create(node_id='pagination-only', name='pagination-only',
                                   ip_address='127.0.0.1', port=1)
        PreDistributedKey.objects.bulk_create([
            PreDistributedKey(node1=node, pool_id='pagination-only', key_index=i,
                              algorithm='kyber_kem', status='READY', expires_at='2030-01-01')
            for i in range(301)
        ])
        # Force a timestamp tie to verify deterministic id ordering.
        PreDistributedKey.objects.update(create_datetime='2026-01-01 00:00:00')

    def test_total_and_pages_beyond_200(self):
        ids = list(PreDistributedKey.objects.order_by('-id').values_list('id', flat=True))
        for page in (1, 20, 21, 30, 31):
            with CaptureQueriesContext(connection) as queries:
                result = _pool_summary({'poolPage': str(page)})
            self.assertEqual(result['total'], 301)
            self.assertEqual(result['ready'], 301)
            self.assertEqual(result['page'], page)
            self.assertEqual(result['pageSize'], 10)
            self.assertEqual([row['id'] for row in result['items']], ids[(page - 1)*10:page*10])
            self.assertTrue(any('LIMIT 10' in q['sql'] for q in queries))
            for row in result['items']:
                for private in ('encrypted_key', 'key_hash', 'key_value', 'ciphertext'):
                    self.assertNotIn(private, row)

    def test_invalid_parameters_and_last_page(self):
        for params, page, size in [
            ({'poolPage': '999'}, 31, 10),
            ({'poolPage': '-1', 'poolPageSize': 'bad'}, 1, 10),
            ({'poolPage': 'bad'}, 1, 10),
            ({'poolPageSize': '10000'}, 1, 100),
            ({'poolPageSize': '0'}, 1, 1),
        ]:
            result = _pool_summary(params)
            self.assertEqual((result['page'], result['pageSize']), (page, size))
            self.assertLessEqual(len(result['items']), size)

    def test_empty_and_growth_are_counted_dynamically(self):
        # Raw delete avoids unrelated model cascades in this minimal test schema.
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM ' + connection.ops.quote_name(PreDistributedKey._meta.db_table))
        result = _pool_summary({'poolPage': '31'})
        self.assertEqual((result['total'], result['page'], result['items']), (0, 1, []))
        node = Node.objects.get(node_id='pagination-only')
        PreDistributedKey.objects.create(node1=node, pool_id='new', key_index=0,
                                         algorithm='kyber_kem', status='READY', expires_at='2030-01-01')
        self.assertEqual(_pool_summary({})['total'], 1)
        # Restore fixture for independently ordered tests.
        PreDistributedKey.objects.bulk_create([
            PreDistributedKey(node1=node, pool_id='restored', key_index=i,
                              algorithm='kyber_kem', status='READY', expires_at='2030-01-01') for i in range(300)
        ])
        PreDistributedKey.objects.update(create_datetime='2026-01-01 00:00:00')


if __name__ == '__main__':
    unittest.main(verbosity=2)
