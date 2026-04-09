# Docker Runbook

## 当前目标

让 `kms-ops/docker-compose.yml` 采用“先本地编译，再容器运行”的方式启动当前有效服务。

## 当前包含的服务

1. `mysql`：共享数据库，端口 `3306`
2. `redis`：共享缓存，端口 `6379`
3. `kafka`：共享消息队列，端口 `9092`
4. `fisco-node`：区块链节点
5. `generate-go`：生成接入层，端口 `8081`
6. `generate-java`：生成业务层，端口 `9081`
7. `updatedel-go`：生命周期接入层，端口 `8082`
8. `updatedel-java`：生命周期业务层，端口 `9082`
9. `kms-distribute`：分发业务层，端口 `8083`
10. `acceptance-backend`：验收后端，端口 `9090`
11. `nginx`：网关，端口 `80`

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

## 网关路径

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
2. `kms-user` 和 `kms-acceptance/front` 当前作为静态前端产物由 `nginx` 提供。
3. `legacy-kms/` 仍然保留为历史参考，不参与当前 Docker 编排。
4. 旧版编排文件如 `docker-compose-before.yml` 仅作历史对照，不代表当前部署方式。
