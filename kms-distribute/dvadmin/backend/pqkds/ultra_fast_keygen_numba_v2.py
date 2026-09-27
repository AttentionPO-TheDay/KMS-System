import numpy as np
import hashlib
import logging
import time
from typing import Dict, Tuple, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

try:
    from numba import jit, prange
    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False

logger = logging.getLogger(__name__)

_CACHE_LOCK = threading.RLock()
_SYSTEM_PARAMS_CACHE = {}

if HAS_NUMBA:
    @jit(nopython=True, parallel=True, cache=True)
    def fast_matrix_multiply_mod(A, B, q):
        n, m = A.shape
        k = B.shape[1]
        result = np.zeros((n, k), dtype=np.int64)
        for i in prange(n):
            for j in range(k):
                val = 0
                for p in range(m):
                    val += A[i, p] * B[p, j]
                result[i, j] = val % q
        return result
    
    @jit(nopython=True, parallel=True, cache=True)
    def fast_gaussian_sample(size, q, sigma_int):
        result = np.zeros(size, dtype=np.int64)
        for i in prange(size):
            val = np.random.normal(0, sigma_int)
            result[i] = int(np.round(val)) % q
        return result
    
    @jit(nopython=True, cache=True)
    def fast_modular_add(a, b, q):
        return (a + b) % q

class UltraFastKeygenNumbaV2:
    def __init__(self, n: int = 512, m: int = 1024, q: int = 12289, num_workers: int = 8):
        self.n = n
        self.m = m
        self.q = q
        self.num_workers = num_workers
        self.sigma = 1.17
        self.sigma_int = int(self.sigma * 100)
        self.beta = q // 4
        self.cached_params = None
    
    def _fast_hash_to_matrix(self, data: str) -> np.ndarray:
        h = hashlib.sha256(data.encode()).digest()
        matrix = np.frombuffer(h, dtype=np.uint8)[:self.n*self.m//32]
        matrix = np.tile(matrix, (self.n*self.m) // len(matrix) + 1)[:self.n*self.m]
        return (matrix.astype(np.int64) % self.q).reshape(self.n, self.m)
    
    def setup_cached(self) -> Dict[str, np.ndarray]:
        cache_key = f"params_{self.n}_{self.m}_{self.q}"
        with _CACHE_LOCK:
            if cache_key in _SYSTEM_PARAMS_CACHE:
                return _SYSTEM_PARAMS_CACHE[cache_key]
            
            A = np.random.randint(0, self.q, (self.n, self.m), dtype=np.int64)
            B = np.random.randint(0, self.q, (self.n, self.m), dtype=np.int64)
            S_0 = np.random.randint(-self.beta, self.beta + 1, (self.m, self.m), dtype=np.int64) % self.q
            
            params = {'A': A, 'B': B, 'S_0': S_0}
            _SYSTEM_PARAMS_CACHE[cache_key] = params
            return params
    
    def generate_falcon_keypair_numba(self, node_id: str) -> Dict[str, Any]:
        start_time = time.time()
        try:
            params = self.setup_cached()
            A = params['A']
            B = params['B']

            H_id = self._fast_hash_to_matrix(node_id)

            D_id = np.random.randint(0, self.q, (self.m, self.m), dtype=np.int64)

            if HAS_NUMBA:
                S_id = np.zeros((self.m, self.m), dtype=np.int64)
                for i in range(self.m):
                    S_id[i] = fast_gaussian_sample(self.m, self.q, self.sigma_int)
                U_id = fast_matrix_multiply_mod(B, S_id, self.q)
            else:
                S_id = np.random.normal(0, self.sigma, (self.m, self.m)).astype(np.int64) % self.q
                U_id = np.dot(B, S_id) % self.q

            elapsed = time.time() - start_time

            return {
                'success': True,
                'node_id': node_id,
                'public_key': U_id.tobytes(),
                'private_key': D_id.tobytes(),
                'secret_value': S_id.tobytes(),
                'timing': elapsed,
                'algorithm': 'UltraFastFalconNumbaV2'
            }
        except Exception as e:
            logger.error(f"Falcon Numba密钥生成失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def generate_kyber_keypair_numba(self, node_id: str) -> Dict[str, Any]:
        start_time = time.time()
        try:
            params = self.setup_cached()
            A = params['A']
            S_0 = params['S_0']
            
            if HAS_NUMBA:
                s_prime_id = fast_gaussian_sample(self.m, self.q, self.sigma_int)
                u_prime_id = fast_matrix_multiply_mod(A, s_prime_id.reshape(-1, 1), self.q).flatten()
            else:
                s_prime_id = np.random.normal(0, self.sigma, self.m).astype(np.int64) % self.q
                u_prime_id = np.dot(A, s_prime_id) % self.q
            
            c_hash = hashlib.sha256(node_id.encode()).digest()
            c = np.frombuffer(c_hash, dtype=np.uint8)[:self.m] % 3 - 1
            
            if HAS_NUMBA:
                S0_c = fast_matrix_multiply_mod(S_0, c.reshape(-1, 1), self.q).flatten()
            else:
                S0_c = np.dot(S_0, c) % self.q
            
            t = (s_prime_id + S0_c) % self.q
            
            if HAS_NUMBA:
                s_id = fast_gaussian_sample(self.m, self.q, self.sigma_int)
            else:
                s_id = np.random.normal(0, self.sigma, self.m).astype(np.int64) % self.q
            
            sk = (t + s_id) % self.q
            
            if HAS_NUMBA:
                pk = fast_matrix_multiply_mod(A, s_id.reshape(-1, 1), self.q).flatten()
                pk = (u_prime_id + pk) % self.q
            else:
                pk = (u_prime_id + np.dot(A, s_id)) % self.q
            
            elapsed = time.time() - start_time
            
            return {
                'success': True,
                'node_id': node_id,
                'public_key': pk.tobytes(),
                'private_key': sk.tobytes(),
                'secret_value': s_id.tobytes(),
                'timing': elapsed,
                'algorithm': 'UltraFastKyberNumbaV2'
            }
        except Exception as e:
            logger.error(f"Kyber Numba密钥生成失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def batch_generate_keypairs(self, node_ids: list, algorithm: str = 'both') -> Dict[str, list]:
        results = {'falcon': [], 'kyber': []}
        
        with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
            if algorithm in ('both', 'falcon'):
                falcon_futures = {executor.submit(self.generate_falcon_keypair_numba, nid): nid 
                                 for nid in node_ids}
                for future in as_completed(falcon_futures):
                    results['falcon'].append(future.result())
            
            if algorithm in ('both', 'kyber'):
                kyber_futures = {executor.submit(self.generate_kyber_keypair_numba, nid): nid 
                                for nid in node_ids}
                for future in as_completed(kyber_futures):
                    results['kyber'].append(future.result())
        
        return results

