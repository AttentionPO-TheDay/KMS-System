"""Offline checks for recovery and publication correctness. No server writes."""
import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


HERE = Path(__file__).resolve().parent
worker = module('science_worker', HERE / 'worker.py')
runner = module('science_runner', HERE.parent / 'run_science_collection.py')


class CollectionChecks(unittest.TestCase):
    def test_resume_update_only_reconciles_even_after_idempotency_expiry(self):
        old = dict(key_id=17, version=3, status='0', digest='old')
        after = dict(old, version=4, digest='new')

        def query(statement, args=()):
            if 'version_history' in statement:
                return [dict(key_id=17, version=3)]
            if 'operation_record' in statement:
                return [dict(key_id=17, key_version=4, result_status='2', chain_status='2')]
            return [after]

        with patch.object(worker, 'sql', side_effect=query), patch.object(worker, 'post') as post:
            tables, summary = worker.update(dict(mapping_key='00' * 32, user='test', wait_seconds=1),
                                           'test-batch', 1, dict(baseline={'rows': [old]}))
        post.assert_not_called()
        self.assertTrue(summary['verified'])
        self.assertIsNone(summary['http_accepted'])
        self.assertEqual(tables['updates'][0]['audit_result_status'], '2')

    def test_resume_generation_does_not_repeat_uncertain_submission(self):
        row = dict(key_id=17, version=1, status='0', encryt_name='SSCL', cre_time='2026-10-24',
                   algorithm_version='1', key_material_state='ready', ua_digest='public', digest='material')
        with patch.object(worker, 'sql', return_value=[row]), patch.object(worker, 'post') as post:
            _, summary = worker.generation(dict(mapping_key='00' * 32, wait_seconds=1),
                                          'test-batch', 1, dict(baseline={'max_id': 16}))
        post.assert_not_called()
        self.assertTrue(summary['verified'])

    def test_version_change_requires_material_and_exactly_one_increment(self):
        old = dict(version=3, status='0', digest='old')
        self.assertTrue(worker.changed(old, dict(version=4, status='0', digest='new')))
        self.assertFalse(worker.changed(old, dict(version=5, status='0', digest='new')))
        self.assertFalse(worker.changed(old, dict(version=4, status='0', digest='old')))
        self.assertFalse(worker.changed(old, None))

    def test_incomplete_run_stays_incomplete_and_csv_neutralizes_formulas(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'batches').mkdir()
            batch = dict(tables={'samples': [dict(name='=1+1', passed=True)]})
            (root / 'batches' / '000000.json').write_text(json.dumps(batch), encoding='utf-8')
            state = dict(next_batch=1, pending={'batch_id': 'pending'},
                         config=dict(kind='revoke', run_id='test', count=2, batch_count=2))
            manifest = runner.finalize(root, state)
            self.assertFalse(manifest['complete'])
            with (root / 'datasets' / 'samples.csv').open(encoding='utf-8-sig', newline='') as f:
                self.assertEqual(next(csv.DictReader(f))['name'], "'=1+1")
            self.assertEqual(manifest['files'][0]['records'], 1)


if __name__ == '__main__':
    unittest.main()
