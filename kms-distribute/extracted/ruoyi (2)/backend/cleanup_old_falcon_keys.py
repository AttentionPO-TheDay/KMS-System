import os
import sys
import django
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings.py')
try:
    django.setup()
except Exception as e:
    print(f"Django setup failed: {e}")
    sys.exit(1)
from pqkds.models import Node
total_nodes = Node.objects.count()
updated_count = 0
print(f"开始清理Falcon旧公钥...")
print(f"总节点数: {total_nodes}\n")
for node in Node.objects.all():
    if node.falcon_public_key and len(node.falcon_public_key) > 5000:
        print(f"[清理] 节点 {node.node_id}: 旧公钥长度 {len(node.falcon_public_key)}")
        node.falcon_public_key = ""
        node.falcon_private_key = ""
        node.save()
        updated_count += 1
print(f"\n✓ 清理完成")
print(f"  总节点数: {total_nodes}")
print(f"  已清理: {updated_count}")
print(f"  保留: {total_nodes - updated_count}")