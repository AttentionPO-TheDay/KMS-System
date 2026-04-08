# KMS 项目概览

## 当前状态

当前仓库已经从旧单体/混合形态演进为 6 个当前有效模块 + 2 个历史参考目录：

1. `kms-user/`：统一普通用户前台
2. `kms-generate/`：密钥生成系统
3. `kms-updatedel/`：密钥更新与回收系统
4. `kms-distribute/`：密钥分发系统
5. `kms-acceptance/`：验收与压测系统
6. `kms-ops/`：共享部署与运维编排
7. `legacy-kms/`：拆分前的 Java 主工程，仅用于历史追溯
8. `legacy-kms-go/`：拆分前的 Go 接入服务，仅用于历史追溯

## 当前推荐目录结构

```text
kms-code-copy/
├── doc/
│   ├── project_overview.md
│   ├── message-protocol.md
│   ├── frontend-role-boundary.md
│   ├── user-permission-implementation.md
│   ├── kms-split-implementation-plan.md
│   └── legacy-project_overview.md
├── kms-user/
│   ├── front/
│   ├── docs/
│   └── README.md
├── kms-generate/
│   ├── front/
│   ├── go-backend/
│   ├── java-backend/
│   ├── docs/
│   ├── tests/
│   └── README.md
├── kms-updatedel/
│   ├── front/
│   ├── go-backend/
│   ├── java-backend/
│   ├── docs/
│   ├── sql/
│   ├── tests/
│   └── README.md
├── kms-distribute/
│   ├── front/
│   ├── java-backend/
│   ├── sql/
│   └── README.md
├── kms-acceptance/
│   ├── front/
│   ├── backend/
│   └── README.md
├── kms-ops/
├── legacy-kms/
└── legacy-kms-go/
```

## 模块职责

### `kms-user/`

统一普通用户前台，提供工作台以及生成、生命周期、分发、权限申请等统一入口。

当前前端路由骨架已经落地：

1. `/workbench`
2. `/generate`
3. `/lifecycle`
4. `/distribute`
5. `/permissions`

### `kms-generate/`

密钥生成系统，负责：

1. 用户注册
2. 公共参数获取
3. 密钥生成接入
4. 生成结果查询
5. 生成记录入库
6. 生成事件上链
7. 生成域权限申请与审批接口

当前目录内已同时包含：

1. `front/` 生成系统前端
2. `go-backend/` 高吞吐 Go 接入层
3. `java-backend/` Java 业务层与 Kafka 消费者

### `kms-updatedel/`

密钥更新与回收系统，负责：

1. 密钥更新
2. 密钥回收
3. 自动更新配置
4. 生命周期查询
5. 权限申请、审批、回退
6. 更新/回收事件消费与后续上链

当前目录内已同时包含：

1. `front/` 生命周期系统前端
2. `go-backend/` 更新/回收接入层
3. `java-backend/` 生命周期业务服务
4. `sql/` 权限申请等脚本

### `kms-distribute/`

密钥分发系统，当前已落地 Java 后端与分发记录相关接口，负责：

1. 分发记录查询
2. 分发详情查看
3. 新增/批量新增分发记录
4. 分发记录修改与删除

当前 `front/` 仍以页面片段为主，尚未形成与 generate / lifecycle 同级的完整独立前端工程。

### `kms-acceptance/`

验收附加系统，负责统一执行压测和记录验收结果。

当前包含：

1. `front/` 验收前端，用于配置和触发测试
2. `backend/` 轻量后端，用于调用 `wrk`、汇总结果、保存历史

当前内置验收项：

1. 生成 TPS
2. 更新 TPS
3. 回收 TPS
4. 回收率

### `kms-ops/`

共享部署与运维目录，负责统一编排：

1. MySQL
2. Redis
3. Kafka
4. FISCO BCOS
5. Nginx
6. generate / updatedel 服务挂载与启动
7. 压测脚本与运维脚本

当前关键入口包括：

1. `kms-ops/docker-compose.yml`
2. `kms-ops/start.sh`
3. `kms-ops/stop.sh`
4. `kms-ops/tests/*.sh`

### `legacy-kms/`

历史 Java 单体工程，仅作为迁移来源和实现追溯参考，不再作为当前主开发入口。

### `legacy-kms-go/`

历史 Go 接入服务，仅作为迁移来源和实现追溯参考，不再作为当前主开发入口。

## 当前开发入口

按当前代码状态，优先阅读这些文档：

1. `doc/project_overview.md`
2. `doc/message-protocol.md`
3. `kms-user/README.md`
4. `kms-generate/README.md`
5. `kms-updatedel/README.md`
6. `kms-distribute/README.md`
7. `kms-acceptance/README.md`

## 规划与历史资料入口

以下文档仍然保留，但用途不同：

1. `doc/kms-split-implementation-plan.md`
   说明：拆分实施规划与历史设计口径，不等同于当前代码现状
2. `doc/legacy-project_overview.md`
   说明：拆分前旧系统总览
3. `legacy-kms/legacy-README.md`
4. `legacy-kms/RuoYi-Vue3-master/legacy-README.md`
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
