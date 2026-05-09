import numpy as np
import hashlib
import logging
from typing import Dict, Any, Tuple
import threading

logger = logging.getLogger(__name__)

def fast_matrix_multiply_mod(A: np.ndarray, B: np.ndarray, q: int) -> np.ndarray:
    result = np.dot(A, B) % q
    return result

def fast_vector_multiply_mod(A: np.ndarray, v: np.ndarray, q: int) -> np.ndarray:
    result = np.dot(A, v) % q
    return result

def fast_gaussian_sample_jit(size: int, q: int, sigma: float = 1.17) -> np.ndarray:
    result = np.random.normal(0, sigma, size=size).astype(np.int64) % q
    return result

class OptimizedKyberKeygen:
    def __init__(self, n: int = 512, m: int = 1024, q: int = 12289, sigma: float = 1.17):
        self.n = n
        self.m = m
        self.q = q
        self.sigma = sigma
        self.sigma_int = int(sigma * 1000)

        self.A_cache = None
        self.S_0_cache = None
        self.U_0_cache = None
        self.hash_cache = {}
        self.lock = threading.Lock()

    def setup_cached(self) -> Dict[str, np.ndarray]:
        if self.A_cache is not None:
            return {
                'A': self.A_cache,
                'S_0': self.S_0_cache,
                'U_0': self.U_0_cache
            }

        self.A_cache = np.random.randint(0, self.q, size=(self.n, self.m), dtype=np.int64)
        self.S_0_cache = np.random.randint(0, 2, size=(self.m, self.m), dtype=np.int64)
        self.U_0_cache = fast_matrix_multiply_mod(self.A_cache, self.S_0_cache, self.q)

        return {
            'A': self.A_cache,
            'S_0': self.S_0_cache,
            'U_0': self.U_0_cache
        }

    def _fast_hash_to_vector(self, user_id: str) -> np.ndarray:
        if user_id in self.hash_cache:
            return self.hash_cache[user_id]

        h = hashlib.sha256(user_id.encode()).digest()
        extended = h
        while len(extended) < self.m:
            extended += hashlib.sha256(extended).digest()

        c = np.frombuffer(extended[:self.m], dtype=np.uint8) % 3 - 1
        c = c.astype(np.int64)

        self.hash_cache[user_id] = c
        return c

    def _fast_gaussian_sample(self, size: int) -> np.ndarray:
        return fast_gaussian_sample_jit(size, self.q, self.sigma)

    def partial_key_gen_fast(self, user_id: str, params: Dict) -> Tuple[np.ndarray, np.ndarray]:
        A = params['A']
        S_0 = params['S_0']

        s_prime_id = self._fast_gaussian_sample(self.m)
        u_prime_id = fast_vector_multiply_mod(A, s_prime_id, self.q)
        c = self._fast_hash_to_vector(user_id)
        S_0_c = fast_vector_multiply_mod(S_0, c, self.q)
        t = (s_prime_id + S_0_c) % self.q

        return t, c, u_prime_id

    def set_secret_value_fast(self) -> np.ndarray:
        return self._fast_gaussian_sample(self.m)

    def set_sk_fast(self, t: np.ndarray, s_id: np.ndarray) -> np.ndarray:
        return (t + s_id) % self.q

    def set_pk_fast(self, u_prime_id: np.ndarray, c: np.ndarray, s_id: np.ndarray, params: Dict) -> np.ndarray:
        U_0 = params['U_0']
        A = params['A']

        U0_c = fast_vector_multiply_mod(U_0, c, self.q)
        A_sid = fast_vector_multiply_mod(A, s_id, self.q)
        pk = (u_prime_id + U0_c + A_sid) % self.q

        return pk

    def generate_keypair_fast(self, user_id: str) -> Dict[str, Any]:
        params = self.setup_cached()

        t, c, u_prime_id = self.partial_key_gen_fast(user_id, params)
        s_id = self.set_secret_value_fast()
        sk = self.set_sk_fast(t, s_id)
        pk = self.set_pk_fast(u_prime_id, c, s_id, params)

        return {
            'sk': sk,
            'pk': pk,
            't': t,
            'c': c,
            's_id': s_id,
            'u_prime_id': u_prime_id
        }



# Falcon-512 和 Falcon-1024 的格密码参数
FALCON_PARAMS = {
    512: {'n': 512, 'm': 1024, 'q': 12289},
    1024: {'n': 1024, 'm': 2048, 'q': 12289},
}


class OptimizedFalconKeygen:
    """
    Falcon 无证书格密码密钥生成器（与 CertificatelessFalconStrict 数学一致）。

    D_id: m×m 短矩阵（离散高斯），确定性生成（从 node_id 派生种子）
    H_id = A·D_id mod q
    S_id: m×m 短矩阵（离散高斯）
    U_id = B·S_id mod q
    """

    def __init__(self, n: int = 512, m: int = 1024, q: int = 12289, security_level: int = None):
        self.n = n
        self.m = m
        self.q = q
        self.sigma = 1.17
        self.security_level = security_level or n

        self.A_cache = None
        self.B_cache = None
        self.lock = threading.Lock()

    @classmethod
    def create(cls, security_level: int = 512) -> 'OptimizedFalconKeygen':
        """根据安全级别创建实例: 512 或 1024"""
        if security_level not in FALCON_PARAMS:
            raise ValueError(f"不支持的安全级别: {security_level}，仅支持 512 和 1024")
        params = FALCON_PARAMS[security_level]
        return cls(
            n=params['n'], m=params['m'], q=params['q'],
            security_level=security_level
        )

    def setup_cached(self) -> Dict[str, np.ndarray]:
        if self.A_cache is not None:
            return {'A': self.A_cache, 'B': self.B_cache}

        self.A_cache = np.random.randint(0, self.q, size=(self.n, self.m), dtype=np.int64)
        self.B_cache = np.random.randint(0, self.q, size=(self.n, self.m), dtype=np.int64)

        return {'A': self.A_cache, 'B': self.B_cache}

    def partial_key_gen_fast(self, user_id: str, params: Dict) -> Tuple[np.ndarray, np.ndarray]:
        """
        PartialKeyGen: 确定性生成 D_id（短矩阵），计算 H_id = A·D_id mod q
        与 CertificatelessFalconStrict.partial_key_gen 完全一致的种子逻辑
        """
        A = params['A']
        seed = int(hashlib.sha256(user_id.encode()).hexdigest(), 16) % (2**32)
        rng = np.random.RandomState(seed)
        D_id = np.round(rng.normal(0, self.sigma, size=(self.m, self.m))).astype(np.int64)
        H_id = np.dot(A, D_id) % self.q
        return D_id, H_id

    def set_secret_value_fast(self) -> np.ndarray:
        """SetSecretValue: 短矩阵（离散高斯）"""
        return np.round(
            np.random.normal(0, self.sigma, size=(self.m, self.m))
        ).astype(np.int64)

    def set_sk_fast(self, D_id: np.ndarray, S_id: np.ndarray) -> Dict[str, np.ndarray]:
        return {'D_id': D_id, 'S_id': S_id}

    def set_pk_fast(self, S_id: np.ndarray, params: Dict) -> np.ndarray:
        """SetPK: U_id = B·S_id mod q"""
        B = params['B']
        U_id = np.dot(B, S_id) % self.q
        return U_id

    def generate_keypair_fast(self, user_id: str) -> Dict[str, Any]:
        params = self.setup_cached()

        D_id, H_id = self.partial_key_gen_fast(user_id, params)
        S_id = self.set_secret_value_fast()
        sk = self.set_sk_fast(D_id, S_id)
        pk = self.set_pk_fast(S_id, params)

        return {
            'sk': sk,
            'pk': pk,
            'D_id': D_id,
            'S_id': S_id,
            'H_id': H_id,
            'security_level': self.security_level,
            'parameters': {'n': self.n, 'm': self.m, 'q': self.q}
        }

