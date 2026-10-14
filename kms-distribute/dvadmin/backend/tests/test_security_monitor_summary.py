"""Admin aggregate contract; mocked data sources, no business writes or database reset."""
import json
import os
import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
import django

django.setup()
from django.test import RequestFactory
from pqkds import security_monitor_views as S


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def request(self, identity=None):
        request = self.factory.get('/api/pqkds/security-monitor/summary/')
        request.kms_identity = identity or {'entryMode': 'DEMO', 'principalType': 'ADMIN',
                                          'roleLevel': 0, 'userId': -1}
        return request

    def counts(self, rows):
        with patch.object(S.connection, 'cursor') as cursor:
            cur = cursor.return_value.__enter__.return_value
            cur.fetchall.return_value = rows
            result = S._kms_counts()
            sql = cur.execute.call_args.args[0]
            self.assertIn('COUNT(*)', sql)
            self.assertIn('GROUP BY status, encryt_type', sql)
            self.assertNotIn('LIMIT', sql.upper())
            self.assertNotIn('key_value', sql)
            self.assertNotIn('SELECT *', sql)
            return result

    def test_empty_database_is_zero_not_unavailable(self):
        result = self.counts([])
        self.assertEqual(result['total'], 0)
        self.assertEqual(result['byStatus'], {'0': 0, '1': 0, '2': 0, '3': 0})
        self.assertEqual(result['byType'], {})

    def test_counts_above_page_cap_include_every_status_and_type(self):
        result = self.counts([('0', 'SM2', 1801), ('1', 'SM2', 19),
                              ('2', 'SSCL', 12), ('3', 'KYBER', 8),
                              ('0', 'KYBER', 9), ('unexpected', None, 2)])
        self.assertEqual(result['total'], 1851)
        self.assertEqual([result[k] for k in ('active', 'frozen', 'rotating', 'revoked')],
                         [1810, 19, 12, 8])
        self.assertEqual(result['byType'], {'SM2': 1820, 'SSCL': 12, 'KYBER': 17, 'unknown': 2})
        self.assertEqual(result['byStatus']['unexpected'], 2)

    def test_non_admin_and_missing_or_invalid_role_rejected_before_sources(self):
        for identity in [
                {'entryMode': 'DEMO', 'principalType': 'NODE', 'roleLevel': 0},
                {'entryMode': 'DEMO', 'principalType': 'ADMIN', 'roleLevel': 1},
                {'entryMode': 'DEMO', 'principalType': 'ADMIN'},
                {'entryMode': 'DEMO', 'principalType': 'ADMIN', 'roleLevel': 'invalid'}]:
            with patch.object(S, '_kms_counts') as keys, patch.object(S.Node.objects, 'count') as nodes:
                response = S.security_summary(self.request(identity))
                self.assertEqual(response.status_code, 403)
                keys.assert_not_called()
                nodes.assert_not_called()

    def test_partial_source_failure_is_null_and_no_material_or_list_fetch(self):
        with ExitStack() as stack:
            managers = {}
            for name in ('Node', 'PreDistributedKey', 'SessionKey'):
                manager = stack.enter_context(patch.object(getattr(S, name), 'objects'))
                manager.count.return_value = 0
                manager.filter.return_value.count.return_value = 0
                manager.values_list.return_value.distinct.return_value = []
                managers[name] = manager
            stack.enter_context(patch.object(S, '_kms_counts', side_effect=RuntimeError('source offline')))
            stack.enter_context(patch.object(S, '_anomaly_counts', side_effect=RuntimeError('source offline')))
            stack.enter_context(patch.object(S, '_distribution_stats', return_value={
                'total': 0, 'byStatus': {}, 'successRate': None, 'crossDomain': {}}))
            response = S.security_summary(self.request())
            self.assertEqual(response.status_code, 200)
            body = json.loads(response.content)['data']
            self.assertIsNone(body['keys'])
            self.assertIsNone(body['anomalies'])
            self.assertEqual(body['nodes']['total'], 0)
            self.assertEqual(body['pool']['total'], 0)
            self.assertEqual(body['sessions']['total'], 0)
            self.assertIsNone(body['distribution']['successRate'])
            for manager in managers.values():
                manager.all.assert_not_called()
            serialized = json.dumps(body)
            for field in ('key_value', 'private_key', 'encrypted_key', 'ciphertext', 'public_key'):
                self.assertNotIn(field, serialized)

    def test_safe_distinguishes_failure_from_empty_distribution(self):
        self.assertIsNone(S._safe(lambda: 1 / 0, 'failure'))
        self.assertEqual(S._safe(lambda: 0, 'empty'), 0)
        with patch.object(S.DistributionBatch, 'objects') as manager:
            manager.count.return_value = 0
            manager.filter.return_value.count.return_value = 0
            stats = S._distribution_stats()
            self.assertEqual(stats['total'], 0)
            self.assertIsNone(stats['successRate'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
