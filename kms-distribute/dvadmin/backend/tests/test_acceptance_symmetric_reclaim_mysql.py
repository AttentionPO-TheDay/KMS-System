"""Opt-in: KMS_ACCEPTANCE_MYSQL_TEST=1 python tests/test_acceptance_symmetric_reclaim_mysql.py."""
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


@unittest.skipUnless(os.environ.get('KMS_ACCEPTANCE_MYSQL_TEST') == '1', 'opt-in MySQL integration')
class SymmetricReclamationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
        import django
        django.setup()
        from pqkds import acceptance_symmetric_reclaim
        cls.service = acceptance_symmetric_reclaim

    def fingerprint(self, observer=None):
        from django.db import connection
        rows = []
        with (observer or connection).cursor() as cursor:
            for model in self.service.ISOLATED_MODELS:
                table = connection.ops.quote_name(model._meta.db_table)
                cursor.execute(f'CHECKSUM TABLE {table}')
                rows.append(cursor.fetchone())
        return rows

    def test_real_12000_sm4_deletions_preserve_controls_and_persistent_data(self):
        from django.db import connection
        before = self.fingerprint()
        original = self.service.create_fixture

        def observe(count):
            rows = original(count)
            observer = connection.copy(alias='symmetric-observer')
            try:
                self.assertEqual(self.fingerprint(observer), before)
            finally:
                observer.close()
            return rows

        with patch.object(self.service, 'create_fixture', side_effect=observe), \
                patch('pqkds.key_pool_local_storage.cleanup_expired_local_pools') as local_cleanup:
            evidence = self.service.run_symmetric_reclamation()
            local_cleanup.assert_not_called()
        self.assertTrue(evidence['passed'])
        self.assertTrue(evidence['cleanupComplete'])
        self.assertTrue(evidence['materialVerified'])
        self.assertEqual(evidence['injected'], 12000)
        self.assertEqual(evidence['reclaimed'], 12000)
        self.assertEqual(evidence['remaining'], 0)
        self.assertEqual(evidence['controlsPassed'], 4)
        self.assertEqual(sum(row['eligible'] and row['deleted'] for row in evidence['rows']), 12000)
        self.assertEqual(len({row['keyHash'] for row in evidence['rows']}), 12004)
        self.assertEqual(self.fingerprint(), before)
        self.assertGreater(evidence['elapsedMs'], 0)
        print('measured:', json.dumps({k: v for k, v in evidence.items() if k != 'rows'}))
        output = os.environ.get('KMS_ACCEPTANCE_EVIDENCE_OUTPUT')
        if output:
            Path(output).write_text(json.dumps(dict(code=200, data=evidence)), encoding='utf-8')

    def test_error_cleans_temporary_tables_and_next_run_works(self):
        before = self.fingerprint()
        with patch.object(self.service.KeyPoolService, 'cleanup_expired', side_effect=RuntimeError('injected failure')):
            with self.assertRaisesRegex(RuntimeError, 'injected failure'):
                self.service.run_symmetric_reclamation(2)
        self.assertEqual(self.fingerprint(), before)
        self.assertTrue(self.service.run_symmetric_reclamation(2)['passed'])
        self.assertEqual(self.fingerprint(), before)

    def test_undeleted_samples_are_not_counted_as_reclaimed(self):
        with patch.object(self.service.KeyPoolService, 'cleanup_expired', return_value={'cleaned': 99999}):
            evidence = self.service.run_symmetric_reclamation(2)
        self.assertEqual(evidence['reclaimed'], 0)
        self.assertEqual(evidence['remaining'], 2)
        self.assertFalse(evidence['passed'])

    def test_fixed_internal_endpoint_rejects_untrusted_calls_and_parameters(self):
        from django.test import RequestFactory
        from pqkds import acceptance_symmetric_reclaim_views as view
        factory = RequestFactory()
        with patch.object(view, '_internal_token_ok', return_value=False):
            self.assertEqual(view.internal_symmetric_reclamation(factory.post('/', '{}', content_type='application/json')).status_code, 403)
        with patch.object(view, '_internal_token_ok', return_value=True), patch.object(self.service, 'run_symmetric_reclamation') as run:
            for body in ('[]', 'null', 'true', 'bad json', '{"keyIds":[1]}', '{"count":1}'):
                self.assertEqual(view.internal_symmetric_reclamation(factory.post('/', body, content_type='application/json')).status_code, 400)
            run.assert_not_called()
        self.assertEqual(view.internal_symmetric_reclamation(factory.get('/')).status_code, 405)


if __name__ == '__main__':
    unittest.main(verbosity=2)
