"""Gadget trapdoors, ExtBasis and GPV-style discrete Gaussian preimages.

Functional research profile, not a standardized encryption/signature scheme.
Kyber and Falcon remain the security primitives of the envelope protocol.
Private extended bases stay inside the KMS trust boundary.
"""
import hashlib
import math
import atexit
import multiprocessing
import os
import secrets
import threading
import time
from concurrent.futures import ProcessPoolExecutor, wait
from concurrent.futures.process import BrokenProcessPool

import numpy as np
from threadpoolctl import threadpool_limits

N, Q, K, MBAR, EXTRA = 16, 65537, 17, 304, 4
PROFILE = 'gadget-gpv-functional-v1'


def digest(matrix):
    return hashlib.sha256(np.asarray(matrix, dtype='<i8').tobytes()).hexdigest()


def uniform(shape, q=Q):
    count = math.prod(shape)
    values = []
    cutoff = (1 << 32) - (1 << 32) % q
    while len(values) < count:
        raw = np.frombuffer(secrets.token_bytes(4 * (count - len(values) + 16)), dtype='<u4')
        values.extend((raw[raw < cutoff] % q).tolist())
    return np.asarray(values[:count], dtype=np.int64).reshape(shape)


def bits(target):
    target = np.asarray(target, dtype=np.int64) % Q
    return ((target[:, None] >> np.arange(K)) & 1).reshape(N * K)


def gadget_basis():
    block = np.zeros((K, K), dtype=np.int64)
    for j in range(K - 1):
        block[j, j], block[j + 1, j] = 2, -1
    block[:, -1] = (Q >> np.arange(K)) & 1
    return np.kron(np.eye(N, dtype=np.int64), block)


def prepare(public, basis, r=None, parent=None):
    public, basis = np.asarray(public, dtype=np.int64), np.asarray(basis, dtype=np.int64)
    if public.shape[0] != N or basis.shape != (public.shape[1],) * 2:
        raise ValueError('格参数维度不一致')
    if np.any((public @ basis) % Q):
        raise ValueError('格基未通过模 q 零空间关系检查')
    with threadpool_limits(limits=1, user_api='blas'):
        orthogonal, triangular = np.linalg.qr(basis.astype(np.float64))
    diagonal = np.diag(triangular)
    if not np.all(np.isfinite(diagonal)) or np.min(np.abs(diagonal)) < 1e-8:
        raise ValueError('格基数值条件不足，拒绝采样')
    return dict(public=public, basis=basis, orthogonal=orthogonal, diagonal=diagonal,
                sigma=float(8 * np.max(np.abs(diagonal))), r=r, parent=parent,
                public_digest=digest(public))


def trapgen():
    """A=[Abar | G-Abar R], explicit full-rank kernel basis, det=q**n.

    The unimodular block transform maps [Abar|G] to A. The block gadget
    basis has determinant q per row, so its transformed columns span the
    entire q-ary kernel rather than merely a dependent subset.
    """
    abar = uniform((N, MBAR))
    r = uniform((MBAR, N * K), 3) - 1
    g = np.kron(np.eye(N, dtype=np.int64), 1 << np.arange(K))
    x = np.column_stack([bits(abar[:, j]) for j in range(MBAR)])
    s = gadget_basis()
    public = np.column_stack((abar, (g - abar @ r) % Q))
    basis = np.block([[np.eye(MBAR, dtype=np.int64) - r @ x, r @ s], [-x, s]])
    return prepare(public, basis, r=r)


def particular(context, target):
    if context['parent'] is not None:
        initial = particular(context['parent'], target)
        return np.concatenate((initial, np.zeros(EXTRA, dtype=np.int64)))
    z = bits(target)
    return np.concatenate((context['r'] @ z, z))


class RandomStream:
    def __init__(self):
        self.buffer = b''
        self.offset = 0

    def uint64(self):
        if self.offset + 8 > len(self.buffer):
            self.buffer, self.offset = secrets.token_bytes(8192), 0
        value = int.from_bytes(self.buffer[self.offset:self.offset + 8], 'little')
        self.offset += 8
        return value

    def below(self, width):
        limit = (1 << 64) - (1 << 64) % width
        while True:
            value = self.uint64()
            if value < limit:
                return value % width

    def unit(self):
        return ((self.uint64() >> 11) + 0.5) / (1 << 53)


def discrete_gaussian(center, deviation, source):
    # Rejection sampling of integers. This is not a rounded continuous normal.
    # Tails beyond 12 standard deviations are explicitly truncated.
    low, high = math.ceil(center - 12 * deviation), math.floor(center + 12 * deviation)
    for _ in range(10000):
        value = low + source.below(high - low + 1)
        if source.unit() < math.exp(-0.5 * ((value - center) / deviation) ** 2):
            return value
    raise RuntimeError('离散高斯采样未收敛')


def norm_bound(context):
    return float(2 * context['sigma'] * math.sqrt(context['public'].shape[1]))


def sample_pre(context, target):
    initial = particular(context, target)
    residual = initial.astype(np.float64)
    coefficients = np.zeros(len(initial), dtype=np.int64)
    source = RandomStream()
    for j in range(len(initial) - 1, -1, -1):
        center = float(residual @ context['orthogonal'][:, j] / context['diagonal'][j])
        z = discrete_gaussian(center, context['sigma'] / abs(context['diagonal'][j]), source)
        coefficients[j] = z
        residual -= z * context['basis'][:, j]
    result = initial - context['basis'] @ coefficients
    if not verify(context['public'], target, result, norm_bound(context)):
        raise ValueError('采样结果未通过整数关系或长度约束')
    return result


def delegate(root, node_id):
    # Bind the public extension to the exact node and root public matrix.
    domain = b'KMS-LATTICE-NODE-V1\0' + root['public_digest'].encode() + b'\0' + node_id.encode()
    extension = np.column_stack([target_for(domain + j.to_bytes(4, 'big')) for j in range(EXTRA)])
    x = np.column_stack([sample_pre(root, -extension[:, j] % Q) for j in range(EXTRA)])
    dimension = root['basis'].shape[0]
    basis = np.block([[root['basis'], x], [np.zeros((EXTRA, dimension), dtype=np.int64), np.eye(EXTRA, dtype=np.int64)]])
    result = prepare(np.column_stack((root['public'], extension)), basis, parent=root)
    result['node_id'] = node_id
    return result


def target_for(message):
    # Hash-to-Z_q^n with rejection sampling and domain separation.
    values, counter = [], 0
    cutoff = (1 << 32) - (1 << 32) % Q
    while len(values) < N:
        raw = hashlib.shake_256(b'KMS-LATTICE-ENVELOPE-V1\0' + message + counter.to_bytes(4, 'big')).digest(64)
        words = np.frombuffer(raw, dtype='<u4')
        values.extend((words[words < cutoff] % Q).tolist())
        counter += 1
    return np.asarray(values[:N], dtype=np.int64)


def verify(public, target, vector, bound):
    vector = np.asarray(vector)
    return bool(vector.shape == (public.shape[1],) and np.issubdtype(vector.dtype, np.integer)
                and np.max(np.abs(vector)) < 10**7 and math.isfinite(bound) and bound > 0
                and np.linalg.norm(vector) <= bound and np.array_equal(public @ vector % Q, target % Q))


_pool_lock = threading.Lock()
_pool_owner = os.getpid()
_sampling_pool = None
_pool_context = None
_worker_context = None
_worker_blas_limit = None
_worker_ready_barrier = None


def _initialize_sampler(context, ready_barrier):
    # spawn imports only this numerical module, without inheriting Django DB
    # sockets. Each process receives the private context once, never per vector.
    global _worker_context, _worker_blas_limit, _worker_ready_barrier
    _worker_context = context
    _worker_blas_limit = threadpool_limits(limits=1, user_api='blas')
    _worker_ready_barrier = ready_barrier


def _sampler_ready():
    _worker_ready_barrier.wait(timeout=30)
    return os.getpid()


def _sample_chunk(indexed_messages, epoch):
    rows = []
    for index, message in indexed_messages:
        began = time.perf_counter()
        vector = sample_pre(_worker_context, target_for(message))
        rows.append((index, vector, dict(worker=f'process-{os.getpid()}', kind='process',
            startMs=(began - epoch) * 1000, endMs=(time.perf_counter() - epoch) * 1000)))
    return rows


def shutdown_sampling_pool():
    global _sampling_pool, _pool_context
    pool, _sampling_pool, _pool_context = _sampling_pool, None, None
    if pool is not None:
        pool.shutdown(wait=True, cancel_futures=True)


def _get_sampling_pool(context):
    global _sampling_pool, _pool_context
    if _sampling_pool is not None and _pool_context is context:
        return _sampling_pool, True
    shutdown_sampling_pool()
    # One bounded pool per Django worker. Different concurrency settings reuse
    # it; submitting N chunks limits the active sampling processes to N.
    spawn = multiprocessing.get_context('spawn')
    size = min(8, len(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else os.cpu_count() or 1)
    pool = ProcessPoolExecutor(max_workers=size, mp_context=spawn,
        initializer=_initialize_sampler, initargs=(context, spawn.Barrier(size)))
    try:
        # Start every child and wait for its initializer before accepting a
        # request. This avoids a request racing the first context load.
        futures = [pool.submit(_sampler_ready) for _ in range(size)]
        for future in futures:
            future.result(timeout=30)
    except BaseException:
        pool.shutdown(wait=True, cancel_futures=True)
        raise
    _sampling_pool, _pool_context = pool, context
    return pool, False


def sample_parallel(context, messages, workers=4, metrics=None):
    global _pool_owner, _pool_lock, _sampling_pool, _pool_context
    if not messages or type(workers) is not int or not 1 <= workers <= 8:
        raise ValueError('采样批次或并发数无效')
    if _pool_owner != os.getpid():
        # A forked web worker must not reuse its parent's pool or lock.
        _pool_owner, _pool_lock = os.getpid(), threading.Lock()
        _sampling_pool, _pool_context = None, None
    waiting = time.perf_counter()
    with _pool_lock:
        queue_ms = (time.perf_counter() - waiting) * 1000
        preparation = time.perf_counter()
        pool, reused = _get_sampling_pool(context)
        setup_ms = (time.perf_counter() - preparation) * 1000
        epoch = time.perf_counter()
        indexed = list(enumerate(messages))
        lanes = min(workers, len(indexed), pool._max_workers)
        futures = []
        try:
            for i in range(lanes):
                futures.append(pool.submit(_sample_chunk, indexed[i::lanes], epoch))
            rows = sorted((row for future in futures for row in future.result()), key=lambda row: row[0])
        except BaseException as error:
            for future in futures:
                future.cancel()
            wait(futures)
            if isinstance(error, BrokenProcessPool):
                shutdown_sampling_pool()
            raise
        compute_ms = (time.perf_counter() - epoch) * 1000
    spans = [row[2] for row in rows]
    boundaries = sorted([(s['startMs'], 1) for s in spans] + [(s['endMs'], -1) for s in spans])
    active = peak = 0
    for _, delta in boundaries:
        active += delta
        peak = max(peak, active)
    if metrics is not None:
        metrics.update(usedWorkers=len({s['worker'] for s in spans}), peakInFlight=peak, spans=spans,
            executionMode='process', poolReused=reused, poolSetupMs=setup_ms, queueMs=queue_ms, computeMs=compute_ms)
    return [row[1] for row in rows]


atexit.register(shutdown_sampling_pool)
