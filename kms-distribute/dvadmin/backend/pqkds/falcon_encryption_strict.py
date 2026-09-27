import numpy as np
import hashlib
import logging
import os
from typing import Dict, Any
import json

logger = logging.getLogger(__name__)

# Falcon-512 和 Falcon-1024 的格密码参数
FALCON_PARAMS = {
    512: {'n': 512, 'm': 1024, 'q': 12289},
    1024: {'n': 1024, 'm': 2048, 'q': 12289},
}


class CertificatelessFalconEncryption:
    """
    严格按照无证书格密码加密方案实现的 Falcon 加解密。

    Encrypt(params, ID, U_ID, μ):
        1. 采样 r₁, r₂ ← Z_q^n (随机向量)
        2. 采样 e₁, e₂ ∈ Z_q^m, e₃ ∈ Z_q^m (噪声向量，高斯分布)
        3. c₁ = Aᵀ·r₁ + e₁  mod q
        4. c₂ = Bᵀ·r₂ + e₂  mod q
        5. c₃ = H(ID)ᵀ·r₁ + U_IDᵀ·r₂ + e₃ + ⌊q/2⌋·μ  mod q
        6. 输出密文 C = (c₁, c₂, c₃)

    Decrypt(params, SK_ID = {D_ID, S_ID}, C):
        1. 计算 μ' = c₃ - D_IDᵀ·c₁ - S_IDᵀ·c₂  mod q
        2. 对 μ' 的每个分量做 rounding: 若距 ⌊q/2⌋ 更近则为 1，否则为 0
        3. 恢复消息比特串 μ
    """

    def __init__(self, certificateless_falcon: 'CertificatelessFalconStrict'):
        self.cf = certificateless_falcon
        self.q = certificateless_falcon.q
        self.n = certificateless_falcon.n
        self.m = certificateless_falcon.m
        self.sigma = getattr(certificateless_falcon, 'sigma', 1.17)
        self.half_q = self.q // 2
        # 每个格元素可嵌入 1 bit，m 个分量可嵌入 m bits
        self.capacity_bits = self.m
        logger.info(
            f"CertificatelessFalconEncryption初始化完成: "
            f"n={self.n}, m={self.m}, q={self.q}, 容量={self.capacity_bits} bits"
        )

    def _sample_gaussian_vector(self, size: int) -> np.ndarray:
        """采样离散高斯噪声向量 e ← D_{Z^size, σ}"""
        samples = np.random.normal(0, self.sigma, size=size)
        return np.round(samples).astype(np.int64) % self.q

    def _sample_uniform_vector(self, size: int) -> np.ndarray:
        """采样均匀随机向量 r ← Z_q^size"""
        return np.random.randint(0, self.q, size=size, dtype=np.int64)

    def _encode_message_to_bits(self, message: bytes) -> np.ndarray:
        """
        将消息字节串直接编码为比特向量 μ ∈ {0,1}^m。
        消息比特放在前 len(message)*8 个位置，其余位置填 0。
        Falcon-512: m=1024 bits = 128 bytes 容量，可嵌入 32 字节 AES 密钥
        Falcon-1024: m=2048 bits = 256 bytes 容量
        """
        msg_bits = len(message) * 8
        if msg_bits > self.m:
            raise ValueError(
                f"消息长度 {len(message)} 字节 ({msg_bits} bits) "
                f"超过格密码容量 {self.m} bits"
            )
        bits = np.zeros(self.m, dtype=np.int64)
        for i in range(msg_bits):
            byte_idx = i // 8
            bit_idx = i % 8
            bits[i] = (message[byte_idx] >> bit_idx) & 1
        return bits

    def _decode_bits_to_message(self, bits: np.ndarray, msg_length: int) -> bytes:
        """
        将比特向量 μ ∈ {0,1}^m 的前 msg_length*8 个比特解码回字节串。
        """
        result = bytearray(msg_length)
        for i in range(msg_length * 8):
            if bits[i] == 1:
                byte_idx = i // 8
                bit_idx = i % 8
                result[byte_idx] |= (1 << bit_idx)
        return bytes(result)

    def _round_to_bit(self, value: np.int64) -> int:
        """
        Rounding 解码：判断 value mod q 距离 0 还是 ⌊q/2⌋ 更近。
        若距 ⌊q/2⌋ 更近 → bit=1，否则 → bit=0。
        """
        v = int(value) % self.q
        dist_to_zero = min(v, self.q - v)
        dist_to_half = abs(v - self.half_q)
        return 1 if dist_to_half < dist_to_zero else 0

    def encrypt_session_key(self, recipient_id: str, session_key: bytes,
                            recipient_pk: np.ndarray) -> Dict[str, Any]:
        """
        使用无证书格密码方案加密 AES 会话密钥。

        严格按照图片中的 Encrypt 算法:
        c₁ = Aᵀ·r₁ + e₁
        c₂ = Bᵀ·r₂ + e₂
        c₃ = H(ID)ᵀ·r₁ + U_IDᵀ·r₂ + e₃ + ⌊q/2⌋·μ
        """
        logger.info(f"[Enc] 开始加密会话密钥，接收者: {recipient_id}, 密钥长度: {len(session_key)} bytes")
        logger.info(f"[Enc] 安全级别: Falcon-{self.n}, 参数: n={self.n}, m={self.m}, q={self.q}")

        if self.cf.system_params is None:
            logger.info(f"[Enc] 系统参数未初始化，自动生成...")
            setup_result = self.cf.setup()
            if not setup_result['success']:
                raise ValueError("系统参数生成失败")

        A = self.cf.system_params['A']  # n × m
        B = self.cf.system_params['B']  # n × m
        H_id = self.cf._hash_to_matrix(recipient_id)  # n × m
        logger.info(f"[Enc] 系统矩阵: A={A.shape}, B={B.shape}, H(id)={H_id.shape}")

        # 处理 U_id (recipient_pk) 的维度
        # U_id 应为 n 维向量 (SetPK: U_id = B · S_id mod q)
        # 但在加密中需要 H(ID)ᵀ·r₁ 和 U_IDᵀ·r₂ 都产生 m 维结果
        # 所以 U_id 实际上是 n×m 矩阵或 n 维向量
        U_id = recipient_pk
        logger.info(f"[Enc] 接收方公钥 U_id 形状: {U_id.shape}")

        # Step 1: 将会话密钥编码为比特向量 μ ∈ {0,1}^m
        mu = self._encode_message_to_bits(session_key)
        logger.info(f"[Enc] 消息编码为 {self.m} 比特向量")

        # Step 2: 采样随机向量和噪声向量
        r_1 = self._sample_uniform_vector(self.n)   # r₁ ∈ Z_q^n
        r_2 = self._sample_uniform_vector(self.n)   # r₂ ∈ Z_q^n
        e_1 = self._sample_gaussian_vector(self.m)   # e₁ ∈ Z_q^m
        e_2 = self._sample_gaussian_vector(self.m)   # e₂ ∈ Z_q^m
        e_3 = self._sample_gaussian_vector(self.m)   # e₃ ∈ Z_q^m
        logger.info(f"[Enc] 随机向量和噪声向量采样完成")

        # Step 3: 计算密文
        # c₁ = Aᵀ·r₁ + e₁  mod q    (Aᵀ: m×n, r₁: n → c₁: m)
        c1 = (np.dot(A.T, r_1) + e_1) % self.q

        # c₂ = Bᵀ·r₂ + e₂  mod q    (Bᵀ: m×n, r₂: n → c₂: m)
        c2 = (np.dot(B.T, r_2) + e_2) % self.q

        # c₃ = H(ID)ᵀ·r₁ + U_IDᵀ·r₂ + e₃ + ⌊q/2⌋·μ  mod q
        # H(ID)ᵀ: m×n, r₁: n → m 维
        c3_term1 = np.dot(H_id.T, r_1) % self.q

        # U_ID 的处理: 如果是 n 维向量，需要扩展为 m 维结果
        if U_id.ndim == 1:
            # U_id 是 n 维向量，U_idᵀ·r₂ 是标量，需要广播到 m 维
            # 按照格密码方案，这里用 B·S_id 的结构: 将标量结果广播
            u_r2_scalar = int(np.dot(U_id, r_2) % self.q)
            c3_term2 = np.full(self.m, u_r2_scalar, dtype=np.int64) % self.q
        else:
            # U_id 是矩阵 (n×m 或 m×n)
            if U_id.shape[0] == self.n and U_id.shape[1] == self.m:
                c3_term2 = np.dot(U_id.T, r_2) % self.q  # m×n · n → m
            elif U_id.shape[0] == self.m and U_id.shape[1] == self.n:
                c3_term2 = np.dot(U_id, r_2) % self.q    # m×n · n → m
            else:
                c3_term2 = np.dot(U_id.T, r_2) % self.q

        # ⌊q/2⌋·μ: 消息嵌入项
        msg_embed = (self.half_q * mu) % self.q

        c3 = (c3_term1 + c3_term2 + e_3 + msg_embed) % self.q
        logger.info(f"[Enc] 密文计算完成: c1={c1.shape}, c2={c2.shape}, c3={c3.shape}")

        # 构造密文输出
        result = {
            'c1': c1.tolist(),
            'c2': c2.tolist(),
            'c3': c3.tolist(),
            'security_level': self.n,
            'params': {'n': self.n, 'm': self.m, 'q': self.q},
            'session_key_length': len(session_key)
        }

        logger.info(f"[Enc] 加密完成，安全级别: Falcon-{self.n}")
        return {
            'success': True,
            'ciphertext': json.dumps(result),
            'algorithm': f'CertificatelessFalcon-{self.n}'
        }

    def encrypt_session_key_with_params(self, recipient_id: str, session_key: bytes,
                                        U_id: np.ndarray, H_id: np.ndarray,
                                        A: np.ndarray, B: np.ndarray) -> Dict[str, Any]:
        """
        使用指定的系统参数加密 AES 会话密钥（不调用 setup/partial_key_gen）。

        参数直接从公钥中提取，确保加密和解密使用相同的 A、B。
        c₁ = Aᵀ·r₁ + e₁
        c₂ = Bᵀ·r₂ + e₂
        c₃ = H(ID)ᵀ·r₁ + U_IDᵀ·r₂ + e₃ + ⌊q/2⌋·μ
        """
        logger.info(f"[Enc] 使用公钥参数加密, 接收者: {recipient_id}, 密钥: {len(session_key)} bytes")
        logger.info(f"[Enc] A={A.shape}, B={B.shape}, H_id={H_id.shape}, U_id={U_id.shape}")

        mu = self._encode_message_to_bits(session_key)

        r_1 = self._sample_uniform_vector(self.n)
        r_2 = self._sample_uniform_vector(self.n)
        e_1 = self._sample_gaussian_vector(self.m)
        e_2 = self._sample_gaussian_vector(self.m)
        e_3 = self._sample_gaussian_vector(self.m)

        c1 = (np.dot(A.T, r_1) + e_1) % self.q
        c2 = (np.dot(B.T, r_2) + e_2) % self.q

        c3_term1 = np.dot(H_id.T, r_1) % self.q

        if U_id.ndim == 1:
            u_r2_scalar = int(np.dot(U_id, r_2) % self.q)
            c3_term2 = np.full(self.m, u_r2_scalar, dtype=np.int64) % self.q
        else:
            if U_id.shape[0] == self.n and U_id.shape[1] == self.m:
                c3_term2 = np.dot(U_id.T, r_2) % self.q
            elif U_id.shape[0] == self.m and U_id.shape[1] == self.n:
                c3_term2 = np.dot(U_id, r_2) % self.q
            else:
                c3_term2 = np.dot(U_id.T, r_2) % self.q

        msg_embed = (self.half_q * mu) % self.q
        c3 = (c3_term1 + c3_term2 + e_3 + msg_embed) % self.q

        logger.info(f"[Enc] 密文: c1={c1.shape}, c2={c2.shape}, c3={c3.shape}")

        result = {
            'c1': c1.tolist(),
            'c2': c2.tolist(),
            'c3': c3.tolist(),
            'security_level': self.n,
            'params': {'n': self.n, 'm': self.m, 'q': self.q},
            'session_key_length': len(session_key)
        }

        return {
            'success': True,
            'ciphertext': json.dumps(result),
            'algorithm': f'CertificatelessFalcon-{self.n}'
        }

    def decrypt_session_key(self, ciphertext_json: str, secret_key_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        使用无证书格密码方案解密 AES 会话密钥。

        严格按照图片中的 Decrypt 算法:
        μ' = c₃ - D_IDᵀ·c₁ - S_IDᵀ·c₂  mod q
        对 μ' 每个分量做 rounding 恢复比特
        """
        logger.info(f"[Dec] 开始解密会话密钥, 安全级别: Falcon-{self.n}")
        try:
            if isinstance(ciphertext_json, str):
                ct = json.loads(ciphertext_json)
            else:
                ct = ciphertext_json

            c1 = np.array(ct['c1'], dtype=np.int64)
            c2 = np.array(ct['c2'], dtype=np.int64)
            c3 = np.array(ct['c3'], dtype=np.int64)
            session_key_length = ct.get('session_key_length', 32)

            D_id = np.array(secret_key_dict['D_id'], dtype=np.int64)
            S_id = np.array(secret_key_dict['S_id'], dtype=np.int64)
            logger.info(f"[Dec] 密文维度: c1={c1.shape}, c2={c2.shape}, c3={c3.shape}")
            logger.info(f"[Dec] 私钥维度: D_id={D_id.shape}, S_id={S_id.shape}")

            # Step 1: μ' = c₃ - D_IDᵀ·c₁ - S_IDᵀ·c₂  mod q
            # D_id: m×m 矩阵, c1: m 向量 → D_idᵀ·c1: m 向量
            if D_id.ndim == 2:
                term1 = np.dot(D_id.T, c1) % self.q
            else:
                # D_id 是 m 维向量
                term1 = (D_id * c1) % self.q

            if S_id.ndim == 2:
                term2 = np.dot(S_id.T, c2) % self.q
            else:
                # S_id 是 m 维向量
                term2 = (S_id * c2) % self.q

            mu_prime = (c3 - term1 - term2) % self.q
            logger.info(f"[Dec] μ' 计算完成, 形状: {mu_prime.shape}")

            # Step 2: Rounding 解码 - 对每个分量判断距 0 还是 ⌊q/2⌋ 更近
            recovered_bits = np.zeros(self.m, dtype=np.int64)
            for i in range(self.m):
                recovered_bits[i] = self._round_to_bit(mu_prime[i])

            logger.info(f"[Dec] Rounding 解码完成, 恢复 {self.m} 比特")

            # Step 3: 将比特向量解码回字节串 (只取前 session_key_length*8 个比特)
            session_key = self._decode_bits_to_message(recovered_bits, session_key_length)

            logger.info(f"[Dec] 会话密钥恢复完成: {len(session_key)} 字节")
            return {
                'success': True,
                'session_key': session_key,
                'key_length': len(session_key),
                'algorithm': f'CertificatelessFalcon-{self.n}'
            }
        except Exception as e:
            logger.error(f"[Dec] 解密失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': f"解密失败: {str(e)}"
            }