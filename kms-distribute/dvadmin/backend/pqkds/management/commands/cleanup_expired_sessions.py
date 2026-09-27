from django.core.management.base import BaseCommand
from django.utils import timezone
from pqkds.models import SessionKey
from pqkds.session_key_expiration_service import SessionKeyExpirationService
import logging
logger = logging.getLogger(__name__)
class Command(BaseCommand):
    help = '清理过期的会话密钥'
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='仅显示将要清理的会话，不实际删除',
        )
    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        self.stdout.write(self.style.SUCCESS('开始清理过期的会话密钥...'))
        result = SessionKeyExpirationService.cleanup_expired_sessions()
        if result['success']:
            cleaned_count = result['cleaned_count']
            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ 成功清理 {cleaned_count} 个过期的会话密钥'
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(
                    f'✗ 清理失败: {result.get("message", "Unknown error")}'
                )
            )