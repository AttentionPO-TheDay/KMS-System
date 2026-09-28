import logging
import json
import base64
import numpy as np
import zlib
from typing import Dict, Any
from functools import wraps
from django.utils import timezone
from django.db import transaction, connection
from .models import Node, SessionKey, FalconKeyPair
from .optimized_keygen_service import OptimizedKeygenService
from .blockchain_service import BlockchainService
from .node_blockchain_upload_service import NodeBlockchainUploadService
# 载荷层：新数据用国密 SM4，历史数据按密钥长度/信封形状回退到 AES-256（决策 D3）
from .sm4_crypto import (
    GCM_IV_BYTES,
    LEGACY_AES_KEY_BYTES,
    PayloadCipher,
    SM4Crypto,
)

logger = logging.getLogger(__name__)


def _to_list(obj):
    """将 numpy 数组转为 list，用于 JSON 序列化"""
    if hasattr(obj, 'tolist'):
        return obj.tolist()
    return obj


def decode_falcon_partial_key(partial_key_b64: str) -> dict:
    """解码Falcon部分私钥，兼容压缩(zlib)和未压缩(纯JSON)两种格式"""
    raw = base64.b64decode(partial_key_b64)
    try:
        # 先尝试zlib解压（新格式）
        decompressed = zlib.decompress(raw)
        return json.loads(decompressed.decode('utf-8'))
    except zlib.error:
        # 回退到纯JSON（旧格式）
        return json.loads(raw.decode('utf-8'))


def ensure_db_connection(func):
    """装饰器：确保数据库连接有效，自动重连"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_msg = str(e)
            if 'Server has gone away' in error_msg or '2006' in error_msg or 'Lost connection' in error_msg:
                logger.warning(f"数据库连接断开，尝试重新连接: {error_msg}")
                try:
                    _force_reconnect_db()
                    return func(*args, **kwargs)
                except Exception as retry_error:
                    logger.error(f"重新连接后仍然失败: {retry_error}")
                    raise
            else:
                raise
    return wrapper


def _force_reconnect_db():
    """
    强制重建数据库连接并设置大数据包支持。

    MySQL 的 max_allowed_packet 只能 SET GLOBAL，且只对新连接生效。
    所以流程是：连接 → SET GLOBAL → 断开 → 重连（新连接继承 GLOBAL 值）。
    """
    # 第一步：建立临时连接，设置 GLOBAL max_allowed_packet
    connection.close()
    connection.connect()
    try:
        with connection.cursor() as cursor:
            try:
                cursor.execute("SET GLOBAL max_allowed_packet=268435456")  # 256MB
                logger.info("[DB] SET GLOBAL max_allowed_packet=256MB 成功")
            except Exception as e:
                logger.warning(f"[DB] SET GLOBAL max_allowed_packet 失败(可能无SUPER权限): {e}")
    except Exception:
        pass

    # 第二步：断开再重连，让新的 max_allowed_packet 生效
    connection.close()
    connection.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET SESSION net_read_timeout=600")
            cursor.execute("SET SESSION net_write_timeout=600")
            cursor.execute("SET SESSION wait_timeout=28800")
            # 验证 max_allowed_packet
            cursor.execute("SELECT @@max_allowed_packet")
            row = cursor.fetchone()
            logger.info(f"[DB] 数据库连接已重建, max_allowed_packet={row[0] if row else 'unknown'}")
    except Exception as e:
        logger.warning(f"[DB] 设置会话参数失败(不影响功能): {e}")


def _safe_update_node(node_id: str, **fields):
    """
    安全地更新节点大字段。
    逐字段写入，避免单条 UPDATE 超过 max_allowed_packet。
    如果遇到连接断开，自动重连后重试。
    """
    from .models import Node
    for field_name, field_value in fields.items():
        for attempt in range(2):
            try:
                Node.objects.filter(node_id=node_id).update(**{field_name: field_value})
                break
            except Exception as e:
                error_msg = str(e)
                if attempt == 0 and ('Server has gone away' in error_msg or '2006' in error_msg):
                    logger.warning(f"[DB] 写入字段 {field_name} 失败，重连后重试: {error_msg}")
                    _force_reconnect_db()
                else:
                    raise

def compress_key_data(key_data: str) -> str:
    """压缩密钥数据"""
    try:
        data_bytes = key_data.encode('utf-8')
        compressed = zlib.compress(data_bytes, level=9)
        compressed_b64 = base64.b64encode(compressed).decode('utf-8')
        return f"COMPRESSED:{compressed_b64}"
    except Exception as e:
        logger.warning(f"密钥压缩失败: {e}，使用原始数据")
        return key_data

def decompress_key_data(key_data: str) -> str:
    """解压缩密钥数据"""
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


class NodeService:
    def __init__(self, node_id: str):
        self.node_id = node_id
        try:
            self.node = Node.objects.get(node_id=node_id)
        except Node.DoesNotExist:
            self.node = None
            logger.warning(f"节点 {node_id} 不存在")

        self.keygen_service = OptimizedKeygenService()
        self.blockchain_service = BlockchainService()
        self.upload_service = NodeBlockchainUploadService()

    @staticmethod
    def recover_kyber_kem_session_key(encrypted_session_key_data: str,
                                       receiver_kyber_partial_key_data: str) -> bytes:
        """
        使用图中 Dec 算法从无证书格密码密文中恢复AES会话密钥。

        Dec: M = ⌊(c₂ − s̄ᵗ · c₁) / (q/2)⌋

        Args:
            encrypted_session_key_data: 二进制序列化的格密码密文 (base64)
            receiver_kyber_partial_key_data: 接收方的 kyber_partial_key_data (JSON)

        Returns:
            32字节的AES会话密钥
        """
        from .kyber_fast_engine import (
            kyber_fast_decrypt, _deserialize_kyber_ct, _KyberCLKeyCache
        )

        # 反序列化密文
        C1, C2, q, key_length = _deserialize_kyber_ct(encrypted_session_key_data)

        # 获取无证书私钥 s̄
        cl_sk = _KyberCLKeyCache.get_cl_private_key(receiver_kyber_partial_key_data)
        sk = cl_sk['sk']

        # 使用图中 Dec 算法解密
        aes_session_key = kyber_fast_decrypt(C1, C2, sk, q, key_length)
        logger.info(
            f"[KyberCL恢复] 格密码解密完成, session_key={len(aes_session_key)}B"
        )

        return aes_session_key
    def register_node(self, name: str, ip_address: str, port: int, **kwargs) -> Dict[str, Any]:
        try:
            import time
            logger.info(f"开始注册节点 {self.node_id}")

            if self.node is None:
                self.node = Node.objects.create(
                    node_id=self.node_id,
                    name=name,
                    ip_address=ip_address,
                    port=port,
                    status='registered'
                )
                logger.info(f"节点 {self.node_id} 创建成功")
            else:
                self.node.name = name
                self.node.ip_address = ip_address
                self.node.port = port
                self.node.status = 'registered'
                self.node.save()
                logger.info(f"节点 {self.node_id} 更新成功")

            for field, value in kwargs.items():
                if hasattr(self.node, field) and value is not None:
                    setattr(self.node, field, value)

            self.node.save()

            # 记录Kyber密钥生成开始时间
            kyber_start_time = time.time()
            kyber_kp = self.keygen_service.generate_kyber_keypair(self.node_id)
            kyber_end_time = time.time()
            kyber_duration = kyber_end_time - kyber_start_time

            if kyber_kp['success']:
                # 融合模块返回的是标准Kyber DLL格式的bytes密钥对
                kyber_pk = kyber_kp['kyber_public_key']
                kyber_sk = kyber_kp['kyber_private_key']
                self.node.kyber_public_key = base64.b64encode(kyber_pk).decode('utf-8')
                self.node.kyber_private_key = base64.b64encode(kyber_sk).decode('utf-8')

                # 保存无证书层密钥 (cl_public_key=u, cl_private_key=s̄, A) 用于图中 Enc/Dec
                _cl_pk = kyber_kp.get('cl_public_key')
                _cl_sk = kyber_kp.get('cl_private_key')
                _sys_A = kyber_kp.get('system_A')
                self.node.kyber_partial_key_data = json.dumps({
                    'partial_key_t': kyber_kp.get('partial_key_t'),
                    'secret_value_s_id': kyber_kp.get('secret_value_s_id'),
                    'hash_c': kyber_kp.get('hash_c'),
                    'u_prime_id': kyber_kp.get('u_prime_id'),
                    'cl_public_key': _cl_pk.tolist() if hasattr(_cl_pk, 'tolist') else _cl_pk,
                    'cl_private_key': _cl_sk.tolist() if hasattr(_cl_sk, 'tolist') else _cl_sk,
                    'A': _sys_A.tolist() if hasattr(_sys_A, 'tolist') else _sys_A,
                    'algorithm': kyber_kp.get('algorithm', 'CertificatelessKyber512_DLL'),
                    'parameters': {'n': 512, 'm': 1024, 'q': 12289},
                })
                self.node.kyber_keygen_time = timezone.now()
                self.node.kyber_keygen_duration = kyber_duration
                logger.info(f"节点 {self.node_id} Kyber公钥生成成功，耗时: {kyber_duration:.4f}秒")
            else:
                logger.error(f"节点 {self.node_id} Kyber密钥生成失败: {kyber_kp.get('error')}")
                return {
                    'success': False,
                    'message': f"Kyber密钥生成失败: {kyber_kp.get('error')}"
                }

            self.node.status = 'kyber_uploaded'
            self.node.save()

            # 顺带生成国密密钥（SM2 + SSCL）—— 2026-09-26 起。
            # 这样新建的节点四种节点腿算法（Kyber / Falcon / 国密 SM2 / 国密 SSCL）里
            # 国密那两种开箱可用。
            # 失败只记日志、不阻断注册：节点没有国密密钥时，对应算法会在分发时报明确原因。
            try:
                gm_result = self.generate_gm_keys()
                if gm_result.get('success'):
                    logger.info(f"节点 {self.node_id} 国密密钥已随注册生成")
                else:
                    logger.warning(f"节点 {self.node_id} 国密密钥生成失败: {gm_result.get('message')}")
            except Exception as gm_exc:  # noqa: BLE001
                logger.warning(f"节点 {self.node_id} 国密密钥生成异常: {gm_exc}")
            self.node.refresh_from_db()

            # 顺带生成 Falcon 密钥 —— 2026-09-26 起（此前必须手动点「生成 Falcon 密钥」）。
            #
            # 为什么要自动生成：密钥池的 Falcon 路径要求**接收方**已有 Falcon 公钥，
            # 否则直接拒绝。少了这一步，新建的演示节点在 Falcon 体系下不可用。
            #
            # 代价（本机实测，Falcon-512）：Falcon 本身 KGC 部分私钥 5.9s + 密钥对 1.9s，
            # 加上写库（Falcon 公钥 7.8MB + 私钥 1.4MB）与上链等开销，
            # **注册整体从约 2 秒变成约 18~22 秒**（改造前实测 21.7s，
            # 停写 falcon_lattice_params 后 18.1s）。
            # 前端必须为此显示"生成中"且抑制重复提交（见 views/nodes/index.vue 的创建对话框）。
            #
            # 与国密同样：失败只记日志、不阻断注册。Kyber 已经落库，节点是可用的，
            # 缺 Falcon 时界面上仍有单节点/批量生成入口可补。
            try:
                falcon_result = self.generate_falcon_keys_v2()
                if falcon_result.get('success'):
                    logger.info(f"节点 {self.node_id} Falcon密钥已随注册生成")
                else:
                    logger.warning(
                        f"节点 {self.node_id} Falcon密钥生成失败: {falcon_result.get('message')}"
                    )
            except Exception as falcon_exc:  # noqa: BLE001
                logger.warning(f"节点 {self.node_id} Falcon密钥生成异常: {falcon_exc}")
            self.node.refresh_from_db()

            try:
                upload_result = self.upload_service.upload_node_registration(self.node)
                if upload_result['success']:
                    logger.info(f"节点 {self.node_id} Kyber公钥已上链")
                else:
                    logger.warning(f"节点 {self.node_id} 上链失败: {upload_result.get('message')}")
            except Exception as e:
                logger.warning(f"节点 {self.node_id} 上链异常: {e}")

            return {
                'success': True,
                'message': f'节点 {self.node_id} 密钥对生成成功（Kyber / Falcon / 国密 均已就绪）',
                'node_id': self.node_id,
                'status': self.node.status,
                'kyber_keygen_time': self.node.kyber_keygen_time.isoformat() if self.node.kyber_keygen_time else None,
                'kyber_keygen_duration': round(self.node.kyber_keygen_duration, 4) if self.node.kyber_keygen_duration else None
            }

        except Exception as e:
            logger.error(f"节点 {self.node_id} 注册异常: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': f'节点注册失败: {str(e)}'
            }

    def provision_node(self, name: str, ip_address: str, port: int, **kwargs) -> Dict[str, Any]:
        """
        阶段 2：**建节点只建账号**，不生成任何密钥。

        与 `register_node` 的区别
        ------------------------
        改造前（register_node）：建节点 → 服务端立刻生成 Kyber/Falcon/SM2/SSCL
                                四套密钥 → status='registered'。实测 18~22 秒。
        改造后（本方法）：建节点 → 建 Node 行 + 建 kms.sys_user 账号
                                → status='PENDING_INIT'。**毫秒级**。
                         四套密钥推迟到**节点首次登录**时生成（见 initialize_base_keys）。

        这条改动对应文档 §2.4 与 §3.1：
        「节点创建和密码学初始化是两个阶段，不能再由后台在创建节点时直接生成完整私钥。」

        为什么整体挪到事务里
        ------------------
        Node 在 `falcon_kds`、sys_user 在 `kms`，两者 schema 不同但**同一个 MySQL
        实例**。`transaction.atomic()` 关掉 autocommit 后，同一条连接上的跨 schema
        INSERT 属于同一个事务，因此不会出现"Node 建了、账号没建"的半截状态。
        """
        from django.db import transaction
        from .node_account_service import ensure_node_account

        with transaction.atomic():
            if self.node is None:
                self.node = Node.objects.create(
                    node_id=self.node_id,
                    name=name,
                    ip_address=ip_address,
                    port=port,
                    status='PENDING_INIT',
                )
                logger.info("节点 %s 创建成功（待初始化）", self.node_id)
            else:
                self.node.name = name
                self.node.ip_address = ip_address
                self.node.port = port
                # 已存在的节点不重置状态：它可能已经完成初始化，
                # 重新注册不该把它打回 PENDING_INIT。
                self.node.save()
                logger.info("节点 %s 更新成功", self.node_id)

            for field, value in kwargs.items():
                if hasattr(self.node, field) and value is not None:
                    setattr(self.node, field, value)
            self.node.save()

            # 建对应的登录账号（跨 schema，见 node_account_service 的说明）
            user_id = ensure_node_account(self.node)
            self.node.sys_user_id = user_id
            self.node.save(update_fields=['sys_user_id'])

        return {
            'success': True,
            'message': f'节点 {self.node_id} 已创建（账号已就绪，等待节点首次登录完成密钥初始化）',
            'node_id': self.node_id,
            'status': self.node.status,
            'sys_user_id': user_id,
        }

    #: 算法 → (主公钥列, 需要一并写入的其它公钥列)
    #:
    #: ⚠️ Falcon 同时写两列是**过渡期的刻意选择**，不是笔误：
    #:   `falcon_sign_public_key` 是签名路径真正读的那一列
    #:   （`envelope_signature._decode_falcon_public_key`），
    #:   而 `falcon_public_key` 仍被 ACTIVE 判定与 `_node_payload` 的就绪位读着。
    #:   放弃 CL-Falcon 之后每个节点只有**一对** Falcon 密钥，两列指向同一把；
    #:   等下一阶段把旧的 CL-Falcon 列清掉时再收敛为一列。
    _PUBLIC_KEY_COLUMNS = {
        'KYBER': ('kyber_public_key', []),
        'SM2': ('gm_public_key', []),
        'SSCL': ('sscl_public_key', []),
        'FALCON': ('falcon_sign_public_key', ['falcon_public_key']),
    }

    def store_node_public_key(self, algorithm: str, public_key: str,
                              security_level: str = None) -> Dict[str, Any]:
        """登记一个算法的**公钥**（文档 §4.4）。

        这是节点初始化的新入口：私钥在节点浏览器产生并留在那里，
        服务端**只收公钥**，既不生成也不持有。

        ⚠️ 编码口径：SM2 / SSCL / Falcon 存 **hex**（与既有列一致），
           Kyber 存 **base64** —— 因为 `wrappers.wrap_for_node` 是按
           `base64.b64decode(node.kyber_public_key)` 取的，且靠解码后的
           字节长度推断变体（pk_len_map）。这里统一从 hex 入参转换，
           免得调用方各传一套，错了要等到封装时才发现。
        """
        import base64 as _b64

        name = str(algorithm or '').strip().upper().replace('CL-', '')
        if name not in self._PUBLIC_KEY_COLUMNS:
            return {
                'success': False,
                'message': f'不支持的算法：{algorithm}（可选 {"/".join(self._PUBLIC_KEY_COLUMNS)}）',
            }

        value = str(public_key or '').strip()
        if not value:
            return {'success': False, 'message': '公钥为空'}

        column, extra_columns = self._PUBLIC_KEY_COLUMNS[name]
        if name == 'KYBER':
            try:
                raw = bytes.fromhex(value)
            except ValueError:
                return {'success': False, 'message': 'Kyber 公钥应为十六进制'}
            # 变体自描述：服务端按长度推断（与 wrappers.pk_len_map 同一口径）
            if len(raw) not in (800, 1184, 1568):
                return {
                    'success': False,
                    'message': f'Kyber 公钥长度 {len(raw)} 不是 800/1184/1568，无法确定变体',
                }
            stored = _b64.b64encode(raw).decode('utf-8')
        else:
            stored = value.lower()

        setattr(self.node, column, stored)
        for column_name in extra_columns:
            setattr(self.node, column_name, stored)

        fields = [column, *extra_columns]
        if security_level:
            level_field = 'kyber_security_level' if name == 'KYBER' else 'falcon_security_level'
            if hasattr(self.node, level_field):
                setattr(self.node, level_field, str(security_level).strip())
                fields.append(level_field)

        self.node.save(update_fields=fields)
        logger.info('节点 %s 登记 %s 公钥（长度 %d）', self.node_id, name, len(stored))
        return {'success': True, 'algorithm': name, 'message': f'{name} 公钥已登记'}

    def initialize_base_keys(self) -> Dict[str, Any]:
        """节点首次初始化的**收尾**（文档 §3.1 / §4.4）。

        ⚠️ 本方法在 §4.4 阶段一**改变了职责**：它**不再生成任何密钥**。
           私钥的产生已移到节点浏览器（`BrowserCryptoProvider`），
           服务端只在校验「四套公钥是否齐备」之后把状态置为 ACTIVE。

        为什么必须改：原先这里在服务端生成并落库四套**私钥**，与文档
        §0/§4「私钥留在节点侧，服务端只登记公钥」直接冲突 ——
        实测 `dvadmin_pqkds_nodes` 里就存着 Falcon 私钥 1.43MB 等材料。

        幂等与失败语义（与原实现一致，未改动）
        --------------------------------------
        * 已是 ACTIVE 的节点直接返回，不重复处理。
        * 公钥不齐即整体失败并**保持 PENDING_INIT**，允许节点补交后重试 ——
          比「齐了三套也算成功」安全：缺任何一套都算初始化未完成。
        """
        from django.utils import timezone

        if (self.node.status or '').lower() == 'active':
            return {
                'success': True,
                'already_initialized': True,
                'status': self.node.status,
                'message': '节点已完成初始化，无需重复生成',
            }

        self.node.refresh_from_db()

        # 落库校验：四套**公钥**必须都在。
        # 与原实现同一口径（原本查的也是公钥列），差别只在公钥现在来自节点侧。
        required = [
            ('Kyber', self.node.kyber_public_key),
            ('SM2', self.node.gm_public_key),
            ('SSCL', self.node.sscl_public_key),
            # Falcon 以签名公钥为准（那才是签名路径读的列）；
            # 兼容早期只写了 falcon_public_key 的节点。
            ('Falcon', self.node.falcon_sign_public_key or self.node.falcon_public_key),
        ]
        missing = [name for name, value in required if not value]
        if missing:
            logger.warning('节点 %s 初始化未完成，缺少公钥: %s', self.node_id, missing)
            return {
                'success': False,
                'status': self.node.status,
                'completed': [name for name, value in required if value],
                'message': '以下基础公钥尚未登记：' + '、'.join(missing) + '，请在节点侧完成生成后重试',
            }

        # 四套齐备 → ACTIVE（文档 §3.1）
        self.node.status = 'active'
        self.node.initialized_at = timezone.now()
        self.node.save(update_fields=['status', 'initialized_at'])

        # 上链（与旧 register_node 一致；失败不影响初始化结论）
        try:
            up = self.upload_service.upload_node_registration(self.node)
            if not up.get('success'):
                logger.warning('节点 %s 上链失败: %s', self.node_id, up.get('message'))
        except Exception as exc:  # noqa: BLE001
            logger.warning('节点 %s 上链异常: %s', self.node_id, exc)

        logger.info('节点 %s 公钥齐备，状态置为 ACTIVE', self.node_id)
        return {
            'success': True,
            'status': 'active',
            'completed': [name for name, _ in required],
            'message': '四套基础公钥齐备，初始化完成',
        }

    def generate_falcon_signing_keypair(self) -> Dict[str, Any]:
        """生成**标准** Falcon-512 签名密钥对（阶段 5 §6.2/§6.3）。

        与 `generate_falcon_keys_v2` 的区别要说清楚，否则会被当成重复实现：
          * `generate_falcon_keys_v2` → CL-Falcon 格材料（D_id/S_id 矩阵），
            是分发中节点腿的**封装目标**，与标准 DLL 不兼容；
          * 本方法 → NIST Falcon-512 **签名密钥**（pk 897B / sk 1281B），
            专用于对分发信封**签名/验签**（§6.3）。

        为什么必须分开：文档 §0.5 明确 Falcon 不再是"无证书算法"，
        而是标准签名算法。把签名与封装混在一个密钥上，
        会导致"拿签名密钥去解密"这类概念错误。

        幂等：已存在时不重新生成 —— 重新生成会让此前用旧私钥签发的信封
        全部验签失败，而调用方无从知道"是密钥换了"还是"信被篡改了"。
        """
        from .crypto_utils import FalconCrypto
        import base64

        if self.node is None:
            return {'success': False, 'message': f'节点 {self.node_id} 不存在'}

        if self.node.falcon_sign_public_key and self.node.falcon_sign_private_key:
            return {'success': True, 'already_exists': True,
                    'message': '标准 Falcon 签名密钥已存在，未重新生成'}

        try:
            crypto = FalconCrypto(512)
            pk, sk = crypto.generate_keypair()
            if len(pk) != crypto.public_key_bytes or len(sk) != crypto.secret_key_bytes:
                return {'success': False,
                        'message': f'生成的密钥长度异常：pk={len(pk)} sk={len(sk)}'}

            # 用 update_fields 定向写入，不用 self.node.save() ——
            # 后者是整行覆盖，会把同一次初始化里前面几步写好的密钥字段
            # 用内存里的旧值冲掉（阶段 2 踩过一次同类问题）。
            Node.objects.filter(node_id=self.node_id).update(
                falcon_sign_public_key=base64.b64encode(pk).decode('ascii'),
                falcon_sign_private_key=base64.b64encode(sk).decode('ascii'),
            )
            self.node.refresh_from_db()
            logger.info('节点 %s 标准 Falcon-512 签名密钥已生成', self.node_id)
            return {'success': True, 'message': '标准 Falcon 签名密钥生成成功'}
        except Exception as exc:  # noqa: BLE001
            logger.error('节点 %s 标准 Falcon 签名密钥生成失败: %s', self.node_id, exc)
            return {'success': False, 'message': f'生成失败: {exc}'}

    @ensure_db_connection
    def generate_falcon_keypair(self) -> Dict[str, Any]:
        try:
            import time
            logger.info(f"开始为节点 {self.node_id} 生成Falcon密钥对")

            if self.node is None:
                return {
                    'success': False,
                    'message': f'节点 {self.node_id} 不存在'
                }

            if not self.node.kyber_public_key:
                return {
                    'success': False,
                    'message': f'节点 {self.node_id} 还未生成Kyber密钥对，请先完成Kyber密钥生成'
                }

            # 获取节点的 Falcon 安全级别
            security_level = int(getattr(self.node, 'falcon_security_level', '512') or '512')
            logger.info(f"节点 {self.node_id} Falcon安全级别: {security_level}")

            # Falcon 密钥生成包含大矩阵乘法，Falcon-1024 尤其耗时。
            # 在长时间 CPU 计算前主动关闭数据库连接，防止 MySQL 空闲超时断开。
            connection.close()
            logger.info(f"[DB] Falcon密钥生成前关闭数据库连接")

            falcon_start_time = time.time()
            falcon_kp = self.keygen_service.generate_falcon_keypair(
                self.node_id, security_level=security_level
            )
            falcon_end_time = time.time()
            falcon_duration = falcon_end_time - falcon_start_time

            # CPU 计算完成，强制重建数据库连接
            _force_reconnect_db()
            logger.info(f"[DB] Falcon密钥生成完成({falcon_duration:.2f}s)，数据库连接已重新建立")

            if falcon_kp['success']:
                # 将公钥数据序列化为包含参数信息的 JSON
                falcon_pk_data = {
                    'U_id': falcon_kp['public_key'],
                    'H_id': falcon_kp.get('H_id'),
                    'A': falcon_kp.get('A'),
                    'B': falcon_kp.get('B'),
                    'algorithm': falcon_kp.get('algorithm', f'CertificatelessFalcon-{security_level}'),
                    'security_level': security_level,
                    'node_id': self.node_id,
                    'parameters': falcon_kp.get('parameters', {
                        'n': 512 if security_level == 512 else 1024,
                        'm': 1024 if security_level == 512 else 2048,
                        'q': 12289
                    })
                }
                falcon_public_key_b64 = compress_key_data(base64.b64encode(
                    json.dumps(falcon_pk_data).encode('utf-8')
                ).decode('utf-8'))

                # 将私钥数据序列化为包含参数信息的 JSON
                falcon_sk_data = {
                    'D_id': falcon_kp['private_key']['D_id'],
                    'S_id': falcon_kp['private_key']['S_id'],
                    'algorithm': f'CertificatelessFalcon-{security_level}',
                    'security_level': security_level,
                    'node_id': self.node_id,
                    'parameters': falcon_kp.get('parameters', {
                        'n': 512 if security_level == 512 else 1024,
                        'm': 1024 if security_level == 512 else 2048,
                        'q': 12289
                    })
                }
                falcon_private_key_b64 = compress_key_data(base64.b64encode(
                    json.dumps(falcon_sk_data).encode('utf-8')
                ).decode('utf-8'))

                keygen_time = timezone.now()

                logger.info(
                    f"节点 {self.node_id} 无证书Falcon-{security_level}密钥对生成成功，"
                    f"耗时: {falcon_duration:.4f}秒"
                )
            else:
                logger.error(f"节点 {self.node_id} Falcon密钥生成失败: {falcon_kp.get('error')}")
                return {
                    'success': False,
                    'message': f"Falcon密钥生成失败: {falcon_kp.get('error')}"
                }

            # 逐字段写入，避免单条 UPDATE 超过 max_allowed_packet。
            #
            # ⚠️ 这里**不再写 falcon_lattice_params**（2026-09-26）。
            # 该列实测 10.2MB/节点，而全仓库没有任何读取方 —— 只有两个打印长度的
            # 排障命令 fix_all_falcon_keys / fix_node_005_falcon 引用过它。
            # 它的内容（D_id/S_id/H_id 与格参数）本来就重复自 falcon_private_key
            # 与 KGC 部分私钥。写它是纯粹的浪费：实测写库 11 秒里它占了大头，
            # 而 Falcon 计算本身只要 1.9 秒。
            # 模型字段保留、历史数据保留，只是不再产生新的。
            _safe_update_node(self.node_id,
                falcon_public_key=falcon_public_key_b64)
            _safe_update_node(self.node_id,
                falcon_private_key=falcon_private_key_b64)
            _safe_update_node(self.node_id,
                falcon_keygen_time=keygen_time,
                falcon_keygen_duration=falcon_duration,
                status='falcon_generated')

            try:
                self.node = Node.objects.get(node_id=self.node_id)
                upload_result = self.upload_service.upload_node_registration(self.node)
                if upload_result['success']:
                    _safe_update_node(self.node_id, status='active')
                    self.node.status = 'active'
                    logger.info(f"节点 {self.node_id} Falcon公钥已上链")
                else:
                    logger.warning(f"节点 {self.node_id} Falcon上链失败: {upload_result.get('message')}")
            except Exception as e:
                logger.warning(f"节点 {self.node_id} Falcon上链异常: {e}")

            return {
                'success': True,
                'message': f'节点 {self.node_id} 无证书Falcon-{security_level}密钥对生成成功，耗时: {falcon_duration:.4f}秒',
                'node_id': self.node_id,
                'status': 'active',
                'security_level': security_level,
                'kyber_keygen_time': self.node.kyber_keygen_time.isoformat() if self.node.kyber_keygen_time else None,
                'kyber_keygen_duration': round(self.node.kyber_keygen_duration, 4) if self.node.kyber_keygen_duration else None,
                'falcon_keygen_time': self.node.falcon_keygen_time.isoformat() if self.node.falcon_keygen_time else None,
                'falcon_keygen_duration': round(self.node.falcon_keygen_duration, 4) if self.node.falcon_keygen_duration else None
            }

        except Exception as e:
            logger.error(f"节点 {self.node_id} Falcon密钥生成异常: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': f'Falcon密钥生成失败: {str(e)}'
            }

    def initiate_session_key_exchange(self, target_id: str, expires_at=None) -> Dict[str, Any]:
        """
        发起 aes_falcon 会话密钥交换。
        使用无证书 Falcon 格密码方案加密 AES 会话密钥。

        流程：
        1. 生成随机 AES 会话密钥 (32字节)
        2. 获取目标节点的 Falcon 公钥
        3. 使用 CertificatelessFalconEncryption.encrypt 加密 AES 密钥
        4. 存储: encrypted_session_key = Falcon 格密码密文
        5. key_exchange_data 中存储加密元数据（不含明文密钥）
        """
        try:
            initiator_id = self.node_id
            logger.info(f"节点 {initiator_id} 向 {target_id} 发起Falcon格密码会话密钥交换")

            try:
                initiator_node = Node.objects.get(node_id=initiator_id)
            except Node.DoesNotExist:
                logger.error(f"发起节点 {initiator_id} 不存在")
                return {'success': False, 'message': f'发起节点 {initiator_id} 不存在'}

            try:
                target_node = Node.objects.get(node_id=target_id)
            except Node.DoesNotExist:
                logger.error(f"目标节点 {target_id} 不存在")
                return {'success': False, 'message': f'目标节点 {target_id} 不存在'}

            # 检查目标节点是否有 Falcon 公钥
            if not target_node.falcon_public_key:
                logger.error(f"目标节点 {target_id} 没有Falcon公钥")
                return {'success': False, 'message': f'目标节点 {target_id} 没有Falcon公钥，请先生成Falcon密钥'}

            if expires_at is None:
                expires_at = timezone.now() + timezone.timedelta(hours=24)
            elif isinstance(expires_at, str):
                try:
                    iso_str = expires_at.strip()
                    if iso_str.endswith('Z'):
                        iso_str = iso_str[:-1]
                    expires_at = timezone.datetime.fromisoformat(iso_str)
                except (ValueError, TypeError) as e:
                    logger.warning(f"无法解析过期时间 {expires_at}: {e}，使用默认24小时")
                    expires_at = timezone.now() + timezone.timedelta(hours=24)

            import hashlib
            import time
            import base64
            import json as _json
            import os

            timestamp = str(int(time.time() * 1000))
            session_hash_input = f"{initiator_id}_{target_id}_{timestamp}"
            session_hash = hashlib.sha256(session_hash_input.encode()).hexdigest()[:32]
            session_id = f"sess_{session_hash}"

            # Step 1: 生成随机会话密钥 —— D3 后是 SM4 的 16 字节（原为 AES-256 的 32 字节）
            aes_key = PayloadCipher.generate_key()
            logger.info(f"生成 SM4 会话密钥: {len(aes_key)} bytes")

            # Step 2: 获取目标节点安全级别并初始化 Falcon 加密
            target_security_level = int(getattr(target_node, 'falcon_security_level', '512') or '512')
            from .falcon_aes_session_encryption import FalconAESSessionKeyEncryption
            falcon_enc = FalconAESSessionKeyEncryption(security_level=target_security_level)

            # Step 3: 使用 Falcon 格密码加密 AES 密钥
            enc_result = falcon_enc.encrypt_aes_key_with_falcon(
                recipient_id=target_id,
                aes_key=aes_key,
                recipient_public_key_b64=target_node.falcon_public_key
            )

            if not enc_result['success']:
                logger.error(f"Falcon格密码加密AES密钥失败: {enc_result.get('message')}")
                return {'success': False, 'message': f"Falcon加密失败: {enc_result.get('message')}"}

            logger.info(f"AES密钥已使用Falcon-{target_security_level}格密码加密")

            # Step 4: 构造密钥交换数据（不含明文密钥）
            key_exchange_data = {
                'algorithm': f'CertificatelessFalcon-{target_security_level}',
                'security_level': target_security_level,
                'initiator': initiator_id,
                'target': target_id,
                'timestamp': timestamp,
                'session_key_length': len(aes_key),
                'encrypted_by': 'falcon_lattice_encryption'
            }

            # encrypted_session_key 存储 Falcon 格密码密文
            encrypted_session_key = enc_result['ciphertext']

            session_key = SessionKey.objects.create(
                session_id=session_id,
                node1=initiator_node,
                node2=target_node,
                status='initiated',
                expires_at=expires_at,
                key_exchange_data=_json.dumps(key_exchange_data, ensure_ascii=False),
                encrypted_session_key=encrypted_session_key,
                session_type='aes_falcon'
            )

            logger.info(f"会话密钥 {session_key.id} 创建成功，session_id: {session_id}，加密方式: Falcon-{target_security_level}")

            return {
                'success': True,
                'message': f'会话密钥交换已发起 (Falcon-{target_security_level}格密码加密)',
                'session_id': session_id,
                'security_level': target_security_level,
                'expires_at': expires_at.isoformat()
            }

        except Exception as e:
            logger.error(f"会话密钥交换异常: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'message': f'会话密钥交换失败: {str(e)}'}

    def initiate_kyber_key_agreement(self, target_id: str, expires_at=None) -> Dict[str, Any]:
        """
        发起Kyber无证书格密码密钥协商。

        使用图中的 Enc 算法:
          c₁ = Aᵗ · r + e₁          (mod q)
          c₂ = uᵗ · r + e₂ + ⌊q/2⌋·M  (mod q)

        流程：
        1. 生成随机AES会话密钥 (32字节)
        2. 从目标节点的 kyber_partial_key_data 中获取无证书公钥 u 和系统参数 A
        3. 使用无证书格密码 Enc 加密 AES 密钥（逐比特向量化）
        4. 存储密文到 encrypted_session_key
        """
        try:
            logger.info(f"节点 {self.node_id} 向 {target_id} 发起Kyber无证书格密码密钥协商")

            try:
                initiator_node = Node.objects.get(node_id=self.node_id)
            except Node.DoesNotExist:
                return {'success': False, 'message': f'发起节点 {self.node_id} 不存在'}

            try:
                target_node = Node.objects.get(node_id=target_id)
            except Node.DoesNotExist:
                return {'success': False, 'message': f'目标节点 {target_id} 不存在'}

            if not target_node.kyber_partial_key_data:
                return {'success': False, 'message': f'目标节点 {target_id} 没有无证书Kyber密钥数据'}

            if expires_at is None:
                expires_at = timezone.now() + timezone.timedelta(hours=24)
            elif isinstance(expires_at, str):
                try:
                    iso_str = expires_at.strip()
                    if iso_str.endswith('Z'):
                        iso_str = iso_str[:-1]
                    expires_at = timezone.datetime.fromisoformat(iso_str)
                except (ValueError, TypeError) as e:
                    logger.warning(f"无法解析过期时间 {expires_at}: {e}，使用默认24小时")
                    expires_at = timezone.now() + timezone.timedelta(hours=24)

            import hashlib
            import time
            import json as _json
            import os
            from .kyber_fast_engine import (
                kyber_fast_encrypt, _serialize_kyber_ct, _KyberCLKeyCache
            )

            timestamp = str(int(time.time() * 1000))
            session_hash_input = f"{self.node_id}_{target_id}_{timestamp}"
            session_hash = hashlib.sha256(session_hash_input.encode()).hexdigest()[:32]
            session_id = f"sess_{session_hash}"

            # 第1步: 生成随机会话密钥 —— D3 后是 SM4 的 16 字节
            aes_session_key = PayloadCipher.generate_key()
            logger.info(f"[KyberCL] 生成 SM4 会话密钥: {len(aes_session_key)} bytes")

            # 第2步: 从无证书密钥数据中获取 A 和 u (公钥)
            cl_pk = _KyberCLKeyCache.get_cl_public_key(target_node.kyber_partial_key_data)
            A = cl_pk['A']
            u = cl_pk['u']
            n, m, q = cl_pk['n'], cl_pk['m'], cl_pk['q']
            logger.info(f"[KyberCL] 无证书公钥: n={n}, m={m}, q={q}")

            # 第3步: 使用图中 Enc 算法加密 AES 密钥
            ct = kyber_fast_encrypt(A, u, aes_session_key, n, m, q, 1.17)
            encrypted_session_key_str = _serialize_kyber_ct(ct)
            logger.info(f"[KyberCL] 格密码加密完成，密文大小: {len(encrypted_session_key_str)} 字符")

            # 第4步: key_exchange_data
            key_exchange_data = {
                'initiator': self.node_id,
                'target': target_id,
                'timestamp': timestamp,
                'protocol': 'kyber_cl_lattice_enc',
            }

            session_key = SessionKey.objects.create(
                session_id=session_id,
                node1=initiator_node,
                node2=target_node,
                status='initiated',
                expires_at=expires_at,
                key_exchange_data=_json.dumps(key_exchange_data, ensure_ascii=False),
                encrypted_session_key=encrypted_session_key_str,
                session_type='kyber_kem'
            )

            logger.info(
                f"[KyberCL] 会话 {session_key.id} 创建成功, "
                f"session_id: {session_id}"
            )

            return {
                'success': True,
                'message': 'Kyber无证书格密码密钥协商已发起',
                'session_id': session_id,
                'expires_at': expires_at.isoformat(),
                'kem_algorithm': 'CertificatelessKyber_Lattice_Enc',
            }

        except Exception as e:
            logger.error(f"Kyber KEM密钥协商异常: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'message': f'Kyber KEM密钥协商失败: {str(e)}'}

    @ensure_db_connection
    def generate_gm_keys(self) -> Dict[str, Any]:
        """给节点生成**国密密钥对**（SM2 与 SSCL 各一对）。

        为什么需要（2026-09-26）：节点腿原本只有抗量子（Kyber/Falcon），
        于是"这次分发不用抗量子"在界面上无路可走。生成国密密钥后，
        用户在「密钥分发」里可选「国密 SM2」或「国密 SSCL」，节点腿即走国密。

        实现要点：
          * 复用本仓库自带的 `sm2_crypto`（用户腿的 SM2/SSCL 封装也是它），不引入新依赖；
          * 私钥是一个 32 字节标量，必须落在 [1, n-1] 内 —— 直接取随机 32 字节
            有极小概率超出曲线阶，所以按 n 取模后 +1；
          * **SSCL 与 SM2 用同一套曲线运算**（见 wrappers.py 里 SsclWrapper 的说明：
            d_A 是 sm2p256v1 上的标量、P_A 是同一曲线上的点，差别只在密钥怎么派生），
            所以这里生成的形状一致，只是分别存到两组字段里，互不混用。
        """
        import secrets
        import time
        from .sm2_crypto import SM2Crypto, SM2_CURVE

        if self.node is None:
            return {'success': False, 'message': f'节点 {self.node_id} 不存在'}

        started = time.time()
        order = int(SM2_CURVE.n)

        def new_pair() -> tuple:
            scalar = secrets.randbelow(order - 1) + 1  # 1 <= d <= n-1
            private_hex = '%064x' % scalar
            public_hex = SM2Crypto.public_key_of(private_hex)
            if not SM2Crypto.is_valid_public_key(public_hex):
                raise ValueError('生成的公钥未通过曲线校验')
            return private_hex, public_hex

        try:
            gm_private, gm_public = new_pair()
            sscl_private, sscl_public = new_pair()
        except Exception as exc:  # noqa: BLE001
            logger.error(f"节点 {self.node_id} 国密密钥生成失败: {exc}")
            return {'success': False, 'message': f'国密密钥生成失败: {exc}'}

        self.node.gm_public_key = gm_public
        self.node.gm_private_key = gm_private
        self.node.gm_keygen_time = timezone.now()
        self.node.sscl_public_key = sscl_public
        self.node.sscl_private_key = sscl_private
        self.node.save(update_fields=[
            'gm_public_key', 'gm_private_key', 'gm_keygen_time',
            'sscl_public_key', 'sscl_private_key',
        ])

        duration = time.time() - started
        logger.info(f"节点 {self.node_id} 国密密钥生成成功（SM2 + SSCL），耗时: {duration:.4f}秒")
        return {
            'success': True,
            'message': f'国密密钥对生成成功（SM2 + SSCL），耗时: {duration:.4f}秒',
            'node_id': self.node_id,
            'public_key': gm_public,
            'sscl_public_key': sscl_public,
            'public_key_length': len(gm_public),
            'duration_sec': round(duration, 4),
        }

    def generate_falcon_keys_v2(self) -> Dict[str, Any]:
        try:
            import time
            from .kgc_service import KGCService
            logger.info(f"节点 {self.node_id} 生成无证书Falcon密钥对 (V2方案 - 基于KGC部分私钥)")

            if self.node is None:
                return {'success': False, 'message': f'节点 {self.node_id} 不存在'}

            # 获取节点的 Falcon 安全级别
            security_level = int(getattr(self.node, 'falcon_security_level', '512') or '512')
            logger.info(f"节点 {self.node_id} Falcon安全级别: Falcon-{security_level}")

            # 第一步：调用KGC生成Falcon部分私钥
            logger.info(f"第一步：调用KGC为节点 {self.node_id} 生成Falcon部分私钥")
            kgc_service = KGCService()
            kgc_result = kgc_service.generate_and_save_falcon_partial_key(self.node_id)

            if not kgc_result['success']:
                logger.error(f"KGC生成Falcon部分私钥失败: {kgc_result.get('message')}")
                return {
                    'success': False,
                    'message': f"KGC生成Falcon部分私钥失败: {kgc_result.get('message')}"
                }

            logger.info(f"KGC已为节点 {self.node_id} 生成Falcon部分私钥")

            # 刷新节点对象以获取最新的部分私钥数据
            self.node.refresh_from_db()

            # 第二步：节点使用部分私钥生成完整的Falcon公私钥对
            logger.info(f"第二步：节点 {self.node_id} 使用部分私钥生成完整Falcon-{security_level}密钥对")
            falcon_start_time = time.time()

            # 从数据库获取部分私钥数据
            if not self.node.falcon_partial_key_data:
                logger.error(f"节点 {self.node_id} 的Falcon部分私钥数据为空")
                return {
                    'success': False,
                    'message': f"节点 {self.node_id} 的Falcon部分私钥数据为空"
                }

            try:
                falcon_partial_data = json.loads(self.node.falcon_partial_key_data)
                logger.info(f"成功解析Falcon部分私钥数据")
            except Exception as e:
                logger.error(f"解析Falcon部分私钥数据失败: {e}")
                return {
                    'success': False,
                    'message': f"解析Falcon部分私钥数据失败: {str(e)}"
                }

            # 从KGC部分私钥中提取D_id和H_id
            # falcon_partial_data 结构:
            #   { partial_key: base64(json{D_id, H_id, node_id, algorithm, parameters}), ... }
            partial_key_b64 = falcon_partial_data.get('partial_key')
            if not partial_key_b64:
                logger.error(f"节点 {self.node_id} 的Falcon部分私钥中缺少partial_key字段")
                return {
                    'success': False,
                    'message': f"Falcon部分私钥数据格式错误: 缺少partial_key字段"
                }

            try:
                partial_key_inner = decode_falcon_partial_key(partial_key_b64)
                D_id_list = partial_key_inner['D_id']
                H_id_list = partial_key_inner['H_id']
                A_list = partial_key_inner.get('A')
                B_list = partial_key_inner.get('B')
                logger.info(
                    f"成功提取KGC部分私钥: D_id维度={len(D_id_list)}x{len(D_id_list[0]) if D_id_list else 0}, "
                    f"H_id维度={len(H_id_list)}x{len(H_id_list[0]) if H_id_list else 0}, "
                    f"A={'有' if A_list else '无'}, B={'有' if B_list else '无'}"
                )
            except Exception as e:
                logger.error(f"解析Falcon部分私钥内部数据失败: {e}")
                return {
                    'success': False,
                    'message': f"Falcon部分私钥内部数据解析失败: {str(e)}"
                }

            # 使用KGC的部分私钥(D_id, H_id, A, B)完成密钥生成
            # 内部执行: SetSecretValue → S_id, SetSK(D_id, S_id), SetPK(S_id) → U_id
            # 注意: Falcon-1024 的矩阵乘法 (1024×2048)×(2048×2048) 耗时较长，
            # 在此期间 MySQL 连接空闲可能超时断开。
            # 因此在长时间 CPU 计算前主动关闭连接，计算完成后再重新建立。
            connection.close()
            logger.info(f"[DB] 长时间CPU计算前主动关闭数据库连接")

            falcon_kp = self.keygen_service.complete_falcon_keygen_with_partial_key(
                node_id=self.node_id,
                D_id_list=D_id_list,
                H_id_list=H_id_list,
                A_list=A_list,
                B_list=B_list,
                security_level=security_level
            )
            falcon_end_time = time.time()
            falcon_duration = falcon_end_time - falcon_start_time

            # CPU 计算完成，强制重建数据库连接
            _force_reconnect_db()
            logger.info(f"[DB] CPU计算完成，数据库连接已重新建立")

            if falcon_kp['success']:
                logger.info(f"节点 {self.node_id} 使用部分私钥成功生成完整Falcon-{security_level}密钥对，耗时: {falcon_duration:.4f}秒")

                # 获取参数信息
                kp_params = falcon_kp.get('parameters', {
                    'n': 512 if security_level == 512 else 1024,
                    'm': 1024 if security_level == 512 else 2048,
                    'q': 12289
                })

                # 序列化 Falcon 公钥（包含系统参数A、B和H_id，加密时需要）
                falcon_pk_data = {
                    'U_id': falcon_kp['public_key'],
                    'H_id': falcon_kp.get('H_id'),
                    'A': falcon_kp.get('A'),
                    'B': falcon_kp.get('B'),
                    'algorithm': f'CertificatelessFalcon-{security_level}',
                    'security_level': security_level,
                    'node_id': self.node_id,
                    'parameters': kp_params
                }
                falcon_public_key_b64 = compress_key_data(base64.b64encode(
                    json.dumps(falcon_pk_data).encode('utf-8')
                ).decode('utf-8'))

                # 序列化 Falcon 私钥
                falcon_private_key_data = {
                    'D_id': falcon_kp['private_key']['D_id'],
                    'S_id': falcon_kp['private_key']['S_id'],
                    'algorithm': f'CertificatelessFalcon-{security_level}',
                    'security_level': security_level,
                    'node_id': self.node_id,
                    'parameters': kp_params
                }
                falcon_private_key_b64 = compress_key_data(base64.b64encode(
                    json.dumps(falcon_private_key_data).encode('utf-8')
                ).decode('utf-8'))

                keygen_time = timezone.now()
                has_kyber = bool(self.node.kyber_public_key)

                # 逐字段写入，避免单条 UPDATE 超过 max_allowed_packet
                logger.info(f"[DB] 开始逐字段写入Falcon-{security_level}密钥数据...")
                _safe_update_node(self.node_id,
                    falcon_public_key=falcon_public_key_b64)
                logger.info(f"[DB] falcon_public_key 写入完成 ({len(falcon_public_key_b64)} chars)")
                _safe_update_node(self.node_id,
                    falcon_private_key=falcon_private_key_b64)
                logger.info(f"[DB] falcon_private_key 写入完成 ({len(falcon_private_key_b64)} chars)")
                # ⚠️ 这里**不再写 falcon_lattice_params**（2026-09-26）。
                # 该列实测 10.2MB/节点，而全仓库没有任何读取方 —— 只有两个打印长度的
                # 排障命令 fix_all_falcon_keys / fix_node_005_falcon 引用过它，
                # 它的内容（D_id/S_id/H_id 与格参数）本就重复自 falcon_private_key
                # 与 KGC 部分私钥。实测写库 11 秒里它占大头，而 Falcon 计算本身只要 1.9 秒。
                # 模型字段保留、历史数据保留，只是不再产生新的。
                _safe_update_node(self.node_id,
                    falcon_keygen_time=keygen_time,
                    falcon_keygen_duration=falcon_duration,
                    status='falcon_generated',
                    partial_key_received=has_kyber)
                logger.info(f"节点 {self.node_id} 无证书Falcon-{security_level}密钥对生成成功，耗时: {falcon_duration:.4f}秒")

                # 刷新 ORM 对象
                self.node.refresh_from_db()

                # 上传到区块链
                try:
                    # 重新获取节点对象
                    self.node = Node.objects.get(node_id=self.node_id)
                    upload_result = self.upload_service.upload_node_registration(self.node)
                    if upload_result['success']:
                        Node.objects.filter(node_id=self.node_id).update(status='active')
                        self.node.status = 'active'
                        logger.info(f"节点 {self.node_id} Falcon公钥已上链")
                    else:
                        logger.warning(f"节点 {self.node_id} Falcon上链失败: {upload_result.get('message')}")
                except Exception as e:
                    logger.warning(f"节点 {self.node_id} Falcon上链异常: {e}")

                return {
                    'success': True,
                    'message': f'无证书Falcon-{security_level}密钥对生成成功，耗时: {falcon_duration:.4f}秒',
                    'public_key': falcon_kp['public_key'],
                    'private_key': falcon_private_key_data,
                    'security_level': security_level,
                    'falcon_keygen_duration': round(falcon_duration, 4),
                    'falcon_keygen_time': self.node.falcon_keygen_time.isoformat() if self.node.falcon_keygen_time else None,
                    'kyber_keygen_duration': round(self.node.kyber_keygen_duration, 4) if self.node.kyber_keygen_duration else None,
                    'kyber_keygen_time': self.node.kyber_keygen_time.isoformat() if self.node.kyber_keygen_time else None,
                    'node_id': self.node_id,
                    'status': self.node.status,
                    'partial_key_received': self.node.partial_key_received
                }
            else:
                logger.error(f"节点 {self.node_id} Falcon密钥生成失败: {falcon_kp.get('error')}")
                return {
                    'success': False,
                    'message': f"Falcon密钥生成失败: {falcon_kp.get('error')}"
                }

        except Exception as e:
            logger.error(f"节点 {self.node_id} Falcon密钥生成异常: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'message': f'Falcon密钥生成失败: {str(e)}'}

    def get_node_key_version_info(self) -> Dict[str, Any]:
        try:
            logger.info(f"查询节点 {self.node_id} 的密钥版本信息")

            if self.node is None:
                return {'success': False, 'message': f'节点 {self.node_id} 不存在'}

            from .models import NodeKeyVersion

            try:
                key_version = NodeKeyVersion.objects.get(node=self.node)
            except NodeKeyVersion.DoesNotExist:
                key_version = NodeKeyVersion.objects.create(
                    node=self.node,
                    kyber_version=1,
                    falcon_version=1,
                    kyber_public_key_hash='',
                    falcon_public_key_hash=''
                )

            return {
                'success': True,
                'message': '密钥版本信息查询成功',
                'node_id': self.node_id,
                'kyber_version': key_version.kyber_version,
                'falcon_version': key_version.falcon_version,
                'kyber_public_key_hash': key_version.kyber_public_key_hash,
                'falcon_public_key_hash': key_version.falcon_public_key_hash
            }

        except Exception as e:
            logger.error(f"查询节点 {self.node_id} 密钥版本信息异常: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'message': f'查询失败: {str(e)}'}

    def encrypt_message(self, message: str, recipient_public_key: str) -> str:
        """把一个字符串"加密"成 JSON 信封。

        ⚠️ 诚实说明：本方法**并不提供机密性**，历史实现如此，本次只做了算法替换：
          1. 随机密钥被**明文放在同一个信封里**（`key` 字段），拿到信封即可解密；
          2. 调用方 `chat_views.send_message` 还把 `message_content` 原文一并落库。
        因此这里的 `encrypted_message` 只是演示用的封装，不是安全边界。
        若要真正加密，应当用 `recipient_public_key` 做 KEM 封装而不是自带密钥。

        载荷层按 D3 换成 SM4（16 字节，原为 AES-256 的 32 字节）。
        """
        try:
            logger.info(f"节点 {self.node_id} 加密消息")

            import json as _json

            if isinstance(recipient_public_key, str):
                try:
                    recipient_public_key = _json.loads(recipient_public_key)
                except (ValueError, TypeError):
                    pass

            key = PayloadCipher.generate_key()
            ciphertext, nonce_tag = SM4Crypto.encrypt(message.encode('utf-8'), key)

            encrypted_data = {
                'ciphertext': base64.b64encode(ciphertext).decode('utf-8'),
                'nonce': base64.b64encode(nonce_tag[:GCM_IV_BYTES]).decode('utf-8'),
                'key': base64.b64encode(key).decode('utf-8'),
            }

            return json.dumps(encrypted_data)

        except Exception as e:
            logger.error(f"节点 {self.node_id} 消息加密异常: {e}")
            import traceback
            traceback.print_exc()
            return json.dumps({'error': str(e)})

    @property
    def real_aes(self):
        """会话消息的载荷加解密器（SM4-GCM）。

        ⚠️ 名字是历史遗留。实现已切到 `PayloadCipher`，因此：
          - 新会话（池里的载荷密钥是 16 字节 SM4）可直接使用；
          - 历史会话（32 字节 AES 密钥）按长度自动分派到旧 AES-256-GCM，
            仍能解开。
        历史实现硬性要求 `len(key) >= 32`，那在 SM4 落地后会直接抛
        "AES密钥长度不足" —— 这正是本次必须一起改掉的地方。
        """

        class PayloadEncryptor:
            @staticmethod
            def encrypt(plaintext: bytes, key: bytes) -> tuple:
                """返回 `(ciphertext, nonce_tag)`。

                新信封：`ciphertext` 是**纯密文**，`nonce_tag = iv(12) || tag(16)`。
                （历史实现返回的是 `(ct||tag, nonce(12))`，见 decrypt 的兼容分支。）
                """
                if not key:
                    raise ValueError("载荷密钥为空")
                # 不做长度硬校验：由 PayloadCipher 按长度分派，
                # 长度非法时它会抛出明确的 ValueError。
                return PayloadCipher.encrypt(plaintext, key)

            @staticmethod
            def decrypt(ciphertext: bytes, key: bytes, nonce: bytes) -> bytes:
                if not key:
                    raise ValueError("载荷密钥为空")

                # ---- 历史信封兼容 ----
                # 旧实现用的是 cryptography 的 AESGCM：`encrypt` 返回 `nonce(12)`，
                # 而 tag 被**追加在密文尾部**，落库形状是
                #     {'ciphertext': ct||tag, 'nonce': <12 字节>, 'alg': 'AES-256-GCM'}
                # 这与本模块新信封（纯密文 + nonce_tag）不同，必须分开处理，
                # 否则存量会话消息会以 "nonce_tag 长度非法" 解不开。
                if len(key) == LEGACY_AES_KEY_BYTES and len(nonce) == 12:
                    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

                    return AESGCM(key).decrypt(nonce, ciphertext, None)

                # 新信封：SM4（12+16）或历史 AES 的 nonce_tag（16+16）
                return PayloadCipher.decrypt(ciphertext, key, nonce)

        return PayloadEncryptor()

    def update_kyber_keys(self, security_level: int = 512) -> Dict[str, Any]:
        """
        更新Kyber密钥 - 使用高效的密钥生成方法，并调用KGC生成部分私钥
        """
        try:
            import time
            from .kgc_service import KGCService
            logger.info(f"节点 {self.node_id} 更新Kyber密钥，安全级别: {security_level}")

            if self.node is None:
                return {'success': False, 'message': f'节点 {self.node_id} 不存在'}

            # 第一步：调用KGC生成Kyber部分私钥
            logger.info(f"第一步：调用KGC为节点 {self.node_id} 生成Kyber部分私钥")
            kgc_service = KGCService()
            kgc_result = kgc_service.generate_and_save_kyber_partial_key(self.node_id)

            if not kgc_result['success']:
                logger.error(f"KGC生成Kyber部分私钥失败: {kgc_result.get('message')}")
                return {
                    'success': False,
                    'message': f"KGC生成Kyber部分私钥失败: {kgc_result.get('message')}"
                }

            logger.info(f"KGC已为节点 {self.node_id} 生成Kyber部分私钥")

            # 刷新节点对象以获取最新的部分私钥数据
            self.node.refresh_from_db()

            # 第二步：节点使用KGC部分私钥生成完整的Kyber公私钥对
            logger.info(f"第二步：节点 {self.node_id} 使用KGC部分私钥生成完整Kyber密钥对")
            kyber_start_time = time.time()

            # 从数据库获取KGC存入的部分私钥数据
            if not self.node.kyber_partial_key_data:
                logger.error(f"节点 {self.node_id} 的Kyber部分私钥数据为空")
                return {
                    'success': False,
                    'message': f"节点 {self.node_id} 的Kyber部分私钥数据为空"
                }

            try:
                kyber_partial_data = json.loads(self.node.kyber_partial_key_data)
                logger.info(f"成功解析Kyber部分私钥数据")
            except Exception as e:
                logger.error(f"解析Kyber部分私钥数据失败: {e}")
                return {
                    'success': False,
                    'message': f"解析Kyber部分私钥数据失败: {str(e)}"
                }

            # 提取KGC的部分私钥: t_id, c_id, u_prime_id
            partial_key_t = kyber_partial_data.get('partial_key_t')
            hash_c = kyber_partial_data.get('hash_c')
            u_prime_id = kyber_partial_data.get('u_prime_id')

            if partial_key_t is None or hash_c is None or u_prime_id is None:
                logger.error(f"节点 {self.node_id} 的Kyber部分私钥数据不完整")
                return {
                    'success': False,
                    'message': f"Kyber部分私钥数据不完整: 缺少t_id/c_id/u_prime_id"
                }

            logger.info(
                f"提取KGC部分私钥: t_id维度={len(partial_key_t)}, "
                f"c_id维度={len(hash_c)}, u_prime_id维度={len(u_prime_id)}"
            )

            # 使用KGC的部分私钥完成密钥生成
            # 内部执行: SetSecretValue → s_id, SetSK(t, s_id), SetPK(u_prime_id, c, s_id), DLL桥接
            kyber_kp = self.keygen_service.complete_kyber_keygen_with_partial_key(
                node_id=self.node_id,
                partial_key_t=partial_key_t,
                hash_c=hash_c,
                u_prime_id=u_prime_id
            )
            kyber_end_time = time.time()
            kyber_duration = kyber_end_time - kyber_start_time

            if kyber_kp['success']:
                logger.info(f"节点 {self.node_id} 使用部分私钥成功生成完整Kyber密钥对，耗时: {kyber_duration:.4f}秒")

                # 融合模块返回的是标准Kyber DLL格式的bytes密钥对
                kyber_pk = kyber_kp['kyber_public_key']
                kyber_sk = kyber_kp['kyber_private_key']
                self.node.kyber_public_key = base64.b64encode(kyber_pk).decode('utf-8')
                self.node.kyber_private_key = base64.b64encode(kyber_sk).decode('utf-8')

                # 保存Kyber部分私钥信息，标记来源为KGC
                self.node.kyber_partial_key_data = json.dumps({
                    'partial_key_t': kyber_kp.get('partial_key_t'),
                    'secret_value_s_id': kyber_kp.get('secret_value_s_id'),
                    'hash_c': kyber_kp.get('hash_c'),
                    'u_prime_id': kyber_kp.get('u_prime_id'),
                    'cl_public_key': _to_list(kyber_kp.get('cl_public_key')),
                    'cl_private_key': _to_list(kyber_kp.get('cl_private_key')),
                    'A': _to_list(kyber_kp.get('system_A')),
                    'algorithm': kyber_kp.get('algorithm', 'CertificatelessKyber512_DLL'),
                    'parameters': {'n': 512, 'm': 1024, 'q': 12289},
                    'partial_key_source': 'KGC'
                })

                self.node.kyber_keygen_time = timezone.now()
                self.node.kyber_keygen_duration = kyber_duration
                self.node.kyber_security_level = str(security_level)
                logger.info(f"节点 {self.node_id} Kyber密钥更新成功，耗时: {kyber_duration:.4f}秒")

                # 如果Falcon密钥也已生成，则标记为已接收部分私钥
                if self.node.falcon_public_key:
                    self.node.partial_key_received = True
                    logger.info(f"节点 {self.node_id} Kyber和Falcon密钥都已生成，标记为已接收部分私钥")

                # 分字段保存到数据库，避免单个数据包过大
                from django.db import connection
                from pqkds.models import Node
                try:
                    connection.close()
                    # 使用 update 方法分字段更新
                    Node.objects.filter(id=self.node.id).update(
                        partial_key_received=self.node.partial_key_received,
                        kyber_keygen_time=self.node.kyber_keygen_time,
                        kyber_keygen_duration=self.node.kyber_keygen_duration,
                        kyber_security_level=self.node.kyber_security_level,
                        status=self.node.status
                    )
                    # 分别保存密钥数据
                    if self.node.kyber_public_key:
                        Node.objects.filter(id=self.node.id).update(kyber_public_key=self.node.kyber_public_key)
                    if self.node.kyber_private_key:
                        Node.objects.filter(id=self.node.id).update(kyber_private_key=self.node.kyber_private_key)
                    if self.node.kyber_partial_key_data:
                        Node.objects.filter(id=self.node.id).update(kyber_partial_key_data=self.node.kyber_partial_key_data)
                except Exception as save_error:
                    logger.error(f"第一次保存失败: {save_error}，尝试重新连接数据库")
                    try:
                        connection.close()
                        self.node.save()
                    except Exception as retry_error:
                        logger.error(f"重新连接后保存仍然失败: {retry_error}")
                        raise

                # 上传到区块链
                try:
                    upload_result = self.upload_service.upload_node_registration(self.node)
                    if upload_result['success']:
                        logger.info(f"节点 {self.node_id} 更新的Kyber公钥已上链")
                    else:
                        logger.warning(f"节点 {self.node_id} 上链失败: {upload_result.get('message')}")
                except Exception as e:
                    logger.warning(f"节点 {self.node_id} 上链异常: {e}")

                return {
                    'success': True,
                    'message': f'Kyber密钥更新成功（基于KGC部分私钥），耗时: {kyber_duration:.4f}秒',
                    'node_id': self.node_id,
                    'kyber_keygen_duration': round(kyber_duration, 4),
                    'kyber_keygen_time': self.node.kyber_keygen_time.isoformat() if self.node.kyber_keygen_time else None,
                    'partial_key_received': self.node.partial_key_received,
                    'partial_key_source': 'KGC'
                }
            else:
                logger.error(f"节点 {self.node_id} Kyber密钥生成失败: {kyber_kp.get('error')}")
                return {
                    'success': False,
                    'message': f"Kyber密钥生成失败: {kyber_kp.get('error')}"
                }
        except Exception as e:
            logger.error(f"更新Kyber密钥异常: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': f'更新Kyber密钥失败: {str(e)}'
            }

    def update_falcon_keys(self, security_level: int = 512, falcon_version: str = 'v2') -> Dict[str, Any]:
        """
        更新Falcon密钥 - 使用高效的密钥生成方法，并调用KGC生成部分私钥
        """
        try:
            import time
            from .kgc_service import KGCService
            logger.info(f"节点 {self.node_id} 更新Falcon密钥，安全级别: {security_level}，版本: {falcon_version}")

            if self.node is None:
                return {'success': False, 'message': f'节点 {self.node_id} 不存在'}

            # 第一步：调用KGC生成Falcon部分私钥
            logger.info(f"第一步：调用KGC为节点 {self.node_id} 生成Falcon部分私钥")
            kgc_service = KGCService()
            kgc_result = kgc_service.generate_and_save_falcon_partial_key(self.node_id)

            if not kgc_result['success']:
                logger.error(f"KGC生成Falcon部分私钥失败: {kgc_result.get('message')}")
                return {
                    'success': False,
                    'message': f"KGC生成Falcon部分私钥失败: {kgc_result.get('message')}"
                }

            logger.info(f"KGC已为节点 {self.node_id} 生成Falcon部分私钥")

            # 刷新节点对象以获取最新的部分私钥数据
            self.node.refresh_from_db()

            # 第二步：节点使用部分私钥生成完整的Falcon公私钥对
            logger.info(f"第二步：节点 {self.node_id} 使用部分私钥生成完整Falcon密钥对")
            falcon_start_time = time.time()
            falcon_kp = self.keygen_service.generate_falcon_keypair(self.node_id)
            falcon_end_time = time.time()
            falcon_duration = falcon_end_time - falcon_start_time

            if falcon_kp['success']:
                logger.info(f"节点 {self.node_id} 使用部分私钥成功生成完整Falcon密钥对，耗时: {falcon_duration:.4f}秒")

                # 保存Falcon公钥（使用压缩格式）
                falcon_pk_bytes = np.array(falcon_kp['public_key'], dtype=np.uint8).tobytes()
                falcon_public_key_b64 = base64.b64encode(falcon_pk_bytes).decode('utf-8')
                self.node.falcon_public_key = compress_key_data(falcon_public_key_b64)

                # 保存Falcon私钥（完整的私钥结构，使用压缩格式）
                falcon_private_key_data = {
                    'D_id': falcon_kp['private_key']['D_id'],
                    'S_id': falcon_kp['private_key']['S_id']
                }
                falcon_private_key_json = json.dumps(falcon_private_key_data)
                falcon_private_key_b64 = base64.b64encode(falcon_private_key_json.encode('utf-8')).decode('utf-8')
                self.node.falcon_private_key = compress_key_data(falcon_private_key_b64)

                # 获取部分私钥数据用于记录来源
                try:
                    falcon_partial_data = json.loads(self.node.falcon_partial_key_data)
                except:
                    falcon_partial_data = {}

                # ⚠️ 这里原先写 falcon_lattice_params（10.2MB，无读取方），
                # 2026-09-26 起停写，理由见 generate_falcon_keys_v2 中的说明。
                self.node.falcon_keygen_time = timezone.now()
                self.node.falcon_keygen_duration = falcon_duration
                self.node.falcon_security_level = str(security_level)
                logger.info(f"节点 {self.node_id} Falcon密钥更新成功，耗时: {falcon_duration:.4f}秒")

                # 如果Kyber密钥也已生成，则标记为已接收部分私钥
                if self.node.kyber_public_key:
                    self.node.partial_key_received = True
                    logger.info(f"节点 {self.node_id} Kyber和Falcon密钥都已生成，标记为已接收部分私钥")

                # 分字段保存到数据库，避免单个数据包过大
                from django.db import connection
                from pqkds.models import Node
                try:
                    connection.close()
                    # 使用 update 方法分字段更新
                    Node.objects.filter(id=self.node.id).update(
                        partial_key_received=self.node.partial_key_received,
                        falcon_keygen_time=self.node.falcon_keygen_time,
                        falcon_keygen_duration=self.node.falcon_keygen_duration,
                        falcon_security_level=self.node.falcon_security_level,
                        status=self.node.status
                    )
                    # 分别保存密钥数据
                    if self.node.falcon_public_key:
                        Node.objects.filter(id=self.node.id).update(falcon_public_key=self.node.falcon_public_key)
                    if self.node.falcon_private_key:
                        Node.objects.filter(id=self.node.id).update(falcon_private_key=self.node.falcon_private_key)
                    if self.node.falcon_partial_key_data:
                        Node.objects.filter(id=self.node.id).update(falcon_partial_key_data=self.node.falcon_partial_key_data)
                    # falcon_lattice_params 已停写（10.2MB/节点、无读取方）—— 见 generate_falcon_keys_v2
                except Exception as save_error:
                    logger.error(f"第一次保存失败: {save_error}，尝试重新连接数据库")
                    try:
                        connection.close()
                        self.node.save()
                    except Exception as retry_error:
                        logger.error(f"重新连接后保存仍然失败: {retry_error}")
                        raise

                # 上传到区块链
                try:
                    upload_result = self.upload_service.upload_node_registration(self.node)
                    if upload_result['success']:
                        logger.info(f"节点 {self.node_id} 更新的Falcon公钥已上链")
                    else:
                        logger.warning(f"节点 {self.node_id} 上链失败: {upload_result.get('message')}")
                except Exception as e:
                    logger.warning(f"节点 {self.node_id} 上链异常: {e}")

                return {
                    'success': True,
                    'message': f'Falcon密钥更新成功（基于KGC部分私钥），耗时: {falcon_duration:.4f}秒',
                    'node_id': self.node_id,
                    'falcon_keygen_duration': round(falcon_duration, 4),
                    'falcon_keygen_time': self.node.falcon_keygen_time.isoformat() if self.node.falcon_keygen_time else None,
                    'partial_key_received': self.node.partial_key_received,
                    'partial_key_source': 'KGC'
                }
            else:
                logger.error(f"节点 {self.node_id} Falcon密钥生成失败: {falcon_kp.get('error')}")
                return {
                    'success': False,
                    'message': f"Falcon密钥生成失败: {falcon_kp.get('error')}"
                }
        except Exception as e:
            logger.error(f"更新Falcon密钥异常: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': f'更新Falcon密钥失败: {str(e)}'
            }

    def update_both_keys(self, kyber_security_level: int = 512, falcon_security_level: int = 512, falcon_version: str = 'v2') -> Dict[str, Any]:
        """
        同时更新Kyber和Falcon密钥 - 使用高效的密钥生成方法，并调用KGC生成部分私钥
        """
        try:
            import time
            from .kgc_service import KGCService
            logger.info(f"节点 {self.node_id} 同时更新Kyber和Falcon密钥")
            logger.info(f"  Kyber安全级别: {kyber_security_level}")
            logger.info(f"  Falcon安全级别: {falcon_security_level}")

            if self.node is None:
                return {'success': False, 'message': f'节点 {self.node_id} 不存在'}

            # 第一步：调用KGC生成Kyber部分私钥
            logger.info(f"第一步：调用KGC为节点 {self.node_id} 生成Kyber部分私钥")
            kgc_service = KGCService()
            kyber_kgc_result = kgc_service.generate_and_save_kyber_partial_key(self.node_id)

            if not kyber_kgc_result['success']:
                logger.error(f"KGC生成Kyber部分私钥失败: {kyber_kgc_result.get('message')}")
                return {
                    'success': False,
                    'message': f"KGC生成Kyber部分私钥失败: {kyber_kgc_result.get('message')}"
                }

            logger.info(f"KGC已为节点 {self.node_id} 生成Kyber部分私钥")

            # 第二步：调用KGC生成Falcon部分私钥
            logger.info(f"第二步：调用KGC为节点 {self.node_id} 生成Falcon部分私钥")
            falcon_kgc_result = kgc_service.generate_and_save_falcon_partial_key(self.node_id)

            if not falcon_kgc_result['success']:
                logger.error(f"KGC生成Falcon部分私钥失败: {falcon_kgc_result.get('message')}")
                return {
                    'success': False,
                    'message': f"KGC生成Falcon部分私钥失败: {falcon_kgc_result.get('message')}"
                }

            logger.info(f"KGC已为节点 {self.node_id} 生成Falcon部分私钥")

            # 刷新节点对象以获取最新的部分私钥数据
            self.node.refresh_from_db()

            # 第三步：节点使用KGC部分私钥生成完整的Kyber密钥对
            logger.info(f"第三步：节点 {self.node_id} 使用KGC部分私钥生成完整Kyber密钥对")
            kyber_start_time = time.time()

            # 从数据库获取KGC存入的Kyber部分私钥
            if not self.node.kyber_partial_key_data:
                return {'success': False, 'message': f"节点 {self.node_id} 的Kyber部分私钥数据为空"}
            kyber_partial = json.loads(self.node.kyber_partial_key_data)
            kp_t = kyber_partial.get('partial_key_t')
            kp_c = kyber_partial.get('hash_c')
            kp_u = kyber_partial.get('u_prime_id')
            if kp_t is None or kp_c is None or kp_u is None:
                return {'success': False, 'message': "Kyber部分私钥数据不完整"}

            kyber_kp = self.keygen_service.complete_kyber_keygen_with_partial_key(
                node_id=self.node_id,
                partial_key_t=kp_t,
                hash_c=kp_c,
                u_prime_id=kp_u
            )
            kyber_end_time = time.time()
            kyber_duration = kyber_end_time - kyber_start_time

            if not kyber_kp['success']:
                logger.error(f"节点 {self.node_id} Kyber密钥生成失败: {kyber_kp.get('error')}")
                return {
                    'success': False,
                    'message': f"Kyber密钥生成失败: {kyber_kp.get('error')}"
                }

            logger.info(f"节点 {self.node_id} 使用部分私钥成功生成完整Kyber密钥对，耗时: {kyber_duration:.4f}秒")

            # 融合模块返回的是标准Kyber DLL格式的bytes密钥对
            kyber_pk = kyber_kp['kyber_public_key']
            kyber_sk = kyber_kp['kyber_private_key']
            self.node.kyber_public_key = base64.b64encode(kyber_pk).decode('utf-8')
            self.node.kyber_private_key = base64.b64encode(kyber_sk).decode('utf-8')
            self.node.kyber_partial_key_data = json.dumps({
                'partial_key_t': kyber_kp.get('partial_key_t'),
                'secret_value_s_id': kyber_kp.get('secret_value_s_id'),
                'hash_c': kyber_kp.get('hash_c'),
                'u_prime_id': kyber_kp.get('u_prime_id'),
                'cl_public_key': _to_list(kyber_kp.get('cl_public_key')),
                'cl_private_key': _to_list(kyber_kp.get('cl_private_key')),
                'A': _to_list(kyber_kp.get('system_A')),
                'algorithm': kyber_kp.get('algorithm', 'CertificatelessKyber512_DLL'),
                'parameters': {'n': 512, 'm': 1024, 'q': 12289},
                'partial_key_source': 'KGC'
            })
            self.node.kyber_keygen_time = timezone.now()
            self.node.kyber_keygen_duration = kyber_duration
            self.node.kyber_security_level = str(kyber_security_level)
            logger.info(f"节点 {self.node_id} Kyber密钥更新成功，耗时: {kyber_duration:.4f}秒")

            # 第四步：节点使用KGC部分私钥生成完整的Falcon密钥对
            logger.info(f"第四步：节点 {self.node_id} 使用KGC部分私钥生成完整Falcon密钥对")
            falcon_start_time = time.time()

            # 从数据库获取KGC存入的Falcon部分私钥
            if not self.node.falcon_partial_key_data:
                return {'success': False, 'message': f"节点 {self.node_id} 的Falcon部分私钥数据为空"}
            falcon_partial = json.loads(self.node.falcon_partial_key_data)
            f_partial_key_b64 = falcon_partial.get('partial_key')
            if not f_partial_key_b64:
                return {'success': False, 'message': "Falcon部分私钥数据不完整"}
            f_partial_inner = decode_falcon_partial_key(f_partial_key_b64)
            f_D_id = f_partial_inner['D_id']
            f_H_id = f_partial_inner['H_id']
            f_A = f_partial_inner.get('A')
            f_B = f_partial_inner.get('B')

            falcon_kp = self.keygen_service.complete_falcon_keygen_with_partial_key(
                node_id=self.node_id,
                D_id_list=f_D_id,
                H_id_list=f_H_id,
                A_list=f_A,
                B_list=f_B,
                security_level=falcon_security_level
            )
            falcon_end_time = time.time()
            falcon_duration = falcon_end_time - falcon_start_time

            if not falcon_kp['success']:
                logger.error(f"节点 {self.node_id} Falcon密钥生成失败: {falcon_kp.get('error')}")
                return {
                    'success': False,
                    'message': f"Falcon密钥生成失败: {falcon_kp.get('error')}"
                }

            logger.info(f"节点 {self.node_id} 使用KGC部分私钥成功生成完整Falcon密钥对，耗时: {falcon_duration:.4f}秒")

            # 获取参数信息
            kp_params = falcon_kp.get('parameters', {
                'n': 512 if falcon_security_level == 512 else 1024,
                'm': 1024 if falcon_security_level == 512 else 2048,
                'q': 12289
            })

            # 保存Falcon公钥（包含系统参数A、B和H_id，加密时需要）
            falcon_pk_data = {
                'U_id': falcon_kp['public_key'],
                'H_id': falcon_kp.get('H_id'),
                'A': falcon_kp.get('A'),
                'B': falcon_kp.get('B'),
                'algorithm': f'CertificatelessFalcon-{falcon_security_level}',
                'security_level': falcon_security_level,
                'node_id': self.node_id,
                'parameters': kp_params
            }
            falcon_public_key_b64 = base64.b64encode(
                json.dumps(falcon_pk_data).encode('utf-8')
            ).decode('utf-8')
            self.node.falcon_public_key = compress_key_data(falcon_public_key_b64)

            # 保存Falcon私钥（包含参数信息的 JSON 格式）
            falcon_private_key_data = {
                'D_id': falcon_kp['private_key']['D_id'],
                'S_id': falcon_kp['private_key']['S_id'],
                'algorithm': f'CertificatelessFalcon-{falcon_security_level}',
                'security_level': falcon_security_level,
                'node_id': self.node_id,
                'parameters': kp_params
            }
            falcon_private_key_b64 = base64.b64encode(
                json.dumps(falcon_private_key_data).encode('utf-8')
            ).decode('utf-8')
            self.node.falcon_private_key = compress_key_data(falcon_private_key_b64)

            # falcon_lattice_params 已停写（10.2MB/节点、无读取方）—— 见 generate_falcon_keys_v2

            self.node.falcon_keygen_time = timezone.now()
            self.node.falcon_keygen_duration = falcon_duration
            self.node.falcon_security_level = str(falcon_security_level)
            logger.info(f"节点 {self.node_id} Falcon密钥更新成功，耗时: {falcon_duration:.4f}秒")

            # 标记为已接收部分私钥
            self.node.partial_key_received = True
            logger.info(f"节点 {self.node_id} Kyber和Falcon密钥都已生成，标记为已接收部分私钥")

            # 分字段保存到数据库，避免单个数据包过大
            from django.db import connection
            from pqkds.models import Node
            try:
                connection.close()
                # 使用 update 方法分字段更新，避免一次性保存大数据
                Node.objects.filter(id=self.node.id).update(
                    partial_key_received=True,
                    kyber_keygen_time=self.node.kyber_keygen_time,
                    kyber_keygen_duration=self.node.kyber_keygen_duration,
                    falcon_keygen_time=self.node.falcon_keygen_time,
                    falcon_keygen_duration=self.node.falcon_keygen_duration,
                    status=self.node.status
                )
                # 分别保存密钥数据
                if self.node.kyber_public_key:
                    Node.objects.filter(id=self.node.id).update(kyber_public_key=self.node.kyber_public_key)
                if self.node.kyber_private_key:
                    Node.objects.filter(id=self.node.id).update(kyber_private_key=self.node.kyber_private_key)
                if self.node.kyber_partial_key_data:
                    Node.objects.filter(id=self.node.id).update(kyber_partial_key_data=self.node.kyber_partial_key_data)
                if self.node.falcon_public_key:
                    Node.objects.filter(id=self.node.id).update(falcon_public_key=self.node.falcon_public_key)
                if self.node.falcon_private_key:
                    Node.objects.filter(id=self.node.id).update(falcon_private_key=self.node.falcon_private_key)
                if self.node.falcon_partial_key_data:
                    Node.objects.filter(id=self.node.id).update(falcon_partial_key_data=self.node.falcon_partial_key_data)
                # falcon_lattice_params 已停写（10.2MB/节点、无读取方）—— 见 generate_falcon_keys_v2
            except Exception as save_error:
                logger.error(f"第一次保存失败: {save_error}，尝试重新连接数据库")
                try:
                    connection.close()
                    # 重试：使用 save 方法
                    self.node.save()
                except Exception as retry_error:
                    logger.error(f"重新连接后保存仍然失败: {retry_error}")
                    raise

            # 上传到区块链
            try:
                upload_result = self.upload_service.upload_node_registration(self.node)
                if upload_result['success']:
                    logger.info(f"节点 {self.node_id} 更新的Kyber和Falcon公钥已上链")
                else:
                    logger.warning(f"节点 {self.node_id} 上链失败: {upload_result.get('message')}")
            except Exception as e:
                logger.warning(f"节点 {self.node_id} 上链异常: {e}")

            return {
                'success': True,
                'message': f'Kyber和Falcon密钥同时更新成功（基于KGC部分私钥），Kyber耗时: {kyber_duration:.4f}秒，Falcon耗时: {falcon_duration:.4f}秒',
                'node_id': self.node_id,
                'kyber_keygen_duration': round(kyber_duration, 4),
                'kyber_keygen_time': self.node.kyber_keygen_time.isoformat() if self.node.kyber_keygen_time else None,
                'falcon_keygen_duration': round(falcon_duration, 4),
                'falcon_keygen_time': self.node.falcon_keygen_time.isoformat() if self.node.falcon_keygen_time else None,
                'partial_key_received': self.node.partial_key_received,
                'partial_key_source': 'KGC'
            }
        except Exception as e:
            logger.error(f"同时更新密钥异常: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': f'同时更新密钥失败: {str(e)}'
            }

