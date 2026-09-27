import hashlib
import logging
from typing import Dict, Any, List
from django.db import transaction
from django.utils import timezone
from .models import Node
from .blockchain_service import BlockchainService
logger = logging.getLogger(__name__)
class DatabaseToBlockchainSyncService:
    def __init__(self):
        self.blockchain_service = BlockchainService()
        self.hash_threshold = 1024 * 1024
    def sync_all_nodes_to_blockchain(self) -> Dict[str, Any]:
        try:
            logger.info("=" * 60)
            logger.info("Starting full sync from database to blockchain")
            logger.info("=" * 60)
            from .models import BlockchainConfig
            active_blockchain_config = (
                BlockchainConfig.objects.filter(is_active=True)
                .order_by('-update_datetime', '-create_datetime', '-id')
                .first()
            )
            if not active_blockchain_config:
                logger.error("No active blockchain configuration found")
                return {
                    'success': False,
                    'message': 'No active blockchain configuration',
                    'synced_nodes': [],
                    'failed_nodes': []
                }
            logger.info(f"Using active blockchain config: {active_blockchain_config.name}")
            try:
                self.blockchain_service._ensure_contract_ready()
                logger.info("Blockchain connection is normal")
            except Exception as e:
                logger.error(f"Blockchain connection failed: {e}")
                return {
                    'success': False,
                    'message': f'Blockchain connection failed: {str(e)}',
                    'synced_nodes': [],
                    'failed_nodes': []
                }
            all_nodes = Node.objects.all()
            total_count = all_nodes.count()
            if total_count == 0:
                logger.warning("No nodes in database, no sync needed")
                return {
                    'success': True,
                    'message': 'No nodes in database',
                    'synced_nodes': [],
                    'failed_nodes': [],
                    'total_count': 0
                }
            logger.info(f"Found {total_count} nodes, starting sync to blockchain...")
            synced_nodes = []
            failed_nodes = []
            for index, node in enumerate(all_nodes, 1):
                logger.info(f"[{index}/{total_count}] Syncing node: {node.node_id}")
                try:
                    if node.blockchain_config != active_blockchain_config:
                        node.blockchain_config = active_blockchain_config
                        node.save(update_fields=['blockchain_config'])
                        logger.info(f"  Node associated with blockchain config: {active_blockchain_config.name}")
                    sync_result = self._sync_single_node_to_blockchain(node, active_blockchain_config)
                    if sync_result['success']:
                        synced_nodes.append({
                            'node_id': node.node_id,
                            'name': node.name,
                            'status': 'synced',
                            'details': sync_result.get('details')
                        })
                        logger.info(f"  Node {node.node_id} sync successful")
                    else:
                        failed_nodes.append({
                            'node_id': node.node_id,
                            'name': node.name,
                            'status': 'failed',
                            'error': sync_result.get('message')
                        })
                        logger.error(f"  Node {node.node_id} sync failed: {sync_result.get('message')}")
                except Exception as e:
                    failed_nodes.append({
                        'node_id': node.node_id,
                        'name': node.name,
                        'status': 'error',
                        'error': str(e)
                    })
                    logger.error(f"  Node {node.node_id} sync error: {e}")
            logger.info("=" * 60)
            logger.info(f"Sync completed: {len(synced_nodes)} succeeded, {len(failed_nodes)} failed")
            logger.info("=" * 60)
            return {
                'success': len(failed_nodes) == 0,
                'message': f'同步完成: 成功{len(synced_nodes)}个, 失败{len(failed_nodes)}个',
                'synced_nodes': synced_nodes,
                'failed_nodes': failed_nodes,
                'total_count': total_count,
                'synced_count': len(synced_nodes),
                'failed_count': len(failed_nodes)
            }
        except Exception as e:
            logger.error(f"Database to blockchain sync failed: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': f'Sync failed: {str(e)}',
                'synced_nodes': [],
                'failed_nodes': [],
                'error_details': str(e)
            }
    def _sync_single_node_to_blockchain(self, node: Node, active_blockchain_config=None) -> Dict[str, Any]:
        try:
            details = {
                'node_id': node.node_id,
                'name': node.name,
                'registration': False,
                'kyber_upload': False,
                'falcon_upload': False
            }
            logger.info(f"  [1/4] Registering node basic info...")
            node_registered = False
            try:
                node_exists = self.blockchain_service.contract.functions.nodeExists(node.node_id).call()
                if node_exists:
                    logger.info(f"    Node already registered on blockchain, skipping registration")
                    details['registration'] = 'skipped'
                    node_registered = True
                else:
                    logger.info(f"    Registering node on blockchain...")
                    register_result = self.blockchain_service.register_node_on_blockchain(
                        node.node_id,
                        node.name,
                        node.ip_address,
                        node.port
                    )
                    if not register_result['success']:
                        return {
                            'success': False,
                            'message': f'Node registration failed: {register_result.get("error")}',
                            'details': details
                        }
                    details['registration'] = 'registered'
                    node_registered = True
                    logger.info(f"    Node registration successful")
            except Exception as e:
                logger.error(f"    Error checking/registering node: {e}")
                logger.info(f"    Attempting to register node...")
                register_result = self.blockchain_service.register_node_on_blockchain(
                    node.node_id,
                    node.name,
                    node.ip_address,
                    node.port
                )
                if not register_result['success']:
                    if 'already registered' in str(register_result.get('error', '')).lower():
                        logger.info(f"    Node already registered (detected from error)")
                        details['registration'] = 'skipped'
                        node_registered = True
                    else:
                        return {
                            'success': False,
                            'message': f'Node registration failed: {register_result.get("error")}',
                            'details': details
                        }
                else:
                    details['registration'] = 'registered'
                    node_registered = True
                    logger.info(f"    Node registration successful")
            if not node_registered:
                return {
                    'success': False,
                    'message': 'Node must be registered before uploading keys',
                    'details': details
                }
            logger.info(f"  [2/4] Uploading Kyber public key...")
            if node.kyber_public_key:
                kyber_result = self._upload_kyber_key_with_hash_check(node)
                if not kyber_result['success']:
                    logger.warning(f"    Kyber public key upload failed: {kyber_result.get('message')}")
                else:
                    details['kyber_upload'] = kyber_result.get('method')
                    logger.info(f"    Kyber public key upload successful ({kyber_result.get('method')})")
            else:
                logger.warning(f"    Node has no Kyber public key")
            logger.info(f"  [3/4] Uploading Falcon public key...")
            if node.falcon_public_key:
                falcon_result = self._upload_falcon_key_with_hash_check(node)
                if not falcon_result['success']:
                    logger.warning(f"    Falcon public key upload failed: {falcon_result.get('message')}")
                else:
                    details['falcon_upload'] = falcon_result.get('method')
                    logger.info(f"    Falcon public key upload successful ({falcon_result.get('method')})")
            else:
                logger.warning(f"    Node has no Falcon public key")
            logger.info(f"  [4/4] Updating node status...")
            with transaction.atomic():
                node.blockchain_synced = True
                node.blockchain_sync_time = timezone.now()
                node.save(update_fields=['blockchain_synced', 'blockchain_sync_time'])
            logger.info(f"     状态更新完成")
            return {
                'success': True,
                'message': f'节点{node.node_id}同步成功',
                'details': details
            }
        except Exception as e:
            logger.error(f"   节点{node.node_id}同步失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': f'节点同步失败: {str(e)}',
                'details': details if 'details' in locals() else {}
            }
    def _upload_kyber_key_with_hash_check(self, node: Node) -> Dict[str, Any]:
        try:
            kyber_key = node.kyber_public_key
            kyber_size = len(kyber_key.encode() if isinstance(kyber_key, str) else kyber_key)
            logger.info(f"     Kyber公钥大小: {kyber_size} 字节")
            if kyber_size < self.hash_threshold:
                logger.info(f"     直接上链Kyber公钥")
                result = self.blockchain_service.upload_kyber_public_key(
                    node.node_id,
                    kyber_key.encode() if isinstance(kyber_key, str) else kyber_key
                )
                if result['success']:
                    return {
                        'success': True,
                        'method': 'direct',
                        'message': 'Kyber公钥直接上链'
                    }
                else:
                    return {
                        'success': False,
                        'method': 'direct',
                        'message': result.get('error', '上链失败')
                    }
            else:
                logger.info(f"     Kyber公钥过大，上链哈希值")
                kyber_hash = hashlib.sha256(
                    kyber_key.encode() if isinstance(kyber_key, str) else kyber_key
                ).hexdigest()
                result = self.blockchain_service.upload_kyber_public_key_hash(
                    node.node_id,
                    kyber_hash
                )
                if result['success']:
                    return {
                        'success': True,
                        'method': 'hash',
                        'hash': kyber_hash,
                        'message': f'Kyber公钥哈希值上链: {kyber_hash[:16]}...'
                    }
                else:
                    return {
                        'success': False,
                        'method': 'hash',
                        'message': result.get('error', '哈希上链失败')
                    }
        except Exception as e:
            logger.error(f"     Kyber公钥上传失败: {e}")
            return {
                'success': False,
                'message': str(e)
            }
    def _upload_falcon_key_with_hash_check(self, node: Node) -> Dict[str, Any]:
        try:
            falcon_key = node.falcon_public_key
            falcon_size = len(falcon_key.encode() if isinstance(falcon_key, str) else falcon_key)
            logger.info(f"     Falcon公钥大小: {falcon_size} 字节")
            if falcon_size < self.hash_threshold:
                logger.info(f"     直接上链Falcon公钥")
                result = self.blockchain_service.upload_falcon_public_key(
                    node.node_id,
                    falcon_key.encode() if isinstance(falcon_key, str) else falcon_key
                )
                if result['success']:
                    return {
                        'success': True,
                        'method': 'direct',
                        'message': 'Falcon公钥直接上链'
                    }
                else:
                    return {
                        'success': False,
                        'method': 'direct',
                        'message': result.get('error', '上链失败')
                    }
            else:
                logger.info(f"     Falcon公钥过大，上链哈希值")
                falcon_hash = hashlib.sha256(
                    falcon_key.encode() if isinstance(falcon_key, str) else falcon_key
                ).hexdigest()
                result = self.blockchain_service.upload_falcon_public_key_hash(
                    node.node_id,
                    falcon_hash
                )
                if result['success']:
                    return {
                        'success': True,
                        'method': 'hash',
                        'hash': falcon_hash,
                        'message': f'Falcon公钥哈希值上链: {falcon_hash[:16]}...'
                    }
                else:
                    return {
                        'success': False,
                        'method': 'hash',
                        'message': result.get('error', '哈希上链失败')
                    }
        except Exception as e:
            logger.error(f"     Falcon公钥上传失败: {e}")
            return {
                'success': False,
                'message': str(e)
            }