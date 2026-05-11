import logging
import json
import base64
from typing import Dict, Any
from Crypto.Random import get_random_bytes
logger = logging.getLogger(__name__)
class KyberAESSessionKeyService:
    def __init__(self, kyber_kem):
        self.kyber = kyber_kem
        from .kyber_aes_session_encryption import CertificatelessKyberEncryption
        self.enc_strict = CertificatelessKyberEncryption(kyber_kem)
        logger.info("KyberAESSessionKeyService初始化完成")
    def generate_node_kyber_keypair(self, node_id: str) -> Dict[str, Any]:
        logger.info(f"[生成节点Kyber密钥对] 节点ID: {node_id}")
        try:
            public_key, secret_key = self.kyber.keygen()
            logger.info(f"[生成节点Kyber密钥对] 密钥对生成完成")
            kyber_public_key_b64 = base64.b64encode(public_key).decode('utf-8')
            kyber_private_key_b64 = base64.b64encode(secret_key).decode('utf-8')
            logger.info(f"[生成节点Kyber密钥对] 完成，公钥大小: {len(kyber_public_key_b64)}字符, 私钥大小: {len(kyber_private_key_b64)}字符")
            return {
                'success': True,
                'kyber_public_key': kyber_public_key_b64,
                'kyber_private_key': kyber_private_key_b64,
                'algorithm': 'CertificatelessKyber',
                'message': '无证书Kyber密钥对生成成功'
            }
        except Exception as e:
            logger.error(f"[生成节点Kyber密钥对] 失败: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'message': f'密钥生成失败: {str(e)}'}
    def encrypt_aes_key_with_kyber(self, recipient_id: str, aes_key: bytes,
                                    recipient_public_key_b64: str) -> Dict[str, Any]:
        logger.info(f"[加密AES密钥] 接收者: {recipient_id}")
        try:
            recipient_pk_bytes = base64.b64decode(recipient_public_key_b64)
            enc_result = self.enc_strict.encrypt_session_key(
                recipient_id, aes_key, recipient_pk_bytes
            )
            if not enc_result['success']:
                return enc_result
            ciphertext_b64 = base64.b64encode(
                enc_result['ciphertext'].encode('utf-8')
            ).decode('utf-8')
            logger.info(f"[加密AES密钥] 完成，密文大小: {len(ciphertext_b64)}字符")
            return {
                'success': True,
                'ciphertext': ciphertext_b64,
                'algorithm': 'CertificatelessKyber',
                'message': 'AES密钥加密成功'
            }
        except Exception as e:
            logger.error(f"[加密AES密钥] 失败: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'message': f'加密失败: {str(e)}'}
    def decrypt_aes_key_with_kyber(self, ciphertext_b64: str,
                                    recipient_private_key_b64: str) -> Dict[str, Any]:
        logger.info(f"[解密AES密钥] 开始解密")
        try:
            ciphertext_json = base64.b64decode(ciphertext_b64).decode('utf-8')
            recipient_sk_bytes = base64.b64decode(recipient_private_key_b64)
            dec_result = self.enc_strict.decrypt_session_key(
                ciphertext_json, recipient_sk_bytes
            )
            if not dec_result['success']:
                return dec_result
            logger.info(f"[解密AES密钥] 完成")
            return {
                'success': True,
                'session_key': dec_result['session_key'],
                'key_length': dec_result['key_length'],
                'algorithm': 'CertificatelessKyber',
                'message': 'AES密钥解密成功'
            }
        except Exception as e:
            logger.error(f"[解密AES密钥] 失败: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'message': f'解密失败: {str(e)}'}