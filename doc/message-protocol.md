# KMS 消息协议文档

## 1. 目的

本文档用于固化当前仓库内生成、更新、回收三条消息链路的实际口径，重点说明：

1. HTTP 接入入口在哪一层
2. Kafka topic 如何划分
3. Java 侧由谁消费
4. Java 业务接口目前暴露到什么程度

本文档以当前代码实现为准。

## 2. 当前链路总览

当前仓库内主要存在两类链路：

```text
A. 生成链路 / 专用接入流量
Client
  -> Go 接入层
  -> Kafka topic
  -> Java 业务消费者
  -> MySQL / 审计 / 上链任务
  -> FISCO BCOS

B. 当前前端主流程中的生命周期管理
Client
  -> Java 业务接口 (/lifecycle/keymanage/*)
  -> MySQL / 操作记录 / 上链任务
  -> FISCO BCOS
```

其中：

1. `kms-generate/go-backend` 负责生成请求接入
2. `kms-updatedel/go-backend` 保留更新、回收接入与健康/指标接口
3. `kms-generate/java-backend` 消费 `key_generate_log`
4. `kms-updatedel/java-backend` 的 `LifecycleKafkaConsumer` 仍可消费 `key_update_log`、`key_revoke_log`
5. 当前 `kms-user/front` 与 `kms-updatedel/front` 的更新、回收、自动更新和安全分析主要直接调用 `kms-updatedel/java-backend` 的 `/lifecycle/keymanage/*` 接口
6. 生成与生命周期系统都会向 `key_chain_task` 投递后续上链任务
7. `kms-distribute/java-backend` 会额外消费生成、更新、回收三类 topic，用于落分发记录

## 3. 入站鉴权（重要，早前文档遗漏）

`kms-generate/go-backend` 与 `kms-updatedel/go-backend` 的入站接口
**不是匿名可调用的**，必须同时满足两个条件：

1. **`X-Internal-Token`**：值等于环境变量 `INTERNAL_TOKEN`，由 `middleware.InternalAuth()` 校验；
   缺失返回 401，不匹配返回 403。该变量**无默认值**，未配置时 Go 服务启动即失败。
2. **`X-Kms-User`**：已认证用户名。由 Java 业务层在转发前写入
   （取值优先为业务层校验过的密钥所有者，否则回退到当前会话用户）。

**为什么需要 `X-Kms-User`**：Go 侧不再信任请求体中的 `user` 字段。
历史上该字段直接决定密钥归属，配合公开的默认内部 Token 与「空密码即放行」逻辑，
可被用来为任意用户生成密钥、或回收任意用户的密钥。
现在身份只来自 Java 已鉴权的会话，且 `/generate-ingress/`、`/updatedel-ingress/`
两条网关路由已下架，Go 入站层仅限 Docker 内网调用。

**对直接调用 Go 的调用方（压测、安全测试）的影响**：
必须同时携带 `X-Internal-Token` 与 `X-Kms-User`，否则会被 401 拒绝。
`kms-acceptance/backend` 与 `security/security_test.sh` 已同步适配。

## 4. Kafka Topic 划分

| Topic | 归属系统 | 用途 | 当前消费者 |
|------|------|------|------|
| `key_generate_log` | `kms-generate` | 生成消息入口 | `GenerateKafkaConsumer`、`DistributeKafkaConsumer` |
| `key_update_log` | `kms-updatedel` | 更新消息入口 | `LifecycleKafkaConsumer`、`DistributeKafkaConsumer` |
| `key_revoke_log` | `kms-updatedel` | 回收消息入口 | `LifecycleKafkaConsumer`、`DistributeKafkaConsumer` |
| `key_chain_task` | 共享 | 上链任务 | 各系统链同步消费者 |
| `key_chain_result` | 共享 | 上链结果回填 | `DistributeKafkaConsumer` |

说明：早前版本的本表只列了 4 个 topic，遗漏了 `key_chain_result`。
该 topic 由链同步成功后产生（`GenerateChainServiceImpl` / `UpdatedelChainService`），
供分发系统回填链哈希与区块高度。

## 5. 生成链路

### 5.1 请求入口

Go 接入层：`kms-generate/go-backend`

当前入口：

1. `POST /generate/request/Register`（匿名：注册入口）
2. `POST /generate/request/ENROLL_KEY`
3. `POST /generate/request/REENROLL_KEY`
4. `POST /generate/request/PARTIAL_KEY`
5. `POST /generate/request/comparam`
6. `GET /generate/ping`

除 `Register` 与 `ping` 外，均在 `InternalAuth` 分组内，需携带 `X-Internal-Token`；
`ENROLL_KEY` / `REENROLL_KEY` / `PARTIAL_KEY` 还需携带 `X-Kms-User`（见第 3 节）。

### 5.2 消费方

Java 消费方：`kms-generate/java-backend` 中的 `GenerateKafkaConsumer`

当前行为：

1. 监听 `key_generate_log`
2. 对生成消息做用户终校验
3. 完成生成记录入库和审计
4. 投递后续 `key_chain_task`

### 5.3 Java 业务接口补充

`kms-generate/java-backend` 当前已暴露：

1. `GET /generate/key/list`
2. `GET /generate/key/public-list`
3. `GET /generate/key/{keyId}`
4. `GET /generate/key/chain/{keyId}`
5. `POST /generate/key/chain/batch`
6. `GET /generate/keymanage/list`
7. `GET /generate/keymanage/{keyId}`
8. `POST /generate/keymanage/comparam`
9. `POST /generate/keymanage`
10. `PUT /generate/keymanage`
11. `DELETE /generate/keymanage/{keyId}`
12. `POST /generate/user/register`
13. `GET /generate/user/non-admin-list`
14. `GET /generate/user/profile`
15. `GET/POST/PUT/DELETE /permission/request/*`

## 6. 更新链路

### 6.1 请求入口

Go 接入层：`kms-updatedel/go-backend`

当前入口：

1. `POST /lifecycle/request/UPDATE_KEY`
2. `POST /lifecycle/request/BATCH_UPDATE_KEYS`（树型批量更新，早前文档遗漏）
3. `GET /lifecycle/ping`
4. `GET /lifecycle/metrics`

三个 `request` 接口均在 `InternalAuth` 分组内，需同时携带
`X-Internal-Token` 与 `X-Kms-User`（见第 3 节）。

### 6.2 消费方

Java 消费方：`kms-updatedel/java-backend` 中的 `LifecycleKafkaConsumer`

当前行为：

1. 监听 `key_update_log`
2. 校验消息声明的用户存在，并校验其确为该密钥所有者
3. 读取 `key_id`
4. 执行轮换逻辑
5. 需要时继续投递上链任务

## 7. 回收链路

### 7.1 请求入口

Go 接入层：`kms-updatedel/go-backend`

当前入口：

1. `POST /lifecycle/request/REVOKE_KEY`
2. `GET /lifecycle/ping`
3. `GET /lifecycle/metrics`

### 7.2 消费方

Java 消费方：`kms-updatedel/java-backend` 中的 `LifecycleKafkaConsumer`

当前行为：

1. 监听 `key_revoke_log`
2. 校验消息声明的用户存在，并校验其确为该密钥所有者
3. 读取 `key_id`
4. 执行回收逻辑
5. 需要时继续投递上链任务

## 8. 生命周期 Java 业务接口补充

`kms-updatedel/java-backend` 当前已暴露：

1. `GET /lifecycle/keymanage/list`
2. `GET /lifecycle/keymanage/{keyId}`
3. `GET /lifecycle/keymanage/analysis/{keyId}`
4. `PUT /lifecycle/keymanage`（见下方语义说明）
5. `PUT /lifecycle/keymanage/auto-update`
6. `DELETE /lifecycle/keymanage/{keyId}`
7. `GET /permission/request/list`
8. `GET /permission/request/{requestId}`
9. `POST /permission/request/submit`
10. `PUT /permission/request/approve/{requestId}`
11. `PUT /permission/request/reject/{requestId}`
12. `PUT /permission/request/rollback/{requestId}`
13. `DELETE /permission/request/{requestId}`

当前 `kms-user/front` 与 `kms-updatedel/front` 的生命周期相关页面主要通过这些 Java 接口直接完成更新、回收、自动更新和安全分析。

### 8.1 `PUT /lifecycle/keymanage` 的两种语义（重要）

该接口按**请求体是否携带新的用户部分公钥 `ua`** 分流：

| 请求体 | 语义 | 行为 |
|---|---|---|
| **不带** `ua` | 元数据更新 | 仅更新 `key_name` / `key_use` / `key_domain` / `auto_update`；**不重新生成密钥材料，`version` 保持不变** |
| **带** `ua` | 真正的密钥轮换 | 用新 `ua` 重新计算部分密钥；同一行 `UPDATE`，`version + 1`，旧版本在链上记为 `Rotated` |

**为什么必须这样分流**：早前实现只要 `keyName` 等字段非空就走轮换，导致：
1. 元数据实际没有被更新（请求里的新名称被丢弃）；
2. 用户前台的「更新」按钮不携带 `ua`，服务端却用自己生成的随机量重新计算部分密钥——
   而客户端本地并不持有与之配套的私钥分量，**更新后密钥无法用于解密/签名**；
3. `version` 每次自增，但用户拿不到对应的新私钥材料。

**使用建议**：
- 只改名称、用途、域、自动更新 → 不要传 `ua`，走元数据更新。
- 需要更换密钥材料 → 客户端必须**先在本地生成新的私钥分量** `d_client'`，
  计算 `uA' = d_client'·G` 后作为 `ua` 提交；
  服务端返回新的 `partialKey`（`t_A'`），客户端据此合成
  `finalPrivateKey = (t_A' + d_client') mod n`。
  `kms-updatedel/front/src/views/algorithm/processView.vue` 是这一流程的参考实现。

> 附带修复：只要请求涉及 `autoUpdate` 字段，就必须具备自动更新权限。
> 否则可以通过「同时修改一个元数据字段」绕过原有的权限检查。

## 9. 分发系统的消息消费补充

`kms-distribute/java-backend` 当前也会消费以下 topic：

1. `key_generate_log`
2. `key_update_log`
3. `key_revoke_log`

用途：

1. 自动沉淀分发记录
2. 让分发查询可以看到来自生成、更新、回收链路的业务事件

## 10. 当前差异与注意事项

1. 生成链路与生命周期链路的 payload 字段命名并未完全统一。
2. 生命周期链路当前主要依赖 `key_id` 驱动更新与回收处理。
3. `kms-updatedel` 当前不是两个独立消费者类分别消费更新和回收，而是由 `LifecycleKafkaConsumer` 统一处理。
4. `kms-distribute` 不是单纯人工录入系统，还包含 Kafka 事件消费逻辑。
5. 回收率验收当前以生命周期 Java 最终 `status=3` 核验为准，`/lifecycle/metrics` 更适合作为接入层受理指标，而不是最终业务完成率。
6. **`key_chain_result` 链路是单向的**：链同步成功后由 Java 投递，仅分发系统消费用于回填；
   不存在「结果回写到 keymanage」的链路。
7. **`key_update_log` / `key_revoke_log` 的消费者位点语义**
   已由 `auto-offset-reset: latest` 改为 `earliest`，并关闭自动提交、改为整批处理完成后提交。
   原因是回收消息丢失会导致密钥未真正失效，而原配置在消费者离线期间会静默跳过消息。
8. **同步路径与 Kafka 路径并存**：前端主流程的更新/回收直接调用
   `kms-updatedel/java-backend` 的 `/lifecycle/keymanage/*`（同步、立即返回），
   不经过 Go 与 Kafka；Kafka 路径主要服务于压测与外部驱动。
   两条路径最终都落到同一个 `LifecycleService`，语义一致。
9. **消费侧不再做密码校验**：身份边界已上移到 Go 入站层。
   历史上「`raw_password` 为空即视为可信」是一个鉴权绕过点（攻击者可省略密码字段），
   现已移除；消费侧只做用户存在性与密钥归属校验。

## 11. 联调建议

1. 先确认 Go 接入层端口与 Java 服务端口是否可达。
2. 再确认 Kafka topic 是否按当前系统口径创建并消费（共 5 个 topic，含 `key_chain_result`）。
3. 联调时优先检查 `X-Internal-Token` / `X-Kms-User` 是否缺失或不一致；
   直接调用 Go 入站层时缺少任一头部都会得到 401，这是最常见的联调故障。
4. 如果需要统一协议字段命名，应作为一次显式协议升级处理，而不是继续在文档里沿用旧名称。
