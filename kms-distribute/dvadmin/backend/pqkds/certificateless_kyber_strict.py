import numpy as np
import hashlib
import logging
from typing import Dict, Tuple, Any
logger = logging.getLogger(__name__)
class CertificatelessKyberStrict:
    def __init__(self, n: int = 512, m: int = 1024, q: int = 12289, sigma: float = 1.17):
        self.n = n
        self.m = m
        self.q = q
        self.sigma = sigma
        self.system_params = None
        logger.info(f"无证书Kyber初始化: n={n}, m={m}, q={q}, σ={sigma}")
    def setup(self) -> Dict[str, Any]:
        logger.info("执行Setup阶段：生成系统参数")
        A = np.random.randint(0, self.q, size=(self.n, self.m), dtype=np.int64)
        logger.info(f"生成矩阵 A ∈ Z_q^{{{self.n}×{self.m}}}")
        S_0 = np.random.randint(0, 2, size=(self.m, self.m), dtype=np.int64)
        logger.info(f"KGC生成秘密密钥 S_0 ∈ {{0,1}}^{{{self.m}×{self.m}}}")
        U_0 = np.dot(A, S_0) % self.q
        logger.info(f"计算 U_0 = A·S_0 ∈ Z_q^{{{self.n}×{self.m}}}")
        self.system_params = {
            'A': A,
            'S_0': S_0,
            'U_0': U_0,
            'n': self.n,
            'm': self.m,
            'q': self.q,
            'sigma': self.sigma
        }
        logger.info("Setup完成")
        return self.system_params
    def sample_gaussian(self, dim: int) -> np.ndarray:
        return np.random.normal(0, self.sigma, dim).astype(np.int64) % self.q
    def hash_function(self, data: bytes, dim: int) -> np.ndarray:
        hash_obj = hashlib.sha256(data)
        hash_bytes = hash_obj.digest()
        result = np.zeros(dim, dtype=np.int64)
        for i in range(dim):
            byte_val = hash_bytes[i % len(hash_bytes)]
            result[i] = (byte_val % 3) - 1
        return result
    def partial_key_gen(self, user_id: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        if self.system_params is None:
            raise ValueError("系统未初始化")
        logger.info(f"PartialKeyGen: 为用户 {user_id} 生成部分密钥")
        A = self.system_params['A']
        S_0 = self.system_params['S_0']
        s_prime_id = self.sample_gaussian(self.m)
        logger.info(f"采样 s'_id ∈ D^{self.m}")
        u_prime_id = np.dot(A, s_prime_id) % self.q
        logger.info(f"计算 u'_id = A·s'_id (mod {self.q})")
        id_bytes = user_id.encode('utf-8')
        A_bytes = self.system_params['A'].tobytes()
        c = self.hash_function(id_bytes + A_bytes, self.m)
        logger.info(f"计算 c = H(id, A)")
        S0_c = np.dot(S_0, c) % self.q
        t = (s_prime_id + S0_c) % self.q
        logger.info(f"计算 t = s'_id + S_0·c (mod {self.q})")
        return t, c, u_prime_id
    def set_secret_value(self) -> np.ndarray:
        logger.info("SetSecretValue: 用户选择秘密值")
        s_id = self.sample_gaussian(self.m)
        logger.info(f"采样 s_id ∈ D^{self.m}")
        return s_id
    def set_sk(self, t: np.ndarray, s_id: np.ndarray) -> np.ndarray:
        logger.info("SetSK: 计算秘密密钥")
        sk = (t + s_id) % self.q
        logger.info(f"计算 sk = t + s_id (mod {self.q})")
        return sk
    def set_pk(self, u_prime_id: np.ndarray, c: np.ndarray, s_id: np.ndarray) -> np.ndarray:
        if self.system_params is None:
            raise ValueError("系统未初始化")
        logger.info("SetPK: 计算公开密钥")
        A = self.system_params['A']
        U_0 = self.system_params['U_0']
        U0_c = np.dot(U_0, c) % self.q
        logger.info("计算 U_0·c")
        A_sid = np.dot(A, s_id) % self.q
        logger.info("计算 A·s_id")
        pk = (u_prime_id + U0_c + A_sid) % self.q
        logger.info(f"计算 pk = u'_id + U_0·c + A·s_id (mod {self.q})")
        return pk
    def encrypt(self, public_key: np.ndarray, message: int) -> Tuple[np.ndarray, np.ndarray]:
        logger.info(f"Enc: 加密消息 M={message}")
        A = self.system_params['A']
        r = self.sample_gaussian(self.n)
        e_1 = self.sample_gaussian(self.m)
        e_2 = self.sample_gaussian(1)[0]
        logger.info("采样 r ← χ^n, e_1 ← χ^m, e_2 ← χ")
        c_1 = (np.dot(r, A) + e_1) % self.q
        logger.info("计算 c_1 = r^T·A + e_1 (mod q)")
        u_T_r = np.dot(public_key, r) % self.q
        c_2 = (u_T_r + e_2 + (self.q // 2) * message) % self.q
        logger.info(f"计算 c_2 = u^T·r + e_2 + ⌊q/2⌋·M (mod q)")
        return c_1, np.array([c_2])
    def decrypt(self, secret_key: np.ndarray, c_1: np.ndarray, c_2: np.ndarray) -> int:
        logger.info("Dec: 解密密文")
        if isinstance(c_2, np.ndarray):
            c_2_val = c_2[0] if c_2.size > 0 else c_2
        else:
            c_2_val = c_2
        message = int(c_2_val > self.q // 2)
        logger.info(f"恢复消息 M = {message}")
        return message
class KyberAESSessionKeyEncryption:
    def __init__(self, kyber: CertificatelessKyberStrict = None):
        self.kyber = kyber or CertificatelessKyberStrict()
        self.aes_key_size = 32
        logger.info("KyberAES会话密钥加密模块初始化")
    def generate_system_params(self) -> Dict[str, Any]:
        return self.kyber.setup()
    def generate_node_keypair(self, node_id: str) -> Dict[str, Any]:
        logger.info(f"为节点 {node_id} 生成无证书Kyber密钥对")
        t, c, u_prime_id = self.kyber.partial_key_gen(node_id)
        logger.info(f"步骤1完成: KGC生成部分密钥")
        s_id = self.kyber.set_secret_value()
        logger.info(f"步骤2完成: 节点选择秘密值")
        sk = self.kyber.set_sk(t, s_id)
        logger.info(f"步骤3完成: 计算完整私钥")
        pk = self.kyber.set_pk(u_prime_id, c, s_id)
        logger.info(f"步骤4完成: 计算完整公钥")
        keypair = {
            'node_id': node_id,
            'public_key': pk.tolist(),
            'private_key': sk.tolist(),
            'partial_key_t': t.tolist(),
            'secret_value_s_id': s_id.tolist(),
            'hash_c': c.tolist(),
            'u_prime_id': u_prime_id.tolist(),
            'algorithm': 'CertificatelessKyberStrict'
        }
        logger.info(f"节点 {node_id} 密钥对生成完成")
        return keypair
    def encrypt_aes_key_with_kyber(self, public_key: list, aes_key: bytes) -> Dict[str, Any]:
        logger.info(f"使用Kyber公钥加密AES会话密钥 (长度: {len(aes_key)} bytes)")
        pk = np.array(public_key, dtype=np.int64)
        ciphertexts = []
        message_bits = []
        for i, byte_val in enumerate(aes_key):
            for bit_idx in range(8):
                message_bit = (byte_val >> bit_idx) & 1
                message_bits.append(message_bit)
                c_1, c_2 = self.kyber.encrypt(pk, message_bit)
                ciphertexts.append({
                    'c_1': c_1.tolist(),
                    'c_2': c_2.tolist()
                })
        logger.info(f"AES密钥加密完成: {len(ciphertexts)} 个密文")
        return {
            'ciphertexts': ciphertexts,
            'message_bits_count': len(message_bits),
            'aes_key_size_bytes': len(aes_key),
            'algorithm': 'Kyber-AES'
        }
    def decrypt_aes_key_with_kyber(self, private_key: list, encrypted_data: Dict) -> bytes:
        logger.info("使用Kyber私钥解密AES会话密钥")
        sk = np.array(private_key, dtype=np.int64)
        ciphertexts = encrypted_data['ciphertexts']
        aes_key_size_bytes = encrypted_data['aes_key_size_bytes']
        message_bits = []
        for ct_idx, ct in enumerate(ciphertexts):
            c_1 = np.array(ct['c_1'], dtype=np.int64)
            c_2 = np.array(ct['c_2'], dtype=np.int64)
            c_2_val = c_2[0] if isinstance(c_2, np.ndarray) else c_2
            c_2_val = int(c_2_val) % int(self.kyber.q)
            midpoint = self.kyber.q // 2
            dist_to_zero = min(c_2_val, self.kyber.q - c_2_val)
            dist_to_mid = min(abs(c_2_val - midpoint), self.kyber.q - abs(c_2_val - midpoint))
            message_bit = 1 if dist_to_mid < dist_to_zero else 0
            message_bits.append(message_bit)
        aes_key_bytes = bytearray()
        for byte_idx in range(aes_key_size_bytes):
            byte_val = 0
            for bit_idx in range(8):
                bit_pos = byte_idx * 8 + bit_idx
                if bit_pos < len(message_bits):
                    byte_val |= (message_bits[bit_pos] << bit_idx)
            aes_key_bytes.append(byte_val)
        logger.info(f"AES密钥解密完成: {len(aes_key_bytes)} bytes")
        return bytes(aes_key_bytes)