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
2. `kms-updatedel/front`：`/lifecycle-api` -> `http://localhost:9082`
3. `kms-user/front`：`/generate-api` -> `9081`，`/lifecycle-api` -> `9082`，`/distribute-api` -> `8083`

Docker 网关发布环境仍由 `kms-ops/nginx/nginx.conf` 统一处理，不依赖这些本地开发代理。

`nginx` 已开启 Docker DNS 运行时解析，后端容器重建后会自动刷新上游地址，避免网关继续指向旧容器 IP 而出现 `502 Bad Gateway`。

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

## 启动方式

在 `kms-ops/` 目录执行：

```bash
docker compose up -d
```

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
