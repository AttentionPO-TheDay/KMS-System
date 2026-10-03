# -*- coding: utf-8 -*-
"""
基于格的安全密钥预分配服务

支持两种格密码方案：
1. Kyber KEM: encaps/decaps 生成共享秘密，AES-GCM 加密会话密钥
2. Falcon 格密码: 无证书格密码方案直接加密会话密钥

密钥池生命周期: 批量生成 → 存储 → 按需取用 → 过期清理
"""
import os
import json
import time
import hashlib
import base64
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import timedelta

from django.utils import timezone
from django.db import transaction, models

from . import api_contract as C
from .models import Node, SessionKey, PreDistributedKey
from .node_key_registry import require_usable_key
from .crypto_utils import KyberCrypto, AESCrypto

# 载荷层已切到国密 SM4（决策 D3）。这里显式导入算法标记与 SM4 实现，
# 并在写出的信封里带上 `payload_algorithm`，供读取端区分新老数据。
from .sm4_crypto import (
    GCM_IV_BYTES,
    PAYLOAD_ALGORITHM_SM4,
    PayloadCipher,
    SM4Crypto,
)

logger = logging.getLogger(__name__)


class KeyPoolService:
    """密钥池管理服务"""

    DEFAULT_POOL_SIZE = 50
    DEFAULT_EXPIRY_HOURS = 24
    LOW_THRESHOLD_RATIO = 0.2  # 低于 20% 触发补充

    # ----------------------------------------------------------------
    #  池项状态（KMS-013：状态机与别名表的**唯一出处**是 `api_contract`）
    # ----------------------------------------------------------------
    # 原先这五个常量在本文件里另行定义，而 `api_contract` 里没有对应物 ——
    # 于是"什么算可用"只在这一个模块里成立，别处要判同一件事就得各写一套。
    # 现在值全部从 `api_contract` 派生（含旧拼写别名表），加一个新别名
    # 只用改一处；派生而不是照抄，是为了让漂移在**导入时**就发生错误，
    # 而不是等到某次消费把可用的行说成不可用（静默）。
    #
    # ⚠️ 迁移目标 `READY → RESERVED → CONSUMED` 里的 `RESERVED` 是**保留值**：
    #    当前没有任何生产写入点，也刻意没有 —— 消费是单事务的
    #    "选中（FOR UPDATE）→ 标记 CONSUMED"，中间窗口为零，没有需要预留的
    #    时间段。理由与转移表写在 `api_contract.POOL_TRANSITIONS` 上方。
    POOL_STATUS_READY_VALUES = (
        (C.POOL_READY,)
        + tuple(
            alias for alias, canonical in C.POOL_LEGACY_STATUS_ALIASES.items()
            if canonical == C.POOL_READY
        )
    )
    POOL_STATUS_RESERVED = C.POOL_RESERVED
    POOL_STATUS_CONSUMED_VALUES = (C.POOL_CONSUMED,) + tuple(
        alias for alias, canonical in C.POOL_LEGACY_STATUS_ALIASES.items()
        if canonical == C.POOL_CONSUMED
    )
    POOL_STATUS_EXPIRED_VALUES = (C.POOL_EXPIRED,) + tuple(
        alias for alias, canonical in C.POOL_LEGACY_STATUS_ALIASES.items()
        if canonical == C.POOL_EXPIRED
    )
    POOL_STATUS_REVOKED = C.POOL_REVOKED

    @staticmethod
    def revoke_pool_items_for_key(node_id: str, key_id, version=None,
                                  algorithm=None) -> int:
        """阶段 6（文档 §7.6）：长期密钥被回收后，连带失效依赖它的池项。

        池项里的密文是用**某个长期公钥**封的。那把长期密钥一旦被回收，
        对应的池项就再也解不开了 —— 但它仍会在池子里显示为 READY，
        等着某次会话去取，然后在解密时失败。让这种"注定失败"的条目
        留在可用集合里，既浪费一次会话，也会把真实故障伪装成偶发问题。

        所以回收长期密钥时主动把它们标成 REVOKED，并提示重新预分配。

        范围只动 READY / RESERVED：已 CONSUMED 的是历史事实，
        改了会让审计记录对不上（那次会话确实用过这把密钥）。

        ---- KMS-007 D3：匹配必须精确到"哪一把长期密钥" ----

        改前这个函数**只按 node_id 匹配**，`key_id` / `version` 两个参数
        只出现在日志文案里。后果：回收任何一个算法的一把密钥，会把该节点
        **全部** READY/RESERVED 池项一次清空（包括用其它仍然有效的算法封的），
        而日志逐字印着 `key_id=… version=…`，读日志的人会以为它是精确失效的。

        现在分两面：

        * **精确面** —— 创建池项时回填的 `long_term_key_id` +
          `long_term_key_version` 命中（回填点见各 `generate_*_pool` 与
          `user_distribution_views.distribute_to_user`）。这是唯一可靠的判据。
        * **退化面** —— KMS-007 之前的历史行这两列是 NULL（迁移 0017 刻意
          不回填：猜一个 key_id 落库比留空更糟，错了没有任何迹象）。它们
          只能退化为「同节点 + **同算法家族**」匹配；**不提供 `algorithm`
          时退化范围是该节点全部算法**（内部运维口的旧行为）。两种退化都
          在日志里如实说明命中条数与范围 —— 不假装精确。

        ⚠️ `algorithm` 收的是**规范名**（`KYBER`/`FALCON`…），不是库里的
           封装拼写；家族展开由 `api_contract.wrapping_algorithms_for` 做。
        """
        from django.db.models import Q

        # 池项的密文可能封给 node1 或 node2 中的任一方，
        # 且算法上分节点腿/用户腿 —— 这里按节点匹配，命中任一角色即失效。
        scope = PreDistributedKey.objects.filter(
            status__in=KeyPoolService.POOL_STATUS_READY_VALUES
            + (KeyPoolService.POOL_STATUS_RESERVED,)
        ).filter(
            Q(node1__node_id=node_id) | Q(node2__node_id=node_id)
        )

        # 版本号只接受**真正的整数**：`True` 会被 `int()` 收成 1、
        # `1.9` 会被截成 1 —— 静默变成"撤 v1"，而那可能正是在产版本。
        # 调用方 `revoke_long_term_key` 已先做过严格校验；经内部运维口
        # （`internal_pool_views`）进来时值来自 JSON，字符串数字是常见形态。
        version_int = None
        if isinstance(version, int) and not isinstance(version, bool):
            version_int = version
        elif isinstance(version, str) and version.strip().isdigit():
            version_int = int(version.strip())

        key_id_text = str(key_id or '').strip()

        with transaction.atomic():
            # --- 精确面：按创建时回填的长期密钥引用命中 -------------------
            # key_id 为空时**不查**：`filter(long_term_key_id=None)` 在
            # Django 里是 `IS NULL`，那会把"没有引用"的历史行误当成精确命中，
            # 于是日志把退化面说成精确面 —— 恰好是要修的那类假精确。
            precise_n = 0
            if key_id_text and version_int is not None:
                precise_n = scope.filter(
                    long_term_key_id=key_id_text,
                    long_term_key_version=version_int,
                ).update(status=KeyPoolService.POOL_STATUS_REVOKED)

            # --- 退化面：历史行（无长期密钥引用）---------------------------
            degraded = scope.filter(long_term_key_id__isnull=True)
            family = C.wrapping_algorithms_for(algorithm) if algorithm else ()
            if algorithm and not family:
                # 传了算法但认不出来：宁可**不退化**也不按节点全清 ——
                # 认不出的算法名去匹配那个节点所有算法的池项，正是上面那个
                # 缺陷的翻版，而且是静默的。留一条日志说明漏掉了什么。
                degraded_n = 0
                logger.error(
                    "长期密钥回收：算法 %r 认不出来，历史行（无长期密钥引用）"
                    "本次**未失效** —— 请核对调用方传入的算法名。node=%s key_id=%s",
                    algorithm, node_id, key_id_text or key_id,
                )
                return precise_n
            if family:
                degraded = degraded.filter(
                    Q(wrapping_algorithm__in=family) | Q(algorithm__in=family)
                )
            degraded_n = degraded.update(status=KeyPoolService.POOL_STATUS_REVOKED)

        total = precise_n + degraded_n
        if total:
            if not algorithm:
                scope_note = (
                    f'调用方未提供算法，退化范围扩大到该节点全部算法'
                    f'（历史行 {degraded_n} 条）—— 粗粒度失效，请核对是否误伤'
                )
            else:
                scope_note = f'同节点+同算法{list(family)}（历史行 {degraded_n} 条）'
            logger.warning(
                "长期密钥回收连带失效池项：node=%s key_id=%s version=%s -> %d 条置为 REVOKED"
                "（精确命中 %d 条；无长期密钥引用的历史行按 %s 退化匹配）",
                node_id, key_id_text or key_id,
                version_int if version_int is not None else version,
                total, precise_n, scope_note,
            )
        return total

    # ================================================================
    #  Kyber KEM 方案: 批量预分配
    # ================================================================
    @staticmethod
    def generate_kyber_pool(
        node1_id: str, node2_id: str,
        count: int = None, expiry_hours: int = None
    ) -> Dict[str, Any]:
        """
        Kyber KEM 方案批量预分配。

        对每条密钥:
        1. 生成随机 AES-256 密钥
        2. Kyber encaps(node2_pk) → ciphertext + shared_secret
        3. AES-GCM(shared_secret) 加密 AES 密钥
        4. 存储加密数据，双方可通过 decaps 恢复
        """
        count = count or KeyPoolService.DEFAULT_POOL_SIZE
        expiry_hours = expiry_hours or KeyPoolService.DEFAULT_EXPIRY_HOURS

        logger.info(f"[KeyPool/Kyber] 为 {node1_id} ↔ {node2_id} 预分配 {count} 条密钥")
        t_total_start = time.perf_counter()

        try:
            node1 = Node.objects.get(node_id=node1_id)
            node2 = Node.objects.get(node_id=node2_id)
        except Node.DoesNotExist as e:
            return {'success': False, 'message': f'节点不存在: {e}'}

        # 闸门（KMS-007）：生成新池项 = 新工作，必须在读物化列之前先判
        # `node2` 的 KYBER 长期密钥还能不能用。
        #
        # 不做这一步会怎样：物化列被清空**只发生在回收时那一把原本是 ACTIVE**
        # （`revoke_public_key` 的分支）。若行已是 EXPIRED / RETIRED，或状态转换
        # 走了别的路径，列里仍是旧公钥 —— 下面那句 `if not node2.kyber_public_key`
        # 判不出来，一批**注定解不开**的池项就这么生成出来并显示 READY，
        # 直到某次会话取用、在节点上解封失败才暴露，现场离原因已经很远。
        #
        # ⚠️ 只把闸门加在空值判断**之前**；下面仍然照旧读 `node2.kyber_public_key`
        #    取材料 —— 登记行是判据，不是材料来源（两者不是同一份数据）。
        # 闸门返回的登记行**顺手留下**：它就是下面回填 `long_term_key_id/version`
        # 用的那一行（KMS-007 D3），不另查一次库 —— 两次查询之间可能发生轮换，
        # 两次读到的会是不同的行，回填的引用就与实际封装用的材料对不上了。
        # 失败形状沿用本层约定（`{'success': False}`），但把 `exc.code` 一并给出：
        # "已回收"与"没有公钥"必须可区分，否则调用方拿到的只是同一句模糊文案，
        # 而两者的处置完全不同（换密钥 vs 先初始化节点）。
        try:
            long_term_key = require_usable_key(node2, 'KYBER')
        except C.ContractError as exc:
            return {
                'success': False,
                'code': exc.code,
                # 调用方（views.py 的 generate 动作）只转达 message、不转达 code，
                # 所以码也必须出现在文案里，判据才看得到。
                'message': f'节点 {node2_id} {exc.message}（{exc.code}）',
            }

        if not node2.kyber_public_key:
            return {'success': False, 'message': f'节点 {node2_id} 没有 Kyber 公钥'}

        # 解码接收方 Kyber 公钥
        try:
            receiver_pk = base64.b64decode(node2.kyber_public_key)
        except Exception as e:
            return {'success': False, 'message': f'Kyber 公钥解码失败: {e}'}

        # 根据公钥长度确定 Kyber 变体
        pk_len_map = {800: 512, 1184: 768, 1568: 1024}
        variant = pk_len_map.get(len(receiver_pk), 512)

        # 验证公私钥变体一致性，防止 decaps 时长度不匹配
        if node2.kyber_private_key:
            try:
                receiver_sk = base64.b64decode(node2.kyber_private_key)
                sk_len_map = {1632: 512, 2400: 768, 3168: 1024}
                sk_variant = sk_len_map.get(len(receiver_sk))
                if sk_variant is not None and sk_variant != variant:
                    logger.error(
                        f"[KeyPool/Kyber] 节点 {node2_id} 公私钥变体不一致: "
                        f"pk={len(receiver_pk)}B→Kyber-{variant}, "
                        f"sk={len(receiver_sk)}B→Kyber-{sk_variant}. "
                        f"请重新生成该节点的密钥。"
                    )
                    return {
                        'success': False,
                        'message': f'节点 {node2_id} 的Kyber公钥(Kyber-{variant})和私钥(Kyber-{sk_variant})变体不一致，'
                                   f'请在节点管理中重新生成密钥'
                    }
            except Exception:
                pass  # 私钥解码失败不阻塞，后续 decaps 时会报错

        try:
            kyber = KyberCrypto(variant)
        except Exception as e:
            return {'success': False, 'message': f'Kyber-{variant} 初始化失败: {e}'}

        # 生成批次 ID
        pool_id = f"pool_kyber_{hashlib.sha256(f'{node1_id}_{node2_id}_{time.time()}'.encode()).hexdigest()[:16]}"
        expires_at = timezone.now() + timedelta(hours=expiry_hours)

        keys_to_create = []
        latencies = []

        for i in range(count):
            t0 = time.perf_counter()
            try:
                # Step 1: 随机载荷密钥 —— D3 后是 SM4 的 16 字节（原为 AES-256 的 32 字节）
                payload_key = PayloadCipher.generate_key()
                key_hash = hashlib.sha256(payload_key).hexdigest()

                # Step 2: Kyber encaps
                kem_ct, shared_secret = kyber.encrypt(receiver_pk)

                # Step 3: 用 KEM 共享秘密派生的 16 字节 KEK 做 SM4-GCM 封装
                kek = PayloadCipher.kek_from_shared_secret(PAYLOAD_ALGORITHM_SM4, shared_secret)
                encrypted_payload, nonce_tag = SM4Crypto.encrypt(payload_key, kek)
                nonce, tag = nonce_tag[:GCM_IV_BYTES], nonce_tag[GCM_IV_BYTES:]

                encrypted_data = json.dumps({
                    'kem_ciphertext': base64.b64encode(kem_ct).decode(),
                    # 字段名沿用历史的 `encrypted_aes_key`：读取端（views.py）按这个名字取值，
                    # 改成新名字会让存量行读不出来。它的含义已由 `payload_algorithm` 标注。
                    'encrypted_aes_key': base64.b64encode(encrypted_payload).decode(),
                    'nonce': base64.b64encode(nonce).decode(),
                    'tag': base64.b64encode(tag).decode(),
                    'variant': variant,
                    # 显式标记算法：读取端据此决定 KEK 取 16 还是 32 字节、
                    # 以及用 SM4 还是旧 AES 解密。缺这个字段的行 = 历史 AES-256 行。
                    'payload_algorithm': PAYLOAD_ALGORITHM_SM4,
                })

                t1 = time.perf_counter()
                latency_ms = (t1 - t0) * 1000
                latencies.append(latency_ms)

                keys_to_create.append(PreDistributedKey(
                    pool_id=pool_id,
                    key_index=i,
                    node1=node1,
                    node2=node2,
                    algorithm='kyber_kem',
                    encrypted_key_data=encrypted_data,
                    key_hash=key_hash,
                    # 阶段 6（文档 §7.5）：新值统一用 READY。
                    # 旧值 'unused' 仍留在库里（历史行），读取侧经
                    # POOL_STATUS_READY_VALUES 一并纳入，不会漏掉它们。
                    status='READY',
                    expires_at=expires_at,
                    generation_time_ms=latency_ms,
                    # KMS-007 D3：记下"这一项是用哪把长期密钥封的"。
                    # 回收时 `revoke_pool_items_for_key` 的精确面全靠这两列；
                    # 留空会退化成"同节点 + 同算法"的粗匹配（迁移 0017）。
                    long_term_key_id=long_term_key.key_id,
                    long_term_key_version=long_term_key.key_version,
                ))
            except Exception as e:
                logger.error(f"[KeyPool/Kyber] 第 {i} 条生成失败: {e}")
                continue

        # 批量写入数据库
        with transaction.atomic():
            PreDistributedKey.objects.bulk_create(keys_to_create)

        t_total = time.perf_counter() - t_total_start
        throughput = len(keys_to_create) / t_total if t_total > 0 else 0
        avg_ms = sum(latencies) / len(latencies) if latencies else 0

        logger.info(
            f"[KeyPool/Kyber] 完成: {len(keys_to_create)}/{count} 条, "
            f"耗时 {t_total:.2f}s, 吞吐量 {throughput:.1f} keys/sec"
        )

        return {
            'success': True,
            'pool_id': pool_id,
            'algorithm': f'Kyber-{variant} KEM',
            'generated': len(keys_to_create),
            'requested': count,
            'total_time_sec': round(t_total, 3),
            'throughput_per_sec': round(throughput, 1),
            'avg_latency_ms': round(avg_ms, 2),
            'expires_at': expires_at.isoformat(),
        }

    # ================================================================
    #  Falcon 格密码方案: 批量预分配
    # ================================================================
    @staticmethod
    def generate_falcon_pool(
        node1_id: str, node2_id: str,
        count: int = None, expiry_hours: int = None
    ) -> Dict[str, Any]:
        """
        Falcon 格密码方案批量预分配。

        对每条密钥:
        1. 生成随机 AES-256 密钥
        2. 用 node2 的 Falcon 公钥（无证书格密码）加密 AES 密钥
        3. 存储加密数据，node2 用 Falcon 私钥解密恢复
        """
        count = count or KeyPoolService.DEFAULT_POOL_SIZE
        expiry_hours = expiry_hours or KeyPoolService.DEFAULT_EXPIRY_HOURS

        logger.info(f"[KeyPool/Falcon] 为 {node1_id} ↔ {node2_id} 预分配 {count} 条密钥")
        t_total_start = time.perf_counter()

        try:
            node1 = Node.objects.get(node_id=node1_id)
            node2 = Node.objects.get(node_id=node2_id)
        except Node.DoesNotExist as e:
            return {'success': False, 'message': f'节点不存在: {e}'}

        # 闸门（KMS-007）：Falcon 池项同样是**新工作**（生成一份新的加密包），
        # 必须在读 `node2.falcon_public_key`（下面空值判断与循环里那一处读取）之前，
        # 先按**事实来源** `NodeLongTermKey` 判这把 FALCON 密钥还能不能用。
        #
        # 不做这一步会怎样：Falcon 这一列有两个易被忽视的坑，叠加起来的现象是
        # "池子照常生成、节点却永远解不开"：
        #   1. `revoke_public_key` 只在被回收的那把**原本是 ACTIVE** 时才清列；
        #      若行不是 ACTIVE（例如 0016 回填的 LEGACY 格材料行），列里是死材料，
        #      下面的 `if not node2.falcon_public_key` 判不出来，照样封装入库；
        #   2. 即使列被清空，旧文案也只有"没有 Falcon 公钥"——
        #      与"密钥已被回收"混在同一句话里，运维按"去初始化"处置却是错的。
        #
        # ⚠️ 闸门只判"能不能用"，材料**仍然**从 `node2.falcon_public_key` 取 ——
        #    绝不换成登记行的 `public_key`：FALCON 上两者不是同一份数据
        #    （登记行的 ACTIVE 是标准 Falcon 签名公钥，本列的旧值可能是 CL-Falcon
        #    格材料），换来源会静默换算法，所有既有信封全部解不开。
        # 返回的登记行只用于回填 `long_term_key_id/version`（KMS-007 D3）——
        # 那是"哪把**登记密钥**在管这一列"的记账，不是材料来源。
        # 失败形状沿用本层约定（`{'success': False}`），并把 `exc.code` 带进 message：
        # 调用方（views.py:3407 / kms_adapter.py:313）只转达 message、不读 code，
        # 码不写进文案，判据与运维就都看不到它。
        try:
            long_term_key = require_usable_key(node2, 'FALCON')
        except C.ContractError as exc:
            return {
                'success': False,
                'code': exc.code,
                'message': f'节点 {node2_id} {exc.message}（{exc.code}）',
            }

        if not node2.falcon_public_key:
            return {'success': False, 'message': f'节点 {node2_id} 没有 Falcon 公钥'}

        # 初始化 Falcon 加密服务
        from .falcon_aes_session_encryption import FalconAESSessionKeyEncryption
        target_security = int(getattr(node2, 'falcon_security_level', '512') or '512')
        falcon_enc = FalconAESSessionKeyEncryption(security_level=target_security)

        pool_id = f"pool_falcon_{hashlib.sha256(f'{node1_id}_{node2_id}_{time.time()}'.encode()).hexdigest()[:16]}"
        expires_at = timezone.now() + timedelta(hours=expiry_hours)

        keys_to_create = []
        latencies = []

        for i in range(count):
            t0 = time.perf_counter()
            try:
                # Step 1: 随机载荷密钥 —— D3 后是 SM4 的 16 字节
                payload_key = PayloadCipher.generate_key()
                key_hash = hashlib.sha256(payload_key).hexdigest()

                # Step 2: Falcon 格密码加密（把载荷密钥交给格封装层）
                enc_result = falcon_enc.encrypt_aes_key_with_falcon(
                    recipient_id=node2_id,
                    aes_key=payload_key,
                    recipient_public_key_b64=node2.falcon_public_key
                )

                if not enc_result.get('success'):
                    logger.warning(f"[KeyPool/Falcon] 第 {i} 条加密失败: {enc_result.get('message')}")
                    continue

                encrypted_data = json.dumps({
                    'ciphertext': enc_result['ciphertext'],
                    'algorithm': enc_result.get('algorithm', f'CertificatelessFalcon-{target_security}'),
                    'security_level': target_security,
                    'payload_algorithm': PAYLOAD_ALGORITHM_SM4,
                })

                t1 = time.perf_counter()
                latency_ms = (t1 - t0) * 1000
                latencies.append(latency_ms)

                keys_to_create.append(PreDistributedKey(
                    pool_id=pool_id,
                    key_index=i,
                    node1=node1,
                    node2=node2,
                    algorithm='falcon_lattice',
                    encrypted_key_data=encrypted_data,
                    key_hash=key_hash,
                    status='READY',
                    expires_at=expires_at,
                    generation_time_ms=latency_ms,
                    # KMS-007 D3：封这一项用的是 node2 的 FALCON 登记密钥，
                    # 回收精确匹配靠这两列（留空则退化为"同节点+同算法"）。
                    long_term_key_id=long_term_key.key_id,
                    long_term_key_version=long_term_key.key_version,
                ))
            except Exception as e:
                logger.error(f"[KeyPool/Falcon] 第 {i} 条生成失败: {e}")
                continue

        with transaction.atomic():
            PreDistributedKey.objects.bulk_create(keys_to_create)

        t_total = time.perf_counter() - t_total_start
        throughput = len(keys_to_create) / t_total if t_total > 0 else 0
        avg_ms = sum(latencies) / len(latencies) if latencies else 0

        logger.info(
            f"[KeyPool/Falcon] 完成: {len(keys_to_create)}/{count} 条, "
            f"耗时 {t_total:.2f}s, 吞吐量 {throughput:.1f} keys/sec"
        )

        return {
            'success': True,
            'pool_id': pool_id,
            'algorithm': f'CertificatelessFalcon-{target_security}',
            'generated': len(keys_to_create),
            'requested': count,
            'total_time_sec': round(t_total, 3),
            'throughput_per_sec': round(throughput, 1),
            'avg_latency_ms': round(avg_ms, 2),
            'expires_at': expires_at.isoformat(),
        }

    # ================================================================
    #  密钥取用
    # ================================================================
    @staticmethod
    def consume_key(
        node1_id: str, node2_id: str,
        algorithm: str = None, session: SessionKey = None,
        skip_locked: bool = True,
    ) -> Dict[str, Any]:
        """从密钥池中取出一条未使用的密钥。支持双向查找（A↔B 或 B↔A）。

        ---- 本函数在 KMS-013 之前的实际状态：从未成功执行过 ----
        两个断口叠在一起，且**每个都被下一层的错误文案掩盖**（roadmap §4）：

        1. 第 518 行用的是**裸名** `POOL_STATUS_READY_VALUES`，而它是
           `KeyPoolService` 的类属性 —— 静态方法里裸名解析到模块作用域，
           必然 `NameError`。经过 HTTP 入口时它被兜底 except 收成
           「密钥取用失败: name 'POOL_STATUS_READY_VALUES' is not defined」，
           看起来像脚本参数问题，实则函数从未跑起来。
        2. 修掉 1 之后还有第二层：`select_for_update` **必须在事务里**，
           而本仓库没开 `ATOMIC_REQUESTS`，autocommit 下 Django 直接抛
           `TransactionManagementError`。

        ---- 现在的事务边界 ----
        `with transaction.atomic():` 包住"选一条 + 标记 CONSUMED"这**整个**
        临界区，行锁才有效。⚠️ 边界是刻意比"写一行"宽的：原先 `atomic()`
        只包了标记那几行，选中与标记之间锁已释放 —— 两个并发请求会拿到
        **同一条** READY 行，随后各自标记、各自返回成功。那正是"重复消费"
        本身，而每个响应都显示 success。

        ---- `skip_locked` 的两种模式和它测什么 ----
        `True`（默认，生产路径）：被其它事务锁住的行直接跳过 → 并发 N 取 1
        时其余请求得到"没有可用"；这正是验收要钉住的恰好一个成功。
        `False`（**只给验收用**）：锁冲突时 InnoDB 等待，等对方提交后
        **重新读到的是 CONSUMED、按 WHERE 过滤掉** → 本函数返回失败而不是
        重复消费。两种模式都拒绝重复消费，区别只在这条路径能不能被走到。
        参数显式放在签名里，是为了让"等锁也安全"这件事**可以被断言**，
        而不是靠读 InnoDB 语义推断。

        ---- 可用性判据之外，为什么还要一道闸门（KMS-013 实测后改成"识破即纠正"）----
        可取的判据是「READY（含旧拼写）+ 未过期」，正常路径下不会取到死件：
        长期密钥被回收时 KMS-007 已把该池项转 REVOKED。但**标记本身可能漏网**
        （算法名认不出、手工改库、标记引入之前的行）—— 逃过标记的行会显示
        READY、被正常选中、直到解封时才失败，现场离原因已经很远。

        所以选中之后按行上自带的**长期密钥引用**（`long_term_key_id` /
        `long_term_key_version`，KMS-007 D3 回填）复核登记表。判据只用行上
        已有的事实，**不去猜"哪个节点是收件方"**：单向池（`pool_dist_*`）
        封给发送方自己、节点间池封给 node2，同是 kyber_kem 在行上分不出来，
        猜错方向的闸门比没有闸门更糟。引用查不到或没有引用的行只记日志
        放行 —— 不能核对 ≠ 有问题。

        ---- 复核不过时的三件事，缺一不可（第一版只有"拒绝"，实测后改的）----
        1. **就地标 REVOKED**（在行锁内）。不标的话：页面的 `effective_status`
           只看过期，会继续显示"可被会话取用"，与消费的结论再次互相矛盾；
           而且死件永远躺在 READY 集合里，每次消费都白探一次。标记用的
           判据与回收路径**同源**（登记行已 REVOKED），不是另写一套策略 ——
           它只是同一条结论在消费时刻的迟到应用。
        2. **跳过它继续取下一条**，并把跳过的事实放进响应（`skipped`）。
           只拒绝不跳过的问题实测出来了：消费按 `key_index` 取第一条，
           一条死件（index 最小）会**毒化整个节点对** —— 之后每次消费都
           撞在它身上返回 KEY_REVOKED，池子里明明有活件却永远取不出来。
           跳过也**不是静默**：跳了什么、为什么、标了什么，响应与日志都有。
        3. 全部探测完仍没有活件时，按第一条死件的错误码如实拒
           （`KEY_REVOKED` 而不是笼统的"没有可用"）—— 调用方的处置不同：
           该重新预分配，而不是"稍后再试"。

        ⚠️ 探测条数有上界（`MAX_PROBE`）：池子被大规模污染时不做无界扫描，
           在响应里如实说明"检查了 N 条"。`skip_locked` 模式下被别的事务
           锁住的行直接跳过，探测不会因此等待。
        """
        now = timezone.now()
        # 阶段 6（文档 §7.5）：可用的判据是 READY。
        # 必须把历史值 'unused' 一并纳入 —— 库里已有按旧值写入的行，
        # 只查 'READY' 会让它们永远取不出来（表现为"池子里有货却说没有"）。
        # ⚠️ 常量写**类限定名**：裸名解析不到类属性（见 docstring 断口 1）。
        q = PreDistributedKey.objects.filter(
            status__in=KeyPoolService.POOL_STATUS_READY_VALUES, expires_at__gt=now
        ).filter(
            models.Q(node1__node_id=node1_id, node2__node_id=node2_id) |
            models.Q(node1__node_id=node2_id, node2__node_id=node1_id)
        )
        if algorithm:
            q = q.filter(algorithm=algorithm)

        # ---- 整个临界区在一个事务里（见 docstring 断口 2）----
        # `MAX_PROBE`：同一次消费内最多探测的候选条数。池子被大规模污染时
        # 不做无界扫描 —— 与 `skip_locked` 的组合意味着探测本身也不等待。
        MAX_PROBE = 64
        with transaction.atomic():
            candidates = list(
                q.order_by('key_index').select_for_update(skip_locked=skip_locked)[:MAX_PROBE]
            )
            if not candidates:
                # 区分"池子空了"与"正被其它请求取用"：两者的处置不同
                # （补货 vs 稍后重试）。skip_locked 下拿不到行锁的那一眼
                # 与真没有行的表现相同，这里用一次无锁计数把话说清楚 ——
                # 计数会瞬时过时，所以措辞是"可能"。
                contended = PreDistributedKey.objects.filter(
                    status__in=KeyPoolService.POOL_STATUS_READY_VALUES, expires_at__gt=now,
                ).filter(
                    models.Q(node1__node_id=node1_id, node2__node_id=node2_id) |
                    models.Q(node1__node_id=node2_id, node2__node_id=node1_id)
                ).exists()
                hint = '（该节点对仍有可用条目，但正被其它请求同时取用）' if contended else ''
                return {
                    'success': False,
                    'code': C.ERR_POOL_ITEM_UNAVAILABLE,
                    'message': f'节点对 {node1_id} ↔ {node2_id} 没有可用的预分配密钥{hint}',
                }

            from .models import NodeLongTermKey
            key = None
            skipped = []
            first_dead = None
            for candidate in candidates:
                # 状态机守卫：消费只允许从 READY 出发（旧拼写归一后判定）。
                # 走到的行已经是 READY（WHERE 只放行它），这里防的是"将来有人
                # 把 WHERE 放宽"—— 表在 `api_contract.POOL_TRANSITIONS`。
                if not C.pool_transition_allowed(candidate.status, C.POOL_CONSUMED):
                    logger.error(
                        "池项 %s#%s 处于 %r，不允许迁移到 CONSUMED —— 跳过",
                        candidate.pool_id, candidate.key_index, candidate.status,
                    )
                    continue

                # 复核长期密钥引用（见 docstring：只看引用，不猜收件方）。
                family = {'kyber_kem': 'KYBER', 'falcon_lattice': 'FALCON'}.get(candidate.algorithm)
                if not (candidate.long_term_key_id
                        and candidate.long_term_key_version is not None and family):
                    logger.warning(
                        "池项 %s#%s（算法 %r）没有长期密钥引用或算法认不出，"
                        "消费前无法核对（放行）—— 失效标记由回收路径的退化面负责",
                        candidate.pool_id, candidate.key_index, candidate.algorithm,
                    )
                    key = candidate
                    break

                rows = NodeLongTermKey.objects.filter(
                    models.Q(node=candidate.node1) | models.Q(node=candidate.node2),
                    algorithm=family,
                    key_id=candidate.long_term_key_id,
                    key_version=candidate.long_term_key_version,
                )
                if rows.filter(status=C.KEY_STATUS_REVOKED).exists():
                    # 识破即纠正：就地标 REVOKED（同一判据的迟到应用），
                    # 跳过它继续取 —— 只拒绝不跳过时，一条死件会毒化整个节点对。
                    candidate.status = C.POOL_REVOKED
                    candidate.save(update_fields=['status'])
                    skipped.append({
                        'pool_id': candidate.pool_id,
                        'keyIndex': candidate.key_index,
                        'reason': 'KEY_REVOKED',
                    })
                    if first_dead is None:
                        first_dead = candidate
                    logger.warning(
                        "池项 %s#%s 引用的 %s 密钥 %s v%s 已回收：就地标记 REVOKED 并跳过",
                        candidate.pool_id, candidate.key_index, family,
                        candidate.long_term_key_id, candidate.long_term_key_version,
                    )
                    continue
                if not rows.exists():
                    logger.warning(
                        "池项 %s#%s 引用的 %s 密钥 %s v%s 在登记表中查不到，无法核对（放行）",
                        candidate.pool_id, candidate.key_index, family,
                        candidate.long_term_key_id, candidate.long_term_key_version,
                    )
                key = candidate
                break

            if key is None:
                # 探测完没有活件：按第一条死件的错误码拒（处置是"重新预分配"，
                # 不是"稍后再试"）。`skipped` 如实带上本次纠正了什么。
                if first_dead is not None:
                    return {
                        'success': False,
                        'code': C.ERR_KEY_REVOKED,
                        'skipped': skipped,
                        'message': (
                            f'节点对 {node1_id} ↔ {node2_id} 没有可用的预分配密钥：'
                            f'检查了 {len(skipped)} 条，全部引用的长期密钥已回收'
                            f'（已就地标记 REVOKED），请重新预分配'
                        ),
                    }
                return {
                    'success': False,
                    'code': C.ERR_POOL_ITEM_UNAVAILABLE,
                    'message': f'节点对 {node1_id} ↔ {node2_id} 没有可消费的预分配密钥',
                }

            # 标记为消费。统一写成新值 CONSUMED（旧拼写经 WHERE 进来，出去一律是新值）。
            key.status = C.POOL_CONSUMED
            key.used_at = now
            if session:
                key.used_by_session = session
            key.save(update_fields=['status', 'used_at', 'used_by_session'])
            consumed = {
                'key_id': key.id,
                'pool_id': key.pool_id,
                'key_index': key.key_index,
                'algorithm': key.algorithm,
                'encrypted_key_data': key.encrypted_key_data,
                'key_hash': key.key_hash,
                'status': key.status,
            }

        logger.info(
            f"[KeyPool] 消耗密钥 {consumed['pool_id']}#{consumed['key_index']} "
            f"for {node1_id} ↔ {node2_id}"
            + (f"（本次跳过 {len(skipped)} 条已回收）" if skipped else "")
        )

        return {'success': True, **consumed, **({'skipped': skipped} if skipped else {})}

    # ================================================================
    #  密钥池统计
    # ================================================================
    @staticmethod
    def get_pool_stats(node1_id: str = None, node2_id: str = None) -> Dict[str, Any]:
        """获取密钥池统计信息。

        KMS-013 起口径归一：「未使用」= READY + 全部旧拼写别名（含未过期的
        历史行），「已使用」= CONSUMED + 别名。改前这里分别查裸值
        `status='unused'` / `'used'`，与 `consume_key` 收的集合**不是同一套** ——
        统计说"还有 3 条可用"而消费说"没有可用"（或反过来），两个数字都
        出自同一个模块却互相矛盾，且没有任何一处会报错。
        新增 `reserved` / `revoked` 读数：监管页要如实显示五个状态
        （`RESERVED` 恒为 0 —— 它是保留值，见 `POOL_TRANSITIONS` 的说明）。
        """
        from django.db import models as db_models
        now = timezone.now()

        base_q = PreDistributedKey.objects.all()
        if node1_id and node2_id:
            base_q = base_q.filter(
                db_models.Q(node1__node_id=node1_id, node2__node_id=node2_id) |
                db_models.Q(node1__node_id=node2_id, node2__node_id=node1_id)
            )

        total = base_q.count()
        unused = base_q.filter(
            status__in=KeyPoolService.POOL_STATUS_READY_VALUES, expires_at__gt=now
        ).count()
        used = base_q.filter(status__in=KeyPoolService.POOL_STATUS_CONSUMED_VALUES).count()
        reserved = base_q.filter(status=KeyPoolService.POOL_STATUS_RESERVED).count()
        revoked = base_q.filter(status=KeyPoolService.POOL_STATUS_REVOKED).count()
        expired = base_q.filter(
            db_models.Q(status__in=KeyPoolService.POOL_STATUS_EXPIRED_VALUES)
            | db_models.Q(status__in=KeyPoolService.POOL_STATUS_READY_VALUES, expires_at__lte=now)
        ).count()

        by_algorithm = {}
        for alg in ['kyber_kem', 'falcon_lattice']:
            alg_q = base_q.filter(algorithm=alg)
            by_algorithm[alg] = {
                'total': alg_q.count(),
                'unused': alg_q.filter(
                    status__in=KeyPoolService.POOL_STATUS_READY_VALUES, expires_at__gt=now
                ).count(),
                'used': alg_q.filter(
                    status__in=KeyPoolService.POOL_STATUS_CONSUMED_VALUES
                ).count(),
            }

        # 按节点对统计
        node_pairs = []
        pairs = base_q.filter(
            status__in=KeyPoolService.POOL_STATUS_READY_VALUES, expires_at__gt=now
        ).values(
            'node1__node_id', 'node1__name', 'node2__node_id', 'node2__name', 'algorithm'
        ).annotate(available=db_models.Count('id')).order_by('-available')

        for p in pairs:
            node_pairs.append({
                'node1_id': p['node1__node_id'],
                'node1_name': p['node1__name'],
                'node2_id': p['node2__node_id'],
                'node2_name': p['node2__name'],
                'algorithm': p['algorithm'],
                'available': p['available'],
            })

        return {
            'total': total,
            'unused': unused,
            'used': used,
            'expired': expired,
            'reserved': reserved,
            'revoked': revoked,
            'by_algorithm': by_algorithm,
            'node_pairs': node_pairs,
        }

    # ================================================================
    #  过期清理（自动删除）
    # ================================================================
    @staticmethod
    def cleanup_expired() -> Dict[str, Any]:
        """删除过期的未使用/已下发密钥，同时清理本地文件中的过期密钥。

        ⚠️ 删除范围**刻意不含** RESERVED / REVOKED：前者是保留值（当前恒空，
        见 `POOL_TRANSITIONS`），后者是"依赖的密钥已回收"的**证据行** ——
        审计要能回答"这批池项后来怎么了"，删掉它等于把原因一起抹掉。
        """
        now = timezone.now()

        # 1. 删除数据库中过期且未被使用的密钥。
        # 范围与 KMS-013 之前**逐项等价**，只是换成符号名：
        #   READY（含旧拼写 'unused'）+ 旧拼写 'distributed'（等价 CONSUMED）
        #   + EXPIRED（含旧拼写 'expired'）。
        # ⚠️ 刻意**不含**规范值 'CONSUMED' / 'RESERVED' / 'REVOKED'：
        #    消费过的行是"被哪次会话用掉"的历史记录，RESERVED 是保留值，
        #    REVOKED 是"依赖的密钥已回收"的证据 —— 都被清理抹掉的话，
        #    审计再问"这批池项后来怎么了"就没有任何行可以回答。
        removable_statuses = (
            KeyPoolService.POOL_STATUS_READY_VALUES
            + ('distributed',)
            + KeyPoolService.POOL_STATUS_EXPIRED_VALUES
        )
        expired_keys = PreDistributedKey.objects.filter(
            expires_at__lte=now,
            status__in=removable_statuses,
        )
        deleted_count, _ = expired_keys.delete()
        logger.info(f"[KeyPool] 自动删除过期密钥: {deleted_count} 条")

        # 2. 清理本地密钥池文件中的过期条目
        local_cleaned = 0
        try:
            from .key_pool_local_storage import cleanup_expired_local_pools
            local_cleaned = cleanup_expired_local_pools()
        except Exception as e:
            logger.warning(f"[KeyPool] 清理本地过期密钥池失败: {e}")

        return {
            'cleaned': deleted_count,
            'local_cleaned': local_cleaned,
        }

    # ================================================================
    #  检查是否需要补充
    # ================================================================
    @staticmethod
    def check_and_replenish(
        node1_id: str, node2_id: str,
        algorithm: str = 'kyber_kem',
        target_size: int = None
    ) -> Optional[Dict[str, Any]]:
        """检查密钥池余量，低于阈值时自动补充。

        ⚠️ 余量口径与 `consume_key` 一致（READY + 旧拼写别名）。
        改前这里只数裸值 `'unused'`，而新写入的行一律是 `'READY'` ——
        于是"余量"恒为 0，每次检查都认为缺货并整批补货：补给动作看起来
        一直在工作，池子却越补越大，而没有任何一处报错。
        """
        from django.db import models as db_models
        target_size = target_size or KeyPoolService.DEFAULT_POOL_SIZE
        now = timezone.now()

        available = PreDistributedKey.objects.filter(
            status__in=KeyPoolService.POOL_STATUS_READY_VALUES,
            expires_at__gt=now, algorithm=algorithm,
        ).filter(
            db_models.Q(node1__node_id=node1_id, node2__node_id=node2_id) |
            db_models.Q(node1__node_id=node2_id, node2__node_id=node1_id)
        ).count()

        threshold = int(target_size * KeyPoolService.LOW_THRESHOLD_RATIO)
        if available >= threshold:
            return None  # 不需要补充

        replenish_count = target_size - available
        logger.info(
            f"[KeyPool] {node1_id} ↔ {node2_id} ({algorithm}) "
            f"余量 {available}/{target_size}，补充 {replenish_count} 条"
        )

        if algorithm == 'falcon_lattice':
            return KeyPoolService.generate_falcon_pool(node1_id, node2_id, replenish_count)
        else:
            return KeyPoolService.generate_kyber_pool(node1_id, node2_id, replenish_count)

    # ================================================================
    #  线上预分配：生成加密数据包供发送方节点下载
    # ================================================================
    @staticmethod
    def generate_distributable_pool(
        sender_node_id: str, receiver_node_id: str,
        count: int = None, expiry_hours: int = None
    ) -> Dict[str, Any]:
        """
        KDS 生成单向密钥池（sender → receiver），
        仅用发送方的 Kyber 公钥加密，返回一份加密数据包下发给发送方。

        密钥池是单向的：
        - sender_node 持有这批密钥，用于向 receiver_node 发送消息
        - receiver_node 如果想向 sender_node 发消息，需要另建一个密钥池

        流程:
        1. 生成 count 条随机 AES 会话密钥
        2. 对每条密钥:
           - Kyber encaps(sender_pk) → kem_ct + shared_secret
           - AES-GCM(shared_secret) 加密 AES 密钥 → 发送方的加密包
        3. 返回一份加密数据包
        4. 数据库记录 key_hash（不存明文）
        """
        count = count or KeyPoolService.DEFAULT_POOL_SIZE
        expiry_hours = expiry_hours or KeyPoolService.DEFAULT_EXPIRY_HOURS

        logger.info(
            f"[KeyPool/Distribute] 为 {sender_node_id} → {receiver_node_id} "
            f"生成单向密钥池: {count} 条"
        )
        t_start = time.perf_counter()

        try:
            sender_node = Node.objects.get(node_id=sender_node_id)
            receiver_node = Node.objects.get(node_id=receiver_node_id)
        except Node.DoesNotExist as e:
            return {'success': False, 'message': f'节点不存在: {e}'}

        # 闸门（KMS-007）：这份池子是**新工作**（为 sender 生成一批新的加密包），
        # 必须在读 `sender_node.kyber_public_key` 之前先判它还能不能用。
        #
        # 不做这一步会怎样：这批密文是**用 sender 自己的公钥**封的（node1=sender，
        # 由 sender 取件后自行解封）。密钥一旦被回收、而物化列因故没被清掉
        # （清列只发生在被回收的那把原本是 ACTIVE 时），池子会照常生成、
        # 记录照常显示可用；直到 sender 真正取件解封失败，才发现整批都是死件，
        # 而日志里从头到尾只有"生成完成"。
        #
        # ⚠️ 材料仍然从 `sender_node.kyber_public_key` 取（下面解码与 encaps 用的
        #    就是它）：登记行只当"能不能用"的判据，不当材料来源。
        # 错误码写进 message：调用方（views.py:3575 / kms_adapter.py:313）
        # 只转达 message，不转达 code —— 不写进文案就等于没有。
        # 返回的登记行**顺手留下**用于回填 `long_term_key_id/version`（KMS-007 D3）：
        # 那一行就是下面 encaps 所用材料的登记来源，不另查一次库 ——
        # 两次查询之间可能发生轮换，回填的引用会与实际封的材料对不上。
        try:
            long_term_key = require_usable_key(sender_node, 'KYBER')
        except C.ContractError as exc:
            return {
                'success': False,
                'code': exc.code,
                'message': f'发送方节点 {sender_node_id} {exc.message}（{exc.code}）',
            }

        # 只需要发送方的 Kyber 公钥（用于加密传输给发送方）
        if not sender_node.kyber_public_key:
            return {'success': False, 'message': f'发送方节点 {sender_node_id} 没有 Kyber 公钥'}

        try:
            sender_pk = base64.b64decode(sender_node.kyber_public_key)
        except Exception as e:
            return {'success': False, 'message': f'Kyber 公钥解码失败: {e}'}

        pk_len_map = {800: 512, 1184: 768, 1568: 1024}
        variant = pk_len_map.get(len(sender_pk), 512)

        try:
            kyber = KyberCrypto(variant)
        except Exception as e:
            return {'success': False, 'message': f'Kyber-{variant} 初始化失败: {e}'}

        pool_id = (
            f"pool_dist_{hashlib.sha256(f'{sender_node_id}_{receiver_node_id}_{time.time()}'.encode()).hexdigest()[:16]}"
        )
        expires_at = timezone.now() + timedelta(hours=expiry_hours)
        expires_at_iso = expires_at.isoformat()

        encrypted_keys = []  # 给发送方的加密密钥列表
        db_records = []
        latencies = []

        for i in range(count):
            t0 = time.perf_counter()
            try:
                # Step 1: 生成随机载荷会话密钥 —— D3 后是 SM4 的 16 字节
                payload_key = PayloadCipher.generate_key()
                key_hash = hashlib.sha256(payload_key).hexdigest()

                # Step 2: 用发送方的 Kyber 公钥封装（KEK 由 KEM 共享秘密派生，16 字节供 SM4 使用）
                kem_ct, ss = kyber.encrypt(sender_pk)
                kek = PayloadCipher.kek_from_shared_secret(PAYLOAD_ALGORITHM_SM4, ss)
                enc_key, nonce_tag = SM4Crypto.encrypt(payload_key, kek)
                nonce, tag = nonce_tag[:GCM_IV_BYTES], nonce_tag[GCM_IV_BYTES:]

                encrypted_keys.append({
                    'index': i,
                    'kem_ciphertext': base64.b64encode(kem_ct).decode(),
                    'encrypted_key': base64.b64encode(enc_key).decode(),
                    'nonce': base64.b64encode(nonce).decode(),
                    'tag': base64.b64encode(tag).decode(),
                    'key_hash': key_hash,
                    'payload_algorithm': PAYLOAD_ALGORITHM_SM4,
                })

                t1 = time.perf_counter()
                latency_ms = (t1 - t0) * 1000
                latencies.append(latency_ms)

                # Step 3: 数据库只记录 hash 和元数据
                db_records.append(PreDistributedKey(
                    pool_id=pool_id,
                    key_index=i,
                    node1=sender_node,
                    node2=receiver_node,
                    algorithm='kyber_kem',
                    encrypted_key_data='{}',
                    key_hash=key_hash,
                    status='distributed',
                    expires_at=expires_at,
                    generation_time_ms=latency_ms,
                    # KMS-007 D3：这批密文是用 sender 自己的长期公钥封的，
                    # 回填引用同样记下来。注意本状态（'distributed'）眼下**不在**
                    # `revoke_pool_items_for_key` 的失效范围内（它只动 READY/RESERVED，
                    # 已在 `POOL_STATUS_CONSUMED_VALUES` 里）—— 回填是为了让
                    # "哪把长期密钥封的这一批"有据可查；将来若把范围扩到这里，
                    # 精确面才有得可依。
                    long_term_key_id=long_term_key.key_id,
                    long_term_key_version=long_term_key.key_version,
                ))
            except Exception as e:
                logger.error(f"[KeyPool/Distribute] 第 {i} 条生成失败: {e}")
                continue

        with transaction.atomic():
            PreDistributedKey.objects.bulk_create(db_records)

        t_total = time.perf_counter() - t_start
        throughput = len(db_records) / t_total if t_total > 0 else 0
        avg_ms = sum(latencies) / len(latencies) if latencies else 0

        logger.info(
            f"[KeyPool/Distribute] 完成: {len(db_records)}/{count} 条, "
            f"耗时 {t_total:.2f}s, 吞吐量 {throughput:.1f} keys/sec"
        )

        return {
            'success': True,
            'pool_id': pool_id,
            'sender_node_id': sender_node_id,
            'receiver_node_id': receiver_node_id,
            'generated': len(db_records),
            'expires_at': expires_at_iso,
            'total_time_sec': round(t_total, 3),
            'throughput_per_sec': round(throughput, 1),
            'avg_latency_ms': round(avg_ms, 2),
            'encrypted_package': {
                'pool_id': pool_id,
                'node_id': sender_node_id,
                'peer_node_id': receiver_node_id,
                'algorithm': 'kyber_kem',
                'variant': variant,
                'expires_at': expires_at_iso,
                'encrypted_keys': encrypted_keys,
            },
        }