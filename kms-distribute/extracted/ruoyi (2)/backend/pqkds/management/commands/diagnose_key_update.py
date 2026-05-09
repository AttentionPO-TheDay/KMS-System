from django.core.management.base import BaseCommand
from pqkds.models import Node
from pqkds.blockchain_service import BlockchainService
from pqkds.node_service import NodeService
class Command(BaseCommand):
    help = '诊断密钥更新问题'
    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS(' 诊断密钥更新问题...')
        )
        self.stdout.write("=" * 50)
        self.stdout.write(" 检查节点状态:")
        nodes = Node.objects.all()[:5]
        for node in nodes:
            kyber_status = '' if node.kyber_public_key else ''
            falcon_status = '' if node.falcon_public_key else ''
            self.stdout.write(f"   节点 {node.node_id}: 状态={node.status}, Kyber={kyber_status}, Falcon={falcon_status}")
        self.stdout.write(f"\n 检查区块链服务:")
        blockchain = BlockchainService()
        if blockchain.contract:
            self.stdout.write("    区块链服务已连接")
            test_node = nodes.first()
            if test_node:
                try:
                    exists = blockchain.contract.functions.nodeExists(test_node.node_id).call()
                    status = ' 已注册' if exists else ' 未注册'
                    self.stdout.write(f"   节点 {test_node.node_id} 区块链注册状态: {status}")
                except Exception as e:
                    self.stdout.write(f"    检查节点注册状态失败: {e}")
        else:
            self.stdout.write("    区块链服务未连接")
        self.stdout.write(f"\n 测试密钥更新功能:")
        test_node = nodes.first()
        if test_node:
            try:
                node_service = NodeService(test_node.node_id)
                self.stdout.write(f"    NodeService创建成功 (节点: {test_node.node_id})")
                if hasattr(node_service, 'update_kyber_keys'):
                    self.stdout.write("    update_kyber_keys方法存在")
                else:
                    self.stdout.write("    update_kyber_keys方法不存在")
                if hasattr(node_service, 'update_falcon_keys'):
                    self.stdout.write("    update_falcon_keys方法存在")
                else:
                    self.stdout.write("    update_falcon_keys方法不存在")
            except Exception as e:
                self.stdout.write(f"    NodeService创建失败: {e}")
        self.stdout.write(f"\n API路径检查:")
        self.stdout.write("   预期的API路径: /api/pqkds/nodes/{node_id}/update_keys/")
        self.stdout.write("   方法: POST")
        self.stdout.write("   参数: key_type, security_level")
        self.stdout.write(f"\n 尝试实际调用密钥更新:")
        if test_node and blockchain.contract:
            try:
                exists = blockchain.contract.functions.nodeExists(test_node.node_id).call()
                if not exists:
                    self.stdout.write(f"    节点 {test_node.node_id} 未在区块链注册，尝试注册...")
                    register_result = blockchain.register_node_on_blockchain(
                        test_node.node_id,
                        test_node.name,
                        test_node.ip_address or "127.0.0.1",
                        test_node.port or 8080
                    )
                    if register_result['success']:
                        self.stdout.write("    节点注册成功")
                    else:
                        self.stdout.write(f"    节点注册失败: {register_result.get('error')}")
                        return
                self.stdout.write("    尝试Kyber密钥更新...")
                node_service = NodeService(test_node.node_id)
                result = node_service.update_kyber_keys(512)
                if result['success']:
                    self.stdout.write("    Kyber密钥更新成功")
                else:
                    self.stdout.write(f"    Kyber密钥更新失败: {result.get('message')}")
            except Exception as e:
                self.stdout.write(f"    密钥更新测试失败: {e}")
        self.stdout.write(f"\n" + "=" * 50)
        self.stdout.write(
            self.style.SUCCESS(' 诊断完成')
        )