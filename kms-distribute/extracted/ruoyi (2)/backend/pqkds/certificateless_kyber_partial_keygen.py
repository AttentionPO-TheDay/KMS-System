import numpy as np
import base64
import logging
import json
import hashlib
from typing import Dict, Any, Tuple
logger = logging.getLogger(__name__)
class CertificatelessKyberPartialKeyGeneration:
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
    def generate_kyber_partial_key(self, node_id: str) -> Dict[str, Any]:
        logger.info(f"KGC为节点{node_id}生成Kyber部分私钥（直接明文传递）")
        try:
            self._initialize_system()
            if self.ck_system.A is None:
                logger.info("系统参数未初始化，执行Setup")
                setup_result = self.ck_system.setup()
                if not setup_result['success']:
                    return {'success': False, 'message': 'Setup失败'}
            logger.info(f"执行PartialKeyGen为节点{node_id}生成部分私钥")
            t, c = self.ck_system.partial_key_gen(node_id)
            partial_key_data = {
                't': t.tolist(),
                'c': c.tolist(),
                'node_id': node_id,
                'algorithm': 'CertificatelessKyber',
                'parameters': {
                    'n': self.n,
                    'm': self.m,
                    'q': self.q,
                    'sigma': self.sigma
                }
            }
            partial_key_b64 = base64.b64encode(
                json.dumps(partial_key_data).encode('utf-8')
            ).decode('utf-8')
            logger.info(f"Kyber部分私钥生成完成，直接明文传递")
            return {
                'success': True,
                'partial_key': partial_key_b64,
                'algorithm': 'CertificatelessKyber',
                'message': 'Kyber部分私钥生成成功'
            }
        except Exception as e:
            logger.error(f"Kyber部分私钥生成失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': f'Kyber部分私钥生成失败: {str(e)}'
            }