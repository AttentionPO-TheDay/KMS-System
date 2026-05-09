import numpy as np
import hashlib
import logging
import time
from typing import Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

logger = logging.getLogger(__name__)

_CACHE_LOCK = threading.RLock()
_SYSTEM_PARAMS_CACHE = {}
_HASH_CACHE = {}

class UltraFastFalconV4:
    def __init__(self, n: int = 512, m: int = 1024, q: int = 12289, num_workers: int = 8):
        self.n = n
        self.m = m
        self.q = q
        self.num_workers = num_workers
        self.sigma = 1.17
        self.beta = q // 4
        self._init_lookup_tables()
    
    def _init_lookup_tables(self):
        self.gaussian_lut = np.random.normal(0, self.sigma, 10000).astype(np.int64) % self.q
        self.random_lut = np.random.randint(0, self.q, 10000, dtype=np.int64)
    
    def _fast_hash_to_vector(self, data: str, size: int) -> np.ndarray:
        cache_key = f"hash_vec_{data}_{size}"
        if cache_key in _HASH_CACHE:
            return _HASH_CACHE[cache_key]
        
        h = hashlib.sha256(data.encode()).digest()
        vec = np.frombuffer(h, dtype=np.uint8)[:size]
        vec = np.tile(vec, (size // len(vec) + 1))[:size]
        vec = (vec.astype(np.int64) % self.q)
        
        _HASH_CACHE[cache_key] = vec
        return vec
    
    def _fast_gaussian_sample_vectorized(self, size: int) -> np.ndarray:
        indices = np.random.randint(0, len(self.gaussian_lut), size)
        return self.gaussian_lut[indices]
    
    def _fast_vector_multiply_mod(self, a: np.ndarray, b: np.ndarray) -> np.int64:
        return np.dot(a, b) % self.q
    
    def setup_cached(self) -> Dict[str, np.ndarray]:
        cache_key = f"params_{self.n}_{self.m}_{self.q}"
        with _CACHE_LOCK:
            if cache_key in _SYSTEM_PARAMS_CACHE:
                return _SYSTEM_PARAMS_CACHE[cache_key]
            
            A = np.random.randint(0, self.q, (self.n, self.m), dtype=np.int64)
            B = np.random.randint(0, self.q, (self.n, self.m), dtype=np.int64)
            
            params = {'A': A, 'B': B}
            _SYSTEM_PARAMS_CACHE[cache_key] = params
            return params
    
    def generate_falcon_keypair_v4(self, node_id: str) -> Dict[str, Any]:
        start_time = time.time()
        try:
            params = self.setup_cached()
            B = params['B']
            
            S_id = self._fast_gaussian_sample_vectorized(self.m)
            
            U_id = np.dot(B, S_id) % self.q
            
            D_id = self._fast_gaussian_sample_vectorized(self.m)
            
            elapsed = time.time() - start_time
            
            return {
                'success': True,
                'node_id': node_id,
                'public_key': U_id.tobytes(),
                'private_key': D_id.tobytes(),
                'secret_value': S_id.tobytes(),
                'timing': elapsed,
                'algorithm': 'UltraFastFalconV4'
            }
        except Exception as e:
            logger.error(f"Falcon V4密钥生成失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def batch_generate_falcon_keypairs(self, node_ids: list) -> list:
        results = []
        with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
            futures = {executor.submit(self.generate_falcon_keypair_v4, nid): nid 
                      for nid in node_ids}
            for future in as_completed(futures):
                results.append(future.result())
        return results

