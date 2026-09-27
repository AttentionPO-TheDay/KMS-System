from django.core.management.base import BaseCommand
from pqkds.models import Node
from pqkds.node_service import NodeService
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = '修复所有节点的Falcon密钥不完整问题'

    def handle(self, *args, **options):
        try:
            nodes = Node.objects.all()
            self.stdout.write(f'开始检查 {nodes.count()} 个节点的Falcon密钥...\n')
            
            fixed_count = 0
            for node in nodes:
                pk_len = len(node.falcon_public_key) if node.falcon_public_key else 0
                sk_len = len(node.falcon_private_key) if node.falcon_private_key else 0
                lp_len = len(node.falcon_lattice_params) if node.falcon_lattice_params else 0
                
                if pk_len == 0 or sk_len == 0:
                    self.stdout.write(f'节点 {node.node_id}: 密钥不完整')
                    self.stdout.write(f'  falcon_public_key: {pk_len} bytes')
                    self.stdout.write(f'  falcon_private_key: {sk_len} bytes')
                    self.stdout.write(f'  falcon_lattice_params: {lp_len} bytes')
                    
                    self.stdout.write(f'  正在生成Falcon密钥...')
                    node_service = NodeService(node.node_id)
                    result = node_service.generate_falcon_keypair()
                    
                    if result['success']:
                        node.refresh_from_db()
                        pk_len = len(node.falcon_public_key) if node.falcon_public_key else 0
                        sk_len = len(node.falcon_private_key) if node.falcon_private_key else 0
                        self.stdout.write(f'  ✓ 修复成功')
                        self.stdout.write(f'    falcon_public_key: {pk_len} bytes')
                        self.stdout.write(f'    falcon_private_key: {sk_len} bytes')
                        fixed_count += 1
                    else:
                        self.stdout.write(f'  ✗ 修复失败: {result.get("message")}')
                    self.stdout.write('')
            
            self.stdout.write(self.style.SUCCESS(f'修复完成! 共修复 {fixed_count} 个节点'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'修复失败: {e}'))
            import traceback
            traceback.print_exc()

