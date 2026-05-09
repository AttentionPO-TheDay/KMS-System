# 连接 Ganache 完整步骤

## 快速开始（3 种方式）

### 方式 1：前端 UI 配置（推荐）

1. **启动 Ganache**
   ```bash
   npx ganache
   ```

2. **记录 Ganache 信息**
   - 从输出中复制第一个账户地址（`0x...`）
   - 从输出中复制第一个账户的私钥（`0x...`）

3. **打开前端**
   - 访问 `http://localhost:8000`
   - 导航到 **区块链管理** 菜单

4. **添加配置**
   - 点击 **添加配置** 按钮
   - 填写表单：
     - 配置名称：`Ganache Local`
     - Provider URL：`http://127.0.0.1:7545`
     - 账户地址：粘贴 Ganache 账户地址
     - 私钥：粘贴 Ganache 私钥
     - 网络ID：`5777`
     - 是否激活：打开
   - 点击 **保存**

5. **验证连接**
   - 点击 **刷新状态** 按钮
   - 确认显示 **已连接**

### 方式 2：Python 脚本配置

```bash
cd backend
python add_ganache_config.py
```

按提示输入 Ganache 信息即可。

### 方式 3：Django Shell 配置

```bash
cd backend
python manage.py shell
```

```python
from pqkds.models import BlockchainConfig

BlockchainConfig.objects.all().delete()
BlockchainConfig.objects.create(
    name='Ganache Local',
    provider_url='http://127.0.0.1:7545',
    account_address='0x...',  # 替换为你的账户地址
    private_key='0x...',      # 替换为你的私钥
    network_id=5777,
    is_active=True
)
```

## 部署智能合约

配置完成后：

1. 在前端点击 **部署合约** 按钮
2. 确认部署
3. 等待完成，会显示合约地址

## 注册节点

部署合约后：

1. 导航到 **节点管理** 菜单
2. **注册新节点** 按钮现在已启用
3. 填写节点信息并注册

## 常见问题

| 问题 | 解决方案 |
|------|--------|
| 连接失败 | 确保 Ganache 运行中，URL 为 `http://127.0.0.1:7545` |
| 私钥格式错误 | 必须以 `0x` 开头，完整复制 |
| 账户地址格式错误 | 必须以 `0x` 开头，长度 42 字符 |
| 部署失败 | 确保账户有足够 ETH（Ganache 默认 100 ETH） |

## 文件位置

- 前端配置页面：`web/src/views/pqkds/blockchain/index.vue`
- 后端 API：`backend/pqkds/views.py` (BlockchainConfigViewSet)
- 快速配置脚本：`backend/add_ganache_config.py`

