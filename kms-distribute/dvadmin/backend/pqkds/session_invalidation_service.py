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
from .models import SessionKey, SessionKeyInvalidation, Node, NodeKeyVersion

logger = logging.getLogger(__name__)


class SessionInvalidationService:
    """会话失效管理服务"""

    @staticmethod
    @transaction.atomic
    def invalidate_sessions_for_node_key_update(node: Node, reason: str = 'node_key_updated') -> dict:
        """
        当节点密钥更新时，标记所有与该节点相关的会话为已失效
        
        Args:
            node: 更新密钥的节点
            reason: 失效原因 ('node_key_updated' 或 'manual_revocation')
        
        Returns:
            dict: 包含失效会话数量和详情的字典
        """
        try:
            # 获取所有与该节点相关的活跃会话
            active_sessions = SessionKey.objects.filter(
                Q(node1=node) | Q(node2=node),
                status__in=['initiated', 'established', 'blockchain_recorded']
            )
            
            invalidated_count = 0
            invalidated_sessions = []
            
            # 获取节点的当前密钥版本
            try:
                key_version = NodeKeyVersion.objects.filter(node=node).latest('kyber_version')
                kyber_version_after = key_version.kyber_version
                falcon_version_after = key_version.falcon_version
            except NodeKeyVersion.DoesNotExist:
                kyber_version_after = None
                falcon_version_after = None
            
            for session in active_sessions:
                # 标记会话为已失效
                session.status = 'revoked'
                session.save(update_fields=['status'])
                
                # 记录失效信息
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
                'invalidated_sessions': invalidated_sessions,
                'message': f'已标记 {invalidated_count} 个会话为失效状态'
            }
        
        except Exception as e:
            logger.error(f"标记会话失效失败: {str(e)}")
            return {
                'success': False,
                'invalidated_count': 0,
                'message': f'标记会话失效失败: {str(e)}'
            }

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

