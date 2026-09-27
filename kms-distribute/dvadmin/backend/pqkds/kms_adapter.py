import hashlib
import hmac
import json
import logging
import os

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import KeyDistributionLog, Node, NodeKeyVersion, PreDistributedKey, SessionKey
from .operation_log import set_request_msg
from .session_invalidation_service import SessionInvalidationService
from .views import _kms_generate_for_algorithm, _kms_key_reference

logger = logging.getLogger(__name__)

KMS_ADAPTER_SERVICE_TOKEN_SETTING = 'PQKDS_KMS_ADAPTER_SERVICE_TOKEN'
KMS_ADAPTER_SERVICE_TOKEN_ENV = 'PQKDS_KMS_ADAPTER_SERVICE_TOKEN'
KMS_ADAPTER_SERVICE_TOKEN_LEGACY_ENV = 'KMS_DEMO_ADAPTER_SERVICE_TOKEN'
KMS_ADAPTER_SERVICE_ID_SETTING = 'PQKDS_KMS_ADAPTER_SERVICE_ID'
KMS_ADAPTER_SERVICE_ID_ENV = 'PQKDS_KMS_ADAPTER_SERVICE_ID'
KMS_ADAPTER_TOKEN_HEADER = 'HTTP_X_KMS_SERVICE_TOKEN'
KMS_ADAPTER_SERVICE_ID_HEADER = 'HTTP_X_KMS_SERVICE_ID'


def _response(code, message, data=None, http_status=None):
    return Response({'code': code, 'message': message, 'data': data}, status=http_status or 200)


def _configured_service_token():
    return (
        getattr(settings, KMS_ADAPTER_SERVICE_TOKEN_SETTING, '')
        or os.environ.get(KMS_ADAPTER_SERVICE_TOKEN_ENV, '')
        or os.environ.get(KMS_ADAPTER_SERVICE_TOKEN_LEGACY_ENV, '')
    )


def _configured_service_id():
    return getattr(settings, KMS_ADAPTER_SERVICE_ID_SETTING, '') or os.environ.get(KMS_ADAPTER_SERVICE_ID_ENV, '')


def _request_service_token(request):
    header_token = request.META.get(KMS_ADAPTER_TOKEN_HEADER, '')
    if header_token:
        return header_token.strip()
    authorization = request.META.get('HTTP_AUTHORIZATION', '')
    if authorization.lower().startswith('bearer '):
        return authorization[7:].strip()
    return ''


def _is_authorized(request):
    configured_token = _configured_service_token()
    if not configured_token:
        logger.error('KMS demo adapter rejected request because service token is not configured')
        return False
    configured_service_id = _configured_service_id()
    request_service_id = request.META.get(KMS_ADAPTER_SERVICE_ID_HEADER, '')
    if configured_service_id and not hmac.compare_digest(request_service_id, configured_service_id):
        return False
    return hmac.compare_digest(_request_service_token(request), configured_token)


def _require_service_credential(view_func):
    def wrapped(request, *args, **kwargs):
        if not _is_authorized(request):
            return _response(401, 'invalid kms service credential', None, http_status=401)
        return view_func(request, *args, **kwargs)
    return wrapped


def _hash_value(value):
    if not value:
        return ''
    return hashlib.sha256(str(value).encode('utf-8')).hexdigest()


def _node_capability_lookup(node):
    key_version = NodeKeyVersion.objects.filter(node=node).first()
    active_sessions = SessionKey.objects.filter(
        models.Q(node1=node) | models.Q(node2=node),
        status__in=['initiated', 'established', 'blockchain_recorded'],
        expires_at__gt=timezone.now(),
    ).count()
    available_pools = PreDistributedKey.objects.filter(
        models.Q(node1=node) | models.Q(node2=node),
        status__in=['unused', 'distributed'],
        expires_at__gt=timezone.now(),
    ).values('algorithm').annotate(count=models.Count('id')).order_by('algorithm')

    capabilities = {
        'kyber': {
            'available': bool(node.kyber_public_key or node.kyber_partial_key_data),
            'public_key_hash': _hash_value(node.kyber_public_key),
            'partial_key_available': bool(node.kyber_partial_key_data),
            'version': key_version.kyber_version if key_version else None,
        },
        'falcon': {
            'available': bool(node.falcon_public_key or node.falcon_partial_key_data),
            'public_key_hash': _hash_value(node.falcon_public_key),
            'partial_key_available': bool(node.falcon_partial_key_data),
            'version': key_version.falcon_version if key_version else None,
        },
        'sm2': {
            'available': False,
            'phase': 'frontend_local_simulation_only',
        },
        'sscl': {
            'available': False,
            'phase': 'frontend_local_simulation_only',
        },
    }

    version_seed = json.dumps({
        'node_id': node.node_id,
        'status': node.status,
        'partial_key_received': node.partial_key_received,
        'kyber_hash': capabilities['kyber']['public_key_hash'],
        'falcon_hash': capabilities['falcon']['public_key_hash'],
        'kyber_version': capabilities['kyber']['version'],
        'falcon_version': capabilities['falcon']['version'],
    }, sort_keys=True)

    return {
        'demo_node_id': node.node_id,
        'node_name': node.name,
        'status': node.status,
        'partial_key_received': node.partial_key_received,
        'last_active': node.last_active.isoformat() if node.last_active else None,
        'capabilities': capabilities,
        'active_session_count': active_sessions,
        'key_pool_summary': list(available_pools),
        'capability_version': hashlib.sha256(version_seed.encode('utf-8')).hexdigest(),
        'lookup_source': 'demo_adapter',
        'lookup_kind': 'read_only_demo_capability',
    }


def _get_node_or_error(demo_node_id):
    if not demo_node_id:
        return None, _response(400, 'missing demo_node_id', None, http_status=400)
    node = Node.objects.filter(node_id=demo_node_id).first()
    if not node:
        return None, _response(404, f'invalid demo_node_id: {demo_node_id}', None, http_status=404)
    return node, None


@api_view(['POST'])
@permission_classes([AllowAny])
@_require_service_credential
def generate_key(request):
    demo_node_id = request.data.get('demo_node_id') or request.data.get('node_id')
    node, error = _get_node_or_error(demo_node_id)
    if error:
        return error
    algorithm = request.data.get('algorithm') or 'PQ_FALCON'
    correlation_id = request.data.get('correlation_id') or request.data.get('operation_id') or request.data.get('key_id') or ''
    try:
        set_request_msg(request, f'KMS适配器生成PQ密钥(节点{node.node_id})')
        result = _kms_generate_for_algorithm(node.node_id, algorithm)
        node.refresh_from_db()
        success = bool(result.get('success'))
        log = KeyDistributionLog.objects.create(
            node=node,
            action='user_key_gen' if success else 'partial_key_gen',
            details=json.dumps({
                'source': 'kms_adapter_generate_key',
                'operation_id': request.data.get('operation_id'),
                'idempotency_key': request.data.get('idempotency_key'),
                'correlation_id': correlation_id,
                'algorithm': algorithm,
                'scheme': request.data.get('scheme'),
                'key_use': request.data.get('key_use'),
                'kms_user_id': request.data.get('kms_user_id'),
                'result_message': result.get('message'),
            }, ensure_ascii=False),
            success=success,
            error_message='' if success else result.get('message', 'generation failed'),
        )
        if not success:
            return _response(400, result.get('message', 'generation failed'), None, http_status=400)
        return _response(200, 'ok', {
            'demo_record_id': str(log.id or log.pk),
            'demo_node_id': node.node_id,
            'status': 'generated',
            'key_material_or_reference': _kms_key_reference(node, result, algorithm),
            'capability_lookup': _node_capability_lookup(node),
        })
    except Exception as exc:
        logger.error(f'KMS适配器生成PQ密钥异常: {exc}')
        return _response(400, f'generation failed: {str(exc)}', None, http_status=400)


@api_view(['POST'])
@permission_classes([AllowAny])
@_require_service_credential
def update_lifecycle(request):
    demo_node_id = request.data.get('demo_node_id') or request.data.get('node_id')
    node, error = _get_node_or_error(demo_node_id)
    if error:
        return error
    lifecycle_action = (request.data.get('action') or 'rotate').lower()
    key_type = (request.data.get('key_type') or request.data.get('algorithm') or 'both').lower()
    if key_type in ['pq_both', 'pq_cl', 'all']:
        key_type = 'both'
    if key_type not in ['kyber', 'falcon', 'both']:
        return _response(400, "invalid key_type, must be 'kyber', 'falcon' or 'both'", None, http_status=400)
    if lifecycle_action not in ['rotate', 'refresh', 'update']:
        return _response(400, "invalid action, must be 'rotate', 'refresh' or 'update'", None, http_status=400)

    try:
        capability_lookup = _node_capability_lookup(node)
        KeyDistributionLog.objects.create(
            node=node,
            action='key_update',
            details=json.dumps({
                'source': 'kms_adapter_lifecycle_lookup',
                'operation_id': request.data.get('operation_id'),
                'idempotency_key': request.data.get('idempotency_key'),
                'action': lifecycle_action,
                'key_type': key_type,
                'kms_user_id': request.data.get('kms_user_id'),
                'result_message': 'read-only capability lookup; demo node keys were not mutated',
            }, ensure_ascii=False),
            success=True,
        )
        return _response(200, 'ok', {
            'demo_node_id': node.node_id,
            'status': 'capability_lookup',
            'key_type': key_type,
            'capability_lookup': capability_lookup,
        })
    except Exception as exc:
        logger.error(f'KMS适配器生命周期能力查询异常: {exc}')
        return _response(400, f'lifecycle lookup failed: {str(exc)}', None, http_status=400)


@api_view(['POST'])
@permission_classes([AllowAny])
@_require_service_credential
def revoke(request):
    demo_node_id = request.data.get('demo_node_id') or request.data.get('node_id')
    session_id = request.data.get('session_id')
    revoke_scope = (request.data.get('scope') or ('session' if session_id else 'node_sessions')).lower()
    node, error = _get_node_or_error(demo_node_id)
    if error:
        return error
    try:
        if revoke_scope == 'session':
            if not session_id:
                return _response(400, 'missing session_id for session revoke', None, http_status=400)
            session = SessionKey.objects.filter(session_id=session_id).filter(models.Q(node1=node) | models.Q(node2=node)).first()
            if not session:
                return _response(404, f'invalid session_id for node: {session_id}', None, http_status=404)
            with transaction.atomic():
                if session.status not in ['revoked', 'expired']:
                    session.status = 'revoked'
                    session.save(update_fields=['status'])
            result = {'success': True, 'invalidated_count': 1, 'invalidated_sessions': [{'session_id': session.session_id}]}
        elif revoke_scope in ['node_sessions', 'capability_reference']:
            result = SessionInvalidationService.invalidate_sessions_for_node_key_update(node, reason='manual_revocation')
        else:
            return _response(400, "invalid scope, must be 'session', 'node_sessions' or 'capability_reference'", None, http_status=400)

        KeyDistributionLog.objects.create(
            node=node,
            action='key_revoke',
            details=json.dumps({
                'source': 'kms_adapter_revoke',
                'operation_id': request.data.get('operation_id'),
                'idempotency_key': request.data.get('idempotency_key'),
                'scope': revoke_scope,
                'session_id': session_id,
                'kms_user_id': request.data.get('kms_user_id'),
                'result': result,
            }, ensure_ascii=False),
            success=bool(result.get('success')),
            error_message='' if result.get('success') else result.get('message', 'revoke failed'),
        )
        if not result.get('success'):
            return _response(400, result.get('message', 'revoke failed'), None, http_status=400)
        return _response(200, 'ok', {
            'demo_node_id': node.node_id,
            'scope': revoke_scope,
            'result': result,
            'capability_lookup': _node_capability_lookup(node),
        })
    except Exception as exc:
        logger.error(f'KMS适配器撤销异常: {exc}')
        return _response(400, f'revoke failed: {str(exc)}', None, http_status=400)


@api_view(['POST'])
@permission_classes([AllowAny])
@_require_service_credential
def distribute_key_pool(request):
    sender_node_id = request.data.get('sender_node_id') or request.data.get('node1_id')
    receiver_node_id = request.data.get('receiver_node_id') or request.data.get('node2_id')
    if not sender_node_id or not receiver_node_id:
        return _response(400, 'missing sender_node_id or receiver_node_id', None, http_status=400)
    try:
        count = int(request.data.get('count') or 50)
        expiry_hours = int(request.data.get('expiry_hours') or 24)
        if count < 1 or count > 1000:
            return _response(400, 'count range: 1-1000', None, http_status=400)
        from .key_pool_service import KeyPoolService
        result = KeyPoolService.generate_distributable_pool(sender_node_id, receiver_node_id, count, expiry_hours)
        if not result.get('success'):
            return _response(400, result.get('message', 'distribution failed'), None, http_status=400)
        sender = Node.objects.filter(node_id=sender_node_id).first()
        projection_data = _node_capability_lookup(sender) if sender else None
        return _response(200, 'ok', {
            'status': 'distributed',
            'sender_demo_node_id': sender_node_id,
            'receiver_demo_node_id': receiver_node_id,
            'result': result,
            'projection': projection_data,
        })
    except Exception as exc:
        logger.error(f'KMS适配器密钥池下发异常: {exc}')
        return _response(400, f'distribution failed: {str(exc)}', None, http_status=400)
