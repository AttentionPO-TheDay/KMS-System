import logging
from django.utils import timezone
from django.db import transaction
from .models import SessionKey
logger = logging.getLogger(__name__)
class SessionKeyExpirationService:
    @staticmethod
    def check_session_expiration(session: SessionKey) -> dict:
        current_time = timezone.now()
        if session.expires_at <= current_time:
            logger.warning(
                f"会话 {session.session_id} 已过期。"
                f"过期时间: {session.expires_at}, 当前时间: {current_time}"
            )
            return {
                'expired': True,
                'message': f'会话密钥已过期，过期时间: {session.expires_at}',
                'expires_at': session.expires_at,
                'current_time': current_time,
                'time_remaining_seconds': None
            }
        time_remaining = (session.expires_at - current_time).total_seconds()
        return {
            'expired': False,
            'message': '会话密钥有效',
            'expires_at': session.expires_at,
            'current_time': current_time,
            'time_remaining_seconds': int(time_remaining)
        }
    @staticmethod
    @transaction.atomic
    def mark_session_as_expired(session: SessionKey) -> dict:
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
        current_time = timezone.now()
        expired_sessions = SessionKey.objects.filter(
            expires_at__lt=current_time
        ).exclude(status='expired')
        count = expired_sessions.count()
        if count > 0:
            expired_sessions.update(status='expired')
            logger.info(f"已清理 {count} 个过期的会话密钥")
        return {
            'success': True,
            'cleaned_count': count,
            'message': f'已清理 {count} 个过期的会话密钥'
        }
    @staticmethod
    def validate_session_for_use(session: SessionKey) -> dict:
        expiration_check = SessionKeyExpirationService.check_session_expiration(session)
        if expiration_check['expired']:
            SessionKeyExpirationService.mark_session_as_expired(session)
            return {
                'valid': False,
                'message': '会话密钥已过期，无法使用',
                'reason': 'expired'
            }
        valid_statuses = ['initiated', 'established', 'blockchain_recorded']
        if session.status not in valid_statuses:
            return {
                'valid': False,
                'message': f'会话状态异常: {session.status}',
                'reason': 'invalid_status'
            }
        return {
            'valid': True,
            'message': '会话密钥有效',
            'reason': None
        }