"""Client selector and response identity checks; no network requests."""
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location('external_sscl_client', ROOT / 'output/external_sscl_client.py')
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.token = self.folder / 'partner-a.token'
        self.token.write_text('test-platform-token-with-at-least-32-characters', encoding='utf-8')
        self.output = self.folder / 'result.json'
        self.pid = 'a' * 182
        self.data = {'nodeName': 'demo-ts', 'sysPid': self.pid, 'nodeStatus': 'ACTIVE', 'algorithm': 'SM2', 'curve': 'sm2p256v1',
                     'publicKeyRegistrationStatus': 'REGISTERED', 'publicKeyStatus': 'ACTIVE',
                     'didOnchain': {'status': 'CONFIRMED', 'transactionValid': True, 'metadataMatches': True}}
        self.session = MagicMock()
        self.response = self.session.request.return_value
        self.response.status_code = 200
        self.response.json.side_effect = lambda: {'code': 200, 'data': self.data}

    def add_private_material(self):
        self.data.update(privateKey='0' * 63 + '1', publicKey='04' + 'b' * 128)
        self.private_path = self.folder / 'private.json'

    def invoke(self, *arguments):
        argv = ['external_sscl_client.py', '--token-file', str(self.token), '--output', str(self.output), *arguments]
        with patch.object(sys, 'argv', argv), patch.object(client.requests, 'Session') as session_factory, patch('sys.stdout', new_callable=io.StringIO):
            session_factory.return_value.__enter__.return_value = self.session
            return client.main()

    def test_sys_pid_automatically_uses_get_without_node_name(self):
        self.assertEqual(self.invoke('--sys-pid', self.pid), 0)
        args, kwargs = self.session.request.call_args
        self.assertEqual(args[0], 'GET')
        self.assertEqual(kwargs['params'], {'sysPid': self.pid})
        self.assertNotIn('json', kwargs)
        self.assertEqual(json.loads(self.output.read_text())['data']['sysPid'], self.pid)

    def test_sys_pid_response_must_match_requested_identifier(self):
        self.data['sysPid'] = 'b' * 182
        with self.assertRaisesRegex(RuntimeError, 'sysPid'):
            self.invoke('--sys-pid', self.pid)

    def test_existing_node_name_activation_and_query_keep_their_methods(self):
        for flags, method in (([], 'POST'), (['--query'], 'GET')):
            with self.subTest(method=method):
                self.assertEqual(self.invoke('--node-name', 'demo-ts', *flags), 0)
                args, kwargs = self.session.request.call_args
                self.assertEqual(args[0], method)
                self.assertEqual(kwargs['params' if method == 'GET' else 'json'], {'nodeName': 'demo-ts', 'algorithm': 'SM2'})

    def test_invalid_or_ambiguous_selector_never_sends_request(self):
        for flags in (['--sys-pid', 'truncated'], ['--node-name', 'demo-ts', '--sys-pid', self.pid]):
            with self.subTest(flags=flags), patch('sys.stderr', new_callable=io.StringIO):
                with self.assertRaises(SystemExit):
                    self.invoke(*flags)
        self.session.request.assert_not_called()

    def test_private_export_posts_explicit_flag_and_saves_separate_file(self):
        self.add_private_material()
        expected = self.data['privateKey']
        with patch('builtins.print') as output:
            self.assertEqual(self.invoke('--sys-pid', self.pid, '--private-key-output', str(self.private_path)), 0)
        args, kwargs = self.session.request.call_args
        self.assertEqual(args[0], 'POST')
        self.assertEqual(kwargs['json'], {'sysPid': self.pid, 'includePrivateKey': True})
        self.assertNotIn(expected, str(output.call_args_list))
        self.assertNotIn('privateKey', self.output.read_text())
        exported = json.loads(self.private_path.read_text())
        self.assertEqual(exported['privateKey'], expected)
        self.assertEqual(exported['sysPid'], self.pid)
        if os.name == 'posix':
            self.assertEqual(self.private_path.stat().st_mode & 0o777, 0o600)

    def test_activation_can_request_private_key_in_same_call(self):
        self.add_private_material()
        self.assertEqual(self.invoke('--node-name', 'demo-ts', '--private-key-output', str(self.private_path)), 0)
        self.assertEqual(self.session.request.call_args.kwargs['json'], {'nodeName': 'demo-ts', 'algorithm': 'SM2', 'includePrivateKey': True})

    def test_explicit_sm2_rejects_old_sscl_response_without_saving_private_key(self):
        self.add_private_material()
        self.data['algorithm'] = 'SSCL'
        with self.assertRaisesRegex(RuntimeError, '算法'):
            self.invoke('--node-name', 'demo-ts', '--private-key-output', str(self.private_path))
        self.assertEqual(self.private_path.read_text(), '')

    def test_old_sscl_sys_pid_keeps_its_real_algorithm_and_domain(self):
        self.add_private_material()
        self.data.update(algorithm='SSCL', domainPublicKey='04' + 'a' * 128)
        self.assertEqual(self.invoke('--sys-pid', self.pid, '--private-key-output', str(self.private_path)), 0)
        self.assertEqual(json.loads(self.private_path.read_text())['algorithm'], 'SSCL')
        self.assertEqual(json.loads(self.private_path.read_text())['domainPublicKey'], '04' + 'a' * 128)

    def test_algorithm_selection_is_sent_on_sys_pid_query(self):
        self.assertEqual(self.invoke('--sys-pid', self.pid, '--algorithm', 'SM2'), 0)
        self.assertEqual(self.session.request.call_args.kwargs['params'], {'sysPid': self.pid, 'algorithm': 'SM2'})

    def test_private_export_rejects_aliases_and_query_flag_without_network(self):
        self.add_private_material()
        for flags in (['--query', '--private-key-output', str(self.private_path)],
                      ['--private-key-output', str(self.token)],
                      ['--private-key-output', str(self.output)]):
            with patch('sys.stderr', new_callable=io.StringIO), self.assertRaises(SystemExit):
                self.invoke('--sys-pid', self.pid, *flags)
        self.session.request.assert_not_called()

    def test_invalid_response_does_not_overwrite_existing_private_file(self):
        self.add_private_material()
        self.private_path.write_text('original-private-material')
        self.data['sysPid'] = 'b' * 182
        with self.assertRaises(RuntimeError):
            self.invoke('--sys-pid', self.pid, '--private-key-output', str(self.private_path))
        self.assertEqual(self.private_path.read_text(), 'original-private-material')
        self.assertNotIn('privateKey', self.output.read_text())

    def test_old_server_missing_private_material_is_reported(self):
        self.private_path = self.folder / 'private.json'
        with self.assertRaisesRegex(RuntimeError, '私钥'):
            self.invoke('--sys-pid', self.pid, '--private-key-output', str(self.private_path))
        self.assertEqual(self.private_path.read_text(), '')

    @unittest.skipUnless(os.name == 'posix', 'Requires POSIX file modes and symlinks')
    def test_private_file_permissions_and_link_rejection(self):
        self.add_private_material()
        self.private_path.write_text('old')
        self.private_path.chmod(0o666)
        with client.private_file(self.private_path): pass
        self.assertEqual(self.private_path.read_text(), 'old')
        self.assertEqual(self.private_path.stat().st_mode & 0o777, 0o600)
        link = self.folder / 'linked-private.json'
        link.symlink_to(self.private_path)
        with self.assertRaises(RuntimeError):
            client.private_file(link)
        link.unlink()
        os.link(self.private_path, link)
        with self.assertRaises(RuntimeError):
            client.private_file(link)
        self.assertEqual(self.private_path.read_text(), 'old')


if __name__ == '__main__': unittest.main()
