from django.core.management.base import BaseCommand
from django.db import transaction
from pqkds.models import SessionKey, Message, Transaction, Node, BlockchainConfig
import logging
logger = logging.getLogger(__name__)
class Command(BaseCommand):
    help = '清理区块链相关数据（会话密钥、消息、交易记录）'
    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='确认执行清理操作',
        )
        parser.add_argument(
            '--reset-nodes',
            action='store_true',
            help='同时重置节点状态',
        )
    def handle(self, *args, **options):
        if not options['confirm']:
            self.stdout.write(
                self.style.WARNING(
                    '  这将清理所有会话密钥、消息和交易记录！\n'
                    '请使用 --confirm 参数确认执行此操作。\n'
                    '使用 --reset-nodes 参数同时重置节点状态。'
                )
            )
            return
        self.stdout.write(' 开始清理区块链相关数据...')
        try:
            with transaction.atomic():
                session_count = SessionKey.objects.count()
                message_count = Message.objects.count()
                transaction_count = Transaction.objects.count()
                node_count = Node.objects.count()
                self.stdout.write(f' 数据统计:')
                self.stdout.write(f'   - 会话密钥: {session_count} 个')
                self.stdout.write(f'   - 消息记录: {message_count} 个')
                self.stdout.write(f'   - 交易记录: {transaction_count} 个')
                self.stdout.write(f'   - 节点数量: {node_count} 个')
                if session_count > 0:
                    SessionKey.objects.all().delete()
                    self.stdout.write(
                        self.style.SUCCESS(f' 已清理 {session_count} 个会话密钥记录')
                    )
                if message_count > 0:
                    Message.objects.all().delete()
                    self.stdout.write(
                        self.style.SUCCESS(f' 已清理 {message_count} 个消息记录')
                    )
                if transaction_count > 0:
                    Transaction.objects.all().delete()
                    self.stdout.write(
                        self.style.SUCCESS(f' 已清理 {transaction_count} 个交易记录')
                    )
                if options['reset_nodes']:
                    reset_count = 0
                    for node in Node.objects.all():
                        if node.status in ['kyber_uploaded', 'partial_key_received', 'falcon_generated', 'active']:
                            node.status = 'registered'
                            node.save(update_fields=['status'])
                            reset_count += 1
                    if reset_count > 0:
                        self.stdout.write(
                            self.style.SUCCESS(f' 已重置 {reset_count} 个节点的状态')
                        )
                active_config = BlockchainConfig.objects.filter(is_active=True).first()
                if active_config:
                    self.stdout.write(f'\n 当前活跃区块链配置:')
                    self.stdout.write(f'   - 名称: {active_config.name}')
                    self.stdout.write(f'   - 合约地址: {active_config.contract_address}')
                    self.stdout.write(f'   - 提供者URL: {active_config.provider_url}')
                self.stdout.write(
                    self.style.SUCCESS('\n 区块链相关数据清理完成！')
                )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f' 清理失败: {str(e)}')
            )
            raise