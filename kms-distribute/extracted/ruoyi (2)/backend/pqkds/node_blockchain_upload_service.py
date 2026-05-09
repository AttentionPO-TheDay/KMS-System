import logging
import hashlib
import json
import base64
from typing import Dict, Any
from django.utils import timezone
from .blockchain_service import BlockchainService
from .models import Node
logger = logging.getLogger(__name__)
class NodeBlockchainUploadService:
    def __init__(self):
        self.blockchain_service = BlockchainService()
    def upload_node_registration(self, node: Node) -> Dict[str, Any]:
        try:
            logger.info(f" 开始上链节点注册信息: {node.node_id}")
            node_info = {
                'node_id': node.node_id,
                'name': node.name,
                'ip_address': node.ip_address,
                'port': node.port,
                'registration_time': timezone.now().isoformat(),
                'status': node.status
            }

            # 第一步：先在区块链上注册节点基本信息
            if self.blockchain_service.is_connected():
                logger.info(f"   开始在区块链上注册节点基本信息...")
                try:
                    node_exists = self.blockchain_service.contract.functions.nodeExists(node.node_id).call()
                    if not node_exists:
                        logger.info(f"   节点在区块链上不存在，开始注册...")
                        register_result = self.blockchain_service.register_node_on_blockchain(
                            node.node_id,
                            node.name,
                            node.ip_address,
                            node.port
                        )
                        if register_result['success']:
                            logger.info(f"   节点基本信息已在区块链上注册")
                            node_info['blockchain_registered'] = True
                        else:
                            logger.warning(f"   节点在区块链上注册失败: {register_result.get('error')}")
                            node_info['blockchain_registered'] = False
                    else:
                        logger.info(f"   节点已在区块链上存在，跳过注册")
                        node_info['blockchain_registered'] = True
                except Exception as e:
                    logger.warning(f"   检查/注册节点时出错: {e}")
                    try:
                        register_result = self.blockchain_service.register_node_on_blockchain(
                            node.node_id,
                            node.name,
                            node.ip_address,
                            node.port
                        )
                        if register_result['success']:
                            logger.info(f"   节点基本信息已在区块链上注册")
                            node_info['blockchain_registered'] = True
                        else:
                            logger.warning(f"   节点在区块链上注册失败: {register_result.get('error')}")
                            node_info['blockchain_registered'] = False
                    except Exception as reg_err:
                        logger.warning(f"   节点注册异常: {reg_err}")
                        node_info['blockchain_registered'] = False

            # 第二步：上传Kyber公钥
            kyber_upload_result = self.upload_kyber_public_key(node)
            node_info['kyber_uploaded'] = kyber_upload_result['success']
            if kyber_upload_result['success']:
                node_info['kyber_hash'] = kyber_upload_result.get('key_hash')
                logger.info(f"   Kyber公钥已上链: {kyber_upload_result.get('key_hash')[:16]}...")

            # 第三步：上传Falcon公钥
            if node.falcon_public_key:
                falcon_upload_result = self.upload_falcon_public_key(node)
                node_info['falcon_uploaded'] = falcon_upload_result['success']
                if falcon_upload_result['success']:
                    node_info['falcon_hash'] = falcon_upload_result.get('key_hash')
                    logger.info(f"   Falcon公钥已上链: {falcon_upload_result.get('key_hash')[:16]}...")

            logger.info(f" 节点 {node.node_id} 注册信息上链完成")
            return {
                'success': True,
                'message': f'节点 {node.node_id} 信息上链成功',
                'node_info': node_info
            }
        except Exception as e:
            logger.error(f" 节点信息上链失败: {e}")
            return {
                'success': False,
                'message': f'节点信息上链失败: {str(e)}'
            }
    def upload_kyber_public_key(self, node: Node) -> Dict[str, Any]:
        try:
            if not node.kyber_public_key:
                return {
                    'success': False,
                    'message': 'Kyber公钥不存在'
                }
            kyber_key_size = len(node.kyber_public_key) / (1024 * 1024)
            logger.info(f"   Kyber公钥大小: {kyber_key_size:.3f}MB")
            key_hash = hashlib.sha256(
                node.kyber_public_key.encode('utf-8')
            ).hexdigest()
            logger.info(f"   Kyber公钥哈希: {key_hash[:32]}...")
            if self.blockchain_service.is_connected():
                # 确保节点已在区块链上注册
                try:
                    node_exists = self.blockchain_service.contract.functions.nodeExists(node.node_id).call()
                    if not node_exists:
                        logger.info(f"   节点在区块链上不存在，先进行注册...")
                        register_result = self.blockchain_service.register_node_on_blockchain(
                            node.node_id,
                            node.name,
                            node.ip_address,
                            node.port
                        )
                        if not register_result['success']:
                            logger.error(f"   节点注册失败: {register_result.get('error')}")
                            return {
                                'success': False,
                                'message': f'节点注册失败: {register_result.get("error")}'
                            }
                        logger.info(f"   节点已成功注册到区块链")
                except Exception as check_err:
                    logger.warning(f"   检查节点存在性时出错: {check_err}，尝试直接注册...")
                    try:
                        register_result = self.blockchain_service.register_node_on_blockchain(
                            node.node_id,
                            node.name,
                            node.ip_address,
                            node.port
                        )
                        if not register_result['success']:
                            logger.error(f"   节点注册失败: {register_result.get('error')}")
                            return {
                                'success': False,
                                'message': f'节点注册失败: {register_result.get("error")}'
                            }
                        logger.info(f"   节点已成功注册到区块链")
                    except Exception as reg_err:
                        logger.error(f"   节点注册异常: {reg_err}")
                        return {
                            'success': False,
                            'message': f'节点注册异常: {str(reg_err)}'
                        }

                # 节点已注册，现在上传Kyber公钥
                kyber_pk_bytes = base64.b64decode(node.kyber_public_key)
                logger.info(f"   解码后的Kyber公钥长度: {len(kyber_pk_bytes)} bytes")
                blockchain_result = self.blockchain_service.upload_kyber_public_key(
                    node.node_id,
                    kyber_pk_bytes
                )
                if blockchain_result['success']:
                    return {
                        'success': True,
                        'key_hash': key_hash,
                        'tx_hash': blockchain_result.get('tx_hash'),
                        'size_mb': kyber_key_size
                    }
                else:
                    logger.warning(f"    Kyber公钥上链失败: {blockchain_result.get('error')}")
            return {
                'success': True,
                'key_hash': key_hash,
                'size_mb': kyber_key_size,
                'blockchain_skipped': True
            }
        except Exception as e:
            logger.error(f"   Kyber公钥上链出错: {e}")
            return {
                'success': False,
                'message': f'Kyber公钥上链失败: {str(e)}'
            }
    def upload_falcon_public_key(self, node: Node) -> Dict[str, Any]:
        try:
            if not node.falcon_public_key:
                return {
                    'success': False,
                    'message': 'Falcon公钥不存在'
                }
            falcon_key_size = len(node.falcon_public_key) / (1024 * 1024)
            logger.info(f"   Falcon公钥大小: {falcon_key_size:.3f}MB")
            key_hash = hashlib.sha256(
                node.falcon_public_key.encode('utf-8')
            ).hexdigest()
            logger.info(f"   Falcon公钥哈希: {key_hash[:32]}...")
            if self.blockchain_service.is_connected():
                # 确保节点已在区块链上注册
                try:
                    node_exists = self.blockchain_service.contract.functions.nodeExists(node.node_id).call()
                    if not node_exists:
                        logger.info(f"   节点在区块链上不存在，先进行注册...")
                        register_result = self.blockchain_service.register_node_on_blockchain(
                            node.node_id,
                            node.name,
                            node.ip_address,
                            node.port
                        )
                        if not register_result['success']:
                            logger.error(f"   节点注册失败: {register_result.get('error')}")
                            return {
                                'success': False,
                                'message': f'节点注册失败: {register_result.get("error")}'
                            }
                        logger.info(f"   节点已成功注册到区块链")
                except Exception as check_err:
                    logger.warning(f"   检查节点存在性时出错: {check_err}，尝试直接注册...")
                    try:
                        register_result = self.blockchain_service.register_node_on_blockchain(
                            node.node_id,
                            node.name,
                            node.ip_address,
                            node.port
                        )
                        if not register_result['success']:
                            logger.error(f"   节点注册失败: {register_result.get('error')}")
                            return {
                                'success': False,
                                'message': f'节点注册失败: {register_result.get("error")}'
                            }
                        logger.info(f"   节点已成功注册到区块链")
                    except Exception as reg_err:
                        logger.error(f"   节点注册异常: {reg_err}")
                        return {
                            'success': False,
                            'message': f'节点注册异常: {str(reg_err)}'
                        }

                # 节点已注册，现在上传Falcon公钥
                blockchain_result = self.blockchain_service.upload_falcon_public_key_hash(
                    node.node_id,
                    node.falcon_public_key
                )
                if blockchain_result['success']:
                    return {
                        'success': True,
                        'key_hash': key_hash,
                        'tx_hash': blockchain_result.get('tx_hash'),
                        'size_mb': falcon_key_size
                    }
                else:
                    logger.warning(f"    Falcon公钥上链失败: {blockchain_result.get('error')}")
            return {
                'success': True,
                'key_hash': key_hash,
                'size_mb': falcon_key_size,
                'blockchain_skipped': True
            }
        except Exception as e:
            logger.error(f"   Falcon公钥上链出错: {e}")
            return {
                'success': False,
                'message': f'Falcon公钥上链失败: {str(e)}'
            }
    def upload_key_update(self, node: Node, key_type: str, security_level: int) -> Dict[str, Any]:
        try:
            logger.info(f" 开始上链密钥更新: {node.node_id} ({key_type})")
            update_info = {
                'node_id': node.node_id,
                'key_type': key_type,
                'security_level': security_level,
                'update_time': timezone.now().isoformat(),
                'hashes': {}
            }
            if key_type in ['kyber', 'both'] and node.kyber_public_key:
                kyber_result = self.upload_kyber_public_key(node)
                if kyber_result['success']:
                    update_info['hashes']['kyber'] = kyber_result.get('key_hash')
                    logger.info(f"   Kyber密钥更新已上链")
            if key_type in ['falcon', 'both'] and node.falcon_public_key:
                falcon_result = self.upload_falcon_public_key(node)
                if falcon_result['success']:
                    update_info['hashes']['falcon'] = falcon_result.get('key_hash')
                    logger.info(f"   Falcon密钥更新已上链")
            logger.info(f" 密钥更新信息上链完成")
            return {
                'success': True,
                'message': '密钥更新信息上链成功',
                'update_info': update_info
            }
        except Exception as e:
            logger.error(f" 密钥更新上链失败: {e}")
            return {
                'success': False,
                'message': f'密钥更新上链失败: {str(e)}'
            }