# -*- coding: utf-8 -*-
"""
Kyber 无证书格密码加速引擎

实现图中的 Enc / Dec 算法:

Enc: 选取随机 r ← χ^n, e₁ ← χ^m, e₂ ← χ
  c₁ = Aᵗ · r + e₁          (mod q)   ∈ Z_q^m
  c₂ = uᵗ · r + e₂ + ⌊q/2⌋·M  (mod q)   ∈ Z_q

Dec: 用 sk = s̄ 解密
  M = ⌊(c₂ − s̄ᵗ · c₁) / (q/2)⌋

其中:
  A  ∈ Z_q^{n×m}  系统公共参数
  u  ∈ Z_q^n       无证书公钥 (= u'_id + U₀·c + A·s_id)
  s̄  ∈ Z_q^m       无证书私钥 (= t + s_id)
"""
import numpy as np
import base64
import hashlib
import logging
import struct
import threading
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)

# ================================================================
#  快速 Enc / Dec（向量化，无 Python for 循环）
# ================================================================

# 缓存 A.T 的 float64 版本，避免每次调用都转换
_AT_cache: Dict[int, np.ndarray] = {}
_AT_lock = threading.Lock()


def _get_AT_float64(A: np.ndarray) -> np.ndarray:
    """获取 A.T 的 float64 缓存版本"""
    key = id(A)
    with _AT_lock:
        if key in _AT_cache:
            return _AT_cache[key]
    AT = np.ascontiguousarray(A.T.astype(np.float64))
    with _AT_lock:
        _AT_cache[key] = AT
    return AT


# 缓存 float64 向量，避免每次调用都转换
_vec_f64_cache: Dict[int, np.ndarray] = {}
_vec_f64_lock = threading.Lock()


def _get_vec_float64(v: np.ndarray) -> np.ndarray:
    """获取向量的 float64 缓存版本"""
    key = id(v)
    with _vec_f64_lock:
        if key in _vec_f64_cache:
            return _vec_f64_cache[key]
    vf = np.ascontiguousarray(v.astype(np.float64))
    with _vec_f64_lock:
        _vec_f64_cache[key] = vf
    return vf


def kyber_fast_encrypt(A: np.ndarray, u: np.ndarray,
                       session_key: bytes,
                       n: int, m: int, q: int, sigma: float) -> dict:
    """
    图中 Enc 算法的向量化实现 (单向量模式)。

    将 AES 密钥编码为 m 维比特向量, 用单个随机向量 r 加密:
      c₁ = Aᵗ · r + e₁   (mod q)   ∈ Z_q^m
      c₂ = uᵗ · r + e₂ + ⌊q/2⌋·M  (mod q)   ∈ Z_q^m (前 256 位有效)
    """
    half_q = q // 2

    # 编码消息为 m 维比特向量
    bits = np.unpackbits(np.frombuffer(session_key, dtype=np.uint8))
    mu = np.zeros(m, dtype=np.float64)
    mu[:len(bits)] = bits[:m]

    # 单向量抽样
    r = np.random.uniform(0, q, size=n)
    np.round(r, out=r)
    e1 = np.round(np.random.normal(0, sigma, size=m))
    e2 = np.round(np.random.normal(0, sigma, size=m))

    # 使用 float64 BLAS 加速 + 缓存
    AT_f = _get_AT_float64(A)
    u_f = _get_vec_float64(u)

    # c₁ = Aᵗ · r + e₁  (m,)
    C1 = (AT_f @ r + e1).astype(np.int64) % q

    # c₂ = uᵗ · r + e₂ + ⌊q/2⌋·M  (m,)
    # 注意: u 是 n 维向量, uᵗ·r 是标量, 广播到 m 维
    u_dot_r = u_f @ r
    C2 = (u_dot_r + e2 + half_q * mu).astype(np.int64) % q

    return {
        'C1': C1,       # m, int64
        'C2': C2,       # m, int64
        'n': n, 'm': m, 'q': q,
        'key_length': len(session_key),
    }


def kyber_fast_decrypt(C1: np.ndarray, C2: np.ndarray,
                       sk: np.ndarray,
                       q: int, key_length: int) -> bytes:
    """
    图中 Dec 算法的向量化实现 (单向量模式)。
      M = ⌊(c₂ − s̄ᵗ · c₁) / (q/2)⌋

    sk = s̄ 是短向量（离散高斯采样，|系数| ≤ O(σ√m)）
    C1: m 维向量 ∈ Z_q^m
    C2: m 维向量 ∈ Z_q^m（每个分量对应一个比特的密文）
    """
    half_q = q // 2

    # 使用 float64 BLAS 加速 + 缓存
    sk_f = _get_vec_float64(sk)
    C1_f = C1.astype(np.float64) if C1.dtype != np.float64 else C1

    # s̄ᵗ · c₁ → 标量
    term = int(sk_f @ C1_f) % q

    # mu' = C2 - s̄ᵗ · c₁  mod q  (m 维)
    C2_i = C2.astype(np.int64) if C2.dtype != np.int64 else C2
    mu_prime = (C2_i - term) % q

    # rounding: 距 q/2 近 → 1, 距 0 近 → 0
    dist_to_half = np.minimum(
        np.abs(mu_prime - half_q),
        np.minimum(np.abs(mu_prime - half_q + q), np.abs(mu_prime - half_q - q))
    )
    dist_to_zero = np.minimum(mu_prime, q - mu_prime)
    bits = (dist_to_half < dist_to_zero).astype(np.uint8)

    # 比特 → 字节
    n_bits = key_length * 8
    key_bits = bits[:n_bits]
    pad_len = (8 - len(key_bits) % 8) % 8
    if pad_len:
        key_bits = np.concatenate([key_bits, np.zeros(pad_len, dtype=np.uint8)])
    return np.packbits(key_bits).tobytes()[:key_length]


# ================================================================
#  二进制密文序列化 / 反序列化
# ================================================================

_CT_MAGIC_KYBER = b'KCTV2'  # V2: 单向量模式

def _serialize_kyber_ct(ct: dict) -> str:
    """将 Kyber 密文序列化为 base64 (V2: 单向量模式)"""
    C1 = ct['C1'].astype(np.int64)
    C2 = ct['C2'].astype(np.int64)
    m = len(C1)
    q = ct['q']
    key_length = ct['key_length']
    # header: magic(5) + m(4) + q(4) + key_length(4) = 17
    header = _CT_MAGIC_KYBER + struct.pack('<III', m, q, key_length)
    payload = header + C1.tobytes() + C2.tobytes()
    return base64.b64encode(payload).decode('ascii')


def _deserialize_kyber_ct(ct_b64: str):
    """反序列化 Kyber 密文，返回 (C1, C2, q, key_length)"""
    raw = base64.b64decode(ct_b64)
    if raw[:5] == _CT_MAGIC_KYBER:
        m, q, key_length = struct.unpack('<III', raw[5:17])
        offset = 17
        elem_size = m * 8
        C1 = np.frombuffer(raw[offset:offset+elem_size], dtype=np.int64).copy()
        offset += elem_size
        C2 = np.frombuffer(raw[offset:offset+elem_size], dtype=np.int64).copy()
        return C1, C2, q, key_length
    # 兼容 V1 格式 (矩阵模式)
    if raw[:5] == b'KCTV1':
        m, num_bits, q, key_length = struct.unpack('<IIII', raw[5:21])
        offset = 21
        C1_size = m * num_bits * 8
        C1 = np.frombuffer(raw[offset:offset+C1_size], dtype=np.int64).reshape(m, num_bits).copy()
        offset += C1_size
        C2 = np.frombuffer(raw[offset:offset+num_bits*8], dtype=np.int64).copy()
        return C1, C2, q, key_length
    raise ValueError("未知的 Kyber 密文格式")


# ================================================================
#  无证书 Kyber 公钥/私钥缓存
# ================================================================

class _KyberCLKeyCache:
    """缓存解析后的无证书层 numpy 密钥，避免重复 JSON 解析"""
    _pk_cache: Dict[str, dict] = {}
    _sk_cache: Dict[str, dict] = {}
    _lock = threading.Lock()

    @classmethod
    def get_cl_public_key(cls, partial_key_data_json: str) -> dict:
        """从 kyber_partial_key_data JSON 中提取 A, u (cl_public_key)"""
        h = hashlib.sha256(partial_key_data_json[:64].encode()).hexdigest()
        with cls._lock:
            if h in cls._pk_cache:
                return cls._pk_cache[h]
        import json
        data = json.loads(partial_key_data_json)
        result = {
            'A': np.array(data['A'], dtype=np.int64),
            'u': np.array(data['cl_public_key'], dtype=np.int64),
            'n': data.get('parameters', {}).get('n', 512),
            'm': data.get('parameters', {}).get('m', 1024),
            'q': data.get('parameters', {}).get('q', 12289),
        }
        with cls._lock:
            cls._pk_cache[h] = result
        return result

    @classmethod
    def get_cl_private_key(cls, partial_key_data_json: str) -> dict:
        """从 kyber_partial_key_data JSON 中提取 s̄ (cl_private_key)"""
        h = hashlib.sha256(partial_key_data_json[:64].encode()).hexdigest()
        with cls._lock:
            if h in cls._sk_cache:
                return cls._sk_cache[h]
        import json
        data = json.loads(partial_key_data_json)
        result = {
            'sk': np.array(data['cl_private_key'], dtype=np.int64),
            'n': data.get('parameters', {}).get('n', 512),
            'm': data.get('parameters', {}).get('m', 1024),
            'q': data.get('parameters', {}).get('q', 12289),
        }
        with cls._lock:
            cls._sk_cache[h] = result
        return result

    @classmethod
    def clear(cls):
        with cls._lock:
            cls._pk_cache.clear()
            cls._sk_cache.clear()
