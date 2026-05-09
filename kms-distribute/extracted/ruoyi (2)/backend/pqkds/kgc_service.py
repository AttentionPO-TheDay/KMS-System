import json
import base64
import hashlib
import numpy as np
from typing import Dict, Any, Tuple, Optional
from django.utils import timezone
from datetime import timedelta
from .models import SystemParameters, Node, Transaction, Block
from .crypto_utils import AESCrypto
from .real_crypto_with_fallback import RealKyberKEM, RealAESCipher, BlockchainBasedCertificatelessFalcon
from .blockchain_service import BlockchainService
class KGCService:
    def __init__(self, security_level=512):
        self.security_level = int(security_level) if security_level else 512
        self.blockchain_falcon = BlockchainBasedCertificatelessFalcon(
            security_level=self.security_level,
            kyber_security_level=self.security_level
        )
        self.real_aes = RealAESCipher()
        self.aes = AESCrypto()
        self.system_params = None
        self.blockchain_service = BlockchainService()
    def get_node_kyber_public_key_from_blockchain(self, node_id: str) -> Dict[str, Any]:
        import logging
        logger = logging.getLogger(__name__)
        try:
            result = self.blockchain_service.get_node_kyber_public_key(node_id)
            if not result['success']:
                logger.error(f"从区块链获取节点 {node_id} Kyber公钥失败: {result.get('error', 'Unknown error')}")
                return {
                    'success': False,
                    'error': f"Failed to get Kyber public key from blockchain: {result.get('error', 'Unknown error')}"
                }
            kyber_public_key_bytes = result['kyber_public_key']
            if not kyber_public_key_bytes or len(kyber_public_key_bytes) == 0:
                logger.error(f"节点 {node_id} 的Kyber公钥为空")
                return {
                    'success': False,
                    'error': f"Node {node_id} Kyber public key is empty"
                }
            logger.info(f" 成功从区块链获取节点 {node_id} 的Kyber公钥，长度: {len(kyber_public_key_bytes)} bytes")
            return {
                'success': True,
                'kyber_public_key': kyber_public_key_bytes
            }
        except Exception as e:
            logger.error(f"从区块链获取节点 {node_id} Kyber公钥时发生异常: {str(e)}")
            return {
                'success': False,
                'error': f"Exception occurred while getting Kyber public key: {str(e)}"
            }
    def initialize_system(self, name: str = "default") -> Dict[str, Any]:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning("initialize_system方法已废弃，V1方案已移除，请使用V2方案的陷门密钥生成")
        return {
            'success': False,
            'message': 'V1方案已移除，请使用V2方案（基于陷门的密钥生成）'
        }
    def load_system_parameters(self, name: str = "default") -> bool:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning("load_system_parameters方法已废弃，V1方案已移除")
        return False
    def generate_partial_key(self, node_id: str) -> Dict[str, Any]:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning("generate_partial_key方法已废弃，V1方案已移除，请使用V2方案")
        return {
            'success': False,
            'message': 'V1方案已移除，请使用V2方案（基于陷门的密钥生成）'
        }
    def generate_kyber_partial_key(self, node_id: str) -> Dict[str, Any]:
        import logging
        logger = logging.getLogger(__name__)
        try:
            logger.info(f"KGC为节点{node_id}生成无证书Kyber部分私钥（融合模块）")
            from .certificateless_kyber_dll_fusion import get_fusion_instance

            fusion = get_fusion_instance(variant=self.security_level)
            partial_result = fusion.kgc_partial_key_gen(node_id)

            if not partial_result['success']:
                logger.error(f"无证书Kyber部分私钥生成失败")
                return {
                    'success': False,
                    'error': '部分私钥生成失败',
                    'message': 'Failed to generate certificateless Kyber partial private key'
                }

            # 序列化部分私钥数据
            from .certificateless_kyber_dll_fusion import CertificatelessKyberDLLFusion
            partial_key_data = {
                'node_id': node_id,
                'algorithm': f'CertificatelessKyber{self.security_level}_DLL',
                'partial_key_t': partial_result['partial_key_t'].tolist(),
                'hash_c': partial_result['hash_c'].tolist(),
                'u_prime_id': partial_result['u_prime_id'].tolist(),
                'timestamp': timezone.now().isoformat(),
                'parameters': {
                    'n': fusion.n,
                    'm': fusion.m,
                    'q': fusion.q,
                    'sigma': fusion.sigma,
                    'variant': fusion.variant,
                }
            }

            logger.info(f"无证书Kyber部分私钥生成完成（融合模块），直接明文传递给节点")
            return {
                'success': True,
                'partial_key_data': partial_key_data,
                'message': 'Certificateless Kyber partial private key generated (fusion module)'
            }
        except Exception as e:
            logger.error(f"KGC生成无证书Kyber部分私钥失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e),
                'message': 'Failed to generate certificateless Kyber partial private key'
            }
    def generate_falcon_partial_key(self, node_id: str, security_level: int = 512) -> Dict[str, Any]:
        import logging
        logger = logging.getLogger(__name__)
        try:
            logger.info(f"KGC为节点{node_id}生成无证书Falcon-{security_level}部分私钥（优化版本，直接明文传递）")
            from .falcon_partial_key_gen_optimized import CertificatelessFalconPartialKeyGenOptimized
            from .falcon_aes_session_encryption import FALCON_PARAMS
            params = FALCON_PARAMS.get(security_level, FALCON_PARAMS[512])
            ck_partial = CertificatelessFalconPartialKeyGenOptimized(
                n=params['n'], m=params['m'], q=params['q'], num_workers=4
            )
            partial_key_result = ck_partial.generate_falcon_partial_key_optimized(node_id)
            if not partial_key_result['success']:
                logger.error(f"无证书Falcon-{security_level}部分私钥生成失败: {partial_key_result['message']}")
                return {
                    'success': False,
                    'error': partial_key_result['message'],
                    'message': 'Failed to generate certificateless Falcon partial private key'
                }
            partial_key_b64 = partial_key_result['partial_key']
            partial_key_data = {
                'node_id': node_id,
                'algorithm': f'CertificatelessFalcon-{security_level}',
                'security_level': security_level,
                'partial_key': partial_key_b64,
                'timestamp': timezone.now().isoformat(),
                'parameters': params
            }
            logger.info(f"无证书Falcon部分私钥生成完成，直接明文传递给节点")
            if 'timing' in partial_key_result:
                timing = partial_key_result['timing']
                logger.info(f"  - PartialKeyGen: {timing.get('partial_key_gen', 0):.3f}秒")
                logger.info(f"  - 总耗时: {timing.get('total', 0):.3f}秒")
            try:
                ck_partial.shutdown()
            except:
                pass
            return {
                'success': True,
                'partial_key_data': partial_key_data,
                'message': 'Certificateless Falcon partial private key generated and delivered to node'
            }
        except Exception as e:
            logger.error(f"KGC生成无证书Falcon部分私钥失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e),
                'message': 'Failed to generate certificateless Falcon partial private key'
            }
    def generate_partial_key_v2(self, node_id: str, algorithm: str = 'v1') -> Dict[str, Any]:
        try:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f" KGC开始为节点 {node_id} 生成{algorithm.upper()}部分私钥")
            try:
                node = Node.objects.get(node_id=node_id)
            except Node.DoesNotExist:
                return {
                    'success': False,
                    'message': f'Node {node_id} not found'
                }
            kyber_result = self.get_node_kyber_public_key_from_blockchain(node_id)
            if not kyber_result['success']:
                return {
                    'success': False,
                    'message': f'Failed to get Kyber public key from blockchain: {kyber_result["error"]}'
                }
            kyber_public_key_bytes = kyber_result['kyber_public_key']
            kyber_public_key_b64 = base64.b64encode(kyber_public_key_bytes).decode('utf-8')
            node_kyber_level = int(getattr(node, 'kyber_security_level', '512') or '512')
            node_falcon_level = int(getattr(node, 'falcon_security_level', '512') or '512')
            logger.info(f" 节点 {node_id} 安全级别配置:")
            logger.info(f"   Kyber安全级别: {node_kyber_level}")
            logger.info(f"   Falcon安全级别: {node_falcon_level}")
            from .real_crypto_with_fallback import BlockchainBasedCertificatelessFalcon
            node_crypto_system = BlockchainBasedCertificatelessFalcon(
                security_level=node_falcon_level,
                kyber_security_level=node_kyber_level,
                force_real_crypto=True
            )
            if algorithm.lower() == 'v2':
                result = node_crypto_system.kgc_partial_key_generation_v2(
                    node_id,
                    kyber_public_key_b64
                )
            else:
                result = node_crypto_system.kgc_partial_key_generation(
                    node_id,
                    kyber_public_key_b64
                )
            if result['success']:
                logger.info(f" {algorithm.upper()}部分私钥生成并加密成功")
            else:
                logger.error(f" {algorithm.upper()}部分私钥生成失败: {result.get('message', 'Unknown error')}")
            return result
        except Exception as e:
            logger.error(f" {algorithm.upper()}部分私钥生成过程中发生错误: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': f'{algorithm.upper()}部分私钥生成失败: {str(e)}'
            }
    def process_node_registration(self, node_id: str) -> Dict[str, Any]:
        try:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"KGC开始为节点{node_id}生成部分私钥（新流程）")
            try:
                node = Node.objects.get(node_id=node_id)
            except Node.DoesNotExist:
                return {
                    'success': False,
                    'message': f'Node {node_id} not found'
                }
            from .partial_key_generation_service import PartialKeyGenerationService
            node_kyber_level = getattr(node, 'kyber_security_level', '512')
            node_falcon_level = getattr(node, 'falcon_security_level', '512')
            try:
                node_kyber_level = int(node_kyber_level) if node_kyber_level else 512
                node_falcon_level = int(node_falcon_level) if node_falcon_level else 512
            except (ValueError, TypeError):
                node_kyber_level = 512
                node_falcon_level = 512
            logger.info(f"节点{node_id}安全级别: Kyber-{node_kyber_level}, Falcon-{node_falcon_level}")
            partial_key_service = PartialKeyGenerationService(node_kyber_level)
            kyber_partial_result = partial_key_service.generate_kyber_partial_private_key(node_id)
            if not kyber_partial_result['success']:
                return kyber_partial_result
            falcon_partial_result = partial_key_service.generate_falcon_partial_private_key(node_id)
            if not falcon_partial_result['success']:
                return falcon_partial_result
            partial_key_package = {
                'kyber_partial_key': kyber_partial_result['partial_key_data'],
                'falcon_partial_key': falcon_partial_result['partial_key_data'],
                'timestamp': timezone.now().isoformat()
            }
            node.partial_key_data = json.dumps(partial_key_package)
            node.partial_key_received = True
            node.status = 'partial_key_received'
            node.save()
            logger.info(f"节点{node_id}部分私钥生成成功，等待节点生成完整密钥对")
            self._create_partial_key_transaction(node, partial_key_package)
            return {
                'success': True,
                'message': f'KGC部分私钥生成完成，节点需要生成完整密钥对',
                'partial_key_package': partial_key_package
            }
        except Exception as e:
            logger.error(f"节点注册失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': f'Failed to process node registration: {str(e)}'
            }
    def _create_partial_key_transaction(self, node: Node, encrypted_package: Dict[str, Any]):
        tx_data = {
            'type': 'partial_key_transfer',
            'recipient': node.node_id,
            'encrypted_package': encrypted_package
        }
        tx_data_str = json.dumps(tx_data, sort_keys=True)
        tx_hash = hashlib.sha256(tx_data_str.encode()).hexdigest()
        latest_block = Block.objects.order_by('-block_number').first()
        if not latest_block:
            latest_block = Block.objects.create(
                block_hash=hashlib.sha256(b'genesis').hexdigest(),
                previous_hash='0' * 64,
                block_number=0,
                merkle_root=hashlib.sha256(b'genesis_merkle').hexdigest(),
                nonce=0
            )
        Transaction.objects.create(
            tx_hash=tx_hash,
            block=latest_block,
            tx_type='partial_key_transfer',
            from_node=node,
            to_node=node,
            data=json.dumps(tx_data),
            signature='kgc_signature',  
            confirmed=True
        )
    def generate_and_save_kyber_partial_key(self, node_id: str) -> Dict[str, Any]:
        import logging
        logger = logging.getLogger(__name__)
        try:
            logger.info(f"KGC生成并保存节点{node_id}的Kyber部分私钥")
            try:
                node = Node.objects.get(node_id=node_id)
            except Node.DoesNotExist:
                logger.error(f"节点{node_id}不存在")
                return {
                    'success': False,
                    'message': f'Node {node_id} not found'
                }
            kyber_result = self.generate_kyber_partial_key(node_id)
            if not kyber_result['success']:
                return kyber_result
            partial_key_data = kyber_result['partial_key_data']
            node.kyber_partial_key_data = json.dumps(partial_key_data)

            # 检查是否两个部分私钥都已接收
            has_kyber_partial = True  # 当前正在保存
            has_falcon_partial = bool(node.falcon_partial_key_data)

            # 如果两个部分私钥都已接收，更新状态
            partial_key_received = False
            if has_kyber_partial and has_falcon_partial:
                partial_key_received = True
                logger.info(f"节点{node_id}的Kyber和Falcon部分私钥都已接收，更新状态为已接收")

            # 使用update而不是save，避免数据包过大的问题
            Node.objects.filter(node_id=node_id).update(
                kyber_partial_key_data=json.dumps(partial_key_data),
                partial_key_received=partial_key_received
            )
            logger.info(f"节点{node_id}的Kyber部分私钥已保存到数据库")
            return {
                'success': True,
                'partial_key_data': partial_key_data,
                'message': 'Kyber partial private key generated and saved successfully',
                'partial_key_received': partial_key_received
            }
        except Exception as e:
            logger.error(f"KGC生成并保存Kyber部分私钥失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e),
                'message': 'Failed to generate and save Kyber partial private key'
            }
    def generate_and_save_falcon_partial_key(self, node_id: str) -> Dict[str, Any]:
        import logging
        logger = logging.getLogger(__name__)
        try:
            logger.info(f"KGC生成并保存节点{node_id}的Falcon部分私钥")
            try:
                node = Node.objects.get(node_id=node_id)
            except Node.DoesNotExist:
                logger.error(f"节点{node_id}不存在")
                return {
                    'success': False,
                    'message': f'Node {node_id} not found'
                }
            # 获取节点的 Falcon 安全级别
            security_level = int(getattr(node, 'falcon_security_level', '512') or '512')
            logger.info(f"节点{node_id}的Falcon安全级别: Falcon-{security_level}")

            # 提前读取需要的数据库字段
            has_kyber_partial = bool(node.kyber_partial_key_data)

            # Falcon-1024 的矩阵乘法 H_id = A·D_id (1024×2048)×(2048×2048) 耗时较长，
            # 在长时间 CPU 计算前主动关闭数据库连接，防止 MySQL 空闲超时断开。
            from django.db import connection as db_conn
            db_conn.close()
            logger.info(f"[DB] Falcon部分私钥生成前关闭数据库连接")

            falcon_result = self.generate_falcon_partial_key(node_id, security_level=security_level)

            if not falcon_result['success']:
                return falcon_result
            partial_key_data = falcon_result['partial_key_data']

            # CPU 计算完成，强制重建数据库连接
            db_conn.close()
            db_conn.connect()
            logger.info(f"[DB] Falcon部分私钥生成完成，数据库连接已重新建立")

            # 如果两个部分私钥都已接收，更新状态
            partial_key_received = has_kyber_partial  # Falcon 部分正在保存

            # 使用update写入，带重试逻辑应对 max_allowed_packet 或连接问题
            partial_data_json = json.dumps(partial_key_data)
            for attempt in range(2):
                try:
                    Node.objects.filter(node_id=node_id).update(
                        falcon_partial_key_data=partial_data_json,
                        partial_key_received=partial_key_received
                    )
                    break
                except Exception as e:
                    if attempt == 0 and ('Server has gone away' in str(e) or '2006' in str(e)):
                        logger.warning(f"[DB] 写入falcon_partial_key_data失败，重连后重试: {e}")
                        db_conn.close()
                        db_conn.connect()
                    else:
                        raise
            logger.info(f"节点{node_id}的Falcon部分私钥已保存到数据库")
            return {
                'success': True,
                'partial_key_data': partial_key_data,
                'message': 'Falcon partial private key generated and saved successfully',
                'partial_key_received': partial_key_received
            }
        except Exception as e:
            logger.error(f"KGC生成并保存Falcon部分私钥失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e),
                'message': 'Failed to generate and save Falcon partial private key'
            }
    def generate_all_partial_keys_for_node(self, node_id: str) -> Dict[str, Any]:
        import logging
        logger = logging.getLogger(__name__)
        try:
            logger.info(f"KGC为节点{node_id}生成所有部分私钥")
            try:
                node = Node.objects.get(node_id=node_id)
            except Node.DoesNotExist:
                logger.error(f"节点{node_id}不存在")
                return {
                    'success': False,
                    'message': f'Node {node_id} not found'
                }
            logger.info(f"生成Kyber部分私钥...")
            kyber_partial_result = self.generate_kyber_partial_key(node_id)
            if kyber_partial_result['success']:
                partial_key_data = kyber_partial_result['partial_key_data']
                node.kyber_partial_key_data = json.dumps(partial_key_data)
                logger.info(f"Kyber部分私钥保存成功")
            else:
                logger.warning(f"Kyber部分私钥生成失败: {kyber_partial_result.get('message')}")
            logger.info(f"生成Falcon部分私钥...")
            falcon_partial_result = self.generate_falcon_partial_key(node_id)
            if falcon_partial_result['success']:
                partial_key_data = falcon_partial_result['partial_key_data']
                node.falcon_partial_key_data = json.dumps(partial_key_data)
                logger.info(f"Falcon部分私钥保存成功")
            else:
                logger.warning(f"Falcon部分私钥生成失败: {falcon_partial_result.get('message')}")
            node.partial_key_received = True
            node.save()
            logger.info(f"节点{node_id}的所有部分私钥生成完成")
            return {
                'success': True,
                'kyber_result': kyber_partial_result,
                'falcon_result': falcon_partial_result,
                'message': 'All partial private keys generated and saved successfully'
            }
        except Exception as e:
            logger.error(f"KGC生成所有部分私钥失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e),
                'message': 'Failed to generate all partial private keys'
            }
    def get_system_status(self) -> Dict[str, Any]:
        if self.system_params is None:
            return {'initialized': False}
        node_stats = {}
        for status, _ in Node._meta.get_field('status').choices:
            node_stats[status] = Node.objects.filter(status=status).count()
        tx_stats = {}
        for tx_type, _ in Transaction.TRANSACTION_TYPES:
            tx_stats[tx_type] = Transaction.objects.filter(tx_type=tx_type).count()
        return {
            'initialized': True,
            'system_params': {
                'name': self.system_params.name,
                'n': self.system_params.n,
                'm': self.system_params.m,
                'q': self.system_params.q,
                'sigma': self.system_params.sigma,
                'created_at': self.system_params.created_at.isoformat()
            },
            'node_stats': node_stats,
            'transaction_stats': tx_stats,
            'total_nodes': Node.objects.count(),
            'total_transactions': Transaction.objects.count(),
            'total_blocks': Block.objects.count()
        }