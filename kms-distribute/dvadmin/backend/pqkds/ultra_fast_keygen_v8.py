import numpy as np
import hashlib
from typing import Dict, Any
from concurrent.futures import ThreadPoolExecutor

try:
    from numba import jit
    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False
    def jit(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

@jit(nopython=True)
def fast_matmul_mod(A, B, q):
    n, m = A.shape
    m2 = B.shape[1]
    result = np.zeros((n, m2), dtype=np.int64)
    for i in range(n):
        for j in range(m2):
            s = 0
            for k in range(m):
                s += A[i, k] * B[k, j]
            result[i, j] = s % q
    return result

class UltraOptimizedFalconKeygen:
    def __init__(self, n: int = 512, m: int = 1024, q: int = 12289):
        self.n = n
        self.m = m
        self.q = q
        self.beta = q // 4
        
        self.A_cache = None
        self.T_cache = None
        self.B_cache = None
        self.hash_cache = {}
        
    def setup_cached(self) -> Dict[str, np.ndarray]:
        if self.A_cache is not None:
            return {
                'A': self.A_cache,
                'T': self.T_cache,
                'B': self.B_cache
            }
        
        self.T_cache = np.random.randint(-self.beta, self.beta + 1, size=(self.m, self.m), dtype=np.int64)
        self.A_cache = np.random.randint(0, self.q, size=(self.n, self.m), dtype=np.int64)
        self.B_cache = np.random.randint(0, self.q, size=(self.n, self.m), dtype=np.int64)
        
        return {
            'A': self.A_cache,
            'T': self.T_cache,
            'B': self.B_cache
        }
    
    def _fast_hash_to_matrix(self, user_id: str) -> np.ndarray:
        if user_id in self.hash_cache:
            return self.hash_cache[user_id]
        
        h = hashlib.sha256(user_id.encode()).digest()
        h_array = np.frombuffer(h, dtype=np.uint8)
        
        H = np.tile(h_array, (self.n * self.m // len(h) + 1))[:self.n * self.m]
        H = H.astype(np.int64) % self.q
        H = H.reshape(self.n, self.m)
        
        self.hash_cache[user_id] = H
        return H
    
    def generate_keypair_fast(self, user_id: str) -> Dict[str, Any]:
        params = self.setup_cached()
        B = params['B']

        H_id = self._fast_hash_to_matrix(user_id)

        D_id = np.random.randint(0, self.q, size=(self.m, self.m), dtype=np.int64)
        S_id = np.random.randint(0, self.q, size=self.m, dtype=np.int64)

        U_id = np.dot(B, S_id) % self.q

        return {
            'sk': {'D_id': D_id, 'S_id': S_id},
            'pk': U_id,
            'D_id': D_id,
            'S_id': S_id,
            'H_id': H_id
        }


class UltraOptimizedKyberKeygen:
    def __init__(self, n: int = 512, m: int = 1024, q: int = 12289, sigma: float = 1.17):
        self.n = n
        self.m = m
        self.q = q
        self.sigma = sigma
        
        self.A_cache = None
        self.S_0_cache = None
        self.U_0_cache = None
        self.hash_cache = {}
        
    def setup_cached(self) -> Dict[str, np.ndarray]:
        if self.A_cache is not None:
            return {
                'A': self.A_cache,
                'S_0': self.S_0_cache,
                'U_0': self.U_0_cache
            }
        
        self.A_cache = np.random.randint(0, self.q, size=(self.n, self.m), dtype=np.int64)
        self.S_0_cache = np.random.randint(0, 2, size=(self.m, self.m), dtype=np.int64)
        self.U_0_cache = np.dot(self.A_cache, self.S_0_cache) % self.q
        
        return {
            'A': self.A_cache,
            'S_0': self.S_0_cache,
            'U_0': self.U_0_cache
        }
    
    def _fast_hash_to_vector(self, user_id: str) -> np.ndarray:
        if user_id in self.hash_cache:
            return self.hash_cache[user_id]
        
        h = hashlib.sha256(user_id.encode()).digest()
        h_array = np.frombuffer(h, dtype=np.uint8)
        c = np.tile(h_array, (self.m // len(h) + 1))[:self.m]
        c = (c % 3 - 1).astype(np.int64)
        
        self.hash_cache[user_id] = c
        return c
    
    def generate_keypair_fast(self, user_id: str) -> Dict[str, Any]:
        params = self.setup_cached()
        A = params['A']
        S_0 = params['S_0']
        U_0 = params['U_0']
        
        s_prime_id = np.random.normal(0, self.sigma, self.m).astype(np.int64) % self.q
        u_prime_id = np.dot(A, s_prime_id) % self.q
        c = self._fast_hash_to_vector(user_id)
        S_0_c = np.dot(S_0, c) % self.q
        t = (s_prime_id + S_0_c) % self.q
        
        s_id = np.random.normal(0, self.sigma, self.m).astype(np.int64) % self.q
        sk = (t + s_id) % self.q
        
        U0_c = np.dot(U_0, c) % self.q
        A_sid = np.dot(A, s_id) % self.q
        pk = (u_prime_id + U0_c + A_sid) % self.q
        
        return {
            'sk': sk,
            'pk': pk,
            't': t,
            'c': c,
            's_id': s_id,
            'u_prime_id': u_prime_id
        }

