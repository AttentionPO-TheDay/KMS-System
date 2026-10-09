# -*- coding: utf-8 -*-
"""公开量 Outbox：业务事务只记账，显式 worker 才联系 Bridge。

没有真实链资料时保留 NOT_CONFIGURED，不借旧链“补成功”。提交前先保存 nonce/txId，
提交响应丢失后只查原交易；不重新提交或生成第二个 DID。同节点、链及 namespace 的
事件严格按 sequence 处理；FAILED 也挡住后续任务，必须核对后显式处置。这里保留顺序，
不声称 Bridge 已实现节点 DID 当前投影（该能力仍为 UNSUPPORTED）。
"""
import hashlib
import json
import os
import uuid
from datetime import timedelta

from django.db import connection, transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from .chain_backend import is_fabric_did
from .fabric_did_client import BindingError, FabricDidClient, local_configuration_error
from .models import ChainKeyBinding, Node


PROVIDER = 'FABRIC_DID'
LEASE_SECONDS = 120  # 三次 HTTP 的有界超时小于租约，更新还要校验 token 防止旧 worker 回写。


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest_metadata(metadata):
    return hashlib.sha256(metadata.encode('utf-8')).hexdigest()


def configured_namespace():
    return os.environ.get('FABRIC_DID_NAMESPACE', 'kms-key-binding-v1')


def lock_registry_node(node):
    if is_fabric_did():
        # 锁已有 Node 行而不是“不存在的 outbox 行”；这是所有登记事件的串行点。
        Node.objects.select_for_update().get(pk=node.pk)


def enqueue_binding(key, event_type):
    if not is_fabric_did():
        return None
    if not connection.in_atomic_block:
        raise RuntimeError('Binding outbox must be created inside the registry transaction')
    if event_type not in ('REGISTERED', 'ROTATED', 'REVOKED'):
        raise ValueError('Invalid binding event type')
    lock_registry_node(key.node)
    chain_id = os.environ.get('FABRIC_DID_CHAIN_ID', '').strip()
    if len(chain_id) > 128:
        raise BindingError('INVALID_CHAIN_ID')
    namespace = configured_namespace()
    if not namespace or len(namespace) > 80:
        raise BindingError('INVALID_NAMESPACE')
    key_ref = f'node/{key.node.node_id}/{key.algorithm}/{key.key_id}/{key.key_version}'
    existing = ChainKeyBinding.objects.select_for_update().filter(
        provider=PROVIDER, chain_id=chain_id, namespace=namespace, key_ref=key_ref,
        event_type=event_type, key_status=key.status,
    ).first()
    if existing is not None:
        # 源节点可删除重建，但原 keyRef 的链证据不能被另一把公钥借用。
        prior = json.loads(existing.metadata)
        if (existing.long_term_key_id != key.pk or prior.get('publicKey') != key.public_key
                or prior.get('publicKeyHash') != key.public_key_hash):
            raise BindingError('BINDING_IDEMPOTENCY_CONFLICT')
        return existing
    # 锁定读要用当前读，不能取 REPEATABLE READ 事务先前建立的旧快照。
    latest = (ChainKeyBinding.objects.select_for_update().filter(node_id=key.node_id)
              .order_by('-sequence').first())
    sequence = (latest.sequence if latest else 0) + 1
    now = timezone.now()
    event_id = digest_metadata(canonical_json({
        'provider': PROVIDER, 'chainId': chain_id, 'namespace': namespace, 'keyRef': key_ref,
        'eventType': event_type, 'keyStatus': key.status, 'revision': sequence,
    }))
    # 白名单构造，绝不序列化 Node/密钥行的 __dict__（里面有设备凭据与私钥列）。
    metadata = canonical_json({
        'schemaVersion': 1,
        'namespace': namespace,
        'nodeId': key.node.node_id,
        'algorithm': key.algorithm,
        'keyId': key.key_id,
        'keyVersion': key.key_version,
        'publicKey': key.public_key,
        'publicKeyHash': key.public_key_hash,
        'status': key.status,
        'eventType': event_type,
        'revision': sequence,
        'eventId': event_id,
        'recordedAt': now.isoformat(),
    })
    error = local_configuration_error(chain_id)
    return ChainKeyBinding.objects.create(
        provider=PROVIDER, chain_id=chain_id, namespace=namespace, node=key.node, long_term_key=key,
        node_id_snapshot=key.node.node_id, algorithm=key.algorithm,
        key_id=key.key_id, key_version=key.key_version, key_ref=key_ref,
        event_type=event_type, key_status=key.status, sequence=sequence, event_id=event_id,
        metadata=metadata, metadata_digest=digest_metadata(metadata),
        status='NOT_CONFIGURED' if error else 'PENDING',
        last_error=error, recorded_at=now,
    )


def get_binding_status(key):
    # 读详情不补任务、不初始化 SDK；旧版本/旧 namespace 不能冒充当前作用域的确认。
    fabric = is_fabric_did()
    chain_id = os.environ.get('FABRIC_DID_CHAIN_ID', '').strip() if fabric else ''
    namespace = configured_namespace() if fabric else ''
    empty = {
        'provider': PROVIDER if fabric else 'LEGACY', 'chainId': chain_id, 'namespace': namespace,
        'did': '', 'txId': '', 'status': 'NOT_REGISTERED' if fabric else 'LEGACY',
        'lastError': local_configuration_error(chain_id) if fabric else '',
        'revision': None, 'eventId': '', 'boundKeyStatus': '', 'currentKeyStatus': key.status,
        'statusMatchesCurrentKey': False,
    }
    if not fabric:
        return empty  # legacy 也不查询新表，迁移未应用时默认路径保持可用。
    row = (ChainKeyBinding.objects.filter(
        long_term_key_id=key.pk, provider=PROVIDER, chain_id=chain_id, namespace=namespace,
    ).order_by('-sequence').first())
    if row is None:
        return empty
    matches = row.key_status == key.status
    stale = row.status == 'CONFIRMED' and not matches
    return {
        'provider': row.provider, 'chainId': row.chain_id, 'namespace': row.namespace,
        'did': row.did, 'txId': row.tx_id,
        'status': 'STALE_BINDING' if stale else row.status, 'evidenceStatus': row.status,
        'lastError': 'CURRENT_KEY_STATE_NOT_BOUND' if stale else row.last_error,
        'revision': row.sequence, 'eventId': row.event_id,
        'payloadDigest': row.metadata_digest, 'boundKeyStatus': row.key_status,
        'currentKeyStatus': key.status, 'statusMatchesCurrentKey': matches,
        'transactionValid': row.transaction_valid, 'metadataMatches': row.metadata_matches,
    }


binding_payload = get_binding_status


def get_backend_status(client_factory=None):
    """配置诊断只查 Bridge 状态，不加载 SDK，更不能补任务或触发旧链构造器。"""
    if not is_fabric_did():
        return {'provider': 'LEGACY', 'chainId': '', 'configured': None, 'status': 'LEGACY',
                'networkChecked': False, 'lastError': ''}
    chain_id = os.environ.get('FABRIC_DID_CHAIN_ID', '').strip()
    error = local_configuration_error(chain_id, require_write=False)
    result = {
        'provider': PROVIDER, 'chainId': chain_id, 'configured': False,
        'enabled': error != 'DISABLED', 'writeEnabled': False,
        'status': 'DISABLED' if error == 'DISABLED' else 'NOT_CONFIGURED',
        'networkChecked': False, 'lastError': error, 'missingFields': [],
        'capabilities': {'currentNodeProjection': False, 'lifecycleEquivalent': False},
    }
    if error:
        result['missingFields'] = {
            'MISSING_CHAIN_ID': ['FABRIC_DID_CHAIN_ID'], 'MISSING_INTERNAL_TOKEN': ['INTERNAL_TOKEN'],
        }.get(error, [])
        return result
    client = None
    try:
        client = (client_factory or FabricDidClient)()
        remote = client.status()
        if remote.get('provider') != PROVIDER or remote.get('chainId') != chain_id:
            raise BindingError('BRIDGE_CHAIN_IDENTITY_MISMATCH')
        allowed_statuses = ('DISABLED', 'NOT_CONFIGURED', 'READY_READ_ONLY', 'READY')
        if remote.get('status') not in allowed_statuses:
            raise BindingError('INVALID_BRIDGE_RESPONSE')
        result['enabled'] = remote.get('enabled') is True
        result['configured'] = remote.get('configured') is True
        local_write = not local_configuration_error(chain_id, require_write=True)
        result['writeEnabled'] = local_write and remote.get('writeEnabled') is True
        if not result['enabled']:
            result['status'] = 'DISABLED'
        elif not result['configured']:
            result['status'] = 'NOT_CONFIGURED'
        elif result['writeEnabled'] and remote.get('status') == 'READY':
            result['status'] = 'READY'
        else:
            result['status'] = 'READY_READ_ONLY'
        result['lastError'] = ''
        # 只透传“缺哪些配置项”的固定名称，绝不把路径、证书、远端 msg 放到公开 API。
        safe_fields = {
            'FABRIC_DID_CHAIN_ID', 'FABRIC_DID_METHOD_ID', 'FABRIC_DID_NAMESPACE', 'INTERNAL_TOKEN',
            'FABRIC_DID_CONNECTION_FILE', 'FABRIC_DID_CONFIG_FILE', 'FABRIC_DID_MSP_ID',
            'FABRIC_DID_CERT_FILE', 'FABRIC_DID_KEY_FILE', 'FABRIC_DID_TLS_CA_FILE',
            'FABRIC_DID_CHANNEL', 'FABRIC_DID_CHAINCODE', 'FABRIC_DID_CONTROLLER_PUBLIC_KEY_FILE',
            'FABRIC_DID_PROPERTIES_FILE', 'networkConfigPath', 'certificatePath', 'privateKeyPath',
            'channelName', 'mspId', 'chaincodeId', 'userName', 'encryption', 'timeOut',
            'fabricSDK.configuration', 'gmCryptoSuiteFactory', 'gmHashAlgorithm', 'gmSecurityLevel',
        }
        missing = remote.get('missingFields')
        if isinstance(missing, list):
            result['missingFields'] = [field for field in missing if isinstance(field, str) and field in safe_fields]
        return result
    except BindingError as exc:
        result['status'] = 'UNAVAILABLE'
        result['lastError'] = exc.code
        return result
    finally:
        if client is not None:
            client.close()


def bridge_binding(row):
    return {
        'provider': row.provider, 'chainId': row.chain_id,
        'nodeId': row.node_id_snapshot, 'algorithm': row.algorithm,
        'keyId': row.key_id, 'keyVersion': row.key_version,
        'eventType': row.event_type, 'revision': row.sequence, 'eventId': row.event_id,
        'metadata': row.metadata, 'metadataDigest': row.metadata_digest,
    }


def validate_prepared(row, data):
    if any(data.get(k) != expected for k, expected in (
        ('provider', row.provider), ('chainId', row.chain_id),
        ('metadata', row.metadata), ('metadataDigest', row.metadata_digest),
    )):
        raise BindingError('PREPARED_BINDING_MISMATCH')
    for field, limit in (('did', 512), ('txId', 256), ('nonce', 4096)):
        value = data.get(field)
        if not isinstance(value, str) or not value or len(value) > limit:
            raise BindingError('INVALID_PREPARED_IDENTITY')
    return {name: data[name] for name in ('provider', 'chainId', 'did', 'txId', 'nonce', 'metadata', 'metadataDigest')}


def verification_confirmed(row, data):
    # 不接受“提交成功”、truthy 字符串或缺字段；交易和回读必须同时对上原身份。
    identities = (
        ('provider', row.provider), ('chainId', row.chain_id), ('did', row.did),
        ('txId', row.tx_id), ('metadataDigest', row.metadata_digest),
    )
    if any(data.get(field) != expected for field, expected in identities):
        raise BindingError('VERIFICATION_IDENTITY_MISMATCH')
    if data.get('status') == 'FAILED':
        raise BindingError('CHAIN_VERIFICATION_FAILED')
    return (data.get('status') == 'CONFIRMED' and
            data.get('transactionValid') is True and data.get('metadataMatches') is True)


def _claim(binding_id):
    with transaction.atomic():
        candidate = ChainKeyBinding.objects.get(pk=binding_id)
        if candidate.status in ('CONFIRMED', 'FAILED', 'UNSUPPORTED'):
            return None
        if candidate.node_id is None or candidate.long_term_key_id is None:
            ChainKeyBinding.objects.filter(pk=binding_id).update(
                status='FAILED', last_error='SOURCE_DELETED', updated_at=timezone.now(),
                lease_token='', lease_until=None,
            )
            return None
        try:
            Node.objects.select_for_update().get(pk=candidate.node_id)
        except Node.DoesNotExist:
            ChainKeyBinding.objects.filter(pk=binding_id).exclude(status='CONFIRMED').update(
                status='FAILED', last_error='SOURCE_DELETED', updated_at=timezone.now(),
            )
            return None
        row = ChainKeyBinding.objects.select_for_update().get(pk=binding_id)
        if row.long_term_key_id is None:
            row.status, row.last_error = 'FAILED', 'SOURCE_DELETED'
            row.save(update_fields=['status', 'last_error', 'updated_at'])
            return None
        if row.status in ('CONFIRMED', 'FAILED', 'UNSUPPORTED'):
            return None
        if ChainKeyBinding.objects.select_for_update().filter(
            node_id=row.node_id, provider=row.provider, chain_id=row.chain_id, namespace=row.namespace,
            sequence__lt=row.sequence,
        ).exclude(status='CONFIRMED').exists():
            return None
        now = timezone.now()
        if row.lease_until and row.lease_until > now:
            return None
        row.lease_token = uuid.uuid4().hex
        row.lease_until = now + timedelta(seconds=LEASE_SECONDS)
        row.attempts += 1
        row.save(update_fields=['lease_token', 'lease_until', 'attempts', 'updated_at'])
        return row


def _persist(row, **values):
    with transaction.atomic():
        count = ChainKeyBinding.objects.filter(
            pk=row.pk, lease_token=row.lease_token, lease_until__gt=timezone.now(),
        ).update(**values, updated_at=timezone.now())
        if count != 1:
            raise BindingError('LEASE_LOST')
    for name, value in values.items():
        setattr(row, name, value)


def _verify(row, client):
    data = client.verify(row)
    if verification_confirmed(row, data):
        _persist(row, status='CONFIRMED', transaction_valid=True, metadata_matches=True,
                 confirmed_at=timezone.now(), last_error='')
    else:
        _persist(row, status='PENDING_VERIFICATION', last_error='AWAITING_TRANSACTION_AND_METADATA')


def process_binding(binding_id, client_factory=FabricDidClient):
    if not is_fabric_did():
        return 'LEGACY_DISABLED'  # legacy 模式绝不处理 Fabric 队列。
    if connection.in_atomic_block:
        raise RuntimeError('Worker must run outside the registry transaction')
    row = _claim(binding_id)
    if row is None:
        return 'BLOCKED'
    client = None
    try:
        needs_submission = not (row.tx_id and row.submit_started)
        config_error = local_configuration_error(row.chain_id, require_write=needs_submission)
        if not row.chain_id or config_error:
            _persist(row, status='NOT_CONFIGURED', last_error=config_error or 'MISSING_CHAIN_ID')
            return row.status
        # 不能把旧空 chainId 任务自动改成当前链；切换链须显式补锚，不是假确认。
        if row.chain_id != os.environ.get('FABRIC_DID_CHAIN_ID', '').strip():
            _persist(row, status='NOT_CONFIGURED', last_error='CHAIN_CONFIGURATION_CHANGED')
            return row.status
        if row.namespace != configured_namespace():
            _persist(row, status='NOT_CONFIGURED', last_error='NAMESPACE_CONFIGURATION_CHANGED')
            return row.status
        client = client_factory()
        remote = client.status()
        if remote.get('provider') != row.provider or remote.get('chainId') != row.chain_id:
            raise BindingError('BRIDGE_CHAIN_IDENTITY_MISMATCH')
        if remote.get('configured') is not True or remote.get('enabled') is not True:
            _persist(row, status='NOT_CONFIGURED', last_error='BRIDGE_NOT_CONFIGURED')
            return row.status
        if needs_submission and (remote.get('writeEnabled') is not True or remote.get('status') != 'READY'):
            _persist(row, status='UNSUPPORTED', last_error='BRIDGE_WRITE_DISABLED_OR_UNSUPPORTED')
            return row.status
        if row.tx_id and row.submit_started:
            # 有过提交机会就不能重发；超时/租约交接/崩溃都只核对原交易。
            _verify(row, client)
            return row.status
        if row.tx_id:
            # PREPARED commit 后、提交标记之前退出：持久化计划尚未获得写机会，
            # 恢复必须用原 nonce/txId，不能重跑 prepare 换一个交易身份。
            prepared = validate_prepared(row, {
                'provider': row.provider, 'chainId': row.chain_id,
                'did': row.did, 'txId': row.tx_id, 'nonce': row.nonce,
                'metadata': row.metadata, 'metadataDigest': row.metadata_digest,
            })
        else:
            # Bridge 合同保证 prepare 只分配交易身份、不提交链。响应丢失且无持久化
            # 身份时允许重试此只读步骤；原 metadata/eventId 不变，不产生第二个 DID。
            _persist(row, status='PENDING_VERIFICATION', last_error='PREPARATION_IN_PROGRESS')
            prepared = validate_prepared(row, client.prepare(bridge_binding(row)))
            _persist(row, status='PREPARED', did=prepared['did'], tx_id=prepared['txId'], nonce=prepared['nonce'], last_error='')
        # 先 commit 标记再调用 submit。极端退出可能使未提交任务待人工核对，不能盲重发。
        if not ChainKeyBinding.objects.filter(
            pk=row.pk, node_id__isnull=False, long_term_key_id__isnull=False,
        ).exists():
            raise BindingError('SOURCE_DELETED')
        _persist(row, status='PENDING_VERIFICATION', submit_started=True)
        try:
            client.submit(bridge_binding(row), prepared)
            _persist(row, status='SUBMITTED')
        except BindingError:
            # 远端可能已接收，响应丢失不能当作“没提交”。马上核对同一 txId。
            _persist(row, status='PENDING_VERIFICATION', last_error='SUBMIT_OUTCOME_UNKNOWN')
        _verify(row, client)
    except BindingError as exc:
        if exc.code != 'LEASE_LOST':
            if exc.code in ('DISABLED', 'NOT_CONFIGURED'):
                status = 'NOT_CONFIGURED'
            elif exc.code in ('WRITE_DISABLED', 'CHAIN_POLICY_NOT_APPROVED', 'UNSUPPORTED'):
                status = 'UNSUPPORTED'
            elif exc.code in ('BRIDGE_TIMEOUT', 'BRIDGE_UNAVAILABLE'):
                status = 'PENDING_VERIFICATION' if row.tx_id or row.status == 'PENDING_VERIFICATION' else 'PENDING'
            else:
                status = 'FAILED'
            try:
                _persist(row, status=status, last_error=exc.code)
            except BindingError as lease_error:
                if lease_error.code != 'LEASE_LOST':
                    raise
    finally:
        if client is not None:
            client.close()
        ChainKeyBinding.objects.filter(pk=row.pk, lease_token=row.lease_token).update(lease_token='', lease_until=None)
    return row.status


def process_pending_bindings(limit=100):
    if not is_fabric_did():
        return {'LEGACY_DISABLED': 0}
    prior = ChainKeyBinding.objects.filter(
        node_id=OuterRef('node_id'), provider=OuterRef('provider'), chain_id=OuterRef('chain_id'),
        namespace=OuterRef('namespace'), sequence__lt=OuterRef('sequence'),
    ).exclude(status='CONFIRMED')
    results = {}
    attempted = []
    for _ in range(limit):
        now = timezone.now()
        # 只挑每节点队头；坏节点的后续任务不能把 limit 填满，饿死其它节点。
        binding_id = (ChainKeyBinding.objects.exclude(status__in=['CONFIRMED', 'FAILED', 'UNSUPPORTED'])
                      .exclude(pk__in=attempted)
                      .filter(Q(lease_until__isnull=True) | Q(lease_until__lte=now))
                      .annotate(has_prior=Exists(prior)).filter(has_prior=False)
                      .order_by('recorded_at', 'pk').values_list('pk', flat=True).first())
        if binding_id is None:
            break
        attempted.append(binding_id)
        status = process_binding(binding_id)
        results[status] = results.get(status, 0) + 1
    return results
