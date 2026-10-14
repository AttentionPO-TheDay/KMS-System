import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('enable_node_fisco', Path(__file__).resolve().parents[1] / 'enable-node-fisco.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ConfigureTests(unittest.TestCase):
    def config(self):
        return {'services': {'updatedel-java': {'environment': {
            'FISCO_CONTRACT_ADDRESS': '0x' + '1' * 40, 'FISCO_PRIVATE_KEY': '${FISCO_PRIVATE_KEY}',
            'KMS_CHAIN_WRITES_ENABLED': 'true', 'KMS_LIFECYCLE_CHAIN_SYNC_ENABLED': 'true'}},
            'generate-java': {'environment': {'UNCHANGED': 'true'}},
            'nginx': {'ports': ['10.112.125.22:8443:443']}}}

    def test_preserves_chain_credentials_tls_and_existing_services(self):
        value = self.config(); original = copy.deepcopy(value)
        result = module.configure(value)
        for name in ('updatedel-java', 'generate-java', 'nginx'):
            self.assertEqual(result['services'][name], original['services'][name])
        env = result['services']['dvadmin3-django']['environment']
        self.assertEqual(env['KMS_NODE_FISCO_ENABLED'], 'true')
        self.assertEqual(env['KMS_CHAIN_WRITES_ENABLED'], 'false')
        self.assertNotIn('FISCO_PRIVATE_KEY', env)
        self.assertEqual(module.configure(result), result)

    def test_invalid_or_paused_java_configuration_cannot_activate(self):
        for field, invalid in [('FISCO_CONTRACT_ADDRESS', ''), ('KMS_CHAIN_WRITES_ENABLED', 'false'), ('KMS_LIFECYCLE_CHAIN_SYNC_ENABLED', 'false')]:
            value=self.config(); value['services']['updatedel-java']['environment'][field]=invalid
            with self.assertRaises(ValueError):
                module.configure(value)
            self.assertNotIn('dvadmin3-django', value['services'])


if __name__ == '__main__':
    unittest.main()
