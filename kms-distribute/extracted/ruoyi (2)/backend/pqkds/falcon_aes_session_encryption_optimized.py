import numpy as np
import base64
import logging
import json
from typing import Dict, Any
from concurrent.futures import ThreadPoolExecutor
import time
logger = logging.getLogger(__name__)
class FalconAESSessionKeyEncryptionOptimized:
    def __init__(self, n: int = 512, m: int = 1024, q: int = 12289, num_workers: int = 4):
        self.n = n
        self.m = m
        self.q = q
        self.num_workers = num_workers
        self.cf_strict = None
        self.enc_strict = None
    def _initialize_cf(self):
        if self.cf_strict is None:
            from .falcon_certificateless_strict_optimized import CertificatelessFalconStrictOptimized
            from .falcon_encryption_strict import CertificatelessFalconEncryption
            self.cf_strict = CertificatelessFalconStrictOptimized(
                self.n, self.m, self.q, num_workers=self.num_workers
            )
            self.enc_strict = CertificatelessFalconEncryption(self.cf_strict)
    def generate_node_falcon_keypair(self, node_id: str) -> Dict[str, Any]:
        logger.info(f"[生成节点Falcon密钥对] 节点ID: {node_id}（优化版本）")
        start_time = time.time()
        try:
            self._initialize_cf()
            logger.info(f"[Step 1] Setup阶段：生成系统参数")
            setup_start = time.time()
            setup_result = self.cf_strict.setup()
            setup_time = time.time() - setup_start
            if not setup_result['success']:
                return {'success': False, 'message': 'Setup失败'}
            logger.info(f"[Step 1] Setup完成，耗时: {setup_time:.3f}秒")
            logger.info(f"[Step 2] PartialKeyGen阶段：为节点生成部分私钥")
            partial_start = time.time()
            D_id, H_id = self.cf_strict.partial_key_gen(node_id)
            partial_time = time.time() - partial_start
            logger.info(f"[Step 2] PartialKeyGen完成，耗时: {partial_time:.3f}秒，D_id形状: {D_id.shape}")
            logger.info(f"[Step 3] SetSecretValue阶段：用户生成秘密值（并行采样）")
            secret_start = time.time()
            S_id = self.cf_strict.set_secret_value()
            secret_time = time.time() - secret_start
            logger.info(f"[Step 3] SetSecretValue完成，耗时: {secret_time:.3f}秒，S_id形状: {S_id.shape}")
            logger.info(f"[Step 4] SetSK阶段：生成秘密密钥")
            sk_start = time.time()
            sk = self.cf_strict.set_sk(D_id, S_id)
            sk_time = time.time() - sk_start
            logger.info(f"[Step 4] SetSK完成，耗时: {sk_time:.3f}秒")
            logger.info(f"[Step 5] SetPK阶段：生成公开密钥")
            pk_start = time.time()
            U_id = self.cf_strict.set_pk(S_id)
            pk_time = time.time() - pk_start
            logger.info(f"[Step 5] SetPK完成，耗时: {pk_time:.3f}秒，U_id形状: {U_id.shape}")
            falcon_public_key_data = {
                'U_id': U_id.tolist(),
                'algorithm': 'CertificatelessFalconStrictOptimized',
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
                'algorithm': 'CertificatelessFalconStrictOptimized',
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
            total_time = time.time() - start_time
            logger.info(f"[生成节点Falcon密钥对] 完成，总耗时: {total_time:.3f}秒")
            logger.info(f"  - Setup: {setup_time:.3f}秒")
            logger.info(f"  - PartialKeyGen: {partial_time:.3f}秒")
            logger.info(f"  - SetSecretValue: {secret_time:.3f}秒")
            logger.info(f"  - SetSK: {sk_time:.3f}秒")
            logger.info(f"  - SetPK: {pk_time:.3f}秒")
            return {
                'success': True,
                'falcon_public_key': falcon_public_key_b64,
                'falcon_private_key': falcon_private_key_b64,
                'algorithm': 'CertificatelessFalconStrictOptimized',
                'message': '优化的无证书Falcon密钥对生成成功',
                'timing': {
                    'setup': setup_time,
                    'partial_key_gen': partial_time,
                    'set_secret_value': secret_time,
                    'set_sk': sk_time,
                    'set_pk': pk_time,
                    'total': total_time
                }
            }
        except Exception as e:
            logger.error(f"[生成节点Falcon密钥对] 失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': f'优化的无证书Falcon密钥对生成失败: {str(e)}'
            }
    def shutdown(self):
        if self.cf_strict is not None:
            self.cf_strict.shutdown()