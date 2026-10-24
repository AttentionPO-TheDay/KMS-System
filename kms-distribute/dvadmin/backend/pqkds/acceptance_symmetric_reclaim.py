"""Measure real expired SM4 pool deletion on connection-local MySQL tables."""
import base64
from datetime import timedelta
import hashlib
import json
import time
import uuid

from django.utils import timezone

from .acceptance_revoke import isolated_tables, MODELS
from .crypto_utils import KyberCrypto
from .key_pool_service import KeyPoolService
from .models import Node, PreDistributedKey, DistributionBatchItem
from .sm4_crypto import PayloadCipher, SM4Crypto, GCM_IV_BYTES

SAMPLE_COUNT = 12000
SOURCE = 'sm4-expired-pool-isolated-mysql'
# ORM deletion updates this reverse SET_NULL relation; shadow it as well.
ISOLATED_MODELS = MODELS + (DistributionBatchItem,)


def timestamp(value):
    # The deployed Django configuration also supports USE_TZ=False.
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_default_timezone())
    return value.isoformat()


def create_fixture(count):
    tag = uuid.uuid4().hex
    nodes = [Node.objects.create(node_id=f'accsm4-{tag}-{i}', name='对称密钥回收验收',
             ip_address='127.0.0.1', port=0, status='ACTIVE') for i in range(2)]
    kem = KyberCrypto(768)
    public, secret = kem.generate_keypair()
    now = timezone.now()
    records, hashes = [], set()
    for i in range(count + 4):
        key = PayloadCipher.generate_key()
        digest = hashlib.sha256(key).hexdigest()
        if digest in hashes:
            raise RuntimeError('对称密钥样本重复')
        hashes.add(digest)
        kem_ct, shared = kem.encrypt(public)
        kek = PayloadCipher.kek_from_shared_secret('sm4', shared)
        encrypted, nonce_tag = SM4Crypto.encrypt(key, kek)
        recovered = SM4Crypto.decrypt(encrypted, PayloadCipher.kek_from_shared_secret(
            'sm4', kem.decrypt(kem_ct, secret)), nonce_tag)
        if recovered != key:
            raise RuntimeError('SM4保护包有效性校验失败')
        status = ('READY', 'EXPIRED')[i % 2] if i < count else ('READY', 'CONSUMED', 'REVOKED', 'RESERVED')[i-count]
        expires = now + timedelta(days=1) if i == count else now - timedelta(hours=1)
        package = dict(payload_algorithm='sm4', key_hash=digest,
            kem_ciphertext=base64.b64encode(kem_ct).decode(),
            encrypted_key=base64.b64encode(encrypted).decode(),
            nonce=base64.b64encode(nonce_tag[:GCM_IV_BYTES]).decode(),
            tag=base64.b64encode(nonce_tag[GCM_IV_BYTES:]).decode())
        records.append(PreDistributedKey(pool_id=f'accsm4-{tag}', key_index=i,
            node1=nodes[0], node2=nodes[1], algorithm='kyber_kem', wrapping_algorithm='kyber_kem',
            payload_algorithm='sm4', recipient_type='pool', encrypted_key_data=json.dumps(package),
            key_hash=digest, status=status, expires_at=expires))
    PreDistributedKey.objects.bulk_create(records, batch_size=500)
    return list(PreDistributedKey.objects.order_by('key_index').values(
        'id', 'pool_id', 'key_index', 'key_hash', 'payload_algorithm', 'status', 'expires_at'))


def run_symmetric_reclamation(count=SAMPLE_COUNT):
    if type(count) is not int or not 2 <= count <= SAMPLE_COUNT:
        raise ValueError('样本数必须在2到12000之间')
    started = time.monotonic_ns()
    with isolated_tables(ISOLATED_MODELS):
        before = create_fixture(count)
        before_at = timezone.now()
        # Preparation and crypto checks are outside the timer. Measure the existing
        # DB cleanup, including ORM work and commit; no business local files touched.
        scan_started = time.monotonic_ns()
        KeyPoolService.cleanup_expired(cleanup_local=False)
        elapsed_ms = (time.monotonic_ns() - scan_started) / 1_000_000
        after = {r.pk: r for r in PreDistributedKey.objects.all()}
        rows = []
        reclaimed = controls_passed = 0
        for record in before:
            eligible = record['key_index'] < count
            current = after.get(record['id'])
            deleted = current is None
            if eligible:
                reclaimed += int(deleted)
            elif current is not None and current.status == record['status'] and current.key_hash == record['key_hash']:
                controls_passed += 1
            rows.append(dict(keyId=record['id'], poolId=record['pool_id'], keyIndex=record['key_index'],
                keyHash=record['key_hash'], algorithm=record['payload_algorithm'], eligible=eligible,
                expiresAt=timestamp(record['expires_at']), beforeStatus=record['status'],
                afterStatus=current.status if current else 'DELETED', deleted=deleted))
        evidence = dict(version=1, source=SOURCE, isolated=True, batchId=uuid.uuid4().hex,
            injected=count, reclaimed=reclaimed, remaining=count-reclaimed,
            controls=4, controlsPassed=controls_passed, materialVerified=True,
            elapsedMs=elapsed_ms, beforeAt=timestamp(before_at), observedAt=timestamp(timezone.now()),
            passed=reclaimed == count and controls_passed == 4, rows=rows)
    evidence['cleanupComplete'] = True
    evidence['totalMs'] = (time.monotonic_ns() - started) / 1_000_000
    return evidence
