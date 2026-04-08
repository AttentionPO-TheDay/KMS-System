# KMS 拆分 Agent 任务拆解

本文档用于后续并行分配给不同 agent 实施，所有任务均以可独立交付、可独立验收为原则。

---

## Agent 1：目录重构与代码迁移

### 目标

把现有代码按新结构迁移到：

1. `kms-generate`
2. `kms-updatedel`
3. `kms-ops`

### 输入

1. 当前目录 `kms`
2. 当前目录 `kms-go`
3. 当前目录 `kms-ops`
4. 总规划文档 `doc/kms-split-implementation-plan.md`

### 输出

1. 新目录下的基础代码骨架
2. 旧目录与新目录迁移映射说明
3. 不再使用的旧文件清单

### 具体任务

1. 将生成相关代码迁移到 `kms-generate`
2. 将更新回收相关代码迁移到 `kms-updatedel`
3. 保留共享运维内容在 `kms-ops`
4. 为每个新工程补充 README
5. 标记共享模块和待重构模块

### 验收标准

1. 目录结构完整
2. 每个目录职责清晰
3. 后续 agent 可以直接进入各自目录开发

---

## Agent 2：生成系统 Go 后端

### 目标

产出 `kms-generate/go-backend`，作为生成链路高吞吐入口。

### 具体任务

1. 基于当前 `kms-go` 创建生成系统 Go 服务
2. 保留 `ENROLL_KEY`、`REENROLL_KEY`
3. 移除 `UPDATE_KEY`、`REVOKE_KEY`
4. 路由前缀调整为 `/generate/request/*`
5. topic 改为 `key_generate_log`
6. 整理配置项，避免硬编码
7. 保留 Fiber + Sonic + Kafka 异步发送性能优化
8. 提供健康检查接口
9. 提供生成压测脚本和启动说明

### 验收标准

1. 服务可独立启动
2. 可接收生成请求
3. 可向 Kafka 生成 topic 正常投递
4. 不包含更新回收逻辑

---

## Agent 3：生命周期系统 Go 后端

### 目标

产出 `kms-updatedel/go-backend`，作为更新和回收链路的独立高并发入口。

### 具体任务

1. 新建生命周期 Go 服务工程
2. 实现 `UPDATE_KEY` 接口
3. 实现 `REVOKE_KEY` 接口
4. 路由前缀调整为 `/lifecycle/request/*`
5. 更新和回收分别投递到：
   - `key_update_log`
   - `key_revoke_log`
6. 统一请求参数命名为 `keyId`
7. 增加 `traceId` 或 `requestId`
8. 接入 Redis 实现幂等去重
9. 返回标准状态码和状态文本
10. 按 `keyId` 设置 Kafka message key
11. 增加监控指标和错误统计
12. 提供更新/回收压测脚本

### 验收标准

1. 服务可独立启动
2. 更新和回收接口均可用
3. Kafka topic 投递正确
4. 具备幂等和明确错误返回

---

## Agent 4：生成系统 Java 后端

### 目标

产出 `kms-generate/java-backend`，作为生成链路业务处理服务。

### 具体任务

1. 从现有 Java 后端提取生成相关模块
2. 新建生成系统启动工程
3. 提取 `ENROLL_KEY` Kafka 消费者
4. 提取批量入库逻辑
5. 提取生成上链逻辑
6. 提供生成记录查询接口
7. 记录生成审计日志
8. 清理更新/回收相关业务入口

### 验收标准

1. 服务可独立启动
2. 可消费 `key_generate_log`
3. 可完成入库与上链
4. 可查询生成结果

---

## Agent 5：生命周期系统 Java 后端

### 目标

产出 `kms-updatedel/java-backend`，作为更新回收链路业务处理服务。

### 具体任务

1. 从现有 Java 后端提取生命周期相关模块
2. 新建生命周期系统启动工程
3. 拆分更新消费者 `UpdateKafkaConsumer`
4. 拆分回收消费者 `RevokeKafkaConsumer`
5. 提取 `rotateKeyById` 相关服务
6. 提取逻辑回收服务
7. 保留权限申请、审批、回退模块
8. 保留自动回退定时任务
9. 提供生命周期查询接口
10. 拆分生命周期上链任务消费者

### 验收标准

1. 服务可独立启动
2. 可消费更新与回收 topic
3. 可完成轮换和回收
4. 权限审批与回退功能正常

---

## Agent 6：生成系统前端

### 目标

产出 `kms-generate/front`，只承载生成相关前端能力。

### 具体任务

1. 基于现有 Vue 前端创建生成系统工程
2. 保留生成页面和相关菜单
3. 移除更新、回收、审批页面
4. API 改为 `generate` 域接口
5. 调整环境变量和构建配置
6. 补充页面访问说明

### 验收标准

1. 可独立启动和构建
2. 页面仅包含生成域能力
3. API 指向生成系统后端

---

## Agent 7：生命周期系统前端

### 目标

产出 `kms-updatedel/front`，只承载更新与回收相关前端能力。

### 具体任务

1. 基于现有 Vue 前端创建生命周期系统工程
2. 保留更新、回收、自动更新、权限相关页面
3. 移除生成专用页面
4. API 改为 `lifecycle` 和 `permission` 域接口
5. 调整环境变量和构建配置
6. 补充页面访问说明

### 验收标准

1. 可独立启动和构建
2. 页面仅包含生命周期域能力
3. API 指向生命周期系统后端

---

## Agent 8：运维与网关编排

### 目标

重构 `kms-ops`，支撑两系统并存部署。

### 具体任务

1. 重构 `docker-compose.yml`
2. 新增四个业务服务容器：
   - `generate-front`
   - `generate-go`
   - `generate-java`
   - `updatedel-front`
   - `updatedel-go`
   - `updatedel-java`
3. 保留共享中间件容器
4. 重构 nginx 路由
5. 定义环境变量与服务依赖
6. 准备一键启动和停止脚本

### 验收标准

1. 两系统可同时启动
2. 路由清晰
3. 共享中间件工作正常

---

## Agent 9：消息协议、联调与压测

### 目标

统一消息协议并验证全链路。

### 具体任务

1. 定义生成 payload
2. 定义更新 payload
3. 定义回收 payload
4. 补充 `traceId`、`requestId`、`actionType`
5. 校验 Kafka topic 分流是否正确
6. 验证上链任务消息流转
7. 验证生成、更新、回收三条链路联调
8. 输出压测脚本和压测报告模板

### 验收标准

1. 三类消息协议清晰
2. 三条链路可完整跑通
3. 压测结果可记录、可复现

---

## 推荐并行顺序

1. Agent 1 先完成目录和迁移骨架
2. Agent 2、3、4、5 可并行开发后端
3. Agent 6、7 在后端接口边界稳定后开展前端拆分
4. Agent 8 在服务命名和端口稳定后改造运维编排
5. Agent 9 贯穿后期联调与压测
