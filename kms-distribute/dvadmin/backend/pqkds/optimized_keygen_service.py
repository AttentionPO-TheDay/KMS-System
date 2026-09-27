import logging
import time
import base64
import numpy as np
from typing import Dict, Any
from .ultra_fast_keygen_optimized_v6 import OptimizedFalconKeygen, FALCON_PARAMS
from .certificateless_kyber_dll_fusion import get_fusion_instance

logger = logging.getLogger(__name__)


class OptimizedKeygenService:
    def __init__(self):
        # Falcon 密钥生成器缓存: security_level -> OptimizedFalconKeygen
        self._falcon_keygen_cache = {}
        # 默认初始化 Falcon-512
        self._get_falcon_keygen(512)

        # Kyber密钥生成使用融合模块（无证书算法 + DLL KEM）
        self.kyber_fusion = get_fusion_instance(variant=512)

        logger.info(
            "优化的密钥生成服务已初始化 "
            "(Kyber: 无证书+DLL融合, Falcon: 无证书格密码 512/1024)"
        )

    def _get_falcon_keygen(self, security_level: int = 512) -> OptimizedFalconKeygen:
        """获取指定安全级别的 Falcon 密钥生成器（带缓存）"""
        if security_level not in self._falcon_keygen_cache:
            keygen = OptimizedFalconKeygen.create(security_level)
            keygen.setup_cached()
            self._falcon_keygen_cache[security_level] = keygen
            logger.info(f"初始化 Falcon-{security_level} 密钥生成器: "
                        f"n={keygen.n}, m={keygen.m}, q={keygen.q}")
        return self._falcon_keygen_cache[security_level]

    def generate_falcon_keypair(self, node_id: str, security_level: int = 512) -> Dict[str, Any]:
        start_time = time.time()
        try:
            # 使用 TrapGen + DLL 融合方案生成 Falcon 密钥
            from .falcon_trapgen_dll import generate_falcon_cl_keypair
            keypair = generate_falcon_cl_keypair(node_id)
            elapsed = time.time() - start_time

            if not keypair.get('success'):
                return {'success': False, 'error': keypair.get('error', '密钥生成失败')}

            logger.info(
                f"[Falcon-{security_level}] 节点{node_id}密钥生成完成(TrapGen+DLL)，"
                f"耗时{elapsed*1000:.2f}ms"
            )
            return {
                'success': True,
                'algorithm': keypair['algorithm'],
                'security_level': security_level,
                'node_id': node_id,
                'public_key': keypair['public_key'].tolist(),
                'private_key': {
                    'D_id': keypair['D_id'].tolist(),
                    'S_id': keypair['S_id'].tolist()
                },
                'D_id': keypair['D_id'].tolist(),
                'S_id': keypair['S_id'].tolist(),
                'H_id': keypair['H_id'].tolist(),
                'A': keypair['A'].tolist(),
                'B': keypair['B'].tolist(),
                'falcon_pk': base64.b64encode(keypair['falcon_pk']).decode('ascii'),
                'falcon_sk': base64.b64encode(keypair['falcon_sk']).decode('ascii'),
                'parameters': keypair.get('parameters', FALCON_PARAMS.get(security_level, {}))
            }
        except ImportError:
            # 回退到旧方案
            logger.warning(f"TrapGen+DLL 不可用，回退到旧方案")
            return self._generate_falcon_keypair_legacy(node_id, security_level)
        except Exception as e:
            logger.error(f"Falcon-{security_level}密钥对生成失败: {e}")
            import traceback; traceback.print_exc()
            return {'success': False, 'error': str(e)}

    def _generate_falcon_keypair_legacy(self, node_id: str, security_level: int = 512) -> Dict[str, Any]:
        """旧方案回退 (无 TrapGen)"""
        start_time = time.time()
        try:
            falcon_keygen = self._get_falcon_keygen(security_level)
            keypair = falcon_keygen.generate_keypair_fast(node_id)
            elapsed = time.time() - start_time
            return {
                'success': True,
                'algorithm': f'CertificatelessFalcon-{security_level}',
                'security_level': security_level,
                'node_id': node_id,
                'public_key': keypair['pk'].tolist(),
                'private_key': {
                    'D_id': keypair['sk']['D_id'].tolist(),
                    'S_id': keypair['sk']['S_id'].tolist()
                },
                'D_id': keypair['D_id'].tolist(),
                'S_id': keypair['S_id'].tolist(),
                'H_id': keypair['H_id'].tolist(),
                'A': falcon_keygen.A_cache.tolist(),
                'B': falcon_keygen.B_cache.tolist(),
                'parameters': keypair.get('parameters', FALCON_PARAMS.get(security_level, {}))
            }
        except Exception as e:
            logger.error(f"Falcon-{security_level}密钥对生成失败(legacy): {e}")
            return {'success': False, 'error': str(e)}

    def complete_falcon_keygen_with_partial_key(
        self, node_id: str, D_id_list: list, H_id_list: list,
        A_list: list = None, B_list: list = None,
        security_level: int = 512
    ) -> Dict[str, Any]:
        """
        使用KGC下发的部分私钥(D_id, H_id, A, B)完成Falcon密钥生成。

        流程：
        1. 从KGC部分私钥中恢复 D_id, H_id, A, B (numpy数组)
        2. 节点自主执行 SetSecretValue → S_id (短矩阵)
        3. 执行 SetSK(D_id, S_id)
        4. 使用KGC的B执行 SetPK(S_id) → U_id = B·S_id mod q
        5. 返回完整密钥对（公钥包含 A, B, H_id, U_id）
        """
        start_time = time.time()
        try:
            params = FALCON_PARAMS.get(security_level, FALCON_PARAMS[512])
            q = params['q']

            logger.info(
                f"[Falcon-{security_level}] 节点{node_id}使用KGC部分私钥完成密钥生成"
            )

            # 恢复KGC的部分私钥为numpy数组
            D_id = np.array(D_id_list, dtype=np.int64)
            H_id = np.array(H_id_list, dtype=np.int64)
            logger.info(f"  KGC部分私钥: D_id={D_id.shape}, H_id={H_id.shape}")

            # 从实际矩阵维度推断n和m，而不是依赖security_level参数
            # D_id: (m, m), H_id: (n, m), A: (n, m), B: (n, m)
            m = D_id.shape[0]
            n = H_id.shape[0]
            if m != params['m'] or n != params['n']:
                logger.warning(
                    f"  KGC部分私钥维度({n},{m})与security_level={security_level}"
                    f"的预期维度({params['n']},{params['m']})不一致，以实际维度为准"
                )

            # 恢复KGC的系统参数 A 和 B
            if A_list is not None and B_list is not None:
                A = np.array(A_list, dtype=np.int64)
                B = np.array(B_list, dtype=np.int64)
                logger.info(f"  使用KGC系统参数: A={A.shape}, B={B.shape}")
            else:
                # 兼容旧数据：如果KGC没有下发A和B，生成新的
                logger.warning("  KGC部分私钥中缺少A/B，生成新的系统参数")
                A = np.random.randint(0, q, size=(n, m), dtype=np.int64)
                B = np.random.randint(0, q, size=(n, m), dtype=np.int64)
                # 重新计算 H_id = A·D_id mod q
                H_id = np.dot(A, D_id) % q
                logger.info(f"  重新计算 H_id={H_id.shape}")

            # SetSecretValue: 节点自主生成秘密值S_id (短矩阵)
            sigma = 1.17
            S_id = np.round(np.random.normal(0, sigma, size=(m, m))).astype(np.int64)
            logger.info(f"  SetSecretValue: S_id={S_id.shape}, max|S_id|={np.max(np.abs(S_id))}")

            # SetSK: SK_id = {D_id, S_id}
            logger.info(f"  SetSK: 完成")

            # SetPK: U_id = B·S_id mod q
            U_id = np.dot(B, S_id) % q
            logger.info(f"  SetPK: U_id={U_id.shape}")

            elapsed = time.time() - start_time
            logger.info(
                f"[Falcon-{security_level}] 节点{node_id}使用KGC部分私钥完成密钥生成，"
                f"耗时{elapsed*1000:.2f}ms"
            )

            actual_params = {'n': n, 'm': m, 'q': q}

            return {
                'success': True,
                'algorithm': f'CertificatelessFalcon-{security_level}',
                'security_level': security_level,
                'node_id': node_id,
                'public_key': U_id.tolist(),
                'private_key': {
                    'D_id': D_id.tolist(),
                    'S_id': S_id.tolist()
                },
                'D_id': D_id.tolist(),
                'S_id': S_id.tolist(),
                'H_id': H_id.tolist(),
                'A': A.tolist(),
                'B': B.tolist(),
                'parameters': actual_params
            }
        except Exception as e:
            logger.error(f"Falcon-{security_level}使用部分私钥完成密钥生成失败: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}

    def complete_kyber_keygen_with_partial_key(
        self, node_id: str, partial_key_t: list, hash_c: list,
        u_prime_id: list
    ) -> Dict[str, Any]:
        """
        使用KGC下发的部分私钥(t_id, c_id, u_prime_id)完成Kyber密钥生成。

        流程：
        1. 从KGC部分私钥中恢复 t, c, u_prime_id (numpy数组)
        2. 调用融合模块的 node_complete_keygen(t, c, u_prime_id)
           内部执行: SetSecretValue → s_id, SetSK(t, s_id), SetPK(u_prime_id, c, s_id)
           DLL桥接: cl_sk → coins → keypair_derand → (kyber_pk, kyber_sk)
        3. 返回标准Kyber格式的密钥对
        """
        start_time = time.time()
        try:
            logger.info(f"[Kyber] 节点{node_id}使用KGC部分私钥完成密钥生成")

            t = np.array(partial_key_t, dtype=np.int64)
            c = np.array(hash_c, dtype=np.int64)
            u_p = np.array(u_prime_id, dtype=np.int64)
            logger.info(f"  KGC部分私钥: t={t.shape}, c={c.shape}, u_prime_id={u_p.shape}")

            result = self.kyber_fusion.node_complete_keygen(node_id, t, c, u_p)
            elapsed = time.time() - start_time

            if not result['success']:
                return {'success': False, 'error': '使用部分私钥完成Kyber密钥生成失败'}

            logger.info(
                f"[Kyber] 节点{node_id}使用KGC部分私钥完成密钥生成，"
                f"耗时{elapsed*1000:.2f}ms, "
                f"pk={len(result['kyber_public_key'])}B, "
                f"sk={len(result['kyber_private_key'])}B"
            )

            from .certificateless_kyber_dll_fusion import CertificatelessKyberDLLFusion
            cl_pk_b64 = CertificatelessKyberDLLFusion.serialize_cl_key(result['cl_public_key'])
            cl_sk_b64 = CertificatelessKyberDLLFusion.serialize_cl_key(result['cl_private_key'])

            return {
                'success': True,
                'algorithm': f'CertificatelessKyber{result["variant"]}_DLL',
                'node_id': node_id,
                'kyber_public_key': result['kyber_public_key'],
                'kyber_private_key': result['kyber_private_key'],
                'cl_public_key': cl_pk_b64,
                'cl_private_key': cl_sk_b64,
                'partial_key_t': result['partial_key_t'].tolist(),
                'secret_value_s_id': result['secret_value_s_id'].tolist(),
                'hash_c': result['hash_c'].tolist(),
                'u_prime_id': result['u_prime_id'].tolist(),
                'variant': result['variant'],
                'pk_bytes': result['pk_bytes'],
                'sk_bytes': result['sk_bytes'],
                'partial_key_source': 'KGC',
            }
        except Exception as e:
            logger.error(f"Kyber使用部分私钥完成密钥生成失败: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}

    def generate_kyber_keypair(self, node_id: str) -> Dict[str, Any]:
        """
        生成无证书Kyber密钥对（融合版）。

        流程：
        1. 无证书算法: Setup → PartialKeyGen → SetSecretValue → SetSK → SetPK
        2. DLL桥接: cl_sk → SHAKE-256 → coins → keypair_derand → (kyber_pk, kyber_sk)
        3. 返回标准Kyber格式的密钥对，可直接用于KEM encaps/decaps
        """
        start_time = time.time()
        try:
            result = self.kyber_fusion.generate_certificateless_keypair(node_id)
            elapsed = time.time() - start_time

            if not result['success']:
                return {'success': False, 'error': '无证书Kyber密钥生成失败'}

            logger.info(
                f"[Kyber] 节点{node_id}无证书+DLL融合密钥生成完成，"
                f"耗时{elapsed*1000:.2f}ms, "
                f"pk={len(result['kyber_public_key'])}B, "
                f"sk={len(result['kyber_private_key'])}B"
            )

            return {
                'success': True,
                'algorithm': f'CertificatelessKyber{result["variant"]}_DLL',
                'node_id': node_id,
                # 标准Kyber DLL格式的密钥对（bytes），用于KEM加解密
                'kyber_public_key': result['kyber_public_key'],
                'kyber_private_key': result['kyber_private_key'],
                # 无证书层密钥（numpy数组），用于无证书格密码 Enc/Dec
                'cl_public_key': result['cl_public_key'],
                'cl_private_key': result['cl_private_key'],
                # 系统矩阵 A（无证书格密码 Enc 加密时需要）
                'system_A': result['system_A'],
                # 无证书层中间值（列表格式，兼容现有存储）
                'partial_key_t': result['partial_key_t'].tolist(),
                'secret_value_s_id': result['secret_value_s_id'].tolist(),
                'hash_c': result['hash_c'].tolist(),
                'u_prime_id': result['u_prime_id'].tolist(),
                # 密钥尺寸信息
                'variant': result['variant'],
                'pk_bytes': result['pk_bytes'],
                'sk_bytes': result['sk_bytes'],
            }
        except Exception as e:
            logger.error(f"Kyber密钥对生成失败: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}


_keygen_service = None


def get_keygen_service() -> OptimizedKeygenService:
    global _keygen_service
    if _keygen_service is None:
        _keygen_service = OptimizedKeygenService()
    return _keygen_service

