import numpy as np
import base64
import json
import logging
import time
from typing import Dict, Any
from .ultra_fast_keygen_implementations import UltraFastCertificatelessKyber
from .key_compression_utils import KeyCompressionUtils
logger = logging.getLogger(__name__)
class CertificatelessKyberManagerV2:
    def __init__(self, security_level: int = 512, num_workers: int = 8):
        self.security_level = int(security_level) if security_level else 512
        self.num_workers = num_workers
        if self.security_level == 512:
            self.n = 512
            self.m = 1024
            self.q = 12289
        elif self.security_level == 768:
            self.n = 768
            self.m = 1536
            self.q = 12289
        elif self.security_level == 1024:
            self.n = 1024
            self.m = 2048
            self.q = 12289
        else:
            raise ValueError(f"不支持的安全级别: {security_level}")
        self.kyber_keygen = UltraFastCertificatelessKyber(
            n=self.n, m=self.m, q=self.q, num_workers=num_workers
        )
        logger.info(f"[CertificatelessKyberManagerV2] 初始化完成: 安全级别={security_level}, n={self.n}, m={self.m}")
    def initialize_system(self) -> Dict[str, Any]:
        try:
            logger.info(f"[Initialize] 开始初始化Kyber系统")
            start_time = time.time()
            elapsed = time.time() - start_time
            logger.info(f"[Initialize] 系统初始化完成，耗时{elapsed:.3f}秒")
            return {
                'success': True,
                'message': 'Kyber系统初始化成功',
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
            logger.info(f"[GenerateKeypair] 为节点{node_id}生成Kyber密钥对")
            start_time = time.time()
            keygen_result = self.kyber_keygen.generate_kyber_keypair_ultra_fast(node_id)
            if not keygen_result['success']:
                logger.error(f"[GenerateKeypair] 密钥对生成失败: {keygen_result.get('message')}")
                return keygen_result
            original_public_key = keygen_result.get('kyber_public_key')
            original_private_key = keygen_result.get('kyber_private_key')
            try:
                public_key_data = json.loads(base64.b64decode(original_public_key).decode('utf-8'))
                private_key_data = json.loads(base64.b64decode(original_private_key).decode('utf-8'))
                compressed_public_key = self._compress_key_data(public_key_data)
                compressed_private_key = self._compress_key_data(private_key_data)
                logger.info(f"[GenerateKeypair] 密钥压缩完成")
                logger.info(f"   公钥: {len(original_public_key)} -> {len(compressed_public_key)} bytes ({len(compressed_public_key)/len(original_public_key)*100:.1f}%)")
                logger.info(f"   私钥: {len(original_private_key)} -> {len(compressed_private_key)} bytes ({len(compressed_private_key)/len(original_private_key)*100:.1f}%)")
            except Exception as e:
                logger.warning(f"[GenerateKeypair] 密钥压缩失败，使用原始格式: {e}")
                compressed_public_key = original_public_key
                compressed_private_key = original_private_key
            total_time = time.time() - start_time
            logger.info(f"[GenerateKeypair] 密钥对生成完成，总耗时{total_time:.3f}秒")
            return {
                'success': True,
                'message': 'Kyber密钥对生成成功',
                'kyber_public_key': compressed_public_key,
                'kyber_private_key': compressed_private_key,
                'algorithm': 'UltraFastKyber',
                'timing': {
                    'total': total_time,
                    **keygen_result.get('timing', {})
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
    def kgc_generate_partial_key(self, node_id: str) -> Dict[str, Any]:
        try:
            logger.info(f"[KGC_PartialKeyGen] 为节点{node_id}生成部分私钥")
            start_time = time.time()
            partial_result = self.kyber_keygen.keygen.partial_key_gen_fast(node_id)
            elapsed = time.time() - start_time
            logger.info(f"[KGC_PartialKeyGen] 部分私钥生成完成，耗时{elapsed:.3f}秒")
            return {
                'success': True,
                'message': 'Kyber部分私钥生成成功',
                'partial_key': partial_result,
                'timing': elapsed
            }
        except Exception as e:
            logger.error(f"[KGC_PartialKeyGen] 部分私钥生成异常: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': f'部分私钥生成异常: {str(e)}'
            }