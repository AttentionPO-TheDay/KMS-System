import logging
import base64
import time
import zlib
import json
import numpy as np
from typing import Dict, Any
from django.db import transaction
from .models import Node
from .blockchain_service import BlockchainService
from .optimized_keygen_service import OptimizedKeygenService
logger = logging.getLogger(__name__)
def compress_key_data(key_data: str) -> str:
    try:
        data_bytes = key_data.encode('utf-8')
        compressed = zlib.compress(data_bytes, level=9)
        compressed_b64 = base64.b64encode(compressed).decode('utf-8')
        return f"COMPRESSED:{compressed_b64}"
    except Exception as e:
        logger.warning(f"密钥压缩失败: {e}，使用原始数据")
        return key_data
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
class CertificatelessKeyUpdateService:
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.blockchain_service = BlockchainService()
        try:
            self.node = Node.objects.get(node_id=node_id)
        except Node.DoesNotExist:
            self.node = None
            logger.warning(f"节点 {node_id} 不存在")
    def update_kyber_keys(self, security_level: int = 512) -> Dict[str, Any]:
        try:
            start_time = time.time()
            logger.info(f"开始更新节点 {self.node_id} 的无证书Kyber密钥对")
            logger.info(f"   安全级别: Kyber-{security_level}")
            node = Node.objects.get(node_id=self.node_id)

            logger.info(f"   使用优化的密钥生成服务生成Kyber-{security_level}密钥对...")
            keygen_start = time.time()
            keygen_service = OptimizedKeygenService()
            keypair_result = keygen_service.generate_kyber_keypair(self.node_id)
            keygen_time = time.time() - keygen_start

            if not keypair_result['success']:
                return {
                    'success': False,
                    'message': f"密钥生成失败: {keypair_result.get('error')}"
                }

            logger.info(f"   将Kyber公钥转换为base64编码...")
            kyber_pk_bytes = np.array(keypair_result['public_key'], dtype=np.uint8).tobytes()
            kyber_public_key = base64.b64encode(kyber_pk_bytes).decode('utf-8')

            logger.info(f"   将Kyber私钥转换为base64编码...")
            kyber_sk_bytes = np.array(keypair_result['private_key'], dtype=np.uint8).tobytes()
            kyber_private_key = base64.b64encode(kyber_sk_bytes).decode('utf-8')

            logger.info(f"   保存Kyber部分私钥数据...")
            kyber_partial_key_data = json.dumps({
                'partial_key_t': keypair_result.get('partial_key_t'),
                'secret_value_s_id': keypair_result.get('secret_value_s_id'),
                'hash_c': keypair_result.get('hash_c'),
                'u_prime_id': keypair_result.get('u_prime_id')
            })

            with transaction.atomic():
                # 使用 update 方法分字段更新，避免单个数据包过大
                Node.objects.filter(id=node.id).update(
                    kyber_public_key=kyber_public_key,
                    kyber_private_key=kyber_private_key,
                    kyber_partial_key_data=kyber_partial_key_data,
                    kyber_security_level=str(security_level)
                )

            total_time = time.time() - start_time
            logger.info(f"无证书Kyber密钥更新成功")
            logger.info(f"   ⏱️  密钥生成耗时: {keygen_time*1000:.2f}ms")
            logger.info(f"   ⏱️  总耗时: {total_time*1000:.2f}ms")

            return {
                'success': True,
                'message': f"无证书Kyber-{security_level}密钥对更新成功",
                'data': {
                    'node_id': self.node_id,
                    'key_type': 'kyber',
                    'algorithm': 'OptimizedKyber',
                    'security_level': security_level,
                    'public_key_length': len(kyber_public_key),
                    'private_key_length': len(kyber_private_key),
                    'generation_time': round(keygen_time, 4),
                    'total_time': round(total_time, 4),
                    'status': node.status
                }
            }
        except Node.DoesNotExist:
            return {
                'success': False,
                'message': f"节点 {self.node_id} 不存在"
            }
        except Exception as e:
            logger.error(f"更新Kyber密钥失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': f'Kyber密钥更新失败: {str(e)}'
            }
    def update_falcon_keys(self, security_level: int = 512) -> Dict[str, Any]:
        try:
            start_time = time.time()
            logger.info(f" 开始更新节点 {self.node_id} 的无证书Falcon-{security_level}密钥对")
            logger.info(f"   安全级别: Falcon-{security_level}")
            node = Node.objects.get(node_id=self.node_id)

            # 检查是否有KGC部分私钥
            if node.falcon_partial_key_data:
                logger.info(f"   发现KGC部分私钥，使用KGC部分私钥完成密钥生成...")
                try:
                    falcon_partial = json.loads(node.falcon_partial_key_data)
                    partial_key_b64 = falcon_partial.get('partial_key')
                    if partial_key_b64:
                        from .node_service import decode_falcon_partial_key
                        partial_inner = decode_falcon_partial_key(partial_key_b64)
                        D_id_list = partial_inner['D_id']
                        H_id_list = partial_inner['H_id']
                        A_list = partial_inner.get('A')
                        B_list = partial_inner.get('B')

                        keygen_start = time.time()
                        keygen_service = OptimizedKeygenService()
                        keypair_result = keygen_service.complete_falcon_keygen_with_partial_key(
                            node_id=self.node_id,
                            D_id_list=D_id_list,
                            H_id_list=H_id_list,
                            A_list=A_list,
                            B_list=B_list,
                            security_level=security_level
                        )
                        keygen_time = time.time() - keygen_start
                        logger.info(f"   使用KGC部分私钥完成密钥生成，耗时: {keygen_time:.4f}秒")
                    else:
                        raise ValueError("falcon_partial_key_data中缺少partial_key字段")
                except Exception as e:
                    logger.warning(f"   使用KGC部分私钥失败: {e}，回退到完整生成")
                    keygen_start = time.time()
                    keygen_service = OptimizedKeygenService()
                    keypair_result = keygen_service.generate_falcon_keypair(
                        self.node_id, security_level=security_level
                    )
                    keygen_time = time.time() - keygen_start
            else:
                logger.info(f"   无KGC部分私钥，使用完整密钥生成流程...")
                keygen_start = time.time()
                keygen_service = OptimizedKeygenService()
                keypair_result = keygen_service.generate_falcon_keypair(
                    self.node_id, security_level=security_level
                )
                keygen_time = time.time() - keygen_start

            if not keypair_result['success']:
                return {
                    'success': False,
                    'message': f"密钥生成失败: {keypair_result.get('error')}"
                }

            # 获取参数信息
            kp_params = keypair_result.get('parameters', {
                'n': 512 if security_level == 512 else 1024,
                'm': 1024 if security_level == 512 else 2048,
                'q': 12289
            })

            logger.info(f"   将Falcon公钥转换为包含参数的JSON格式...")
            falcon_pk_data = {
                'U_id': keypair_result['public_key'],
                'H_id': keypair_result.get('H_id'),
                'A': keypair_result.get('A'),
                'B': keypair_result.get('B'),
                'algorithm': f'CertificatelessFalcon-{security_level}',
                'security_level': security_level,
                'node_id': self.node_id,
                'parameters': kp_params
            }
            falcon_public_key_b64 = base64.b64encode(
                json.dumps(falcon_pk_data).encode('utf-8')
            ).decode('utf-8')
            logger.info(f"   压缩Falcon公钥...")
            falcon_public_key = compress_key_data(falcon_public_key_b64)

            logger.info(f"   将Falcon私钥转换为包含参数的JSON格式...")
            falcon_sk_data = {
                'D_id': keypair_result['private_key']['D_id'],
                'S_id': keypair_result['private_key']['S_id'],
                'algorithm': f'CertificatelessFalcon-{security_level}',
                'security_level': security_level,
                'node_id': self.node_id,
                'parameters': kp_params
            }
            falcon_private_key_b64 = base64.b64encode(
                json.dumps(falcon_sk_data).encode('utf-8')
            ).decode('utf-8')
            logger.info(f"   压缩Falcon私钥...")
            falcon_private_key = compress_key_data(falcon_private_key_b64)

            logger.info(f"   保存Falcon格密码参数...")
            falcon_lattice_params = json.dumps({
                'D_id': keypair_result.get('D_id'),
                'S_id': keypair_result.get('S_id'),
                'H_id': keypair_result.get('H_id'),
                'algorithm': f'CertificatelessFalcon-{security_level}',
                'security_level': security_level,
                'parameters': kp_params
            })

            with transaction.atomic():
                # 使用 update 方法分字段更新，避免单个数据包过大
                Node.objects.filter(id=node.id).update(
                    falcon_public_key=falcon_public_key,
                    falcon_private_key=falcon_private_key,
                    falcon_lattice_params=falcon_lattice_params,
                    falcon_security_level=str(security_level),
                    partial_key_received=True,
                    status='active'
                )

            total_time = time.time() - start_time
            logger.info(f" 无证书Falcon密钥更新成功")
            logger.info(f"   ⏱️  密钥生成耗时: {keygen_time*1000:.2f}ms")
            logger.info(f"   ⏱️  总耗时: {total_time*1000:.2f}ms")
            logger.info(f"    公钥长度: {len(falcon_public_key)} bytes")
            logger.info(f"    私钥长度: {len(falcon_private_key)} bytes")

            return {
                'success': True,
                'message': f"无证书Falcon-{security_level}密钥对更新成功",
                'data': {
                    'node_id': self.node_id,
                    'key_type': 'falcon',
                    'algorithm': 'OptimizedFalcon',
                    'security_level': security_level,
                    'public_key_length': len(falcon_public_key),
                    'private_key_length': len(falcon_private_key),
                    'generation_time': round(keygen_time, 4),
                    'total_time': round(total_time, 4),
                    'status': node.status
                }
            }
        except Node.DoesNotExist:
            return {
                'success': False,
                'message': f"节点 {self.node_id} 不存在"
            }
        except Exception as e:
            logger.error(f" 更新Falcon密钥失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': f"更新Falcon密钥失败: {str(e)}"
            }
    def update_both_keys(self, kyber_security_level: int = 512, falcon_security_level: int = 512) -> Dict[str, Any]:
        try:
            start_time = time.time()
            logger.info(f" 开始同时更新节点 {self.node_id} 的Kyber和Falcon密钥对")
            logger.info(f"   Kyber安全级别: {kyber_security_level}")
            logger.info(f"   Falcon安全级别: {falcon_security_level}")
            logger.info(f"  步骤1: 更新Kyber密钥对...")
            kyber_result = self.update_kyber_keys(kyber_security_level)
            if not kyber_result['success']:
                return {
                    'success': False,
                    'message': f"Kyber密钥更新失败: {kyber_result['message']}"
                }
            logger.info(f"   步骤1完成: Kyber密钥更新成功")
            logger.info(f"  步骤2: 更新Falcon密钥对...")
            falcon_result = self.update_falcon_keys(falcon_security_level)
            if not falcon_result['success']:
                return {
                    'success': False,
                    'message': f"Falcon密钥更新失败: {falcon_result['message']}"
                }
            logger.info(f"   步骤2完成: Falcon密钥更新成功")
            node = Node.objects.get(node_id=self.node_id)
            total_time = time.time() - start_time
            logger.info(f" 所有密钥更新完成")
            logger.info(f"   ⏱️  总耗时: {total_time:.3f}秒")
            return {
                'success': True,
                'message': f"无证书Kyber-{kyber_security_level}和Falcon-{falcon_security_level}密钥对同时更新成功",
                'data': {
                    'node_id': self.node_id,
                    'key_type': 'both',
                    'kyber_security_level': kyber_security_level,
                    'falcon_security_level': falcon_security_level,
                    'kyber_data': kyber_result['data'],
                    'falcon_data': falcon_result['data'],
                    'total_time': round(total_time, 4),
                    'final_status': node.status
                }
            }
        except Exception as e:
            logger.error(f" 同时更新密钥失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': f"同时更新密钥失败: {str(e)}"
            }