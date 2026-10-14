"""Experimental custom matrix encryption, NOT standard Falcon/FN-DSA.

Only the fixed reference parameter set is supported. Partial and user matrices
are independent CSPRNG rounded Gaussian samples (sigma=1.17, rejection at 8).
This preserves the reference algebra, not a claim of trapdoor/security proof.
No server-side complete-key generation or legacy material decoding is provided.
"""
import base64
import hashlib
import json
import math
import secrets
import struct
from functools import lru_cache

import numpy as np

ALGORITHM = 'FALCON_CL_V1'
SCHEME = 'KMS_SPLIT_FALCON_CL_V1'
PARAMS = {'n': 512, 'm': 1024, 'q': 12289}
N, M, Q = 512, 1024, 12289
MAX_MATERIAL = 8_000_000
CT_BYTES = 21 + 3 * M * 8


def _b64(raw):
    return base64.b64encode(raw).decode('ascii')


def _decode(value, limit):
    if not isinstance(value, str) or len(value) > (limit + 2) // 3 * 4:
        raise ValueError('Falcon CL encoding/size invalid')
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError('Falcon CL encoding invalid') from exc
    if len(raw) > limit or _b64(raw) != value:
        raise ValueError('Falcon CL encoding noncanonical')
    return raw


def _matrix(value, rows, cols, secret=False):
    dtype = np.dtype('i1' if secret else '<u2')
    raw = _decode(value, rows * cols * dtype.itemsize)
    if len(raw) != rows * cols * dtype.itemsize:
        raise ValueError('Falcon CL matrix shape invalid')
    out = np.frombuffer(raw, dtype=dtype).reshape(rows, cols).astype(np.int64)
    if np.any(np.abs(out) > 8) if secret else np.any(out >= Q):
        raise ValueError('Falcon CL matrix range invalid')
    out.flags.writeable = False
    return out


def encode_material(matrices, kind, node_id):
    fields = {'PUBLIC': ('A', 'B', 'H_id', 'U_id'), 'PARTIAL': ('A', 'B', 'H_id', 'D_id'), 'PRIVATE': ('D_id', 'S_id')}[kind]
    data = {'algorithm': ALGORITHM, 'purpose': 'ENCRYPT', 'version': 1,
            'parameters': PARAMS, 'nodeId': node_id, 'kind': kind}
    for field in fields:
        data[field] = _b64(np.asarray(matrices[field], dtype='i1' if field in ('D_id', 'S_id') else '<u2').tobytes())
    return _b64(json.dumps(data, separators=(',', ':'), ensure_ascii=True).encode('ascii'))


def parse_material(value, kind, node_id=None):
    # Full encoded material + kind/version/params are the cache identity; no prefix aliases.
    if not isinstance(value, str) or len(value) > MAX_MATERIAL:
        raise ValueError('Falcon CL material size invalid')
    fields = {'PUBLIC': {'A', 'B', 'H_id', 'U_id'}, 'PARTIAL': {'A', 'B', 'H_id', 'D_id'}, 'PRIVATE': {'D_id', 'S_id'}}[kind]
    def unique(pairs):
        obj = {}
        for key, val in pairs:
            if key in obj:
                raise ValueError('Falcon CL duplicate field')
            obj[key] = val
        return obj
    data = json.loads(_decode(value, MAX_MATERIAL).decode('ascii'), object_pairs_hook=unique)
    if (not isinstance(data, dict) or set(data) != fields | {'algorithm', 'purpose', 'version', 'parameters', 'nodeId', 'kind'}
            or data['algorithm'] != ALGORITHM or data['purpose'] != 'ENCRYPT'
            or type(data['version']) is not int or data['version'] != 1
            or data['parameters'] != PARAMS or any(type(v) is not int for v in data['parameters'].values())
            or data['kind'] != kind or not isinstance(data['nodeId'], str) or not data['nodeId']
            or node_id is not None and data['nodeId'] != node_id):
        raise ValueError('Falcon CL material contract invalid')
    out = {'nodeId': data['nodeId']}
    for field in fields:
        out[field] = _matrix(data[field], M if field in ('D_id', 'S_id') else N, M, field in ('D_id', 'S_id'))
    return out


@lru_cache(maxsize=2)
def public_material(value):
    return parse_material(value, 'PUBLIC')


def partial_public_fingerprint(value, kind, node_id):
    material = parse_material(value, kind, node_id)
    digest = hashlib.sha256(b'FALCON_CL_V1|ENCRYPT|1|512|1024|12289|PARTIAL_PUBLIC')
    digest.update(node_id.encode('utf-8'))
    for field in ('A', 'B', 'H_id'):
        digest.update(np.asarray(material[field], dtype='<u2').tobytes())
    return digest.hexdigest()


def fingerprint(value, kind):
    parse_material(value, kind)
    return hashlib.sha256((ALGORITHM + '|ENCRYPT|1|512|1024|12289|' + kind + '|' + value).encode('ascii')).hexdigest()


def _uniform(count):
    # Rejection avoids reduction bias. Every entropy byte comes from OS CSPRNG.
    result = []
    bound = 65536 - 65536 % Q
    while len(result) < count:
        candidates = np.frombuffer(secrets.token_bytes((count - len(result)) * 2 + 32), dtype='<u2')
        result.extend((candidates[candidates < bound] % Q).tolist())
    return np.array(result[:count], dtype=np.int64)


def _short(count, random_bytes=secrets.token_bytes):
    result = []
    while len(result) < count:
        size = count - len(result)
        # 53-bit strictly positive uniforms, no public-ID/32-bit seed derivation.
        words = np.frombuffer(random_bytes(size * 16), dtype='<u8')
        u = ((words >> np.uint64(11)).astype(np.float64) + 1) / (2**53 + 1)
        values = np.rint(np.sqrt(-2 * np.log(u[::2])) * np.cos(2 * math.pi * u[1::2]) * 1.17).astype(np.int64)
        result.extend(values[np.abs(values) <= 8].tolist())
    return np.array(result[:count], dtype=np.int64)


def issue_partial(node_id, context=None):
    """Reuse real Falcon TrapGen/SamplePre, never a random-matrix substitute.

    As in the legacy custom scheme, A=[I|circ(h)] and SamplePre coefficients
    contribute to D's sampler. V1 replaces its 32-bit RandomState with a full
    SHAKE-256 stream including fresh 256-bit OS entropy and the bound transcript.
    This is a versioned experimental derivative, not a proved trapdoor sampler.
    """
    from .falcon_trapgen_dll import FalconTrapGen
    trapgen = FalconTrapGen()  # Missing real implementation is a hard failure; no fallback.
    setup = trapgen.generate()
    h = setup['h']
    a = np.zeros((N, M), dtype=np.int64)
    np.fill_diagonal(a[:, :N], 1)
    a[:, N:] = h[(np.arange(N)[:, None] - np.arange(N)[None, :]) % N] % Q
    b = _uniform(N * M).reshape(N, M)
    transcript = b'FALCON_CL_V1|ENCRYPT|PARTIAL|' + json.dumps(context or {'nodeId': node_id}, sort_keys=True, separators=(',', ':')).encode('utf-8')
    coefficients = trapgen.sample_pre(setup['falcon_sk'], setup['falcon_pk'], transcript)
    seed = hashlib.sha256(np.asarray(coefficients, dtype='<i2').tobytes() + transcript + secrets.token_bytes(32)).digest()
    counter = 0
    def stream(size):
        nonlocal counter
        counter += 1
        return hashlib.shake_256(b'FALCON_CL_V1|D_SAMPLE|' + seed + counter.to_bytes(8, 'little')).digest(size)
    d = _short(M * M, stream).reshape(M, M)
    try:
        return encode_material({'A': a, 'B': b, 'H_id': a @ d % Q, 'D_id': d}, 'PARTIAL', node_id)
    finally:
        d.fill(0)
        coefficients.fill(0)
        setup.pop('falcon_sk', None)  # Python immutable bytes cannot promise complete erasure.


def decode_ciphertext(value):
    raw = _decode(value, CT_BYTES)
    if len(raw) != CT_BYTES or raw[:5] != b'FCTV2' or struct.unpack('<IIII', raw[5:21]) != (N, M, Q, 16):
        raise ValueError('Falcon CL ciphertext header/length invalid')
    vectors = np.frombuffer(raw[21:], dtype='<i8').reshape(3, M).copy()
    if np.any(vectors < 0) or np.any(vectors >= Q):
        raise ValueError('Falcon CL ciphertext range invalid')
    return vectors


def encrypt(public_key, payload_key, recipient_id=None):
    if not isinstance(payload_key, bytes) or len(payload_key) != 16:
        raise ValueError('Falcon CL payload must be exactly 16 bytes')
    pk = public_material(public_key)
    if recipient_id is not None and recipient_id != pk['nodeId']:
        raise ValueError('Falcon CL wrong recipient')
    r1, r2 = _uniform(N), _uniform(N)
    e1, e2, e3 = (_short(M) for _ in range(3))
    mu = np.zeros(M, dtype=np.int64)
    mu[:128] = np.unpackbits(np.frombuffer(payload_key, dtype=np.uint8))
    c1 = (pk['A'].T @ r1 + e1) % Q
    c2 = (pk['B'].T @ r2 + e2) % Q
    c3 = (pk['H_id'].T @ r1 + pk['U_id'].T @ r2 + e3 + (Q // 2) * mu) % Q
    return _b64(b'FCTV2' + struct.pack('<IIII', N, M, Q, 16) + np.asarray([c1, c2, c3], dtype='<i8').tobytes())


def decrypt(private_key, ciphertext, recipient_id=None):
    sk = parse_material(private_key, 'PRIVATE', recipient_id)
    c1, c2, c3 = decode_ciphertext(ciphertext)
    # Exact integer arithmetic; do not use the legacy object-id transpose cache.
    value = (c3 - sk['D_id'].T @ c1 - sk['S_id'].T @ c2) % Q
    half = Q // 2
    dist_half = np.minimum(np.abs(value - half), np.minimum(np.abs(value - half + Q), np.abs(value - half - Q)))
    bits = (dist_half < np.minimum(value, Q - value)).astype(np.uint8)
    return np.packbits(bits[:128]).tobytes()
