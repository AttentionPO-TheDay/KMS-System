# -*- coding: utf-8 -*-
"""仅调用内部 Bridge；供应方国密 SDK 留在独立 JVM，不在 Django 中加载。"""
import json
import os
from urllib.parse import urlparse

import requests


class BindingError(RuntimeError):
    def __init__(self, code):
        # 不透传远端 msg/异常串：里面可能带文件路径、签名、证书或内部令牌。
        self.code = code
        super().__init__(code)


def _flag(name):
    return os.environ.get(name, 'false').strip().lower() in ('1', 'true', 'yes')


def local_configuration_error(chain_id=None, require_write=True):
    from .chain_backend import chain_writes_enabled
    if require_write and not chain_writes_enabled():
        return 'CHAIN_WRITES_PAUSED'
    if not _flag('FABRIC_DID_ENABLED'):
        return 'DISABLED'
    if not (chain_id or os.environ.get('FABRIC_DID_CHAIN_ID', '').strip()):
        return 'MISSING_CHAIN_ID'
    if not os.environ.get('INTERNAL_TOKEN', '').strip():
        return 'MISSING_INTERNAL_TOKEN'
    if require_write and not _flag('FABRIC_DID_WRITE_ENABLED'):
        return 'WRITE_DISABLED'
    return ''


class FabricDidClient:
    def __init__(self):
        self.base_url = os.environ.get(
            'FABRIC_DID_BRIDGE_URL', 'http://fabric-did-bridge:9094/internal/fabric-did',
        ).rstrip('/')
        parsed = urlparse(self.base_url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
            raise BindingError('INVALID_BRIDGE_URL')
        self.token = os.environ.get('INTERNAL_TOKEN', '')
        self.session = requests.Session()
        # 内部令牌不能跟着 HTTP 重定向发送给另一个地址。
        self.session.trust_env = False

    def close(self):
        self.session.close()

    def _request(self, method, path, payload=None):
        try:
            response = self.session.request(
                method, self.base_url + '/' + path,
                json=payload, headers={'X-Internal-Token': self.token},
                timeout=(3, 10), allow_redirects=False,
            )
        except requests.Timeout:
            raise BindingError('BRIDGE_TIMEOUT') from None
        except requests.RequestException:
            raise BindingError('BRIDGE_UNAVAILABLE') from None
        try:
            envelope = response.json()
        except (ValueError, TypeError):
            raise BindingError('INVALID_BRIDGE_RESPONSE') from None
        if response.status_code != 200 or not isinstance(envelope, dict) or envelope.get('code') != 200:
            data = envelope.get('data') if isinstance(envelope, dict) else None
            code = data.get('errorCode') if isinstance(data, dict) else None
            safe_codes = ('DISABLED', 'NOT_CONFIGURED', 'WRITE_DISABLED', 'CHAIN_POLICY_NOT_APPROVED',
                          'UNSUPPORTED', 'TRANSACTION_INVALID', 'METADATA_MISMATCH', 'DID_BINDING_CONFLICT')
            raise BindingError(code if code in safe_codes else 'BRIDGE_REJECTED')
        data = envelope.get('data')
        if not isinstance(data, dict):
            raise BindingError('INVALID_BRIDGE_RESPONSE')
        return data

    def status(self):
        return self._request('GET', 'status')

    def prepare(self, binding):
        return self._request('POST', 'bindings/prepare', json.loads(binding['metadata']))

    def submit(self, binding, prepared):
        return self._request('POST', 'bindings/submit', dict(prepared, binding=json.loads(binding['metadata'])))

    def verify(self, binding):
        return self._request('POST', 'bindings/verify', {
            'provider': binding.provider, 'chainId': binding.chain_id,
            'did': binding.did, 'txId': binding.tx_id,
            'metadataDigest': binding.metadata_digest, 'expectedMetadata': binding.metadata,
        })
