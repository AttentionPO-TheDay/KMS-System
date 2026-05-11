import numpy as np
import hashlib
import logging
import time
from typing import Dict, Tuple, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

logger = logging.getLogger(__name__)

_CACHE_LOCK = threading.RLock()
_SYSTEM_PARAMS_CACHE = {}
_HASH_CACHE = {}

class UltraFastKeygenV3:
    def __init__(self, n: int = 512, m: int = 1024, q: int = 12289, num_workers: int = 8):
        self.n = n
        self.m = m
        self.q = q
        self.num_workers = num_workers
        self.sigma = 1.17
        self.beta = q // 4
        self.cached_params = None
        self._init_lookup_tables()
    
    def _init_lookup_tables(self):
        self.gaussian_lut = np.random.normal(0, self.sigma, 10000).astype(np.int64) % self.q
        self.random_lut = np.random.randint(0, self.q, 10000, dtype=np.int64)
    
    def _fast_hash_to_matrix(self, data: str) -> np.ndarray:
        cache_key = f"hash_{data}"
        if cache_key in _HASH_CACHE:
            return _HASH_CACHE[cache_key]
        
        h = hashlib.sha256(data.encode()).digest()
        matrix = np.frombuffer(h, dtype=np.uint8)[:self.n*self.m//32]
        matrix = np.tile(matrix, (self.n*self.m) // len(matrix) + 1)[:self.n*self.m]
        matrix = (matrix.astype(np.int64) % self.q).reshape(self.n, self.m)
        
        _HASH_CACHE[cache_key] = matrix
        return matrix
    
    def _fast_gaussian_sample_vectorized(self, size: int) -> np.ndarray:
        indices = np.random.randint(0, len(self.gaussian_lut), size)
        return self.gaussian_lut[indices]
    
    def _fast_matrix_multiply_mod(self, A: np.ndarray, B: np.ndarray) -> np.ndarray:
        result = np.dot(A, B)
        return result % self.q
    
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
    
    def generate_falcon_keypair_ultra_fast(self, node_id: str) -> Dict[str, Any]:
        start_time = time.time()
        try:
            params = self.setup_cached()
            A = params['A']
            B = params['B']

            H_id = self._fast_hash_to_matrix(node_id)

            D_id = np.random.randint(0, self.q, (self.m, self.m), dtype=np.int64)

            S_id = np.zeros((self.m, self.m), dtype=np.int64)
            for i in range(self.m):
                S_id[i] = self._fast_gaussian_sample_vectorized(self.m)

            U_id = self._fast_matrix_multiply_mod(B, S_id)

            elapsed = time.time() - start_time

            return {
                'success': True,
                'node_id': node_id,
                'public_key': U_id.tobytes(),
                'private_key': D_id.tobytes(),
                'secret_value': S_id.tobytes(),
                'timing': elapsed,
                'algorithm': 'UltraFastFalconV3'
            }
        except Exception as e:
            logger.error(f"Falcon超快密钥生成失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def generate_kyber_keypair_ultra_fast(self, node_id: str) -> Dict[str, Any]:
        start_time = time.time()
        try:
            params = self.setup_cached()
            A = params['A']
            S_0 = params['S_0']
            
            s_prime_id = self._fast_gaussian_sample_vectorized(self.m)
            u_prime_id = self._fast_matrix_multiply_mod(A, s_prime_id.reshape(-1, 1)).flatten()
            
            c_hash = hashlib.sha256(node_id.encode()).digest()
            c = np.frombuffer(c_hash, dtype=np.uint8)[:self.m] % 3 - 1
            
            S0_c = self._fast_matrix_multiply_mod(S_0, c.reshape(-1, 1)).flatten()
            t = (s_prime_id + S0_c) % self.q
            
            s_id = self._fast_gaussian_sample_vectorized(self.m)
            sk = (t + s_id) % self.q
            
            pk = (u_prime_id + np.dot(A, s_id)) % self.q
            
            elapsed = time.time() - start_time
            
            return {
                'success': True,
                'node_id': node_id,
                'public_key': pk.tobytes(),
                'private_key': sk.tobytes(),
                'secret_value': s_id.tobytes(),
                'timing': elapsed,
                'algorithm': 'UltraFastKyberV3'
            }
        except Exception as e:
            logger.error(f"Kyber超快密钥生成失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def batch_generate_falcon_keypairs(self, node_ids: list) -> list:
        results = []
        with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
            futures = {executor.submit(self.generate_falcon_keypair_ultra_fast, nid): nid 
                      for nid in node_ids}
            for future in as_completed(futures):
                results.append(future.result())
        return results
    
    def batch_generate_kyber_keypairs(self, node_ids: list) -> list:
        results = []
        with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
            futures = {executor.submit(self.generate_kyber_keypair_ultra_fast, nid): nid 
                      for nid in node_ids}
            for future in as_completed(futures):
                results.append(future.result())
        return results

