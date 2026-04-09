# KMS 消息协议文档

## 1. 目的

本文档用于固化当前仓库内生成、更新、回收三条消息链路的实际口径，重点说明：

1. HTTP 接入入口在哪一层
2. Kafka topic 如何划分
3. Java 侧由谁消费
4. Java 业务接口目前暴露到什么程度

本文档以当前代码实现为准。

## 2. 当前链路总览

当前链路统一模式如下：

```text
Client
  -> Go 接入层
  -> Kafka topic
  -> Java 业务消费者
  -> MySQL / 审计 / 上链任务
  -> FISCO BCOS
```

其中：

1. `kms-generate/go-backend` 负责生成请求接入
2. `kms-updatedel/go-backend` 负责更新、回收请求接入
3. `kms-generate/java-backend` 消费 `key_generate_log`
4. `kms-updatedel/java-backend` 的 `LifecycleKafkaConsumer` 统一消费 `key_update_log`、`key_revoke_log`
5. 生成与生命周期系统都会向 `key_chain_task` 投递后续上链任务
6. `kms-distribute/java-backend` 会额外消费生成、更新、回收三类 topic，用于落分发记录

## 3. Kafka Topic 划分

| Topic | 归属系统 | 用途 | 当前消费者 |
|------|------|------|------|
| `key_generate_log` | `kms-generate` | 生成消息入口 | `GenerateKafkaConsumer`、`DistributeKafkaConsumer` |
| `key_update_log` | `kms-updatedel` | 更新消息入口 | `LifecycleKafkaConsumer`、`DistributeKafkaConsumer` |
| `key_revoke_log` | `kms-updatedel` | 回收消息入口 | `LifecycleKafkaConsumer`、`DistributeKafkaConsumer` |
| `key_chain_task` | 共享 | 上链任务 | 各系统链同步消费者 |

## 4. 生成链路

### 4.1 请求入口

Go 接入层：`kms-generate/go-backend`

当前入口：

1. `POST /generate/request/Register`
2. `POST /generate/request/ENROLL_KEY`
3. `POST /generate/request/REENROLL_KEY`
4. `POST /generate/request/comparam`
5. `GET /generate/ping`

### 4.2 消费方

Java 消费方：`kms-generate/java-backend` 中的 `GenerateKafkaConsumer`

当前行为：

1. 监听 `key_generate_log`
2. 对生成消息做用户终校验
3. 完成生成记录入库和审计
4. 投递后续 `key_chain_task`

### 4.3 Java 业务接口补充

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

## 5. 更新链路

### 5.1 请求入口

Go 接入层：`kms-updatedel/go-backend`

当前入口：

1. `POST /lifecycle/request/UPDATE_KEY`
2. `GET /lifecycle/ping`
3. `GET /lifecycle/metrics`

### 5.2 消费方

Java 消费方：`kms-updatedel/java-backend` 中的 `LifecycleKafkaConsumer`

当前行为：

1. 监听 `key_update_log`
2. 使用消息中的用户信息做终校验
3. 读取 `key_id`
4. 执行轮换逻辑
5. 需要时继续投递上链任务

## 6. 回收链路

### 6.1 请求入口

Go 接入层：`kms-updatedel/go-backend`

当前入口：

1. `POST /lifecycle/request/REVOKE_KEY`
2. `GET /lifecycle/ping`
3. `GET /lifecycle/metrics`

### 6.2 消费方

Java 消费方：`kms-updatedel/java-backend` 中的 `LifecycleKafkaConsumer`

当前行为：

1. 监听 `key_revoke_log`
2. 使用消息中的用户信息做终校验
3. 读取 `key_id`
4. 执行回收逻辑
5. 需要时继续投递上链任务

## 7. 生命周期 Java 业务接口补充

`kms-updatedel/java-backend` 当前已暴露：

1. `GET /lifecycle/keymanage/list`
2. `GET /lifecycle/keymanage/{keyId}`
3. `PUT /lifecycle/keymanage`
4. `PUT /lifecycle/keymanage/auto-update`
5. `DELETE /lifecycle/keymanage/{keyId}`
6. `GET /permission/request/list`
7. `GET /permission/request/{requestId}`
8. `POST /permission/request/submit`
9. `PUT /permission/request/approve/{requestId}`
10. `PUT /permission/request/reject/{requestId}`
11. `PUT /permission/request/rollback/{requestId}`
12. `DELETE /permission/request/{requestId}`

## 8. 分发系统的消息消费补充

`kms-distribute/java-backend` 当前也会消费以下 topic：

1. `key_generate_log`
2. `key_update_log`
3. `key_revoke_log`

用途：

1. 自动沉淀分发记录
2. 让分发查询可以看到来自生成、更新、回收链路的业务事件

## 9. 当前差异与注意事项

1. 生成链路与生命周期链路的 payload 字段命名并未完全统一。
2. 生命周期链路当前主要依赖 `key_id` 驱动更新与回收处理。
3. `kms-updatedel` 当前不是两个独立消费者类分别消费更新和回收，而是由 `LifecycleKafkaConsumer` 统一处理。
4. `kms-distribute` 不是单纯人工录入系统，还包含 Kafka 事件消费逻辑。
5. 回收率统计当前由 `kms-updatedel/go-backend` 的 `/lifecycle/metrics` 提供受理层指标，不等于最终业务完成率。

## 10. 联调建议

1. 先确认 Go 接入层端口与 Java 服务端口是否可达。
2. 再确认 Kafka topic 是否按当前系统口径创建并消费。
3. 联调时优先检查用户鉴权失败日志，因为三条消息链路都会在消费侧做二次校验。
4. 如果需要统一协议字段命名，应作为一次显式协议升级处理，而不是继续在文档里沿用旧名称。
