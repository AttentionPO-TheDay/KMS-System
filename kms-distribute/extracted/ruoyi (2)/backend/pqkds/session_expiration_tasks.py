import logging
from celery import shared_task
from django.utils import timezone
from .session_key_expiration_service import SessionKeyExpirationService
logger = logging.getLogger(__name__)
@shared_task(bind=True, max_retries=3)
def cleanup_expired_sessions_task(self):
    try:
        logger.info("开始执行定时任务：清理过期的会话密钥")
        result = SessionKeyExpirationService.cleanup_expired_sessions()
        if result['success']:
            logger.info(
                f"定时任务执行成功：已清理 {result['cleaned_count']} 个过期的会话密钥"
            )
            return {
                'status': 'success',
                'cleaned_count': result['cleaned_count'],
                'message': result['message']
            }
        else:
            logger.error(f"定时任务执行失败: {result.get('message', 'Unknown error')}")
            return {
                'status': 'failed',
                'message': result.get('message', 'Unknown error')
            }
    except Exception as e:
        logger.error(f"定时任务执行异常: {str(e)}")
        raise self.retry(exc=e, countdown=60)
@shared_task(bind=True, max_retries=3)
def validate_all_active_sessions_task(self):
    try:
        from .models import SessionKey
        logger.info("开始执行定时任务：验证所有活跃会话")
        active_sessions = SessionKey.objects.filter(
            status__in=['initiated', 'established', 'blockchain_recorded']
        )
        expired_count = 0
        valid_count = 0
        for session in active_sessions:
            validation_result = SessionKeyExpirationService.validate_session_for_use(session)
            if not validation_result['valid']:
                expired_count += 1
                logger.warning(
                    f"会话 {session.session_id} 验证失败: {validation_result['message']}"
                )
            else:
                valid_count += 1
        logger.info(
            f"会话验证完成：有效会话 {valid_count} 个，过期会话 {expired_count} 个"
        )
        return {
            'status': 'success',
            'valid_sessions': valid_count,
            'expired_sessions': expired_count,
            'message': f'验证完成：有效会话 {valid_count} 个，过期会话 {expired_count} 个'
        }
    except Exception as e:
        logger.error(f"会话验证定时任务执行异常: {str(e)}")
        raise self.retry(exc=e, countdown=60)