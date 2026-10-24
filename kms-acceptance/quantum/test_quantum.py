import json
import math
import os
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from circuit import hadamard, probabilities, simulate
from service import Handler, LOCK


class CircuitTests(unittest.TestCase):
    def test_hadamard_is_unitary_and_self_inverse(self):
        state = [0.5, -0.5, 0.5, 0.5]
        before = state[:]
        hadamard(state, 1)
        self.assertAlmostEqual(sum(v * v for v in state), 1)
        hadamard(state, 1)
        for a, b in zip(state, before):
            self.assertAlmostEqual(a, b)

    def test_grover_matches_analytic_probability_for_distinct_targets(self):
        for target in (0, 5, 31):
            probs, trace = probabilities([target], 5, 4)
            expected = math.sin(9 * math.asin(1 / math.sqrt(32))) ** 2
            self.assertAlmostEqual(probs[target], expected)
            self.assertAlmostEqual(sum(probs), 1)
            self.assertEqual(len(trace), 5)

    def test_missing_oracle_has_no_search_advantage(self):
        probs, _ = probabilities([7], 5, 4, enabled=False)
        for value in probs:
            self.assertAlmostEqual(value, 1 / 32)

    def test_public_lwe_instance_really_accepts_recovered_secret(self):
        result = simulate()
        candidate = int(result['recovered'], 2)
        public, q = result['publicInstance'], result['q']
        for row, b in zip(public['A'], public['b']):
            error = (sum(a * ((candidate >> j) & 1) for j, a in enumerate(row)) - b) % q
            self.assertLessEqual(min(error, q - error), public['noiseBound'])
        self.assertTrue(result['verified'])
        self.assertEqual(sum(result['counts'].values()), result['shots'])


class ServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, payload, token='test-internal-token'):
        req = urllib.request.Request(f'http://127.0.0.1:{self.server.server_port}/evaluate',
                                     json.dumps(payload).encode(), {'X-Internal-Token': token})
        try:
            with urllib.request.urlopen(req) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    @patch.dict(os.environ, {'INTERNAL_TOKEN': 'test-internal-token'})
    def test_authentication_fixed_inputs_and_concurrency(self):
        self.assertEqual(self.request({'caseId': 'quantum-lwe-usvp'}, token='wrong')[0], 403)
        for payload in ({'caseId': 'unknown'}, {'caseId': []}, {'caseId': 'quantum-lwe-usvp', 'command': 'anything'}, []):
            self.assertEqual(self.request(payload)[0], 400)
        with LOCK:
            self.assertEqual(self.request({'caseId': 'quantum-lwe-usvp'})[0], 429)

    @patch.dict(os.environ, {'INTERNAL_TOKEN': 'test-internal-token'})
    @patch('service.subprocess.check_output', side_effect=RuntimeError('private diagnostic'))
    def test_worker_failure_is_not_a_complete_evaluation(self, _):
        status, body = self.request({'caseId': 'quantum-lwe-usvp'})
        self.assertEqual(status, 503)
        self.assertNotIn('private', str(body))
        self.assertFalse(LOCK.locked())


if __name__ == '__main__':
    unittest.main()
