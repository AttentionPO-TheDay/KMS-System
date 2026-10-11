"""Administrator-only reads of chain configuration and public node key records."""
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from . import api_contract as C
from .chain_backend import chain_write_state, chain_writes_enabled
from .chain_binding_service import get_backend_status
from .models import ChainKeyBinding, NodeKeyAutoRevocationBatch, NodeLongTermKey
from .node_key_payloads import iso, long_term_key_payload
from .user_distribution_views import require_kms_user


def _admin(identity):
    try:
        return int(identity.get('roleLevel')) <= 0
    except (TypeError, ValueError):
        return False


def _error(message, status):
    return JsonResponse({'code': status, 'message': message}, status=status)


@require_http_methods(['GET'])
@require_kms_user
def chain_runtime_status(request, identity):
    if not _admin(identity):
        return _error('仅管理员可以查看链运行配置，请联系管理员', 403)

    # ENABLED is a write gate, not evidence of a connected blockchain network.
    data = get_backend_status()
    data['chainWriteState'] = chain_write_state()
    data.setdefault('writeEnabled', chain_writes_enabled())
    observed = dict(ChainKeyBinding.objects.order_by().values('status')
                    .annotate(count=Count('pk')).values_list('status', 'count'))
    counts = {state: 0 for state, _ in ChainKeyBinding.STATES}
    counts.update(observed)  # Unknown stored states are facts too, not silently discarded.
    data['bindingCounts'] = {
        'total': sum(observed.values()), 'byStatus': counts, 'observed': observed,
    }
    latest = NodeKeyAutoRevocationBatch.objects.order_by('-completed_at').first()
    data['latestBatch'] = ({
        'batchId': latest.batch_id,
        'startedAt': iso(latest.started_at), 'completedAt': iso(latest.completed_at),
        'keys': latest.key_count, 'poolItems': latest.pool_count,
        'sessions': latest.session_count, 'elapsedMs': latest.elapsed_ms,
        'keysPerSecond': (round(latest.key_count * 1000 / latest.elapsed_ms, 1)
                          if latest.elapsed_ms else None),
    } if latest else None)
    return JsonResponse({'code': 200, 'message': 'success', 'data': data})


@require_http_methods(['GET'])
@require_kms_user
def admin_node_long_term_keys(request, identity):
    if not _admin(identity):
        return _error('仅管理员可以查看全部节点长期密钥，请联系管理员', 403)
    try:
        page = max(1, min(int(request.GET.get('page', 1)), 1_000_000))
        size = max(1, min(int(request.GET.get('pageSize', 30)), 100))
    except (TypeError, ValueError):
        return _error('page 和 pageSize 应为整数', 400)
    algorithm = C.canonical_algorithm(request.GET.get('algorithm', ''))
    status = request.GET.get('status', '').strip().upper()
    node_id = request.GET.get('nodeId', '').strip()
    if algorithm and algorithm not in dict(NodeLongTermKey._meta.get_field('algorithm').choices):
        return _error('algorithm 只能为 SM2、SSCL、KYBER 或 FALCON', 400)
    if status and status not in dict(C.KEY_STATUS_CHOICES):
        return _error('status 不是有效的长期密钥状态', 400)
    if len(node_id) > 64:
        return _error('nodeId 不能超过 64 字', 400)

    # Restrict the join to node identifiers; never fetch Node's private-key columns.
    rows = NodeLongTermKey.objects.select_related('node').only(
        'id', 'node', 'algorithm', 'key_id', 'key_version', 'status',
        'public_key', 'public_key_hash', 'security_level', 'device_id',
        'effective_at', 'expires_at', 'revoked_at', 'revoked_reason',
        'legacy', 'legacy_source', 'create_datetime', 'update_datetime',
        'generation_scheme', 'generation_scheme_version', 'generation_issuance_id',
        'generation_authorization_ticket_id', 'generation_context',
        'node__id', 'node__node_id', 'node__name',
    )
    if algorithm:
        rows = rows.filter(algorithm=algorithm)
    if status:
        rows = rows.filter(status=status)
    if node_id:
        rows = rows.filter(node__node_id=node_id)
    result = Paginator(rows.order_by('-id'), size).get_page(page)
    data = [{**long_term_key_payload(key),
             'rowId': key.pk, 'nodeId': key.node.node_id,
             'nodeName': key.node.name, 'nodePk': key.node_id}
            for key in result.object_list]
    return JsonResponse({'code': 200, 'message': 'success', 'data': {
        'rows': data, 'total': result.paginator.count, 'page': result.number,
        'pageSize': size,
    }})
