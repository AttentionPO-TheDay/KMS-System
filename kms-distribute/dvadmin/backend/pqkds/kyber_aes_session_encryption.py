"""无证书 Kyber 会话密钥封装（KEM + DEM）。

载荷层已按决策 D3 换成**国密 SM4**：会话密钥由调用方生成（现为 16 字节），
本模块只负责用 Kyber 共享秘密派生出的 KEK 把它封起来。

历史兼容：信封里的 `payload_algorithm` 标记决定用 SM4 还是旧的 AES-256-GCM。
缺该标记 = 2026-09 之前写入的数据 = AES-256（KEK 取共享秘密前 32 字节）。

⚠️ 模块名保留历史的 `kyber_aes_session_encryption`（改名会牵动多处 import），
但**实现里已经没有任何 AES 加密路径用于新数据**，AES 只作为读取历史数据的分支存在。
"""
import hashlib
import json
import logging
from typing import Any, Dict

from .sm4_crypto import (
    GCM_IV_BYTES,
    PAYLOAD_ALGORITHM_SM4,
    InvalidTag,
    PayloadCipher,
    SM4Crypto,
)

logger = logging.getLogger(__name__)


class CertificatelessKyberEncryption:
    def __init__(self, kyber_kem):
        self.kyber = kyber_kem
        logger.info("CertificatelessKyberEncryption初始化完成")

    def encrypt_session_key(self, recipient_id: str, session_key: bytes,
                            recipient_pk_bytes: bytes) -> Dict[str, Any]:
        logger.info(f"[Kyber Enc] 开始封装会话密钥，接收者: {recipient_id}")
        try:
            ciphertext, shared_secret = self.kyber.encaps(recipient_pk_bytes)
            logger.info(
                f"[Kyber Enc] KEM密钥封装完成，密文长度: {len(ciphertext)}, "
                f"共享秘密长度: {len(shared_secret)}"
            )
            # KEK 取共享秘密前 16 字节 —— SM4 只接受 16 字节密钥
            kek = PayloadCipher.kek_from_shared_secret(PAYLOAD_ALGORITHM_SM4, shared_secret)
            encrypted_key, nonce_tag = SM4Crypto.encrypt(session_key, kek)
            logger.info(f"[Kyber Enc] SM4-GCM加密完成，密文长度: {len(encrypted_key)}")
            result = {
                'kyber_ciphertext': ciphertext.hex(),
                'encrypted_key': encrypted_key.hex(),
                'nonce': nonce_tag[:GCM_IV_BYTES].hex(),
                'tag': nonce_tag[GCM_IV_BYTES:].hex(),
                # 显式标记：读取端据此选择 SM4 还是历史 AES-256
                'payload_algorithm': PAYLOAD_ALGORITHM_SM4,
            }
            return {
                'success': True,
                'ciphertext': json.dumps(result),
                'algorithm': 'CertificatelessKyber',
            }
        except Exception as e:
            logger.error(f"[Kyber Enc] 加密失败: {e}")
            return {
                'success': False,
                'message': f"加密失败: {str(e)}",
            }

    def decrypt_session_key(self, ciphertext_json: str,
                            recipient_sk_bytes: bytes) -> Dict[str, Any]:
        logger.info("[Kyber Dec] 开始解封会话密钥")
        try:
            ct = json.loads(ciphertext_json)
            kyber_ciphertext = bytes.fromhex(ct['kyber_ciphertext'])
            encrypted_key = bytes.fromhex(ct['encrypted_key'])
            nonce = bytes.fromhex(ct['nonce'])
            tag = bytes.fromhex(ct['tag'])
            logger.info("[Kyber Dec] 提取密文完成")

            shared_secret = self.kyber.decaps(kyber_ciphertext, recipient_sk_bytes)
            logger.info(f"[Kyber Dec] KEM密钥解封装完成，共享秘密长度: {len(shared_secret)}")

            # 缺 `payload_algorithm` 的历史数据走 AES-256（KEK 32 字节）
            payload_alg = PayloadCipher.algorithm_from_envelope(ct)
            kek = PayloadCipher.kek_from_shared_secret(payload_alg, shared_secret)
            session_key = PayloadCipher.decrypt_with(payload_alg, encrypted_key, kek, nonce + tag)
            logger.info(
                f"[Kyber Dec] {payload_alg} 解密完成，会话密钥长度: {len(session_key)}"
            )
            return {
                'success': True,
                'session_key': session_key,
                'key_length': len(session_key),
                'algorithm': 'CertificatelessKyber',
            }
        except InvalidTag:
            # 认证失败单独识别：它意味着密文/标签被篡改，或密钥不对，
            # 与"格式解析失败"是两码事，排查时不该混在一起。
            logger.error("[Kyber Dec] 认证失败：密文或标签被篡改，或共享秘密不匹配")
            return {
                'success': False,
                'message': "解密失败: 认证标签校验不通过（数据可能被篡改）",
            }
        except Exception as e:
            logger.error(f"[Kyber Dec] 解密失败: {e}")
            return {
                'success': False,
                'message': f"解密失败: {str(e)}",
            }