"""Regression guard: server FISCO deployment must enable the Django event writer."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FiscoChainConfigurationTests(unittest.TestCase):
    def test_all_event_writers_use_enabled_legacy_backend(self):
        services = json.loads((ROOT / 'docker-compose.fisco-enabled.yml').read_text(encoding='utf-8'))['services']
        for name in ('generate-java', 'updatedel-java', 'dvadmin3-django'):
            with self.subTest(service=name):
                env = services[name]['environment']
                self.assertEqual(env['KMS_CHAIN_BACKEND'], 'legacy')
                self.assertEqual(env['KMS_CHAIN_WRITES_ENABLED'], 'true')

    def test_node_evidence_and_lifecycle_use_same_contract(self):
        services = json.loads((ROOT / 'docker-compose.fisco-enabled.yml').read_text(encoding='utf-8'))['services']
        self.assertEqual(services['dvadmin3-django']['environment']['KMS_NODE_FISCO_CONTRACT_ADDRESS'],
                         services['updatedel-java']['environment']['FISCO_CONTRACT_ADDRESS'])


if __name__ == '__main__':
    unittest.main()
