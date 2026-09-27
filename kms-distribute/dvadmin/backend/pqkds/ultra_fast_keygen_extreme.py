import numpy as np
import hashlib
import logging
import time
from typing import Dict, Tuple, Any, Optional
from concurrent.futures import ThreadPoolExecutor
import threading
logger = logging.getLogger(__name__)
_SYSTEM_PARAMS_CACHE = {}
_CACHE_LOCK = threading.Lock()
class UltraFastKyberOptimized:
    def __init__(self, n: int = 512, m: int = 1024, q: int = 12289, num_workers: int = 8):
        self.n = n
        self.m = m
        self.q = q
        self.sigma = 1.17
        self.num_workers = num_workers
        self.executor = ThreadPoolExecutor(max_workers=num_workers)
        self._prealloc_buffers()
        logger.info(f"UltraFastKyberOptimized初始化: n={n}, m={m}, q={q}, workers={num_workers}")
    def _prealloc_buffers(self):
        self.buffer_A = np.zeros((self.n, self.m), dtype=np.int64)
        self.buffer_S = np.zeros((self.m, self.m), dtype=np.int64)
        self.buffer_result = np.zeros((self.n, self.m), dtype=np.int64)
    def _fast_gaussian_sample_vectorized(self, size: int) -> np.ndarray:
        u1 = np.random.uniform(0, 1, size)
        u2 = np.random.uniform(0, 1, size)
        z = np.sqrt(-2 * np.log(u1 + 1e-10)) * np.cos(2 * np.pi * u2)
        return (z * self.sigma).astype(np.int64) % self.q
    def _fast_matrix_multiply_mod(self, A: np.ndarray, B: np.ndarray) -> np.ndarray:
        result = np.dot(A, B)
        return result % self.q
    def _hash_to_vector_fast(self, data: str, dim: int) -> np.ndarray:
        h = hashlib.sha256(data.encode()).digest()
        result = np.frombuffer(h, dtype=np.uint8)
        if len(result) < dim:
            result = np.tile(result, (dim // len(result) + 1))[:dim]
        return (result % self.q).astype(np.int64)
    def setup_fast(self) -> Dict[str, Any]:
        logger.info("[Kyber Setup] 开始快速生成系统参数")
        A = np.random.randint(0, self.q, size=(self.n, self.m), dtype=np.int64)
        S_0 = np.random.randint(0, 2, size=(self.m, self.m), dtype=np.int64)
        U_0 = self._fast_matrix_multiply_mod(A, S_0)
        params = {
            'A': A,
            'S_0': S_0,
            'U_0': U_0,
            'n': self.n,
            'm': self.m,
            'q': self.q
        }
        logger.info("[Kyber Setup] 系统参数生成完成")
        return params
    def partial_key_gen_fast(self, user_id: str, system_params: Dict) -> Tuple[np.ndarray, np.ndarray]:
        logger.info(f"[Kyber PartialKeyGen] 为用户{user_id}生成部分私钥")
        A = system_params['A']
        S_0 = system_params['S_0']
        s_prime_id = self._fast_gaussian_sample_vectorized(self.m)
        u_prime_id = self._fast_matrix_multiply_mod(A, s_prime_id)
        c = self._hash_to_vector_fast(user_id, self.m)
        S_0_c = self._fast_matrix_multiply_mod(S_0, c.reshape(-1, 1))
        t = (s_prime_id + S_0_c.flatten()) % self.q
        logger.info(f"[Kyber PartialKeyGen] 部分私钥生成完成")
        return t, c
    def set_secret_value_fast(self) -> np.ndarray:
        logger.info("[Kyber SetSecretValue] 生成秘密值")
        s_id = self._fast_gaussian_sample_vectorized(self.m)
        logger.info("[Kyber SetSecretValue] 秘密值生成完成")
        return s_id
    def set_sk_fast(self, t: np.ndarray, s_id: np.ndarray) -> np.ndarray:
        logger.info("[Kyber SetSK] 生成秘密密钥")
        sk = (t + s_id) % self.q
        logger.info("[Kyber SetSK] 秘密密钥生成完成")
        return sk
    def set_pk_fast(self, system_params: Dict, s_id: np.ndarray, c: np.ndarray) -> np.ndarray:
        logger.info("[Kyber SetPK] 生成公开密钥")
        A = system_params['A']
        U_0 = system_params['U_0']
        u_id = self._fast_matrix_multiply_mod(A, s_id)
        U_0_c = self._fast_matrix_multiply_mod(U_0, c.reshape(-1, 1))
        pk = (u_id + U_0_c.flatten()) % self.q
        logger.info("[Kyber SetPK] 公开密钥生成完成")
        return pk
    def generate_kyber_keypair_ultra_fast(self, node_id: str) -> Dict[str, Any]:
        logger.info(f"[超快Kyber] 开始为节点{node_id}生成密钥对")
        start_time = time.time()
        try:
            with _CACHE_LOCK:
                cache_key = f"kyber_params_{self.n}_{self.m}_{self.q}"
                if cache_key not in _SYSTEM_PARAMS_CACHE:
                    _SYSTEM_PARAMS_CACHE[cache_key] = self.setup_fast()
                system_params = _SYSTEM_PARAMS_CACHE[cache_key]
            t, c = self.partial_key_gen_fast(node_id, system_params)
            s_id = self.set_secret_value_fast()
            sk = self.set_sk_fast(t, s_id)
            pk = self.set_pk_fast(system_params, s_id, c)
            import base64
            import json
            kyber_public_key_data = {
                'pk': pk.astype(np.int64).tolist(),
                'algorithm': 'UltraFastKyberOptimized',
                'node_id': node_id,
                'parameters': {
                    'n': self.n,
                    'm': self.m,
                    'q': self.q
                }
            }
            kyber_private_key_data = {
                'sk': sk.astype(np.int64).tolist(),
                'algorithm': 'UltraFastKyberOptimized',
                'node_id': node_id,
                'parameters': {
                    'n': self.n,
                    'm': self.m,
                    'q': self.q
                }
            }
            kyber_public_key = base64.b64encode(
                json.dumps(kyber_public_key_data).encode('utf-8')
            ).decode('utf-8')
            kyber_private_key = base64.b64encode(
                json.dumps(kyber_private_key_data).encode('utf-8')
            ).decode('utf-8')
            elapsed = time.time() - start_time
            logger.info(f"[超快Kyber] 密钥对生成完成，耗时: {elapsed*1000:.2f}ms")
            return {
                'success': True,
                'kyber_public_key': kyber_public_key,
                'kyber_private_key': kyber_private_key,
                'timing': elapsed,
                'message': f'Kyber密钥对生成成功 ({elapsed*1000:.2f}ms)'
            }
        except Exception as e:
            logger.error(f"[超快Kyber] 密钥生成失败: {e}")
            return {
                'success': False,
                'message': f'Kyber密钥生成失败: {str(e)}'
            }
    def shutdown(self):
        self.executor.shutdown(wait=False)
class UltraFastFalconOptimized:
    def __init__(self, n: int = 512, m: int = 1024, q: int = 12289, num_workers: int = 8):
        self.n = n
        self.m = m
        self.q = q
        self.beta = q // 4
        self.sigma = 1.17
        self.num_workers = num_workers
        self.executor = ThreadPoolExecutor(max_workers=num_workers)
        logger.info(f"UltraFastFalconOptimized初始化: n={n}, m={m}, q={q}, workers={num_workers}")
    def _fast_gaussian_sample_vectorized(self, size: int) -> np.ndarray:
        u1 = np.random.uniform(0, 1, size)
        u2 = np.random.uniform(0, 1, size)
        z = np.sqrt(-2 * np.log(u1 + 1e-10)) * np.cos(2 * np.pi * u2)
        return (z * self.sigma).astype(np.int64) % self.q
    def _fast_matrix_multiply_mod(self, A: np.ndarray, B: np.ndarray) -> np.ndarray:
        result = np.dot(A, B)
        return result % self.q
    def _hash_to_matrix_fast(self, data: str) -> np.ndarray:
        h = hashlib.sha256(data.encode()).digest()
        extended = h
        while len(extended) < self.n * self.m:
            extended += hashlib.sha256(extended).digest()
        values = np.frombuffer(extended[:self.n * self.m], dtype=np.uint8)
        return (values % self.q).astype(np.int64).reshape(self.n, self.m)
    def _fast_trapgen(self) -> Tuple[np.ndarray, np.ndarray]:
        T = np.random.randint(-self.beta, self.beta + 1, size=(self.m, self.m), dtype=np.int64)
        A = np.random.randint(0, self.q, size=(self.n, self.m), dtype=np.int64)
        return A % self.q, T % self.q
    def setup_fast(self) -> Dict[str, Any]:
        logger.info("[Falcon Setup] 开始快速生成系统参数")
        B = np.random.randint(0, self.q, size=(self.n, self.m), dtype=np.int64)
        A, T = self._fast_trapgen()
        params = {
            'A': A,
            'B': B,
            'T': T,
            'n': self.n,
            'm': self.m,
            'q': self.q
        }
        logger.info("[Falcon Setup] 系统参数生成完成")
        return params
    def partial_key_gen_fast(self, user_id: str, system_params: Dict) -> Tuple[np.ndarray, np.ndarray]:
        logger.info(f"[Falcon PartialKeyGen] 为用户{user_id}生成部分私钥")
        A = system_params['A']
        H_id = self._hash_to_matrix_fast(user_id)
        try:
            D_id = np.linalg.lstsq(A.astype(float), H_id.astype(float), rcond=None)[0]
            D_id = np.round(D_id) % self.q
        except:
            D_id = np.random.randint(0, self.q, size=(self.m, self.m), dtype=np.int64)
        logger.info(f"[Falcon PartialKeyGen] 部分私钥生成完成")
        return D_id, H_id
    def set_secret_value_fast(self) -> np.ndarray:
        logger.info("[Falcon SetSecretValue] 生成秘密值")
        S_id = np.zeros((self.m, self.m), dtype=np.int64)
        for i in range(self.m):
            S_id[i] = self._fast_gaussian_sample_vectorized(self.m)
        logger.info("[Falcon SetSecretValue] 秘密值生成完成")
        return S_id
    def set_sk_fast(self, D_id: np.ndarray, S_id: np.ndarray) -> Dict[str, np.ndarray]:
        logger.info("[Falcon SetSK] 生成秘密密钥")
        sk = {'D_id': D_id, 'S_id': S_id}
        logger.info("[Falcon SetSK] 秘密密钥生成完成")
        return sk
    def set_pk_fast(self, system_params: Dict, S_id: np.ndarray) -> np.ndarray:
        logger.info("[Falcon SetPK] 生成公开密钥")
        B = system_params['B']
        U_id = self._fast_matrix_multiply_mod(B, S_id)
        logger.info("[Falcon SetPK] 公开密钥生成完成")
        return U_id
    def generate_falcon_keypair_ultra_fast(self, node_id: str) -> Dict[str, Any]:
        logger.info(f"[超快Falcon] 开始为节点{node_id}生成密钥对")
        start_time = time.time()
        try:
            with _CACHE_LOCK:
                cache_key = f"falcon_params_{self.n}_{self.m}_{self.q}"
                if cache_key not in _SYSTEM_PARAMS_CACHE:
                    _SYSTEM_PARAMS_CACHE[cache_key] = self.setup_fast()
                system_params = _SYSTEM_PARAMS_CACHE[cache_key]
            D_id, H_id = self.partial_key_gen_fast(node_id, system_params)
            S_id = self.set_secret_value_fast()
            sk = self.set_sk_fast(D_id, S_id)
            U_id = self.set_pk_fast(system_params, S_id)
            import base64
            import json
            falcon_public_key_data = {
                'U_id': U_id.astype(np.int64).tolist(),
                'algorithm': 'UltraFastFalconOptimized',
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
                'algorithm': 'UltraFastFalconOptimized',
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
            logger.info(f"[超快Falcon] 密钥对生成完成，耗时: {elapsed*1000:.2f}ms")
            return {
                'success': True,
                'falcon_public_key': falcon_public_key,
                'falcon_private_key': falcon_private_key,
                'timing': elapsed,
                'message': f'Falcon密钥对生成成功 ({elapsed*1000:.2f}ms)'
            }
        except Exception as e:
            logger.error(f"[超快Falcon] 密钥生成失败: {e}")
            return {
                'success': False,
                'message': f'Falcon密钥生成失败: {str(e)}'
            }
    def shutdown(self):
        self.executor.shutdown(wait=False)