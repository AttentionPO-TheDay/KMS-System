import numpy as np
import logging
import hashlib
from typing import Dict, Any, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import threading
from functools import lru_cache
import time
logger = logging.getLogger(__name__)
class ParallelGaussianSampler:
    def __init__(self, sigma: float = 1.17, num_workers: int = 8):
        self.sigma = sigma
        self.num_workers = num_workers
        self.executor = ThreadPoolExecutor(max_workers=num_workers)
        self.lock = threading.Lock()
        logger.info(f"[ParallelGaussianSampler] 初始化，{num_workers}个工作线程")
    @staticmethod
    def _sample_chunk(args: Tuple[int, int, float]) -> np.ndarray:
        chunk_id, size, sigma = args
        np.random.seed(chunk_id)
        return np.round(np.random.normal(0, sigma, size=size)).astype(np.int64)
    def sample_vector_parallel(self, size: int, q: int) -> np.ndarray:
        if size <= 1000:
            return np.round(np.random.normal(0, self.sigma, size=size)).astype(np.int64) % q
        chunk_size = max(256, size // self.num_workers)
        num_chunks = (size + chunk_size - 1) // chunk_size
        tasks = [(i, chunk_size if i < num_chunks - 1 else size - (num_chunks - 1) * chunk_size, self.sigma) 
                 for i in range(num_chunks)]
        chunks = list(self.executor.map(self._sample_chunk, tasks))
        result = np.concatenate(chunks)[:size]
        return result % q
    def sample_matrix_parallel(self, rows: int, cols: int, q: int) -> np.ndarray:
        if rows * cols <= 100000:
            u1 = np.random.uniform(0, 1, size=(rows, cols))
            u2 = np.random.uniform(0, 1, size=(rows, cols))
            z = np.sqrt(-2 * np.log(u1)) * np.cos(2 * np.pi * u2)
            return (z * self.sigma).astype(np.int64) % q
        def sample_row(row_id: int) -> np.ndarray:
            np.random.seed(row_id * 12289)
            u1 = np.random.uniform(0, 1, size=cols)
            u2 = np.random.uniform(0, 1, size=cols)
            z = np.sqrt(-2 * np.log(u1)) * np.cos(2 * np.pi * u2)
            return (z * self.sigma).astype(np.int64) % q
        tasks = list(range(rows))
        rows_data = list(self.executor.map(sample_row, tasks))
        return np.array(rows_data)
    def shutdown(self):
        self.executor.shutdown(wait=True)
        logger.info("[ParallelGaussianSampler] 关闭线程池")
class FastLatticeDelegation:
    def __init__(self, n: int = 512, m: int = 1024, q: int = 12289):
        self.n = n
        self.m = m
        self.q = q
        self.sigma = 1.17
        logger.info(f"[FastLatticeDelegation] 初始化，n={n}, m={m}, q={q}")
    def fast_generate_D_id(self, A: np.ndarray, H_id: np.ndarray) -> np.ndarray:
        logger.info("[FastLatticeDelegation] 使用快速委派生成D_id")
        try:
            D_id = np.linalg.lstsq(A.astype(np.float64), H_id.astype(np.float64), rcond=None)[0]
            D_id = np.round(D_id).astype(np.int64) % self.q
            verify = np.dot(A, D_id) % self.q
            error = np.linalg.norm(verify - H_id)
            logger.info(f"[FastLatticeDelegation] D_id生成完成，近似误差: {error:.2f}")
            return D_id
        except Exception as e:
            logger.warning(f"[FastLatticeDelegation] lstsq失败，使用随机采样: {e}")
            return np.random.randint(0, self.q, size=(self.m, self.m), dtype=np.int64)
    def fast_solve_iterative(self, A: np.ndarray, target: np.ndarray, iterations: int = 5) -> np.ndarray:
        X = np.random.rand(A.shape[1], target.shape[1]) * 100
        learning_rate = 0.001
        for iter_idx in range(iterations):
            residual = np.dot(A, X) - target
            grad = np.dot(A.T, residual)
            X = X - learning_rate * grad
        return np.round(X).astype(np.int64) % self.q
class UltraFastKeygenOptimized:
    def __init__(self, n: int = 512, m: int = 1024, q: int = 12289, num_workers: int = 8):
        self.n = n
        self.m = m
        self.q = q
        self.sigma = 1.17
        self.sampler = ParallelGaussianSampler(sigma=self.sigma, num_workers=num_workers)
        self.lattice = FastLatticeDelegation(n, m, q)
        self.system_params_cache: Dict[str, Any] = {}
        self.lock = threading.Lock()
        logger.info(f"[UltraFastKeygenOptimized] 初始化完成")
    def _cached_setup(self) -> Dict[str, np.ndarray]:
        cache_key = f"{self.n}_{self.m}_{self.q}"
        if cache_key not in self.system_params_cache:
            with self.lock:
                if cache_key not in self.system_params_cache:
                    logger.info("[UltraFastKeygenOptimized] Setup系统参数（首次，已缓存）")
                    A = np.random.randint(0, self.q, size=(self.n, self.m), dtype=np.int64)
                    B = np.random.randint(0, self.q, size=(self.n, self.m), dtype=np.int64)
                    self.system_params_cache[cache_key] = {'A': A, 'B': B}
        return self.system_params_cache[cache_key]
    def partial_key_gen_fast(self, node_id: str) -> Tuple[np.ndarray, np.ndarray]:
        logger.info(f"[部分私钥生成] 节点{node_id}")
        params = self._cached_setup()
        A = params['A']
        H_id_hash = hashlib.sha256(node_id.encode()).digest()
        H_id = np.array([int(b) % self.q for b in H_id_hash] + 
                       [np.random.randint(0, self.q) for _ in range(self.n * self.m - len(H_id_hash))]
                       ).reshape(self.n, self.m)
        D_id = self.lattice.fast_generate_D_id(A, H_id)
        return D_id, H_id
    def set_secret_value_fast(self) -> np.ndarray:
        logger.info("[秘密值生成] SetSecretValue阶段")
        return self.sampler.sample_vector_parallel(self.m, self.q)
    def set_pk_fast(self, S_id: np.ndarray) -> np.ndarray:
        logger.info("[公开密钥生成] SetPK阶段")
        params = self._cached_setup()
        B = params['B']
        U_id = np.dot(B, S_id) % self.q
        return U_id
    def shutdown(self):
        self.sampler.shutdown()
        logger.info("[UltraFastKeygenOptimized] 系统关闭")