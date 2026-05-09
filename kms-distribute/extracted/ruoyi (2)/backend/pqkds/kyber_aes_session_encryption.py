import numpy as np
import hashlib
import logging
from typing import Dict, Any
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
import json
import base64
logger = logging.getLogger(__name__)
class CertificatelessKyberEncryption:
    def __init__(self, kyber_kem):
        self.kyber = kyber_kem
        logger.info("CertificatelessKyberEncryption初始化完成")
    def encrypt_session_key(self, recipient_id: str, session_key: bytes,
                           recipient_pk_bytes: bytes) -> Dict[str, Any]:
        logger.info(f"[Kyber Enc] 开始加密会话密钥，接收者: {recipient_id}")
        try:
            ciphertext, shared_secret = self.kyber.encaps(recipient_pk_bytes)
            logger.info(f"[Kyber Enc] KEM密钥封装完成，密文长度: {len(ciphertext)}, 共享秘密长度: {len(shared_secret)}")
            aes_key = shared_secret[:32]
            cipher = AES.new(aes_key, AES.MODE_GCM)
            encrypted_key, tag = cipher.encrypt_and_digest(session_key)
            logger.info(f"[Kyber Enc] AES-GCM加密完成，密文长度: {len(encrypted_key)}")
            result = {
                'kyber_ciphertext': ciphertext.hex(),
                'encrypted_key': encrypted_key.hex(),
                'nonce': cipher.nonce.hex(),
                'tag': tag.hex()
            }
            return {
                'success': True,
                'ciphertext': json.dumps(result),
                'algorithm': 'CertificatelessKyber'
            }
        except Exception as e:
            logger.error(f"[Kyber Enc] 加密失败: {e}")
            return {
                'success': False,
                'message': f"加密失败: {str(e)}"
            }
    def decrypt_session_key(self, ciphertext_json: str, 
                           recipient_sk_bytes: bytes) -> Dict[str, Any]:
        logger.info(f"[Kyber Dec] 开始解密会话密钥")
        try:
            ct = json.loads(ciphertext_json)
            kyber_ciphertext = bytes.fromhex(ct['kyber_ciphertext'])
            encrypted_key = bytes.fromhex(ct['encrypted_key'])
            nonce = bytes.fromhex(ct['nonce'])
            tag = bytes.fromhex(ct['tag'])
            logger.info(f"[Kyber Dec] 提取密文完成")
            shared_secret = self.kyber.decaps(kyber_ciphertext, recipient_sk_bytes)
            logger.info(f"[Kyber Dec] KEM密钥解封装完成，共享秘密长度: {len(shared_secret)}")
            aes_key = shared_secret[:32]
            cipher = AES.new(aes_key, AES.MODE_GCM, nonce=nonce)
            session_key = cipher.decrypt_and_verify(encrypted_key, tag)
            logger.info(f"[Kyber Dec] AES-GCM解密完成，会话密钥长度: {len(session_key)}")
            return {
                'success': True,
                'session_key': session_key,
                'key_length': len(session_key),
                'algorithm': 'CertificatelessKyber'
            }
        except Exception as e:
            logger.error(f"[Kyber Dec] 解密失败: {e}")
            return {
                'success': False,
                'message': f"解密失败: {str(e)}"
            }