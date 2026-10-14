"""Read-only diagnostics for the authenticated node's own long-term keys."""
import hashlib

from django.db.models import Count, Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from . import api_contract as C
from .models import Node, NodeLongTermKey, PreDistributedKey, SessionKey
from .user_distribution_views import require_kms_user


def _error(message, status):
    return JsonResponse({'code': status, 'message': message}, status=status)


def _resolve(request, identity):
    user_id = identity.get('userId')
    node = Node.objects.only('id', 'node_id', 'name', 'sys_user_id').filter(sys_user_id=user_id).first() if user_id is not None else None
    if node is None:
        return None, None, _error('当前账号未关联节点', 403)
    key_id = request.GET.get('keyId', '').strip()
    if not key_id or len(key_id) > 64:
        return None, None, _error('请输入有效的密钥ID', 400)
    rows = NodeLongTermKey.objects.filter(node=node, key_id=key_id)
    raw_version = request.GET.get('version', '')
    if raw_version:
        try:
            version = int(raw_version)
            if version < 1 or version > 2147483647:
                raise ValueError()
        except ValueError:
            return None, None, _error('版本须为正整数', 400)
        rows = rows.filter(key_version=version)
    if not rows.exists():
        return None, None, _error('未找到属于本节点的密钥或版本', 404)
    return node, rows, None


@require_http_methods(['GET'])
@require_kms_user
def node_key_health(request, identity):
    node, rows, error = _resolve(request, identity)
    if error is not None:
        return error
    key = rows.order_by('-key_version').first()
    findings = []
    observations = [f'节点 {node.node_id}', f'登记版本 v{key.key_version}', f'状态 {key.status}']
    public = key.public_key or ''
    if not public.strip():
        findings.append(dict(rule='PUBLIC_KEY_MISSING', severity='ERROR', message='登记公钥缺失', advice='在原设备核对密钥材料'))
    elif not key.public_key_hash or hashlib.sha256(public.encode('utf-8')).hexdigest().lower() != key.public_key_hash.lower():
        findings.append(dict(rule='PUBLIC_KEY_HASH_MISMATCH', severity='ERROR', message='公钥与登记摘要不一致', advice='请联系管理员复核登记记录'))
    else:
        observations.append('公钥摘要一致')
    if key.status == C.KEY_STATUS_ACTIVE:
        column = C.algorithm_column(key.algorithm)
        if column:
            mirror = Node.objects.filter(pk=node.pk).values_list(column, flat=True).first()
            if mirror != public:
                findings.append(dict(rule='MATERIALIZED_PUBLIC_KEY_MISMATCH', severity='WARN', message='生产公钥与登记公钥不一致', advice='请联系管理员复核生产版本'))
            else:
                observations.append('生产公钥与登记记录一致')
        if key.active_slot != key.algorithm:
            findings.append(dict(rule='CURRENT_SLOT_MISMATCH', severity='WARN', message='生产槽位与算法不一致', advice='请联系管理员复核生产槽位'))
        if key.expires_at and key.expires_at <= timezone.now():
            findings.append(dict(rule='KEY_EXPIRED', severity='WARN', message='密钥已到期', advice='请更新密钥'))
    unavailable = key.status in (C.KEY_STATUS_REVOKED, C.KEY_STATUS_EXPIRED)
    health = 'REVOKED' if unavailable else 'SUSPICIOUS' if findings else 'OK'
    return JsonResponse({'code': 200, 'data': dict(keyId=key.key_id, keyName=key.algorithm,
        version=key.key_version, status=key.status, health=health, findings=findings,
        observations=observations, publicKeyHash=key.public_key_hash)})


@require_http_methods(['GET'])
@require_kms_user
def node_key_analysis(request, identity):
    node, rows, error = _resolve(request, identity)
    if error is not None:
        return error
    key = rows.only('key_id', 'key_version', 'algorithm', 'status').order_by('-key_version').first()
    versions = list(rows.values_list('key_version', flat=True))
    pools = PreDistributedKey.objects.filter(Q(node1=node) | Q(node2=node),
        long_term_key_id=key.key_id, long_term_key_version__in=versions)
    sessions = SessionKey.objects.filter(Q(node1=node) | Q(node2=node)).filter(
        Q(recipient_key_id=key.key_id, recipient_key_version__in=versions)
        | Q(falcon_key_id=key.key_id, falcon_key_version__in=versions))
    footprints = pools.filter(recipient_type='node').order_by('-id').values(
        'pool_id', 'key_index', 'status', 'long_term_key_version', 'expires_at')
    ready = pools.filter(status__in=['READY', 'unused', 'RESERVED']).values('pool_id', 'status').annotate(item_count=Count('id')).order_by('pool_id')
    trails = sessions.order_by('-id').values('session_id', 'status', 'session_type',
        'recipient_key_version', 'falcon_key_version', 'node1__node_id', 'node2__node_id')
    node_ids = set()
    for a, b in pools.values_list('node1_id', 'node2_id'):
        node_ids.update([a, b])
    for a, b in sessions.values_list('node1_id', 'node2_id'):
        node_ids.update([a, b])
    affected = Node.objects.filter(pk__in=node_ids).exclude(pk=node.pk).values('node_id', 'name', 'permission_level', 'domain_id').order_by('node_id')
    counts = dict(footprints=footprints.count(), poolGroups=ready.count(), sessions=trails.count(), nodes=affected.count())
    return JsonResponse({'code': 200, 'data': dict(
        baseInfo=dict(keyId=key.key_id, keyName=key.algorithm, encrytName=key.algorithm,
                      version=key.key_version, status=key.status, userName=node.node_id),
        distributeFootprints=list(footprints[:200]), affectedPoolItems=list(ready[:200]),
        operationTrails=list(trails[:200]), affectedNodes=list(affected[:200]),
        counts=counts, truncated=any(count > 200 for count in counts.values()))})
