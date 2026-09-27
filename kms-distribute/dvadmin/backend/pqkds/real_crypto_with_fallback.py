import os
import logging
import base64
import json
import zlib
import hashlib
import numpy as np
from typing import Tuple, Dict, Any, Optional
from pathlib import Path

# 载荷层：新数据用国密 SM4（16 字节），历史数据按密钥长度/信封标记回退 AES-256（决策 D3）
from .sm4_crypto import PAYLOAD_ALGORITHM_SM4, PayloadCipher
logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent.parent
FALCON_512_DLL = BASE_DIR / "falcon" / "falcon512.dll"
FALCON_1024_DLL = BASE_DIR / "falcon" / "falcon1024.dll"
KYBER_512_DLL = BASE_DIR / "kyber" / "libpqcrystals_kyber512_ref.dll"
KYBER_768_DLL = BASE_DIR / "kyber" / "libpqcrystals_kyber768_ref.dll"
KYBER_1024_DLL = BASE_DIR / "kyber" / "libpqcrystals_kyber1024_ref.dll"
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
class RealKyberKEM:
    def __init__(self, security_level=512, force_dll=False):
        self.security_level = security_level
        self.use_dll = False
        self.dll_impl = None
        self.demo_impl = None
        self.fusion = None
        try:
            from .certificateless_kyber_dll_fusion import get_fusion_instance
            self.fusion = get_fusion_instance(variant=int(security_level))
            self.use_dll = True
            logger.info(f" Kyber无证书+DLL融合实现加载成功 (安全级别: {security_level})")
            logger.info(f"   公钥长度: {self.fusion.pk_bytes} 字节")
            logger.info(f"   私钥长度: {self.fusion.sk_bytes} 字节")
        except Exception as e:
            logger.warning(f" 融合模块加载失败，尝试直接DLL: {e}")
            try:
                from .crypto_utils import KyberCrypto
                self.dll_impl = KyberCrypto(security_level)
                self.use_dll = True
                logger.info(f" Kyber DLL实现加载成功 (安全级别: {security_level})")
            except Exception as e2:
                if force_dll:
                    logger.error(f" 强制要求使用Kyber DLL但加载失败: {e2}")
                    raise RuntimeError(f"Kyber DLL加载失败: {e2}")
                else:
                    logger.warning(f" Kyber DLL加载失败，回退到演示版本: {e2}")
                    from .demo_crypto import DemoKyberKEM
                    self.demo_impl = DemoKyberKEM(security_level)
                    self.use_dll = False
    def keygen(self) -> Tuple[bytes, bytes]:
        if self.fusion:
            # 使用融合模块：无证书密钥生成 + DLL keypair_derand
            import uuid
            user_id = f"kem_user_{uuid.uuid4().hex[:12]}"
            result = self.fusion.generate_certificateless_keypair(user_id)
            return result['kyber_public_key'], result['kyber_private_key']
        elif self.use_dll:
            return self.dll_impl.generate_keypair()
        else:
            return self.demo_impl.keygen()
    def encaps(self, public_key: bytes) -> Tuple[bytes, bytes]:
        if self.fusion:
            return self.fusion.encaps(public_key)
        elif self.use_dll:
            return self.dll_impl.encrypt(public_key)
        else:
            return self.demo_impl.encaps(public_key)
    def decaps(self, ciphertext: bytes, private_key: bytes) -> bytes:
        if self.fusion:
            return self.fusion.decaps(ciphertext, private_key)
        elif self.use_dll:
            return self.dll_impl.decrypt(ciphertext, private_key)
        else:
            return self.demo_impl.decaps(ciphertext, private_key)
class RealFalconSignature:
    def __init__(self, security_level=512, force_dll=False):
        self.security_level = security_level
        self.use_dll = False
        self.dll_impl = None
        self.demo_impl = None
        try:
            from .crypto_utils import FalconCrypto
            self.dll_impl = FalconCrypto(security_level)
            self.use_dll = True
            logger.info(f" Falcon DLL实现加载成功 (安全级别: {security_level})")
        except Exception as e:
            if force_dll:
                logger.error(f" 强制要求使用Falcon DLL但加载失败: {e}")
                raise RuntimeError(f"Falcon DLL加载失败: {e}")
            else:
                logger.warning(f" Falcon DLL加载失败，回退到演示版本: {e}")
                from .demo_crypto import DemoFalconSignature
                self.demo_impl = DemoFalconSignature(security_level)
                self.use_dll = False
    def keygen(self) -> Tuple[bytes, bytes]:
        if self.use_dll:
            return self.dll_impl.generate_keypair()
        else:
            return self.demo_impl.keygen()
    def sign(self, message: bytes, private_key: bytes) -> bytes:
        if self.use_dll:
            return self.dll_impl.sign(message, private_key)
        else:
            return self.demo_impl.sign(message, private_key)
    def verify(self, signature: bytes, message: bytes, public_key: bytes) -> bool:
        if self.use_dll:
            verified_message = self.dll_impl.verify(signature, public_key)
            return verified_message == message
        else:
            return self.demo_impl.verify(signature, message, public_key)
class RealAESCipher:
    """载荷加解密（历史类名保留，实现已随 D3 切到 SM4）。

    `crypto_utils.AESCrypto` 已改为委托 `sm4_crypto.PayloadCipher`：
    16 字节密钥走 SM4-GCM，32 字节走历史 AES-256-GCM。因此本类无需单独改动，
    但名字已名不副实 —— 新代码请直接用 `PayloadCipher`。
    """

    def __init__(self):
        pass
    def encrypt(self, data: bytes, key: bytes) -> Tuple[bytes, bytes]:
        from .crypto_utils import AESCrypto
        aes = AESCrypto()
        return aes.encrypt(data, key)
    def decrypt(self, ciphertext: bytes, key: bytes, nonce_tag: bytes) -> bytes:
        from .crypto_utils import AESCrypto
        aes = AESCrypto()
        return aes.decrypt(ciphertext, key, nonce_tag)
class CertificatelessKyberV2Wrapper:
    def __init__(self, security_level: int = 512):
        self.security_level = int(security_level) if security_level else 512
        try:
            from .certificateless_kyber_v2 import CertificatelessKyberManagerV2
            self.kyber_manager = CertificatelessKyberManagerV2(security_level=self.security_level)
            init_result = self.kyber_manager.initialize_system()
            if not init_result['success']:
                logger.warning(f"Kyber V2系统初始化失败: {init_result['message']}")
            logger.info(f"Kyber V2系统初始化成功，安全级别: {self.security_level}")
        except Exception as e:
            logger.error(f"无法加载Kyber V2: {e}")
            raise RuntimeError(f"Kyber V2加载失败: {e}")
class BlockchainBasedCertificatelessFalcon:
    def __init__(self, security_level=512, kyber_security_level=None, force_real_crypto=True):
        self.security_level = int(security_level) if security_level else 512
        if kyber_security_level is not None:
            self.kyber_security_level = int(kyber_security_level) if kyber_security_level else 512
        else:
            self.kyber_security_level = self.security_level
        logger.info(f" BlockchainBasedCertificatelessFalcon初始化:")
        logger.info(f"   Falcon安全级别: {self.security_level}")
        logger.info(f"   Kyber安全级别: {self.kyber_security_level}")
        logger.info(f"   强制真实密码学: {force_real_crypto}")
        if force_real_crypto:
            self.kyber = RealKyberKEM(self.kyber_security_level, force_dll=True)
            self.falcon = RealFalconSignature(self.security_level, force_dll=True)
        else:
            self.kyber = RealKyberKEM(self.kyber_security_level)
            self.falcon = RealFalconSignature(self.security_level)
        self.aes = RealAESCipher()
        crypto_type = "真实DLL" if force_real_crypto else "带回退"
        logger.info(f"基于区块链的无证书Falcon系统V2初始化完成 (安全级别: {self.security_level}, 密码学类型: {crypto_type})")
    def node_registration_phase(self, node_id: str, node_info: Dict[str, Any]) -> Dict[str, Any]:
        try:
            import time
            import base64
            start_time = time.time()
            logger.info(f" 开始节点注册阶段（无证书Kyber+DLL融合方案）: {node_id}")
            keygen_start = time.time()
            logger.info(f"  生成无证书Kyber-{self.kyber_security_level} DLL融合密钥对...")
            public_key, private_key = self.kyber.keygen()
            keygen_time = time.time() - keygen_start
            logger.info(f"  无证书Kyber密钥对生成成功")
            logger.info(f"    原始公钥长度: {len(public_key)} bytes")
            logger.info(f"    原始私钥长度: {len(private_key)} bytes")
            kyber_public_key_b64 = base64.b64encode(public_key).decode('utf-8')
            kyber_private_key_b64 = base64.b64encode(private_key).decode('utf-8')
            total_time = time.time() - start_time
            logger.info(f"  Kyber密钥Base64编码后:")
            logger.info(f"    公钥长度: {len(kyber_public_key_b64)} chars")
            logger.info(f"    私钥长度: {len(kyber_private_key_b64)} chars")
            logger.info(f"   ⏱️  密钥生成耗时: {keygen_time:.4f}秒")
            logger.info(f"   ⏱️  总耗时: {total_time:.4f}秒")
            from django.utils import timezone
            blockchain_data = {
                'node_id': node_id,
                'kyber_public_key': kyber_public_key_b64,
                'node_info': node_info,
                'registration_time': str(timezone.now()),
                'algorithm': f'CertificatelessKyber{self.kyber_security_level}_DLL'
            }
            return {
                'success': True,
                'kyber_public_key': kyber_public_key_b64,
                'kyber_private_key': kyber_private_key_b64,
                'blockchain_data': blockchain_data,
                'algorithm': f'CertificatelessKyber{self.kyber_security_level}_DLL',
                'generation_time': {
                    'keygen': round(keygen_time, 4),
                    'total': round(total_time, 4)
                },
                'key_sizes': {
                    'public_key': len(public_key),
                    'private_key': len(private_key),
                    'public_key_b64': len(kyber_public_key_b64),
                    'private_key_b64': len(kyber_private_key_b64)
                },
                'message': f'无证书Kyber-{self.kyber_security_level}密钥对生成成功（耗时{total_time:.3f}秒）'
            }
        except Exception as e:
            logger.error(f" 节点注册阶段失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': f'节点注册失败: {str(e)}'
            }
    def kgc_partial_key_generation(self, node_id: str, kyber_public_key: str) -> Dict[str, Any]:
        try:
            logger.info(f" KGC开始为节点 {node_id} 生成部分私钥")
            logger.warning("该方法已废弃，Falcon部分私钥现由FalconAESSessionKeyEncryption直接生成")
            return {'success': False, 'message': '方法已废弃'}
        except Exception as e:
            logger.error(f" 部分私钥生成失败: {e}")
            return {'success': False, 'message': str(e)}
    def kgc_partial_key_generation_v2(self, node_id: str, kyber_public_key: str) -> Dict[str, Any]:
        logger.warning("kgc_partial_key_generation_v2已废弃，请使用FalconAESSessionKeyEncryption")
        return {'success': False, 'message': '方法已废弃'}
    def node_falcon_key_generation_v2(self, node_id: str, kyber_private_key: str, encrypted_package: str) -> Dict[str, Any]:
        logger.warning("node_falcon_key_generation_v2已废弃")
        return {'success': False, 'message': '方法已废弃'}
    def _verify_falcon_signature(self, signature: bytes, message: bytes, public_key: str) -> bool:
        try:
            logger.info(f" 开始验证Falcon签名，签名长度: {len(signature)}")
            public_key_bytes = base64.b64decode(public_key)
            try:
                public_key_str = public_key_bytes.decode('utf-8')
                public_key_data = json.loads(public_key_str)
                if public_key_data.get('algorithm') in ['CertificatelessFalcon', 'CertificatelessFalconV2']:
                    logger.info("检测到无证书Falcon公钥，使用无证书验证系统")
                    signature_for_verification = signature
                    if isinstance(signature, bytes) and len(signature) == 16384:
                        logger.info("检测到V2方案bytes格式签名，转换为数组格式")
                        import numpy as np
                        signature_for_verification = np.frombuffer(signature, dtype=np.float64)
                        logger.info(f"签名转换完成，数组长度: {len(signature_for_verification)}")
                    verify_result = self.certificateless_v2.verify_signature(
                        message, signature_for_verification, public_key_data
                    )
                    return verify_result.get('success', False)
                elif 'h' in public_key_data and isinstance(public_key_data['h'], list):
                    logger.info("检测到标准Falcon公钥（JSON格式）")
                    import numpy as np
                    h_array = np.array(public_key_data['h'], dtype=np.uint16)
                    falcon_pk_bytes = h_array.tobytes()
                    expected_pk_len = self.falcon.dll_impl.public_key_bytes if hasattr(self.falcon, 'dll_impl') else 897
                    if len(falcon_pk_bytes) != expected_pk_len:
                        if len(falcon_pk_bytes) < expected_pk_len:
                            falcon_pk_bytes = falcon_pk_bytes + b'\x00' * (expected_pk_len - len(falcon_pk_bytes))
                        else:
                            falcon_pk_bytes = falcon_pk_bytes[:expected_pk_len]
                    return self.falcon.verify(signature, message, falcon_pk_bytes)
                else:
                    logger.warning("无法识别的Falcon公钥格式")
                    return False
            except (UnicodeDecodeError, json.JSONDecodeError):
                logger.info("检测到二进制格式的Falcon公钥")
                public_key_size = len(public_key_bytes)
                logger.info(f" Falcon公钥大小: {public_key_size} 字节")
                if public_key_size > 100000:
                    logger.info("检测到V2方案大型公钥，使用V2验证方法")
                    try:
                        import numpy as np
                        import io
                        with io.BytesIO(public_key_bytes) as f:
                            loaded_data = np.load(f, allow_pickle=True)
                            if isinstance(loaded_data, np.ndarray):
                                falcon_pk_array = loaded_data
                            else:
                                falcon_pk_array = list(loaded_data.values())[0]
                        logger.info(f" V2公钥解压成功，形状: {falcon_pk_array.shape}")
                        pk_shape = falcon_pk_array.shape
                        if pk_shape == (512, 1024):
                            v2_security_level = 1024
                        elif pk_shape == (256, 512):
                            v2_security_level = 512
                        else:
                            v2_security_level = self.security_level
                        logger.info(f" 根据公钥形状 {pk_shape} 确定V2安全级别: {v2_security_level}")
                        signature_for_verification = signature
                        if isinstance(signature, bytes) and len(signature) == 16384:
                            logger.info("检测到V2方案bytes格式签名，转换为数组格式")
                            signature_for_verification = np.frombuffer(signature, dtype=np.float64)
                            logger.info(f"签名转换完成，数组长度: {len(signature_for_verification)}")
                        from .certificateless_falcon_v2 import CertificatelessFalconV2
                        falcon_v2_temp = CertificatelessFalconV2(v2_security_level)
                        verify_result = falcon_v2_temp.verify(
                            signature_for_verification, message, falcon_pk_array
                        )
                        logger.info(f" V2方案验证完成，安全级别: {v2_security_level}, 结果: {verify_result}")
                        return verify_result
                    except Exception as v2_error:
                        logger.error(f" V2方案验证失败: {v2_error}")
                        return False
                else:
                    return self.falcon.verify(signature, message, public_key_bytes)
        except Exception as e:
            logger.error(f" Falcon签名验证异常: {e}")
            return False
    def _normalize_falcon_public_key(self, public_key_data: str) -> str:
        import base64
        import json
        if not public_key_data:
            raise ValueError("Falcon公钥数据为空")
        try:
            decoded = base64.b64decode(public_key_data)
            if len(decoded) in [897, 1793]:
                logger.info(f" Falcon公钥已是标准Base64格式，长度: {len(decoded)}字节")
                return public_key_data
            try:
                json_data = json.loads(decoded.decode('utf-8'))
                if isinstance(json_data, dict):
                    if 'falcon_pk_real' in json_data and json_data['falcon_pk_real']:
                        logger.info(f" 从JSON提取标准Falcon公钥成功（falcon_pk_real字段）")
                        return json_data['falcon_pk_real']
                    if 'public_key' in json_data:
                        pk_list = json_data['public_key']
                        pk_json_str = json.dumps(pk_list)
                        pk_bytes = base64.b64encode(pk_json_str.encode()).decode('utf-8')
                        logger.info(f" Falcon公钥从矩阵JSON格式标准化成功")
                        return pk_bytes
            except Exception as e:
                logger.warning(f" JSON解析失败: {e}，继续尝试其他格式")
        except Exception as e:
            logger.warning(f" Base64解码失败: {e}，继续尝试其他格式")
        try:
            json_data = json.loads(public_key_data)
            if isinstance(json_data, dict):
                if 'falcon_pk_real' in json_data and json_data['falcon_pk_real']:
                    logger.info(f" 从JSON字符串提取标准Falcon公钥成功")
                    return json_data['falcon_pk_real']
                if 'public_key' in json_data:
                    pk_list = json_data['public_key']
                    pk_json_str = json.dumps(pk_list)
                    pk_bytes = base64.b64encode(pk_json_str.encode()).decode('utf-8')
                    logger.info(f" Falcon公钥从矩阵JSON字符串标准化成功")
                    return pk_bytes
        except Exception as e:
            logger.warning(f" 直接JSON解析失败: {e}")
        logger.warning(f" 无法完全标准化Falcon公钥格式，将使用原始数据（长度: {len(public_key_data)}）")
        return public_key_data
    def session_key_exchange_send(self, sender_falcon_sk: str, receiver_falcon_pk: str,
                                  receiver_id: str = "receiver_node") -> Dict[str, Any]:
        try:
            logger.info(f" [Falcon] 开始会话密钥交换发送阶段（使用严格无证书Falcon）")
            import os
            import base64
            import json
            from .falcon_aes_session_encryption import FalconAESSessionKeyEncryption
            if not receiver_falcon_pk:
                logger.error(f" [Falcon] 接收方Falcon公钥为空")
                return {
                    'success': False,
                    'message': '接收方Falcon公钥为空'
                }
            logger.info(f" [Falcon] 接收方公钥长度: {len(receiver_falcon_pk)} 字符")
            # 会话密钥 = 载荷密钥：D3 后是 SM4 的 16 字节（原为 AES-256 的 32 字节）
            session_key = PayloadCipher.generate_key()
            logger.info(f" [Falcon] SM4 会话密钥生成成功，长度: {len(session_key)}")
            # 自动从公钥中检测安全级别
            falcon_service = FalconAESSessionKeyEncryption()
            enc_result = falcon_service.encrypt_aes_key_with_falcon(
                receiver_id,
                session_key,
                receiver_falcon_pk
            )
            if not enc_result['success']:
                logger.error(f" [Falcon] 会话密钥加密失败: {enc_result['message']}")
                return {
                    'success': False,
                    'message': f'会话密钥加密失败: {enc_result["message"]}'
                }
            security_level = enc_result.get('security_level', 512)
            session_key_package = {
                'ciphertext': enc_result['ciphertext'],
                'encryption_method': 'Falcon_Certificateless_Enc',
                'algorithm': f'CertificatelessFalcon-{security_level}',
                'security_level': security_level
            }
            logger.info(f" [Falcon] 会话密钥交换包生成完成 (Falcon-{security_level})")
            return {
                'success': True,
                'session_key_package': session_key_package,
                'session_key': base64.b64encode(session_key).decode('utf-8'),
                'message': f'会话密钥交换包生成成功 (Falcon-{security_level})'
            }
        except Exception as e:
            logger.error(f" [Falcon] 会话密钥交换发送失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': f'会话密钥交换失败: {str(e)}'
            }
    def session_key_exchange_receive(self, receiver_falcon_sk: str, sender_node_id: str,
                    session_key_package: Dict[str, Any]) -> Dict[str, Any]:
        try:
            logger.info(f" [Falcon] 开始会话密钥交换接收阶段（使用严格无证书Falcon）")
            import base64
            from .falcon_aes_session_encryption import FalconAESSessionKeyEncryption
            if 'ciphertext' not in session_key_package:
                logger.error(f" [Falcon] 会话密钥交换包格式错误，缺少密文数据")
                return {
                    'success': False,
                    'message': '会话密钥交换包格式错误'
                }
            # 从包中获取安全级别
            security_level = session_key_package.get('security_level', 512)
            falcon_service = FalconAESSessionKeyEncryption(security_level=security_level)
            receiver_falcon_sk = decompress_key_data(receiver_falcon_sk)
            dec_result = falcon_service.decrypt_aes_key_with_falcon(
                session_key_package['ciphertext'],
                receiver_falcon_sk
            )
            if not dec_result['success']:
                logger.error(f" [Falcon] 会话密钥解密失败: {dec_result['message']}")
                return {
                    'success': False,
                    'message': f'会话密钥解密失败: {dec_result["message"]}'
                }
            logger.info(f" [Falcon] 会话密钥交换接收成功 (Falcon-{security_level})")
            return {
                'success': True,
                'session_key': dec_result['session_key'],
                'message': f'会话密钥交换接收成功 (Falcon-{security_level})'
            }
        except Exception as e:
            logger.error(f" [Falcon] 会话密钥交换接收失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': f'会话密钥交换失败: {str(e)}'
            }
    def generate_falcon_keys_v2(self, node_id: str, security_level: int = 512) -> Dict[str, Any]:
        import time
        import json
        try:
            start_time = time.time()
            logger.info(f" 开始为节点 {node_id} 生成Falcon-{security_level}密钥对（无证书Falcon方案）")
            from .falcon_aes_session_encryption import FalconAESSessionKeyEncryption, FALCON_PARAMS
            if security_level not in FALCON_PARAMS:
                return {'success': False, 'message': f'不支持的安全级别: {security_level}'}
            params = FALCON_PARAMS[security_level]
            falcon_service = FalconAESSessionKeyEncryption(security_level=security_level)
            falcon_service._initialize_cf()
            if falcon_service.cf_strict.system_params is None:
                setup_result = falcon_service.cf_strict.setup()
                if not setup_result['success']:
                    return {'success': False, 'message': 'Setup失败'}
            keygen_start = time.time()
            S_id = falcon_service.cf_strict.set_secret_value()
            U_id = falcon_service.cf_strict.set_pk(S_id)
            D_id_result = falcon_service.cf_strict.partial_key_gen(node_id)
            if not D_id_result['success']:
                return D_id_result
            D_id = D_id_result['D_id']
            keygen_time = time.time() - keygen_start
            encoding_start = time.time()
            falcon_public_key_data = {
                'U_id': U_id.tolist(),
                'algorithm': f'CertificatelessFalcon-{security_level}',
                'security_level': security_level,
                'node_id': node_id,
                'parameters': params
            }
            falcon_private_key_data = {
                'D_id': D_id.tolist(),
                'S_id': S_id.tolist(),
                'algorithm': f'CertificatelessFalcon-{security_level}',
                'security_level': security_level,
                'node_id': node_id,
                'parameters': params
            }
            falcon_public_key = base64.b64encode(
                json.dumps(falcon_public_key_data).encode('utf-8')
            ).decode('utf-8')
            falcon_private_key = base64.b64encode(
                json.dumps(falcon_private_key_data).encode('utf-8')
            ).decode('utf-8')
            encoding_time = time.time() - encoding_start
            total_time = time.time() - start_time
            logger.info(f" Falcon-{security_level}密钥对生成成功（无证书Falcon方案）")
            logger.info(f"    公钥U_id形状: {U_id.shape}")
            logger.info(f"    私钥D_id形状: {D_id.shape}")
            logger.info(f"    私钥S_id形状: {S_id.shape}")
            logger.info(f"   ⏱️  密钥生成耗时: {keygen_time:.4f}秒")
            logger.info(f"   ⏱️  Base64编码耗时: {encoding_time:.4f}秒")
            logger.info(f"   ⏱️  总耗时: {total_time:.4f}秒")
            return {
                'success': True,
                'falcon_public_key': falcon_public_key,
                'falcon_private_key': falcon_private_key,
                'algorithm': f'CertificatelessFalcon-{security_level}',
                'security_level': security_level,
                'variant': security_level,
                'generation_time': {
                    'keygen': round(keygen_time, 4),
                    'encoding': round(encoding_time, 4),
                    'total': round(total_time, 4)
                },
                'key_sizes': {
                    'public_key': len(falcon_public_key),
                    'private_key': len(falcon_private_key)
                },
                'message': f'Falcon-{security_level}密钥对生成成功（耗时{total_time:.3f}秒）'
            }
        except Exception as e:
            logger.error(f" Falcon-{security_level}密钥生成失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': f'Falcon密钥生成失败: {str(e)}'
            }
    def kgc_partial_key_generation_v2_kyber(self, node_id: str, kyber_public_key_b64: str) -> Dict[str, Any]:
        try:
            logger.info(f"[KGC] 开始为节点 {node_id} 生成Kyber V2部分私钥...")
            import time
            start_time = time.time()
            kyber_v2_wrapper = CertificatelessKyberV2Wrapper(security_level=self.kyber_security_level)
            partial_key_result = kyber_v2_wrapper.kyber_manager.kgc_generate_partial_key(node_id)
            if not partial_key_result['success']:
                logger.error(f"[KGC] 部分私钥生成失败: {partial_key_result['message']}")
                return {
                    'success': False,
                    'message': f'部分私钥生成失败: {partial_key_result["message"]}'
                }
            logger.info(f"[KGC] 部分私钥生成成功，准备加密...")
            partial_key_data = partial_key_result['partial_key_data']
            try:
                kyber_pk_bytes = base64.b64decode(kyber_public_key_b64)
                logger.info(f"[KGC] Kyber公钥解码成功，长度: {len(kyber_pk_bytes)} bytes")
            except Exception as e:
                logger.error(f"[KGC] Kyber公钥解码失败: {e}")
                return {
                    'success': False,
                    'message': f'Kyber公钥解码失败: {str(e)}'
                }
            try:
                kyber_ciphertext, kyber_shared_secret = self.kyber.encaps(kyber_pk_bytes)
                logger.info(f"[KGC] Kyber KEM encaps成功，共享密钥长度: {len(kyber_shared_secret)} bytes")
            except Exception as e:
                logger.error(f"[KGC] Kyber KEM encaps失败: {e}")
                return {
                    'success': False,
                    'message': f'Kyber KEM encaps失败: {str(e)}'
                }
            partial_key_json = json.dumps(partial_key_data).encode('utf-8')
            # 载荷层按 D3 用 SM4：KEK 从 Kyber 共享秘密取前 16 字节。
            # （原先是 AES-256 + 32 字节 KEK；信封里的 `payload_algorithm` 让读取端
            #   能区分新老数据 —— `key_update_service` 的两个解密点据此分派。）
            payload_kek = PayloadCipher.kek_from_shared_secret(PAYLOAD_ALGORITHM_SM4, kyber_shared_secret)
            encrypted_partial_key, nonce_tag = PayloadCipher.encrypt_with(
                PAYLOAD_ALGORITHM_SM4, partial_key_json, payload_kek
            )
            logger.info("[KGC] 部分私钥加密成功（SM4-GCM）")
            encrypted_package = {
                'kyber_ciphertext': base64.b64encode(kyber_ciphertext).decode('utf-8'),
                'encrypted_partial_key': base64.b64encode(encrypted_partial_key).decode('utf-8'),
                'nonce_tag': base64.b64encode(nonce_tag).decode('utf-8'),
                'node_id': node_id,
                'algorithm': 'CertificatelessKyberV2',
                'payload_algorithm': PAYLOAD_ALGORITHM_SM4,
            }
            elapsed = time.time() - start_time
            logger.info(f"[KGC] Kyber V2部分私钥生成并加密完成，耗时: {elapsed:.3f}秒")
            return {
                'success': True,
                'encrypted_package': encrypted_package,
                'encrypted_partial_key': json.dumps(encrypted_package),
                'message': 'Kyber V2部分私钥生成并加密成功'
            }
        except Exception as e:
            logger.error(f"[KGC] Kyber V2部分私钥生成失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': f'Kyber V2部分私钥生成失败: {str(e)}'
            }
    def node_kyber_key_generation_v2(self, node_id: str, kyber_private_key: str, encrypted_package: str) -> Dict[str, Any]:
        try:
            logger.info(f"[节点] 开始接收Kyber V2部分私钥并生成完整密钥对...")
            import time
            start_time = time.time()
            package_data = json.loads(encrypted_package)
            kyber_ciphertext = base64.b64decode(package_data['kyber_ciphertext'])
            encrypted_partial_key = base64.b64decode(package_data['encrypted_partial_key'])
            nonce_tag = base64.b64decode(package_data['nonce_tag'])
            logger.info(f"[节点] 加密包解析成功")
            kyber_sk_bytes = base64.b64decode(kyber_private_key)
            logger.info(f"[节点] 节点Kyber私钥解码成功，长度: {len(kyber_sk_bytes)} bytes")
            kyber_shared_secret = self.kyber.decaps(kyber_ciphertext, kyber_sk_bytes)
            logger.info(f"[节点] Kyber KEM decaps成功，共享密钥长度: {len(kyber_shared_secret)} bytes")
            partial_key_json = self.aes.decrypt(encrypted_partial_key, kyber_shared_secret, nonce_tag)
            partial_key_data = json.loads(partial_key_json.decode('utf-8'))
            logger.info(f"[节点] 部分私钥解密成功")
            kyber_v2_wrapper = CertificatelessKyberV2Wrapper(security_level=self.kyber_security_level)
            secret_result = kyber_v2_wrapper.kyber_manager.user_generate_secret_value(node_id)
            if not secret_result['success']:
                logger.error(f"[节点] 秘密值生成失败: {secret_result['message']}")
                return {
                    'success': False,
                    'message': f'秘密值生成失败: {secret_result["message"]}'
                }
            logger.info(f"[节点] 秘密值生成成功")
            keygen_result = kyber_v2_wrapper.kyber_manager.user_set_sk_and_pk(
                node_id,
                partial_key_data['t'],
                partial_key_data['c'],
                partial_key_data['u_prime_id']
            )
            if not keygen_result['success']:
                logger.error(f"[节点] 完整密钥对生成失败: {keygen_result['message']}")
                return {
                    'success': False,
                    'message': f'完整密钥对生成失败: {keygen_result["message"]}'
                }
            logger.info(f"[节点] 完整密钥对生成成功")
            elapsed = time.time() - start_time
            logger.info(f"[节点] Kyber V2完整密钥对生成完成，耗时: {elapsed:.3f}秒")
            return {
                'success': True,
                'kyber_private_key': keygen_result['kyber_private_key'],
                'kyber_public_key': keygen_result['kyber_public_key'],
                'algorithm': 'CertificatelessKyberV2',
                'security_level': self.kyber_security_level,
                'sk_size': keygen_result.get('sk_size', 0),
                'pk_size': keygen_result.get('pk_size', 0),
                'generation_time': elapsed,
                'message': 'Kyber V2完整密钥对生成成功'
            }
        except Exception as e:
            logger.error(f"[节点] Kyber V2密钥生成失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': f'Kyber V2密钥生成失败: {str(e)}'
            }