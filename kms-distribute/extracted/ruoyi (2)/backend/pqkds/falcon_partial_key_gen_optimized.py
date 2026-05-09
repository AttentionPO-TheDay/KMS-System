import numpy as np
import base64
import logging
import json
import hashlib
import zlib
from typing import Dict, Any
from django.utils import timezone
import time
logger = logging.getLogger(__name__)
class CertificatelessFalconPartialKeyGenOptimized:
    def __init__(self, n: int = 512, m: int = 1024, q: int = 12289, num_workers: int = 4):
        self.n = n
        self.m = m
        self.q = q
        self.num_workers = num_workers
        self.cf_strict = None
    def _initialize_cf(self):
        if self.cf_strict is None:
            from .falcon_certificateless_strict_optimized import CertificatelessFalconStrictOptimized
            self.cf_strict = CertificatelessFalconStrictOptimized(
                self.n, self.m, self.q, num_workers=self.num_workers
            )
    def generate_falcon_partial_key_optimized(self, node_id: str) -> Dict[str, Any]:
        logger.info(f"KGC为节点{node_id}生成无证书Falcon部分私钥（优化版本，直接明文传递）")
        start_time = time.time()
        try:
            self._initialize_cf()
            if self.cf_strict.system_params is None:
                logger.info("系统参数未初始化，执行Setup")
                setup_result = self.cf_strict.setup()
                if not setup_result['success']:
                    return {'success': False, 'message': 'Setup失败'}
            logger.info(f"执行PartialKeyGen为节点{node_id}生成部分私钥")
            partial_start = time.time()
            partial_result = self.cf_strict.partial_key_gen(node_id)
            partial_time = time.time() - partial_start
            if not partial_result['success']:
                logger.error(f"PartialKeyGen失败: {partial_result.get('message', 'Unknown error')}")
                return {
                    'success': False,
                    'message': f'PartialKeyGen失败: {partial_result.get("message", "Unknown error")}'
                }
            D_id = partial_result['D_id']
            H_id = partial_result['H_id']
            logger.info(f"PartialKeyGen完成，耗时: {partial_time:.3f}秒")
            partial_key_data = {
                'D_id': D_id.tolist(),
                'H_id': H_id.tolist(),
                'A': self.cf_strict.system_params['A'].tolist(),
                'B': self.cf_strict.system_params['B'].tolist(),
                'node_id': node_id,
                'algorithm': 'CertificatelessFalconOptimized',
                'parameters': {
                    'n': self.n,
                    'm': self.m,
                    'q': self.q
                }
            }
            # 使用zlib压缩后再base64编码，避免MySQL max_allowed_packet限制
            raw_json = json.dumps(partial_key_data).encode('utf-8')
            compressed = zlib.compress(raw_json, 9)
            partial_key_b64 = base64.b64encode(compressed).decode('utf-8')
            total_time = time.time() - start_time
            logger.info(
                f"无证书Falcon部分私钥生成完成，总耗时: {total_time:.3f}秒, "
                f"原始大小: {len(raw_json)/1024:.0f}KB, 压缩后: {len(compressed)/1024:.0f}KB"
            )
            return {
                'success': True,
                'partial_key': partial_key_b64,
                'algorithm': 'CertificatelessFalconOptimized',
                'message': '无证书Falcon部分私钥生成成功',
                'timing': {
                    'partial_key_gen': partial_time,
                    'total': total_time
                }
            }
        except Exception as e:
            logger.error(f"无证书Falcon部分私钥生成失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': f'无证书Falcon部分私钥生成失败: {str(e)}'
            }
    def shutdown(self):
        if self.cf_strict is not None:
            self.cf_strict.shutdown()