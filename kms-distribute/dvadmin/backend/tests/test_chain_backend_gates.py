"""旧链误写反证：执行源码中的入口方法，但网络/数据库依赖均替换为 mock。

不调用 django.setup，不读真实应用数据库或身份配置；建议在 --network none 的
一次性测试容器中运行。它验证调用顺序，不冒充真实 Fabric/旧链联调。
"""
import ast
import os
import sys
import typing
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pqkds.chain_backend import NoLegacyWrite, selected_backend


def method(relative, class_name, name, **extra):
    tree = ast.parse((ROOT / relative).read_text(encoding='utf-8-sig'))
    owner = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
    target = next(node for node in owner.body if isinstance(node, ast.FunctionDef) and node.name == name)
    target.decorator_list = []
    namespace = {'__name__': 'pqkds.gate_test', '__package__': 'pqkds', 'Dict': typing.Dict, 'Any': typing.Any,
                 'Optional': typing.Optional, 'logger': Mock(), **extra}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[target], type_ignores=[])), relative, 'exec'), namespace)
    return namespace[name]


class BackendGates(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {'KMS_CHAIN_BACKEND': 'fabric-did', 'KMS_CHAIN_WRITES_ENABLED': 'true'})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_bad_selector_never_falls_back(self):
        os.environ['KMS_CHAIN_BACKEND'] = 'fabric-typo'
        from django.core.exceptions import ImproperlyConfigured
        with self.assertRaises(ImproperlyConfigured):
            selected_backend()

    def test_web3_constructor_rejects_before_initialize(self):
        initialize = Mock(side_effect=AssertionError('unexpected legacy initialization'))
        initializer = method('pqkds/blockchain_service.py', 'BlockchainService', '__init__')
        with self.assertRaises(NoLegacyWrite):
            initializer(SimpleNamespace(_initialize=initialize))
        initialize.assert_not_called()

    def test_upload_constructor_rejects_before_web3(self):
        legacy = Mock(side_effect=AssertionError('unexpected legacy client'))
        initializer = method('pqkds/node_blockchain_upload_service.py', 'NodeBlockchainUploadService', '__init__', BlockchainService=legacy)
        with self.assertRaises(NoLegacyWrite):
            initializer(SimpleNamespace())
        legacy.assert_not_called()

    def test_independent_kds_constructor_rejects_before_http_provider(self):
        web3 = Mock(side_effect=AssertionError('unexpected Web3'))
        initializer = method('pqkds/blockchain_integration.py', 'BlockchainKDS', '__init__', Web3=web3)
        with self.assertRaises(NoLegacyWrite):
            initializer(SimpleNamespace())
        web3.assert_not_called()
        web3.HTTPProvider.assert_not_called()

    def test_cached_kds_write_entries_also_reject(self):
        for name, args in [('register_user_with_blockchain', ('offline-user',)),
                           ('update_user_key', ('offline-user',)),
                           ('_store_public_key_on_chain', ('offline-user', {}))]:
            entry = method('pqkds/blockchain_integration.py', 'BlockchainKDS', name)
            with self.assertRaises(NoLegacyWrite):
                entry(SimpleNamespace(), *args)

    def test_node_service_uses_no_legacy_constructor(self):
        node = SimpleNamespace(node_id='offline-node')
        model = SimpleNamespace(objects=SimpleNamespace(get=Mock(return_value=node)), DoesNotExist=RuntimeError)
        legacy = Mock(side_effect=AssertionError('unexpected legacy client'))
        upload = Mock(side_effect=AssertionError('unexpected legacy upload'))
        initializer = method('pqkds/node_service.py', 'NodeService', '__init__', Node=model,
                             OptimizedKeygenService=Mock(return_value=object()),
                             BlockchainService=legacy, NodeBlockchainUploadService=upload)
        service = SimpleNamespace()
        initializer(service, 'offline-node')
        legacy.assert_not_called()
        upload.assert_not_called()
        self.assertIsNone(service.blockchain_service)
        result = service.upload_service.upload_node_registration(node)
        self.assertFalse(result['success'])
        self.assertEqual(result['provider'], 'FABRIC_DID')

    def test_pause_default_and_false_skip_all_legacy_node_constructors(self):
        for selected in ('legacy', 'fabric-did'):
            for flag in (None, 'false', 'invalid'):
                os.environ['KMS_CHAIN_BACKEND'] = selected
                if flag is None:
                    os.environ.pop('KMS_CHAIN_WRITES_ENABLED', None)
                else:
                    os.environ['KMS_CHAIN_WRITES_ENABLED'] = flag
                model = SimpleNamespace(objects=SimpleNamespace(get=Mock(return_value=object())), DoesNotExist=RuntimeError)
                legacy, upload = Mock(), Mock()
                initializer = method('pqkds/node_service.py', 'NodeService', '__init__', Node=model,
                    OptimizedKeygenService=Mock(), BlockchainService=legacy, NodeBlockchainUploadService=upload)
                node_service = SimpleNamespace()
                initializer(node_service, 'offline-node')
                legacy.assert_not_called()
                upload.assert_not_called()
                self.assertEqual(node_service.upload_service.upload_node_registration(None)['code'], 'CHAIN_WRITES_PAUSED')

    def test_node_service_default_legacy_still_uses_existing_paths(self):
        os.environ['KMS_CHAIN_BACKEND'] = 'legacy'
        model = SimpleNamespace(objects=SimpleNamespace(get=Mock(return_value=object())), DoesNotExist=RuntimeError)
        legacy, upload = Mock(), Mock()
        initializer = method('pqkds/node_service.py', 'NodeService', '__init__', Node=model,
                             OptimizedKeygenService=Mock(), BlockchainService=legacy,
                             NodeBlockchainUploadService=upload)
        initializer(SimpleNamespace(), 'offline-node')
        legacy.assert_called_once()
        upload.assert_called_once()

    def test_digest_event_does_not_dispatch_to_fisco(self):
        tree = ast.parse((ROOT / 'pqkds/kms_service_client.py').read_text(encoding='utf-8-sig'))
        entry = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'record_chain_event')
        request = Mock(side_effect=AssertionError('unexpected HTTP'))
        headers = Mock(side_effect=AssertionError('unexpected credentials'))
        namespace = {'__name__': 'pqkds.gate_test', '__package__': 'pqkds', 'Optional': typing.Optional,
                     'logger': Mock(), '_internal_headers': headers, 'requests': request}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[entry], type_ignores=[])), 'kms_service_client.py', 'exec'), namespace)
        self.assertIsNone(namespace['record_chain_event']('KEY_UPDATED', 42))
        request.post.assert_not_called()
        headers.assert_not_called()

    def test_old_setup_rejects_before_django_setup_or_config_deletion(self):
        source = (ROOT / '_blockchain_setup.py').read_text(encoding='utf-8-sig')
        # 真实 setup 脚本包含配置清理，测试必须在 bootstrap 行硬停；绝不执行其下半段。
        tree = ast.parse(source)
        prefix = []
        for node in tree.body:
            prefix.append(node)
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute) and node.value.func.attr == 'setup':
                break
        fake_django = SimpleNamespace(setup=Mock(side_effect=AssertionError('guard must run before setup')))
        with patch.dict(sys.modules, {'django': fake_django}):
            with self.assertRaises(NoLegacyWrite):
                exec(compile(ast.fix_missing_locations(ast.Module(body=prefix, type_ignores=[])), '_blockchain_setup.py', 'exec'), {})
        fake_django.setup.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
