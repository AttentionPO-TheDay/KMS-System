import numpy as np
import base64
import json
import logging
import time
from typing import Dict, Any
from .falcon_certificateless_strict_optimized import CertificatelessFalconStrictOptimized
from .key_compression_utils import KeyCompressionUtils
logger = logging.getLogger(__name__)
class CertificatelessFalconManagerV2:
    def __init__(self, security_level: int = 512, num_workers: int = 8):
        self.security_level = int(security_level) if security_level else 512
        self.num_workers = num_workers
        if self.security_level == 512:
            self.n = 512
            self.m = 1024
            self.q = 12289
        elif self.security_level == 1024:
            self.n = 1024
            self.m = 2048
            self.q = 12289
        else:
            raise ValueError(f"不支持的安全级别: {security_level}")
        self.falcon_system = CertificatelessFalconStrictOptimized(
            n=self.n, m=self.m, q=self.q, num_workers=num_workers
        )
        logger.info(f"[CertificatelessFalconManagerV2] 初始化完成: 安全级别={security_level}, n={self.n}, m={self.m}")
    def initialize_system(self) -> Dict[str, Any]:
        try:
            logger.info(f"[Initialize] 开始初始化Falcon系统")
            start_time = time.time()
            setup_result = self.falcon_system.setup()
            if not setup_result['success']:
                return {
                    'success': False,
                    'message': f'Setup失败: {setup_result.get("message", "未知错误")}'
                }
            elapsed = time.time() - start_time
            logger.info(f"[Initialize] 系统初始化完成，耗时{elapsed:.3f}秒")
            return {
                'success': True,
                'message': 'Falcon系统初始化成功',
                'setup_time': elapsed
            }
        except Exception as e:
            logger.error(f"[Initialize] 系统初始化失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': f'系统初始化异常: {str(e)}'
            }
    def _compress_key_data(self, key_data: Dict) -> str:
        return KeyCompressionUtils.compress_key_data(key_data)
    def generate_keypair(self, node_id: str) -> Dict[str, Any]:
        try:
            logger.info(f"[GenerateKeypair] 为节点{node_id}生成Falcon密钥对")
            start_time = time.time()
            if self.falcon_system.system_params is None:
                logger.error("[GenerateKeypair] 系统参数未初始化")
                return {
                    'success': False,
                    'message': '系统参数未初始化'
                }
            logger.info("[GenerateKeypair] Step 1: 生成部分私钥D_id")
            partial_time_start = time.time()
            D_id_result = self.falcon_system.partial_key_gen(node_id)
            if not D_id_result['success']:
                logger.error(f"[GenerateKeypair] 部分私钥生成失败")
                return D_id_result
            D_id = D_id_result['D_id']
            H_id = D_id_result['H_id']
            partial_time = time.time() - partial_time_start
            logger.info(f"[GenerateKeypair] D_id生成完成，耗时{partial_time:.3f}秒")
            logger.info("[GenerateKeypair] Step 2: 生成秘密值S_id")
            secret_time_start = time.time()
            S_id = self.falcon_system.set_secret_value()
            secret_time = time.time() - secret_time_start
            logger.info(f"[GenerateKeypair] S_id生成完成，耗时{secret_time:.3f}秒")
            logger.info("[GenerateKeypair] Step 3: 生成秘密密钥")
            sk_time_start = time.time()
            sk = self.falcon_system.set_sk(D_id, S_id)
            sk_time = time.time() - sk_time_start
            logger.info(f"[GenerateKeypair] 秘密密钥生成完成，耗时{sk_time:.3f}秒")
            logger.info("[GenerateKeypair] Step 4: 生成公开密钥")
            pk_time_start = time.time()
            U_id = self.falcon_system.set_pk(S_id)
            pk_time = time.time() - pk_time_start
            logger.info(f"[GenerateKeypair] 公开密钥生成完成，耗时{pk_time:.3f}秒")
            logger.info("[GenerateKeypair] 编码密钥对")
            encode_time_start = time.time()
            public_key_data = {
                'U_id': U_id.tolist() if isinstance(U_id, np.ndarray) else U_id,
                'algorithm': 'CertificatelessFalconStrictOptimized',
                'node_id': node_id,
                'security_level': self.security_level,
                'parameters': {
                    'n': self.n,
                    'm': self.m,
                    'q': self.q
                }
            }
            private_key_data = {
                'D_id': D_id.tolist() if isinstance(D_id, np.ndarray) else D_id,
                'S_id': S_id.tolist() if isinstance(S_id, np.ndarray) else S_id,
                'algorithm': 'CertificatelessFalconStrictOptimized',
                'node_id': node_id,
                'security_level': self.security_level,
                'parameters': {
                    'n': self.n,
                    'm': self.m,
                    'q': self.q
                }
            }
            try:
                public_key_b64 = self._compress_key_data(public_key_data)
                private_key_b64 = self._compress_key_data(private_key_data)
                logger.info(f"[GenerateKeypair] 密钥压缩完成")
            except Exception as e:
                logger.warning(f"[GenerateKeypair] 密钥压缩失败，使用原始格式: {e}")
                public_key_b64 = base64.b64encode(
                    json.dumps(public_key_data).encode('utf-8')
                ).decode('utf-8')
                private_key_b64 = base64.b64encode(
                    json.dumps(private_key_data).encode('utf-8')
                ).decode('utf-8')
            encode_time = time.time() - encode_time_start
            total_time = time.time() - start_time
            logger.info(f"[GenerateKeypair] 密钥对生成完成，总耗时{total_time:.3f}秒")
            return {
                'success': True,
                'message': 'Falcon密钥对生成成功',
                'falcon_public_key': public_key_b64,
                'falcon_private_key': private_key_b64,
                'algorithm': 'CertificatelessFalconStrictOptimized',
                'timing': {
                    'partial_key_gen': partial_time,
                    'secret_value': secret_time,
                    'sk_generation': sk_time,
                    'pk_generation': pk_time,
                    'encoding': encode_time,
                    'total': total_time
                }
            }
        except Exception as e:
            logger.error(f"[GenerateKeypair] 密钥对生成异常: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': f'密钥对生成异常: {str(e)}'
            }