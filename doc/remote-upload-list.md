# 远端部署：该传什么、怎么起

> 场景：远端服务器**能联网**，不用镜像 tar 那套（`ship.ps1` 的自包含镜像模式）。
> 采用**源码模式**：本地打包 → FTP 上传 → 远端 `docker compose` 构建并启动。

---

## 手工 FTP 逐项清单（不想打 tar 时照这个勾）

路径都相对仓库根。**总上传量约 375 MB**（与 tar 包一致）。

### ① `kms-ops/` —— 整目录上传，但**排除下列条目**

必须带的：

| 条目 | 体积 | 说明 |
|---|---|---|
| `runtime/` | 302 MB | Java jar ×2 + Go 二进制 ×3 —— 镜像构建输入 |
| `fisco/console/` | 51 MB | console 运行容器挂载 + SDK 证书（`conf/`） |
| `front/` | 51 MB | 4 个前端产物 —— nginx 镜像构建输入 |
| `nodes/127.0.0.1/` | 49 MB | 正在跑的 FISCO 链（**只带这个子目录**） |
| `build/` | <1 MB | **6 个 Dockerfile**（曾被 gitignore 吃掉，务必确认在） |
| `mysql/init/`、`mysql/my.cnf` | <1 MB | 建库脚本（含菜单迁移 SQL） |
| `nginx/nginx.conf`、`nginx/snippets/` | <1 MB | 网关配置 |
| `portal/` | <1 MB | 门户落地页 |
| `docker-compose.yml`、`deploy.sh`、`check.ps1` | <1 MB | 编排与部署脚本 |
| `.env` | <1 MB | **含库口令与合约地址/部署私钥，必需** |
| `kms-java-backend/`、`scripts/`、`tests/`、`wrk/`、`README.md`、`*.sh`、`*.ps1` | ~4 MB | 可选（不参与构建，带上便于远端排障） |

**不要传**：

| 条目 | 体积 | 为什么 |
|---|---|---|
| `dist/` | 1.86 GB | 本机打包产物 |
| `kafka/kafka_data/` | 1.63 GB | 运行态消息数据 —— **带过去等于把本机队列搬上生产** |
| `mysql/data/` | 222 MB | 运行态库数据。带了它 MySQL **不会**执行 `init/` 建库脚本（只在空数据目录时执行） |
| `nodes/127.0.0.1.bak.*`、`nodes/127.0.0.1.broken.*` | 194 MB | 历次排障留下的旧链现场 |
| `experiments/` | 24 MB | 本地实验（含 `.venv`） |
| `redis/data/` | 1.5 MB | 运行态缓存 |
| `nginx/logs/`、`dvadmin-logs/` | — | 运行态日志 |
| `fisco/.rebuild/`、`fisco/cert/` | <1 MB | 重建链产物；**CA 私钥只应留在本机** |
| `tests/_probe_out/`、`.omc/` | <1 MB | 本地编译产物 / 本地状态 |

> ⚠️ 最容易犯的错是**整个 `mysql/`、`kafka/`、`redis/` 一起拖过去**。
> 正确做法：`mysql/` 只传 `init/` 与 `my.cnf`；**`kafka/` 与 `redis/` 什么都不用传**
> （Docker 首次启动会自动创建挂载目录）。

### ② `kms-distribute/extracted/ruoyi (2)/` —— **只传 3 项**

| 条目 | 体积 | 说明 |
|---|---|---|
| `backend/` | 9.4 MB | Django 应用本体（含 kyber/falcon 的 C 源码，构建期编译） |
| `requirements.txt` | <1 MB | 该镜像 `pip install` 用它 |
| `docker_env/django/Dockerfile` | <1 MB | 镜像定义 |

**其余全部不要传**：`web/`（**543 MB**）、`ruoyi-ui/`、`.ganache_db/`、
`legacy-merge-backup/`、`logs/`，以及根目录那一堆文档与脚本 ——
该 Dockerfile 只 `COPY requirements.txt` 与 `./backend/`。

> 目录名里有**空格和括号**：FTP 客户端与远端命令都要加引号，
> 例如 `"/opt/kms/kms-distribute/extracted/ruoyi (2)"`。

---

## 一句话回答（推荐做法）

**不要手工挑文件传。** 本地执行一次：

```powershell
pwsh -File kms-ops\ship-source.ps1
```

得到 `kms-ops/dist/kms-source-deploy.tar.gz`（约 **376 MB**、2382 个条目），
**FTP 只传这一个文件**。远端解开后：

```bash
tar -xzf kms-source-deploy.tar.gz -C /opt/kms
cd "/opt/kms/kms-ops"
bash deploy.sh check      # 先检查：漏传、凭据、架构、端口
bash deploy.sh build      # 构建 7 个应用镜像（基础镜像自动拉）
bash deploy.sh up         # 启动
bash deploy.sh verify     # HTTP 健康检查
```

`docker compose up -d --build` 等价于 build + up，也可以一步到位。

---

## 为什么不能"只传源码"

镜像里 `COPY` 的**不是源码，而是本地构建产物**：

| 必须随包带上 | 是什么 | 平时的状态 |
|---|---|---|
| `kms-ops/runtime/` | Java jar ×2、Go 二进制 ×3（302 MB） | 被 `.gitignore` 排除 |
| `kms-ops/front/` | 4 个前端产物（51 MB） | 被 `.gitignore` 排除 |
| `kms-ops/build/` | **6 个 Dockerfile** | ⚠️ 长期被 `.gitignore` 的通用 `build/` 规则排除，**从未进入版本库** |
| `kms-ops/nodes/127.0.0.1/` | 正在跑的 FISCO 链（45 MB） | 被 `.gitignore` 排除 |
| `kms-ops/.env` | 库口令、内部令牌、**合约地址与部署私钥** | 被 `.gitignore` 排除 |
| `kms-ops/fisco/console/conf/*.crt\|*.key\|config.toml` | SDK 证书（打进 Java 镜像 + console 挂载） | 被 `.gitignore` 排除 |
| `kms-distribute/extracted/ruoyi (2)/` | Django 镜像的构建上下文 | 受版本管理 |

> 那张表里"被 gitignore 排除"的几项就是**用 git 方式部署必然失败**的原因，
> 也是 FTP 手工挑选时最容易漏的东西。`kms-ops/build/` 那条是本次才发现的
> （`.gitignore` 里一条通用的 `build/` 把 Dockerfile 目录一并吃掉了），已修。

`ship-source.ps1` 已把这些全部带上，因此**远端不需要 JDK / Maven / Node / Go**。

---

## 包里刻意不带的东西

| 不带 | 原因 |
|---|---|
| `mysql/data`、`redis/data`、`kafka/kafka_data`、`nginx/logs`、`dvadmin-logs` | 运行态数据。远端首次启动自动创建；建库脚本在 `mysql/init/`。**带过去反而会把本机数据搬上生产** |
| `nodes/*.bak.*`、`nodes/*.broken.*` | 历次排障留下的旧链现场，合计 194 MB，与部署无关 |
| `fisco/cert/` | CA 私钥，只应留在本机 |
| `kms-distribute/.../web/` | **543 MB**，而该镜像只 COPY `requirements.txt` 与 `./backend/` |
| `experiments/`、`tests/_probe_out/`、`dist/` | 本地实验与缓存 |

---

## 远端要求

- Docker + `docker compose` 插件；能访问镜像仓库、apt 与 pypi（Django 镜像构建期要 `apt-get` / `pip install`）
- **镜像源**：目标机若直连 Docker Hub 超时（典型报错
  `failed to resolve source metadata for docker.io/library/nginx:alpine … i/o timeout`），
  需在 `/etc/docker/daemon.json` 配 `registry-mirrors` 后 `systemctl restart docker`。
  实测（2026-09-24）远端就是靠切镜像源才拉到镜像的 —— 这一条不是"可选优化"，是前提。
  验证：`docker pull nginx:alpine`。

  构建共需 **7 个公共基础镜像**（只看 compose 的 `image:` 会漏掉后两个）：

  | 来源 | 镜像 |
  |---|---|
  | Dockerfile 的 `FROM` | `debian:bookworm-slim`、`eclipse-temurin:8-jre`、`nginx:alpine` |
  | compose 直接引用 | `mysql:8.0`、`redis:6.2`、`apache/kafka:latest`、`ubuntu:22.04` |

  远端自查（与 `deploy.sh check` 同一份清单）：
  ```bash
  for i in debian:bookworm-slim eclipse-temurin:8-jre nginx:alpine \
           mysql:8.0 redis:6.2 apache/kafka:latest ubuntu:22.04; do
    docker image inspect "$i" >/dev/null 2>&1 && echo "ok   $i" || echo "缺   $i"
  done
  ```
  若某台目标机**确实拉不到**（内网/离线），再从本机 `ship-source.ps1 -WithBaseImages`
  导出 `kms-base-images.tar` 带过去 `docker load` —— 镜像源可用时这一步是多余的。
- 架构不限：源码模式在远端构建镜像，amd64 / arm64 都行
  （镜像模式则要求 amd64 —— 那是 `ship.ps1` 那条路的限制）
- 空闲端口：**对外只需要 `80`**（网关）。另外这些只绑回环、同样不能与他人冲突：
  `3307`(MySQL) `6379`(Redis) `9092`(Kafka) `8545~8548`(链 RPC) `20200~20203`(链 channel)。
  `8081/8082/9081/9082/8001` **不再发布到宿主机**（2026-09-24 起）——
  网关与验收容器都按服务名在 Docker 内网访问，部署环境不需要腾出这些端口。
  本机调试要用它们时加覆盖文件：
  `docker compose -f docker-compose.yml -f docker-compose.debug-ports.yml up -d`

## 上线前必须处理

1. **轮换 `.env` 里的开发占位口令**：`MYSQL_ROOT_PASSWORD`、`KMS_TOKEN_SECRET`、
   `INTERNAL_TOKEN`、`DRUID_LOGIN_USERNAME/PASSWORD`、`KGC_MASTER_SECRET`。
2. **不要动** `FISCO_CONTRACT_ADDRESS` 与 `FISCO_PRIVATE_KEY`：它们与包内这条链上
   已部署的 KeyEvidence 合约绑定，改了上链立刻失败（合约是 `onlyOwner`）。
3. `KMS_CAPTCHA_ENABLED=true` 表示登录需要图形验证码（当前值，两端一致）。

---

## 两种模式的取舍

| | 源码模式（本文） | 镜像模式（`ship.ps1`） |
|---|---|---|
| 传输体积 | **376 MB** | 1.27 GB + 158 MB |
| 远端需要 | Docker + 联网 | Docker（可离线） |
| 架构限制 | 无 | 仅 amd64 |
| 适合 | 能联网、想少传、跨架构 | 内网/离线、要求"传完即起" |

> 顺带一提：`kms-ops/dist/` 里若还留着 `kms-images.tar`（1.27 GB）等镜像模式产物，
> 走源码模式后可以删掉，省 1.4 GB 磁盘。
