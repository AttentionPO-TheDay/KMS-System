import numpy as np
import base64
import zlib
import hashlib
import logging
import threading
from typing import Dict, Any, Tuple
import json

logger = logging.getLogger(__name__)

# Falcon-512 和 Falcon-1024 的格密码参数
FALCON_PARAMS = {
    512: {'n': 512, 'm': 1024, 'q': 12289},
    1024: {'n': 1024, 'm': 2048, 'q': 12289},
}


def decompress_key_data(key_data: str) -> str:
    try:
        if not key_data.startswith("COMPRESSED:"):
            return key_data
        compressed_b64 = key_data[11:]
        compressed = base64.b64decode(compressed_b64)
        decompressed = zlib.decompress(compressed)
        return decompressed.decode('utf-8')
    except Exception as e:
        logger.warning(f"密钥解压缩失败: {e}，使用原始数据")
        return key_data


def _parse_key_json(key_b64: str) -> dict:
    """从 base64 或直接 JSON 字符串中解析密钥数据"""
    key_b64 = decompress_key_data(key_b64)
    # 尝试 base64 解码后 JSON 解析
    try:
        decoded_str = base64.b64decode(key_b64).decode('utf-8')
        return json.loads(decoded_str)
    except Exception:
        pass
    # 尝试直接 JSON 解析
    try:
        return json.loads(key_b64)
    except Exception:
        pass
    raise ValueError("无法解析密钥数据: 既不是 base64(JSON) 也不是直接 JSON")


# ================================================================
#  Falcon 密钥 numpy 缓存 —— 避免重复解析 7MB+ 的 JSON 公钥/私钥
# ================================================================
class _FalconKeyCache:
    """
    按 key_b64 的 SHA-256 哈希缓存解析后的 numpy 数组。
    公钥缓存: {hash -> {A, B, H_id, U_id, n, m, q, security_level}}
    私钥缓存: {hash -> {D_id, S_id, n, m, q}}
    """
    _pk_cache: Dict[str, dict] = {}
    _sk_cache: Dict[str, dict] = {}
    _lock = threading.Lock()

    @classmethod
    def get_public_key(cls, key_b64: str) -> dict:
        h = hashlib.sha256(key_b64[:64].encode()).hexdigest()
        with cls._lock:
            if h in cls._pk_cache:
                return cls._pk_cache[h]
        # 解析
        data = _parse_key_json(key_b64)
        result = {
            'U_id': np.array(data['U_id'], dtype=np.int64),
            'A': np.array(data['A'], dtype=np.int64),
            'B': np.array(data['B'], dtype=np.int64),
            'H_id': np.array(data['H_id'], dtype=np.int64),
            'n': data.get('parameters', {}).get('n', 512),
            'm': data.get('parameters', {}).get('m', 1024),
            'q': data.get('parameters', {}).get('q', 12289),
            'security_level': data.get('security_level', 512),
        }
        with cls._lock:
            cls._pk_cache[h] = result
        return result

    @classmethod
    def get_private_key(cls, key_b64: str) -> dict:
        h = hashlib.sha256(key_b64[:64].encode()).hexdigest()
        with cls._lock:
            if h in cls._sk_cache:
                return cls._sk_cache[h]
        data = _parse_key_json(key_b64)
        params = data.get('parameters', {})
        result = {
            'D_id': np.array(data['D_id'], dtype=np.int64),
            'S_id': np.array(data['S_id'], dtype=np.int64),
            'n': params.get('n', 512),
            'm': params.get('m', 1024),
            'q': params.get('q', 12289),
            'security_level': data.get('security_level', 512),
        }
        with cls._lock:
            cls._sk_cache[h] = result
        return result

    @classmethod
    def clear(cls):
        with cls._lock:
            cls._pk_cache.clear()
            cls._sk_cache.clear()


# ================================================================
#  密文快速序列化/反序列化 —— 用 numpy 二进制替代 JSON
# ================================================================
import struct

_CT_MAGIC = b'FCTV2'  # 标识二进制密文格式

def _serialize_ciphertext_fast(ct: dict, n: int, m: int, q: int, key_length: int) -> str:
    """将密文 {c1, c2, c3} 序列化为紧凑的 base64 字符串"""
    c1 = ct['c1'] if isinstance(ct['c1'], np.ndarray) else np.array(ct['c1'], dtype=np.int64)
    c2 = ct['c2'] if isinstance(ct['c2'], np.ndarray) else np.array(ct['c2'], dtype=np.int64)
    c3 = ct['c3'] if isinstance(ct['c3'], np.ndarray) else np.array(ct['c3'], dtype=np.int64)
    # 头部: magic(5) + n(4) + m(4) + q(4) + key_length(4) = 21 bytes
    header = _CT_MAGIC + struct.pack('<IIII', n, m, q, key_length)
    payload = header + c1.astype(np.int64).tobytes() + c2.astype(np.int64).tobytes() + c3.astype(np.int64).tobytes()
    return base64.b64encode(payload).decode('ascii')


def _deserialize_ciphertext_fast(ciphertext_b64: str, fallback_q: int = 12289):
    """反序列化密文，自动检测二进制/JSON格式，返回 (c1, c2, c3, q, key_length)"""
    raw = base64.b64decode(ciphertext_b64)

    # 检测二进制格式
    if raw[:5] == _CT_MAGIC:
        n, m, q, key_length = struct.unpack('<IIII', raw[5:21])
        offset = 21
        elem_size = m * 8  # int64 = 8 bytes
        c1 = np.frombuffer(raw[offset:offset+elem_size], dtype=np.int64).copy()
        offset += elem_size
        c2 = np.frombuffer(raw[offset:offset+elem_size], dtype=np.int64).copy()
        offset += elem_size
        c3 = np.frombuffer(raw[offset:offset+elem_size], dtype=np.int64).copy()
        return c1, c2, c3, q, key_length

    # 兼容旧 JSON 格式
    ct_data = json.loads(raw.decode('utf-8'))
    if isinstance(ct_data, str):
        ct_data = json.loads(ct_data)
    c1 = np.array(ct_data['c1'], dtype=np.int64)
    c2 = np.array(ct_data['c2'], dtype=np.int64)
    c3 = np.array(ct_data['c3'], dtype=np.int64)
    ct_q = ct_data.get('q', ct_data.get('params', {}).get('q', fallback_q))
    key_length = ct_data.get('key_length', ct_data.get('session_key_length', 32))
    return c1, c2, c3, ct_q, key_length


class FalconAESSessionKeyEncryption:
    """
    基于无证书 Falcon 格密码方案的 AES 会话密钥加解密服务。
    支持 Falcon-512 (n=512, m=1024) 和 Falcon-1024 (n=1024, m=2048)。
    """

    def __init__(self, security_level: int = 512, n: int = None, m: int = None, q: int = 12289):
        if n is not None and m is not None:
            # 兼容旧的直接传参方式，根据 n 推断安全级别
            self.n = n
            self.m = m
            self.q = q
            self.security_level = n
        else:
            if security_level not in FALCON_PARAMS:
                raise ValueError(f"不支持的安全级别: {security_level}，仅支持 512 和 1024")
            params = FALCON_PARAMS[security_level]
            self.n = params['n']
            self.m = params['m']
            self.q = params['q']
            self.security_level = security_level
        self.cf_strict = None
        self.enc_strict = None
        logger.info(
            f"FalconAESSessionKeyEncryption初始化: "
            f"安全级别=Falcon-{self.security_level}, n={self.n}, m={self.m}, q={self.q}"
        )
    def _initialize_cf(self, n: int = None, m: int = None, q: int = None):
        """初始化无证书 Falcon 方案实例，支持按需切换参数"""
        target_n = n or self.n
        target_m = m or self.m
        target_q = q or self.q
        # 如果参数变了或还没初始化，重新创建
        if (self.cf_strict is None or
                self.cf_strict.n != target_n or
                self.cf_strict.m != target_m):
            from .falcon_certificateless_strict import CertificatelessFalconStrict
            from .falcon_encryption_strict import CertificatelessFalconEncryption
            self.cf_strict = CertificatelessFalconStrict(target_n, target_m, target_q)
            self.enc_strict = CertificatelessFalconEncryption(self.cf_strict)
            self.n = target_n
            self.m = target_m
            self.q = target_q
            logger.info(f"初始化 CertificatelessFalcon: n={target_n}, m={target_m}, q={target_q}")
    def generate_node_falcon_keypair(self, node_id: str) -> Dict[str, Any]:
        logger.info(f"[生成节点Falcon密钥对] 节点ID: {node_id}, 安全级别: Falcon-{self.security_level}")
        try:
            self._initialize_cf()
            logger.info(f"[Step 1] Setup阶段：生成系统参数 (n={self.n}, m={self.m}, q={self.q})")
            setup_result = self.cf_strict.setup()
            if not setup_result['success']:
                return {'success': False, 'message': 'Setup失败'}
            logger.info(f"[Step 2] PartialKeyGen阶段：为节点生成部分私钥")
            D_id, H_id = self.cf_strict.partial_key_gen(node_id)
            logger.info(f"[Step 2] D_id生成完成，形状: {D_id.shape}")
            logger.info(f"[Step 3] SetSecretValue阶段：用户生成秘密值")
            S_id = self.cf_strict.set_secret_value()
            logger.info(f"[Step 3] S_id生成完成，形状: {S_id.shape}")
            logger.info(f"[Step 4] SetSK阶段：生成秘密密钥")
            sk = self.cf_strict.set_sk(D_id, S_id)
            logger.info(f"[Step 4] 秘密密钥生成完成")
            logger.info(f"[Step 5] SetPK阶段：生成公开密钥")
            U_id = self.cf_strict.set_pk(S_id)
            logger.info(f"[Step 5] 公开密钥U_id生成完成，形状: {U_id.shape}")
            falcon_public_key_data = {
                'U_id': U_id.tolist(),
                'H_id': H_id.tolist(),
                'A': self.cf_strict.system_params['A'].tolist(),
                'B': self.cf_strict.system_params['B'].tolist(),
                'algorithm': f'CertificatelessFalcon-{self.security_level}',
                'security_level': self.security_level,
                'node_id': node_id,
                'parameters': {
                    'n': self.n,
                    'm': self.m,
                    'q': self.q
                }
            }
            falcon_private_key_data = {
                'D_id': sk['D_id'].tolist(),
                'S_id': sk['S_id'].tolist(),
                'algorithm': f'CertificatelessFalcon-{self.security_level}',
                'security_level': self.security_level,
                'node_id': node_id,
                'parameters': {
                    'n': self.n,
                    'm': self.m,
                    'q': self.q
                }
            }
            falcon_public_key_b64 = base64.b64encode(
                json.dumps(falcon_public_key_data).encode('utf-8')
            ).decode('utf-8')
            falcon_private_key_b64 = base64.b64encode(
                json.dumps(falcon_private_key_data).encode('utf-8')
            ).decode('utf-8')
            logger.info(
                f"[生成节点Falcon密钥对] 完成 Falcon-{self.security_level}, "
                f"公钥大小: {len(falcon_public_key_b64)}字符, 私钥大小: {len(falcon_private_key_b64)}字符"
            )
            return {
                'success': True,
                'falcon_public_key': falcon_public_key_b64,
                'falcon_private_key': falcon_private_key_b64,
                'algorithm': f'CertificatelessFalcon-{self.security_level}',
                'security_level': self.security_level,
                'message': f'无证书Falcon-{self.security_level}密钥对生成成功'
            }
        except Exception as e:
            logger.error(f"[生成节点Falcon密钥对] 失败: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'message': f'密钥生成失败: {str(e)}'}
    def encrypt_aes_key_with_falcon(self, recipient_id: str, aes_key: bytes,
                                    recipient_public_key_b64: str) -> Dict[str, Any]:
        """
        使用无证书 Falcon 格密码方案加密 AES 会话密钥。
        使用快速引擎 + numpy 缓存 + 二进制密文序列化。
        """
        logger.info(f"[加密AES密钥] 接收者: {recipient_id}, AES密钥长度: {len(aes_key)} bytes")
        try:
            if not recipient_public_key_b64:
                raise ValueError("接收方公钥为空")

            # 从缓存获取已解析的 numpy 公钥数据
            pk = _FalconKeyCache.get_public_key(recipient_public_key_b64)
            A, B, H_id, U_id = pk['A'], pk['B'], pk['H_id'], pk['U_id']
            pk_n, pk_m, pk_q = pk['n'], pk['m'], pk['q']
            pk_security = pk['security_level']

            logger.info(f"[加密AES密钥] Falcon-{pk_security}, n={pk_n}, m={pk_m}")

            # 使用快速引擎加密
            from .falcon_fast_engine import fast_encrypt
            ct = fast_encrypt(A, B, H_id, U_id, aes_key, pk_n, pk_m, pk_q, 1.17)

            # 二进制序列化密文: 比 JSON 快 10x+
            ciphertext_b64 = _serialize_ciphertext_fast(ct, pk_n, pk_m, pk_q, len(aes_key))

            logger.info(f"[加密AES密钥] 完成 Falcon-{pk_security}，密文大小: {len(ciphertext_b64)}字符")
            return {
                'success': True,
                'ciphertext': ciphertext_b64,
                'algorithm': f'CertificatelessFalcon-{pk_security}',
                'security_level': pk_security,
                'message': f'AES密钥使用Falcon-{pk_security}格密码加密成功'
            }
        except Exception as e:
            logger.error(f"[加密AES密钥] 失败: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'message': f'AES密钥加密失败: {str(e)}'}
    def decrypt_aes_key_with_falcon(self, ciphertext_b64: str,
                                    private_key_b64: str) -> Dict[str, Any]:
        """
        使用无证书 Falcon 格密码方案解密 AES 会话密钥。
        使用快速引擎 + numpy 缓存 + 二进制密文反序列化。
        """
        logger.info("[解密AES密钥] 开始解密")
        try:
            # 从缓存获取已解析的 numpy 私钥数据
            sk_cached = _FalconKeyCache.get_private_key(private_key_b64)
            sk = {'D_id': sk_cached['D_id'], 'S_id': sk_cached['S_id']}
            sk_q = sk_cached['q']
            sk_security = sk_cached['security_level']

            logger.info(f"[解密AES密钥] Falcon-{sk_security}, D_id={sk['D_id'].shape}")

            # 反序列化密文（自动检测二进制/JSON格式）
            c1, c2, c3, ct_q, key_length = _deserialize_ciphertext_fast(ciphertext_b64, sk_q)

            # 使用快速引擎解密
            from .falcon_fast_engine import fast_decrypt
            session_key = fast_decrypt(c1, c2, c3, sk['D_id'], sk['S_id'], ct_q, key_length)

            logger.info(f"[解密AES密钥] 完成 Falcon-{sk_security}, 密钥长度: {len(session_key)}")
            return {
                'success': True,
                'session_key': session_key,
                'key_length': len(session_key),
                'algorithm': f'CertificatelessFalcon-{sk_security}'
            }
        except Exception as e:
            logger.error(f"[解密AES密钥] 失败: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'message': f'AES密钥解密失败: {str(e)}'}