"""Admin-only paged metadata. No key material, decryption data or write actions."""
import logging
import os
from datetime import datetime, timedelta

from django.db import connection
from django.db.models import Count, Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import (ChainKeyBinding, DistributionBatch, KeyDistributionLog, Node,
                     NodeLongTermKey, PreDistributedKey, SessionKey)
from .security_monitor_views import _distribution_items, _node_distribution_items
from .user_distribution_views import require_kms_user

logger = logging.getLogger(__name__)


def iso(value):
    return value.isoformat() if hasattr(value, 'isoformat') else value


def pagination(params, total):
    size = min(100, max(1, int(params.get('pageSize', 20))))
    page = min(max(1, int(params.get('page', 1))), max(1, (total + size - 1) // size))
    return page, size, (page - 1) * size


def dates(params):
    result = []
    for name in ('from', 'to'):
        value = params.get(name, '')
        date = datetime.strptime(value, '%Y-%m-%d') if value else None
        if date and name == 'to':
            date += timedelta(days=1)
        if date and timezone.is_aware(timezone.now()):
            date = timezone.make_aware(date)
        result.append(date)
    return result


def filtered(rows, params, ids, nodes=(), algorithm=None):
    query = params.get('q', '').strip()
    node = params.get('node', '').strip()
    if len(query) > 128 or len(node) > 64:
        raise ValueError('筛选内容过长')
    if query:
        clause = Q()
        for field in ids:
            clause |= Q(**{field + '__icontains': query})
        rows = rows.filter(clause)
    if node and nodes:
        clause = Q()
        for field in nodes:
            clause |= Q(**{field + '__icontains': node})
        rows = rows.filter(clause)
    if params.get('status'):
        rows = rows.filter(status=params['status'])
    if params.get('algorithm') and algorithm:
        rows = rows.filter(**{algorithm: params['algorithm']})
    start, end = dates(params)
    if start:
        rows = rows.filter(create_datetime__gte=start)
    if end:
        rows = rows.filter(create_datetime__lt=end)
    return rows


def page_rows(rows, params):
    total = rows.count()
    page, size, offset = pagination(params, total)
    return rows.order_by('-create_datetime', '-id')[offset:offset + size], dict(
        total=total, page=page, pageSize=size)


def counts(rows):
    return {row['status']: row['count'] for row in rows.order_by().values('status').annotate(count=Count('pk'))}


def binding_payload(binding):
    if not binding:
        return dict(status='NOT_REGISTERED', transactionValid=False, metadataMatches=False)
    return dict(status=binding.status, txId=binding.tx_id, blockHeight=binding.block_height,
                transactionValid=binding.transaction_valid, metadataMatches=binding.metadata_matches,
                lastError=binding.last_error)


def node_keys(params):
    base = NodeLongTermKey.objects.all()
    statuses = counts(base)
    by_type = {row['algorithm']: row['count'] for row in base.order_by().values('algorithm').annotate(count=Count('pk'))}
    rows = filtered(base, params, ('key_id',), ('node__node_id',), 'algorithm')
    rows, page = page_rows(rows, params)
    # Explicit projection: do not load multi-megabyte public matrices or any node secret.
    records = list(rows.values('id', 'key_id', 'key_version', 'algorithm', 'status', 'security_level',
        'generation_scheme', 'node__node_id', 'effective_at', 'create_datetime', 'expires_at'))
    bindings = {}
    binding_rows = ChainKeyBinding.objects.filter(long_term_key_id__in=[r['id'] for r in records])
    contract = os.getenv('KMS_NODE_FISCO_CONTRACT_ADDRESS', '').strip().lower()
    if contract:
        binding_rows = binding_rows.filter(provider='FISCO', chain_id='fisco:group-1:' + contract)
    for binding in binding_rows.only('long_term_key', 'status', 'tx_id', 'block_height',
            'transaction_valid', 'metadata_matches', 'last_error').order_by('-id'):
        bindings.setdefault(binding.long_term_key_id, binding)
    items = [dict(rowId=r['id'], keyId=r['key_id'], nodeId=r['node__node_id'], algorithm=r['algorithm'],
        status=r['status'], version=r['key_version'], securityLevel=r['security_level'],
        generationScheme=r['generation_scheme'], createdAt=iso(r['create_datetime']),
        effectiveAt=iso(r['effective_at']), expiresAt=iso(r['expires_at']),
        chainBinding=binding_payload(bindings.get(r['id']))) for r in records]
    return dict(page, items=items, summary=dict(total=sum(statuses.values()), byStatus=statuses, byType=by_type),
                source='节点长期密钥版本记录，不含验收压测数据')


def pool_records(params):
    base = PreDistributedKey.objects.all()
    canonical = params.copy()
    selected_status, selected_algorithm = canonical.pop('status', ''), canonical.pop('algorithm', '')
    if isinstance(selected_status, list): selected_status = selected_status[0]
    if isinstance(selected_algorithm, list): selected_algorithm = selected_algorithm[0]
    rows = filtered(base, canonical, ('pool_id', 'long_term_key_id'), ('node1__node_id', 'node2__node_id'))
    if selected_status:
        aliases = {'READY': ['READY', 'unused'], 'CONSUMED': ['CONSUMED', 'used', 'distributed'], 'EXPIRED': ['EXPIRED', 'expired']}
        rows = rows.filter(status__in=aliases.get(selected_status, [selected_status]))
    if selected_algorithm:
        rows = rows.filter(Q(wrapping_algorithm=selected_algorithm) | Q(wrapping_algorithm='', algorithm=selected_algorithm))
    rows, page = page_rows(rows, params)
    fields = ('id', 'pool_id', 'key_index', 'node1__node_id', 'node2__node_id', 'wrapping_algorithm',
              'algorithm', 'payload_algorithm', 'status', 'long_term_key_id', 'long_term_key_version',
              'used_by_session__session_id', 'generation_time_ms', 'create_datetime', 'expires_at')
    items = [dict(rowId=r['id'], poolId=r['pool_id'], keyIndex=r['key_index'],
        sourceNode=r['node1__node_id'], targetNode=r['node2__node_id'],
        wrappingAlgorithm=r['wrapping_algorithm'] or r['algorithm'], payloadAlgorithm=r['payload_algorithm'],
        status=r['status'], longTermKeyId=r['long_term_key_id'], longTermKeyVersion=r['long_term_key_version'],
        sessionId=r['used_by_session__session_id'], generationTimeMs=r['generation_time_ms'],
        createdAt=iso(r['create_datetime']), expiresAt=iso(r['expires_at'])) for r in rows.values(*fields)]
    return dict(page, items=items, summary=dict(total=base.count(), byStatus=counts(base)),
                source='预分配保护包记录，不等于唯一密钥；不返回密文或解封材料')


def session_records(params):
    base = SessionKey.objects.all()
    rows = filtered(base, params, ('session_id',), ('node1__node_id', 'node2__node_id'), 'session_type')
    rows, page = page_rows(rows, params)
    fields = ('id', 'session_id', 'node1__node_id', 'node2__node_id', 'node1__domain_id',
              'node2__domain_id', 'session_type', 'status', 'create_datetime', 'expires_at')
    items = [dict(rowId=r['id'], sessionId=r['session_id'], sourceNode=r['node1__node_id'],
        targetNode=r['node2__node_id'], sourceDomain=r['node1__domain_id'], targetDomain=r['node2__domain_id'],
        sessionType=r['session_type'], status=r['status'], createdAt=iso(r['create_datetime']),
        expiresAt=iso(r['expires_at'])) for r in rows.values(*fields)]
    return dict(page, items=items, summary=dict(total=base.count(), byStatus=counts(base)),
                source='实际会话记录；已建立与已上链是不同状态')


def acceptance_records(params):
    # Same MySQL server, read-only cross-schema metadata. Dataset is always fenced by account AND domain.
    account = os.getenv('KMS_ACCEPTANCE_USER', 'acceptance_user')
    clauses, values = ['user_name = %s', 'key_domain = %s'], [account, 'acceptance']
    for name, column in (('status', 'status'), ('algorithm', 'encryt_name')):
        if params.get(name):
            clauses.append(column + ' = %s'); values.append(params[name])
    query = params.get('q', '').strip()
    if len(query) > 128:
        raise ValueError('筛选内容过长')
    if query:
        clauses.append('CAST(key_id AS CHAR) LIKE %s'); values.append('%' + query + '%')
    start, end = dates(params)
    for column, value in (('cre_time >= %s', start), ('cre_time < %s', end)):
        if value:
            clauses.append(column); values.append(value)
    where = ' AND '.join(clauses)
    with connection.cursor() as cursor:
        cursor.execute('SELECT status, COUNT(*) FROM kms.keymanage WHERE user_name = %s AND key_domain = %s GROUP BY status', [account, 'acceptance'])
        statuses = {str(status): count for status, count in cursor.fetchall()}
        cursor.execute('SELECT chain_status, COUNT(*) FROM kms.keymanage WHERE user_name = %s AND key_domain = %s GROUP BY chain_status', [account, 'acceptance'])
        chain_counts = {str(status): count for status, count in cursor.fetchall()}
        cursor.execute('SELECT COUNT(*) FROM kms.keymanage WHERE ' + where, values)
        total = cursor.fetchone()[0]
        page, size, offset = pagination(params, total)
        cursor.execute('SELECT key_id, user_name, encryt_name, key_name, version, status, chain_status, chain_hash, block_height, cre_time '
                       'FROM kms.keymanage WHERE ' + where + ' ORDER BY key_id DESC LIMIT %s OFFSET %s', values + [size, offset])
        items = [dict(keyId=str(r[0]), userName=r[1], algorithm=r[2], keyName=r[3], version=r[4], status=str(r[5]),
            chainStatus=str(r[6]), txId=r[7], blockHeight=r[8], createdAt=iso(r[9])) for r in cursor.fetchall()]
    return dict(items=items, total=total, page=page, pageSize=size,
                summary=dict(total=sum(statuses.values()), byStatus=statuses, chainCounts=chain_counts),
                account=account, source='kms.keymanage 验收专用记录，异步入库；不属于任何节点长期密钥')


def json_text(column, path):
    extracted = f"JSON_EXTRACT({column}, '{path}')"
    if connection.vendor == 'mysql':
        extracted = f'JSON_UNQUOTE({extracted})'
    return f"NULLIF(NULLIF(CASE WHEN JSON_VALID({column}) THEN {extracted} ELSE NULL END, ''), 'null')"


def distribution_query():
    """Group node audit logs in SQL, then UNION authoritative batches. No 100/500-row cap."""
    quote = connection.ops.quote_name
    batch, logs, nodes = (quote(m._meta.db_table) for m in (DistributionBatch, KeyDistributionLog, Node))
    ref = f"COALESCE({json_text('l.details', '$.batchId')}, {json_text('l.details', '$.batch_id')})"
    peer = f"COALESCE({json_text('l.details', '$.peerNodeCode')}, {json_text('l.details', '$.targetNodeCode')}, '')"
    same = "MAX(CASE WHEN COALESCE(t.domain_id, '') <> '' AND t.domain_id = n.domain_id THEN 1 ELSE 0 END)"
    cross = "MAX(CASE WHEN COALESCE(t.domain_id, '') <> '' AND t.domain_id <> COALESCE(n.domain_id, '') THEN 1 ELSE 0 END)"
    return f"""SELECT batch_id AS batchId, create_datetime AS createdAt, status,
        distribution_type AS distributionType, 'batch' AS sourceKind
        FROM {batch}
        UNION ALL
        SELECT {ref} AS batchId, MAX(COALESCE(l.timestamp, l.create_datetime)) AS createdAt,
        CASE WHEN SUM(CASE WHEN l.success THEN 1 ELSE 0 END) = COUNT(*) THEN 'success'
             WHEN SUM(CASE WHEN l.success THEN 1 ELSE 0 END) = 0 THEN 'failed' ELSE 'partial' END AS status,
        CASE WHEN {same} = 1 AND {cross} = 1 THEN 'mixed' WHEN {cross} = 1 THEN 'cross' ELSE 'same' END AS distributionType,
        'audit' AS sourceKind
        FROM {logs} l LEFT JOIN {nodes} n ON n.id = l.node_id LEFT JOIN {nodes} t ON t.node_id = {peer}
        WHERE l.action = 'pool_consume' AND COALESCE({ref}, '') <> ''
          AND NOT EXISTS (SELECT 1 FROM {batch} b WHERE b.batch_id = {ref})
        GROUP BY {ref}"""


def distribution_records(params):
    sql = distribution_query()
    clauses, values = [], []
    for name, column in (('status', 'status'), ('range', 'distributionType')):
        if params.get(name):
            clauses.append(column + ' = %s'); values.append(params[name])
    for name, column in (('q', 'batchId'), ('node', None)):
        value = params.get(name, '').strip()
        if len(value) > 128:
            raise ValueError('筛选内容过长')
        if value:
            if name == 'node':
                quote = connection.ops.quote_name
                logs, nodes = (quote(m._meta.db_table) for m in (KeyDistributionLog, Node))
                ref = f"COALESCE({json_text('f.details', '$.batchId')}, {json_text('f.details', '$.batch_id')})"
                peer = f"COALESCE({json_text('f.details', '$.peerNodeCode')}, {json_text('f.details', '$.targetNodeCode')}, '')"
                # EXISTS never truncates receiver lists (unlike MySQL GROUP_CONCAT).
                clauses.append(f"(sourceKind = 'audit' AND EXISTS (SELECT 1 FROM {logs} f LEFT JOIN {nodes} fn ON fn.id = f.node_id WHERE f.action = 'pool_consume' AND {ref} = u.batchId AND (fn.node_id LIKE %s OR {peer} LIKE %s)))")
                values.extend(['%' + value + '%'] * 2)
            else:
                clauses.append(column + ' LIKE %s'); values.append('%' + value + '%')
    start, end = dates(params)
    if start:
        clauses.append('createdAt >= %s'); values.append(start)
    if end:
        clauses.append('createdAt < %s'); values.append(end)
    where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
    with connection.cursor() as cursor:
        cursor.execute('SELECT status, distributionType, COUNT(*) FROM (' + sql + ') u GROUP BY status, distributionType')
        grouped = cursor.fetchall()
        cursor.execute('SELECT COUNT(*) FROM (' + sql + ') u' + where, values)
        total = cursor.fetchone()[0]
        page, size, offset = pagination(params, total)
        cursor.execute('SELECT batchId, createdAt, status, distributionType, sourceKind FROM (' + sql + ') u' + where +
                       ' ORDER BY createdAt DESC, batchId DESC LIMIT %s OFFSET %s', values + [size, offset])
        selected = cursor.fetchall()
    ids = [r[0] for r in selected]
    details = _distribution_items(queryset=DistributionBatch.objects.filter(batch_id__in=ids))
    ref_sql = f"COALESCE({json_text('details', '$.batchId')}, {json_text('details', '$.batch_id')})"
    log_rows = KeyDistributionLog.objects.filter(action='pool_consume').extra(
        where=[ref_sql + ' IN (' + ','.join(['%s'] * len(ids)) + ')'], params=ids) if ids else KeyDistributionLog.objects.none()
    seen = {r['batchId'] for r in details}
    details.extend(r for r in _node_distribution_items(queryset=log_rows) if r['batchId'] not in seen)
    by_id = {r['batchId']: r for r in details}
    items = [dict(by_id.get(r[0], {}), batchId=r[0], createdAt=iso(r[1]), status=r[2],
                  distributionType=r[3], sourceKind=r[4]) for r in selected]
    statuses, ranges = {}, {}
    for status, scope, count in grouped:
        statuses[status] = statuses.get(status, 0) + count
        ranges[scope] = ranges.get(scope, 0) + count
    return dict(items=items, total=total, page=page, pageSize=size,
        summary=dict(total=sum(statuses.values()), byStatus=statuses, byRange=ranges),
        source='实际分发批次与节点取用审计合并，按批次 ID 去重；不返回密钥材料')


READERS = dict(keys=node_keys, pool=pool_records, sessions=session_records,
               distribution=distribution_records, acceptance=acceptance_records)


@require_http_methods(['GET'])
@require_kms_user
def admin_data_records(request, identity):
    try:
        admin = identity.get('principalType') == 'ADMIN' and int(identity.get('roleLevel')) <= 0
    except (TypeError, ValueError):
        admin = False
    if not admin:
        return JsonResponse(dict(code=403, msg='需要管理员权限', data=None), status=403)
    section = request.GET.get('section', '')
    if section not in READERS:
        return JsonResponse(dict(code=400, msg='无效的数据分类', data=None), status=400)
    try:
        pagination(request.GET, 0)
        dates(request.GET)
        data = READERS[section](request.GET)
    except ValueError:
        return JsonResponse(dict(code=400, msg='筛选参数无效，请检查页码、日期和搜索内容', data=None), status=400)
    except Exception as error:
        logger.warning('Admin metadata source unavailable: section=%s type=%s', section, type(error).__name__)
        return JsonResponse(dict(code=503, msg='数据源暂时不可用，请刷新重试', data=None), status=503)
    return JsonResponse(dict(code=200, msg='OK', data=data))
