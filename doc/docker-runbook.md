# Docker Runbook

## 当前目标

让 `kms-ops/docker-compose.yml` 采用“先本地编译，再容器运行”的方式启动当前有效服务。

## 当前包含的服务

1. `mysql`：共享数据库，宿主机端口 `3307`，容器内端口 `3306`
2. `redis`：共享缓存，端口 `6379`
3. `kafka`：共享消息队列，端口 `9092`
4. `fisco-node`：区块链节点
5. `fisco-console`：FISCO Console 运行容器
6. `generate-go`：生成接入层，端口 `8081`
7. `generate-java`：生成业务层，端口 `9081`
8. `updatedel-go`：生命周期接入层，端口 `8082`
9. `updatedel-java`：生命周期业务层，端口 `9082`
10. `kms-distribute`：分发业务层，端口 `8083`
11. `acceptance-backend`：验收后端，端口 `9090`
12. `nginx`：网关，端口 `80`

## 统一配置口径

### MySQL

1. 数据库名：`kms`
2. 用户名：`root`
3. 密码：`root123456`

### 服务发现

容器内统一使用 Docker 网络服务名：

1. `mysql`
2. `redis`
3. `kafka`
4. `fisco-node`

## 本地编译

推荐直接执行：

```powershell
./kms-ops/build-local.ps1
```

该脚本会完成：

1. 构建 `kms-generate/java-backend`
2. 构建 `kms-updatedel/java-backend`
3. 构建 `kms-distribute/java-backend`
4. 构建 `kms-generate/go-backend`
5. 构建 `kms-updatedel/go-backend`
6. 构建 `kms-acceptance/backend`
7. 构建 `kms-generate/front`
8. 构建 `kms-updatedel/front`
9. 构建 `kms-distribute/extracted/ruoyi (2)/web`（新分发 demo 前端；
   旧 `kms-distribute/front` 已不再构建与发布）
10. 构建 `kms-user/front`
11. 构建 `kms-acceptance/front`
12. 整理产物到 `kms-ops/runtime` 和 `kms-ops/front`

## 启动方式

当前部署口径分两步：

1. 先构建运行产物

```bash
bash ./kms-ops/build-local.sh
```

2. 再启动运行环境

```bash
bash ./kms-ops/start.sh
```

`start.sh` 会在首次启动或 live 目录缺失时恢复运行态数据，包括：

1. `kms-ops/mysql/data/`
2. `kms-ops/redis/data/`
3. `kms-ops/kafka/kafka_data/`
4. 从 `kms-ops/fisco/template/` 恢复单节点 FISCO live 数据到 `kms-ops/nodes/127.0.0.1/`
5. 从模板恢复 `kms-ops/fisco/console/conf/`
6. 将 `kms-ops/fisco/live/contract.env` 或模板状态中的合约地址同步到 `.env`
7. 若缺少 console 运行包，则通过 `kms-ops/nodes/127.0.0.1/download_console.sh` 下载并同步到 `kms-ops/fisco/console/`
8. 若 `.env` 不存在，则自动从 `kms-ops/.env.example` 初始化

`rebuild-env.sh` 会执行完整重建：

1. `docker compose down`
2. 清空 MySQL / Redis / Kafka 数据目录
3. 清空 `kms-ops/nodes/` 与 `kms-ops/fisco/live/` live 目录
4. 重新执行 `build-local.sh`
5. 再执行 `start.sh`

区块链当前采用单节点模板恢复模式：

- 模板目录：`kms-ops/fisco/template/`
- live 节点目录：`kms-ops/nodes/127.0.0.1/`
- live 状态目录：`kms-ops/fisco/live/`

普通重置不再默认重新 build chain；只有模板不存在或显式执行手动兜底脚本时，才会从零重建单节点链。

为什么之前一次重置会出现很多文件：

1. `kms-ops/nodes/` 是当前 live 节点目录，执行链恢复、console 下载或重新部署时会生成运行态文件
2. `kms-ops/fisco/console/conf/`、`kms-ops/fisco/live/contract.env`、deploy 日志和合约生成物都属于运行态
3. 仓库顶层 `nodes/` 仍然存在历史残留目录名，阅读文档和脚本时需要和 `kms-ops/nodes/` 区分开

现在的推荐口径是：

- **提交模板**：`kms-ops/fisco/template/`
- **live 运行态目录**：`kms-ops/nodes/`、`kms-ops/fisco/console/conf/`、`kms-ops/fisco/live/`

停止：

```bash
docker compose down
```

## 宿主机端口发布口径（2026-09-24 收紧）

**对外只需要 80 端口**（网关）。其余一律不发布，或只绑回环：

| 端口 | 服务 | 宿主发布 | 说明 |
|---|---|---|---|
| 80 | 网关 nginx | `0.0.0.0:80` | 唯一对外入口 |
| 3307 / 6379 / 9092 | MySQL / Redis / Kafka | `127.0.0.1` | 仅宿主机可连 |
| 8545~8548 / 20200~20203 | 4 个 FISCO 节点 | `127.0.0.1` | 仅宿主机可连 |
| 8081 / 8082 / 9081 / 9082 / 8001 | Go 入站层 ×2、Java 业务层 ×2、dvadmin | **不发布** | 网关与验收容器都按**服务名**在 Docker 内网访问 |

后 5 个原先发布到宿主机，2026-09-24 去掉，原因两条：

1. **部署环境不允许占用这些端口**（远端实测
   `failed to bind host port 127.0.0.1:8081/tcp: address already in use`），
   而它们本来就不需要宿主端口 —— 网关走 `http://generate-go:8081` 这类服务名；
   验收容器也走内网（`ACCEPTANCE_*_BASE_URL` 注入的就是内网地址，
   调用 `security_test.sh` 时用 `--GenerateGoBaseUrl` 等参数传进去）。
2. 少发布一个端口就少一份暴露面：Go 入站层的身份来自 Java 写入的 `X-Kms-User`
   内部头，dvadmin 的演示接口没有鉴权，都不该对外可达。

**本机调试**若需要直连这些端口（`kms-ops/check.ps1`、`kms-ops/tests/*_load_test.sh`、
`tools/verify-pa-target.mjs` 用的是 `127.0.0.1:8081` 这类地址），加覆盖文件即可：

```bash
docker compose -f docker-compose.yml -f docker-compose.debug-ports.yml up -d
```

覆盖文件只绑回环，不会对局域网暴露；**部署时不要带这个 `-f`**。

## 网关路径

### API

1. `/generate-api/` -> generate Java
2. `/updatedel-api/` -> updatedel Java
3. `/lifecycle-api/` -> updatedel Java
4. `/distribute-api/` -> distribute Java（8083，kms-user 分发记录查询）
5. `/pqkds-api/` -> dvadmin3-django
6. `/acceptance-api/` -> acceptance backend `/api/`

已下架（安全加固）：`/generate-ingress/`、`/updatedel-ingress/`、`/lifecycle-ingress/`。
Go 入站层仅限 Docker 内网调用，不再经网关对外暴露，
因为其身份来源为 Java 写入的 `X-Kms-User` 内部头，对外暴露会导致身份可伪造。

### 前端

1. `/generate/`
2. `/updatedel/`
3. `/lifecycle/` -> `/updatedel/`
4. `/distribute/`
5. `/user/`
6. `/acceptance/`

## 前端本地开发代理

Docker 网关路径与本地 Vite 开发代理不是一回事。

当前本地开发应保持：

1. `kms-generate/front`：`/generate-api` -> `http://localhost:9081`
2. `kms-updatedel/front`：`/generate-api` -> `http://localhost:9081`
3. `kms-updatedel/front`：`/lifecycle-api` -> `http://localhost:9082`
4. `kms-user/front`：`/generate-api` -> `http://localhost:9081`
5. `kms-user/front`：`/lifecycle-api` -> `http://localhost:9082`
6. `kms-user/front`：`/distribute-api` -> `http://localhost:8083`

这样前端本地联调与 Docker 网关中的 API 映射保持一致，不会再出现请求误转发到 `localhost:80` 导致的 `502` 和验证码加载失败。

网关配置同时启用了 Docker DNS 运行时解析，因此 `generate-java`、`updatedel-java`、`kms-distribute` 等容器重建后，Nginx 会自动刷新上游地址，不需要再手工重启网关来清理旧 IP。

## 启动后检查

在 `kms-ops/` 目录执行：

```powershell
./check.ps1
```

脚本会检查：

1. `docker compose ps`
2. `generate-go` 健康接口
3. `updatedel-go` 健康接口
4. MySQL 关键表是否存在：`sys_user`、`keymanage`、`permission_request`、`key_distribute_record`

## 首次排查顺序

1. `docker compose ps`
2. `docker compose logs mysql`
3. `docker compose logs generate-java`
4. `docker compose logs updatedel-java`
5. `docker compose logs kms-distribute`
6. `docker compose logs acceptance-backend`
7. `docker compose logs nginx`

## 说明

1. `docker-compose.yml` 当前直接消费本地构建产物，不在容器内执行 Maven 或 Go 编译。
   因此**必须先执行 `build-local.ps1` / `build-local.sh`**，否则容器会因缺少
   `kms-ops/runtime/` 下的产物而启动失败。这是当前采用的部署口径；
   若后续改为镜像内构建，需同步修改本节与各服务 Dockerfile。
2. `kms-user` 和 `kms-acceptance/front` 当前作为静态前端产物由 `nginx` 提供。
3. `legacy-kms/` 仍然保留为历史参考，不参与当前 Docker 编排。
4. 旧版编排文件如 `docker-compose-before.yml` 仅作历史对照，不代表当前部署方式。
5. 当前编排除基础设施外共 9 个应用服务：`generate-go`、`generate-java`、
   `updatedel-go`、`updatedel-java`、`kms-distribute`、`dvadmin3-django`、
   `acceptance-backend`、`fisco-console`、`nginx`。
   其中 `dvadmin3-django`（8001→8000）与 `fisco-console`
   （`network_mode: service:fisco-node`，无独立端口）在早前版本中曾被遗漏。
6. 需轮换的安全凭据（均无默认值，参见 `kms-ops/.env.example`）：
   `KMS_TOKEN_SECRET`、`INTERNAL_TOKEN`、`MYSQL_ROOT_PASSWORD`、
   `DRUID_LOGIN_USERNAME/PASSWORD`；可选 `KGC_MASTER_SECRET`。
   任一必填项缺失时 `docker compose` 会直接报错退出，这是有意设计。
