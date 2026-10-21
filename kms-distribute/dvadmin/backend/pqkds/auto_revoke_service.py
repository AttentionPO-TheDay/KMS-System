"""Set-based health inspection and automatic revocation of node long-term keys.

Only an ACTIVE key whose stored public material is missing or whose stored
SHA-256 disagrees with that material is automatically revoked. A mismatch
between the key registry and the Node materialized column is recorded for
review: either side could be wrong, so it is not a safe automatic decision.
"""
from __future__ import annotations

import logging
import hashlib
import json
import os
import time
import uuid

from django.db import close_old_connections, connection, transaction
from django.db.models import Max
from django.utils import timezone

from . import api_contract as C
from .chain_backend import is_fabric_did
from .chain_binding_service import (PROVIDER, canonical_json, configured_namespace,
                                    digest_metadata)
from .fabric_did_client import BindingError, local_configuration_error
from .models import (Node, NodeKeyAutoRevocationBatch, NodeLongTermKey,
                     PreDistributedKey, SessionKey, SessionKeyInvalidation,
                     NodeKeyInspection, ChainKeyBinding)

logger = logging.getLogger(__name__)
LOCK_NAME = 'kms-node-key-auto-revoke-v1'
KEY_TABLE = NodeLongTermKey._meta.db_table
NODE_TABLE = Node._meta.db_table
POOL_TABLE = PreDistributedKey._meta.db_table
SESSION_TABLE = SessionKey._meta.db_table
INVALIDATION_TABLE = SessionKeyInvalidation._meta.db_table
INSPECTION_TABLE = NodeKeyInspection._meta.db_table
BATCH_LIMIT = 5000


def _severe_condition(alias='k'):
    return (f"({alias}.public_key IS NULL OR TRIM({alias}.public_key) = '' OR "
            f"{alias}.public_key_hash IS NULL OR {alias}.public_key_hash = '' OR "
            f"LOWER(SHA2({alias}.public_key, 256)) <> LOWER({alias}.public_key_hash))")


def _algorithm_match(table_alias):
    """SQL clause and params derived from the shared algorithm contract."""
    parts, params = [], []
    for algorithm in ('KYBER', 'SM2', 'SSCL', 'FALCON'):
        family = C.wrapping_algorithms_for(algorithm)
        placeholders = ', '.join(['%s'] * len(family))
        parts.append(f"(t.algorithm = %s AND {table_alias} IN ({placeholders}))")
        params.extend([algorithm, *family])
    return '(' + ' OR '.join(parts) + ')', params


def _prepare_tables(cursor):
    cursor.execute("""
        CREATE TEMPORARY TABLE IF NOT EXISTS kms_auto_revoke_candidates (
          id BIGINT PRIMARY KEY, node_id BIGINT NOT NULL, algorithm VARCHAR(20) NOT NULL,
          key_id VARCHAR(64) NOT NULL, key_version INT NOT NULL, rule VARCHAR(40) NOT NULL,
          INDEX (node_id, algorithm), INDEX (key_id, key_version)
        ) ENGINE=MEMORY
    """)
    cursor.execute("""
        CREATE TEMPORARY TABLE IF NOT EXISTS kms_auto_revoke_sessions (
          session_id BIGINT PRIMARY KEY, node_id BIGINT NOT NULL
        ) ENGINE=MEMORY
    """)
    cursor.execute('DELETE FROM kms_auto_revoke_candidates')
    cursor.execute('DELETE FROM kms_auto_revoke_sessions')


def inspect_key(key, node):
    """Single-row version of scan predicates; detection only, never revocation."""
    if key.status != C.KEY_STATUS_ACTIVE:
        return '', '', C.INSPECTION_RESOLVED
    public = key.public_key or ''
    if not public.strip():
        rule = 'PUBLIC_KEY_MISSING'
    elif not key.public_key_hash:
        rule = 'PUBLIC_KEY_HASH_MISSING'
    elif hashlib.sha256(public.encode('utf-8')).hexdigest().lower() != key.public_key_hash.lower():
        rule = 'PUBLIC_KEY_HASH_MISMATCH'
    else:
        column = C.algorithm_column(key.algorithm)
        materialized = getattr(node, column, None) if column else None
        # SQL NULL comparison is unknown, not a detected mismatch.
        if materialized is not None and materialized != public:
            return 'MATERIALIZED_PUBLIC_KEY_MISMATCH', 'WARNING', C.INSPECTION_PENDING_REVIEW
        return '', '', C.INSPECTION_RESOLVED
    return rule, 'ERROR', C.INSPECTION_PENDING_REVIEW


def _inspect_warnings(cursor, now):
    """Record registry/materialized-column drift for review; never auto revoke."""
    mismatch = ('(CASE k.algorithm '
                "WHEN 'KYBER' THEN n.kyber_public_key "
                "WHEN 'SM2' THEN n.gm_public_key "
                "WHEN 'SSCL' THEN n.sscl_public_key "
                "WHEN 'FALCON' THEN n.falcon_sign_public_key END) <> k.public_key")
    cursor.execute(f"""
        INSERT INTO {INSPECTION_TABLE}
          (key_id, rule, severity, action, detected_at, action_at, batch_id, handled_by)
        SELECT k.id, 'MATERIALIZED_PUBLIC_KEY_MISMATCH', 'WARNING',
               '{C.INSPECTION_PENDING_REVIEW}', %s, NULL, '', ''
        FROM {KEY_TABLE} k JOIN {NODE_TABLE} n ON n.id = k.node_id
        WHERE k.status = 'ACTIVE' AND NOT {_severe_condition()}
          AND {mismatch}
        ON DUPLICATE KEY UPDATE
          rule = IF(disposition IN ('confirmed','dismissed','manual_revoked'), rule, VALUES(rule)),
          severity = IF(disposition IN ('confirmed','dismissed','manual_revoked'), severity, 'WARNING'),
          action = IF(disposition IN ('confirmed','dismissed','manual_revoked'), action, '{C.INSPECTION_PENDING_REVIEW}'),
          action_at = IF(disposition IN ('confirmed','dismissed','manual_revoked'), action_at, NULL)
    """, [now])
    cursor.execute(f"""
        UPDATE {INSPECTION_TABLE} i JOIN {KEY_TABLE} k ON k.id = i.key_id
        JOIN {NODE_TABLE} n ON n.id = k.node_id
        SET i.action = '{C.INSPECTION_RESOLVED}', i.action_at = %s
        WHERE i.action = '{C.INSPECTION_PENDING_REVIEW}'
          AND (i.disposition IS NULL OR i.disposition NOT IN ('confirmed','dismissed','manual_revoked'))
          AND (k.status <> 'ACTIVE' OR NOT ({mismatch}))
    """, [now])


def _enqueue_fabric_bindings(cursor, now):
    """Write the same REVOKED snapshots as the registry path, in bounded bulk."""
    cursor.execute('SELECT id FROM kms_auto_revoke_candidates')
    key_ids = [row[0] for row in cursor.fetchall()]
    if not key_ids:
        return
    chain_id = os.environ.get('FABRIC_DID_CHAIN_ID', '').strip()
    namespace = configured_namespace()
    if len(chain_id) > 128:
        raise BindingError('INVALID_CHAIN_ID')
    if not namespace or len(namespace) > 80:
        raise BindingError('INVALID_NAMESPACE')
    keys = list(NodeLongTermKey.objects.select_related('node').filter(
        pk__in=key_ids, status='REVOKED').order_by('node_id', 'id'))
    if len(keys) != len(key_ids):
        raise RuntimeError('Fabric revocation binding source count mismatch')
    node_ids = {key.node_id for key in keys}
    sequences = dict(ChainKeyBinding.objects.filter(node_id__in=node_ids)
                     .values('node_id').annotate(value=Max('sequence'))
                     .values_list('node_id', 'value'))
    existing = {row.long_term_key_id: row for row in ChainKeyBinding.objects.filter(
        long_term_key_id__in=key_ids, provider=PROVIDER, chain_id=chain_id,
        namespace=namespace, event_type='REVOKED', key_status='REVOKED')}
    error = local_configuration_error(chain_id)
    rows = []
    for key in keys:
        prior = existing.get(key.pk)
        if prior is not None:
            previous = json.loads(prior.metadata)
            if (previous.get('publicKey') != key.public_key or
                    previous.get('publicKeyHash') != key.public_key_hash):
                raise BindingError('BINDING_IDEMPOTENCY_CONFLICT')
            continue
        sequence = sequences.get(key.node_id, 0) + 1
        sequences[key.node_id] = sequence
        key_ref = f'node/{key.node.node_id}/{key.algorithm}/{key.key_id}/{key.key_version}'
        event_id = digest_metadata(canonical_json({
            'provider': PROVIDER, 'chainId': chain_id, 'namespace': namespace,
            'keyRef': key_ref, 'eventType': 'REVOKED', 'keyStatus': 'REVOKED',
            'revision': sequence,
        }))
        metadata = canonical_json({
            'schemaVersion': 1, 'namespace': namespace,
            'nodeId': key.node.node_id, 'algorithm': key.algorithm,
            'keyId': key.key_id, 'keyVersion': key.key_version,
            'publicKey': key.public_key, 'publicKeyHash': key.public_key_hash,
            'status': 'REVOKED', 'eventType': 'REVOKED',
            'revision': sequence, 'eventId': event_id,
            'recordedAt': now.isoformat(),
        })
        rows.append(ChainKeyBinding(
            provider=PROVIDER, chain_id=chain_id, namespace=namespace,
            node=key.node, long_term_key=key, node_id_snapshot=key.node.node_id,
            algorithm=key.algorithm, key_id=key.key_id, key_version=key.key_version,
            key_ref=key_ref, event_type='REVOKED', key_status='REVOKED',
            sequence=sequence, event_id=event_id, metadata=metadata,
            metadata_digest=digest_metadata(metadata),
            status='NOT_CONFIGURED' if error else 'PENDING', last_error=error,
            recorded_at=now,
        ))
    ChainKeyBinding.objects.bulk_create(rows, batch_size=500)


def _revoke_batch(cursor, batch_id, now):
    phases = {}
    mark = time.monotonic_ns()
    def tick(name):
        nonlocal mark
        current = time.monotonic_ns()
        phases[name] = round((current - mark) / 1_000_000, 2)
        mark = current
    pool_wrap_match, wrap_params = _algorithm_match('p.wrapping_algorithm')
    pool_algo_match, algo_params = _algorithm_match('p.algorithm')
    session_match, session_params = _algorithm_match('s.session_type')

    # A key row and its materialized Node column are changed inside the same
    # transaction. The caller has already locked all affected Node rows.
    cursor.execute(f"""
        UPDATE {KEY_TABLE} k JOIN kms_auto_revoke_candidates t ON t.id = k.id
        SET k.status = 'REVOKED', k.active_slot = NULL, k.revoked_at = %s,
            k.revoked_reason = CONCAT('自动健康审查：', t.rule), k.update_datetime = %s
        WHERE k.status = 'ACTIVE'
    """, [now, now])
    key_count = cursor.rowcount
    if not key_count:
        return 0, 0, 0, phases
    tick('key_update')

    for algorithm, columns in {
        'KYBER': ('kyber_public_key',),
        'SM2': ('gm_public_key',),
        'SSCL': ('sscl_public_key',),
        'FALCON': ('falcon_sign_public_key', 'falcon_public_key'),
    }.items():
        assignments = ', '.join(f'n.{col} = %s' for col in columns)
        cursor.execute(f"""
            UPDATE {NODE_TABLE} n JOIN kms_auto_revoke_candidates t ON t.node_id = n.id
            SET {assignments} WHERE t.algorithm = %s
        """, [''] * len(columns) + [algorithm])
    tick('node_columns')

    # Keep each join on one node column and one key-reference path so MySQL can
    # use the existing node and long-term-key indexes instead of scanning the
    # entire pool for each candidate.
    pool_count = 0
    for node_column in ('node1_id', 'node2_id'):
        cursor.execute(f"""
            UPDATE kms_auto_revoke_candidates t JOIN {POOL_TABLE} p
              ON p.{node_column} = t.node_id
             AND p.long_term_key_id = t.key_id
             AND p.long_term_key_version = t.key_version
            SET p.status = 'REVOKED'
            WHERE p.status IN ('READY', 'RESERVED', 'unused')
        """)
        pool_count += cursor.rowcount
        cursor.execute(f"""
            UPDATE kms_auto_revoke_candidates t JOIN {POOL_TABLE} p
              ON p.{node_column} = t.node_id AND p.long_term_key_id IS NULL
             AND ({pool_wrap_match} OR {pool_algo_match})
            SET p.status = 'REVOKED'
            WHERE p.status IN ('READY', 'RESERVED', 'unused')
        """, [*wrap_params, *algo_params])
        pool_count += cursor.rowcount
    tick('pool_update')

    cursor.execute(f"""
        INSERT IGNORE INTO kms_auto_revoke_sessions (session_id, node_id)
        SELECT s.id, t.node_id
        FROM kms_auto_revoke_candidates t JOIN {SESSION_TABLE} s
          ON s.node1_id = t.node_id AND s.falcon_key_id = t.key_id
         AND s.falcon_key_version = t.key_version
        WHERE t.algorithm = 'FALCON'
          AND s.status IN ('initiated', 'established', 'blockchain_recorded')
    """)
    cursor.execute(f"""
        INSERT IGNORE INTO kms_auto_revoke_sessions (session_id, node_id)
        SELECT s.id, t.node_id
        FROM kms_auto_revoke_candidates t JOIN {SESSION_TABLE} s
          ON s.node2_id = t.node_id AND s.recipient_key_id = t.key_id
         AND s.recipient_key_version = t.key_version
        WHERE t.algorithm <> 'FALCON' AND {session_match}
          AND s.status IN ('initiated', 'established', 'blockchain_recorded')
    """, session_params)
    cursor.execute(f"""
        INSERT IGNORE INTO kms_auto_revoke_sessions (session_id, node_id)
        SELECT s.id, t.node_id
        FROM kms_auto_revoke_candidates t JOIN {SESSION_TABLE} s
          ON s.node2_id = t.node_id AND s.recipient_key_id IS NULL
        WHERE t.algorithm <> 'FALCON' AND {session_match}
          AND s.status IN ('initiated', 'established', 'blockchain_recorded')
    """, session_params)
    cursor.execute('SELECT COUNT(*) FROM kms_auto_revoke_sessions')
    session_count = cursor.fetchone()[0]
    tick('session_match')
    if session_count:
        cursor.execute(f"""
            INSERT INTO {INVALIDATION_TABLE}
              (session_id, invalidated_node_id, reason, invalidated_at,
               create_datetime, update_datetime)
            SELECT session_id, node_id, 'automatic_revocation', %s, %s, %s
            FROM kms_auto_revoke_sessions
        """, [now, now, now])
        cursor.execute(f"""
            UPDATE {SESSION_TABLE} s JOIN kms_auto_revoke_sessions t ON t.session_id = s.id
            SET s.status = 'revoked'
        """)
    tick('session_records_update')

    cursor.execute(f"""
        INSERT INTO {INSPECTION_TABLE}
          (key_id, rule, severity, action, detected_at, action_at, batch_id, handled_by)
        SELECT t.id, t.rule, 'ERROR', '{C.INSPECTION_AUTO_REVOKED}', %s, %s, %s, ''
        FROM kms_auto_revoke_candidates t
        ON DUPLICATE KEY UPDATE
          rule = IF(disposition IN ('confirmed','dismissed','manual_revoked'), {INSPECTION_TABLE}.rule, VALUES(rule)),
          severity = IF(disposition IN ('confirmed','dismissed','manual_revoked'), severity, 'ERROR'),
          action = IF(disposition IN ('confirmed','dismissed','manual_revoked'), action, '{C.INSPECTION_AUTO_REVOKED}'),
          action_at = IF(disposition IN ('confirmed','dismissed','manual_revoked'), action_at, VALUES(action_at)),
          batch_id = IF(disposition IN ('confirmed','dismissed','manual_revoked'), batch_id, VALUES(batch_id))
    """, [now, now, batch_id])
    tick('key_audit')
    if is_fabric_did():
        _enqueue_fabric_bindings(cursor, now)
        tick('fabric_binding')
    return key_count, pool_count, session_count, phases


def scan_once():
    """Inspect the database and commit up to 5,000 revocations as one batch."""
    started_ns = time.monotonic_ns()
    started_at = timezone.now()
    batch_id = str(uuid.uuid4())
    with connection.cursor() as cursor:
        _prepare_tables(cursor)
        cursor.execute(f"""
            SELECT k.node_id FROM {KEY_TABLE} k
            WHERE k.status = 'ACTIVE' AND {_severe_condition()}
            ORDER BY k.id LIMIT %s
        """, [BATCH_LIMIT])
        node_ids = sorted({row[0] for row in cursor.fetchall()})
        if not node_ids:
            _inspect_warnings(cursor, started_at)
            return {'keys': 0, 'pool': 0, 'sessions': 0, 'elapsed_ms': 0}

        with transaction.atomic():
            # Registrations and rotations serialize on the Node row. Lock in ID
            # order, then re-evaluate candidates under the lock.
            list(Node.objects.select_for_update().filter(pk__in=node_ids)
                 .order_by('pk').values_list('pk', flat=True))
            placeholders = ', '.join(['%s'] * len(node_ids))
            cursor.execute(f"""
                INSERT INTO kms_auto_revoke_candidates
                  (id, node_id, algorithm, key_id, key_version, rule)
                SELECT k.id, k.node_id, k.algorithm, k.key_id, k.key_version,
                  CASE WHEN k.public_key IS NULL OR TRIM(k.public_key) = ''
                       THEN 'PUBLIC_KEY_MISSING'
                       WHEN k.public_key_hash IS NULL OR k.public_key_hash = ''
                       THEN 'PUBLIC_KEY_HASH_MISSING'
                       ELSE 'PUBLIC_KEY_HASH_MISMATCH' END
                FROM {KEY_TABLE} k
                WHERE k.node_id IN ({placeholders}) AND k.status = 'ACTIVE'
                  AND {_severe_condition()}
                ORDER BY k.id LIMIT %s
            """, [*node_ids, BATCH_LIMIT])
            key_count, pool_count, session_count, phases = _revoke_batch(
                cursor, batch_id, timezone.now())
            if key_count:
                elapsed_ms = max(1, (time.monotonic_ns() - started_ns) // 1_000_000)
                NodeKeyAutoRevocationBatch.objects.create(
                    batch_id=batch_id, started_at=started_at,
                    completed_at=timezone.now(), key_count=key_count,
                    pool_count=pool_count, session_count=session_count,
                    elapsed_ms=elapsed_ms,
                )
        _inspect_warnings(cursor, timezone.now())
    elapsed_ms = max(1, (time.monotonic_ns() - started_ns) // 1_000_000)
    return {'keys': key_count, 'pool': pool_count, 'sessions': session_count,
            'elapsed_ms': elapsed_ms, 'batch_id': batch_id,
            'keys_per_second': round(key_count * 1000 / elapsed_ms, 1),
            'phases_ms': phases}


def run_once():
    """Singleton across processes; only the holder scans at a time."""
    close_old_connections()
    with connection.cursor() as cursor:
        cursor.execute('SELECT GET_LOCK(%s, 0)', [LOCK_NAME])
        if cursor.fetchone()[0] != 1:
            return None
    try:
        return scan_once()
    finally:
        with connection.cursor() as cursor:
            cursor.execute('SELECT RELEASE_LOCK(%s)', [LOCK_NAME])
        close_old_connections()


def run_forever():
    """Dedicated process, started after migrations by docker compose."""
    interval = max(0.1, float(os.getenv('KMS_AUTO_REVOKE_SCAN_INTERVAL_SECONDS', '1')))
    while True:
        try:
            result = run_once()
            if result and result['keys']:
                logger.warning('automatic key revocation committed: %s', result)
                continue  # Drain an existing backlog without a one-second gap.
        except Exception:
            logger.exception('automatic key inspection failed; retrying')
        time.sleep(interval)
