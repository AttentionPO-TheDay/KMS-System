from celery.schedules import crontab
CELERY_BEAT_SCHEDULE = {
    'cleanup-expired-sessions': {
        'task': 'pqkds.session_expiration_tasks.cleanup_expired_sessions_task',
        'schedule': crontab(minute=0),
    },
    'validate-active-sessions': {
        'task': 'pqkds.session_expiration_tasks.validate_all_active_sessions_task',
        'schedule': crontab(minute='*/30'),
    },
}