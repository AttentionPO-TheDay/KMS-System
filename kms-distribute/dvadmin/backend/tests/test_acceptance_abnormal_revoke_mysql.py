"""Opt-in MySQL integration: KMS_ACCEPTANCE_MYSQL_TEST=1 python this_file.py.

The production scanner runs on temporary tables only. Persistent table fingerprints
and an independent observer connection prove that fixtures never enter business data.
KMS_ACCEPTANCE_SOURCE_DIR may point to a copied source directory inside a container.
"""
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


@unittest.skipUnless(os.environ.get('KMS_ACCEPTANCE_MYSQL_TEST') == '1', 'opt-in MySQL integration')
class AbnormalRevocationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
        import django
        django.setup()
        source = os.environ.get('KMS_ACCEPTANCE_SOURCE_DIR')
        if source:
            for name in ('auto_revoke_service', 'acceptance_revoke', 'acceptance_revoke_views'):
                spec = importlib.util.spec_from_file_location('pqkds.' + name, Path(source) / (name + '.py'))
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)
        from pqkds import acceptance_revoke
        cls.service = acceptance_revoke

    def fingerprint(self, observer=None):
        from django.db import connection
        rows = []
        with (observer or connection).cursor() as cursor:
            for model in self.service.MODELS:
                table = connection.ops.quote_name(model._meta.db_table)
                pk = connection.ops.quote_name(model._meta.pk.column)
                cursor.execute(f'SELECT COUNT(*), COALESCE(BIT_XOR(CRC32({pk})),0) FROM {table}')
                rows.append(cursor.fetchone())
        return rows

    def test_6000_real_anomalies_cross_two_batches_and_controls_preserved(self):
        from django.db import connection
        before = self.fingerprint()
        original = self.service.create_fixture
        original_scan = self.service.scan_once
        active_after_scan = []

        def observe_scan():
            result = original_scan()
            active_after_scan.append(self.service.NodeLongTermKey.objects.filter(status='ACTIVE').count())
            return result

        def observe(count):
            keys, expected = original(count)
            observer = connection.copy(alias='acceptance-observer')
            try:
                self.assertEqual(self.fingerprint(observer), before)
            finally:
                observer.close()
            return keys, expected

        with patch.object(self.service, 'create_fixture', side_effect=observe), \
                patch.object(self.service, 'scan_once', side_effect=observe_scan):
            result = self.service.run_abnormal_revocation()
        self.assertTrue(result['passed'])
        self.assertTrue(result['cleanupComplete'])
        for field in ('injected', 'attempted', 'detected', 'revoked', 'poolRevoked', 'sessionsRevoked', 'invalidations'):
            self.assertEqual(result[field], 6000, field)
        self.assertEqual(result['controlsPassed'], 4)
        self.assertEqual(len(result['rows']), 6004)
        self.assertEqual(result['version'], 2)
        self.assertEqual(result['batchLimit'], 5000)
        self.assertEqual([batch['revoked'] for batch in result['batches']], [5000, 1000])
        self.assertEqual([batch['attempted'] for batch in result['batches']], [5000, 1000])
        self.assertEqual(sum(row['attempted'] for row in result['rows']), 6000)
        self.assertEqual(active_after_scan, [1004, 4])
        self.assertEqual(self.fingerprint(), before)
        self.assertEqual(sum(row['revoked'] for row in result['rules']), 6000)
        output = os.environ.get('KMS_ACCEPTANCE_EVIDENCE_OUTPUT')
        if output:
            Path(output).write_text(json.dumps(dict(code=200, data=result)), encoding='utf-8')
        print('measured:', json.dumps({k: v for k, v in result.items() if k != 'rows'}))

    def test_unattempted_keys_are_separate_from_attempted_successes(self):
        before = self.fingerprint()
        original_scan = self.service.scan_once
        calls = []

        def stall_second_pass():
            calls.append(True)
            if len(calls) == 1:
                return original_scan()
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute('DELETE FROM kms_auto_revoke_candidates')
            return dict(keys=0, pool=0, sessions=0, elapsed_ms=0)

        with patch.object(self.service, 'scan_once', side_effect=stall_second_pass):
            result = self.service.run_abnormal_revocation()
        self.assertEqual(len(calls), 2)
        self.assertEqual(result['injected'], 6000)
        self.assertEqual(result['revoked'], 5000)
        self.assertEqual(result['attempted'], 5000)
        self.assertEqual(sum(row['abnormal'] and row['afterStatus'] == 'ACTIVE' for row in result['rows']), 1000)
        self.assertEqual(result['revoked'] * 100 / result['attempted'], 100)
        self.assertEqual(sum(not row['attempted'] and row['abnormal'] for row in result['rows']), 1000)
        self.assertFalse(result['passed'])
        self.assertTrue(result['cleanupComplete'])
        self.assertEqual(self.fingerprint(), before)

    def test_failure_drops_all_temporary_tables_and_next_run_works(self):
        before = self.fingerprint()
        with patch.object(self.service, 'scan_once', side_effect=RuntimeError('injected scanner failure')):
            with self.assertRaisesRegex(RuntimeError, 'injected scanner failure'):
                self.service.run_abnormal_revocation(12)
        self.assertEqual(self.fingerprint(), before)
        self.assertTrue(self.service.run_abnormal_revocation(12)['passed'])
        self.assertEqual(self.fingerprint(), before)

    def test_internal_view_rejects_untrusted_calls_and_business_object_parameters(self):
        from django.test import RequestFactory
        from pqkds import acceptance_revoke_views as view
        factory = RequestFactory()
        with patch.object(view, '_internal_token_ok', return_value=False):
            self.assertEqual(view.internal_abnormal_revocation(factory.post('/', '{}', content_type='application/json')).status_code, 403)
        with patch.object(view, '_internal_token_ok', return_value=True), patch.object(self.service, 'run_abnormal_revocation') as run:
            for body in ('[]', 'null', 'true', 'bad json', '{"nodeId":"business"}', '{"keyIds":[1]}', '{"count":5000}'):
                self.assertEqual(view.internal_abnormal_revocation(factory.post('/', body, content_type='application/json')).status_code, 400)
            run.assert_not_called()
        self.assertEqual(view.internal_abnormal_revocation(factory.get('/')).status_code, 405)


if __name__ == '__main__':
    unittest.main(verbosity=2)
