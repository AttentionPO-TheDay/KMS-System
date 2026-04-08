# KMS 消息协议文档

## 1. 目的

本文档用于固化当前仓库内生成、更新、回收三条消息链路的实际口径，重点说明：

1. HTTP 接入入口在哪一层
2. Kafka topic 如何划分
3. Java 侧由谁消费
4. 当前 payload 字段长什么样

本文档以当前代码实现为准，不再沿用旧版“Java 接收入站、Go 消费出站”的历史描述。

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
4. `kms-updatedel/java-backend` 消费 `key_update_log`、`key_revoke_log`
5. 上链任务统一进入 `key_chain_task`

## 3. Kafka Topic 划分

| Topic | 归属系统 | 用途 | 当前消费者 |
|------|------|------|------|
| `key_generate_log` | `kms-generate` | 生成消息入口 | `GenerateKafkaConsumer` |
| `key_update_log` | `kms-updatedel` | 更新消息入口 | `UpdateKafkaConsumer` |
| `key_revoke_log` | `kms-updatedel` | 回收消息入口 | `RevokeKafkaConsumer` |
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

消费规则：

1. 监听 `key_generate_log`
2. 仅处理 `ENROLL_KEY`
3. 使用 `raw_user`、`raw_password` 终校验用户身份
4. 从 `generated_key` 中提取密钥内容
5. 批量入库后发送 `key_chain_task`

### 4.3 当前 Payload

```json
{
  "raw_user": "alice",
  "raw_password": "plain-password",
  "action_type": "ENROLL_KEY",
  "generated_key": {
    "keyId": 1001,
    "userName": "alice",
    "encrytType": "SM2",
    "encrytName": "SM2",
    "keyName": "demo-key",
    "keyUse": "sign",
    "keyValue": "...",
    "ua": "terminal-a",
    "keyDomain": "default"
  }
}
```

### 4.4 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `raw_user` | string | 是 | 原始用户名，用于 Java 侧终校验 |
| `raw_password` | string | 是 | 原始密码，用于 Java 侧终校验 |
| `action_type` | string | 是 | 当前固定为 `ENROLL_KEY` |
| `generated_key` | object | 是 | 已生成的密钥实体 |

## 5. 更新链路

### 5.1 请求入口

Go 接入层：`kms-updatedel/go-backend`

当前入口：

1. `POST /lifecycle/request/UPDATE_KEY`
2. `GET /lifecycle/ping`
3. `GET /lifecycle/metrics`

### 5.2 消费方

Java 消费方：`kms-updatedel/java-backend` 中的 `UpdateKafkaConsumer`

消费规则：

1. 监听 `key_update_log`
2. 使用 `raw_user`、`raw_password` 校验用户身份
3. 读取 `key_id`
4. 调用 `KeyRotateService.rotateKeyById(keyId)` 执行轮换

### 5.3 当前 Payload

```json
{
  "trace_id": "uuid",
  "action_type": "UPDATE_KEY",
  "raw_user": "alice",
  "raw_password": "plain-password",
  "key_id": 1001,
  "key_info": {
    "key_id": 1001,
    "user_name": "alice",
    "encryt_type": "SM2",
    "encryt_name": "SM2",
    "key_name": "demo-key",
    "key_use": "sign",
    "key_domain": "default"
  }
}
```

### 5.4 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `trace_id` | string | 否 | 当前生命周期链路使用的追踪 ID |
| `action_type` | string | 是 | 当前固定为 `UPDATE_KEY` |
| `raw_user` | string | 是 | 用户名 |
| `raw_password` | string | 是 | 用户密码 |
| `key_id` | number | 是 | 待更新密钥 ID |
| `key_info` | object | 否 | 请求携带的密钥快照，当前 Java 消费者主要使用 `key_id` |

## 6. 回收链路

### 6.1 请求入口

Go 接入层：`kms-updatedel/go-backend`

当前入口：

1. `POST /lifecycle/request/REVOKE_KEY`
2. `GET /lifecycle/ping`
3. `GET /lifecycle/metrics`

### 6.2 消费方

Java 消费方：`kms-updatedel/java-backend` 中的 `RevokeKafkaConsumer`

消费规则：

1. 监听 `key_revoke_log`
2. 使用 `raw_user`、`raw_password` 校验用户身份
3. 读取 `key_id`
4. 调用 `KeyRevokeService.revokeKeyById(keyId)` 执行回收

### 6.3 当前 Payload

```json
{
  "trace_id": "uuid",
  "action_type": "REVOKE_KEY",
  "raw_user": "alice",
  "raw_password": "plain-password",
  "key_id": 1001,
  "key_info": {
    "key_id": 1001,
    "user_name": "alice",
    "encryt_type": "SM2",
    "encryt_name": "SM2",
    "key_name": "demo-key",
    "key_use": "sign",
    "key_domain": "default"
  }
}
```

### 6.4 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `trace_id` | string | 否 | 当前生命周期链路使用的追踪 ID |
| `action_type` | string | 是 | 当前固定为 `REVOKE_KEY` |
| `raw_user` | string | 是 | 用户名 |
| `raw_password` | string | 是 | 用户密码 |
| `key_id` | number | 是 | 待回收密钥 ID |
| `key_info` | object | 否 | 请求携带的密钥快照，当前 Java 消费者主要使用 `key_id` |

## 7. Java 业务接口补充

除了消息接入层，当前 Java 业务接口也已经落地：

### `kms-generate/java-backend`

1. `GET /generate/key/list`
2. `GET /generate/key/{keyId}`
3. `GET /generate/key/chain/{keyId}`
4. `POST /generate/user/register`
5. `GET /generate/user/non-admin-list`
6. `GET /generate/user/profile`
7. `GET/POST/PUT/DELETE /generate/keymanage/*`
8. `GET/POST/PUT /permission/request/*`

### `kms-updatedel/java-backend`

1. `GET /lifecycle/keymanage/list`
2. `GET /lifecycle/keymanage/{keyId}`
3. `PUT /lifecycle/keymanage`
4. `PUT /lifecycle/keymanage/auto-update`
5. `DELETE /lifecycle/keymanage/{keyId}`
6. `GET/POST/PUT /permission/request/*`

## 8. 当前差异与注意事项

1. 生成链路的 payload 使用 `action_type`、`raw_user`、`generated_key` 这套字段名。
2. 生命周期链路当前统一使用下划线字段，如 `trace_id`、`key_id`、`key_info`。
3. `traceId` / `requestId` 并未在所有链路完全统一，当前文档以代码现状为准。
4. 生命周期消息里的 `key_info` 当前主要作为快照信息，Java 消费核心仍依赖 `key_id`。
5. 回收率统计当前由 `kms-updatedel/go-backend` 的 `/lifecycle/metrics` 提供受理层指标，不等于最终业务完成率。

## 9. 联调建议

1. 先确认 Go 接入层端口与 Java 服务端口一致。
2. 再确认 Kafka topic 是否按系统分流。
3. 联调时优先检查用户鉴权失败日志，因为三条消息链路都会在 Java 消费侧二次校验账号密码。
4. 若要统一消息字段命名，应先评估 generate 与 lifecycle 两条链路的兼容改造成本，再做协议升级。
