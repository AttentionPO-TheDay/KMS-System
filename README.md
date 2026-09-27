# KMS —— 无证书密钥的生命周期管理

系统按**密钥的生命周期**划分为三个子系统：

| 子系统 | 在生命周期中的位置 | 目录 |
|---|---|---|
| **密钥生成** | 产出新的一套密钥 | `kms-generate/` |
| **密钥更新与回收** | 更新 / 回收基础的那一套 | `kms-updatedel/` |
| **密钥分发** | 用非对称密钥加密后分发对称密钥 | `kms-distribute/` |

三者处理的都是**同一套无证书密钥**，只是处于生命周期的不同阶段。
密钥分发中，非对称密钥是**封装工具**，被投递的是对称密钥（SM4）。

---

## 仓库结构

| 目录 | 说明 | 跟踪文件 |
|---|---|---|
| `kms-generate/` | 密钥生成系统（Go 接入层 + Java 业务层） | 379 |
| `kms-updatedel/` | 密钥更新与回收系统（Go + Java + 管理端前端） | 668 |
| `kms-distribute/` | 密钥分发系统（Django 节点管理后端 + SQL） | 438 |
| `kms-user/` | 普通用户前台 | 249 |
| `kms-acceptance/` | 验收与压测系统 | 26 |
| `kms-ops/` | 统一部署编排（Compose / 网关 / 构建与发版脚本） | 256 |
| `design-tokens/` | **共享设计令牌**（自托管字体 + 配色），5 个前端经 `@tokens` 别名引用 | 110 |
| `tools/` | 真浏览器验证脚本（CDP 驱动）与查库工具 | 57 |
| `doc/` | 文档 | 23 |
| `security/` | `security_test.sh`，验收镜像的构建输入 | 1 |

顶层的 `README.md`、`.gitignore`、`.gitattributes` 为仓库配置。

---

## 各子系统说明

### `kms-generate` —— 密钥生成

- `go-backend/`：高并发接入层
- `java-backend/`：生成业务层

> `/generate/` 静态前端已退役，页面并入统一管理端。退役理由见
> `doc/retired-generate-frontend.md`。**后端不受影响**：`/generate-api/`
> 仍代理到 `generate-java`，管理端仍在用它查询公钥、用户密钥池与生成历史。

### `kms-updatedel` —— 密钥更新与回收

- `go-backend/`：生命周期接入层
- `java-backend/`：生命周期业务层（更新 / 回收 / 自动更新 / 安全分析）
- `front/`：统一管理端（`/updatedel/`）

### `kms-distribute` —— 密钥分发

- `dvadmin/`：Django 后端，承载**节点管理**（节点的增删改、Kyber / Falcon /
  国密密钥的生成与就绪状态）。它是管理端「分发与区块链」各页面的数据来源。
- `sql/`：分发相关建表脚本

> 分发自带的静态后台（原 `dvadmin/web/`）与旧分发 Java 服务均已下线，
> 网关对 `/distribute/` 与 `/distribute-api/` 显式返回 404。
> `/pqkds-api/` **仍在服务**，是节点管理页的数据来源。

### `kms-user` —— 普通用户前台

登录入口，含密钥生成、更新与回收、分发、对称密钥查看等用户侧页面。

### `kms-acceptance` —— 验收与压测

无登录，后端用固定凭据替代身份。

### `kms-ops` —— 部署编排

```text
kms-ops/build-local.ps1    本地构建（Maven + Go + 4 个前端）
kms-ops/docker-compose.yml 服务编排
kms-ops/nginx/nginx.conf   统一网关（路由 + 静态资源）
kms-ops/ship.ps1           打包镜像模式的部署包
kms-ops/ship-source.ps1    打包源码模式的部署包
kms-ops/deploy.sh          远端部署入口（check / build / up / verify）
```

---

## 快速入口

| 想看什么 | 看哪里 |
|---|---|
| 系统整体设计 | `doc/project_overview.md` |
| 服务间通信协议 | `doc/message-protocol.md` |
| 部署方式 | `kms-ops/README.md`、`doc/docker-runbook.md` |
| 三子系统重构方案 | `doc/three-subsystem-refactor-plan.md` |
| 节点管理与链上运维 | `doc/fisco-chain-and-node-page-runbook.md` |

### 部署

```powershell
# 本地构建 + 启动
pwsh -File kms-ops/build-local.ps1
cd kms-ops; docker compose build; docker compose up -d
```

```bash
# 远端
bash deploy.sh check && bash deploy.sh build && bash deploy.sh up && bash deploy.sh verify
```

### 验证

```bash
node tools/verify-pages-smoke.mjs        # 全部页面冒烟
node tools/verify-node-keys-autogen.mjs  # 节点密钥自动生成
node tools/verify-node-batch-falcon.mjs  # 批量生成与失败隔离
node tools/verify-node-crud.mjs          # 节点增删
```

判据是**渲染后的 DOM**，不是 HTTP 状态码——本系统的故障史里，
"接口 200 但页面上什么都没有"出现过多次。

---

## 历史资料

以下内容仅用于历史追溯或阶段性说明，**不代表当前实现**：

1. `doc/kms-split-implementation-plan.md`
2. `doc/java-ruoyi-repair-guide.md`
3. `doc/kms-agent-task-breakdown.md`
4. `doc/legacy-project_overview.md`
5. `doc/pqkds-demo-migration-execution-plan.md`
6. `doc/remote-upload-list.md`
7. `doc/retired-generate-frontend.md`

> **2026-09-26 清理**：已删除 `legacy-kms/`、`legacy-kms-go/`、
> `kms-generate/front/`、`kms-distribute/front/`、
> `kms-distribute/java-backend/` 等约 1800 个死代码文件。
> 需要查阅可 `git checkout pre-cleanup-20260926 -- <路径>` 从回滚点取回。
