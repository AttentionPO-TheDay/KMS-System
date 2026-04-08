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
10. `nginx`：网关，端口 `80`

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
./build-local.ps1
```

脚本位置：`kms-ops/build-local.ps1`

它会完成：

1. 构建 `kms-generate/java-backend`
2. 构建 `kms-updatedel/java-backend`
3. 构建 `kms-distribute/java-backend`
4. 交叉编译 `kms-generate/go-backend` 为 Linux 二进制
5. 交叉编译 `kms-updatedel/go-backend` 为 Linux 二进制

手工命令如下。

### Java

```powershell
mvn -DskipTests package
```

分别在以下目录执行：

1. `kms-generate/java-backend`
2. `kms-updatedel/java-backend`
3. `kms-distribute/java-backend`

### Go

在各自目录执行：

```powershell
$env:GOOS = "linux"
$env:GOARCH = "amd64"
$env:CGO_ENABLED = "0"
go build -o dist/key-service ./cmd/main.go
```

目录如下：

1. `kms-generate/go-backend`
2. `kms-updatedel/go-backend`

## 启动方式

在 `kms-ops/` 目录执行：

```bash
docker compose up
```

后台启动：

```bash
docker compose up -d
```

停止：

```bash
docker compose down
```

## 首次排查顺序

1. `docker compose ps`
2. `docker compose logs mysql`
3. `docker compose logs generate-java`
4. `docker compose logs updatedel-java`
5. `docker compose logs kms-distribute`

## 说明

1. `docker-compose.yml` 当前直接消费本地构建产物，不再在容器内执行 Maven 或 Go 编译。
2. 2 个 Go 服务必须产出 Linux 可执行文件，输出位置固定为 `dist/key-service`。
3. 3 个 Java 服务 jar 名已改为各自独立名称，避免都叫 `ruoyi-admin.jar`。
4. Java 配置已统一改为优先读取环境变量，默认值与 Docker 编排一致。
5. `legacy-kms/` 仍然保留为历史参考，不参与当前 Docker 编排。
