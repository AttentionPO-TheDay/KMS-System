from django.core.management.base import BaseCommand
from pqkds.models import Node
from pqkds.node_service import NodeService
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = '修复节点005的Falcon密钥'

    def handle(self, *args, **options):
        try:
            node = Node.objects.get(node_id='005')
            self.stdout.write(f'节点005当前状态: {node.status}')
            self.stdout.write(f'  falcon_public_key长度: {len(node.falcon_public_key) if node.falcon_public_key else 0}')
            self.stdout.write(f'  falcon_private_key长度: {len(node.falcon_private_key) if node.falcon_private_key else 0}')
            self.stdout.write(f'  falcon_lattice_params长度: {len(node.falcon_lattice_params) if node.falcon_lattice_params else 0}')

            self.stdout.write('\n开始为节点005生成Falcon密钥...')
            node_service = NodeService('005')
            result = node_service.generate_falcon_keypair()
            self.stdout.write(f'生成结果: {result}')

            node.refresh_from_db()
            self.stdout.write(f'\n生成后节点005状态: {node.status}')
            self.stdout.write(f'  falcon_public_key长度: {len(node.falcon_public_key) if node.falcon_public_key else 0}')
            self.stdout.write(f'  falcon_private_key长度: {len(node.falcon_private_key) if node.falcon_private_key else 0}')
            self.stdout.write(f'  falcon_lattice_params长度: {len(node.falcon_lattice_params) if node.falcon_lattice_params else 0}')
            
            self.stdout.write(self.style.SUCCESS('修复完成!'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'修复失败: {e}'))
            import traceback
            traceback.print_exc()

