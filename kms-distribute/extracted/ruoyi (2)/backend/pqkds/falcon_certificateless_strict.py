import numpy as np
import hashlib
import logging
from typing import Dict, Tuple, Any
import json

logger = logging.getLogger(__name__)


class CertificatelessFalconStrict:
    """
    无证书格密码方案的严格实现。

    密钥结构:
    - D_id: m×m 短矩阵 (部分私钥，由 KGC 生成)，元素 ∈ {-B, ..., B}
    - S_id: m×m 短矩阵 (用户秘密值)，元素 ∈ {-B, ..., B}
    - H(id) = A·D_id mod q  (n×m 公开矩阵)
    - U_id = B·S_id mod q   (n×m 公开矩阵)

    加密 (Encrypt):
    c₁ = Aᵀ·r₁ + e₁  mod q
    c₂ = Bᵀ·r₂ + e₂  mod q
    c₃ = H(id)ᵀ·r₁ + U_idᵀ·r₂ + e₃ + ⌊q/2⌋·μ  mod q

    解密 (Decrypt):
    μ' = c₃ - D_idᵀ·c₁ - S_idᵀ·c₂  mod q
       = e₃ - D_idᵀ·e₁ - S_idᵀ·e₂ + ⌊q/2⌋·μ  mod q
    当 D_id, S_id 短且噪声小时，rounding 可正确恢复 μ
    """

    def __init__(self, n: int = 512, m: int = 1024, q: int = 12289):
        self.n = n
        self.m = m
        self.q = q
        self.beta = q // 4
        self.beta_prime = q // 8
        self.sigma = 1.17  # 噪声标准差
        self.system_params = None
        self.kgc_keys = None
        logger.info(f"CertificatelessFalconStrict初始化: n={n}, m={m}, q={q}")

    def setup(self) -> Dict[str, Any]:
        """Setup: 生成系统公开参数 A (n×m), B (n×m)"""
        logger.info("[Setup] 开始生成系统参数")
        A = np.random.randint(0, self.q, size=(self.n, self.m), dtype=np.int64)
        B = np.random.randint(0, self.q, size=(self.n, self.m), dtype=np.int64)
        logger.info(f"[Setup] A: {A.shape}, B: {B.shape}")

        self.system_params = {
            'A': A, 'B': B,
            'n': self.n, 'm': self.m, 'q': self.q,
            'beta': self.beta, 'beta_prime': self.beta_prime,
            'sigma': self.sigma
        }
        # KGC 的主密钥就是 A 本身（用于生成部分私钥）
        self.kgc_keys = {'pk_KGC': A, 'sk_KGC': A}
        logger.info("[Setup] 系统参数生成完成")
        return {'success': True}

    def partial_key_gen(self, user_id: str) -> Tuple[np.ndarray, np.ndarray]:
        """
        PartialKeyGen: KGC 为用户生成部分私钥 D_id (短矩阵)
        D_id ∈ Z^{m×m}，元素从离散高斯分布采样
        H(id) = A·D_id mod q (公开)
        """
        if self.system_params is None or self.kgc_keys is None:
            raise ValueError("系统未初始化，请先调用setup()")
        logger.info(f"[PartialKeyGen] 为用户{user_id}生成部分私钥")

        A = self.system_params['A']

        # 使用确定性种子生成 D_id
        seed = int(hashlib.sha256(user_id.encode()).hexdigest(), 16) % (2**32)
        rng = np.random.RandomState(seed)
        D_id = np.round(rng.normal(0, self.sigma, size=(self.m, self.m))).astype(np.int64)
        logger.info(f"[PartialKeyGen] D_id: {D_id.shape}, max|D_id|={np.max(np.abs(D_id))}")

        # H(id) = A·D_id mod q
        H_id = np.dot(A, D_id) % self.q
        logger.info(f"[PartialKeyGen] H(id): {H_id.shape}")

        return D_id, H_id

    def set_secret_value(self) -> np.ndarray:
        """SetSecretValue: 用户生成秘密值 S_id (短矩阵)"""
        logger.info("[SetSecretValue] 用户生成秘密值S_id")
        S_id = np.round(
            np.random.normal(0, self.sigma, size=(self.m, self.m))
        ).astype(np.int64)
        logger.info(f"[SetSecretValue] S_id生成完成: {S_id.shape}, 最大元素: {np.max(np.abs(S_id))}")
        return S_id

    def set_sk(self, D_id: np.ndarray, S_id: np.ndarray) -> dict:
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

    def _hash_to_matrix(self, data: str) -> np.ndarray:
        """
        H(id): 计算用户的公开矩阵 H(id) = A·D_id mod q
        需要先调用 partial_key_gen 生成 D_id
        """
        # 使用确定性种子重新生成 D_id
        seed = int(hashlib.sha256(data.encode()).hexdigest(), 16) % (2**32)
        rng = np.random.RandomState(seed)
        D_id = np.round(rng.normal(0, self.sigma, size=(self.m, self.m))).astype(np.int64)
        A = self.system_params['A']
        H_id = np.dot(A, D_id) % self.q
        return H_id

    def _matrix_norm(self, M: np.ndarray) -> float:
        return float(np.linalg.norm(M))