# -*- coding: utf-8 -*-
"""安全监控总览（阶段 7 / 文档 §8.7）。

    GET /security-monitor/summary/

为什么放在分发模块（Django）而不是主 KMS
--------------------------------------
§8.7 列的七项里，有四项的数据源在此：节点（`dvadmin_pqkds_nodes`）、
预分配池项、会话、分发批次。主 KMS 要答这几项得跨库查或调这里，
不如由数据归属方直接汇总。

**但密钥的 ACTIVE / REVOKED 计数在 `kms.keymanage`** —— 那属于主 KMS。
本项目里 Django 用同一把 root 连接、同一个 MySQL 实例，因此可以只读地
跨 schema 统计。这属于**已知的越权读**：真要长期使用应当由主 KMS 提供
内部接口。此处如实标注，不假装边界是干净的。

设计取舍
-------
每项统计**各自 try/except**，不因一项失败让整个面板空白。
监控面板最怕的就是"某个数据源挂了 → 整页没有数字 → 运维以为系统全挂"。
失败的那一项返回 null 并由前端如实显示"不可用"，而不是显示 0 ——
0 是一个有效值，会让人误以为"确实没有"。
"""

from __future__ import annotations

import logging

from django.db import connection
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import DistributionBatch, Node, PreDistributedKey, SessionKey
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


def _kms_counts():
    """跨 schema 只读统计 kms.keymanage 的状态分布。

    ⚠️ 已知的越权读：这属于主 KMS 的数据。走同一实例的 root 连接只是
    工程上的便利，不是架构上的许可。失败时返回 None，不影响其它统计。
    """
    out = {}
    with connection.cursor() as cur:
        cur.execute(
            "SELECT status, COUNT(*) FROM kms.keymanage GROUP BY status"
        )
        for status, cnt in cur.fetchall():
            out[str(status)] = int(cnt)
    return out


@csrf_exempt
@require_http_methods(['GET'])
@require_kms_user
def security_summary(request, identity):
    """安全监控总览。管理员视角 —— 只做聚合统计，不返回任何密钥材料。"""
    active_keys = None
    revoked_keys = None
    try:
        counts = _safe(_kms_counts, 'kms.keymanage')
        if counts is not None:
            # KeyStatus：0=有效 1=冻结 2=轮换 3=回收
            active_keys = counts.get('0', 0)
            revoked_keys = counts.get('3', 0)
    except Exception as exc:  # noqa: BLE001
        logger.warning('读取密钥状态分布失败: %s', exc)

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
        'keys': None if active_keys is None else {
            'active': active_keys,
            'revoked': revoked_keys,
            'note': '跨 schema 只读统计，数据源为 kms.keymanage',
        },

        # ---- 预分配池（第 3 项）----
        'pool': _safe(lambda: {
            'ready': PreDistributedKey.objects.filter(
                status__in=['READY', 'unused']).count(),
            'reserved': PreDistributedKey.objects.filter(status='RESERVED').count(),
            'consumed': PreDistributedKey.objects.filter(
                status__in=['CONSUMED', 'used', 'distributed']).count(),
            'revoked': PreDistributedKey.objects.filter(status='REVOKED').count(),
            'expired': PreDistributedKey.objects.filter(
                status__in=['EXPIRED', 'expired']).count(),
        }, 'pool'),

        # ---- 会话（第 4 项）----
        'sessions': _safe(lambda: {
            'total': SessionKey.objects.count(),
            'initiated': SessionKey.objects.filter(status='initiated').count(),
            'established': SessionKey.objects.filter(status='established').count(),
            'expired': SessionKey.objects.filter(status='expired').count(),
            'revoked': SessionKey.objects.filter(status='revoked').count(),
        }, 'sessions'),

        # ---- 分发成功率（第 6 项）----
        'distribution': _safe(lambda: _distribution_stats(), 'distribution'),
    }

    # ---- 异常密钥数（第 5 项）----
    # 主 KMS 的健康检查是逐把密钥算的，这里做不了全量；
    # 能如实给出的是"结构上可判定的异常"：材料缺失、版本漂移的候选。
    payload['anomalies'] = _safe(lambda: _anomaly_counts(), 'anomalies')

    return JsonResponse({'code': 200, 'msg': 'OK', 'data': payload})


def _distribution_stats():
    total = DistributionBatch.objects.count()
    by_status = {}
    for s in ['success', 'partial', 'failed', 'pending']:
        by_status[s] = DistributionBatch.objects.filter(status=s).count()

    # 同上：统计"跨域分发"占比 —— 这是 §8.5 的标记在监控上的直接用途
    cross = DistributionBatch.objects.filter(distribution_type='cross').count()
    same = DistributionBatch.objects.filter(distribution_type='same').count()
    mixed = DistributionBatch.objects.filter(distribution_type='mixed').count()

    ok = by_status['success']
    return {
        'total': total,
        'byStatus': by_status,
        # 成功率以"成功 / 总数"计。分母为 0 时返回 None 而非 0 ——
        # 没有分发过，成功率是无定义的，给 0 会被读成"一次都没成功"。
        'successRate': (round(ok / total, 4) if total else None),
        'crossDomain': {'cross': cross, 'same': same, 'mixed': mixed},
    }


def _anomaly_counts():
    """结构上可判定的异常密钥数（全量健康检查需逐把跑，这里只做可判定的部分）。

    判据与 KeyHealthService 保持一致：
      * ua 或 key_value 为空 → 材料不完整
      * key_material_state = legacy_unusable → 早期密钥，设计如此不算故障，
        单列出来以免混进"异常"里吓人
    """
    out = {}
    with connection.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM kms.keymanage "
            "WHERE (ua IS NULL OR ua = '') OR (key_value IS NULL OR key_value = '')"
        )
        out['materialMissing'] = int(cur.fetchone()[0])

        cur.execute(
            "SELECT COUNT(*) FROM kms.keymanage WHERE key_material_state = %s",
            ['legacy_unusable'],
        )
        out['legacyUnusable'] = int(cur.fetchone()[0])

    out['note'] = ('materialMissing 属真实缺陷；legacyUnusable 是早期密钥的'
                   '已知情况（用户侧份额未持久化），列在此处仅为区分，不是故障')
    return out