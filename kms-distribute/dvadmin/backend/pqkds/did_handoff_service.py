# -*- coding: utf-8 -*-
"""生成并保存 DID SDK 参数交接包；本模块没有任何 submit 调用。"""
import hashlib
import json
import os
import re

from django.db import transaction
from django.utils import timezone

from .fabric_did_client import BindingError, FabricDidClient, local_configuration_error
from .models import DidSdkHandoff, Node, NodeLongTermKey


INTERFACE_PATH = '/internal/fabric-did/bindings/handoff'
_HEX_64 = re.compile(r'^[0-9a-f]{64}$')
_HEX_48 = re.compile(r'^[0-9a-f]{48}$')


class HandoffError(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(code)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _build_payload(key, sequence, recorded_at):
    namespace = os.environ.get('FABRIC_DID_NAMESPACE', 'kms-key-binding-v1')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', namespace or ''):
        raise HandoffError('INVALID_NAMESPACE', 'DID namespace 配置无效')
    if key.status != 'ACTIVE':
        raise HandoffError('KEY_NOT_ACTIVE', '只有当前 ACTIVE 公钥可以生成 DID 参数交接包')
    expected_hash = _digest(key.public_key)
    if not key.public_key_hash or key.public_key_hash.lower() != expected_hash:
        raise HandoffError('PUBLIC_KEY_HASH_MISMATCH', '登记公钥与公钥摘要不一致，请先修复密钥记录')
    key_ref = f'node/{key.node.node_id}/{key.algorithm}/{key.key_id}/{key.key_version}'
    event_id = _digest(_canonical({
        'namespace': namespace, 'keyRef': key_ref, 'eventType': 'REGISTERED',
        'keyStatus': key.status, 'revision': sequence,
    }))
    return {
        'schemaVersion': 1,
        'namespace': namespace,
        'eventId': event_id,
        'nodeId': key.node.node_id,
        'algorithm': key.algorithm,
        'keyId': key.key_id,
        'keyVersion': key.key_version,
        'publicKey': key.public_key,
        'publicKeyHash': key.public_key_hash.lower(),
        'status': key.status,
        'revision': sequence,
        'eventType': 'REGISTERED',
        'recordedAt': recorded_at.isoformat(),
    }


def _prepare(record, payload, client_factory):
    chain_id = os.environ.get('FABRIC_DID_CHAIN_ID', '').strip()
    config_error = local_configuration_error(chain_id, require_write=False)
    if config_error:
        record.prepare_status = 'NOT_CONFIGURED'
        record.last_error = config_error
        record.save(update_fields=['prepare_status', 'last_error', 'updated_at'])
        return record
    client = None
    try:
        client = client_factory()
        prepared = client.prepare_handoff(payload)
        metadata = _canonical(payload)
        if (prepared.get('provider') != 'FABRIC_DID'
                or prepared.get('chainId') != chain_id
                or prepared.get('metadata') != metadata
                or prepared.get('metadataDigest') != _digest(metadata)
                or prepared.get('status') != 'PREPARED'
                or prepared.get('submitted') is not False
                or not _HEX_64.fullmatch(str(prepared.get('txId') or ''))
                or not _HEX_48.fullmatch(str(prepared.get('nonce') or ''))):
            raise BindingError('INVALID_BRIDGE_RESPONSE')
        record.prepare_status = 'PREPARED'
        record.prepared_payload = _canonical(prepared)
        record.did = str(prepared.get('did') or '')
        record.tx_id = str(prepared['txId'])
        record.nonce = str(prepared['nonce'])
        record.last_error = ''
    except BindingError as exc:
        record.prepare_status = ('BRIDGE_UNAVAILABLE' if exc.code in (
            'BRIDGE_TIMEOUT', 'BRIDGE_UNAVAILABLE') else 'FAILED')
        record.last_error = exc.code
    finally:
        if client is not None:
            client.close()
    record.save(update_fields=[
        'prepare_status', 'prepared_payload', 'did', 'tx_id', 'nonce',
        'last_error', 'updated_at',
    ])
    return record


def create_handoff(node, *, algorithm, key_id, key_version, requested_by='',
                   client_factory=FabricDidClient):
    if not isinstance(algorithm, str) or algorithm != algorithm.strip().upper():
        raise HandoffError('INVALID_PARAMETER', 'algorithm 必须使用列表中的大写原值')
    if not isinstance(key_id, str) or not key_id or key_id != key_id.strip():
        raise HandoffError('INVALID_PARAMETER', 'keyId 必须使用列表中的原值')
    if isinstance(key_version, bool) or not isinstance(key_version, int) or key_version < 1:
        raise HandoffError('INVALID_PARAMETER', 'keyVersion 必须是正整数')
    with transaction.atomic():
        Node.objects.select_for_update().get(pk=node.pk)
        key = NodeLongTermKey.objects.select_for_update().filter(
            node=node, algorithm=algorithm, key_id=key_id, key_version=key_version,
        ).first()
        if key is None:
            raise HandoffError('KEY_NOT_FOUND', '没有找到指定的节点密钥版本')
        latest = DidSdkHandoff.objects.select_for_update().filter(
            node=node).order_by('-sequence').first()
        sequence = (latest.sequence if latest else 0) + 1
        now = timezone.now()
        payload = _build_payload(key, sequence, now)
        encoded = _canonical(payload)
        record = DidSdkHandoff.objects.create(
            node=node, long_term_key=key, node_id_snapshot=node.node_id,
            algorithm=key.algorithm, key_id=key.key_id, key_version=key.key_version,
            key_status=key.status, sequence=sequence, event_id=payload['eventId'],
            request_payload=encoded, request_digest=_digest(encoded),
            requested_by=str(requested_by or ''), created_at=now,
        )
    return _prepare(record, payload, client_factory)


def record_payload(record, include_package=False):
    data = {
        'recordId': str(record.record_id), 'nodeId': record.node_id_snapshot,
        'algorithm': record.algorithm, 'keyId': record.key_id,
        'keyVersion': record.key_version, 'keyStatus': record.key_status,
        'sequence': record.sequence, 'eventId': record.event_id,
        'requestDigest': record.request_digest, 'prepareStatus': record.prepare_status,
        'did': record.did, 'txId': record.tx_id, 'lastError': record.last_error,
        'submitted': False, 'createdAt': record.created_at.isoformat(),
    }
    if include_package:
        data['handoffPackage'] = {
            'recordId': str(record.record_id),
            'submitted': False,
            'sdkContract': {
                'prepareMethod': 'DidHandler.genTxId',
                'submitMethod': 'DidHandler.createDidDocument',
                'submitInvoked': False,
            },
            'interface': {'method': 'POST', 'path': record.interface_path},
            'request': json.loads(record.request_payload),
            'prepared': json.loads(record.prepared_payload) if record.prepared_payload else None,
        }
    return data
