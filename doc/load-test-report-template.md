# KMS 压测报告模板

## 测试信息

| 项目 | 内容 |
|------|------|
| 测试时间 | YYYY-MM-DD HH:MM:SS |
| 测试环境 | DEV / TEST / PRE-PROD / PROD |
| 测试人员 |  |
| 测试类型 | 性能压测 / 链路联调 / 回归测试 |

---

## 1. 测试概述

### 1.1 测试目的

[描述本次压测的目的]

### 1.2 测试范围

- [ ] 生成链路 (ENROLL_KEY)
- [ ] 更新链路 (UPDATE_KEY)
- [ ] 回收链路 (REVOKE_KEY)

### 1.3 测试前置条件

- [ ] Kafka 集群正常运行
- [ ] KMS-Java-Backend 服务正常
- [ ] KMS-Go-Backend 服务正常
- [ ] FISCO-BCOS 区块链网络正常
- [ ] MySQL 数据库正常

---

## 2. 测试结果汇总

### 2.1 生成链路 (ENROLL_KEY)

| 指标 | 目标值 | 实际值 | 结果 |
|------|--------|--------|------|
| QPS |  |  |  |
| 平均响应时间 (ms) |  |  |  |
| P99 响应时间 (ms) |  |  |  |
| 错误率 (%) |  |  |  |
| 上链成功率 (%) |  |  |  |

### 2.2 更新链路 (UPDATE_KEY)

| 指标 | 目标值 | 实际值 | 结果 |
|------|--------|--------|------|
| QPS |  |  |  |
| 平均响应时间 (ms) |  |  |  |
| P99 响应时间 (ms) |  |  |  |
| 错误率 (%) |  |  |  |
| 上链成功率 (%) |  |  |  |

### 2.3 回收链路 (REVOKE_KEY)

| 指标 | 目标值 | 实际值 | 结果 |
|------|--------|--------|------|
| QPS |  |  |  |
| 平均响应时间 (ms) |  |  |  |
| P99 响应时间 (ms) |  |  |  |
| 错误率 (%) |  |  |  |
| 上链成功率 (%) |  |  |  |

---

## 3. 详细测试数据

### 3.1 生成链路详细数据

```
[粘贴 generate_load_test.sh 的压测输出]
```

### 3.2 更新链路详细数据

```
[粘贴 update_load_test.sh 的压测输出]
```

### 3.3 回收链路详细数据

```
[粘贴 revoke_load_test.sh 的压测输出]
```

---

## 4. 消息流转验证

### 4.1 生成链路

| 环节 | 状态 | 说明 |
|------|------|------|
| Client -> Go-Backend | PASS / FAIL |  |
| Go-Backend -> Kafka | PASS / FAIL |  |
| Kafka -> Java-Backend | PASS / FAIL |  |
| Java-Backend -> FISCO | PASS / FAIL |  |
| 全链路耗时 |  | ms |

### 4.2 更新链路

| 环节 | 状态 | 说明 |
|------|------|------|
| Client -> Go-Backend | PASS / FAIL |  |
| Go-Backend -> Kafka | PASS / FAIL |  |
| Kafka -> Java-Backend | PASS / FAIL |  |
| Java-Backend -> FISCO | PASS / FAIL |  |
| 全链路耗时 |  | ms |

### 4.3 回收链路

| 环节 | 状态 | 说明 |
|------|------|------|
| Client -> Go-Backend | PASS / FAIL |  |
| Go-Backend -> Kafka | PASS / FAIL |  |
| Kafka -> Java-Backend | PASS / FAIL |  |
| Java-Backend -> FISCO | PASS / FAIL |  |
| 全链路耗时 |  | ms |

---

## 5. 问题记录

| 序号 | 问题描述 | 严重程度 | 状态 | 备注 |
|------|----------|----------|------|------|
| 1 |  | 高/中/低 | OPEN / RESOLVED |  |

---

## 6. 结论与建议

### 6.1 结论

[综合评估本次压测结果]

### 6.2 建议

[针对发现问题的改进建议]

---

## 7. 附录

### 7.1 测试脚本

- generate_load_test.sh
- update_load_test.sh
- revoke_load_test.sh

### 7.2 环境配置

```
[描述测试环境的配置信息]
```

### 7.3 压测命令

```bash
# 生成链路压测
./kms-ops/tests/generate_load_test.sh

# 更新链路压测
./kms-ops/tests/update_load_test.sh

# 回收链路压测
./kms-ops/tests/revoke_load_test.sh
```
