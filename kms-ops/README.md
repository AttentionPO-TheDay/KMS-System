# kms-ops

共享部署与运维编排目录。

## 当前职责

1. 统一编排 MySQL、Redis、Kafka、FISCO BCOS
2. 启动 generate、updatedel、extracted demo、acceptance 相关服务
3. 承载 Nginx 网关和静态前端发布目录
4. 提供本地构建、检查和压测辅助脚本

## 关键入口

1. `docker-compose.yml`：当前完整编排
2. `build-local.ps1` / `build-local.sh`：本地构建并整理运行产物
3. `start.sh`：从模板恢复 live 运行态并启动整套环境
4. `rebuild-env.sh`：停服、清空运行数据、重新构建并重启
5. `check.ps1`：启动后检查脚本
6. `nginx/nginx.conf`：统一网关和静态资源路由

## 当前编排服务

1. `mysql`：宿主机 `3307` -> 容器 `3306`
2. `redis`：`6379`
3. `kafka`：`9092`
4. `fisco-node`
5. `fisco-console`
6. `generate-go`：`8081`
7. `generate-java`：`9081`
8. `updatedel-go`：`8082`
9. `updatedel-java`：`9082`
10. `kms-distribute`：旧分发后台服务，`8083`
11. `dvadmin3-django`：新分发 demo 后端，`8001` -> `8000`
12. `acceptance-backend`：`9090`
13. `nginx`：`80`

## 当前网关路径

### API

1. `/generate-ingress/` -> generate Go
2. `/generate-api/` -> generate Java
3. `/updatedel-ingress/` -> updatedel Go
4. `/lifecycle-ingress/` -> `/updatedel-ingress/`
5. `/updatedel-api/` -> updatedel Java
6. `/lifecycle-api/` -> updatedel Java
7. `/pqkds-api/` -> extracted demo Django
8. `/acceptance-api/` -> acceptance backend `/api/`

旧分发 Java 后端仅作为后台服务运行，不通过 nginx 恢复 `/distribute-api/`。

### 前端

1. `/generate/`
2. `/updatedel/`
3. `/lifecycle/` -> `/updatedel/`
4. `/distribute/`
5. `/user/`
6. `/acceptance/`

## 前端开发代理口径

为避免本地 Vite 开发时请求落到错误的 `localhost:80`，当前前端开发代理统一为：

1. `kms-generate/front`：`/generate-api` -> `http://localhost:9081`
2. `kms-updatedel/front`：`/generate-api` -> `http://localhost:9081`
3. `kms-updatedel/front`：`/lifecycle-api` -> `http://localhost:9082`
4. `kms-user/front`：`/generate-api` -> `9081`，`/lifecycle-api` -> `9082`

Docker 网关发布环境仍由 `kms-ops/nginx/nginx.conf` 统一处理，不依赖这些本地开发代理。

`nginx` 已开启 Docker DNS 运行时解析，后端容器重建后会自动刷新上游地址，避免网关继续指向旧容器 IP 而出现 `502 Bad Gateway`。

## 公共查询总表

三套业务后台当前都保留一张公共查询总表：`src/views/query/keyList/index.vue`。

对应菜单入口：

1. `密钥查询 -> 用户密钥查询`
2. `密钥查询 -> 区块链查看`

当前约定：

1. `用户密钥页` 与 `用户密钥查询` 使用同一组件，公共菜单仅保留 `用户密钥查询`
2. 公共查询总表已支持 `存证详情` 综合弹窗
3. 综合弹窗展示业务字段、工作状态、存证状态、上链版本、区块高度、交易哈希
4. `链上凭证` 继续保留为轻量链上信息弹窗

## 本地构建

在仓库根目录执行：

```powershell
./kms-ops/build-local.ps1
```

脚本当前会：

1. 构建 `kms-generate/java-backend`
2. 构建 `kms-updatedel/java-backend`
3. 构建 `kms-generate/go-backend`
4. 构建 `kms-updatedel/go-backend`
5. 构建 `kms-acceptance/backend`
6. 构建 `kms-generate/front`
7. 构建 `kms-updatedel/front`
8. 构建 `kms-distribute/java-backend` 后台服务
9. 构建 `kms-distribute/extracted/ruoyi (2)/web` 新分发 demo 前端
10. 构建 `kms-user/front`
11. 构建 `kms-acceptance/front`
12. 整理产物到 `kms-ops/runtime` 和 `kms-ops/front`

如果只需单独校验前端，可分别在各自 `front/` 目录执行：

```powershell
npm run build:prod
```

说明：RuoYi 前端项目默认使用 `build:prod`，extracted demo 前端使用 `build`；旧 `kms-distribute/front` 不再构建和发布。

## 启动方式

首次部署或新服务器启动，先在仓库根目录执行：

```bash
bash ./kms-ops/build-local.sh
```

再在 `kms-ops/` 目录执行：

```bash
bash ./start.sh
```

`start.sh` 会自动：

1. 检查 `runtime/` 和前端静态产物是否已构建
2. 初始化 MySQL / Redis / Kafka 运行目录
3. 优先从 `kms-ops/fisco/template/` 恢复单节点 live 数据到 `kms-ops/nodes/127.0.0.1`
4. 从模板恢复 `kms-ops/fisco/console/conf/`，并把 live 状态中的合约地址同步到 `.env`
5. 在缺少 console 运行包时，从 `kms-ops/nodes/127.0.0.1` 下载并同步 console 运行包到 `kms-ops/fisco/console/`
6. 启动 Docker 编排（包含 `fisco-console`）
7. 仅在 `.env` 与 live 状态都缺少合约地址时才自动部署 `KeyEvidence`
8. 若 `.env` 不存在，则自动从 `.env.example` 初始化

`rebuild-env.sh` 会执行：

1. `docker compose down`
2. 清空 MySQL / Redis / Kafka 运行数据
3. 清空 `kms-ops/nodes/` 与 `kms-ops/fisco/live/` live 运行态
4. 重新执行 `build-local.sh`
5. 再执行 `start.sh`

当前 FISCO 目录分两类：

1. `kms-ops/fisco/template/`：仓库内受控的单节点 dev 模板，除配置外还包含可恢复的节点数据、证书和状态快照
2. `kms-ops/nodes/`、`kms-ops/fisco/console/conf/`、`kms-ops/fisco/live/`：当前 live 运行态目录

之所以以前容易出现大量无关文件，是因为链节点、console 证书、deploy 日志和合约生成物都属于运行态；如果没有正确隔离到 ignored live 目录，`git status` 会一次性出现很多噪音。

如需刷新当前模板，请执行：

```bash
bash ./kms-ops/scripts/refresh-fisco-template.sh
```

如需手动从零重建单节点链并刷新模板，请执行：

```bash
bash ./kms-ops/scripts/init-FBchain.sh
```

停止：

```bash
docker compose down
```

补充说明：`start.sh` 末尾的控制台输出里 MySQL 仍打印 `3306`，但当前宿主机实际暴露端口以 `docker-compose.yml` 为准，即 `3307`。

## 检查方式

在 `kms-ops/` 目录执行：

```powershell
./check.ps1
```

## 相关文档

1. `doc/docker-runbook.md`
2. `doc/project_overview.md`
