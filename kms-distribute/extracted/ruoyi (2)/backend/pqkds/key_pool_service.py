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

from .models import Node, SessionKey, PreDistributedKey
from .crypto_utils import KyberCrypto, AESCrypto

logger = logging.getLogger(__name__)


class KeyPoolService:
    """密钥池管理服务"""

    DEFAULT_POOL_SIZE = 50
    DEFAULT_EXPIRY_HOURS = 24
    LOW_THRESHOLD_RATIO = 0.2  # 低于 20% 触发补充

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
                # Step 1: 随机 AES 密钥
                aes_key = os.urandom(32)
                key_hash = hashlib.sha256(aes_key).hexdigest()

                # Step 2: Kyber encaps
                kem_ct, shared_secret = kyber.encrypt(receiver_pk)

                # Step 3: AES-GCM 加密
                from Crypto.Cipher import AES as AES_Cipher
                aes_kem_key = shared_secret[:32]
                cipher = AES_Cipher.new(aes_kem_key, AES_Cipher.MODE_GCM)
                encrypted_aes_key, tag = cipher.encrypt_and_digest(aes_key)

                encrypted_data = json.dumps({
                    'kem_ciphertext': base64.b64encode(kem_ct).decode(),
                    'encrypted_aes_key': base64.b64encode(encrypted_aes_key).decode(),
                    'nonce': base64.b64encode(cipher.nonce).decode(),
                    'tag': base64.b64encode(tag).decode(),
                    'variant': variant,
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
                    status='unused',
                    expires_at=expires_at,
                    generation_time_ms=latency_ms,
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
                # Step 1: 随机 AES 密钥
                aes_key = os.urandom(32)
                key_hash = hashlib.sha256(aes_key).hexdigest()

                # Step 2: Falcon 格密码加密
                enc_result = falcon_enc.encrypt_aes_key_with_falcon(
                    recipient_id=node2_id,
                    aes_key=aes_key,
                    recipient_public_key_b64=node2.falcon_public_key
                )

                if not enc_result.get('success'):
                    logger.warning(f"[KeyPool/Falcon] 第 {i} 条加密失败: {enc_result.get('message')}")
                    continue

                encrypted_data = json.dumps({
                    'ciphertext': enc_result['ciphertext'],
                    'algorithm': enc_result.get('algorithm', f'CertificatelessFalcon-{target_security}'),
                    'security_level': target_security,
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
                    status='unused',
                    expires_at=expires_at,
                    generation_time_ms=latency_ms,
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
        algorithm: str = None, session: SessionKey = None
    ) -> Dict[str, Any]:
        """
        从密钥池中取出一条未使用的密钥。
        支持双向查找（A↔B 或 B↔A）。
        """
        now = timezone.now()
        q = PreDistributedKey.objects.filter(
            status='unused', expires_at__gt=now
        ).filter(
            models.Q(node1__node_id=node1_id, node2__node_id=node2_id) |
            models.Q(node1__node_id=node2_id, node2__node_id=node1_id)
        )
        if algorithm:
            q = q.filter(algorithm=algorithm)

        key = q.order_by('key_index').select_for_update(skip_locked=True).first()
        if not key:
            return {
                'success': False,
                'message': f'节点对 {node1_id} ↔ {node2_id} 没有可用的预分配密钥'
            }

        with transaction.atomic():
            key.status = 'used'
            key.used_at = now
            if session:
                key.used_by_session = session
            key.save(update_fields=['status', 'used_at', 'used_by_session'])

        logger.info(
            f"[KeyPool] 消耗密钥 {key.pool_id}#{key.key_index} "
            f"({key.get_algorithm_display()}) for {node1_id} ↔ {node2_id}"
        )

        return {
            'success': True,
            'key_id': key.id,
            'pool_id': key.pool_id,
            'key_index': key.key_index,
            'algorithm': key.algorithm,
            'encrypted_key_data': key.encrypted_key_data,
            'key_hash': key.key_hash,
        }

    # ================================================================
    #  密钥池统计
    # ================================================================
    @staticmethod
    def get_pool_stats(node1_id: str = None, node2_id: str = None) -> Dict[str, Any]:
        """获取密钥池统计信息"""
        from django.db import models as db_models
        now = timezone.now()

        base_q = PreDistributedKey.objects.all()
        if node1_id and node2_id:
            base_q = base_q.filter(
                db_models.Q(node1__node_id=node1_id, node2__node_id=node2_id) |
                db_models.Q(node1__node_id=node2_id, node2__node_id=node1_id)
            )

        total = base_q.count()
        unused = base_q.filter(status='unused', expires_at__gt=now).count()
        used = base_q.filter(status='used').count()
        expired = base_q.filter(
            db_models.Q(status='expired') | db_models.Q(status='unused', expires_at__lte=now)
        ).count()

        by_algorithm = {}
        for alg in ['kyber_kem', 'falcon_lattice']:
            alg_q = base_q.filter(algorithm=alg)
            by_algorithm[alg] = {
                'total': alg_q.count(),
                'unused': alg_q.filter(status='unused', expires_at__gt=now).count(),
                'used': alg_q.filter(status='used').count(),
            }

        # 按节点对统计
        node_pairs = []
        pairs = base_q.filter(status='unused', expires_at__gt=now).values(
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
            'by_algorithm': by_algorithm,
            'node_pairs': node_pairs,
        }

    # ================================================================
    #  过期清理（自动删除）
    # ================================================================
    @staticmethod
    def cleanup_expired() -> Dict[str, Any]:
        """删除过期的未使用/已下发密钥，同时清理本地文件中的过期密钥"""
        now = timezone.now()

        # 1. 删除数据库中过期且未被使用的密钥（unused / distributed / expired）
        expired_keys = PreDistributedKey.objects.filter(
            expires_at__lte=now,
            status__in=['unused', 'distributed', 'expired']
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
        """检查密钥池余量，低于阈值时自动补充"""
        from django.db import models as db_models
        target_size = target_size or KeyPoolService.DEFAULT_POOL_SIZE
        now = timezone.now()

        available = PreDistributedKey.objects.filter(
            status='unused', expires_at__gt=now, algorithm=algorithm
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

        from Crypto.Cipher import AES as AES_Cipher

        for i in range(count):
            t0 = time.perf_counter()
            try:
                # Step 1: 生成随机 AES 会话密钥
                aes_key = os.urandom(32)
                key_hash = hashlib.sha256(aes_key).hexdigest()

                # Step 2: 用发送方的 Kyber 公钥加密
                kem_ct, ss = kyber.encrypt(sender_pk)
                cipher = AES_Cipher.new(ss[:32], AES_Cipher.MODE_GCM)
                enc_key, tag = cipher.encrypt_and_digest(aes_key)

                encrypted_keys.append({
                    'index': i,
                    'kem_ciphertext': base64.b64encode(kem_ct).decode(),
                    'encrypted_key': base64.b64encode(enc_key).decode(),
                    'nonce': base64.b64encode(cipher.nonce).decode(),
                    'tag': base64.b64encode(tag).decode(),
                    'key_hash': key_hash,
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