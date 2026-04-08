# KMS 项目拆分实施规划

> 说明：本文档保留拆分时期的规划与目标设计，主要用于理解当初的拆分思路。
> 当前仓库现状请优先参考 `doc/project_overview.md`、`doc/message-protocol.md` 以及各模块 `README.md`。

## 1. 目标

当前项目需要从单一混合形态拆分为两套独立业务系统，同时保留共享中间件与统一运维编排。

拆分后的目标结构为：

1. `kms-generate`
   - 密钥生成系统
   - 独立前端
   - 独立 Go 后端
   - 独立 Java 后端
   - 核心目标：支撑密钥生成链路 `100000 TPS`
2. `kms-updatedel`
   - 密钥更新与回收系统
   - 独立前端
   - 独立 Go 后端
   - 独立 Java 后端
   - 核心目标：支撑更新 `5000 TPS`、回收 `5000 TPS`
3. `kms-ops`
   - 统一运维编排目录
   - 第一阶段继续共享中间件：MySQL、Redis、Kafka、FISCO BCOS、Nginx

本规划的核心原则：

1. 先拆系统边界，再拆数据边界
2. 先拆接口和消息链路，再拆前端页面
3. 第一阶段不拆共享中间件实例
4. 保证生成链路和生命周期链路可独立压测、独立扩容、互不干扰

---

## 2. 最终目录规划

```text
kms-code/
├── doc/
│   └── kms-split-implementation-plan.md
├── kms-generate/
│   ├── front/
│   ├── go-backend/
│   ├── java-backend/
│   ├── docs/
│   └── tests/
├── kms-updatedel/
│   ├── front/
│   ├── go-backend/
│   ├── java-backend/
│   ├── docs/
│   └── tests/
└── kms-ops/
    ├── nginx/
    ├── mysql/
    ├── redis/
    ├── kafka/
    ├── fisco/
    ├── scripts/
    └── docker-compose.yml
```

### 2.1 目录职责

1. `kms-generate/front`
   - 生成系统前端工程
2. `kms-generate/go-backend`
   - 生成系统高并发 Go 接入服务
3. `kms-generate/java-backend`
   - 生成系统 Java 业务服务
4. `kms-updatedel/front`
   - 更新与回收系统前端工程
5. `kms-updatedel/go-backend`
   - 更新与回收系统 Go 接入服务
6. `kms-updatedel/java-backend`
   - 更新与回收系统 Java 业务服务
7. `kms-ops`
   - 共享中间件、网关、部署编排、联调脚本

---

## 3. 系统边界定义

## 3.1 `kms-generate` 系统边界

### 负责的业务

1. 用户注册
2. 公共参数获取
3. 密钥生成
4. 生成结果查询
5. 生成事件入库
6. 生成事件上链

### 不负责的业务

1. 密钥更新
2. 密钥回收
3. 自动更新策略
4. 权限审批与回退

### 当前代码对应来源

1. Go 侧
   - `legacy-kms-go/cmd/main.go`
   - `legacy-kms-go/controllers/request_controller.go` 中 `EnrollKey`、`ReenrollKey`
   - `legacy-kms-go/service/key_service.go` 中生成逻辑
   - `legacy-kms-go/service/generator/*`
   - `legacy-kms-go/utils/kafka_producer.go`
2. Java 侧
   - `KafkaConsumer` 中 `ENROLL_KEY` 处理
   - `keymanageServiceImpl` 中新增入库与新增上链逻辑
   - `ChainConsumer`
3. 前端侧
   - `keygenerate`
   - 生成结果展示与查询相关页面

---

## 3.2 `kms-updatedel` 系统边界

### 负责的业务

1. 密钥更新
2. 密钥回收
3. 自动更新开关/配置
4. 生命周期查询
5. 权限申请
6. 权限审批
7. 权限自动回退
8. 更新/回收事件上链

### 不负责的业务

1. 新密钥生成算法计算
2. 生成侧高吞吐入站链路

### 当前代码对应来源

1. Go 侧
   - `legacy-kms-go/controllers/request_controller.go` 中 `UpdateKey`、`RevokeKey`
   - `legacy-kms-go/service/key_service.go` 中更新/回收 Kafka 投递逻辑
2. Java 侧
   - `RequestController` 中 `UPDATE_KEY`、`REVOKE_KEY`
   - `keymanageServiceImpl.rotateKeyById`
   - `keymanageServiceImpl.deletekeymanageByKeyId`
   - `PermissionRequestController`
   - `PermissionRequestServiceImpl`
   - `PermissionRevokeTask`
3. 前端侧
   - `keyupdate`
   - `keydelete`
   - `keyautoupdate`
   - `permission/request`

---

## 4. 总体架构

```text
                           +-------------------+
                           |      kms-ops      |
                           | nginx / kafka     |
                           | mysql / redis     |
                           | fisco / scripts   |
                           +---------+---------+
                                     |
                +--------------------+--------------------+
                |                                         |
                v                                         v

      +---------------------------+           +----------------------------+
      |       kms-generate        |           |       kms-updatedel        |
      |                           |           |                            |
      | front                     |           | front                      |
      | go-backend                |           | go-backend                 |
      | java-backend              |           | java-backend               |
      +---------------------------+           +----------------------------+
```

### 4.1 架构原则

1. 两套系统代码独立
2. 两套系统前端独立发布
3. 两套系统 Go 后端独立监听端口
4. 两套系统 Java 后端独立部署与扩容
5. Kafka topic 按业务拆分
6. 上链任务与主消费链路分离

---

## 5. 接口边界规划

## 5.1 `kms-generate` 接口规划

### Go 接入接口

1. `POST /generate/request/Register`
2. `POST /generate/request/ENROLL_KEY`
3. `POST /generate/request/REENROLL_KEY`
4. `POST /generate/request/comparam`
5. `GET /generate/ping`

### Java 业务接口

1. `GET /generate/key/list`
2. `GET /generate/key/{keyId}`
3. `GET /generate/key/chain/{keyId}`
4. `GET /generate/user/profile`

---

## 5.2 `kms-updatedel` 接口规划

### Go 接入接口

1. `POST /lifecycle/request/UPDATE_KEY`
2. `POST /lifecycle/request/REVOKE_KEY`
3. `GET /lifecycle/ping`

### Java 业务接口

1. `GET /lifecycle/key/list`
2. `GET /lifecycle/key/{keyId}`
3. `PUT /lifecycle/key/auto-update`
4. `POST /permission/request/submit`
5. `GET /permission/request/list`
6. `GET /permission/request/{requestId}`
7. `PUT /permission/request/approve/{requestId}`
8. `PUT /permission/request/reject/{requestId}`
9. `PUT /permission/request/rollback/{requestId}`

### 5.3 命名约束

1. 新系统不要继续复用 `/keymanage/request/*`
2. 统一使用 `keyId`，不要混用 `keyid`
3. 新接口需自带 `traceId` 或 `requestId`

---

## 6. Go 服务拆分规划

## 6.1 `kms-generate/go-backend`

### 职责

1. 高并发接收生成请求
2. 执行 SM2/SSCL/AES 本地生成
3. 参数校验
4. 异步写 Kafka
5. 提供高吞吐监控指标

### 核心性能目标

1. 密钥生成目标 `100000 TPS`
2. 独占端口
3. 独占 Kafka producer 参数
4. 独占 topic
5. 独立压测脚本

### 迁移建议

1. 保留当前生成控制器
2. 移除 `UPDATE_KEY`
3. 移除 `REVOKE_KEY`
4. 把 topic 常量改为生成专用

---

## 6.2 `kms-updatedel/go-backend`

### 职责

1. 高并发接收更新请求
2. 高并发接收回收请求
3. 参数校验
4. 幂等控制
5. Kafka 投递
6. 返回明确处理状态
7. 提供更新/回收链路监控指标

### 核心性能目标

1. 更新目标 `5000 TPS`
2. 回收目标 `5000 TPS`
3. 更新与回收内部拆成两条独立 pipeline

### 必须补齐的能力

1. 统一请求 DTO
2. 补充 `traceId` / `requestId`
3. Redis 幂等去重
4. 更新与回收分 topic 投递
5. Kafka 消息 key 使用 `keyId`
6. 明确响应状态
   - `accepted`
   - `duplicate`
   - `queue_full`
   - `auth_failed`
   - `invalid_param`
7. 补充指标
   - QPS
   - 入队数
   - 投递失败数
   - 积压数
   - 鉴权失败数

---

## 7. Java 服务拆分规划

## 7.1 `kms-generate/java-backend`

### 职责

1. 消费生成消息
2. 用户鉴权终校验
3. 生成记录入库
4. 触发上链
5. 提供生成记录查询接口
6. 记录生成审计日志

### 推荐模块

1. `GenerateKafkaConsumer`
2. `GenerateKeyService`
3. `GenerateChainService`
4. `GenerateAuditService`
5. `GenerateKeyController`

### 拆分要求

1. 只保留 `ENROLL_KEY` 链路
2. 不再包含更新/回收处理逻辑

---

## 7.2 `kms-updatedel/java-backend`

### 职责

1. 消费更新消息
2. 消费回收消息
3. 执行轮换
4. 执行逻辑回收
5. 写生命周期日志
6. 触发上链
7. 权限审批
8. 自动回退定时任务

### 推荐模块

1. `UpdateKafkaConsumer`
2. `RevokeKafkaConsumer`
3. `LifecycleChainConsumer`
4. `KeyRotateService`
5. `KeyRevokeService`
6. `LifecycleKeyController`
7. `PermissionRequestController`
8. `PermissionRollbackTaskService`

### 拆分要求

1. 生命周期系统只负责已有密钥状态变更
2. 不负责密钥生成算法计算

---

## 8. Kafka 规划

当前 `go_key_manage_log` 不再适合作为统一入口 topic，需要拆分。

## 8.1 推荐 topic 方案

1. `key_generate_log`
   - 生成系统消息入口
2. `key_update_log`
   - 更新消息入口
3. `key_revoke_log`
   - 回收消息入口
4. `key_chain_task_generate`
   - 生成系统上链任务
5. `key_chain_task_lifecycle`
   - 生命周期系统上链任务

## 8.2 原则

1. 生成与生命周期必须分 topic
2. 更新与回收建议分 topic
3. 同一密钥按 `keyId` 作为消息 key 保证顺序
4. 上链任务与主业务消费分离

---

## 9. 数据库规划

## 9.1 第一阶段策略

1. 保持一个 MySQL 实例
2. 暂不强制拆表
3. 暂时继续使用 `keymanage` 表
4. 通过代码职责控制写入边界
   - `kms-generate` 只新增
   - `kms-updatedel` 只更新/回收/生命周期变更

## 9.2 第二阶段预留

后续可按演进需要拆成：

1. 独立 schema
   - `kms_generate`
   - `kms_lifecycle`
2. 或独立表
   - `key_record`
   - `key_lifecycle_log`
   - `permission_request`

---

## 10. 前端拆分规划

## 10.1 `kms-generate/front`

### 保留内容

1. 密钥生成页
2. 生成历史页
3. 公参页
4. 注册页

### 移除内容

1. 更新页
2. 回收页
3. 自动更新页
4. 权限审批页

### API 规划

1. `src/api/generate/*`
2. 独立 `VITE_APP_BASE_API`

---

## 10.2 `kms-updatedel/front`

### 保留内容

1. 更新页
2. 回收页
3. 自动更新页
4. 权限申请页
5. 审批页
6. 生命周期审计页

### 移除内容

1. 生成专用页面
2. 生成专用 API 模块

### API 规划

1. `src/api/lifecycle/*`
2. `src/api/permission/*`
3. 独立 `VITE_APP_BASE_API`

---

## 11. Nginx 与部署规划

## 11.1 域名建议

优先建议使用双域名：

1. `generate.xxx.com`
2. `lifecycle.xxx.com`

如果暂时没有双域名条件，则使用路径区分：

1. `/generate/*`
2. `/lifecycle/*`

## 11.2 路由建议

1. `/generate-ingress/*` -> `kms-generate/go-backend`
2. `/generate-api/*` -> `kms-generate/java-backend`
3. `/lifecycle-ingress/*` -> `kms-updatedel/go-backend`
4. `/lifecycle-api/*` -> `kms-updatedel/java-backend`

## 11.3 容器建议

`kms-ops/docker-compose.yml` 第一阶段建议包含：

1. `mysql`
2. `redis`
3. `kafka`
4. `fisco-node`
5. `generate-front`
6. `generate-go`
7. `generate-java`
8. `updatedel-front`
9. `updatedel-go`
10. `updatedel-java`
11. `nginx`

---

## 12. 实施阶段拆解

## 阶段 A：目录与仓库重构

### A1. 顶层目录重组

1. 创建 `kms-generate`
2. 创建 `kms-updatedel`
3. 保留 `kms-ops`
4. 建立迁移映射表

### A2. 现有代码归属梳理

1. 标记生成系统模块
2. 标记生命周期系统模块
3. 标记共享能力模块
4. 标记待删除的旧耦合模块

---

## 阶段 B：Go 服务拆分

### B1. 生成 Go 服务

1. 从当前 `kms-go` 提取生成链路
2. 只保留 `ENROLL_KEY`
3. 调整路由前缀
4. 替换 Kafka topic
5. 准备生成压测脚本

### B2. 生命周期 Go 服务

1. 提取更新/回收链路
2. 标准化请求结构
3. 补充幂等逻辑
4. 更新与回收分 topic
5. 增加监控和错误码
6. 准备更新/回收压测脚本

---

## 阶段 C：Java 服务拆分

### C1. 生成 Java 服务

1. 提取生成消费者
2. 提取生成查询接口
3. 提取生成上链逻辑
4. 清理更新/回收相关代码

### C2. 生命周期 Java 服务

1. 提取更新消费者
2. 提取回收消费者
3. 保留审批与回退模块
4. 提供生命周期查询接口
5. 拆分上链任务消费者

---

## 阶段 D：前端拆分

### D1. 生成前端

1. 复制并裁剪当前前端工程
2. 只保留生成页面
3. 替换 API 路径
4. 独立构建产物

### D2. 生命周期前端

1. 复制并裁剪当前前端工程
2. 只保留更新/回收/权限页面
3. 替换 API 路径
4. 独立构建产物

---

## 阶段 E：消息与数据治理

### E1. Kafka topic 拆分

1. 新建生成 topic
2. 新建更新 topic
3. 新建回收 topic
4. 新建上链 topic

### E2. 消息协议统一

1. 定义生成 payload
2. 定义更新 payload
3. 定义回收 payload
4. 加入 `traceId`
5. 加入操作结果字段

### E3. 数据写入边界治理

1. 明确生成系统只新增
2. 明确生命周期系统只更新/回收
3. 明确审计字段归属

---

## 阶段 F：部署与联调

### F1. Compose 重构

1. 新增双前端服务
2. 新增双 Go 服务
3. 新增双 Java 服务
4. 保留共享中间件

### F2. Nginx 重构

1. 生成系统静态资源路由
2. 生命周期系统静态资源路由
3. 四条后端路由分流
4. 健康检查路由

### F3. 联调与压测

1. 生成链路联调
2. 更新链路联调
3. 回收链路联调
4. 上链链路验证
5. 高并发压测

---

## 13. Agent 任务分配建议

以下任务粒度适合后续并行分配给不同 agent。

## Agent 1：目录与模块迁移

### 任务目标

1. 创建 `kms-generate`、`kms-updatedel`、`kms-ops` 目标结构
2. 迁移现有代码到新目录
3. 输出旧目录到新目录的映射表

### 交付物

1. 新目录结构
2. 模块迁移说明
3. 冗余模块清单

---

## Agent 2：生成 Go 服务

### 任务目标

1. 基于现有 `kms-go` 提取 `kms-generate/go-backend`
2. 删除更新/回收相关路由和服务逻辑
3. 改造生成专用 topic
4. 保留高吞吐优化参数

### 交付物

1. 可独立启动的生成 Go 服务
2. 生成专用配置
3. 生成压测脚本

---

## Agent 3：生命周期 Go 服务

### 任务目标

1. 新建 `kms-updatedel/go-backend`
2. 实现 `UPDATE_KEY`
3. 实现 `REVOKE_KEY`
4. 加入幂等、消息 key、topic 分流、错误码和指标

### 交付物

1. 可独立启动的生命周期 Go 服务
2. 更新/回收请求协议文档
3. 更新/回收压测脚本

---

## Agent 4：生成 Java 服务

### 任务目标

1. 新建 `kms-generate/java-backend`
2. 提取生成消费者
3. 提取生成查询接口
4. 提取生成上链任务

### 交付物

1. 可独立启动的生成 Java 服务
2. 生成消费者实现
3. 生成链路接口文档

---

## Agent 5：生命周期 Java 服务

### 任务目标

1. 新建 `kms-updatedel/java-backend`
2. 提取更新/回收消费者
3. 保留并整理权限审批/回退模块
4. 暴露生命周期查询 API

### 交付物

1. 可独立启动的生命周期 Java 服务
2. 更新/回收消费者实现
3. 权限审批接口文档

---

## Agent 6：生成前端

### 任务目标

1. 新建 `kms-generate/front`
2. 保留生成相关页面
3. 替换 API base
4. 独立构建

### 交付物

1. 生成系统前端工程
2. 菜单与页面清单
3. 构建配置

---

## Agent 7：生命周期前端

### 任务目标

1. 新建 `kms-updatedel/front`
2. 保留更新/回收/权限页面
3. 替换 API base
4. 独立构建

### 交付物

1. 生命周期系统前端工程
2. 菜单与页面清单
3. 构建配置

---

## Agent 8：运维编排与网关

### 任务目标

1. 重构 `kms-ops/docker-compose.yml`
2. 重构 `nginx.conf`
3. 定义环境变量与服务依赖
4. 保持共享中间件方案可运行

### 交付物

1. 新版 compose 文件
2. 新版 nginx 配置
3. 启动脚本与说明

---

## Agent 9：联调与压测

### 任务目标

1. 验证 Kafka topic 链路
2. 验证生成联调
3. 验证更新联调
4. 验证回收联调
5. 输出压测结果

### 交付物

1. 联调报告
2. 压测报告
3. 性能瓶颈清单

---

## 14. 实施顺序建议

必须按以下顺序推进：

1. 目录重构
2. Kafka topic 与消息协议拆分
3. Go 服务拆分
4. Java 服务拆分
5. 前端拆分
6. `kms-ops` 编排改造
7. 联调与压测

不建议先拆前端，不建议第一阶段先拆数据库。

---

## 15. 第一阶段验收标准

## `kms-generate`

1. 前端可独立打开
2. Go 服务可独立接收生成请求
3. Java 服务可独立消费生成消息
4. 生成结果可查询
5. 生成上链可工作
6. 可独立压测

## `kms-updatedel`

1. 前端可独立打开
2. Go 服务可独立接收更新请求
3. Go 服务可独立接收回收请求
4. Java 服务可独立消费更新/回收消息
5. 权限审批与自动回退可工作
6. 可独立压测

## `kms-ops`

1. 两套系统可通过共享中间件同时运行
2. 路由边界清晰
3. 生成链路不会压垮生命周期链路

---

## 16. 关键风险与控制

### 风险 1：系统拆了，底层接口没拆

控制措施：

1. 强制新系统使用新路径前缀
2. 禁止继续复用混合型旧接口

### 风险 2：生命周期 Go 服务仍只是简单转发

控制措施：

1. 必须补幂等、错误码、topic 分流、指标
2. 必须支持高并发下明确失败返回

### 风险 3：Kafka topic 仍互相争抢

控制措施：

1. 生成、更新、回收拆 topic
2. 上链任务拆 topic

### 风险 4：Java 服务仍保留生成与生命周期混合代码

控制措施：

1. 按业务拆消费者
2. 按业务拆服务层
3. 避免一个服务承载两类业务主流程

### 风险 5：前端看似两套，实际共用同一 API 模块

控制措施：

1. 独立 API 目录
2. 独立构建
3. 独立环境变量

---

## 17. 下一步执行建议

下一阶段建议优先落地以下三件事：

1. 建立目标目录骨架
2. 输出旧代码到新目录的模块迁移清单
3. 定义三类 Kafka 业务消息协议

完成这三步后，再按 agent 并行推进代码实现，风险最低。
