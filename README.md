# KMS Code Copy

KMS 当前主仓库，包含普通用户前台、生成系统、生命周期系统、分发系统、验收系统，以及统一部署编排目录。

## 仓库结构

1. `doc/`：当前文档、协议说明、运维说明、历史规划资料
2. `kms-user/`：统一普通用户前台
3. `kms-generate/`：密钥生成系统
4. `kms-updatedel/`：密钥更新与回收系统
5. `kms-distribute/`：密钥分发系统
6. `kms-acceptance/`：验收与压测系统
7. `kms-ops/`：共享部署与运维编排
8. `legacy-kms/`：拆分前 Java 历史工程，仅作参考
9. `legacy-kms-go/`：拆分前 Go 历史工程，仅作参考

## 当前推荐阅读顺序

1. `doc/project_overview.md`
2. `doc/message-protocol.md`
3. `kms-user/README.md`
4. `kms-generate/README.md`
5. `kms-updatedel/README.md`
6. `kms-distribute/README.md`
7. `kms-acceptance/README.md`
8. `kms-ops/README.md`

## 模块说明

### `kms-user`

统一普通用户前台，负责：

1. 登录、注册、个人中心
2. 密钥生成、生成记录、公共库与公共参数查询
3. 密钥更新、回收、自动更新操作、安全分析与结果回执
4. 分发记录查询
5. 权限申请、申请记录、回退

当前用户侧页面中，`/generate` 承接生成、历史记录、公共库与参数查询；`/lifecycle` 支持更新、回收、自动更新、结果回执与单条密钥“安全分析”。

### `kms-generate`

密钥生成系统，包含：

1. `go-backend/` 生成接入层
2. `java-backend/` 生成业务层
3. `front/` 生成系统管理员前端，当前已将算法说明整合为统一的“算法图解与演示”页

统一算法页覆盖 SM2 / SSCL 的理论速览、真实请求交互和本地恢复演示。

### `kms-updatedel`

密钥更新与回收系统，包含：

1. `go-backend/` 生命周期接入层
2. `java-backend/` 生命周期业务层，提供生命周期查询、自动更新与密钥安全分析接口
3. `front/` 生命周期管理员前端，支持密钥更新、回收、自动更新和“安全分析”

前端部分查询会通过 `VITE_APP_GENERATE_API`（默认 `/generate-api`）读取生成系统数据。

### `kms-distribute`

密钥分发系统，当前负责：

1. 分发记录查询与维护
2. 消费生成、更新、回收事件并沉淀分发记录

### `kms-acceptance`

验收与压测系统，负责：

1. 管理压测场景
2. 调用 `wrk` 执行测试
3. 保存测试历史

### `kms-ops`

统一编排目录，负责：

1. Docker Compose 编排
2. 本地构建产物整理
3. Nginx 网关与静态前端发布
4. 启动检查和压测辅助脚本

## 快速入口

### 看当前实现

```text
doc/project_overview.md
doc/message-protocol.md
```

### 看部署方式

```text
kms-ops/README.md
doc/docker-runbook.md
```

### 看普通用户前台

```text
kms-user/README.md
```

## 当前部署入口

如果要按当前编排整体启动，优先看：

1. `kms-ops/build-local.ps1`
2. `kms-ops/docker-compose.yml`
3. `kms-ops/nginx/nginx.conf`
4. `kms-ops/check.ps1`

## 历史资料说明

以下目录和部分文档仅用于历史追溯、迁移参考或阶段性方案说明，不代表当前实现：

1. `legacy-kms/`
2. `legacy-kms-go/`
3. `doc/kms-split-implementation-plan.md`
4. `doc/java-ruoyi-repair-guide.md`
5. `doc/kms-agent-task-breakdown.md`
