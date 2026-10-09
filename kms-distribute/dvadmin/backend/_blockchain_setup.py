import os, django, json
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
from pqkds.chain_backend import require_legacy_backend
# 此脚本随后会删除旧配置；必须在任何 Django 启动/数据库写入之前拒绝 Fabric。
require_legacy_backend('执行旧 Ganache 初始化/删除配置脚本')
django.setup()

ACCOUNT = '0x16480bed623d72e0336A9f3B995e6F69e8eE926f'
PRIVATE_KEY = '0xe716428e71ecae21125ea84e72506dc59299eea9cc6785881da1d1e18112ef9f'

from web3 import Web3

# 如果没有从 Ganache 输出解析到，直接连接获取
if not ACCOUNT or not PRIVATE_KEY:
    w3 = Web3(Web3.HTTPProvider('http://127.0.0.1:7545'))
    if w3.is_connected() and w3.eth.accounts:
        ACCOUNT = w3.eth.accounts[0]
        # 没有私钥时用本地签名模式
        PRIVATE_KEY = None
        print(f'从 Ganache 获取账户: {ACCOUNT}')
    else:
        print('ERROR: Cannot connect to Ganache')
        exit(1)

from pqkds.models import BlockchainConfig

# 删除旧配置，创建新的
BlockchainConfig.objects.all().delete()
config = BlockchainConfig.objects.create(
    name='Ganache Local',
    provider_url='http://127.0.0.1:7545',
    account_address=ACCOUNT,
    private_key=PRIVATE_KEY or '',
    network_id=5777,
    is_active=True
)
print(f'BlockchainConfig created: {config.name}')

# 部署智能合约
from pqkds.blockchain_service import BlockchainService
try:
    svc = BlockchainService()
    result = svc.compile_and_deploy_contract()
    if result.get('success'):
        print(f'Contract deployed at: {result["contract_address"]}')
    else:
        print(f'Contract deploy failed: {result.get("error", "unknown")}')
except Exception as e:
    print(f'Contract deploy error: {e}')
