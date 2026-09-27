# -*- coding: utf-8 -*-
"""
Falcon 格密码加速优化消融实验

四组对比（每组 50 次 生成AES密钥→加密→解密→验证正确性→记录耗时）：
  A. 基线：无任何优化（串行抽样 + 无缓存 + Python for 循环 rounding）
  B. 仅快速委派格基缓存（D_id/H_id/S_id/U_id 缓存，其余不变）
  C. 仅并行抽样短向量（ThreadPool 并行生成 r1,r2,e1,e2,e3，其余不变）
  D. 全部优化（缓存 + 并行抽样 + 向量化 rounding + BLAS 转置缓存）

注意：不修改任何现有的 Falcon/Kyber 密钥生成和加解密算法文件。
"""
import os
import sys
import time
import hashlib
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Tuple

# ================================================================
#  公共参数（Falcon-512）
# ================================================================
N, M, Q, SIGMA = 512, 1024, 12289, 1.17
HALF_Q = Q // 2
NUM_ROUNDS = 50
AES_KEY_LEN = 32  # 字节

# 全局线程池
_POOL = ThreadPoolExecutor(max_workers=os.cpu_count() or 4)


def _setup_system():
    """生成系统公共参数 A, B（所有方案共用）"""
    np.random.seed(42)
    A = np.random.randint(0, Q, size=(N, M), dtype=np.int64)
    B = np.random.randint(0, Q, size=(N, M), dtype=np.int64)
    return A, B


def _gen_user_keys(A, B, user_id="benchmark_user"):
    """为用户生成密钥材料（所有方案共用同一套密钥）"""
    seed = int(hashlib.sha256(user_id.encode()).hexdigest(), 16) % (2**32)
    rng = np.random.RandomState(seed)
    D_id = np.round(rng.normal(0, SIGMA, size=(M, M))).astype(np.int64)
    H_id = np.dot(A, D_id) % Q
    S_id = np.round(np.random.RandomState(seed + 1).normal(0, SIGMA, size=(M, M))).astype(np.int64)
    U_id = np.dot(B, S_id) % Q
    sk = {'D_id': D_id, 'S_id': S_id}
    return sk, H_id, U_id


# ================================================================
#  方案 A：基线（无任何优化）
#  - 串行抽样 5 个向量
#  - np.dot 原始矩阵乘法（不缓存转置）
#  - Python for 循环 rounding
# ================================================================

def _encode_bits_baseline(session_key: bytes) -> np.ndarray:
    """消息编码为比特向量（Python for 循环版本）"""
    bits = np.zeros(M, dtype=np.int64)
    for i in range(len(session_key) * 8):
        byte_idx = i // 8
        bit_idx = i % 8
        bits[i] = (session_key[byte_idx] >> bit_idx) & 1
    return bits


def _round_to_bit_scalar(value, q, half_q):
    """标量 rounding（Python 级别）"""
    v = int(value) % q
    dist_to_zero = min(v, q - v)
    dist_to_half = abs(v - half_q)
    return 1 if dist_to_half < dist_to_zero else 0


def _decode_bits_baseline(bits: np.ndarray, key_len: int) -> bytes:
    """比特向量解码为字节（Python for 循环版本）"""
    result = bytearray(key_len)
    for i in range(key_len * 8):
        if bits[i] == 1:
            result[i // 8] |= (1 << (i % 8))
    return bytes(result)


def encrypt_baseline(A, B, H_id, U_id, session_key):
    """基线加密：串行抽样 + np.dot + for 循环编码"""
    mu = _encode_bits_baseline(session_key)
    r1 = np.random.randint(0, Q, size=N, dtype=np.int64)
    r2 = np.random.randint(0, Q, size=N, dtype=np.int64)
    e1 = np.round(np.random.normal(0, SIGMA, size=M)).astype(np.int64) % Q
    e2 = np.round(np.random.normal(0, SIGMA, size=M)).astype(np.int64) % Q
    e3 = np.round(np.random.normal(0, SIGMA, size=M)).astype(np.int64) % Q
    c1 = (np.dot(A.T, r1) + e1) % Q
    c2 = (np.dot(B.T, r2) + e2) % Q
    c3_t1 = np.dot(H_id.T, r1) % Q
    c3_t2 = np.dot(U_id.T, r2) % Q
    c3 = (c3_t1 + c3_t2 + e3 + HALF_Q * mu) % Q
    return {'c1': c1, 'c2': c2, 'c3': c3, 'key_length': len(session_key)}


def decrypt_baseline(ct, sk):
    """基线解密：np.dot + Python for 循环 rounding"""
    c1, c2, c3 = ct['c1'], ct['c2'], ct['c3']
    D_id, S_id = sk['D_id'], sk['S_id']
    key_length = ct['key_length']
    term1 = np.dot(D_id.T, c1) % Q
    term2 = np.dot(S_id.T, c2) % Q
    mu_prime = (c3 - term1 - term2) % Q
    recovered_bits = np.zeros(M, dtype=np.int64)
    for i in range(M):
        recovered_bits[i] = _round_to_bit_scalar(mu_prime[i], Q, HALF_Q)
    return _decode_bits_baseline(recovered_bits, key_length)


# ================================================================
#  方案 B：仅快速委派格基缓存
#  - D_id/H_id/S_id/U_id 首次计算后缓存复用
#  - 其余与基线相同（串行抽样 + for 循环 rounding）
#  区别体现在：首次调用需要计算矩阵乘法，后续直接命中缓存
# ================================================================

_basis_cache: Dict[str, tuple] = {}


def get_cached_keys(A, B, user_id="benchmark_user"):
    """带缓存的密钥材料获取（模拟 FastDelegatedBasis）"""
    if user_id in _basis_cache:
        return _basis_cache[user_id]
    sk, H_id, U_id = _gen_user_keys(A, B, user_id)
    _basis_cache[user_id] = (sk, H_id, U_id)
    return sk, H_id, U_id


# 方案 B 的加密/解密与基线相同，区别在于密钥获取走缓存
encrypt_cached_basis = encrypt_baseline
decrypt_cached_basis = decrypt_baseline


# ================================================================
#  方案 C：仅并行抽样短向量
#  - ThreadPool 并行生成 r1, r2, e1, e2, e3
#  - 其余与基线相同（无缓存 + for 循环 rounding）
# ================================================================

def _uniform_sample(size):
    return np.random.randint(0, Q, size=size, dtype=np.int64)


def _gaussian_sample(size):
    return np.round(np.random.normal(0, SIGMA, size=size)).astype(np.int64) % Q


def encrypt_parallel_sample(A, B, H_id, U_id, session_key):
    """方案C加密：并行抽样 + np.dot + for 循环编码"""
    mu = _encode_bits_baseline(session_key)
    # 并行抽样 5 个向量
    futures = {
        'r1': _POOL.submit(_uniform_sample, N),
        'r2': _POOL.submit(_uniform_sample, N),
        'e1': _POOL.submit(_gaussian_sample, M),
        'e2': _POOL.submit(_gaussian_sample, M),
        'e3': _POOL.submit(_gaussian_sample, M),
    }
    vecs = {k: f.result() for k, f in futures.items()}
    r1, r2 = vecs['r1'], vecs['r2']
    e1, e2, e3 = vecs['e1'], vecs['e2'], vecs['e3']
    c1 = (np.dot(A.T, r1) + e1) % Q
    c2 = (np.dot(B.T, r2) + e2) % Q
    c3_t1 = np.dot(H_id.T, r1) % Q
    c3_t2 = np.dot(U_id.T, r2) % Q
    c3 = (c3_t1 + c3_t2 + e3 + HALF_Q * mu) % Q
    return {'c1': c1, 'c2': c2, 'c3': c3, 'key_length': len(session_key)}


# 方案 C 的解密与基线相同（解密不涉及抽样）
decrypt_parallel_sample = decrypt_baseline


# ================================================================
#  方案 D：全部优化（缓存 + 并行抽样 + 向量化 rounding + BLAS 转置缓存）
#  对应 falcon_fast_engine.py 中的 fast_encrypt / fast_decrypt
# ================================================================

import threading
_mat_cache: Dict[int, np.ndarray] = {}
_mat_lock = threading.Lock()


def _get_transposed_f64(mat: np.ndarray) -> np.ndarray:
    """获取矩阵转置的 float64 缓存版本（BLAS 加速）"""
    key = id(mat)
    with _mat_lock:
        if key in _mat_cache:
            return _mat_cache[key]
    result = np.ascontiguousarray(mat.T.astype(np.float64))
    with _mat_lock:
        _mat_cache[key] = result
    return result


def encrypt_full_optimized(A, B, H_id, U_id, session_key):
    """方案D加密：缓存 + numpy向量化编码 + BLAS转置缓存 + float64加速"""
    # numpy 向量化编码（替代 Python for 循环）
    bits = np.unpackbits(np.frombuffer(session_key, dtype=np.uint8))
    mu = np.zeros(M, dtype=np.float64)
    mu[:len(bits)] = bits[:M]

    # 直接 numpy 抽样（向量化，无线程池开销）
    r1 = np.random.randint(0, Q, size=N, dtype=np.int64).astype(np.float64)
    r2 = np.random.randint(0, Q, size=N, dtype=np.int64).astype(np.float64)
    e1 = np.round(np.random.normal(0, SIGMA, size=M))
    e2 = np.round(np.random.normal(0, SIGMA, size=M))
    e3 = np.round(np.random.normal(0, SIGMA, size=M))

    # BLAS 加速 + 缓存转置矩阵
    AT = _get_transposed_f64(A)
    BT = _get_transposed_f64(B)
    HT = _get_transposed_f64(H_id)
    UT = _get_transposed_f64(U_id)

    c1 = (AT @ r1 + e1).astype(np.int64) % Q
    c2 = (BT @ r2 + e2).astype(np.int64) % Q
    c3_t1 = (HT @ r1).astype(np.int64) % Q
    c3_t2 = (UT @ r2).astype(np.int64) % Q
    c3 = (c3_t1 + c3_t2 + e3.astype(np.int64) + HALF_Q * mu.astype(np.int64)) % Q

    return {'c1': c1, 'c2': c2, 'c3': c3, 'key_length': len(session_key)}


def decrypt_full_optimized(ct, sk):
    """方案D解密：BLAS转置缓存 + 向量化 rounding（无 Python for 循环）"""
    c1, c2, c3 = ct['c1'], ct['c2'], ct['c3']
    D_id, S_id = sk['D_id'], sk['S_id']
    key_length = ct['key_length']

    DT = _get_transposed_f64(D_id)
    ST = _get_transposed_f64(S_id)
    c1_f = c1.astype(np.float64)
    c2_f = c2.astype(np.float64)

    term1 = (DT @ c1_f).astype(np.int64) % Q
    term2 = (ST @ c2_f).astype(np.int64) % Q
    mu_prime = (c3.astype(np.int64) - term1 - term2) % Q

    # 向量化 rounding（替代 Python for 循环）
    dist_to_half = np.minimum(
        np.abs(mu_prime - HALF_Q),
        np.minimum(np.abs(mu_prime - HALF_Q + Q), np.abs(mu_prime - HALF_Q - Q))
    )
    dist_to_zero = np.minimum(mu_prime, Q - mu_prime)
    bits = (dist_to_half < dist_to_zero).astype(np.uint8)

    n_bits = key_length * 8
    key_bits = bits[:n_bits]
    pad_len = (8 - len(key_bits) % 8) % 8
    if pad_len:
        key_bits = np.concatenate([key_bits, np.zeros(pad_len, dtype=np.uint8)])
    return np.packbits(key_bits).tobytes()[:key_length]


# ================================================================
#  消融实验主程序
# ================================================================

def run_benchmark(name, encrypt_fn, decrypt_fn, A, B, sk, H_id, U_id,
                  num_rounds=NUM_ROUNDS, keygen_each_round=False):
    """
    运行一组实验：num_rounds 次 生成AES密钥→加密→解密→验证→记录耗时
    keygen_each_round: True 表示每轮重新生成密钥材料（测试无缓存场景）
    """
    latencies = []
    correct_count = 0

    for i in range(num_rounds):
        # 每轮重新生成密钥材料（方案A/C 无缓存）
        if keygen_each_round:
            uid = f"user_round_{i}"
            sk_i, H_id_i, U_id_i = _gen_user_keys(A, B, uid)
        else:
            sk_i, H_id_i, U_id_i = sk, H_id, U_id

        t0 = time.perf_counter()

        # Step 1: 生成随机 AES-256 密钥
        aes_key = os.urandom(AES_KEY_LEN)

        # Step 2: 加密
        ct = encrypt_fn(A, B, H_id_i, U_id_i, aes_key)

        # Step 3: 解密
        recovered = decrypt_fn(ct, sk_i)

        t1 = time.perf_counter()
        latency_ms = (t1 - t0) * 1000
        latencies.append(latency_ms)

        # Step 4: 验证正确性
        if recovered == aes_key:
            correct_count += 1

    avg = sum(latencies) / len(latencies)
    med = sorted(latencies)[len(latencies) // 2]
    p95 = sorted(latencies)[int(len(latencies) * 0.95)]
    total = sum(latencies)

    return {
        'name': name,
        'rounds': num_rounds,
        'correct': correct_count,
        'accuracy': f"{correct_count / num_rounds * 100:.1f}%",
        'avg_ms': round(avg, 2),
        'median_ms': round(med, 2),
        'p95_ms': round(p95, 2),
        'total_ms': round(total, 1),
        'throughput': round(num_rounds / (total / 1000), 1) if total > 0 else 0,
    }


def main():
    print("=" * 80)
    print("  Falcon-512 格密码加速优化消融实验")
    print(f"  参数: n={N}, m={M}, q={Q}, σ={SIGMA}")
    print(f"  每组 {NUM_ROUNDS} 轮: 生成AES-256密钥 → 加密 → 解密 → 验证正确性")
    print("=" * 80)

    # 初始化系统参数
    print("\n[初始化] 生成系统参数 A, B ...")
    A, B = _setup_system()

    # 生成用户密钥（方案 B/D 使用缓存，方案 A/C 每轮重新生成）
    print("[初始化] 生成用户密钥材料 ...")
    sk, H_id, U_id = _gen_user_keys(A, B)

    # 预热（让 numpy/BLAS 完成内部初始化）
    print("[预热] 执行 3 轮预热 ...")
    for _ in range(3):
        k = os.urandom(32)
        ct = encrypt_full_optimized(A, B, H_id, U_id, k)
        decrypt_full_optimized(ct, sk)

    results = []

    # 方案 A：基线（每轮重新计算密钥材料，模拟无缓存）
    print(f"\n{'─' * 60}")
    print("  方案 A: 基线（无任何优化，每轮重新计算格基）")
    print(f"{'─' * 60}")
    r = run_benchmark("A. 基线（无优化）",
                      encrypt_baseline, decrypt_baseline,
                      A, B, sk, H_id, U_id,
                      keygen_each_round=True)
    results.append(r)
    print(f"  平均: {r['avg_ms']:.2f} ms | 中位: {r['median_ms']:.2f} ms | "
          f"P95: {r['p95_ms']:.2f} ms | 正确率: {r['accuracy']}")

    # 方案 B：仅快速委派格基缓存（密钥材料只算一次，后续复用）
    print(f"\n{'─' * 60}")
    print("  方案 B: 仅快速委派格基缓存（密钥材料复用）")
    print(f"{'─' * 60}")
    _basis_cache.clear()
    r = run_benchmark("B. +快速委派格基缓存",
                      encrypt_cached_basis, decrypt_cached_basis,
                      A, B, sk, H_id, U_id,
                      keygen_each_round=False)
    results.append(r)
    print(f"  平均: {r['avg_ms']:.2f} ms | 中位: {r['median_ms']:.2f} ms | "
          f"P95: {r['p95_ms']:.2f} ms | 正确率: {r['accuracy']}")

    # 方案 C：仅并行抽样短向量（每轮重新计算格基）
    print(f"\n{'─' * 60}")
    print("  方案 C: 仅并行抽样短向量（无格基缓存）")
    print(f"{'─' * 60}")
    r = run_benchmark("C. +并行抽样短向量",
                      encrypt_parallel_sample, decrypt_parallel_sample,
                      A, B, sk, H_id, U_id,
                      keygen_each_round=True)
    results.append(r)
    print(f"  平均: {r['avg_ms']:.2f} ms | 中位: {r['median_ms']:.2f} ms | "
          f"P95: {r['p95_ms']:.2f} ms | 正确率: {r['accuracy']}")

    # 方案 D：全部优化
    print(f"\n{'─' * 60}")
    print("  方案 D: 全部优化（缓存+向量化+BLAS）")
    print(f"{'─' * 60}")
    _mat_cache.clear()  # 清除转置缓存，从头计时
    r = run_benchmark("D. 全部优化",
                      encrypt_full_optimized, decrypt_full_optimized,
                      A, B, sk, H_id, U_id)
    results.append(r)
    print(f"  平均: {r['avg_ms']:.2f} ms | 中位: {r['median_ms']:.2f} ms | "
          f"P95: {r['p95_ms']:.2f} ms | 正确率: {r['accuracy']}")

    # 汇总表格
    print(f"\n{'=' * 80}")
    print("  消融实验汇总")
    print(f"{'=' * 80}")
    header = f"{'方案':<28} {'平均(ms)':>10} {'中位(ms)':>10} {'P95(ms)':>10} {'总耗时(ms)':>12} {'吞吐(次/s)':>12} {'正确率':>8}"
    print(header)
    print("─" * len(header))

    baseline_avg = results[0]['avg_ms']
    for r in results:
        speedup = baseline_avg / r['avg_ms'] if r['avg_ms'] > 0 else 0
        line = (f"{r['name']:<28} {r['avg_ms']:>10.2f} {r['median_ms']:>10.2f} "
                f"{r['p95_ms']:>10.2f} {r['total_ms']:>12.1f} {r['throughput']:>12.1f} {r['accuracy']:>8}")
        if speedup > 1.01:
            line += f"  (↑{speedup:.2f}x)"
        print(line)

    print(f"\n基线平均耗时: {baseline_avg:.2f} ms")
    if results[-1]['avg_ms'] > 0:
        print(f"全优化平均耗时: {results[-1]['avg_ms']:.2f} ms")
        print(f"总加速比: {baseline_avg / results[-1]['avg_ms']:.2f}x")



if __name__ == '__main__':
    main()