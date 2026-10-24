"""SysPid query client checks; no external network requests."""
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location('query_sm2_by_syspid', ROOT / 'output/query_sm2_by_syspid.py')
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)


class QueryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.token = self.folder / 'partner-a.token'
        self.token.write_text('test-platform-token-with-at-least-32-characters')
        self.ca = self.folder / 'kms-server.crt'
        self.ca.write_text('test-certificate')
        self.output = self.folder / 'status.json'
        self.pid = 'a' * 182
        self.data = dict(sysPid=self.pid, algorithm='SM2', curve='sm2p256v1',
                         publicKey='04' + 'b' * 128, nodeStatus='ACTIVE',
                         publicKeyRegistrationStatus='REGISTERED', publicKeyStatus='ACTIVE',
                         didOnchain=dict(status='CONFIRMED', transactionValid=True, metadataMatches=True))
        self.body = dict(code=200, data=self.data)
        self.session = MagicMock()
        self.session.get.return_value.status_code = 200
        self.session.get.return_value.json.side_effect = lambda: self.body

    def invoke(self, *flags, defaults=False):
        args = ['query_sm2_by_syspid.py', '--sys-pid', self.pid, '--output', str(self.output)]
        if not defaults:
            args += ['--token-file', str(self.token), '--ca', str(self.ca)]
        with patch.object(sys, 'argv', args + list(flags)), \
                patch.object(client.requests, 'Session') as factory, \
                patch.object(client, '__file__', str(self.folder / 'query_sm2_by_syspid.py')), \
                patch.dict(os.environ, {}, clear=True), patch('sys.stdout', new_callable=io.StringIO) as stdout:
            factory.return_value.__enter__.return_value = self.session
            code = client.main()
            return code, stdout.getvalue()

    def test_query_is_get_only_with_sm2_tls_and_exact_identifier(self):
        code, stdout = self.invoke()
        self.assertEqual(code, 0)
        args, kwargs = self.session.get.call_args
        self.assertEqual(args, ('https://192.168.129.34:8443/external-api/v1/nodes/activate/',))
        self.assertEqual(kwargs['params'], dict(sysPid=self.pid, algorithm='SM2'))
        self.assertFalse(kwargs['allow_redirects'])
        self.assertEqual(self.session.verify, str(self.ca))
        self.assertFalse(self.session.trust_env)
        self.session.post.assert_not_called()
        self.assertIn('REGISTERED', stdout)
        self.assertEqual(json.loads(self.output.read_text())['data']['publicKey'], self.data['publicKey'])

    def test_default_credentials_are_resolved_beside_script(self):
        self.assertEqual(self.invoke(defaults=True)[0], 0)
        self.assertEqual(self.session.verify, str(self.ca))
        self.session.headers.update.assert_called_once_with({
            'Authorization': 'Bearer ' + self.token.read_text(), 'Accept': 'application/json'})

    def test_invalid_pid_missing_ca_and_credential_overwrite_fail_before_network(self):
        for flags in (['--sys-pid', 'truncated'], ['--ca', str(self.folder / 'missing.crt')],
                      ['--output', str(self.token)], ['--output', str(self.ca)]):
            with self.subTest(flags=flags), patch('sys.stderr', new_callable=io.StringIO), self.assertRaises(SystemExit):
                self.invoke(*flags)
        self.session.get.assert_not_called()

    def test_response_identity_algorithm_and_curve_must_match(self):
        for field, value in [('sysPid', 'b' * 182), ('algorithm', 'SSCL'), ('curve', 'wrong-curve')]:
            with self.subTest(field=field), patch.dict(self.data, {field: value}), self.assertRaises(RuntimeError):
                self.invoke()

    def test_pending_failed_and_revoked_states_do_not_report_ready(self):
        for value, expected in [('SUBMITTED', 2), ('FAILED', 1), ('DISABLED', 1)]:
            with self.subTest(value=value), patch.dict(self.data['didOnchain'], status=value):
                self.assertEqual(self.invoke()[0], expected)
        with patch.dict(self.data, publicKeyStatus='REVOKED'):
            self.assertEqual(self.invoke()[0], 2)

    def test_private_material_is_not_printed_or_saved(self):
        self.data.update(privateKey='secret-must-not-appear', domainPublicKey='private-domain-material')
        _, stdout = self.invoke()
        for value in ('secret-must-not-appear', 'privateKey', 'domainPublicKey'):
            self.assertNotIn(value, stdout)
            self.assertNotIn(value, self.output.read_text())

    def test_http_error_is_saved_and_reported(self):
        self.body = dict(code=404, msg='EXTERNAL_NODE_NOT_FOUND', data={})
        self.session.get.return_value.status_code = 404
        with self.assertRaisesRegex(RuntimeError, '404'):
            self.invoke()
        self.assertEqual(json.loads(self.output.read_text())['code'], 404)

    def test_legacy_sscl_must_be_selected_explicitly(self):
        self.data['algorithm'] = 'SSCL'
        self.assertEqual(self.invoke('--algorithm', 'SSCL')[0], 0)
        self.assertEqual(self.session.get.call_args.kwargs['params']['algorithm'], 'SSCL')


if __name__ == '__main__':
    unittest.main()
