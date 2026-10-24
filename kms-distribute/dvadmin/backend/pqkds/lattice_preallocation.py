"""Persistent, server-only lattice preparation and envelope-bound preimages."""
import base64
import hashlib
import json
import os
import time
from functools import lru_cache

import numpy as np
from Crypto.Cipher import AES
from django.db import transaction

from . import lattice_preallocation_math as lattice


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def seal(value):
    key = storage_key()
    cipher = AES.new(key, AES.MODE_GCM)
    encrypted, tag = cipher.encrypt_and_digest(canonical(value))
    return base64.b64encode(cipher.nonce + tag + encrypted).decode()


def unseal(value):
    raw = base64.b64decode(value, validate=True)
    key = storage_key()
    return json.loads(AES.new(key, AES.MODE_GCM, nonce=raw[:16]).decrypt_and_verify(raw[32:], raw[16:32]))


def storage_key():
    secret = os.environ.get('KMS_LATTICE_STORAGE_KEY') or os.environ.get('INTERNAL_TOKEN', '')
    if len(secret) < 32:
        raise ValueError('格陷门存储需要至少 32 字符的服务端秘密')
    return hashlib.sha256(b'KMS-LATTICE-STORAGE-V1\0' + secret.encode()).digest()


@lru_cache(maxsize=16)
def load_context(material_id):
    from .models import LatticePreparation
    row = LatticePreparation.objects.get(pk=material_id)
    private = unseal(row.encrypted_secret)
    parent = load_context(str(row.parent_id)) if row.parent_id else None
    context = lattice.prepare(row.public_matrix, private['basis'],
                              r=np.asarray(private['r'], dtype=np.int64) if private.get('r') is not None else None,
                              parent=parent)
    if context['public_digest'] != row.public_digest:
        raise ValueError('持久化格参数摘要不一致')
    context['material_id'] = str(row.pk)
    return context


def public_record(row):
    return dict(id=str(row.pk), kind=row.kind, parentId=str(row.parent_id) if row.parent_id else None,
                nodeId=row.node.node_id if row.node_id else None, nodeName=row.node.name if row.node_id else None,
                publicDigest=row.public_digest, n=lattice.N, q=lattice.Q, dimension=len(row.public_matrix[0]),
                normBound=row.norm_bound,
                profile=lattice.PROFILE, createdAt=row.created_at.isoformat())


def create_root():
    from .models import LatticePreparation
    started = time.perf_counter()
    context = lattice.trapgen()
    elapsed = (time.perf_counter() - started) * 1000
    row = LatticePreparation.objects.create(kind='ROOT', public_matrix=context['public'].tolist(), norm_bound=lattice.norm_bound(context),
        public_digest=context['public_digest'], encrypted_secret=seal(dict(basis=context['basis'].tolist(), r=context['r'].tolist())))
    reloaded = load_context(str(row.pk))
    return row, dict(generationMs=elapsed, fullRank=bool(np.all(np.abs(reloaded['diagonal']) > 1e-8)),
                     kernelRelation=bool(not np.any(context['public'] @ context['basis'] % lattice.Q)),
                     determinantLogQ=lattice.N, secretPersistedEncrypted=True,
                     maxGramSchmidt=float(np.max(np.abs(context['diagonal']))))


def create_delegation(root, node):
    from .models import LatticePreparation
    if root.kind != 'ROOT':
        raise ValueError('委派必须选择离线生成的主格参数')
    started = time.perf_counter()
    context = lattice.delegate(load_context(str(root.pk)), node.node_id)
    elapsed = (time.perf_counter() - started) * 1000
    # ExtBasis remains inside KMS. It is never delivered to an untrusted node.
    with transaction.atomic():
        row, created = LatticePreparation.objects.get_or_create(parent=root, node=node, defaults=dict(kind='DELEGATED',
            public_matrix=context['public'].tolist(), public_digest=context['public_digest'], norm_bound=lattice.norm_bound(context),
            encrypted_secret=seal(dict(basis=context['basis'].tolist(), r=None))))
    loaded = load_context(str(row.pk))
    target = lattice.target_for(b'delegation-check:' + str(row.pk).encode())
    vector = lattice.sample_pre(loaded, target)
    return row, dict(delegationMs=elapsed, reused=not created, kernelRelation=bool(not np.any(context['public'] @ context['basis'] % lattice.Q)),
                     nodeBound=context['public_digest'] == loaded['public_digest'],
                     preimageVerified=lattice.verify(loaded['public'], target, vector, lattice.norm_bound(loaded)))


def prepared_for(node_id):
    from .models import LatticePreparation
    return LatticePreparation.objects.filter(kind='DELEGATED', node__node_id=node_id).order_by('-created_at').first()


def attach_proofs(packages, preparation, workers=4):
    """Used by both the actual pool-ingress path and the acceptance driver."""
    context = load_context(str(preparation.pk))
    if preparation.kind != 'DELEGATED':
        raise ValueError('预分配需要节点委派格基')
    if any('latticeProof' in package for package in packages):
        raise ValueError('格证明必须由服务端生成')
    messages = [canonical(package) for package in packages]
    started = time.perf_counter()
    metrics = {}
    vectors = lattice.sample_parallel(context, messages, workers, metrics)
    elapsed = (time.perf_counter() - started) * 1000
    result = []
    for package, message, vector in zip(packages, messages, vectors):
        result.append({**package, 'latticeProof': dict(version=1, preparationId=str(preparation.pk),
            publicDigest=context['public_digest'], packageDigest=hashlib.sha256(message).hexdigest(),
            vector=vector.tolist())})
    return result, elapsed, metrics


def verify_package(package, receiver_id):
    from .models import LatticePreparation
    proof = package.get('latticeProof')
    if not isinstance(proof, dict) or proof.get('version') != 1:
        return False
    try:
        row = LatticePreparation.objects.select_related('node').get(pk=proof['preparationId'], kind='DELEGATED')
        public = np.asarray(row.public_matrix, dtype=np.int64)
        return _verify_prepared_package(package, receiver_id, row, public)
    except (LatticePreparation.DoesNotExist, ValueError, TypeError, KeyError, OverflowError):
        return False


def _verify_prepared_package(package, receiver_id, preparation, public):
    """Reuse immutable batch parameters while verifying every package independently."""
    proof = package.get('latticeProof')
    if not isinstance(proof, dict) or proof.get('version') != 1:
        return False
    try:
        if (preparation.kind != 'DELEGATED' or str(proof['preparationId']) != str(preparation.pk)
                or preparation.node.node_id != receiver_id or proof['publicDigest'] != preparation.public_digest):
            return False
        message = canonical({k: v for k, v in package.items() if k != 'latticeProof'})
        vector = proof['vector']
        if not isinstance(vector, list) or any(type(x) is not int or abs(x) >= 10**7 for x in vector):
            return False
        return proof['packageDigest'] == hashlib.sha256(message).hexdigest() and lattice.verify(
            public, lattice.target_for(message), np.asarray(vector, dtype=np.int64), preparation.norm_bound)
    except (ValueError, TypeError, KeyError, OverflowError):
        return False


def protect_pool_rows(rows, receiver_id, preparation=None, workers=4):
    """Run before the pool transaction commits; unverified rows never go READY."""
    preparation = preparation or prepared_for(receiver_id)
    if preparation is None or not rows:
        return dict(enabled=False, verified=0, samplingMs=0)
    if preparation.node.node_id != receiver_id:
        raise ValueError('格基委派节点与预分配接收节点不一致')
    packages = [json.loads(row.encrypted_key_data) for row in rows]
    protected, elapsed, metrics = attach_proofs(packages, preparation, workers)
    public = np.asarray(preparation.public_matrix, dtype=np.int64)
    for row, package in zip(rows, protected):
        if not _verify_prepared_package(package, receiver_id, preparation, public):
            raise ValueError('预分配入池格证明验证失败')
        row.encrypted_key_data = canonical(package).decode('utf-8')
        row.lattice_preparation = preparation
    from .models import PreDistributedKey
    PreDistributedKey.objects.bulk_update(rows, ['encrypted_key_data', 'lattice_preparation'])
    return dict(enabled=True, verified=len(rows), samplingMs=elapsed, preparationId=str(preparation.pk), **metrics)


def verify_pool_row(row):
    if not row.lattice_preparation_id:
        return True  # Legacy/unprepared nodes retain their existing protocol.
    try:
        package = json.loads(row.encrypted_key_data)
        if package.get('latticeProof', {}).get('preparationId') != str(row.lattice_preparation_id):
            return False
        if package.get('key_hash') != row.key_hash:
            return False
        return verify_package(package, row.lattice_preparation.node.node_id)
    except (ValueError, TypeError, AttributeError):
        return False
