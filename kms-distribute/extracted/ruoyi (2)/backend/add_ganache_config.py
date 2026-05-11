#!/usr/bin/env python
"""
添加 Ganache 区块链配置脚本
使用方法: python add_ganache_config.py
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
django.setup()

from pqkds.models import BlockchainConfig

def add_ganache_config():
    print("\n" + "="*60)
    print("🔗 Ganache 区块链配置添加工具")
    print("="*60)

    # 获取用户输入
    print("\n请输入 Ganache 配置信息（从 npx ganache 输出中复制）：\n")

    name = input("配置名称 [Ganache Local]: ").strip() or "Ganache Local"
    provider_url = input("Provider URL [http://127.0.0.1:7545]: ").strip() or "http://127.0.0.1:7545"
    account_address = input("账户地址 (0x...): ").strip()
    private_key = input("私钥 (0x...): ").strip()
    network_id = input("网络ID [5777]: ").strip() or "5777"

    # 验证输入
    if not account_address or not account_address.startswith('0x'):
        print("❌ 错误：账户地址必须以 0x 开头")
        return False

    if not private_key or not private_key.startswith('0x'):
        print("❌ 错误：私钥必须以 0x 开头")
        return False

    try:
        network_id = int(network_id)
    except ValueError:
        print("❌ 错误：网络ID必须是数字")
        return False

    # 删除旧配置
    old_count = BlockchainConfig.objects.count()
    if old_count > 0:
        print(f"\n⚠️  将删除 {old_count} 个旧配置...")
        BlockchainConfig.objects.all().delete()

    # 创建新配置
    config = BlockchainConfig.objects.create(
        name=name,
        provider_url=provider_url,
        account_address=account_address,
        private_key=private_key,
        network_id=network_id,
        is_active=True
    )

    print("\n✅ 区块链配置添加成功！")
    print(f"  配置名称: {config.name}")
    print(f"  Provider URL: {config.provider_url}")
    print(f"  账户地址: {config.account_address}")
    print(f"  网络ID: {config.network_id}")
    print(f"  是否活跃: {config.is_active}")
    print("\n现在可以在前端部署智能合约了！\n")
    return True

if __name__ == '__main__':
    try:
        add_ganache_config()
    except Exception as e:
        print(f"❌ 错误: {e}")
        sys.exit(1)


if __name__ == '__main__':
    print("=" * 60)
    print("Ganache 区块链配置添加脚本")
    print("=" * 60)
    print("\n⚠️  请先修改脚本中的以下信息：")
    print("  1. account_address - 替换为 Ganache 的账户地址")
    print("  2. private_key - 替换为 Ganache 的私钥")
    print("\n从 Ganache 终端获取这些信息：")
    print("  Available Accounts 中的第一个地址")
    print("  Private Keys 中的第一个私钥")
    print("\n" + "=" * 60)
    
    response = input("\n是否继续？(y/n): ")
    if response.lower() == 'y':
        add_ganache_config()
    else:
        print("已取消")

