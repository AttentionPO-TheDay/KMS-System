from django.core.management.base import BaseCommand
from django.db import connection
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = '增加 MySQL max_allowed_packet 配置'

    def handle(self, *args, **options):
        try:
            with connection.cursor() as cursor:
                # 查看当前配置
                cursor.execute("SHOW VARIABLES LIKE 'max_allowed_packet'")
                result = cursor.fetchone()
                if result:
                    current_value = result[1]
                    self.stdout.write(f"当前 max_allowed_packet: {current_value} bytes")
                
                # 设置为 256MB
                cursor.execute("SET GLOBAL max_allowed_packet = 268435456")
                self.stdout.write(self.style.SUCCESS("✓ 已设置 max_allowed_packet = 256MB"))
                
                # 验证设置
                cursor.execute("SHOW VARIABLES LIKE 'max_allowed_packet'")
                result = cursor.fetchone()
                if result:
                    new_value = result[1]
                    self.stdout.write(f"新的 max_allowed_packet: {new_value} bytes")
                    
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ 设置失败: {e}"))
            self.stdout.write(self.style.WARNING(
                "请手动修改 MySQL 配置文件 (my.cnf 或 my.ini):\n"
                "[mysqld]\n"
                "max_allowed_packet = 256M"
            ))

