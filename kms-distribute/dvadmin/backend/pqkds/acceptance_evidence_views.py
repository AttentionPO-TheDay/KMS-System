# -*- coding: utf-8 -*-
"""节点预分配验收证据的可信写入与内部只读出口。"""

from __future__ import annotations

import json
import math

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .internal_pool_views import _internal_token_ok
from .models import AcceptancePreallocationEvidence, Node, PreDistributedKey
from .user_distribution_views import require_kms_user


_ALLOWED_FIELDS = {'poolId', 'targetNodeCode', 'requested', 'localMs', 'serverMs'}


def _response(data=None, *, code=200, msg='OK', status=200):
    return JsonResponse({'code': code, 'msg': msg, 'data': data}, status=status)


def _as_finite_number(value, field, *, minimum=0.0, maximum=3_600_000.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'{field} 必须是数字')
    if not math.isfinite(number) or number < minimum or number > maximum:
        raise ValueError(f'{field} 超出允许范围')
    return number


def _serialize(row):
    return {
        'id': f'node-preallocation-{row.id}',
        'criterionId': 'preallocation',
        'value': row.local_throughput,
        'unit': '条/秒',
        'operator': '>',
        'target': 50,
        'passed': row.local_throughput > 50,
        'verified': True,
        'source': 'node-measured',
        'evidence': (
            f'{row.node.node_id} 向 {row.target_node.node_id} 预分配，'
            f'池 {row.pool_id}，成功 {row.generated}/{row.requested} 条'
        ),
        'measuredAt': row.measured_at.isoformat(),
        'recordedAt': row.updated_at.isoformat(),
        'nodeCode': row.node.node_id,
        'nodeName': row.node.name,
        'targetNodeCode': row.target_node.node_id,
        'poolId': row.pool_id,
        'requested': row.requested,
        'generated': row.generated,
        'failed': row.failed,
        'localMs': round(row.local_ms, 2),
        'localThroughput': round(row.local_throughput, 3),
        'serverMs': round(row.server_ms, 2),
        'serverThroughput': round(row.server_throughput, 3),
    }


@csrf_exempt
@require_http_methods(['POST'])
@require_kms_user
def node_preallocation_evidence(request, identity):
    """接收当前登录节点的本机计时，服务端复核池归属与成功条数。"""
    node = Node.objects.filter(sys_user_id=identity.get('userId')).first()
    if node is None:
        return _response(code=403, msg='当前账号未关联节点', status=403)
    try:
        payload = json.loads(request.body or b'{}')
    except (TypeError, ValueError):
        return _response(code=400, msg='请求体不是合法 JSON', status=400)
    if not isinstance(payload, dict) or set(payload) - _ALLOWED_FIELDS:
        return _response(code=400, msg='只接受预分配计时字段，不接受 nodeId、密钥或命令字段', status=400)

    pool_id = str(payload.get('poolId') or '').strip()
    target_code = str(payload.get('targetNodeCode') or '').strip()
    if not pool_id or not target_code:
        return _response(code=400, msg='poolId 与 targetNodeCode 必填', status=400)
    target = Node.objects.filter(node_id=target_code).first()
    if target is None:
        return _response(code=404, msg='目标节点不存在', status=404)
    try:
        requested = int(payload.get('requested'))
        local_ms = _as_finite_number(payload.get('localMs'), 'localMs', minimum=0.001)
        server_ms = _as_finite_number(payload.get('serverMs', 0), 'serverMs')
    except (TypeError, ValueError) as exc:
        return _response(code=400, msg=str(exc), status=400)
    if requested < 1 or requested > 1000:
        return _response(code=400, msg='requested 必须在 1 到 1000 之间', status=400)

    generated = PreDistributedKey.objects.filter(
        pool_id=pool_id, node2=node, node1=target,
    ).count()
    if generated < 1:
        return _response(code=409, msg='未找到属于当前节点和目标节点的已入池记录', status=409)
    if generated > requested:
        return _response(code=409, msg='服务端池条数超过节点上报的请求数，拒绝记录不一致证据', status=409)

    local_throughput = generated / (local_ms / 1000.0)
    server_throughput = generated / (server_ms / 1000.0) if server_ms > 0 else 0
    row, _ = AcceptancePreallocationEvidence.objects.update_or_create(
        pool_id=pool_id,
        defaults={
            'node': node,
            'target_node': target,
            'requested': requested,
            'generated': generated,
            'failed': requested - generated,
            'local_ms': local_ms,
            'local_throughput': local_throughput,
            'server_ms': server_ms,
            'server_throughput': server_throughput,
            'measured_at': timezone.now(),
        },
    )
    return _response(_serialize(row), msg='预分配验收证据已记录')


@require_http_methods(['GET'])
def internal_preallocation_evidence(request):
    """仅供验收后端读取，浏览器和节点端都不能直接调用。"""
    if not _internal_token_ok(request):
        return _response(code=401, msg='内部令牌无效', status=401)
    rows = AcceptancePreallocationEvidence.objects.select_related('node', 'target_node').all()[:200]
    return _response([_serialize(row) for row in rows])
