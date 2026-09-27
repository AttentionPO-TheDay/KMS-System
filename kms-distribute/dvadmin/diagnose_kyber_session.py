"""
诊断Kyber会话密钥问题
"""
import os
import sys
import django
import base64

sys.path.insert(0, 'D:/pythonProject/1.3-3/falcon-kds2 - aug/ruoyi')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ruoyi.settings')
django.setup()

from backend.pqkds.models import SessionKey
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

print("\n=== 诊断Kyber会话密钥 ===\n")

# 查找最近的Kyber会话
sessions = SessionKey.objects.filter(session_type='kyber_kem').order_by('-created_at')[:5]

if not sessions:
    print("❌ 没有找到Kyber会话")
else:
    for session in sessions:
        print(f"\n会话ID: {session.session_id}")
        print(f"节点1: {session.node1.node_id}")
        print(f"节点2: {session.node2.node_id}")
        print(f"状态: {session.status}")
        
        # 检查encrypted_session_key
        print(f"\nencrypted_session_key检查:")
        print(f"  类型: {type(session.encrypted_session_key)}")
        print(f"  值: {session.encrypted_session_key[:50] if session.encrypted_session_key else 'None'}...")
        
        if session.encrypted_session_key:
            try:
                decoded = base64.b64decode(session.encrypted_session_key)
                print(f"  ✓ Base64解码成功")
                print(f"  解码后长度: {len(decoded)} bytes")
                if len(decoded) < 32:
                    print(f"  ❌ 警告: 密钥长度不足 ({len(decoded)} < 32)")
                else:
                    print(f"  ✓ 密钥长度正确")
            except Exception as e:
                print(f"  ❌ Base64解码失败: {e}")
        
        # 检查key_exchange_data
        print(f"\nkey_exchange_data检查:")
        if session.key_exchange_data:
            import json
            try:
                data = json.loads(session.key_exchange_data)
                print(f"  ✓ JSON解析成功")
                print(f"  包含字段: {list(data.keys())}")
                if 'session_key' in data:
                    print(f"  session_key: {data['session_key'][:50]}...")
            except Exception as e:
                print(f"  ❌ JSON解析失败: {e}")

