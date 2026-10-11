"""One paginated audit source for administrator and node revocation views."""
import json
import logging

from django.core.paginator import Paginator
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt

from . import api_contract as C
from .kms_service_client import record_chain_event
from .node_key_review_service import handle_inspection, inspection_payload, key_impact

logger = logging.getLogger(__name__)
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .models import Node, NodeKeyAutoRevocationBatch, NodeKeyInspection, NodeLongTermKey
from .user_distribution_views import require_kms_user


def _int_param(request, name, default, maximum):
    try:
        return max(1, min(int(request.GET.get(name, default)), maximum))
    except (ValueError, TypeError):
        return default


@require_http_methods(['GET'])
@require_kms_user
def node_key_reviews(request, identity):
    """Admins see every node; node accounts see only their own key records."""
    try:
        admin = int(identity.get('roleLevel')) <= 0
    except (TypeError, ValueError):
        admin = False
    node = None if admin else Node.objects.filter(sys_user_id=identity.get('userId')).first()
    if not admin and node is None:
        return JsonResponse({'code': 403, 'message': '当前账号没有节点密钥记录访问权限'}, status=403)

    mode = request.GET.get('mode', 'revoked')
    if mode not in ('revoked', 'review', 'handled'):
        return JsonResponse({'code': 400, 'message': 'mode 只能为 revoked、review 或 handled'}, status=400)
    page = _int_param(request, 'page', 1, 1_000_000)
    size = _int_param(request, 'pageSize', 30, 100)
    algorithm = request.GET.get('algorithm', '').strip().upper()
    keyword = request.GET.get('keyword', '').strip()[:64]
    node_id = request.GET.get('nodeId', '').strip()[:64] if admin else ''

    if mode == 'revoked':
        rows = NodeLongTermKey.objects.filter(status='REVOKED')
    elif mode == 'handled':
        rows = NodeLongTermKey.objects.filter(inspection__disposition__isnull=False)
    else:
        rows = NodeLongTermKey.objects.filter(inspection__action=C.INSPECTION_PENDING_REVIEW)
    if node is not None:
        rows = rows.filter(node=node)
    elif node_id:
        rows = rows.filter(node__node_id=node_id)
    if algorithm:
        rows = rows.filter(algorithm=algorithm)
    if keyword:
        rows = rows.filter(key_id__icontains=keyword)

    result = Paginator(rows.order_by('-id').values(
        'id', 'node__node_id', 'algorithm', 'key_id', 'key_version',
        'status', 'revoked_at', 'revoked_reason', 'inspection__rule',
        'inspection__severity', 'inspection__action', 'inspection__detected_at',
        'inspection__batch_id', 'inspection__handled_by', 'inspection__handled_at',
        'inspection__disposition', 'inspection__disposition_note', 'inspection__action_at',
    ), size).get_page(page)
    data = [{
        'rowId': row['id'], 'nodeId': row['node__node_id'],
        'algorithm': row['algorithm'], 'keyId': row['key_id'],
        'keyVersion': row['key_version'], 'status': row['status'],
        'revokedAt': row['revoked_at'].isoformat() if row['revoked_at'] else None,
        'revokedReason': row['revoked_reason'],
        'rule': row['inspection__rule'], 'severity': row['inspection__severity'],
        'action': row['inspection__action'],
        'detectedAt': row['inspection__detected_at'].isoformat()
                      if row['inspection__detected_at'] else None,
        'batchId': row['inspection__batch_id'],
        'handledBy': row['inspection__handled_by'],
        'handledAt': row['inspection__handled_at'].isoformat() if row['inspection__handled_at'] else None,
        'actionAt': row['inspection__action_at'].isoformat() if row['inspection__action_at'] else None,
        'disposition': row['inspection__disposition'],
        'dispositionNote': row['inspection__disposition_note'],
    } for row in result.object_list]
    latest = NodeKeyAutoRevocationBatch.objects.order_by('-completed_at').first() if admin else None
    return JsonResponse({'code': 200, 'message': 'success', 'data': {
        'rows': data, 'total': result.paginator.count, 'page': result.number,
        'pageSize': size,
        'latestBatch': ({'batchId': latest.batch_id, 'keys': latest.key_count,
                         'poolItems': latest.pool_count, 'sessions': latest.session_count,
                         'elapsedMs': latest.elapsed_ms,
                         'keysPerSecond': round(latest.key_count * 1000 / latest.elapsed_ms, 1)}
                        if latest and latest.elapsed_ms else None),
    }})


def _admin(identity):
    try:
        return int(identity.get('roleLevel')) <= 0
    except (TypeError, ValueError):
        return False


def _failure(message, status):
    return JsonResponse({'code': status, 'message': message}, status=status)


@require_http_methods(['GET'])
@require_kms_user
def node_key_review_impact(request, row_id, identity):
    if not _admin(identity):
        return _failure('仅管理员可以预览影响面，请联系管理员处置', 403)
    key = NodeLongTermKey.objects.select_related('node').filter(pk=row_id).first()
    if key is None:
        return _failure('密钥记录不存在，请刷新列表', 404)
    inspection = NodeKeyInspection.objects.filter(key=key).first()
    return JsonResponse({'code': 200, 'message': 'success', 'data': {
        'key': {'rowId': key.pk, 'nodeId': key.node.node_id, 'keyId': key.key_id,
                'keyVersion': key.key_version, 'algorithm': key.algorithm,
                'status': key.status, 'publicKeyHash': key.public_key_hash,
                'revokedReason': key.revoked_reason},
        'inspection': inspection_payload(inspection) if inspection else None,
        'impact': key_impact(key, key.node),
    }})


@csrf_exempt
@require_http_methods(['POST'])
@require_kms_user
def node_key_review_action(request, row_id, operation, identity):
    if not _admin(identity):
        return _failure('仅管理员可以处置异常密钥，请联系管理员', 403)
    try:
        payload = json.loads(request.body or b'{}')
        if not isinstance(payload, dict) or not isinstance(payload.get('note', ''), str):
            return _failure('请求体应为 JSON 对象，note 应为文本', 400)
        note = payload.get('note', '').strip()
        if len(note) > 2000:
            return _failure('处置说明不能超过 2000 字', 400)
        if operation in ('dismiss', 'revoke') and not note:
            return _failure('忽略误报或人工回收必须填写原因', 400)
        source = NodeLongTermKey.objects.filter(pk=row_id).values('node_id').first()
        if source is None:
            return _failure('密钥记录不存在，请刷新列表', 404)
        with transaction.atomic():
            # rowId is NodeLongTermKey.pk, NEVER inspection.pk. Node lock first
            # serializes with registration, rotation and automatic severe scans.
            node = Node.objects.select_for_update().get(pk=source['node_id'])
            key = NodeLongTermKey.objects.select_for_update().get(pk=row_id, node=node)
            inspection = NodeKeyInspection.objects.select_for_update().filter(key=key).first()
            if inspection is None:
                return _failure('该密钥没有巡检记录，请先等待巡检', 404)
            result = handle_inspection(key, node, inspection, operation,
                                       identity['userId'], note)
            # Only a new revocation emits an event, after the outermost commit.
            # Dependency recovery/recheck never retries chain evidence.
            result['chainHash'] = ''
            revoked = result.get('revoked')
            if revoked and not revoked['alreadyRevoked']:
                def record_revocation():
                    result['chainHash'] = record_chain_event(
                        'KEY_REVOKED', int(revoked['rowId']), int(revoked['keyVersion']),
                        node.node_id, str(revoked['publicKeyHash'] or '')) or ''
                transaction.on_commit(record_revocation)
        status = 503 if result.get('partialFailure') else 200
        message = ('密钥已回收，但会话失效失败；未记录处置成功，请在待复核或回收记录中重试人工回收。'
                   + result['impact']['sessionMessage'] if status == 503 else 'success')
        return JsonResponse({'code': status, 'message': message, 'data': result}, status=status)
    except (ValueError, UnicodeDecodeError):
        return _failure('请求体不是有效 JSON', 400)
    except (Node.DoesNotExist, NodeLongTermKey.DoesNotExist):
        return _failure('节点或密钥已删除，请刷新列表', 404)
    except C.ContractError as exc:
        return _failure(exc.message, exc.http_status)
    except Exception:
        logger.exception('管理员异常密钥处置失败 rowId=%s operation=%s', row_id, operation)
        return _failure('处置失败，请刷新确认状态并联系管理员查看服务日志', 500)
