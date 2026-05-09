import numpy as np
import hashlib
import logging
import time
from typing import Dict, Tuple, Any
import threading
logger = logging.getLogger(__name__)
try:
    from numba import jit, prange
    NUMBA_AVAILABLE = True
    logger.info("Numba JIT编译已启用")
except ImportError:
    NUMBA_AVAILABLE = False
    logger.warning("Numba不可用，使用纯NumPy实现")
    def jit(*args, **kwargs):
        def decorator(func):
            return func
        return decorator
    def prange(n):
        return range(n)
@jit(nopython=True, parallel=True, cache=True)
def _numba_gaussian_sample_batch(size: int, sigma: float, q: int) -> np.ndarray:
    result = np.zeros(size, dtype=np.int64)
    for i in prange(size):
        u1 = np.random.uniform(0, 1)
        u2 = np.random.uniform(0, 1)
        z = np.sqrt(-2 * np.log(u1 + 1e-10)) * np.cos(2 * np.pi * u2)
        result[i] = int((z * sigma) % q)
    return result
@jit(nopython=True, parallel=True, cache=True)
def _numba_matrix_multiply_mod(A: np.ndarray, B: np.ndarray, q: int) -> np.ndarray:
    n, m = A.shape
    m2, p = B.shape
    result = np.zeros((n, p), dtype=np.int64)
    for i in prange(n):
        for j in range(p):
            s = 0
            for k in range(m):
                s += A[i, k] * B[k, j]
            result[i, j] = s % q
    return result
@jit(nopython=True, cache=True)
def _numba_vector_add_mod(a: np.ndarray, b: np.ndarray, q: int) -> np.ndarray:
    result = np.zeros_like(a)
    for i in range(len(a)):
        result[i] = (a[i] + b[i]) % q
    return result
class SuperFastKyberOptimized:
    def __init__(self, n: int = 512, m: int = 1024, q: int = 12289):
        self.n = n
        self.m = m
        self.q = q
        self.sigma = 1.17
        self._cache = {}
        self._cache_lock = threading.Lock()
        logger.info(f"SuperFastKyberOptimized初始化: n={n}, m={m}, q={q}")
    def _fast_gaussian_sample(self, size: int) -> np.ndarray:
        if NUMBA_AVAILABLE:
            return _numba_gaussian_sample_batch(size, self.sigma, self.q)
        else:
            u1 = np.random.uniform(0, 1, size)
            u2 = np.random.uniform(0, 1, size)
            z = np.sqrt(-2 * np.log(u1 + 1e-10)) * np.cos(2 * np.pi * u2)
            return (z * self.sigma).astype(np.int64) % self.q
    def _fast_matrix_multiply(self, A: np.ndarray, B: np.ndarray) -> np.ndarray:
        if NUMBA_AVAILABLE:
            return _numba_matrix_multiply_mod(A, B, self.q)
        else:
            result = np.dot(A, B)
            return result % self.q
    def _hash_to_vector_ultra_fast(self, data: str, dim: int) -> np.ndarray:
        h = hashlib.sha256(data.encode()).digest()
        result = np.frombuffer(h, dtype=np.uint8)
        if len(result) < dim:
            result = np.tile(result, (dim // len(result) + 1))[:dim]
        return (result % self.q).astype(np.int64)
    def setup_ultra_fast(self) -> Dict[str, Any]:
        logger.info("[Kyber Setup] 生成系统参数")
        A = np.random.randint(0, self.q, size=(self.n, self.m), dtype=np.int64)
        S_0 = np.random.randint(0, 2, size=(self.m, self.m), dtype=np.int64)
        U_0 = self._fast_matrix_multiply(A, S_0)
        return {'A': A, 'S_0': S_0, 'U_0': U_0}
    def generate_kyber_keypair_super_fast(self, node_id: str) -> Dict[str, Any]:
        logger.info(f"[超极速Kyber] 为节点{node_id}生成密钥对")
        start_time = time.time()
        try:
            with self._cache_lock:
                if 'system_params' not in self._cache:
                    self._cache['system_params'] = self.setup_ultra_fast()
                system_params = self._cache['system_params']
            A = system_params['A']
            S_0 = system_params['S_0']
            U_0 = system_params['U_0']
            s_prime_id = self._fast_gaussian_sample(self.m)
            u_prime_id = self._fast_matrix_multiply(A, s_prime_id.reshape(-1, 1)).flatten()
            c = self._hash_to_vector_ultra_fast(node_id, self.m)
            S_0_c = self._fast_matrix_multiply(S_0, c.reshape(-1, 1)).flatten()
            t = (s_prime_id + S_0_c) % self.q
            s_id = self._fast_gaussian_sample(self.m)
            sk = (t + s_id) % self.q
            u_id = self._fast_matrix_multiply(A, s_id.reshape(-1, 1)).flatten()
            U_0_c = self._fast_matrix_multiply(U_0, c.reshape(-1, 1)).flatten()
            pk = (u_id + U_0_c) % self.q
            import base64
            import json
            kyber_public_key_data = {
                'pk': pk.astype(np.int64).tolist(),
                'algorithm': 'SuperFastKyberOptimized',
                'node_id': node_id,
                'parameters': {
                    'n': self.n,
                    'm': self.m,
                    'q': self.q,
                    'sigma': self.sigma
                }
            }
            kyber_private_key_data = {
                'sk': sk.astype(np.int64).tolist(),
                'algorithm': 'SuperFastKyberOptimized',
                'node_id': node_id,
                'parameters': {
                    'n': self.n,
                    'm': self.m,
                    'q': self.q,
                    'sigma': self.sigma
                }
            }
            kyber_public_key = base64.b64encode(
                json.dumps(kyber_public_key_data).encode('utf-8')
            ).decode('utf-8')
            kyber_private_key = base64.b64encode(
                json.dumps(kyber_private_key_data).encode('utf-8')
            ).decode('utf-8')
            elapsed = time.time() - start_time
            logger.info(f"[超极速Kyber] 完成，耗时: {elapsed*1000:.2f}ms")
            return {
                'success': True,
                'kyber_public_key': kyber_public_key,
                'kyber_private_key': kyber_private_key,
                'timing': elapsed
            }
        except Exception as e:
            logger.error(f"[超极速Kyber] 失败: {e}")
            return {'success': False, 'message': str(e)}
class SuperFastFalconOptimized:
    def __init__(self, n: int = 512, m: int = 1024, q: int = 12289):
        self.n = n
        self.m = m
        self.q = q
        self.beta = q // 4
        self.sigma = 1.17
        self._cache = {}
        self._cache_lock = threading.Lock()
        logger.info(f"SuperFastFalconOptimized初始化: n={n}, m={m}, q={q}")
    def _fast_gaussian_sample(self, size: int) -> np.ndarray:
        if NUMBA_AVAILABLE:
            return _numba_gaussian_sample_batch(size, self.sigma, self.q)
        else:
            u1 = np.random.uniform(0, 1, size)
            u2 = np.random.uniform(0, 1, size)
            z = np.sqrt(-2 * np.log(u1 + 1e-10)) * np.cos(2 * np.pi * u2)
            return (z * self.sigma).astype(np.int64) % self.q
    def _fast_matrix_multiply(self, A: np.ndarray, B: np.ndarray) -> np.ndarray:
        if NUMBA_AVAILABLE:
            return _numba_matrix_multiply_mod(A, B, self.q)
        else:
            result = np.dot(A, B)
            return result % self.q
    def _hash_to_matrix_ultra_fast(self, data: str) -> np.ndarray:
        h = hashlib.sha256(data.encode()).digest()
        extended = h
        while len(extended) < self.n * self.m:
            extended += hashlib.sha256(extended).digest()
        values = np.frombuffer(extended[:self.n * self.m], dtype=np.uint8)
        return (values % self.q).astype(np.int64).reshape(self.n, self.m)
    def setup_ultra_fast(self) -> Dict[str, Any]:
        logger.info("[Falcon Setup] 生成系统参数")
        B = np.random.randint(0, self.q, size=(self.n, self.m), dtype=np.int64)
        A = np.random.randint(0, self.q, size=(self.n, self.m), dtype=np.int64)
        T = np.random.randint(-self.beta, self.beta + 1, size=(self.m, self.m), dtype=np.int64)
        return {'A': A, 'B': B, 'T': T}
    def generate_falcon_keypair_super_fast(self, node_id: str) -> Dict[str, Any]:
        logger.info(f"[超极速Falcon] 为节点{node_id}生成密钥对")
        start_time = time.time()
        try:
            with self._cache_lock:
                if 'system_params' not in self._cache:
                    self._cache['system_params'] = self.setup_ultra_fast()
                system_params = self._cache['system_params']
            A = system_params['A']
            B = system_params['B']
            H_id = self._hash_to_matrix_ultra_fast(node_id)
            try:
                D_id = np.linalg.lstsq(A.astype(float), H_id.astype(float), rcond=None)[0]
                D_id = np.round(D_id) % self.q
            except:
                D_id = np.random.randint(0, self.q, size=(self.m, self.m), dtype=np.int64)
            S_id = np.zeros((self.m, self.m), dtype=np.int64)
            for i in range(self.m):
                S_id[i] = self._fast_gaussian_sample(self.m)
            U_id = self._fast_matrix_multiply(B, S_id)
            import base64
            import json
            falcon_public_key_data = {
                'U_id': U_id.astype(np.int64).tolist(),
                'algorithm': 'SuperFastFalconOptimized',
                'node_id': node_id,
                'parameters': {
                    'n': self.n,
                    'm': self.m,
                    'q': self.q
                }
            }
            falcon_private_key_data = {
                'D_id': D_id.astype(np.int64).tolist(),
                'S_id': S_id.astype(np.int64).tolist(),
                'algorithm': 'SuperFastFalconOptimized',
                'node_id': node_id,
                'parameters': {
                    'n': self.n,
                    'm': self.m,
                    'q': self.q
                }
            }
            falcon_public_key = base64.b64encode(
                json.dumps(falcon_public_key_data).encode('utf-8')
            ).decode('utf-8')
            falcon_private_key = base64.b64encode(
                json.dumps(falcon_private_key_data).encode('utf-8')
            ).decode('utf-8')
            elapsed = time.time() - start_time
            logger.info(f"[超极速Falcon] 完成，耗时: {elapsed*1000:.2f}ms")
            return {
                'success': True,
                'falcon_public_key': falcon_public_key,
                'falcon_private_key': falcon_private_key,
                'timing': elapsed
            }
        except Exception as e:
            logger.error(f"[超极速Falcon] 失败: {e}")
            return {'success': False, 'message': str(e)}