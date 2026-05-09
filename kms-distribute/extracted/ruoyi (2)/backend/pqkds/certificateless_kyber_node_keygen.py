import numpy as np
import base64
import logging
import json
from typing import Dict, Any
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
logger = logging.getLogger(__name__)
class CertificatelessKyberNodeKeyGeneration:
    def __init__(self, n: int = 512, m: int = 1024, q: int = 12289, sigma: float = 1.17):
        self.n = n
        self.m = m
        self.q = q
        self.sigma = sigma
        self.ck_system = None
    def _initialize_system(self):
        if self.ck_system is None:
            from .certificateless_kyber_system import CertificatelessKyberSystem
            self.ck_system = CertificatelessKyberSystem(self.n, self.m, self.q, self.sigma)
    def generate_node_kyber_keypair(self, node_id: str) -> Dict[str, Any]:
        logger.info(f"[生成节点Kyber密钥对] 节点ID: {node_id}")
        try:
            self._initialize_system()
            logger.info(f"[Step 1] Setup阶段：生成系统参数")
            setup_result = self.ck_system.setup()
            if not setup_result['success']:
                return {'success': False, 'message': 'Setup失败'}
            logger.info(f"[Step 2] PartialKeyGen阶段：为节点生成部分私钥")
            t, c = self.ck_system.partial_key_gen(node_id)
            logger.info(f"[Step 2] t生成完成，形状: {t.shape}")
            logger.info(f"[Step 3] SetSecretValue阶段：用户生成秘密值")
            s_id = self.ck_system.set_secret_value()
            logger.info(f"[Step 3] s_id生成完成，形状: {s_id.shape}")
            logger.info(f"[Step 4] SetSK阶段：生成秘密密钥")
            sk = self.ck_system.set_sk(t, s_id)
            logger.info(f"[Step 4] 秘密密钥生成完成，形状: {sk.shape}")
            logger.info(f"[Step 5] SetPK阶段：生成公开密钥")
            pk = self.ck_system.set_pk(s_id, c)
            logger.info(f"[Step 5] 公开密钥生成完成，形状: {pk.shape}")
            kyber_public_key_data = {
                'pk': pk.tolist(),
                'algorithm': 'CertificatelessKyber',
                'node_id': node_id,
                'parameters': {
                    'n': self.n,
                    'm': self.m,
                    'q': self.q,
                    'sigma': self.sigma
                }
            }
            kyber_private_key_data = {
                'sk': sk.tolist(),
                'algorithm': 'CertificatelessKyber',
                'node_id': node_id,
                'parameters': {
                    'n': self.n,
                    'm': self.m,
                    'q': self.q,
                    'sigma': self.sigma
                }
            }
            system_params_data = {
                'A': self.ck_system.A.tolist(),
                'S_0': self.ck_system.S_0.tolist(),
                'pk_kgc': self.ck_system.pk_kgc.tolist(),
                'parameters': {
                    'n': self.n,
                    'm': self.m,
                    'q': self.q,
                    'sigma': self.sigma
                }
            }
            kyber_public_key_b64 = base64.b64encode(
                json.dumps(kyber_public_key_data).encode('utf-8')
            ).decode('utf-8')
            kyber_private_key_b64 = base64.b64encode(
                json.dumps(kyber_private_key_data).encode('utf-8')
            ).decode('utf-8')
            system_params_b64 = base64.b64encode(
                json.dumps(system_params_data).encode('utf-8')
            ).decode('utf-8')
            logger.info(f"[生成节点Kyber密钥对] 完成")
            return {
                'success': True,
                'kyber_public_key': kyber_public_key_b64,
                'kyber_private_key': kyber_private_key_b64,
                'system_params': system_params_b64,
                'algorithm': 'CertificatelessKyber',
                'message': '无证书Kyber密钥对生成成功'
            }
        except Exception as e:
            logger.error(f"[生成节点Kyber密钥对] 失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': f'无证书Kyber密钥对生成失败: {str(e)}'
            }