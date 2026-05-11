import numpy as np
import hashlib
import logging
from typing import Dict, Tuple, Any
from concurrent.futures import ThreadPoolExecutor
import threading
logger = logging.getLogger(__name__)


class ParallelShortVectorSampler:
    def __init__(self, sigma: float = 1.17, num_workers: int = 4):
        self.sigma = sigma
        self.num_workers = num_workers
        self.executor = ThreadPoolExecutor(max_workers=num_workers)

    def sample_short_matrix_parallel(self, rows: int, cols: int) -> np.ndarray:
        """快速采样短矩阵（离散高斯分布），向量化操作"""
        samples = np.random.normal(0, self.sigma, size=(rows, cols))
        return np.round(samples).astype(np.int64)

    def shutdown(self):
        self.executor.shutdown(wait=True)


class CertificatelessFalconStrictOptimized:
    """
    无证书Falcon方案的优化实现（与CertificatelessFalconStrict数学一致）。

    D_id: m×m 短矩阵（离散高斯），确定性生成（从node_id派生种子）
    H_id = A·D_id mod q
    S_id: m×m 短矩阵（离散高斯）
    U_id = B·S_id mod q
    """

    def __init__(self, n: int = 512, m: int = 1024, q: int = 12289, num_workers: int = 4):
        self.n = n
        self.m = m
        self.q = q
        self.beta = q // 4
        self.beta_prime = q // 8
        self.sigma = 1.17
        self.system_params = None
        self.kgc_keys = None
        self.sampler = ParallelShortVectorSampler(sigma=self.sigma, num_workers=num_workers)
        logger.info(f"CertificatelessFalconStrictOptimized初始化: n={n}, m={m}, q={q}, workers={num_workers}")

    def setup(self) -> Dict[str, Any]:
        """Setup: 生成系统公开参数 A (n×m), B (n×m)"""
        logger.info("[Setup] 开始生成系统参数（优化版本）")
        A = np.random.randint(0, self.q, size=(self.n, self.m), dtype=np.int64)
        B = np.random.randint(0, self.q, size=(self.n, self.m), dtype=np.int64)
        logger.info(f"[Setup] A: {A.shape}, B: {B.shape}")
        self.system_params = {
            'A': A, 'B': B,
            'n': self.n, 'm': self.m, 'q': self.q,
            'beta': self.beta, 'beta_prime': self.beta_prime,
            'sigma': self.sigma
        }
        self.kgc_keys = {'pk_KGC': A, 'sk_KGC': A}
        logger.info("[Setup] 系统参数生成完成")
        return {'success': True}

    def partial_key_gen(self, user_id: str) -> Dict[str, Any]:
        """
        PartialKeyGen: 为用户生成部分私钥 D_id (短矩阵)
        D_id 使用确定性种子生成，确保同一 id 总是得到相同的 D_id
        H_id = A·D_id mod q
        """
        if self.system_params is None or self.kgc_keys is None:
            raise ValueError("系统未初始化，请先调用setup()")
        logger.info(f"[PartialKeyGen] 为用户{user_id}生成部分私钥（优化版本）")
        A = self.system_params['A']

        # 确定性种子 — 与 CertificatelessFalconStrict.partial_key_gen 完全一致
        seed = int(hashlib.sha256(user_id.encode()).hexdigest(), 16) % (2**32)
        rng = np.random.RandomState(seed)
        D_id = np.round(rng.normal(0, self.sigma, size=(self.m, self.m))).astype(np.int64)
        logger.info(f"[PartialKeyGen] D_id: {D_id.shape}, max|D_id|={np.max(np.abs(D_id))}")

        H_id = np.dot(A, D_id) % self.q
        logger.info(f"[PartialKeyGen] H(id): {H_id.shape}")
        return {
            'success': True,
            'D_id': D_id,
            'H_id': H_id
        }

    def set_secret_value(self) -> np.ndarray:
        """SetSecretValue: 用户生成秘密值 S_id (短矩阵)"""
        logger.info("[SetSecretValue] 用户生成秘密值（并行采样）")
        S_id = self.sampler.sample_short_matrix_parallel(self.m, self.m)
        logger.info(f"[SetSecretValue] S_id: {S_id.shape}, max|S_id|={np.max(np.abs(S_id))}")
        return S_id

    def set_sk(self, D_id: np.ndarray, S_id: np.ndarray) -> Dict[str, np.ndarray]:
        """SetSK: SK_id = {D_id, S_id}"""
        logger.info("[SetSK] 生成秘密密钥")
        return {'D_id': D_id, 'S_id': S_id}

    def set_pk(self, S_id: np.ndarray) -> np.ndarray:
        """SetPK: U_id = B·S_id mod q"""
        if self.system_params is None:
            raise ValueError("系统参数未初始化")
        logger.info("[SetPK] 计算公开密钥")
        B = self.system_params['B']
        U_id = np.dot(B, S_id) % self.q
        logger.info(f"[SetPK] U_id: {U_id.shape}")
        return U_id

    def shutdown(self):
        self.sampler.shutdown()