# KMS 代码迁移映射表

> 说明：本文中的迁移来源目录已在仓库中重命名为 `legacy-kms/` 和 `legacy-kms-go/`，以下路径均已按当前仓库名称更新。

## 一、系统边界概述

### kms-generate（密钥生成系统）
负责：用户注册、公共参数获取、密钥生成、生成结果查询、生成事件入库、生成事件上链

### kms-updatedel（密钥更新与回收系统）
负责：密钥更新、密钥回收、自动更新开关/配置、生命周期查询、权限申请/审批/自动回退、更新/回收事件上链

---

## 二、源文件归属映射

### 2.1 Go 后端文件归属

| 源文件路径 | 归属系统 | 归属模块 | 说明 |
|-----------|---------|---------|------|
| `legacy-kms-go/cmd/main.go` | kms-generate | go-backend | 高并发接入服务入口（生成专用） |
| `legacy-kms-go/controllers/request_controller.go` | **kms-generate**：`EnrollKey`、`ReenrollKey`<br>**kms-updatedel**：`UpdateKey`、`RevokeKey` | 共享控制器 | 需要拆分到各自系统 |
| `legacy-kms-go/service/key_service.go` | **kms-generate**：`EnrollKey`方法<br>**kms-updatedel**：`UpdateKey`、`RevokeKey`方法 | 共享Service | 需要拆分到各自系统 |
| `legacy-kms-go/service/generator/sscl_generator.go` | kms-generate | go-backend | SSCL密钥生成算法 |
| `legacy-kms-go/service/generator/sm2_generator.go` | kms-generate | go-backend | SM2密钥生成算法（如果存在） |
| `legacy-kms-go/utils/kafka_producer.go` | kms-generate | go-backend | Kafka异步生产者（生成专用topic） |
| `legacy-kms-go/models/keymanage.go` | 共享 | 共享 | 数据模型定义 |

**不再使用的冗余模块：**
- 无（当前 legacy-kms-go 结构清晰，无冗余）

### 2.2 Java 后端文件归属

| 源文件路径 | 归属系统 | 归属模块 | 说明 |
|-----------|---------|---------|------|
| `legacy-kms/ruoyi-admin/.../controller/RequestController.java` | **kms-generate**：`Register`、`ENROLL_KEY`<br>**kms-updatedel**：`UPDATE_KEY`、`REVOKE_KEY` | 共享Controller | 需要拆分 |
| `legacy-kms/ruoyi-admin/.../controller/KeymanageController.java` | kms-generate | java-backend | 密钥查询接口（生成结果查询） |
| `legacy-kms/ruoyi-admin/.../service/impl/KafkaConsumer.java` | **kms-generate**：`ENROLL_KEY` 消费处理<br>**kms-updatedel**：`UPDATE_KEY`、`REVOKE_KEY` 消费处理 | 共享Consumer | 需要拆分为两个独立的Consumer |
| `legacy-kms/ruoyi-admin/.../service/impl/keymanageServiceImpl.java` | **kms-generate**：`insertkeymanage`（新增入库）<br>**kms-updatedel**：`rotateKeyById`、`deletekeymanageByKeyId`（更新/回收） | 共享Service | 需要拆分或重构 |
| `legacy-kms/ruoyi-admin/.../service/impl/ChainConsumer.java` | 共享 | 共享 | 上链任务消费（ENROLL/ROTATE/REVOKE） |
| `legacy-kms/ruoyi-admin/.../service/impl/FiscoBcosService.java` | 共享 | 共享 | 区块链上链服务 |
| `legacy-kms/ruoyi-admin/.../service/impl/generator/SSCLGenerator.java` | kms-generate | java-backend | SSCL生成器（Java侧，如需要） |
| `legacy-kms/ruoyi-admin/.../service/impl/generator/ECCGenerator.java` | kms-generate | java-backend | SM2生成器（Java侧，如需要） |
| `legacy-kms/ruoyi-system/.../permission/service/*` | kms-updatedel | java-backend | 权限申请/审批/回退模块 |
| `legacy-kms/ruoyi-system/.../permission/task/PermissionRevokeTask.java` | kms-updatedel | java-backend | 权限自动回退定时任务 |

**不再使用的冗余模块：**
- 无明确冗余模块，但部分模块需拆分

### 2.3 前端文件归属

| 源文件路径 | 归属系统 | 说明 |
|-----------|---------|------|
| `legacy-kms/RuoYi-Vue3-master/src/views/keygenerate/*` | kms-generate | 密钥生成页面 |
| `legacy-kms/RuoYi-Vue3-master/src/views/register.vue` | kms-generate | 用户注册页面 |
| `legacy-kms/RuoYi-Vue3-master/src/views/userKeys.vue` | kms-generate | 生成结果展示与查询页面 |
| `legacy-kms/RuoYi-Vue3-master/src/views/keyupdate/*` | kms-updatedel | 密钥更新页面 |
| `legacy-kms/RuoYi-Vue3-master/src/views/keydelete/*` | kms-updatedel | 密钥回收页面 |
| `legacy-kms/RuoYi-Vue3-master/src/views/keyautoupdate/*` | kms-updatedel | 自动更新配置页面 |
| `legacy-kms/RuoYi-Vue3-master/src/views/permission/*` | kms-updatedel | 权限申请/审批页面 |
| `legacy-kms/RuoYi-Vue3-master/src/api/keyuser/*` | kms-generate | 用户注册API |
| `legacy-kms/RuoYi-Vue3-master/src/views/keymanage/*` | kms-generate | 密钥管理页面 |

**不再使用的冗余模块：**
- 无

---

## 三、共享模块说明

以下模块被两个系统共享使用，迁移后需保持引用：

| 模块 | 路径 | 共享方式 |
|-----|------|---------|
| Kafka Producer | kms-generate/go-backend | 生成系统独占topic：`key_generate_log` |
| Kafka Producer | kms-updatedel/go-backend | 更新/回收系统使用独立topic |
| ChainConsumer | kms-generate/java-backend<br>kms-updatedel/java-backend | 共享 `key_chain_task` topic |
| FiscoBcosService | 共享 | 两个系统均需调用区块链上链 |
| MySQL/Redis | kms-ops | 共享数据库实例 |

---

## 四、Kafka Topic 规划

| Topic | 归属系统 | 用途 |
|-------|---------|------|
| `key_generate_log` | kms-generate | 生成系统消息入口 |
| `key_update_log` | kms-updatedel | 更新消息入口 |
| `key_revoke_log` | kms-updatedel | 回收消息入口 |
| `key_chain_task` | 共享 | 上链任务（生成、更新、回收共用） |

---

## 五、接口边界规划

### kms-generate Go 后端接口
- `POST /generate/request/Register` - 用户注册
- `POST /generate/request/ENROLL_KEY` - 密钥生成
- `POST /generate/request/REENROLL_KEY` - 重新生成
- `POST /generate/request/comparam` - 公共参数获取
- `GET /generate/ping` - 健康检查

### kms-updatedel Go 后端接口
- `POST /lifecycle/request/UPDATE_KEY` - 密钥更新
- `POST /lifecycle/request/REVOKE_KEY` - 密钥回收
- `GET /lifecycle/ping` - 健康检查

---

## 六、当前落地状态

| 模块 | 当前状态 | 说明 |
|-----|------|------|
| `kms-generate/go-backend` | ✅ 已落地 | 已提供 `/generate/request/*` 接口并投递 `key_generate_log` |
| `kms-updatedel/go-backend` | ✅ 已落地 | 已提供 `/lifecycle/request/*` 接口并投递更新/回收 topic |
| `kms-generate/java-backend` | ✅ 已落地 | 已提供生成查询接口，并消费 `key_generate_log` |
| `kms-updatedel/java-backend` | ✅ 已落地 | 已提供生命周期接口，并消费 `key_update_log` / `key_revoke_log` |
| `kms-user/front` | ✅ 已建立骨架 | 已提供统一普通用户前台基础路由 |
| `kms-distribute/java-backend` | ✅ 已落地 | 已提供分发记录 CRUD 接口 |
| `kms-distribute/front` | ⏳ 部分落地 | 当前仍以页面片段为主，尚未形成完整工程 |

---

## 七、关键文件依赖关系

### Go 后端依赖
```
cmd/main.go
  └── controllers/RequestController
        └── service/KeyManageService
              ├── service/generator/* (kms-generate专用)
              └── utils/KafkaProducer (kms-generate专用)
```

### Java 后端依赖
```
RequestController (拆分)
  ├── kms-generate: Register, ENROLL_KEY
  └── kms-updatedel: UPDATE_KEY, REVOKE_KEY

KafkaConsumer (拆分)
  ├── kms-generate: ENROLL_KEY 消费 -> 批量入库 -> 发送上链
  └── kms-updatedel: UPDATE_KEY/REVOKE_KEY 消费 -> 轮换/回收 -> 发送上链

ChainConsumer (共享)
  └── 消费 key_chain_task -> 执行上链
```

---

## 七、说明

1. 本文档主要用于说明迁移来源与归属，不再表示“目标骨架尚未创建”。
2. 当前仓库已经进入多系统并存阶段，实际现状请同时参考 `doc/project_overview.md` 与各模块 `README.md`。

*文档创建日期：2026-04-08*
*文档版本：v1.1*
