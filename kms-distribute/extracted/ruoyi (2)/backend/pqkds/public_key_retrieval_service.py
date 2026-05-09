import logging
import time
import zlib
import base64
from typing import Dict, Any, Optional
from .blockchain_service import BlockchainService
from .node_discovery_service import NodeDiscoveryService
from .models import Node
logger = logging.getLogger(__name__)
def decompress_key_data(key_data: str) -> str:
    try:
        if not key_data or not key_data.startswith("COMPRESSED:"):
            return key_data
        compressed_b64 = key_data[11:]
        compressed = base64.b64decode(compressed_b64)
        decompressed = zlib.decompress(compressed)
        return decompressed.decode('utf-8')
    except Exception as e:
        logger.warning(f"密钥解压缩失败: {e}，使用原始数据")
        return key_data
class PublicKeyRetrievalService:
    _cache = {}
    CACHE_TTL = 3600
    def __init__(self):
        self.blockchain_service = BlockchainService()
        self.node_discovery_service = NodeDiscoveryService()
    def get_node_public_keys(self, node_id: str) -> Dict[str, Any]:
        logger.info(f"获取节点 {node_id} 的公钥")
        cached_keys = self._get_cached_keys(node_id)
        if cached_keys:
            logger.info(f"从缓存获取节点 {node_id} 的公钥")
            return {
                'success': True,
                'kyber_public_key': cached_keys['kyber_public_key'],
                'falcon_public_key': cached_keys['falcon_public_key'],
                'source': 'cache'
            }
        blockchain_result = self.blockchain_service.get_node_info_from_blockchain(node_id)
        if blockchain_result.get('success'):
            kyber_key = blockchain_result.get('kyber_public_key')
            falcon_key = blockchain_result.get('falcon_public_key')
            kyber_key = decompress_key_data(kyber_key) if kyber_key else kyber_key
            falcon_key = decompress_key_data(falcon_key) if falcon_key else falcon_key
            self._cache_keys(node_id, kyber_key, falcon_key)
            logger.info(f"从区块链获取节点 {node_id} 的公钥")
            return {
                'success': True,
                'kyber_public_key': kyber_key,
                'falcon_public_key': falcon_key,
                'source': 'blockchain'
            }
        logger.warning(f"从区块链查询节点 {node_id} 失败，尝试从数据库查询")
        try:
            db_node = Node.objects.get(node_id=node_id)
            kyber_key = db_node.kyber_public_key
            falcon_key = db_node.falcon_public_key
            kyber_key = decompress_key_data(kyber_key) if kyber_key else kyber_key
            falcon_key = decompress_key_data(falcon_key) if falcon_key else falcon_key
            self._cache_keys(node_id, kyber_key, falcon_key)
            logger.info(f"从数据库获取节点 {node_id} 的公钥")
            return {
                'success': True,
                'kyber_public_key': kyber_key,
                'falcon_public_key': falcon_key,
                'source': 'database'
            }
        except Node.DoesNotExist:
            logger.error(f"节点 {node_id} 不存在")
            return {
                'success': False,
                'error': f'节点 {node_id} 不存在'
            }
        except Exception as e:
            logger.error(f"获取节点 {node_id} 公钥失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    def get_kyber_public_key(self, node_id: str) -> Optional[str]:
        result = self.get_node_public_keys(node_id)
        if result.get('success'):
            return result.get('kyber_public_key')
        return None
    def get_falcon_public_key(self, node_id: str) -> Optional[str]:
        result = self.get_node_public_keys(node_id)
        if result.get('success'):
            return result.get('falcon_public_key')
        return None
    def _cache_keys(self, node_id: str, kyber_key: str, falcon_key: str):
        self._cache[node_id] = {
            'kyber_public_key': kyber_key,
            'falcon_public_key': falcon_key,
            'timestamp': time.time()
        }
        logger.debug(f"缓存节点 {node_id} 的公钥")
    def _get_cached_keys(self, node_id: str) -> Optional[Dict[str, str]]:
        if node_id not in self._cache:
            return None
        cached_data = self._cache[node_id]
        cache_age = time.time() - cached_data['timestamp']
        if cache_age > self.CACHE_TTL:
            logger.debug(f"节点 {node_id} 的缓存已过期")
            del self._cache[node_id]
            return None
        return {
            'kyber_public_key': cached_data['kyber_public_key'],
            'falcon_public_key': cached_data['falcon_public_key']
        }
    def clear_cache(self, node_id: Optional[str] = None):
        if node_id:
            if node_id in self._cache:
                del self._cache[node_id]
                logger.info(f"清除节点 {node_id} 的缓存")
        else:
            self._cache.clear()
            logger.info("清除所有缓存")