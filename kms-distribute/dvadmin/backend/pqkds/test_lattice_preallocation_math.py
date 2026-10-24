import copy
import math
import unittest

import numpy as np

from . import lattice_preallocation_math as lattice


class LatticeMathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = lattice.trapgen()
        cls.child = lattice.delegate(cls.root, 'test-node-A')

    @classmethod
    def tearDownClass(cls):
        lattice.shutdown_sampling_pool()

    def test_generated_trapdoor_spans_full_kernel(self):
        root = self.root
        self.assertFalse(np.any(root['public'] @ root['basis'] % lattice.Q))
        sign, logdet = np.linalg.slogdet(root['basis'].astype(float))
        self.assertNotEqual(sign, 0)
        self.assertAlmostEqual(logdet, lattice.N * math.log(lattice.Q), places=5)

    def test_extension_is_node_and_root_bound(self):
        child = self.child
        self.assertTrue(np.array_equal(child['public'][:, :self.root['public'].shape[1]], self.root['public']))
        self.assertFalse(np.any(child['public'] @ child['basis'] % lattice.Q))
        self.assertNotEqual(lattice.delegate(self.root, 'test-node-B')['public_digest'], child['public_digest'])
        self.assertNotEqual(lattice.delegate(lattice.trapgen(), 'test-node-A')['public_digest'], child['public_digest'])

    def test_parallel_samples_satisfy_independently_recomputed_relations(self):
        messages = [f'envelope-{i}'.encode() for i in range(16)]
        metrics = {}
        vectors = lattice.sample_parallel(self.child, messages, 4, metrics)
        self.assertGreaterEqual(metrics['usedWorkers'], 2)
        self.assertGreaterEqual(metrics['peakInFlight'], 2)
        self.assertEqual(len(metrics['spans']), 16)
        self.assertEqual(metrics['executionMode'], 'process')
        self.assertTrue(all(span['kind'] == 'process' for span in metrics['spans']))
        self.assertTrue(all(span['startMs'] <= span['endMs'] for span in metrics['spans']))
        self.assertEqual(len({lattice.digest(x) for x in vectors}), 16)
        for message, vector in zip(messages, vectors):
            self.assertTrue(np.array_equal(self.child['public'] @ vector % lattice.Q, lattice.target_for(message)))
            self.assertLessEqual(np.linalg.norm(vector), lattice.norm_bound(self.child))

    def test_pool_reuses_context_when_concurrency_changes(self):
        messages = [f'reuse-{i}'.encode() for i in range(8)]
        lattice.sample_parallel(self.child, messages, 1)
        metrics = {}
        vectors = lattice.sample_parallel(self.child, messages, 4, metrics)
        self.assertTrue(metrics['poolReused'])
        self.assertGreaterEqual(metrics['computeMs'], max(s['endMs'] for s in metrics['spans']))
        self.assertEqual(len(vectors), len(messages))
        for message, vector in zip(messages, vectors):
            self.assertTrue(lattice.verify(self.child['public'], lattice.target_for(message), vector, lattice.norm_bound(self.child)))

    def test_context_switch_never_reuses_another_nodes_private_basis(self):
        lattice.sample_parallel(self.child, [b'old-context'], 1)
        other = lattice.delegate(self.root, 'test-switched-node')
        metrics = {}
        vector = lattice.sample_parallel(other, [b'new-context'], 4, metrics)[0]
        self.assertFalse(metrics['poolReused'])
        self.assertTrue(lattice.verify(other['public'], lattice.target_for(b'new-context'), vector, lattice.norm_bound(other)))
        self.assertFalse(lattice.verify(self.child['public'], lattice.target_for(b'new-context'), vector, lattice.norm_bound(self.child)))

    def test_failed_batch_does_not_leave_work_running_in_next_batch(self):
        with self.assertRaises(TypeError):
            lattice.sample_parallel(self.child, [None, b'valid-peer-task'], 2)
        metrics = {}
        vector = lattice.sample_parallel(self.child, [b'after-failure'], 1, metrics)[0]
        self.assertEqual(metrics['peakInFlight'], 1)
        self.assertTrue(lattice.verify(self.child['public'], lattice.target_for(b'after-failure'), vector, lattice.norm_bound(self.child)))

    def test_proofs_are_not_reusable_for_other_messages_or_nodes(self):
        target = lattice.target_for(b'first')
        vector = lattice.sample_pre(self.child, target)
        bound = lattice.norm_bound(self.child)
        self.assertFalse(lattice.verify(self.child['public'], lattice.target_for(b'changed'), vector, bound))
        self.assertFalse(lattice.verify(lattice.delegate(self.root, 'other')['public'], target, vector, bound))
        changed = vector.copy(); changed[0] += lattice.Q
        self.assertFalse(lattice.verify(self.child['public'], target, changed, 1))

    def test_serial_and_parallel_produce_valid_fresh_samples(self):
        message = b'same-target'
        a = lattice.sample_parallel(self.child, [message], 1)[0]
        b = lattice.sample_parallel(self.child, [message], 4)[0]
        self.assertFalse(np.array_equal(a, b))
        for vector in (a, b):
            self.assertTrue(lattice.verify(self.child['public'], lattice.target_for(message), vector, lattice.norm_bound(self.child)))

    def test_random_matrices_and_invalid_inputs_are_rejected(self):
        invalid = self.root['basis'].copy(); invalid[0, 0] += 1
        with self.assertRaises(ValueError): lattice.prepare(self.root['public'], invalid)
        with self.assertRaises(ValueError): lattice.sample_parallel(self.child, [b'x'], 0)
        with self.assertRaises(ValueError): lattice.sample_parallel(self.child, [b'x'], True)
        self.assertFalse(lattice.verify(self.child['public'], lattice.target_for(b'x'), np.zeros(580, dtype=float), 1))


if __name__ == '__main__':
    unittest.main()
