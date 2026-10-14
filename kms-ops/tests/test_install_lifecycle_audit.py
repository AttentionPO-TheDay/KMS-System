import copy
import importlib.util
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml

spec = importlib.util.spec_from_file_location('install_audit', Path(__file__).resolve().parents[1] / 'install-lifecycle-audit.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ConfigureTests(unittest.TestCase):
    def config(self):
        return {'services': {'acceptance-backend': {'image': 'kms-acceptance-backend:local', 'volumes': ['existing:/app/other']},
                             'updatedel-java': {'environment': {'FISCO_PRIVATE_KEY': '${FISCO_PRIVATE_KEY}'}},
                             'nginx': {'ports': ['10.112.125.22:8443:443']}}, 'volumes': {'existing': {}}}

    def test_preserves_other_settings_and_is_idempotent(self):
        config = self.config()
        original = copy.deepcopy(config)
        result = module.configure(config)
        self.assertEqual(config, original)
        for name in ('updatedel-java', 'nginx'):
            self.assertEqual(result['services'][name], original['services'][name])
        self.assertEqual(result['services']['acceptance-backend']['volumes'], ['existing:/app/other', module.VOLUME + ':' + module.TARGET])
        self.assertEqual(module.configure(result), result)

    def test_conflicts_fail_without_mutation(self):
        for mount in ('other:' + module.TARGET, module.VOLUME + ':' + module.TARGET + ':ro',
                      {'type': 'volume', 'source': module.VOLUME, 'target': module.TARGET, 'read_only': True}):
            config = self.config()
            config['services']['acceptance-backend']['volumes'].append(mount)
            original = copy.deepcopy(config)
            with self.assertRaises(module.InstallError):
                module.configure(config)
            self.assertEqual(config, original)

    def test_volume_conflict_and_anonymous_unrelated_mount(self):
        config = self.config()
        config['services']['acceptance-backend']['volumes'].append('/unrelated')
        self.assertEqual(module.configure(config)['services']['acceptance-backend']['volumes'][1], '/unrelated')
        config['volumes'][module.VOLUME] = {'external': True}
        with self.assertRaises(module.InstallError):
            module.configure(config)

    def test_real_compose_validation_does_not_write(self):
        with tempfile.TemporaryDirectory(prefix='kms-audit-install-') as directory:
            root = Path(directory)
            config = self.config()
            config['name'] = 'kms-audit-install-test'
            config['services']['updatedel-java']['image'] = 'kms-updatedel-java:local'
            config['services']['nginx']['image'] = 'kms-gateway-nginx:local'
            config['services']['updatedel-java']['environment']['FISCO_PRIVATE_KEY'] = 'TEST_ONLY_NOT_A_KEY'
            base = root / 'docker-compose.yml'
            base.write_text(yaml.safe_dump(config), encoding='utf-8')
            overlay = root / 'docker-compose.fisco-enabled.yml'
            overlay.write_text(yaml.safe_dump({'services': {'updatedel-java': {'environment': {'CHAIN_TEST': 'preserved'}}}}), encoding='utf-8')
            original = base.read_bytes()
            output = io.StringIO()
            with patch.object(module, '__file__', str(root / 'install-lifecycle-audit.py')), patch('sys.argv', ['install-lifecycle-audit.py']), contextlib.redirect_stdout(output):
                module.main()
            self.assertEqual(base.read_bytes(), original)
            self.assertNotIn('TEST_ONLY_NOT_A_KEY', output.getvalue())
            self.assertIn('Read-only validation complete', output.getvalue())
            self.assertEqual(list(root.glob('.audit-compose-*')), [])

    def test_activation_only_recreates_three_services(self):
        with tempfile.TemporaryDirectory(prefix='kms-audit-install-') as directory:
            root = Path(directory)
            config = self.config()
            base = root / 'docker-compose.yml'
            base.write_text(yaml.safe_dump(config), encoding='utf-8')
            commands = []
            def fake_run(args, cwd):
                commands.append(args)
                if 'config' in args:
                    return json.dumps({'services': {'acceptance-backend': {'volumes': []}}, 'volumes': {}})
                return ''
            with patch.object(module, '__file__', str(root / 'install-lifecycle-audit.py')), patch('sys.argv', ['install-lifecycle-audit.py', '--activate']), patch.object(module, 'run', fake_run), contextlib.redirect_stdout(io.StringIO()):
                module.main()
            self.assertEqual(yaml.safe_load(base.read_text()), module.configure(config))
            self.assertEqual(commands[-1][-3:], ['updatedel-java', 'acceptance-backend', 'nginx'])
            self.assertIn('--no-deps', commands[-1])
            self.assertEqual(len(list(root.glob('lifecycle-compose-backup-*'))), 1)


if __name__ == '__main__':
    unittest.main()
