# Ganache 连接指南

## 1. 启动 Ganache

```bash
npx ganache
```

Ganache 启动后会显示类似以下信息：

```
ganache v7.x.x (@ganache/cli: 0.x.x, @ganache/core: 0.x.x)
Starting RPC server

Available Accounts
==================
(0) 0x1234567890123456789012345678901234567890 (100 ETH)
(1) 0x0987654321098765432109876543210987654321 (100 ETH)
...

Private Keys
==================
(0) 0xabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcd
(1) 0xfedcbafedcbafedcbafedcbafedcbafedcbafedcbafedcbafedcbafedcbafedcba
...

RPC Listening on 127.0.0.1:7545
```

## 2. 获取配置信息

从 Ganache 输出中复制以下信息：

- **Provider URL**: `http://127.0.0.1:7545`
- **Account Address**: 第一个账户地址（例如：`0x1234567890123456789012345678901234567890`）
- **Private Key**: 第一个账户的私钥（例如：`0xabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcd`）
- **Network ID**: `5777`（Ganache 默认）

## 3. 在前端添加配置

1. 打开浏览器，进入 `http://localhost:8000`
2. 导航到 **区块链管理** 菜单
3. 点击 **添加配置** 按钮
4. 填写表单：
   - **配置名称**: `Ganache Local`
   - **Provider URL**: `http://127.0.0.1:7545`
   - **账户地址**: 粘贴第一个账户地址
   - **私钥**: 粘贴第一个账户的私钥
   - **网络ID**: `5777`
   - **是否激活**: 打开开关
5. 点击 **保存**

## 4. 验证连接

1. 点击 **刷新状态** 按钮
2. 如果连接成功，会显示：
   - 连接状态：**已连接**
   - 最新区块：显示区块号
   - 网络ID：`5777`

## 5. 部署智能合约

1. 点击 **部署合约** 按钮
2. 确认部署
3. 等待部署完成，会显示合约地址和交易哈希

## 6. 注册节点

1. 导航到 **节点管理** 菜单
2. 点击 **注册新节点** 按钮（现在应该已启用）
3. 填写节点信息并注册

## 常见问题

### 连接失败

- 确保 Ganache 正在运行
- 确保 Provider URL 正确：`http://127.0.0.1:7545`
- 检查防火墙设置

### 私钥格式错误

- 私钥必须以 `0x` 开头
- 确保复制完整的私钥

### 账户地址格式错误

- 账户地址必须以 `0x` 开头
- 地址长度应为 42 个字符（包括 `0x`）

