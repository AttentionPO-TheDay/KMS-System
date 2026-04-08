# KMS 项目概览

## 当前状态

当前仓库已经按双系统方向整理为三块主结构：

1. `kms-generate/`：密钥生成系统
2. `kms-updatedel/`：密钥更新与回收系统
3. `kms-ops/`：共享部署与运维编排

同时保留两份历史迁移来源目录：

1. `legacy-kms/`：拆分前的 Java 主工程
2. `legacy-kms-go/`：拆分前的 Go 前置服务

## 当前推荐目录结构

```text
kms-code-copy/
├── doc/
│   ├── project_overview.md
│   ├── legacy-project_overview.md
│   ├── kms-split-implementation-plan.md
│   └── kms-agent-task-breakdown.md
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
├── kms-ops/
├── legacy-kms/
└── legacy-kms-go/
```

## 目录职责

### `kms-generate/`

密钥生成系统，承载生成链路相关的前端、Go 接入服务和 Java 业务服务。

### `kms-updatedel/`

密钥更新与回收系统，承载生命周期管理、权限审批和回退等相关功能。

### `kms-ops/`

当前有效的部署与运维目录，负责统一编排：

1. MySQL
2. Redis
3. Kafka
4. FISCO BCOS
5. Nginx
6. 双系统后端挂载与启动

`kms-ops/docker-compose.yml` 和 `kms-ops/start.sh` 已按 `kms-generate/`、`kms-updatedel/` 的新结构组织。

### `legacy-kms/`

历史 Java 单体目录，仅作为迁移来源和实现追溯参考，不再作为主开发入口。

### `legacy-kms-go/`

历史 Go 前置服务目录，仅作为迁移来源和实现追溯参考，不再作为主开发入口。

## 开发入口

按当前目标，优先阅读这些文档：

1. `doc/kms-split-implementation-plan.md`
2. `kms-generate/README.md`
3. `kms-updatedel/README.md`
4. `kms-generate/docs/migration-map.md`

## 历史资料入口

需要回溯旧实现时，再查看：

1. `doc/legacy-project_overview.md`
2. `legacy-kms/legacy-README.md`
3. `legacy-kms/RuoYi-Vue3-master/legacy-README.md`
4. `legacy-kms/`
5. `legacy-kms-go/`

## 推荐理解顺序

1. 先看 `doc/kms-split-implementation-plan.md` 理解拆分目标
2. 再看 `doc/project_overview.md` 了解当前目录职责
3. 然后进入 `kms-generate/` 或 `kms-updatedel/` 做具体开发
4. 只有在迁移或排查旧逻辑时，再进入 `legacy-*` 目录
