import numpy as np
import base64
import logging
import json
from typing import Dict, Any, Tuple
from Crypto.Random import get_random_bytes
logger = logging.getLogger(__name__)
class CertificatelessKyberSystem:
    def __init__(self, n: int = 512, m: int = 1024, q: int = 12289, sigma: float = 1.17):
        self.n = n
        self.m = m
        self.q = q
        self.sigma = sigma
        self.A = None
        self.S_0 = None
        self.pk_kgc = None
        self.D = None
        logger.info(f"CertificatelessKyberSystem初始化: n={n}, m={m}, q={q}, σ={sigma}")
    def setup(self) -> Dict[str, Any]:
        logger.info("[Setup] 开始生成系统参数")
        try:
            logger.info(f"[Setup] 生成随机矩阵A: ({self.n}, {self.m})")
            self.A = np.random.randint(0, self.q, size=(self.n, self.m), dtype=np.int64)
            logger.info(f"[Setup] 矩阵A生成完成")
            logger.info(f"[Setup] 生成KGC秘密密钥S_0: ({self.m}, {self.m})")
            self.S_0 = np.random.randint(0, 2, size=(self.m, self.m), dtype=np.int64)
            logger.info(f"[Setup] KGC秘密密钥S_0生成完成")
            logger.info(f"[Setup] 计算KGC公钥: U_0 = A · S_0")
            self.pk_kgc = np.matmul(self.A, self.S_0) % self.q
            logger.info(f"[Setup] KGC公钥U_0生成完成，形状: {self.pk_kgc.shape}")
            self.D = self.sigma
            logger.info(f"[Setup] 系统参数生成完成")
            return {
                'success': True,
                'A': self.A,
                'S_0': self.S_0,
                'pk_kgc': self.pk_kgc,
                'message': 'Setup阶段完成'
            }
        except Exception as e:
            logger.error(f"[Setup] 失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': f'Setup失败: {str(e)}'
            }
    def _discrete_gaussian_sample(self, shape: Tuple[int, ...]) -> np.ndarray:
        samples = np.random.normal(0, self.sigma, size=shape)
        samples = np.round(samples).astype(np.int64)
        samples = samples % self.q
        return samples
    def partial_key_gen(self, user_id: str) -> Tuple[np.ndarray, np.ndarray]:
        logger.info(f"[PartialKeyGen] 为用户{user_id}生成部分私钥")
        try:
            if self.A is None or self.S_0 is None:
                raise ValueError("系统参数未初始化，请先调用setup()")
            logger.info(f"[PartialKeyGen] 采样s'_id从离散高斯分布")
            s_prime_id = self._discrete_gaussian_sample((self.m,))
            logger.info(f"[PartialKeyGen] s'_id采样完成")
            logger.info(f"[PartialKeyGen] 计算u'_id = A · s'_id")
            u_prime_id = np.matmul(self.A, s_prime_id) % self.q
            logger.info(f"[PartialKeyGen] u'_id计算完成，形状: {u_prime_id.shape}")
            logger.info(f"[PartialKeyGen] 计算c = H(id, A)")
            import hashlib
            hash_input = user_id.encode('utf-8') + self.A.tobytes()
            hash_output = hashlib.sha256(hash_input).digest()
            c = np.frombuffer(hash_output, dtype=np.uint8)
            c = np.tile(c, (self.m // len(c) + 1))[:self.m]
            c = (c % 3) - 1
            c = c.astype(np.int64)
            logger.info(f"[PartialKeyGen] c计算完成，形状: {c.shape}")
            logger.info(f"[PartialKeyGen] 计算t = s'_id + S_0 · c")
            S_0_c = np.matmul(self.S_0, c) % self.q
            t = (s_prime_id + S_0_c) % self.q
            logger.info(f"[PartialKeyGen] t计算完成，形状: {t.shape}")
            logger.info(f"[PartialKeyGen] 部分私钥生成完成")
            return t, c
        except Exception as e:
            logger.error(f"[PartialKeyGen] 失败: {e}")
            import traceback
            traceback.print_exc()
            raise
    def set_secret_value(self) -> np.ndarray:
        logger.info(f"[SetSecretValue] 用户生成秘密值")
        try:
            logger.info(f"[SetSecretValue] 采样s_id从离散高斯分布")
            s_id = self._discrete_gaussian_sample((self.m,))
            logger.info(f"[SetSecretValue] s_id采样完成，形状: {s_id.shape}")
            return s_id
        except Exception as e:
            logger.error(f"[SetSecretValue] 失败: {e}")
            import traceback
            traceback.print_exc()
            raise
    def set_sk(self, t: np.ndarray, s_id: np.ndarray) -> np.ndarray:
        logger.info(f"[SetSK] 生成秘密密钥")
        try:
            logger.info(f"[SetSK] 计算sk = t + s_id")
            sk = (t + s_id) % self.q
            logger.info(f"[SetSK] 秘密密钥生成完成，形状: {sk.shape}")
            return sk
        except Exception as e:
            logger.error(f"[SetSK] 失败: {e}")
            import traceback
            traceback.print_exc()
            raise
    def set_pk(self, s_id: np.ndarray, c: np.ndarray) -> np.ndarray:
        logger.info(f"[SetPK] 生成公开密钥")
        try:
            if self.A is None or self.pk_kgc is None:
                raise ValueError("系统参数未初始化")
            logger.info(f"[SetPK] 计算u_id = A · s_id")
            u_id = np.matmul(self.A, s_id) % self.q
            logger.info(f"[SetPK] u_id计算完成，形状: {u_id.shape}")
            logger.info(f"[SetPK] 计算U_0 · c")
            U_0_c = np.matmul(self.pk_kgc, c) % self.q
            logger.info(f"[SetPK] U_0 · c计算完成")
            logger.info(f"[SetPK] 计算pk = u_id + U_0 · c")
            pk = (u_id + U_0_c) % self.q
            logger.info(f"[SetPK] 公开密钥生成完成，形状: {pk.shape}")
            return pk
        except Exception as e:
            logger.error(f"[SetPK] 失败: {e}")
            import traceback
            traceback.print_exc()
            raise
    def enc(self, message: bytes, pk: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        logger.info(f"[Enc] 加密消息")
        try:
            if self.A is None:
                raise ValueError("系统参数未初始化")
            M = np.frombuffer(message, dtype=np.uint8)
            M = np.tile(M, (self.m // len(M) + 1))[:self.m]
            M = (M % 2).astype(np.int64)
            logger.info(f"[Enc] 消息转换完成，形状: {M.shape}")
            logger.info(f"[Enc] 采样r从χ^n")
            r = self._discrete_gaussian_sample((self.n,))
            logger.info(f"[Enc] r采样完成")
            logger.info(f"[Enc] 采样e_1从χ^m")
            e_1 = self._discrete_gaussian_sample((self.m,))
            logger.info(f"[Enc] e_1采样完成")
            logger.info(f"[Enc] 采样e_2从χ")
            e_2 = self._discrete_gaussian_sample((1,))[0]
            logger.info(f"[Enc] e_2采样完成")
            logger.info(f"[Enc] 计算c_1 = A^t · r + e_1")
            A_t = self.A.T
            c_1 = (np.matmul(A_t, r) + e_1) % self.q
            logger.info(f"[Enc] c_1计算完成，形状: {c_1.shape}")
            logger.info(f"[Enc] 计算c_2 = u^t · r + e_2 + ⌊q/2⌋ · M")
            u_t = pk.T
            u_t_r = np.matmul(u_t, r) % self.q
            q_half = self.q // 2
            c_2 = (u_t_r + e_2 + q_half * M) % self.q
            logger.info(f"[Enc] c_2计算完成，形状: {c_2.shape}")
            logger.info(f"[Enc] 加密完成")
            return c_1, c_2
        except Exception as e:
            logger.error(f"[Enc] 失败: {e}")
            import traceback
            traceback.print_exc()
            raise
    def dec(self, c_1: np.ndarray, c_2: np.ndarray, sk: np.ndarray) -> bytes:
        logger.info(f"[Dec] 解密密文")
        try:
            logger.info(f"[Dec] 计算M = ⌊(c_2 - s^t · c_1) / (q/2)⌋")
            sk_t = sk.T
            s_t_c_1 = np.matmul(sk_t, c_1) % self.q
            logger.info(f"[Dec] s^t · c_1计算完成")
            q_half = self.q // 2
            numerator = (c_2 - s_t_c_1) % self.q
            logger.info(f"[Dec] 分子计算完成")
            M = np.round(numerator / q_half).astype(np.int64) % 2
            logger.info(f"[Dec] M计算完成，形状: {M.shape}")
            message = bytes(M[:8].astype(np.uint8))
            logger.info(f"[Dec] 解密完成")
            return message
        except Exception as e:
            logger.error(f"[Dec] 失败: {e}")
            import traceback
            traceback.print_exc()
            raise