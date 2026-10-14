# -*- coding: utf-8 -*-
"""安全监控总览（阶段 7 / 文档 §8.7）。

    GET /security-monitor/summary/

为什么放在分发模块（Django）而不是主 KMS
--------------------------------------
§8.7 列的七项里，有四项的数据源在此：节点（`dvadmin_pqkds_nodes`）、
预分配池项、会话、分发批次。主 KMS 要答这几项得跨库查或调这里，
不如由数据归属方直接汇总。

节点长期密钥、预分配池项、会话与分发批次都属于当前节点业务模型，统一从
Django 所属数据表读取。旧 `kms.keymanage` 是用户腿遗留模型，不应混入管理端
节点密钥统计。

设计取舍
-------
每项统计**各自 try/except**，不因一项失败让整个面板空白。
监控面板最怕的就是"某个数据源挂了 → 整页没有数字 → 运维以为系统全挂"。
失败的那一项返回 null 并由前端如实显示"不可用"，而不是显示 0 ——
0 是一个有效值，会让人误以为"确实没有"。
"""

from __future__ import annotations

import json
import logging

from django.db.models import Count
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import (
    DistributionBatch, KeyDistributionLog, Node, NodeLongTermKey,
    PreDistributedKey, SessionKey,
)
from .node_permission import LEVEL_LABELS
from .user_distribution_views import require_kms_user

logger = logging.getLogger(__name__)


def _safe(fn, label):
    """跑一项统计；失败返回 None 并记日志。

    返回 None 而非 0 是刻意的：0 是有效值，会被读成"确实没有"。
    None 会被前端显示成"不可用"，如实反映"这项没测到"。
    """
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        logger.warning('监控统计项 %s 失败: %s', label, exc)
        return None


def _key_counts():
    """统计当前节点长期密钥；只返回可审计元数据，不返回公钥或生成上下文。"""
    statuses = ['PENDING', 'ACTIVE', 'RETIRED', 'REVOKED', 'EXPIRED', 'LEGACY']
    by_status = {status: 0 for status in statuses}
    for row in NodeLongTermKey.objects.values('status').annotate(count=Count('id')):
        by_status[row['status'] or 'UNKNOWN'] = row['count']

    by_type = {
        row['algorithm'] or 'UNKNOWN': row['count']
        for row in NodeLongTermKey.objects.values('algorithm').annotate(count=Count('id'))
    }
    rows = (NodeLongTermKey.objects.select_related('node')
            .order_by('-create_datetime')[:200])
    items = [{
        'keyId': row.key_id,
        'nodeId': row.node.node_id if row.node_id else '',
        'algorithm': row.algorithm or '',
        'status': row.status or '',
        'version': row.key_version,
        'securityLevel': row.security_level or '',
        'activeSlot': row.active_slot or '',
        'generationScheme': row.generation_scheme or '',
        'effectiveAt': row.effective_at.isoformat() if row.effective_at else None,
        'expiresAt': row.expires_at.isoformat() if row.expires_at else None,
        'createdAt': row.create_datetime.isoformat() if row.create_datetime else None,
    } for row in rows]
    return {
        'total': NodeLongTermKey.objects.count(),
        'byStatus': by_status,
        'byType': by_type,
        'active': by_status['ACTIVE'],
        'pending': by_status['PENDING'],
        'retired': by_status['RETIRED'],
        'revoked': by_status['REVOKED'],
        'expired': by_status['EXPIRED'],
        'legacy': by_status['LEGACY'],
        'items': items,
        'note': '当前节点长期密钥记录；仅展示标识、算法、版本、状态和时间等只读元数据',
    }


@csrf_exempt
@require_http_methods(['GET'])
@require_kms_user
def security_summary(request, identity):
    """安全监控总览。管理员视角 —— 只做聚合统计，不返回任何密钥材料。"""
    # require_kms_user resolves authority, but is not itself an admin gate.
    try:
        admin = identity.get('principalType') == 'ADMIN' and int(identity['roleLevel']) <= 0
    except (KeyError, TypeError, ValueError):
        admin = False
    if not admin:
        return JsonResponse({'code': 403, 'msg': '需要管理员权限', 'data': None}, status=403)

    payload = {
        # ---- 节点（文档 §8.7 第 1 项）----
        'nodes': _safe(lambda: {
            'total': Node.objects.count(),
            'active': Node.objects.filter(status='active').count(),
            'pendingInit': Node.objects.filter(status='PENDING_INIT').count(),
            'disabled': Node.objects.filter(status__in=['inactive', 'disabled']).count(),
            # 多级授权分布 —— 让"谁有 L3"一眼可见
            'byLevel': {
                lvl: Node.objects.filter(permission_level=lvl).count()
                for lvl in LEVEL_LABELS
            },
            'byDomain': _safe(lambda: {
                d: Node.objects.filter(domain_id=d).count()
                for d in Node.objects.values_list('domain_id', flat=True).distinct()
                if d
            }, 'nodes.byDomain'),
        }, 'nodes'),

        # ---- 密钥（第 2 项）----
        'keys': _safe(_key_counts, 'node long-term keys'),

        # ---- 预分配池（第 3 项）----
        'pool': _safe(lambda: _pool_summary(request.GET), 'pool'),

        # ---- 会话（第 4 项）----
        'sessions': _safe(lambda: {
            'total': SessionKey.objects.count(),
            'initiated': SessionKey.objects.filter(status='initiated').count(),
            'established': SessionKey.objects.filter(status='established').count(),
            'expired': SessionKey.objects.filter(status='expired').count(),
            'revoked': SessionKey.objects.filter(status='revoked').count(),
            'items': _session_items(),
        }, 'sessions'),

        # ---- 分发成功率（第 6 项）----
        'distribution': _safe(lambda: _distribution_stats(), 'distribution'),
    }

    return JsonResponse({'code': 200, 'msg': 'OK', 'data': payload})


def _distribution_stats():
    # 新节点到节点分发的真实批次首先落在 pool_consume 审计日志与 SessionKey；
    # 旧用户腿/未来统一服务则写 DistributionBatch。两种来源合并并按 batchId 去重。
    items = _distribution_items()
    seen = {item['batchId'] for item in items}
    items.extend(item for item in _node_distribution_items() if item['batchId'] not in seen)

    total = len(items)
    by_status = {
        status: sum(1 for item in items if item.get('status') == status)
        for status in ['success', 'partial', 'failed', 'pending']
    }
    cross = sum(1 for item in items if item.get('distributionType') == 'cross')
    same = sum(1 for item in items if item.get('distributionType') == 'same')
    mixed = sum(1 for item in items if item.get('distributionType') == 'mixed')
    ok = by_status['success']
    return {
        'total': total,
        'byStatus': by_status,
        # 成功率以"成功 / 总数"计。分母为 0 时返回 None 而非 0 ——
        # 没有分发过，成功率是无定义的，给 0 会被读成"一次都没成功"。
        'successRate': (round(ok / total, 4) if total else None),
        'crossDomain': {'cross': cross, 'same': same, 'mixed': mixed},
        'items': items,
        'crossDomainItems': [item for item in items
                             if item.get('distributionType') in ('cross', 'mixed')],
    }


def _session_items(limit=100):
    """管理员只读会话摘要，不返回密文、密钥或内部令牌。"""
    rows = SessionKey.objects.select_related('node1', 'node2').order_by('-create_datetime')[:limit]
    return [{
        'sessionId': row.session_id,
        'sourceNode': row.node1.node_id if row.node1_id else '',
        'targetNode': row.node2.node_id if row.node2_id else '',
        'sourceDomain': row.node1.domain_id if row.node1_id else '',
        'targetDomain': row.node2.domain_id if row.node2_id else '',
        'sessionType': row.session_type or '',
        'status': row.status or '',
        'createdAt': row.create_datetime.isoformat() if row.create_datetime else None,
        'expiresAt': row.expires_at.isoformat() if row.expires_at else None,
    } for row in rows]


def _pool_summary(params):
    def positive_int(name, default):
        try:
            return max(1, int(params.get(name, default)))
        except (TypeError, ValueError):
            return default

    page_size = min(100, positive_int('poolPageSize', 10))
    total = PreDistributedKey.objects.count()
    page = min(positive_int('poolPage', 1), max(1, (total + page_size - 1) // page_size))
    return {
        'total': total,
        'page': page,
        'pageSize': page_size,
        'ready': PreDistributedKey.objects.filter(status__in=['READY', 'unused']).count(),
        'reserved': PreDistributedKey.objects.filter(status='RESERVED').count(),
        'consumed': PreDistributedKey.objects.filter(
            status__in=['CONSUMED', 'used', 'distributed']).count(),
        'revoked': PreDistributedKey.objects.filter(status='REVOKED').count(),
        'expired': PreDistributedKey.objects.filter(status__in=['EXPIRED', 'expired']).count(),
        'items': _pool_items(page, page_size),
    }


def _pool_items(page=1, page_size=10):
    """管理员只读池项摘要，不返回密文、哈希或任何可解封材料。"""
    rows = (PreDistributedKey.objects
            .select_related('node1', 'node2', 'used_by_session')
            .order_by('-create_datetime', '-id')[(page - 1) * page_size:page * page_size])
    return [{
        'id': row.pk,
        'poolId': row.pool_id,
        'keyIndex': row.key_index,
        'sourceNode': row.node1.node_id if row.node1_id else '',
        'targetNode': row.node2.node_id if row.node2_id else '',
        'wrappingAlgorithm': row.wrapping_algorithm or row.algorithm or '',
        'payloadAlgorithm': row.payload_algorithm or '',
        'recipientType': row.recipient_type or '',
        'status': row.status or '',
        'longTermKeyId': row.long_term_key_id or '',
        'longTermKeyVersion': row.long_term_key_version,
        'sessionId': row.used_by_session.session_id if row.used_by_session_id else '',
        'generationTimeMs': row.generation_time_ms,
        'createdAt': row.create_datetime.isoformat() if row.create_datetime else None,
        'expiresAt': row.expires_at.isoformat() if row.expires_at else None,
    } for row in rows]


def _distribution_items(limit=100, cross_only=False, queryset=None):
    """管理员只读分发摘要，严格排除 node_ids、密文和可执行字段。"""
    supplied = queryset is not None
    queryset = queryset if supplied else DistributionBatch.objects.order_by('-create_datetime')
    if cross_only:
        queryset = queryset.filter(distribution_type__in=['cross', 'mixed'])
    rows = (queryset if supplied else queryset[:limit]).only('batch_id', 'status', 'distribution_type',
        'source_domain_id', 'target_domain_ids', 'node_success_count', 'user_envelope_ok', 'wrapping_algorithm', 'create_datetime')
    items = []
    for row in rows:
        try:
            target_domains = json.loads(row.target_domain_ids or '[]')
        except (TypeError, ValueError):
            target_domains = []
        items.append({
            'batchId': row.batch_id,
            'status': row.status or '',
            'distributionType': row.distribution_type or '',
            'sourceNode': '',
            'receiverNode': '',
            'wrappingAlgorithm': row.wrapping_algorithm or '',
            'sessionStatus': '',
            'sourceDomain': row.source_domain_id or '',
            'targetDomains': [str(value) for value in target_domains if value][:12],
            'nodeSuccessCount': row.node_success_count,
            'userEnvelopeOk': bool(row.user_envelope_ok),
            'createdAt': row.create_datetime.isoformat() if row.create_datetime else None,
        })
    return items


def _node_distribution_items(limit=500, queryset=None):
    """从节点分发审计日志恢复管理员批次摘要，并用 SessionKey 补充会话状态。

    `pool_consume.details.batchId` 是节点提交时签名覆盖的分发批次号；
    `SessionKey.key_exchange_data.batch_id` 在历史实现中存的是池批次号，不能替代它。
    响应只含审计元数据，不返回 details 中的 keyHash、链上原文或任何密钥材料。
    """
    logs = list(queryset.select_related('node').only('id', 'node', 'details', 'timestamp', 'create_datetime',
        'success', 'node__id', 'node__node_id', 'node__domain_id').order_by('-create_datetime', '-id') if queryset is not None else
        KeyDistributionLog.objects
        .filter(action='pool_consume')
        .select_related('node')
        .order_by('-create_datetime', '-id')[:limit]
    )
    parsed = []
    session_ids = set()
    target_codes = set()
    for log in logs:
        try:
            details = json.loads(log.details or '{}')
        except (TypeError, ValueError):
            details = {}
        if not isinstance(details, dict):
            details = {}
        session_id = str(details.get('sessionId') or '')
        target_code = str(details.get('peerNodeCode') or details.get('targetNodeCode') or '')
        if session_id:
            session_ids.add(session_id)
        if target_code:
            target_codes.add(target_code)
        parsed.append((log, details, session_id, target_code))

    sessions = {
        row.session_id: row
        for row in SessionKey.objects.filter(session_id__in=session_ids).only('session_id', 'status', 'session_type')
    }
    targets = {
        row.node_id: row
        for row in Node.objects.filter(node_id__in=target_codes).only('node_id', 'domain_id')
    }

    grouped = {}
    for log, details, session_id, target_code in parsed:
        batch_id = str(details.get('batchId') or details.get('batch_id') or '')
        if not batch_id:
            continue
        source = log.node
        target = targets.get(target_code)
        session = sessions.get(session_id)
        row = grouped.get(batch_id)
        if row is None:
            row = {
                'batchId': batch_id,
                'sourceNode': source.node_id if source else '',
                'receiverNodeIds': [],
                'wrappingAlgorithms': [],
                'sessionStatuses': [],
                'sourceDomain': source.domain_id if source else '',
                'targetDomains': [],
                'createdAt': ((log.timestamp or log.create_datetime).isoformat()
                              if (log.timestamp or log.create_datetime) else None),
                'attemptCount': 0,
                'nodeSuccessCount': 0,
            }
            grouped[batch_id] = row

        row['attemptCount'] += 1
        if log.success:
            row['nodeSuccessCount'] += 1
        if target_code and target_code not in row['receiverNodeIds']:
            row['receiverNodeIds'].append(target_code)
        target_domain = target.domain_id if target else ''
        if target_domain and target_domain not in row['targetDomains']:
            row['targetDomains'].append(target_domain)
        algorithm = str(details.get('algorithm') or (session.session_type if session else '') or '')
        if algorithm and algorithm not in row['wrappingAlgorithms']:
            row['wrappingAlgorithms'].append(algorithm)
        session_status = session.status if session else ''
        if session_status and session_status not in row['sessionStatuses']:
            row['sessionStatuses'].append(session_status)

    items = []
    for row in grouped.values():
        successes = row['nodeSuccessCount']
        attempts = row.pop('attemptCount')
        source_domain = row.get('sourceDomain') or ''
        target_domains = row.get('targetDomains') or []
        same_count = sum(1 for domain in target_domains if domain == source_domain)
        cross_count = sum(1 for domain in target_domains if domain != source_domain)
        row['status'] = ('success' if attempts and successes == attempts
                         else 'failed' if successes == 0 else 'partial')
        row['distributionType'] = ('mixed' if same_count and cross_count
                                   else 'cross' if cross_count else 'same')
        row['receiverNode'] = ', '.join(row.pop('receiverNodeIds'))
        row['wrappingAlgorithm'] = ', '.join(row.pop('wrappingAlgorithms'))
        statuses = row.pop('sessionStatuses')
        row['sessionStatus'] = statuses[0] if len(statuses) == 1 else ('mixed' if statuses else '')
        row['nodeCount'] = attempts
        row['userEnvelopeOk'] = False
        items.append(row)
    return items
