import logging
from typing import Dict, Any, Optional
from .blockchain_service import BlockchainService
from .models import Node
logger = logging.getLogger(__name__)
class NodeDiscoveryService:
    def __init__(self):
        self.blockchain_service = BlockchainService()
    def discover_node(self, node_id: str) -> Dict[str, Any]:
        logger.info(f"开始发现节点 {node_id} 的网络地址")
        try:
            blockchain_result = self.blockchain_service.get_node_info_from_blockchain(node_id)
            if blockchain_result.get('success'):
                node_info = {
                    'node_id': node_id,
                    'ip_address': blockchain_result.get('ip_address'),
                    'port': blockchain_result.get('port'),
                    'name': blockchain_result.get('name'),
                    'is_active': blockchain_result.get('is_active'),
                    'source': 'blockchain'
                }
                logger.info(f"从区块链发现节点 {node_id}: {node_info['ip_address']}:{node_info['port']}")
                return {
                    'success': True,
                    'node_info': node_info
                }
            else:
                logger.warning(f"从区块链查询节点 {node_id} 失败: {blockchain_result.get('error')}")
                try:
                    db_node = Node.objects.get(node_id=node_id)
                    node_info = {
                        'node_id': node_id,
                        'ip_address': str(db_node.ip_address),
                        'port': db_node.port,
                        'name': db_node.name,
                        'is_active': db_node.status == 'active',
                        'source': 'database'
                    }
                    logger.info(f"从数据库发现节点 {node_id}: {node_info['ip_address']}:{node_info['port']}")
                    return {
                        'success': True,
                        'node_info': node_info
                    }
                except Node.DoesNotExist:
                    logger.error(f"节点 {node_id} 在区块链和数据库中都不存在")
                    return {
                        'success': False,
                        'error': f'节点 {node_id} 不存在'
                    }
                except Exception as e:
                    logger.error(f"从数据库查询节点 {node_id} 失败: {e}")
                    return {
                        'success': False,
                        'error': f'查询节点失败: {str(e)}'
                    }
        except Exception as e:
            logger.error(f"节点发现异常: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    def get_node_network_address(self, node_id: str) -> Optional[Dict[str, Any]]:
        result = self.discover_node(node_id)
        if result.get('success'):
            node_info = result.get('node_info', {})
            return {
                'ip_address': node_info.get('ip_address'),
                'port': node_info.get('port')
            }
        return None