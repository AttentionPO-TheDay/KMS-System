import copy
import hashlib
import unittest
from types import SimpleNamespace

from . import lattice_preallocation_math as lattice
from .lattice_preallocation import canonical, _verify_prepared_package


class LatticePackageVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        context = lattice.delegate(lattice.trapgen(), 'B')
        cls.public = context['public']
        cls.preparation = SimpleNamespace(pk='test-preparation', kind='DELEGATED',
            node=SimpleNamespace(node_id='B'), public_digest=context['public_digest'],
            norm_bound=lattice.norm_bound(context))
        package = {'batch_id': 'batch-one', 'receiver_node_id': 'B', 'key_hash': 'original'}
        message = canonical(package)
        cls.package = {**package, 'latticeProof': dict(version=1, preparationId=cls.preparation.pk,
            publicDigest=cls.preparation.public_digest, packageDigest=hashlib.sha256(message).hexdigest(),
            vector=lattice.sample_pre(context, lattice.target_for(message)).tolist())}

    def test_valid_package_and_each_binding(self):
        verify = lambda package, receiver='B': _verify_prepared_package(package, receiver, self.preparation, self.public)
        self.assertTrue(verify(self.package))
        self.assertFalse(verify(self.package, 'C'))
        for field, value in [('preparationId', 'other'), ('publicDigest', 'changed'),
                             ('packageDigest', 'changed'), ('version', 2)]:
            with self.subTest(field=field):
                changed = copy.deepcopy(self.package)
                changed['latticeProof'][field] = value
                self.assertFalse(verify(changed))
        changed = copy.deepcopy(self.package)
        changed['key_hash'] = 'tampered'
        self.assertFalse(verify(changed))
        changed = copy.deepcopy(self.package)
        changed['latticeProof']['vector'][0] += 1
        self.assertFalse(verify(changed))
