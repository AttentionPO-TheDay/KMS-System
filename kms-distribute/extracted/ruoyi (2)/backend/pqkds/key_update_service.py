import logging
import base64
import time
from typing import Dict, Any
from django.db import transaction
from .models import Node
from .blockchain_service import BlockchainService
from .certificateless_falcon_v2 import CertificatelessFalconManagerV2
logger = logging.getLogger(__name__)
class KeyUpdateService:
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.blockchain_service = BlockchainService()
    def update_kyber_keys_only(self, security_level: int = 512) -> Dict[str, Any]:
        try:
            logger.info(f" 开始更新节点 {self.node_id} 的Kyber密钥对，安全级别: {security_level}")
            node = Node.objects.get(node_id=self.node_id)
            logger.info(f" 步骤1: 生成新的Kyber-{security_level}密钥对...")
            kyber_kem = RealKyberKEM(security_level)
            kyber_keypair_tuple = kyber_kem.keygen()
            if not kyber_keypair_tuple or len(kyber_keypair_tuple) != 2:
                return {
                    'success': False,
                    'message': f"Kyber-{security_level}密钥对生成失败"
                }
            kyber_public_key = kyber_keypair_tuple[0]
            kyber_private_key = kyber_keypair_tuple[1]
            logger.info(f" Kyber密钥对生成成功，公钥长度: {len(kyber_public_key)}, 私钥长度: {len(kyber_private_key)}")
            with transaction.atomic():
                node.kyber_public_key = base64.b64encode(kyber_public_key).decode('utf-8')
                node.kyber_private_key = base64.b64encode(kyber_private_key).decode('utf-8')
                node.kyber_security_level = security_level
                node.status = 'registered'
                node.save()
            logger.info(f" 步骤2: Kyber密钥已更新到数据库")
            logger.info(f" 步骤3: 上传新的Kyber公钥到区块链...")
            blockchain_result = self.blockchain_service.upload_kyber_public_key(
                self.node_id,
                kyber_public_key
            )
            if blockchain_result['success']:
                with transaction.atomic():
                    node.status = 'kyber_uploaded'
                    node.save()
                logger.info(f" Kyber公钥上传到区块链成功")
                blockchain_uploaded = True
            else:
                logger.warning(f" Kyber公钥上传到区块链失败: {blockchain_result.get('error', 'Unknown error')}")
                blockchain_uploaded = False
            return {
                'success': True,
                'message': f"Kyber-{security_level}密钥对更新成功",
                'data': {
                    'node_id': self.node_id,
                    'key_type': 'kyber',
                    'security_level': security_level,
                    'public_key_length': len(kyber_public_key),
                    'private_key_length': len(kyber_private_key),
                    'blockchain_uploaded': blockchain_uploaded,
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
            return {
                'success': False,
                'message': f"更新Kyber密钥失败: {str(e)}"
            }
    def update_falcon_keys_only(self, security_level: int = 512, falcon_version: str = 'v2') -> Dict[str, Any]:
        try:
            logger.info(f" 开始更新节点 {self.node_id} 的Falcon密钥对，安全级别: {security_level}，方案版本: {falcon_version}")
            if falcon_version not in ['v1', 'v2']:
                return {
                    'success': False,
                    'message': f"不支持的Falcon版本: {falcon_version}，仅支持 'v1' 或 'v2'"
                }
            node = Node.objects.get(node_id=self.node_id)
            if not node.kyber_public_key or not node.kyber_private_key:
                return {
                    'success': False,
                    'message': "节点缺少Kyber密钥，无法更新Falcon密钥"
                }
            logger.info(f" 步骤1: 清除旧的Falcon密钥数据...")
            with transaction.atomic():
                node.falcon_public_key = ''
                node.falcon_private_key = ''
                node.partial_key_received = False
                node.partial_key_data = ''
                node.falcon_security_level = security_level
                if node.status in ['falcon_generated', 'falcon_uploaded', 'falcon_v2_generated', 'falcon_v2_uploaded']:
                    node.status = 'kyber_uploaded'
                node.save()
            logger.info(f" 旧的Falcon密钥数据已清除")
            logger.info(f" 步骤2: KGC生成新的部分私钥...")
            try:
                kgc_service = KGCService(security_level)
                if not kgc_service.load_system_parameters("default"):
                    init_result = kgc_service.initialize_system("default")
                    if not init_result['success']:
                        return {
                            'success': False,
                            'message': f'KGC系统初始化失败: {init_result["message"]}'
                        }
                partial_key_result = kgc_service.process_node_registration(self.node_id)
                if not partial_key_result['success']:
                    return {
                        'success': False,
                        'message': f'KGC生成部分私钥失败: {partial_key_result["message"]}'
                    }
                logger.info(f" KGC生成部分私钥成功")
            except Exception as kgc_error:
                logger.error(f"KGC处理失败: {kgc_error}")
                return {
                    'success': False,
                    'message': f'KGC处理失败: {str(kgc_error)}'
                }
            logger.info(f" 步骤3: 生成新的Falcon密钥对...")
            node.refresh_from_db()
            if not node.partial_key_received or not node.partial_key_data:
                return {
                    'success': False,
                    'message': 'KGC部分私钥未接收到'
                }
            if falcon_version == 'v1':
                falcon_result = self._generate_falcon_keys_v1(node, security_level)
            else:
                falcon_result = self._generate_falcon_keys_v2(node, security_level)
            if not falcon_result['success']:
                return falcon_result
            logger.info(f" 步骤4: 上传新的Falcon公钥哈希到区块链...")
            node.refresh_from_db()
            if node.falcon_public_key:
                blockchain_result = self.blockchain_service.upload_falcon_public_key_hash(
                    self.node_id,
                    node.falcon_public_key
                )
                if blockchain_result['success']:
                    with transaction.atomic():
                        if falcon_version == 'v1':
                            node.status = 'falcon_uploaded'
                        else:
                            node.status = 'falcon_v2_uploaded'
                        node.save()
                    logger.info(f" Falcon公钥哈希上传到区块链成功")
                    blockchain_uploaded = True
                else:
                    logger.warning(f" Falcon公钥哈希上传到区块链失败")
                    blockchain_uploaded = False
            else:
                blockchain_uploaded = False
            return {
                'success': True,
                'message': f"Falcon-{security_level} {falcon_version.upper()}密钥对更新成功",
                'data': {
                    'node_id': self.node_id,
                    'key_type': 'falcon',
                    'falcon_version': falcon_version,
                    'security_level': security_level,
                    'public_key_length': len(node.falcon_public_key) if node.falcon_public_key else 0,
                    'private_key_length': len(node.falcon_private_key) if node.falcon_private_key else 0,
                    'blockchain_uploaded': blockchain_uploaded,
                    'status': node.status
                }
            }
        except Node.DoesNotExist:
            return {
                'success': False,
                'message': f"节点 {self.node_id} 不存在"
            }
        except Exception as e:
            logger.error(f"更新Falcon密钥失败: {e}")
            return {
                'success': False,
                'message': f"更新Falcon密钥失败: {str(e)}"
            }
    def _generate_falcon_keys_v1(self, node: Node, security_level: int) -> Dict[str, Any]:
        try:
            import json
            partial_key_data = json.loads(node.partial_key_data)
            kyber_ciphertext = base64.b64decode(partial_key_data['kyber_ciphertext'])
            encrypted_partial_key = base64.b64decode(partial_key_data['encrypted_partial_key'])
            nonce_tag = base64.b64decode(partial_key_data['nonce_tag'])
            from .real_crypto_with_fallback import RealKyberKEM, RealAESCipher, RealFalconSignature
            kyber_security_level = int(node.kyber_security_level) if node.kyber_security_level else 512
            kyber_kem = RealKyberKEM(kyber_security_level)
            kyber_private_key = base64.b64decode(node.kyber_private_key)
            kyber_shared_secret = kyber_kem.decaps(kyber_ciphertext, kyber_private_key)
            aes_cipher = RealAESCipher()
            partial_key_bytes = aes_cipher.decrypt(encrypted_partial_key, kyber_shared_secret, nonce_tag)
            falcon_signature = RealFalconSignature(security_level, force_dll=True)
            falcon_public_key, falcon_private_key = falcon_signature.keygen()
            logger.info(f" Falcon V1密钥对生成成功")
            logger.info(f"   公钥长度: {len(falcon_public_key)} 字节")
            logger.info(f"   私钥长度: {len(falcon_private_key)} 字节")
            with transaction.atomic():
                node.falcon_private_key = base64.b64encode(falcon_private_key).decode('utf-8')
                node.falcon_public_key = base64.b64encode(falcon_public_key).decode('utf-8')
                node.status = 'falcon_generated'
                node.save()
            logger.info(f" Falcon V1密钥对生成并保存成功")
            return {
                'success': True,
                'message': 'Falcon V1密钥对生成成功'
            }
        except Exception as e:
            logger.error(f"Falcon V1密钥生成失败: {e}")
            return {
                'success': False,
                'message': f'Falcon V1密钥生成失败: {str(e)}'
            }
    def _generate_falcon_keys_v2(self, node: Node, security_level: int) -> Dict[str, Any]:
        try:
            if not node.partial_key_data:
                return {
                    'success': False,
                    'message': '节点缺少部分私钥数据，请先从KGC获取'
                }
            import json
            try:
                partial_key_data = json.loads(node.partial_key_data)
            except json.JSONDecodeError as e:
                return {
                    'success': False,
                    'message': f'部分私钥数据格式错误: {str(e)}'
                }
            required_fields = ['kyber_ciphertext', 'encrypted_partial_key', 'nonce_tag']
            for field in required_fields:
                if field not in partial_key_data:
                    return {
                        'success': False,
                        'message': f'部分私钥数据缺少字段: {field}'
                    }
            kyber_ciphertext = base64.b64decode(partial_key_data['kyber_ciphertext'])
            encrypted_partial_key = base64.b64decode(partial_key_data['encrypted_partial_key'])
            nonce_tag = base64.b64decode(partial_key_data['nonce_tag'])
            from .real_crypto_with_fallback import RealKyberKEM, RealAESCipher
            if not node.kyber_private_key:
                return {
                    'success': False,
                    'message': '节点缺少Kyber私钥，无法解密部分私钥'
                }
            kyber_security_level = int(node.kyber_security_level) if node.kyber_security_level else 512
            kyber_kem = RealKyberKEM(kyber_security_level)
            kyber_private_key = base64.b64decode(node.kyber_private_key)
            try:
                kyber_shared_secret = kyber_kem.decaps(kyber_ciphertext, kyber_private_key)
            except Exception as e:
                return {
                    'success': False,
                    'message': f'Kyber解密失败: {str(e)}'
                }
            aes_cipher = RealAESCipher()
            try:
                partial_key_bytes = aes_cipher.decrypt(encrypted_partial_key, kyber_shared_secret, nonce_tag)
            except Exception as e:
                return {
                    'success': False,
                    'message': f'AES解密部分私钥失败: {str(e)}'
                }
            try:
                falcon_manager = CertificatelessFalconManagerV2(security_level)
                init_result = falcon_manager.initialize_system()
                if not init_result['success']:
                    return {
                        'success': False,
                        'message': f'Falcon V2系统初始化失败: {init_result["message"]}'
                    }
            except Exception as e:
                return {
                    'success': False,
                    'message': f'Falcon V2管理器初始化失败: {str(e)}'
                }
            try:
                falcon_keypair_result = falcon_manager.generate_keypair(self.node_id)
            except Exception as e:
                return {
                    'success': False,
                    'message': f'Falcon密钥对生成异常: {str(e)}'
                }
            if not falcon_keypair_result['success']:
                return {
                    'success': False,
                    'message': f'Falcon密钥对生成失败: {falcon_keypair_result["message"]}'
                }
            if 'falcon_private_key' not in falcon_keypair_result or 'falcon_public_key' not in falcon_keypair_result:
                return {
                    'success': False,
                    'message': 'Falcon密钥对生成失败：缺少必要的密钥字段'
                }
            with transaction.atomic():
                node.falcon_private_key = falcon_keypair_result['falcon_private_key']
                node.falcon_public_key = falcon_keypair_result['falcon_public_key']
                node.status = 'falcon_v2_generated'
                node.save()
            logger.info(f" Falcon V2密钥对生成并保存成功")
            return {
                'success': True,
                'message': 'Falcon密钥对生成成功'
            }
        except Exception as e:
            logger.error(f"生成Falcon V2密钥对失败: {e}")
            return {
                'success': False,
                'message': f'生成Falcon密钥对失败: {str(e)}'
            }
    def update_both_keys(self, kyber_security_level: int = 512, falcon_security_level: int = 512, falcon_version: str = 'v2') -> Dict[str, Any]:
        try:
            logger.info(f" 开始同时更新节点 {self.node_id} 的Kyber和Falcon密钥对")
            logger.info(f"   Kyber安全级别: {kyber_security_level}")
            logger.info(f"   Falcon安全级别: {falcon_security_level}")
            logger.info(f" 步骤1: 更新Kyber密钥对...")
            kyber_result = self.update_kyber_keys_only(kyber_security_level)
            if not kyber_result['success']:
                return {
                    'success': False,
                    'message': f"Kyber密钥更新失败: {kyber_result['message']}"
                }
            logger.info(f" 步骤1完成: Kyber密钥更新成功")
            logger.info(f" 步骤2: 更新Falcon密钥对...")
            import time
            time.sleep(1)
            falcon_result = self.update_falcon_keys_only(falcon_security_level, falcon_version)
            if not falcon_result['success']:
                return {
                    'success': False,
                    'message': f"Falcon密钥更新失败: {falcon_result['message']}"
                }
            logger.info(f" 步骤2完成: Falcon密钥更新成功")
            node = Node.objects.get(node_id=self.node_id)
            return {
                'success': True,
                'message': f"Kyber-{kyber_security_level}和Falcon-{falcon_security_level} {falcon_version.upper()}密钥对同时更新成功",
                'data': {
                    'node_id': self.node_id,
                    'key_type': 'both',
                    'kyber_security_level': kyber_security_level,
                    'falcon_security_level': falcon_security_level,
                    'falcon_version': falcon_version,
                    'kyber_data': kyber_result['data'],
                    'falcon_data': falcon_result['data'],
                    'final_status': node.status
                }
            }
        except Exception as e:
            logger.error(f"同时更新密钥失败: {e}")
            return {
                'success': False,
                'message': f"同时更新密钥失败: {str(e)}"
            }