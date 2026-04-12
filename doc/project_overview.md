# KMS 项目概览

## 当前状态

当前仓库已经演进为 6 个当前有效模块和 2 个历史参考目录：

1. `kms-user/`：统一普通用户前台
2. `kms-generate/`：密钥生成系统
3. `kms-updatedel/`：密钥更新与回收系统
4. `kms-distribute/`：密钥分发系统
5. `kms-acceptance/`：验收与压测系统
6. `kms-ops/`：共享部署与运维编排
7. `legacy-kms/`：拆分前的 Java 主工程，仅用于历史追溯
8. `legacy-kms-go/`：拆分前的 Go 接入服务，仅用于历史追溯

## 推荐目录结构

```text
kms-code-copy/
├── doc/
├── kms-user/
├── kms-generate/
├── kms-updatedel/
├── kms-distribute/
├── kms-acceptance/
├── kms-ops/
├── legacy-kms/
└── legacy-kms-go/
```

## 模块职责

### `kms-user/`

统一普通用户前台，当前已经是可联调的用户门户，不再只是路由骨架。

当前已实现的用户侧主入口包括：

1. `/workbench` 统一工作台
2. `/generate` 密钥生成、生成记录、公共库与公共参数查询
3. `/lifecycle` 生命周期操作、安全分析与结果回执
4. `/distribute` 分发记录查询
5. `/permissions` 权限申请、记录与回退
6. `/login`、`/register`、`/user/profile`

当前用户流中，`/generate` 统一承接生成、记录、公共库与参数查询；`/lifecycle` 可以对单条密钥查看“安全分析”，并查看生命周期结果回执。

前端通过独立 API 客户端直连不同后端：

1. `generateApi` -> `/generate-api`
2. `lifecycleApi` -> `/lifecycle-api`
3. `distributeApi` -> `/distribute-api`

### `kms-generate/`

密钥生成系统，负责：

1. 用户注册
2. 公共参数获取
3. 密钥生成接入
4. 生成结果查询
5. 生成记录入库
6. 生成事件上链
7. 生成域权限申请与审批
8. 管理员端算法图解与演示

当前目录内包含：

1. `front/` 生成系统管理员前端，当前算法说明已合并为统一的“算法图解与演示”页
2. `go-backend/` 高吞吐 Go 接入层
3. `java-backend/` Java 业务层与 Kafka 消费者
4. `docs/` 迁移与设计文档

统一算法页覆盖 SM2 / SSCL 的理论速览、真实请求交互和本地恢复演示。

### `kms-updatedel/`

密钥更新与回收系统，负责：

1. 密钥更新
2. 密钥回收
3. 自动更新配置
4. 生命周期查询
5. 密钥安全分析
6. 权限申请、审批、回退
7. 更新/回收事件消费与后续上链

当前目录内包含：

1. `front/` 生命周期管理员前端，支持更新、回收、自动更新和“安全分析”
2. `go-backend/` 更新/回收接入层
3. `java-backend/` 生命周期业务服务，提供生命周期查询和分析聚合接口
4. `sql/` 权限申请等脚本
5. `docs/` 迁移与设计文档

补充说明：生命周期前端的部分只读查询会通过 `VITE_APP_GENERATE_API`（默认 `/generate-api`）访问生成系统数据。

### `kms-distribute/`

密钥分发系统，当前不仅提供记录查询与维护，还会自动消费其他业务域事件生成分发记录。

当前能力包括：

1. 分发记录查询
2. 分发详情查看
3. 新增与批量新增分发记录
4. 分发记录修改与删除
5. 分发记录导出
6. 消费 `key_generate_log`、`key_update_log`、`key_revoke_log`

当前目录内包含：

1. `front/` 独立分发前端
2. `java-backend/` Java 业务服务与 Kafka 消费者
3. `sql/` 分发记录表脚本

### `kms-acceptance/`

验收与压测系统，负责执行 `wrk` 压测、记录历史结果，并对关键验收指标给出统一入口。

当前包含：

1. `front/` 验收前端，用于配置和触发测试
2. `backend/` Go 后端，用于执行 `wrk`、汇总结果、保存历史

当前内置场景：

1. 生成 TPS
2. 更新 TPS
3. 回收 TPS
4. 回收率

### `kms-ops/`

共享部署与运维目录，统一编排：

1. MySQL
2. Redis
3. Kafka
4. FISCO BCOS
5. Generate Go / Java
6. Updatedel Go / Java
7. Distribute Java
8. Acceptance Backend
9. Nginx 网关与前端静态资源

当前关键入口包括：

1. `kms-ops/docker-compose.yml`
2. `kms-ops/build-local.ps1`
3. `kms-ops/check.ps1`
4. `kms-ops/nginx/nginx.conf`

### `legacy-kms/` 与 `legacy-kms-go/`

仅作为迁移来源和实现追溯参考，不再作为当前主开发入口。

## 当前开发入口

按当前代码状态，优先阅读这些文档：

1. `doc/project_overview.md`
2. `doc/message-protocol.md`
3. `kms-user/README.md`
4. `kms-generate/README.md`
5. `kms-updatedel/README.md`
6. `kms-distribute/README.md`
7. `kms-acceptance/README.md`
8. `kms-ops/README.md`

## 规划与历史资料入口

以下资料保留用于历史追溯或拆分方案参考，不代表当前实现：

1. `doc/kms-split-implementation-plan.md`
2. `doc/java-ruoyi-repair-guide.md`
3. `doc/kms-agent-task-breakdown.md`
4. `doc/legacy-project_overview.md`
5. `legacy-kms/`
6. `legacy-kms-go/`

## 推荐理解顺序

1. 先看 `doc/project_overview.md` 了解当前模块与职责
2. 再看 `doc/message-protocol.md` 了解当前链路与消息约定
3. 普通用户前台开发优先进入 `kms-user/`
4. 生成链路开发进入 `kms-generate/`
5. 生命周期链路开发进入 `kms-updatedel/`
6. 分发、验收、部署分别进入 `kms-distribute/`、`kms-acceptance/`、`kms-ops/`
7. 只有在迁移或排查旧逻辑时，再进入 `legacy-*` 目录
