"""Run only in an isolated container: native algorithms, no Django settings or DB."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pqkds.acceptance_pq import CASES, run_checks
from pqkds.crypto_utils import KyberCrypto, FalconCrypto


class AcceptancePQTests(unittest.TestCase):
    def test_all_deployed_native_algorithms_and_independent_vectors(self):
        results = [run_checks(case_id) for case_id in CASES]
        for result in results:
            self.assertTrue(result['passed'], json.dumps(result, ensure_ascii=False))
            self.assertTrue(all(c['status'] == 'passed' for c in result['checks']))
            self.assertTrue(all(c['recordedAt'] and c['durationMs'] >= 0 for c in result['checks']))
        self.assertEqual(sum(len(r['checks']) for r in results), 26)
        # Evidence contains outcomes only, never the ephemeral cryptographic buffers.
        for result in results:
            self.assertEqual(set(result), {'version', 'caseId', 'category', 'source', 'scope', 'checks', 'passed'})
            for row in result['checks']:
                self.assertEqual(set(row), {'id', 'name', 'expected', 'actual', 'passed', 'status', 'durationMs', 'recordedAt'})

    def test_accepting_corrupt_ciphertext_cannot_pass(self):
        original = KyberCrypto.encrypt
        def remember(crypto, pk):
            ct, shared = original(crypto, pk)
            crypto.acceptance_test_shared = shared
            return ct, shared
        def broken(crypto, ct, sk):
            return crypto.acceptance_test_shared
        with patch.object(KyberCrypto, 'encrypt', remember), patch.object(KyberCrypto, 'decrypt', broken):
            result = run_checks('pq-parameter-downgrade')
        self.assertFalse(result['passed'])
        self.assertTrue(all(not c['passed'] for c in result['checks'] if c['id'].endswith('-tamper')))

    def test_accepting_modified_signatures_cannot_pass(self):
        with patch.object(FalconCrypto, 'verify', return_value=b'KMS acceptance ephemeral message v1'):
            result = run_checks('pq-issuance-source-forgery')
        self.assertFalse(result['passed'])
        self.assertTrue(all(not c['passed'] for c in result['checks'] if c['id'] in ('falcon-signature-tamper', 'falcon-wrong-key')))

    def test_native_exception_is_error_not_successful_rejection(self):
        with patch.object(FalconCrypto, 'verify', side_effect=RuntimeError('private-buffer-must-not-leak')):
            result = run_checks('pq-sign-encrypt-confusion')
        self.assertFalse(result['passed'])
        self.assertTrue(all(c['status'] == 'error' for c in result['checks']))
        self.assertNotIn('private-buffer-must-not-leak', json.dumps(result))

    def test_refuses_arbitrary_case(self):
        with self.assertRaises(ValueError):
            run_checks('custom-command')


if __name__ == '__main__':
    unittest.main(verbosity=2)
