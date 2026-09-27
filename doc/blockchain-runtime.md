# KMS 区块链运行逻辑说明

## 1. 文档目的

本文档用于说明当前仓库中“区块链”相关能力的实际运行方式，重点回答以下问题：

1. 区块链在系统里承担什么职责
2. 相关组件如何部署和连接
3. 密钥生成、更新、回收分别如何触发上链
4. 链上结果如何回写并展示到前端

本文档以当前代码实现为准。

---

## 2. 一句话概括

当前系统中的区块链并不是业务主库，而是 **密钥生命周期关键动作的可信存证层**。

整体模式如下：

```text
前端/外部请求
  -> Go/Java 业务服务
  -> MySQL 先落库
  -> Kafka 投递上链任务
  -> Java 链消费者调用 FISCO BCOS 合约
  -> 合约写入链上状态并触发事件
  -> Java 回写交易哈希 / 区块高度
  -> 前端查询数据库中的链上结果快照
```

也就是说，这是一套 **MySQL 主数据 + Kafka 解耦 + FISCO BCOS 存证增强** 的架构。

---

## 3. 区块链在系统中的职责

当前区块链主要承担 3 个职责：

1. **存证**：对密钥生成、轮换、回收等关键动作进行链上留痕
2. **可信状态佐证**：对公钥、版本、状态变化提供不可随意篡改的佐证
3. **审计**：通过链上事件为后续审计和追踪提供依据

因此：

- **MySQL 是主数据源**
- **FISCO BCOS 是可信审计账本**
- 前端“区块链查看”页面展示的主要是数据库回填后的链上结果，而不是直接实时读取链节点

---

## 4. 基础设施与部署方式

区块链相关基础设施集中在 `kms-ops/docker-compose.yml` 中。

### 4.1 FISCO BCOS 相关服务

1. `fisco-node`
   - FISCO BCOS 节点
   - 暴露端口：`20200`、`8545`
2. `fisco-console`
   - 链控制台容器
   - 挂载合约目录和控制台配置

### 4.2 业务服务的链配置

`generate-java` 与 `updatedel-java` 都通过环境变量注入以下区块链配置：

- `FISCO_HOST`
- `FISCO_PRIVATE_KEY`
- `KMS_CHAIN_TOPIC`
- `KMS_CHAIN_RESULT_TOPIC`

说明业务服务不是硬编码访问区块链，而是通过统一配置接入链节点。

---

## 5. 智能合约：KeyEvidence

当前密钥存证合约为：

- `kms-ops/fisco/contracts/KeyEvidence.sol`

### 5.1 链上记录结构

合约通过 `records[keyId]` 维护密钥链上状态，每条记录包含：

- `keyId`
- `username`
- `publicKey`
- `algorithm`
- `usage`
- `isAutoUpdate`
- `status`
- `createTime`
- `updateTime`
- `version`

其中：

- `status = 0` 表示 Active
- `status = 1` 表示 Frozen
- `status = 2` 表示 Rotated
- `status = 3` 表示 Revoked

### 5.2 合约支持的动作

#### 1）首次上链：`uploadKey(...)`

作用：

- 首次写入密钥存证记录
- 保存公钥、算法、用途、自动更新标记、版本号等信息
- 默认状态为 Active
- 触发 `UploadSuccess` 事件

#### 2）密钥轮换：`rotateKey(...)`

作用：

- 先触发旧版本状态变化事件，标记旧版本为 Rotated
- 再把链上记录更新为新公钥和新版本
- 触发 `KeyRotated` 事件

#### 3）状态变更：`changeKeyStatus(...)`

作用：

- 修改链上状态（例如回收）
- 触发 `StatusChanged` 事件

---

## 6. Kafka 在区块链链路中的作用

当前链路采用 **异步上链**，避免主业务流程被链调用阻塞。

### 6.1 上链任务 Topic

- `key_chain_task`

作用：

- 生成系统将 ENROLL 类型任务发到这里
- 生命周期系统将 ROTATE / REVOKE 类型任务发到这里
- 不同 Java 消费者根据 `actionType` 分流处理

### 6.2 上链结果 Topic

- `key_chain_result`

作用：

- 链调用完成后，把 `chain_status`、`chain_hash`、`block_height`、`error_message` 等结果发回
- 下游系统可根据结果回填展示或更新分发记录

---

## 7. 生成流程如何上链

生成链路主要涉及两个阶段：

1. 先入库
2. 再异步上链

### 7.1 生成记录入库与投递上链任务

`kms-generate/java-backend` 中的 `GenerateKafkaConsumer` 在消费生成消息后会：

1. 解析生成消息
2. 组装 `Keymanage`
3. 设置默认字段：
   - `version = 1`
   - `status = 0`
   - `chainStatus = 0`（待上链）
4. 批量写入数据库
5. 向 `key_chain_task` 发送 `ENROLL` 上链任务

### 7.2 生成链消费者处理 ENROLL 任务

`ChainTaskConsumer` 监听 `key_chain_task`，但只处理 `ENROLL` 类型消息。

它的职责是：

1. 解析消息中的 `actionType`
2. 忽略非 `ENROLL` 的任务
3. 对每个密钥调用 `GenerateChainService.processChainSync(...)`

### 7.3 生成系统如何调用链

`GenerateChainServiceImpl` 是生成域真正执行上链的服务，主要逻辑如下：

1. 根据密钥材料计算最终公钥 `PA`
   - 支持 SM2
   - 支持 SSCL
2. 懒初始化 FISCO SDK 与合约包装器
3. 调用合约 `uploadKey(...)`
4. 检查交易回执是否成功
5. 检查是否收到 `UploadSuccess` 事件
6. 成功后回写：
   - `chainStatus = 1`
   - `chainHash = 交易哈希`
   - `blockHeight = 区块高度`
7. 向 `key_chain_result` 发布结果消息

如果失败，则将 `chainStatus` 标记为 `2` 并发布失败结果。

---

## 8. 更新流程如何上链

更新流程在 `kms-updatedel` 中完成。

### 8.1 生命周期服务先改库，再发上链任务

`LifecycleService.rotateKey(...)` 的主要步骤如下：

1. 读取当前密钥记录
2. 校验是否允许更新
3. 生成下一版本密钥数据
4. 将版本号递增
5. 设置业务状态为 Active
6. 将 `chainStatus` 置为 `0`（待上链）
7. 更新数据库
8. 写入操作记录
9. 投递 `ROTATE` 类型的 `key_chain_task` 消息

### 8.2 生命周期链消费者处理 ROTATE

`UpdatedelChainConsumer` 监听 `key_chain_task`，并在接收到 `ROTATE` 时：

1. 读取要更新的密钥
2. 调用 `UpdatedelChainService.processRotateChainSync(...)`

### 8.3 生命周期系统如何调用链执行轮换

`UpdatedelChainService.processRotateChainSync(...)` 的逻辑为：

1. 重新计算最终公钥 `PA`
2. 确保 FISCO SDK 和合约已准备好
3. 调用合约 `rotateKey(...)`
4. 检查交易回执
5. 检查是否收到 `KeyRotated` 事件
6. 校验事件状态是否为 Active
7. 成功后回写数据库：
   - `chainStatus = 1`
   - `chainHash`
   - `blockHeight`
8. 更新操作记录结果
9. 向 `key_chain_result` 发布结果消息

失败时则写入失败状态并记录错误原因。

---

## 9. 回收流程如何上链

### 9.1 生命周期服务先更新业务状态，再发回收上链任务

`LifecycleService.revokeKey(...)` 的主要步骤如下：

1. 查询当前密钥
2. 若已回收则直接返回
3. 更新数据库中的业务状态为回收
4. 重置链状态为待处理
5. 写入操作记录
6. 投递 `REVOKE` 类型的 `key_chain_task` 消息

### 9.2 生命周期链消费者处理 REVOKE

`UpdatedelChainConsumer` 收到 `REVOKE` 类型消息后，会调用：

- `UpdatedelChainService.processRevokeChainSync(...)`

### 9.3 生命周期系统如何调用链执行回收

`processRevokeChainSync(...)` 的逻辑为：

1. 确保 FISCO SDK 和合约已准备好
2. 调用合约 `changeKeyStatus(keyId, 3)`
3. 检查交易回执
4. 检查是否收到 `StatusChanged` 事件
5. 校验事件中的状态是否为 `Revoked`
6. 成功后回写数据库：
   - `chainStatus = 1`
   - `chainHash`
   - `blockHeight`
7. 更新操作记录结果
8. 向 `key_chain_result` 发布结果消息

失败时同样回写失败状态并保留错误信息。

---

## 10. 链配置与连接方式

生成系统与生命周期系统都通过各自的 `application.yml` 配置 FISCO 连接信息。

主要配置项包括：

- `fisco.host`
- `fisco.contract-address`
- `fisco.private-key`

当前两个系统默认使用同一个合约地址，但该地址应由本地单节点模板恢复后的 `.env` / 本地状态文件决定，不应再把某个历史地址当作固定真值。

Java 服务内部通过合约包装器完成以下动作：

1. 读取 `config-fisco.toml`
2. 根据 `fisco.host` 解析真实地址
3. 初始化 `BcosSDK`
4. 使用私钥创建链账户
5. 加载 `KeyEvidence` 合约

这意味着：

- 业务服务直接使用 FISCO Java SDK 调链
- 合约地址与私钥由部署环境统一注入
- 本地 dev 环境现在推荐从 `kms-ops/fisco/template/` 恢复单节点链模板，再由 `kms-ops/fisco/live/contract.env` 与 `.env` 提供链元数据
- 若未配置私钥，则会退化为临时账户，但正式环境应提供固定私钥

---

## 11. 链上结果如何回流到其他系统

### 11.1 结果消息结构

生成系统和生命周期系统在链执行结束后，都会发送包含以下字段的消息到 `key_chain_result`：

- `key_id`
- `action_type`
- `chain_status`
- `chain_hash`
- `block_height`
- `error_message`

### 11.2 分发系统对链结果的消费

> **2026-09-26 注**：本节描述的 `kms-distribute/java-backend` 与其中的
> `DistributeKafkaConsumer` **已随代码清理删除**（Q11 已确认该服务整体下线，
> 网关 `/distribute-api/` 也已改为显式 404）。以下内容保留作历史记录；
> 当前分发侧的链上数据由 dvadmin（`kms-distribute/dvadmin/backend/`）承载。

`kms-distribute/java-backend` 中的 `DistributeKafkaConsumer` 会监听 `key_chain_result`，并根据：

- `key_id`
- `action_type`
- `chain_hash`
- `block_height`

去更新分发记录，使分发系统中的记录也能看到对应链上凭证。

因此，区块链结果不只服务于生成和生命周期系统，也会同步到分发记录展示链路中。

---

## 12. 前端“区块链查看”页面实际展示的是什么

当前前端中的“区块链查看”页面，并不是直接连接 FISCO 节点查询链上原始状态，而是调用业务后端接口查询链状态快照。

### 12.1 查询入口

生成系统前端会调用：

- `GET /generate/key/chain/{keyId}`

对应后端控制器：

- `ChainController`

它返回的是 `GenerateChainService.getChainStatus(keyId)` 的结果。

### 12.2 返回内容

当前页面主要展示：

- `chainStatus`
- `chainHash`
- `blockHeight`
- `version`

这些数据本质上来自数据库中的链同步结果，而不是浏览器直接读链。

因此当前“区块链查看”页面更准确的定义是：

**链上同步结果与凭证展示页面**。

---

## 13. 当前系统中的三条核心区块链链路

### 13.1 生成上链

```text
生成请求
  -> 生成系统消费生成消息
  -> MySQL 插入密钥记录（chainStatus=0）
  -> Kafka: key_chain_task(ENROLL)
  -> kms-generate ChainTaskConsumer
  -> GenerateChainServiceImpl.uploadKey
  -> FISCO BCOS 合约 uploadKey(...)
  -> 回写 chainHash / blockHeight / chainStatus=1
  -> Kafka: key_chain_result
```

### 13.2 更新上链

```text
更新请求
  -> LifecycleService.rotateKey
  -> MySQL 更新版本与密钥内容（chainStatus=0）
  -> Kafka: key_chain_task(ROTATE)
  -> kms-updatedel UpdatedelChainConsumer
  -> UpdatedelChainService.rotateKey
  -> FISCO BCOS 合约 rotateKey(...)
  -> 回写 chainHash / blockHeight / chainStatus=1
  -> Kafka: key_chain_result
```

### 13.3 回收上链

```text
回收请求
  -> LifecycleService.revokeKey
  -> MySQL 标记回收（chainStatus=0）
  -> Kafka: key_chain_task(REVOKE)
  -> kms-updatedel UpdatedelChainConsumer
  -> UpdatedelChainService.changeKeyStatus
  -> FISCO BCOS 合约 changeKeyStatus(...)
  -> 回写 chainHash / blockHeight / chainStatus=1
  -> Kafka: key_chain_result
```

---

## 14. 当前设计的关键特点

### 14.1 优点

1. **主链路不阻塞**
   - 业务先落库，再异步上链
2. **职责清晰**
   - MySQL 负责业务数据
   - Kafka 负责解耦
   - FISCO BCOS 负责可信存证
3. **便于审计**
   - 通过链上事件可追踪生成、轮换、回收过程
4. **便于扩展**
   - 其他系统可以继续消费 `key_chain_result` 做联动展示

### 14.2 当前现实口径

当前实现不是“链上优先”，而是“数据库主导 + 链上存证增强”。

换句话说：

- 业务以数据库状态为准
- 区块链为关键状态提供可信证明
- 前端优先读取数据库中的链同步结果

---

## 15. 结论

当前仓库中的区块链系统运行逻辑可以总结为：

1. **FISCO BCOS 是密钥生命周期的可信存证层**
2. **生成、更新、回收都会异步触发上链**
3. **上链动作统一通过 Kafka 的 `key_chain_task` 解耦**
4. **上链结果通过 `key_chain_result` 回流到业务系统**
5. **前端看到的是数据库中保存的链上结果快照，而不是直接读链**

因此，这套系统中的“区块链”主要不是为了替代数据库，而是为了给密钥的关键状态变化提供可信、可审计、可追踪的链上依据。
---

## 16. 故障排查：上链失败 `0x1a (RevertInstruction)`

### 16.1 典型症状

Java 服务日志中出现：

```
WARN  GenerateChainServiceImpl - FISCO private key not configured, using ephemeral account
ERROR GenerateChainServiceImpl - KeyId: X 上链失败，状态码: 0x1a, 信息: null
ERROR ChainTaskConsumer - 密钥生成上链失败: keyId=X
```

### 16.2 根因

`0x1a` 是 FISCO BCOS 的 `RevertInstruction` 状态码，表示合约内部某个 `require()` 检查失败。在 KMS 场景中，最常见的原因是 **合约的 `onlyOwner` 校验不通过**：

```solidity
modifier onlyOwner() {
    require(msg.sender == owner, "only owner");
    _;
}
```

`KeyEvidence` 合约的 `uploadKey`、`rotateKey`、`changeKeyStatus` 都带有 `onlyOwner` 修饰器。`owner` 是部署合约时的账户地址。如果 Java 服务使用的账户不是部署合约的那个账户，所有写操作都会被 revert。

当 `FISCO_PRIVATE_KEY` 环境变量为空时，Java 服务会回退到随机生成的临时账户（ephemeral account），这个临时地址与合约 `owner` 不一致，因此上链必然失败。

### 16.3 为什么 `FISCO_PRIVATE_KEY` 会变空

在环境重建 (`rebuild-env.sh`) 或首次启动时，流程如下：

1. `rebuild-env.sh` 清理 `fisco/live/` 运行态目录
2. 调用 `start.sh`，从 `fisco/template/` 恢复链节点和 console 配置
3. `start.sh` 同时从模板状态文件 (`fisco/template/state/.env.template.local`) 恢复 `.env`
4. 如果模板状态文件中 `FISCO_PRIVATE_KEY` 为空，则 `.env` 中的私钥也为空
5. 而模板中 `FISCO_CONTRACT_ADDRESS` 可能保留了旧地址（实际在新恢复的空链上不存在）

这导致：

- `start.sh` 看到合约地址已存在，**跳过** `deploy-keyevidence.sh`
- 私钥没有被提取，Java 服务以空私钥启动
- 上链时使用临时账户，`onlyOwner` 校验失败

### 16.4 修复方案（已实施）

#### 修复 1：`start.sh` 增加私钥空值检测

`start.sh` 中的自动部署判断从"只检查合约地址"改为"同时检查合约地址和私钥"：

```bash
# 旧逻辑（只看地址）：
if ! grep -q '^FISCO_CONTRACT_ADDRESS=0x' .env; then
    bash ./deploy-keyevidence.sh
fi

# 新逻辑（地址和私钥都检查）：
needs_deploy=false
if ! grep -q '^FISCO_CONTRACT_ADDRESS=0x' .env; then
    needs_deploy=true
else
    fisco_pk=$(grep '^FISCO_PRIVATE_KEY=' .env | tail -n 1 | cut -d '=' -f 2-)
    if [ -z "$fisco_pk" ]; then
        needs_deploy=true
    fi
fi
if [ "$needs_deploy" = true ]; then
    bash ./deploy-keyevidence.sh
fi
```

这样即使模板中带了旧合约地址但私钥为空，也会自动触发重新部署。

#### 修复 2：`deploy-keyevidence.sh` 自动回写模板

部署完成后，将合约地址和私钥同步写回 `fisco/template/state/.env.template.local`，保证后续从模板恢复时私钥已经内置在模板中。

#### 修复 3：`fisco/template/console/conf/config.toml` 格式修正

Console 的 SDK 配置从不兼容的格式修正为 FISCO BCOS Java SDK 2.9.x 能正确解析的格式：

| 配置项 | 旧值（不兼容） | 新值（正确） |
|--------|----------------|--------------|
| `certPath` | `"."` | `"conf"` |
| `peers` | `["fisco-node:20200"]` | `["127.0.0.1:20200"]` |
| `useSsl` | `"true"` | 删除（该字段不被 SDK 识别） |
| `keyStoreDir` | `"../account"` | `"account"` |
| `type` | `"pem"` | 改为 `accountFileFormat = "pem"` |

Console 容器与 FISCO 节点共享网络（`network_mode: "service:fisco-node"`），所以 peers 应使用 `127.0.0.1` 而非 `fisco-node`。

### 16.5 手动修复步骤

如果遇到这个问题，不需要重建整个环境，只需运行：

```bash
cd kms-ops
bash ./deploy-keyevidence.sh
```

该脚本会自动：

1. 编译并部署合约（拿到新地址）
2. 从 console 账户中提取部署者私钥
3. 写入 `.env`、`fisco/live/contract.env`、模板状态文件
4. 重启 Java 服务（`generate-java`、`updatedel-java`、`kms-distribute`）

### 16.6 验证上链是否修复

重启后生成一条新密钥，观察 `kms_generate_java` 日志：

```bash
docker logs kms_generate_java --tail 30 2>&1 | grep -E "上链|uploadKey|chain"
```

正常应看到：

```
INFO  - uploadKey calling contract: keyId=X, ...
INFO  - KeyId: X 上链成功，txHash: 0x..., blockHeight: Y
```

如果仍然看到 `FISCO private key not configured`，检查 `.env` 中 `FISCO_PRIVATE_KEY` 是否有值，并确认 Java 容器已被 `--force-recreate` 重建。
