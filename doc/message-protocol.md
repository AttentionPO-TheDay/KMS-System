# KMS 消息协议文档

## 概述

本文档定义 KMS (Key Management Service) 系统中三类核心操作的统一消息协议，用于生成、更新、回收密钥的消息流转。

---

## 1. 生成 Payload (key_generate_log)

**Kafka Topic**: `key_generate_log`

**ActionType**: `ENROLL_KEY`

```json
{
  "traceId": "uuid",
  "requestId": "uuid",
  "actionType": "ENROLL_KEY",
  "userId": "string",
  "keyAlgorithm": "SSCL|SM2",
  "keySize": 256,
  "timestamp": 1234567890
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| traceId | string (UUID) | 是 | 全链路追踪ID，用于串联整个请求链路 |
| requestId | string (UUID) | 是 | 每次请求的唯一标识 |
| actionType | string | 是 | 固定值: `ENROLL_KEY` |
| userId | string | 是 | 用户唯一标识 |
| keyAlgorithm | string | 是 | 密钥算法: `SSCL` 或 `SM2` |
| keySize | integer | 是 | 密钥长度，单位bit |
| timestamp | integer | 是 | Unix时间戳（秒） |

### 消息流转

```
Client -> KMS-Java-Backend -> Kafka(key_generate_log) -> KMS-Go-Backend -> FISCO-BCOS
```

---

## 2. 更新 Payload (key_update_log)

**Kafka Topic**: `key_update_log`

**ActionType**: `UPDATE_KEY`

```json
{
  "traceId": "uuid",
  "requestId": "uuid",
  "actionType": "UPDATE_KEY",
  "keyId": "string",
  "userId": "string",
  "timestamp": 1234567890
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| traceId | string (UUID) | 是 | 全链路追踪ID |
| requestId | string (UUID) | 是 | 每次请求的唯一标识 |
| actionType | string | 是 | 固定值: `UPDATE_KEY` |
| keyId | string | 是 | 待更新密钥的唯一标识 |
| userId | string | 是 | 用户唯一标识 |
| timestamp | integer | 是 | Unix时间戳（秒） |

### 消息流转

```
Client -> KMS-Java-Backend -> Kafka(key_update_log) -> KMS-Go-Backend -> FISCO-BCOS
```

---

## 3. 回收 Payload (key_revoke_log)

**Kafka Topic**: `key_revoke_log`

**ActionType**: `REVOKE_KEY`

```json
{
  "traceId": "uuid",
  "requestId": "uuid",
  "actionType": "REVOKE_KEY",
  "keyId": "string",
  "userId": "string",
  "reason": "string",
  "timestamp": 1234567890
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| traceId | string (UUID) | 是 | 全链路追踪ID |
| requestId | string (UUID) | 是 | 每次请求的唯一标识 |
| actionType | string | 是 | 固定值: `REVOKE_KEY` |
| keyId | string | 是 | 待回收密钥的唯一标识 |
| userId | string | 是 | 用户唯一标识 |
| reason | string | 是 | 回收原因 |
| timestamp | integer | 是 | Unix时间戳（秒） |

### 消息流转

```
Client -> KMS-Java-Backend -> Kafka(key_revoke_log) -> KMS-Go-Backend -> FISCO-BCOS
```

---

## 4. Kafka Topic 分流规则

| Topic Name | ActionType | 说明 |
|------------|------------|------|
| key_generate_log | ENROLL_KEY | 密钥生成消息 |
| key_update_log | UPDATE_KEY | 密钥更新消息 |
| key_revoke_log | REVOKE_KEY | 密钥回收消息 |

### 分流校验清单

- [ ] key_generate_log topic 仅接收 actionType=ENROLL_KEY 的消息
- [ ] key_update_log topic 仅接收 actionType=UPDATE_KEY 的消息
- [ ] key_revoke_log topic 仅接收 actionType=REVOKE_KEY 的消息
- [ ] 每个消息必须包含 traceId 和 requestId
- [ ] timestamp 必须为有效的 Unix 时间戳

---

## 5. 三条链路联调验证

### 5.1 生成链路验证

1. 构造 ENROLL_KEY 消息，发送至 key_generate_log topic
2. 验证 KMS-Java-Backend 接收并解析消息
3. 验证 KMS-Go-Backend 消费消息并上链
4. 验证上链结果回调或状态更新

### 5.2 更新链路验证

1. 构造 UPDATE_KEY 消息，发送至 key_update_log topic
2. 验证 KMS-Java-Backend 接收并解析消息
3. 验证 KMS-Go-Backend 消费消息并上链
4. 验证更新结果回调或状态更新

### 5.3 回收链路验证

1. 构造 REVOKE_KEY 消息，发送至 key_revoke_log topic
2. 验证 KMS-Java-Backend 接收并解析消息
3. 验证 KMS-Go-Backend 消费消息并上链
4. 验证回收结果回调或状态更新

---

## 6. 联调测试脚本

测试脚本位于 `kms-ops/tests/` 目录：

- `generate_load_test.sh` - 生成链路压测脚本
- `update_load_test.sh` - 更新链路压测脚本
- `revoke_load_test.sh` - 回收链路压测脚本

---

## 7. 压测报告模板

压测报告模板位于 `doc/load-test-report-template.md`
