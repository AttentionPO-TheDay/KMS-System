"""Exercise the production health scanner against real, connection-local fixtures.

MySQL temporary tables shadow the fixed production table names on this connection
only. All tables touched by scan_once (including its chain outbox) are shadowed
before any fixture write; closing the connection is the final cleanup fence.
"""
from contextlib import contextmanager
from datetime import timedelta
import hashlib
import time
import uuid

from django.db import connection
from django.utils import timezone

from . import api_contract as C
from .auto_revoke_service import BATCH_LIMIT, inspect_key, scan_once
from .models import (Node, NodeLongTermKey, PreDistributedKey, SessionKey,
                     SessionKeyInvalidation, NodeKeyInspection,
                     NodeKeyAutoRevocationBatch, ChainKeyBinding)

MODELS = (Node, NodeLongTermKey, PreDistributedKey, SessionKey,
          SessionKeyInvalidation, NodeKeyInspection,
          NodeKeyAutoRevocationBatch, ChainKeyBinding)
RULES = ('PUBLIC_KEY_MISSING', 'PUBLIC_KEY_HASH_MISSING', 'PUBLIC_KEY_HASH_MISMATCH')
ALGORITHMS = ('KYBER', 'SM2', 'SSCL', 'FALCON')
SAMPLE_COUNT = 6000


@contextmanager
def isolated_tables(models=MODELS):
    if connection.vendor != 'mysql' or connection.in_atomic_block:
        raise RuntimeError('异常回收验收需要独立的 MySQL 自动提交连接')
    connection.close()
    created = []
    try:
        with connection.cursor() as cursor:
            for model in models:
                table = connection.ops.quote_name(model._meta.db_table)
                # MySQL rejects CREATE TEMPORARY t LIKE t (1066). Reuse its
                # canonical DDL, retaining indexes/defaults but omitting FKs:
                # temporary InnoDB tables do not support foreign keys.
                cursor.execute(f'SHOW CREATE TABLE {table}')
                ddl = cursor.fetchone()[1]
                ddl = '\n'.join(line for line in ddl.splitlines() if ' FOREIGN KEY ' not in line)
                ddl = ddl.replace(',\n)', '\n)').replace('CREATE TABLE ', 'CREATE TEMPORARY TABLE ', 1)
                cursor.execute(ddl)
                created.append(table)
        yield
    finally:
        # DROP TEMPORARY can never drop a persistent table, even after a failure.
        try:
            with connection.cursor() as cursor:
                for table in reversed(created):
                    cursor.execute(f'DROP TEMPORARY TABLE IF EXISTS {table}')
                for table in ('kms_auto_revoke_candidates', 'kms_auto_revoke_sessions'):
                    cursor.execute(f'DROP TEMPORARY TABLE IF EXISTS {table}')
        finally:
            connection.close()


def create_fixture(count):
    tag = uuid.uuid4().hex
    nodes = [Node(node_id=f'accrevoke-{tag}-{i}', name='异常回收验收',
                  ip_address='127.0.0.1', port=0, status='ACTIVE')
             for i in range((count + 3) // 4 + 1)]
    Node.objects.bulk_create(nodes, batch_size=500)
    # MySQL does not return bulk-created primary keys on every supported version.
    nodes = list(Node.objects.order_by('pk'))
    keys, expected = [], {}
    for i in range(count + 4):
        algorithm = ALGORITHMS[i % 4] if i < count else ALGORITHMS[i - count]
        node = nodes[i // 4] if i < count else nodes[-1]
        public = f'acceptance-public-metadata-{tag}-{i}'
        digest = hashlib.sha256(public.encode()).hexdigest()
        rule = RULES[i % 3] if i < count else ('MATERIALIZED_PUBLIC_KEY_MISMATCH' if i == count + 3 else '')
        if rule == 'PUBLIC_KEY_MISSING':
            public = ''
        elif rule == 'PUBLIC_KEY_HASH_MISSING':
            digest = ''
        elif rule == 'PUBLIC_KEY_HASH_MISMATCH':
            digest = '0' * 64
        setattr(node, C.algorithm_column(algorithm), 'different-public-metadata' if i == count + 3 else public)
        key_id = f'accrevoke-{tag}-{i}'
        expected[key_id] = rule
        keys.append(NodeLongTermKey(node=node, algorithm=algorithm, key_id=key_id,
                    key_version=1, status='ACTIVE', active_slot=algorithm,
                    public_key=public, public_key_hash=digest))
    Node.objects.bulk_update(nodes, ['kyber_public_key', 'gm_public_key',
                                   'sscl_public_key', 'falcon_sign_public_key'], batch_size=500)
    NodeLongTermKey.objects.bulk_create(keys, batch_size=500)
    keys = list(NodeLongTermKey.objects.select_related('node').order_by('pk'))
    now = timezone.now()
    pools, sessions = [], []
    # Each fixture has one dependent pool item and one session, including controls.
    for i, key in enumerate(keys):
        wrapping = {'KYBER': 'kyber_kem', 'SM2': 'gm_sm2', 'SSCL': 'gm_sscl', 'FALCON': 'aes_falcon'}[key.algorithm]
        pools.append(PreDistributedKey(pool_id=f'accrevoke-{tag}', key_index=i,
            node1=key.node, node2=key.node, algorithm=wrapping, wrapping_algorithm=wrapping,
            long_term_key_id=key.key_id, long_term_key_version=1, status='READY',
            expires_at=now + timedelta(hours=1)))
        references = dict(falcon_key_id=key.key_id, falcon_key_version=1) if key.algorithm == 'FALCON' else dict(
            recipient_key_id=key.key_id, recipient_key_version=1)
        sessions.append(SessionKey(session_id=f'accrevoke-{tag}-{i}',
            node1=key.node, node2=key.node, session_type=wrapping, status='established',
            expires_at=now + timedelta(hours=1), **references))
    PreDistributedKey.objects.bulk_create(pools, batch_size=500)
    SessionKey.objects.bulk_create(sessions, batch_size=500)
    for key in keys:
        actual, _, _ = inspect_key(key, key.node)
        if actual != expected[key.key_id]:
            raise RuntimeError('验收异常数据与生产检测规则不一致')
    return keys, expected


def run_abnormal_revocation(count=SAMPLE_COUNT):
    if type(count) is not int or not 3 <= count <= SAMPLE_COUNT:
        raise ValueError('异常样本数必须在 3 到 6000 之间')
    started = time.monotonic_ns()
    with isolated_tables():
        keys, expected = create_fixture(count)
        before_at = timezone.now().isoformat()
        # Drain the submitted backlog without a throughput/time cutoff. The
        # scanner's candidate table is the actual attempted set, independent of
        # successful writes. Count unique keys, including attempted failures.
        scan_started = time.monotonic_ns()
        batches, attempted_ids = [], set()
        detection_elapsed_ms = 0.0
        detection_at = ''
        revoke_started_at = ''
        auto_revoked = False
        while len(attempted_ids) < count:
            measured = scan_once()
            with connection.cursor() as cursor:
                cursor.execute('SELECT id FROM kms_auto_revoke_candidates')
                candidates = {row[0] for row in cursor.fetchall()}
            previous = len(attempted_ids)
            attempted_ids.update(candidates)
            detection_elapsed_ms += float(measured.get('detection_elapsed_ms') or 0)
            detection_at = detection_at or measured.get('detection_at', '')
            revoke_started_at = revoke_started_at or measured.get('revoke_started_at', '')
            auto_revoked = auto_revoked or bool(measured.get('auto_revoked'))
            batches.append(dict(batchId=measured.get('batch_id', ''), attempted=len(candidates), revoked=measured['keys'],
                poolRevoked=measured['pool'], sessionsRevoked=measured['sessions'], elapsedMs=measured['elapsed_ms'],
                detectionElapsedMs=measured.get('detection_elapsed_ms', 0), detectionAt=measured.get('detection_at', ''),
                revokeStartedAt=measured.get('revoke_started_at', ''), autoRevoked=bool(measured.get('auto_revoked'))))
            if not candidates or (len(attempted_ids) == previous and not measured['keys']):
                break  # No pending dispatch or no progress: report actual outcomes, never loop forever.
        elapsed_ms = max(1, (time.monotonic_ns() - scan_started) / 1_000_000)
        after = {key.pk: key for key in NodeLongTermKey.objects.order_by('pk')}
        findings = {row.key_id: row for row in NodeKeyInspection.objects.all()}
        rows, completed, controls_ok = [], 0, 0
        by_rule = {rule: dict(rule=rule, injected=0, detected=0, revoked=0) for rule in RULES}
        for key in keys:
            rule, current, finding = expected[key.key_id], after[key.pk], findings.get(key.pk)
            abnormal = rule in RULES
            if abnormal:
                item = by_rule[rule]
                item['injected'] += 1
                detected = finding is not None and finding.rule == rule
                revoked = detected and finding.action == C.INSPECTION_AUTO_REVOKED and current.status == 'REVOKED'
                item['detected'] += int(detected)
                item['revoked'] += int(revoked)
                completed += int(revoked)
                passed = revoked
            else:
                passed = current.status == 'ACTIVE' and (finding is None if not rule else
                    finding is not None and finding.rule == rule and finding.action == C.INSPECTION_PENDING_REVIEW)
                controls_ok += int(passed)
            rows.append(dict(keyId=key.pk, nodeId=key.node.node_id, algorithm=key.algorithm,
                rule=rule, abnormal=abnormal, attempted=key.pk in attempted_ids, beforeStatus=key.status, afterStatus=current.status,
                detectedRule=finding.rule if finding else '',
                action=finding.action if finding else '', passed=passed))
        pool_count = PreDistributedKey.objects.filter(status='REVOKED').count()
        session_count = SessionKey.objects.filter(status='revoked').count()
        invalidations = SessionKeyInvalidation.objects.filter(reason='automatic_revocation').count()
        recorded = NodeKeyAutoRevocationBatch.objects.filter(batch_id__in=[b['batchId'] for b in batches if b['batchId']])
        if sum(b.key_count for b in recorded) != sum(b['revoked'] for b in batches):
            raise RuntimeError('回收批次审计与扫描结果不一致')
        passed = (completed == count and controls_ok == 4 and sum(b['revoked'] for b in batches) == count
                  and pool_count == session_count == invalidations == count
                  and PreDistributedKey.objects.filter(status='READY').count() == 4
                  and SessionKey.objects.filter(status='established').count() == 4)
        evidence = dict(version=2, source='node-auto-revoke-isolated-mysql', isolated=True,
            batchId=str(uuid.uuid4()), batchLimit=BATCH_LIMIT, batches=batches,
            injected=count, attempted=len(attempted_ids), detected=sum(i['detected'] for i in by_rule.values()),
            revoked=completed, controls=4, controlsPassed=controls_ok, poolRevoked=pool_count,
            sessionsRevoked=session_count, invalidations=invalidations, passed=passed,
            elapsedMs=elapsed_ms, detectionElapsedMs=detection_elapsed_ms, detectionAt=detection_at,
            revokeStartedAt=revoke_started_at, autoRevoked=auto_revoked,
            beforeAt=before_at, observedAt=timezone.now().isoformat(),
            rules=list(by_rule.values()), rows=rows)
    evidence['cleanupComplete'] = True
    evidence['totalMs'] = (time.monotonic_ns() - started) / 1_000_000
    return evidence
