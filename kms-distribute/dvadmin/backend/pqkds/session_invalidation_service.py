"""
会话失效和过期管理服务

功能：
1. 当节点密钥更新时，标记所有相关会话为已失效
2. 当会话过期时，标记为已过期
3. 防止失效和过期的会话用于发送消息
4. 记录会话失效的原因和时间
"""

import logging
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from . import api_contract as C
from .models import SessionKey, SessionKeyInvalidation, Node, NodeKeyVersion

logger = logging.getLogger(__name__)


class SessionInvalidationService:
    """会话失效管理服务"""

    @staticmethod
    @transaction.atomic
    def invalidate_sessions_for_node_key_update(node: Node, reason: str = 'node_key_updated',
                                                *, algorithm: str = '', key_id: str = '',
                                                key_version=None) -> dict:
        """节点密钥被回收/更新时，标记**受影响**的会话为已失效。

        ---- KMS-016：从"该节点全部活跃会话"改成"引用那一版密钥的会话" ----

        原实现按 `Q(node1=node) | Q(node2=node)` 匹配 —— **该节点的所有活跃
        会话一并撤销**，不分算法、不分版本。两个后果都是实测过的：

          * 撤一把 KYBER，会把该节点名下 SM2/SSCL 保护的、以及用**另一把**
            Falcon 签名的活跃会话一起杀掉 —— 一次无关回收变成对所有在谈会话
            的单方面终止（KMS-016 全量验收 §7 实测踩中：撤 B 的 KYBER，
            B 的 SSCL 会话在关闭前就已经是 `revoked`）；
          * 与 KMS-007 修池项时消掉的缺陷同源（"撤一个算法清空全部"），
            池项那半当时改成了精确面 + 退化面，会话这半没有跟上。

        现在按 KMS-011 落库的**具体版本引用**匹配（`recipient_key_id/version`
        接收侧、`falcon_key_id/version` 发送侧签名密钥）：

          * 精确面：会话引用的那一版被撤 → 撤销；
          * 退化面：**历史行**（KMS-011 之前建的，四列全 NULL）无版本可对，
            退化为"同节点 + 同算法家族"（`wrapping_algorithms_for`），
            并在日志里如实说明 —— 不假装精确；
          * 无 `algorithm/key_id/key_version` 的调用方（还有两个老入口）走
            **粗粒度模式**：维持原行为，但记一条 warning —— "粗粒度"必须
            看得见，否则它会被当成精确的。

        返回值新增 `skipped_unmatched`（扫过但确认不受影响的历史行数）——
        与 `invalidated_count` 一起，让"撤了之后会话还剩几条"可审计。
        """
        name = C.canonical_algorithm(algorithm) if algorithm else ''
        version_int = None
        if isinstance(key_version, int) and not isinstance(key_version, bool):
            version_int = key_version
        elif isinstance(key_version, str) and key_version.strip().isdigit():
            version_int = int(key_version.strip())
        kid = str(key_id or '').strip()
        precise = bool(name and kid and version_int is not None)

        try:
            active_sessions = SessionKey.objects.filter(
                Q(node1=node) | Q(node2=node),
                status__in=['initiated', 'established', 'blockchain_recorded']
            )

            invalidated_count = 0
            invalidated_sessions = []
            skipped_unmatched = 0

            # 获取节点的当前密钥版本（沿用原语义：写入失效记录的 after 值）
            try:
                key_version_row = NodeKeyVersion.objects.filter(node=node).latest('kyber_version')
                kyber_version_after = key_version_row.kyber_version
                falcon_version_after = key_version_row.falcon_version
            except NodeKeyVersion.DoesNotExist:
                kyber_version_after = None
                falcon_version_after = None

            family = C.wrapping_algorithms_for(name) if name else ()

            for session in active_sessions:
                if precise:
                    affected, why = SessionInvalidationService._session_references(
                        session, node, name, kid, version_int, family,
                    )
                    if not affected:
                        skipped_unmatched += 1
                        logger.info(
                            '会话 %s 不引用被撤的 %s/%s v%s（%s）—— 保持原状',
                            session.session_id, name, kid, version_int, why,
                        )
                        continue
                else:
                    logger.warning(
                        '会话失效走**粗粒度**模式（调用方未提供 algorithm/key_id/version）：'
                        '节点 %s 的全部活跃会话都会被撤销 —— 这不是精确匹配',
                        node.node_id,
                    )

                session.status = 'revoked'
                session.save(update_fields=['status'])

                invalidation_record = SessionKeyInvalidation.objects.create(
                    session=session,
                    invalidated_node=node,
                    reason=reason,
                    kyber_version_after=kyber_version_after,
                    falcon_version_after=falcon_version_after
                )

                invalidated_count += 1
                invalidated_sessions.append({
                    'session_id': session.session_id,
                    'node1': session.node1.node_id,
                    'node2': session.node2.node_id,
                    'invalidation_id': invalidation_record.id
                })

                logger.info(
                    f"会话 {session.session_id} 已标记为失效。"
                    f"原因: {reason}, 触发节点: {node.node_id}"
                )

            return {
                'success': True,
                'invalidated_count': invalidated_count,
                'skipped_unmatched': skipped_unmatched,
                'invalidated_sessions': invalidated_sessions,
                'message': f'已标记 {invalidated_count} 个会话为失效状态'
                           + (f'（另有 {skipped_unmatched} 个不引用被撤版本，保持原状）'
                              if skipped_unmatched else '')
            }

        except Exception as e:
            logger.error(f"标记会话失效失败: {str(e)}")
            return {
                'success': False,
                'invalidated_count': 0,
                'message': f'标记会话失效失败: {str(e)}'
            }

    @staticmethod
    def _session_references(session, node, name, kid, version_int, family):
        """会话是否引用 (node, name, kid, version) 这一版密钥。返回 (bool, 说明)。

        两条引用面（与 KMS-011 落库的四列一一对应）：
          * 接收侧：`session.node2`（收件方）的 **保护密钥** 引用；
          * 发送侧：`session.node1`（发送方）的 **Falcon 签名密钥** 引用。
        历史行（四列全 NULL）退化为"同节点 + 同算法家族"，如实标注。
        """
        session_type = C.canonical_algorithm(session.session_type or '')

        # 接收侧：保护密钥
        if session.node2_id == node.id:
            if (session.recipient_key_id and session.recipient_key_version is not None):
                if (session.recipient_key_id == kid
                        and int(session.recipient_key_version) == version_int
                        and session_type == name):
                    return True, '接收侧保护密钥命中（精确）'
                return False, (f'接收侧引用的是 {session.recipient_key_id}'
                               f' v{session.recipient_key_version}（{session_type}）')
            # 历史行：版本列 NULL → 算法家族退化
            if family and session.session_type in family:
                return True, '历史行（无版本引用）按算法家族命中（退化）'
            return False, f'历史行（无版本引用）且算法 {session.session_type!r} 不在家族 {list(family)} 内'

        # 发送侧：Falcon 签名密钥
        if session.node1_id == node.id and name == 'FALCON':
            if session.falcon_key_id and session.falcon_key_version is not None:
                if (session.falcon_key_id == kid
                        and int(session.falcon_key_version) == version_int):
                    return True, '发送侧签名密钥命中（精确）'
                return False, f'发送侧签名引用的是 {session.falcon_key_id} v{session.falcon_key_version}'
            return False, '历史行（无签名密钥引用），Falcon 撤钥无法退化关联'

        return False, f'会话与节点 {node.node_id} 的该角色（{name}）无引用关系'

    @staticmethod
    def check_session_validity(session: SessionKey) -> dict:
        """
        检查会话是否有效（未失效且未过期）
        
        Args:
            session: 要检查的会话
        
        Returns:
            dict: 包含有效性状态的字典
        """
        # 检查会话状态
        if session.status == 'revoked':
            return {
                'valid': False,
                'reason': 'revoked',
                'message': '会话已失效（节点密钥已更新）',
                'status': session.status
            }
        
        if session.status == 'expired':
            return {
                'valid': False,
                'reason': 'expired',
                'message': '会话已过期',
                'status': session.status
            }
        
        # 检查会话是否过期
        current_time = timezone.now()
        if session.expires_at <= current_time:
            return {
                'valid': False,
                'reason': 'expired',
                'message': f'会话已过期（过期时间: {session.expires_at}）',
                'status': session.status,
                'expires_at': session.expires_at
            }
        
        # 检查会话状态是否有效
        valid_statuses = ['initiated', 'established', 'blockchain_recorded']
        if session.status not in valid_statuses:
            return {
                'valid': False,
                'reason': 'invalid_status',
                'message': f'会话状态异常: {session.status}',
                'status': session.status
            }
        
        # 计算剩余时间
        time_remaining = (session.expires_at - current_time).total_seconds()
        
        return {
            'valid': True,
            'reason': None,
            'message': '会话有效',
            'status': session.status,
            'expires_at': session.expires_at,
            'time_remaining_seconds': int(time_remaining)
        }

    @staticmethod
    @transaction.atomic
    def mark_session_as_expired(session: SessionKey) -> dict:
        """
        标记会话为已过期
        
        Args:
            session: 要标记的会话
        
        Returns:
            dict: 操作结果
        """
        try:
            session.status = 'expired'
            session.save(update_fields=['status'])
            logger.info(f"会话 {session.session_id} 已标记为过期状态")
            return {
                'success': True,
                'message': f'会话 {session.session_id} 已标记为过期',
                'session_id': session.session_id
            }
        except Exception as e:
            logger.error(f"标记会话过期失败: {str(e)}")
            return {
                'success': False,
                'message': f'标记会话过期失败: {str(e)}'
            }

    @staticmethod
    @transaction.atomic
    def cleanup_expired_sessions() -> dict:
        """
        清理所有过期的会话
        
        Returns:
            dict: 清理结果
        """
        try:
            current_time = timezone.now()
            expired_sessions = SessionKey.objects.filter(
                expires_at__lt=current_time
            ).exclude(status__in=['expired', 'revoked'])
            
            count = expired_sessions.count()
            if count > 0:
                expired_sessions.update(status='expired')
                logger.info(f"已清理 {count} 个过期的会话密钥")
            
            return {
                'success': True,
                'cleaned_count': count,
                'message': f'已清理 {count} 个过期的会话密钥'
            }
        except Exception as e:
            logger.error(f"清理过期会话失败: {str(e)}")
            return {
                'success': False,
                'message': f'清理过期会话失败: {str(e)}'
            }

    @staticmethod
    def get_session_invalidation_history(session: SessionKey) -> list:
        """
        获取会话的失效历史记录
        
        Args:
            session: 会话对象
        
        Returns:
            list: 失效记录列表
        """
        try:
            invalidations = SessionKeyInvalidation.objects.filter(
                session=session
            ).order_by('-invalidated_at')
            
            history = []
            for inv in invalidations:
                history.append({
                    'id': inv.id,
                    'reason': inv.reason,
                    'invalidated_node': inv.invalidated_node.node_id,
                    'invalidated_at': inv.invalidated_at.isoformat(),
                    'kyber_version_before': inv.kyber_version_before,
                    'kyber_version_after': inv.kyber_version_after,
                    'falcon_version_before': inv.falcon_version_before,
                    'falcon_version_after': inv.falcon_version_after
                })
            
            return history
        except Exception as e:
            logger.error(f"获取会话失效历史失败: {str(e)}")
            return []

    @staticmethod
    def get_node_invalidated_sessions(node: Node, limit: int = 100) -> dict:
        """
        获取由某个节点密钥更新导致失效的所有会话
        
        Args:
            node: 节点对象
            limit: 返回记录的最大数量
        
        Returns:
            dict: 失效会话列表
        """
        try:
            invalidations = SessionKeyInvalidation.objects.filter(
                invalidated_node=node
            ).order_by('-invalidated_at')[:limit]
            
            sessions = []
            for inv in invalidations:
                sessions.append({
                    'session_id': inv.session.session_id,
                    'node1': inv.session.node1.node_id,
                    'node2': inv.session.node2.node_id,
                    'reason': inv.reason,
                    'invalidated_at': inv.invalidated_at.isoformat(),
                    'current_status': inv.session.status
                })
            
            return {
                'success': True,
                'total': len(sessions),
                'sessions': sessions
            }
        except Exception as e:
            logger.error(f"获取节点失效会话失败: {str(e)}")
            return {
                'success': False,
                'message': f'获取节点失效会话失败: {str(e)}'
            }

    @staticmethod
    @transaction.atomic
    def validate_session_for_message_sending(session: SessionKey) -> dict:
        """
        验证会话是否可用于发送消息
        
        Args:
            session: 会话对象
        
        Returns:
            dict: 验证结果
        """
        # 检查会话有效性
        validity_check = SessionInvalidationService.check_session_validity(session)
        
        if not validity_check['valid']:
            return {
                'can_send': False,
                'reason': validity_check['reason'],
                'message': validity_check['message']
            }
        
        # 检查会话密钥数据是否完整
        if not session.key_exchange_data or not session.encrypted_session_key:
            return {
                'can_send': False,
                'reason': 'incomplete_key_data',
                'message': '会话密钥数据不完整'
            }
        
        return {
            'can_send': True,
            'reason': None,
            'message': '会话可用于发送消息',
            'time_remaining_seconds': validity_check.get('time_remaining_seconds')
        }

    @staticmethod
    def get_session_status_summary(node: Node = None) -> dict:
        """
        获取会话状态统计摘要
        
        Args:
            node: 可选，指定节点则只统计该节点相关的会话
        
        Returns:
            dict: 状态统计信息
        """
        try:
            if node:
                sessions = SessionKey.objects.filter(
                    Q(node1=node) | Q(node2=node)
                )
            else:
                sessions = SessionKey.objects.all()
            
            total = sessions.count()
            initiated = sessions.filter(status='initiated').count()
            established = sessions.filter(status='established').count()
            blockchain_recorded = sessions.filter(status='blockchain_recorded').count()
            expired = sessions.filter(status='expired').count()
            revoked = sessions.filter(status='revoked').count()
            
            # 计算即将过期的会话（24小时内）
            current_time = timezone.now()
            from datetime import timedelta
            soon_expire_time = current_time + timedelta(hours=24)
            soon_expire = sessions.filter(
                expires_at__lte=soon_expire_time,
                expires_at__gt=current_time,
                status__in=['initiated', 'established', 'blockchain_recorded']
            ).count()
            
            return {
                'success': True,
                'total': total,
                'initiated': initiated,
                'established': established,
                'blockchain_recorded': blockchain_recorded,
                'expired': expired,
                'revoked': revoked,
                'soon_expire': soon_expire,
                'active': initiated + established + blockchain_recorded
            }
        except Exception as e:
            logger.error(f"获取会话状态统计失败: {str(e)}")
            return {
                'success': False,
                'message': f'获取会话状态统计失败: {str(e)}'
            }

