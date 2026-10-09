# -*- coding: utf-8 -*-
"""Experimental, public-only issuance provenance, not proof of client seed use.

The independent 32-byte contribution exists only in the confidential issuance
response. Authorization renewal never recovers or generates that contribution.
"""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import os
import secrets
import uuid
from datetime import timedelta
from urllib.parse import urlsplit

from django.db import transaction
from django.utils import timezone

from . import api_contract as C
from .models import KeyGenerationAuthorization, KeyGenerationIssuance, Node, NodeLongTermKey

AUTHORIZATION_TTL = timedelta(minutes=10)
GENERATION_FIELDS = frozenset({
    'schemeId', 'schemeVersion', 'generationIssuanceId', 'authorizationTicketId',
})
BINDING_FIELDS = (
    'userId', 'nodeId', 'bindingKind', 'deviceFingerprint', 'demoSessionId', 'demoRevision',
)
PRIVATE_FIELDS = frozenset({
    'privatekey', 'secretkey', 'private', 'secret', 'sk', 'share', 'kgcshare',
    'localsecret', 'seed', 'ikm', 'd', 'z', 'recoveryseed',
})


def policy_enabled():
    # Enable only after seeded-oracle/interoperability and independent review gates.
    return os.environ.get('KMS_SPLIT_KEYGEN_ENABLED', 'false').lower() == 'true'


def _fail(message, code=C.ERR_INVALID_PARAMETER):
    raise C.ContractError(message, code=code)


def reject_private_fields(value):
    """Reject nested secret fields before service/logging/metadata paths."""
    if isinstance(value, dict):
        for name, child in value.items():
            normalized = str(name).replace('_', '').replace('-', '').lower()
            if normalized in PRIVATE_FIELDS:
                _fail('公钥接口禁止上传私密生成材料')
            reject_private_fields(child)
    elif isinstance(value, list):
        for child in value:
            reject_private_fields(child)


def validate_generation(generation, algorithm):
    if generation is None:
        return None
    if not isinstance(generation, dict) or set(generation) != GENERATION_FIELDS:
        _fail('generation 只能包含四个必填公共方案/票据字段', C.ERR_KEYGEN_SCHEME_INVALID)
    if (generation['schemeId'] != C.SPLIT_GENERATION_SCHEMES.get(algorithm)
            or type(generation['schemeVersion']) is not int
            or generation['schemeVersion'] != 1):
        _fail('未知或不匹配的生成方案', C.ERR_KEYGEN_SCHEME_INVALID)
    for name in ('generationIssuanceId', 'authorizationTicketId'):
        raw = generation[name]
        try:
            valid = isinstance(raw, str) and str(uuid.UUID(raw)) == raw
        except (ValueError, AttributeError):
            valid = False
        if not valid:
            _fail('生成来源/授权标识无效', C.ERR_KEYGEN_SCHEME_INVALID)
    return generation


def _decimal(raw, *, minimum=0):
    if isinstance(raw, bool) or not isinstance(raw, (str, int)):
        _fail('可信身份中的数值字段无效', C.ERR_KEYGEN_CONTEXT_MISMATCH)
    text = str(raw)
    if not text.isascii() or not text.isdigit() or int(text) < minimum:
        _fail('可信身份中的数值字段无效', C.ERR_KEYGEN_CONTEXT_MISMATCH)
    return str(int(text))


def require_confidential_transport(request, *, demo=False):
    if demo:
        from .demo_context import trusted_demo_request
        if not trusted_demo_request(request):
            _fail('需要受控本机 Demo 网关', C.ERR_KEYGEN_CONTEXT_MISMATCH)
        return
    if request.is_secure():
        return
    # Do not trust Host or client X-Forwarded-Proto alone as a local/TLS proof.
    host = urlsplit('//' + request.get_host()).hostname
    try:
        peer_local = ipaddress.ip_address(request.META.get('REMOTE_ADDR', '')).is_loopback
    except ValueError:
        peer_local = False
    if host not in {'localhost', '127.0.0.1', '::1'} or not peer_local:
        _fail('非回环独立模式签发必须使用 HTTPS', C.ERR_KEYGEN_HTTPS_REQUIRED)


def trusted_binding(request, node, identity, device_id=None, *, require_init_lease=True):
    if (identity.get('userId') != node.sys_user_id
            or str(node.status or '').lower() in {'inactive', 'disabled'}):
        _fail('节点身份无效或节点已停用', C.ERR_KEYGEN_CONTEXT_MISMATCH)
    demo = identity.get('entryMode') == 'DEMO'
    binding = {
        'userId': _decimal(identity.get('userId'), minimum=1),
        'nodeId': node.node_id,
        'bindingKind': 'DEMO' if demo else 'DEVICE',
        'deviceFingerprint': '', 'demoSessionId': '', 'demoRevision': '',
    }
    if demo:
        from .demo_context import trusted_demo_request, validate_init_lease
        session = getattr(request, 'demo_session_id', '')
        if (not trusted_demo_request(request) or not session
                or identity.get('principalType') != 'NODE'
                or identity.get('nodeId') != node.node_id):
            _fail('演示身份上下文无效', C.ERR_KEYGEN_CONTEXT_MISMATCH)
        if (require_init_lease and str(node.status or '').lower() != 'active'
                and not validate_init_lease(request, node.node_id)):
            _fail('初始化租约已失效', 'DEMO_INIT_LEASE_REQUIRED')
        # Never put the bearer session Cookie into a public context/database/DTO.
        binding['demoSessionId'] = hashlib.sha256(session.encode('utf-8')).hexdigest()
        binding['demoRevision'] = _decimal(identity.get('sessionRevision'))
    else:
        try:
            device_key = json.loads(node.device_auth_public_key or '{}')
            fingerprint = hashlib.sha256(
                f"{device_key['crv']}|{device_key['x']}|{device_key['y']}".encode('utf-8')
            ).hexdigest()[:32]
        except (ValueError, KeyError, TypeError):
            _fail('需要已激活的可信设备', C.ERR_KEYGEN_CONTEXT_MISMATCH)
        if (device_key.get('crv') != 'P-256' or not node.key_device_id
                or fingerprint != node.key_device_id
                or (device_id is not None and device_id != fingerprint)):
            _fail('设备与已激活指纹不一致', C.ERR_KEYGEN_CONTEXT_MISMATCH)
        binding['deviceFingerprint'] = fingerprint
    return binding


def _lock_node(node):
    # Existing row is the serialization point even when no issuance/key exists.
    return Node.objects.select_for_update().get(pk=node.pk)


def _assert_binding(issuance, node, binding):
    locked = _lock_node(node)
    if (not binding or locked.sys_user_id is None
            or binding.get('userId') != str(locked.sys_user_id)
            or binding.get('nodeId') != locked.node_id
            or str(locked.status or '').lower() in {'inactive', 'disabled'}
            or (binding.get('bindingKind') == 'DEVICE'
                and binding.get('deviceFingerprint') != locked.key_device_id)):
        _fail('当前节点/设备绑定已改变', C.ERR_KEYGEN_CONTEXT_MISMATCH)
    context = issuance.context
    if (issuance.node_id != node.pk or not isinstance(context, dict)
            or set(context) != set(C.SPLIT_CONTEXT_FIELDS)
            or not binding or any(context.get(k) != binding.get(k) for k in BINDING_FIELDS)
            or context['generationIssuanceId'] != issuance.pk
            or context['coreFamily'] != issuance.algorithm
            or context['keyId'] != issuance.key_id
            or context['keyVersion'] != str(issuance.key_version)
            or context['schemeId'] != C.SPLIT_GENERATION_SCHEMES.get(issuance.algorithm)
            or context['schemeVersion'] != '1'
            or context['purpose'] != ('KEM_KEYGEN' if issuance.algorithm == 'KYBER' else 'SIGN_KEYGEN')):
        _fail('生成来源与当前可信上下文不一致；不得自动换钥', C.ERR_KEYGEN_CONTEXT_MISMATCH)
    if issuance.status == 'ABANDONED':
        _fail('原生成发放已显式放弃', C.ERR_KEYGEN_AUTHORIZATION_SUPERSEDED)


def _get_issuance(issuance_id):
    row = KeyGenerationIssuance.objects.select_for_update().filter(pk=issuance_id).first()
    if row is None or row.pk != issuance_id:
        _fail('找不到精确生成来源', C.ERR_KEYGEN_CONTEXT_MISMATCH)
    return row


def canonical_public_key(algorithm, public_key, variant, *, stored=False):
    if not isinstance(public_key, str):
        _fail('公钥必须为编码字符串')
    try:
        raw = (base64.b64decode(public_key, validate=True)
               if stored and algorithm == 'KYBER' else bytes.fromhex(public_key))
    except (ValueError, TypeError):
        _fail('公钥编码无效')
    expected = {'512': 800, '768': 1184, '1024': 1568} if algorithm == 'KYBER' else {'512': 897}
    if len(raw) != expected.get(variant) or (algorithm == 'FALCON' and raw[0] != 9):
        _fail('公钥参数集与原生成上下文不同', C.ERR_KEYGEN_CONTEXT_MISMATCH)
    material = base64.b64encode(raw).decode('ascii') if algorithm == 'KYBER' else raw.hex()
    if stored and public_key != material:
        _fail('新方案公钥存储编码必须规范且无空白', C.ERR_KEYGEN_CONTEXT_MISMATCH)
    return material, hashlib.sha256(material.encode('utf-8')).hexdigest()


def _expiry_iso(value):
    aware = timezone.make_aware(value) if timezone.is_naive(value) else value
    return aware.isoformat()


def _new_authorization(issuance, digest=''):
    return KeyGenerationAuthorization.objects.create(
        authorization_ticket_id=str(uuid.uuid4()), issuance=issuance,
        public_key_hash=digest, expires_at=timezone.now() + AUTHORIZATION_TTL,
    )


@transaction.atomic
def issue_contribution(node, binding, *, algorithm, key_id, key_version, variant,
                       abandon_generation_issuance_id=None):
    from .node_key_registry import _as_version, _validate_key_id
    if not policy_enabled():
        _fail('实验生成策略尚未通过启用门槛', C.ERR_KEYGEN_POLICY_DISABLED)
    if algorithm not in C.SPLIT_GENERATION_SCHEMES:
        _fail('签发仅支持规范 KYBER/FALCON 家族', C.ERR_KEYGEN_SCHEME_INVALID)
    variant = str(variant)
    if variant not in ({'512', '768', '1024'} if algorithm == 'KYBER' else {'512'}):
        _fail('生成参数集无效')
    kid, version = _validate_key_id(key_id), _as_version(key_version)
    if not kid:
        _fail('签发必须显式提供 keyId')
    locked = _lock_node(node)
    if (locked.sys_user_id != node.sys_user_id or locked.key_device_id != node.key_device_id
            or str(locked.status or '').lower() in {'inactive', 'disabled'}):
        _fail('节点绑定已改变', C.ERR_KEYGEN_CONTEXT_MISMATCH)
    if NodeLongTermKey.objects.select_for_update().filter(
            node=node, algorithm=algorithm, key_id=kid, key_version=version).exists():
        _fail('该 keyRef 已登记，请复用已封存材料', C.ERR_KEYGEN_ISSUANCE_CONFLICT)
    previous = KeyGenerationIssuance.objects.select_for_update().filter(
        node=node, algorithm=algorithm, key_id=kid, key_version=version, current_slot='CURRENT',
    ).first()
    if previous:
        _assert_binding(previous, node, binding)
        if (abandon_generation_issuance_id != previous.pk or previous.status != 'ISSUED'
                or previous.public_key_hash):
            _fail('该 keyRef 已签发；复用封存材料或显式放弃未用来源', C.ERR_KEYGEN_ISSUANCE_CONFLICT)
        previous.status, previous.current_slot = 'ABANDONED', None
        previous.save(update_fields=['status', 'current_slot'])
        previous.authorizations.filter(status__in=['ISSUED', 'EXPIRED']).update(
            status='SUPERSEDED', current_slot=None,
        )
    elif abandon_generation_issuance_id is not None:
        _fail('指定的放弃来源不存在', C.ERR_KEYGEN_ISSUANCE_CONFLICT)
    issuance_id = str(uuid.uuid4())
    context = {
        'schemeId': C.SPLIT_GENERATION_SCHEMES[algorithm], 'schemeVersion': '1',
        'coreFamily': algorithm, 'variant': variant, **binding,
        'keyId': kid, 'keyVersion': str(version),
        'purpose': 'KEM_KEYGEN' if algorithm == 'KYBER' else 'SIGN_KEYGEN',
        'generationIssuanceId': issuance_id,
    }
    issuance = KeyGenerationIssuance.objects.create(
        generation_issuance_id=issuance_id, node=node, algorithm=algorithm,
        key_id=kid, key_version=version, context=context,
    )
    ticket = _new_authorization(issuance)
    return {
        'generationScheme': context['schemeId'], 'generationIssuanceId': issuance_id,
        'authorizationTicketId': ticket.pk, 'context': context,
        'share': base64.b64encode(secrets.token_bytes(32)).decode('ascii'),
        'expiresAt': _expiry_iso(ticket.expires_at),
        'transportScope': 'LOCAL_DEMO_EXPERIMENT_ONLY' if binding['bindingKind'] == 'DEMO'
                          else 'AUTHENTICATED_CONFIDENTIAL_ISSUANCE',
    }


@transaction.atomic
def list_issuances(node, binding):
    _lock_node(node)
    records = []
    for issuance in KeyGenerationIssuance.objects.filter(node=node, current_slot='CURRENT'):
        if any(issuance.context.get(k) != binding.get(k) for k in BINDING_FIELDS):
            continue
        _assert_binding(issuance, node, binding)
        ticket = issuance.authorizations.filter(current_slot='CURRENT').first()
        records.append({
            'generationIssuanceId': issuance.pk, 'context': issuance.context,
            'status': issuance.status, 'publicKeyHash': issuance.public_key_hash,
            'authorizationTicketId': ticket.pk if ticket else None,
            'authorizationStatus': ('EXPIRED' if ticket and ticket.status == 'ISSUED'
                                    and ticket.expires_at <= timezone.now() else ticket.status)
                                   if ticket else None,
            'expiresAt': _expiry_iso(ticket.expires_at) if ticket else None,
        })
    return {'issuances': records}


@transaction.atomic
def renew_authorization(node, binding, *, generation_issuance_id, public_key):
    _lock_node(node)
    issuance = _get_issuance(generation_issuance_id)
    _assert_binding(issuance, node, binding)
    _, digest = canonical_public_key(issuance.algorithm, public_key, issuance.context['variant'])
    if issuance.public_key_hash and issuance.public_key_hash != digest:
        _fail('原来源已绑定不同公钥', C.ERR_KEYGEN_PUBLIC_KEY_CONFLICT)
    if issuance.status == 'BOUND':
        ticket = issuance.authorizations.select_for_update().filter(status='BOUND').first()
        if ticket is None or ticket.public_key_hash != digest:
            _fail('已登记来源与授权记录不一致', C.ERR_KEYGEN_PUBLIC_KEY_CONFLICT)
    else:
        issuance.public_key_hash = digest
        issuance.save(update_fields=['public_key_hash'])
        issuance.authorizations.filter(status__in=['ISSUED', 'EXPIRED']).update(
            status='SUPERSEDED', current_slot=None,
        )
        ticket = _new_authorization(issuance, digest)
    return {
        'generationIssuanceId': issuance.pk, 'authorizationTicketId': ticket.pk,
        'expiresAt': _expiry_iso(ticket.expires_at),
    }


def consume_authorization(node, binding, generation, *, algorithm, key_id, key_version,
                          public_key, security_level=''):
    """Called only within registry transaction after locking the existing Node."""
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError('Key generation authorization requires registry transaction')
    issuance = _get_issuance(generation['generationIssuanceId'])
    _assert_binding(issuance, node, binding)
    context = issuance.context
    if (issuance.algorithm != algorithm or issuance.key_id != key_id
            or issuance.key_version != key_version or context['keyId'] != key_id
            or context['keyVersion'] != str(key_version)
            or context['schemeId'] != generation['schemeId']
            or (security_level and str(security_level) != context['variant'])):
        _fail('登记字段与冻结生成上下文不同', C.ERR_KEYGEN_CONTEXT_MISMATCH)
    _, digest = canonical_public_key(algorithm, public_key, context['variant'], stored=True)
    ticket = KeyGenerationAuthorization.objects.select_for_update().filter(
        pk=generation['authorizationTicketId'], issuance=issuance,
    ).first()
    if ticket is None or ticket.pk != generation['authorizationTicketId']:
        _fail('授权不属于该原始来源', C.ERR_KEYGEN_CONTEXT_MISMATCH)
    if (issuance.public_key_hash and issuance.public_key_hash != digest
            or ticket.public_key_hash and ticket.public_key_hash != digest):
        _fail('来源/授权已绑定另一公钥', C.ERR_KEYGEN_PUBLIC_KEY_CONFLICT)
    if ticket.status == 'BOUND':
        exact = NodeLongTermKey.objects.select_for_update().filter(
            node=node, algorithm=algorithm, key_id=key_id, key_version=key_version,
        ).first()
        if (issuance.status != 'BOUND' or ticket.public_key_hash != digest or exact is None
                or exact.public_key_hash != digest or exact.public_key != public_key
                or exact.generation_issuance_id != issuance.pk
                or exact.generation_scheme != context['schemeId']
                or exact.generation_context != context):
            _fail('已消费授权只允许保留登记行的精确重试，不能重新创建', C.ERR_KEYGEN_PUBLIC_KEY_CONFLICT)
        return issuance
    if ticket.status == 'SUPERSEDED':
        _fail('授权已被替代', C.ERR_KEYGEN_AUTHORIZATION_SUPERSEDED)
    if ticket.status == 'EXPIRED' or ticket.expires_at <= timezone.now():
        _fail('登记授权已过期；续期必须复用原来源和已封存公钥', C.ERR_KEYGEN_AUTHORIZATION_EXPIRED)
    if ticket.status != 'ISSUED' or issuance.status != 'ISSUED':
        _fail('来源/授权状态无效', C.ERR_KEYGEN_CONTEXT_MISMATCH)
    ticket.status, ticket.public_key_hash = 'BOUND', digest
    ticket.save(update_fields=['status', 'public_key_hash'])
    issuance.status, issuance.public_key_hash = 'BOUND', digest
    issuance.save(update_fields=['status', 'public_key_hash'])
    return issuance


def validate_existing_provenance(key, node, binding, generation):
    if generation is not None:
        if (key.generation_scheme != generation['schemeId']
                or key.generation_issuance_id != generation['generationIssuanceId']
                or key.generation_scheme_version != generation['schemeVersion']):
            _fail('精确重试不能改写原始来源', C.ERR_KEYGEN_PUBLIC_KEY_CONFLICT)
        consume_authorization(
            node, binding, generation, algorithm=key.algorithm, key_id=key.key_id,
            key_version=key.key_version, public_key=key.public_key,
            security_level=key.security_level,
        )
    elif key.generation_issuance_id:
        # Omitting generation must not bypass the original device/Demo revision fence.
        issuance = _get_issuance(key.generation_issuance_id)
        _assert_binding(issuance, node, binding)


def public_generation_payload(key):
    return {
        'generation': {
            'schemeId': key.generation_scheme,
            'schemeVersion': key.generation_scheme_version,
            'generationIssuanceId': key.generation_issuance_id,
            'authorizationTicketId': key.generation_authorization_ticket_id,
        } if key.generation_scheme else None,
        'generationScheme': key.generation_scheme,
        'generationSchemeVersion': key.generation_scheme_version,
        'generationIssuanceId': key.generation_issuance_id,
        'generationContext': key.generation_context,
        'generationProvenance': 'CLIENT_ATTESTED_SERVER_ISSUANCE_VALIDATED'
                                if key.generation_scheme else 'UNRECORDED',
    }
