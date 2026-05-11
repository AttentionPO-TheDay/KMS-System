import logging
from typing import Dict, Any, Optional
from .public_key_retrieval_service import PublicKeyRetrievalService
from .node_discovery_service import NodeDiscoveryService
from .models import Node
logger = logging.getLogger(__name__)
class KeyNegotiationService:
    def __init__(self, source_node_id: str):
        self.source_node_id = source_node_id
        self.public_key_service = PublicKeyRetrievalService()
        self.node_discovery_service = NodeDiscoveryService()
        try:
            self.source_node = Node.objects.get(node_id=source_node_id)
        except Node.DoesNotExist:
            logger.error(f"源节点 {source_node_id} 不存在")
            self.source_node = None
    def get_target_node_public_keys(self, target_node_id: str) -> Dict[str, Any]:
        logger.info(f"节点 {self.source_node_id} 获取节点 {target_node_id} 的公钥")
        if not self.source_node:
            return {
                'success': False,
                'error': f'源节点 {self.source_node_id} 不存在'
            }
        try:
            keys_result = self.public_key_service.get_node_public_keys(target_node_id)
            if not keys_result.get('success'):
                logger.error(f"获取节点 {target_node_id} 的公钥失败: {keys_result.get('error')}")
                return keys_result
            kyber_key = keys_result.get('kyber_public_key')
            falcon_key = keys_result.get('falcon_public_key')
            if not kyber_key and not falcon_key:
                logger.error(f"节点 {target_node_id} 没有任何公钥")
                return {
                    'success': False,
                    'error': f'节点 {target_node_id} 没有任何公钥'
                }
            logger.info(f"成功获取节点 {target_node_id} 的公钥")
            return {
                'success': True,
                'target_node_id': target_node_id,
                'kyber_public_key': kyber_key,
                'falcon_public_key': falcon_key,
                'source': keys_result.get('source')
            }
        except Exception as e:
            logger.error(f"获取目标节点公钥异常: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    def discover_target_node(self, target_node_id: str) -> Dict[str, Any]:
        logger.info(f"节点 {self.source_node_id} 发现节点 {target_node_id} 的网络地址")
        try:
            discovery_result = self.node_discovery_service.discover_node(target_node_id)
            if not discovery_result.get('success'):
                logger.error(f"发现节点 {target_node_id} 失败: {discovery_result.get('error')}")
                return discovery_result
            node_info = discovery_result.get('node_info', {})
            logger.info(f"成功发现节点 {target_node_id}: {node_info.get('ip_address')}:{node_info.get('port')}")
            return {
                'success': True,
                'target_node_id': target_node_id,
                'ip_address': node_info.get('ip_address'),
                'port': node_info.get('port'),
                'name': node_info.get('name'),
                'is_active': node_info.get('is_active'),
                'source': node_info.get('source')
            }
        except Exception as e:
            logger.error(f"发现目标节点异常: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    def prepare_key_negotiation(self, target_node_id: str) -> Dict[str, Any]:
        logger.info(f"节点 {self.source_node_id} 准备与节点 {target_node_id} 进行密钥协商")
        try:
            keys_result = self.get_target_node_public_keys(target_node_id)
            if not keys_result.get('success'):
                return keys_result
            discovery_result = self.discover_target_node(target_node_id)
            if not discovery_result.get('success'):
                return discovery_result
            logger.info(f"密钥协商准备完成: 源节点={self.source_node_id}, 目标节点={target_node_id}")
            return {
                'success': True,
                'source_node_id': self.source_node_id,
                'target_node_id': target_node_id,
                'target_kyber_public_key': keys_result.get('kyber_public_key'),
                'target_falcon_public_key': keys_result.get('falcon_public_key'),
                'target_ip_address': discovery_result.get('ip_address'),
                'target_port': discovery_result.get('port'),
                'target_name': discovery_result.get('name'),
                'keys_source': keys_result.get('source'),
                'discovery_source': discovery_result.get('source')
            }
        except Exception as e:
            logger.error(f"准备密钥协商异常: {e}")
            return {
                'success': False,
                'error': str(e)
            }