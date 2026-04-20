# kms-ops

共享部署与运维编排目录。

## 当前职责

1. 统一编排 MySQL、Redis、Kafka、FISCO BCOS
2. 启动 generate、updatedel、distribute、acceptance 相关服务
3. 承载 Nginx 网关和静态前端发布目录
4. 提供本地构建、检查和压测辅助脚本

## 关键入口

1. `docker-compose.yml`：当前完整编排
2. `build-local.ps1`：本地构建并整理运行产物
3. `check.ps1`：启动后检查脚本
4. `nginx/nginx.conf`：统一网关和静态资源路由

## 当前编排服务

1. `mysql`：`3306`
2. `redis`：`6379`
3. `kafka`：`9092`
4. `fisco-node`
5. `generate-go`：`8081`
6. `generate-java`：`9081`
7. `updatedel-go`：`8082`
8. `updatedel-java`：`9082`
9. `kms-distribute`：`8083`
10. `acceptance-backend`：`9090`
11. `nginx`：`80`

## 当前网关路径

### API

1. `/generate-ingress/` -> generate Go
2. `/generate-api/` -> generate Java
3. `/updatedel-ingress/` -> updatedel Go
4. `/lifecycle-ingress/` -> `/updatedel-ingress/`
5. `/updatedel-api/` -> updatedel Java
6. `/lifecycle-api/` -> updatedel Java
7. `/distribute-api/` -> distribute Java
8. `/acceptance-api/` -> acceptance backend `/api/`

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
4. `kms-user/front`：`/generate-api` -> `9081`，`/lifecycle-api` -> `9082`，`/distribute-api` -> `8083`

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
3. 构建 `kms-distribute/java-backend`
4. 构建 `kms-generate/go-backend`
5. 构建 `kms-updatedel/go-backend`
6. 构建 `kms-acceptance/backend`
7. 构建 `kms-generate/front`
8. 构建 `kms-updatedel/front`
9. 构建 `kms-distribute/front`
10. 构建 `kms-user/front`
11. 构建 `kms-acceptance/front`
12. 整理产物到 `kms-ops/runtime` 和 `kms-ops/front`

如果只需单独校验前端，可分别在各自 `front/` 目录执行：

```powershell
npm run build:prod
```

说明：前端项目默认没有 `build` 脚本，统一使用 `build:prod`。

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
3. 生成单节点 FISCO 数据到 `kms-ops/nodes/`
4. 同步链证书到 `kms-ops/fisco/console/conf/`
5. 启动 Docker 编排
6. 在 `.env` 尚未写入合约地址时自动部署 `KeyEvidence`
7. 若 `.env` 不存在，则自动从 `.env.example` 初始化

停止：

```bash
docker compose down
```

## 检查方式

在 `kms-ops/` 目录执行：

```powershell
./check.ps1
```

## 相关文档

1. `doc/docker-runbook.md`
2. `doc/project_overview.md`
