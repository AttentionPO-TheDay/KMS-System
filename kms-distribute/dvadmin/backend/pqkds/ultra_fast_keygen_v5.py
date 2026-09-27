import numpy as np
import hashlib
import logging
from typing import Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor
import threading

logger = logging.getLogger(__name__)

class FastKyberKeygen:
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
        
        self.gaussian_table = self._precompute_gaussian_table()
        
    def _precompute_gaussian_table(self) -> np.ndarray:
        table = np.zeros(256, dtype=np.int64)
        for i in range(256):
            val = int(np.random.normal(0, self.sigma))
            table[i] = val % self.q
        return table
    
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
        extended = h
        while len(extended) < self.m:
            extended += hashlib.sha256(extended).digest()

        c = np.frombuffer(extended[:self.m], dtype=np.uint8) % 3 - 1
        c = c.astype(np.int64)

        self.hash_cache[user_id] = c
        return c
    
    def _fast_gaussian_sample(self, size: int) -> np.ndarray:
        indices = np.random.randint(0, 256, size=size)
        return self.gaussian_table[indices]
    
    def partial_key_gen_fast(self, user_id: str, params: Dict) -> Tuple[np.ndarray, np.ndarray]:
        A = params['A']
        S_0 = params['S_0']
        
        s_prime_id = self._fast_gaussian_sample(self.m)
        u_prime_id = np.dot(A, s_prime_id) % self.q
        c = self._fast_hash_to_vector(user_id)
        S_0_c = np.dot(S_0, c) % self.q
        t = (s_prime_id + S_0_c) % self.q
        
        return t, c, u_prime_id
    
    def set_secret_value_fast(self) -> np.ndarray:
        return self._fast_gaussian_sample(self.m)
    
    def set_sk_fast(self, t: np.ndarray, s_id: np.ndarray) -> np.ndarray:
        return (t + s_id) % self.q
    
    def set_pk_fast(self, u_prime_id: np.ndarray, c: np.ndarray, s_id: np.ndarray, params: Dict) -> np.ndarray:
        U_0 = params['U_0']
        A = params['A']
        
        U0_c = np.dot(U_0, c) % self.q
        A_sid = np.dot(A, s_id) % self.q
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


class FastFalconKeygen:
    def __init__(self, n: int = 512, m: int = 1024, q: int = 12289):
        self.n = n
        self.m = m
        self.q = q
        self.beta = q // 4
        
        self.A_cache = None
        self.T_cache = None
        self.B_cache = None
        self.hash_cache = {}
        self.lock = threading.Lock()
        
        self.gaussian_table = self._precompute_gaussian_table()
        
    def _precompute_gaussian_table(self) -> np.ndarray:
        table = np.random.normal(0, 1.17, size=(self.m, self.m)).astype(np.int64)
        return table % self.q
    
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
        extended = h
        while len(extended) < self.n * self.m:
            extended += hashlib.sha256(extended).digest()

        H = np.frombuffer(extended[:self.n * self.m], dtype=np.uint8).reshape(self.n, self.m)
        H = H.astype(np.int64) % self.q

        self.hash_cache[user_id] = H
        return H
    
    def _fast_gaussian_sample_matrix(self) -> np.ndarray:
        return np.random.normal(0, 1.17, size=(self.m, self.m)).astype(np.int64) % self.q
    
    def partial_key_gen_fast(self, user_id: str, params: Dict) -> Tuple[np.ndarray, np.ndarray]:
        A = params['A']
        T = params['T']
        H_id = self._fast_hash_to_matrix(user_id)

        D_id = np.random.randint(-self.beta, self.beta + 1, size=(self.m, self.m), dtype=np.int64)
        D_id = D_id % self.q

        return D_id, H_id
    
    def set_secret_value_fast(self) -> np.ndarray:
        return np.random.randint(0, self.q, size=self.m, dtype=np.int64)

    def set_sk_fast(self, D_id: np.ndarray, S_id: np.ndarray) -> Dict[str, np.ndarray]:
        return {'D_id': D_id, 'S_id': S_id}

    def set_pk_fast(self, S_id: np.ndarray, params: Dict) -> np.ndarray:
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
            'H_id': H_id
        }


class ParallelKeygenPool:
    def __init__(self, num_workers: int = 4):
        self.kyber_gen = FastKyberKeygen()
        self.falcon_gen = FastFalconKeygen()
        self.executor = ThreadPoolExecutor(max_workers=num_workers)
    
    def generate_kyber_keypairs_batch(self, user_ids: list) -> list:
        futures = [
            self.executor.submit(self.kyber_gen.generate_keypair_fast, uid)
            for uid in user_ids
        ]
        return [f.result() for f in futures]
    
    def generate_falcon_keypairs_batch(self, user_ids: list) -> list:
        futures = [
            self.executor.submit(self.falcon_gen.generate_keypair_fast, uid)
            for uid in user_ids
        ]
        return [f.result() for f in futures]
    
    def shutdown(self):
        self.executor.shutdown(wait=True)

