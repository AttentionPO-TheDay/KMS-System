# KMS（密钥管理系统）项目整体概览（历史版）

> 本文档描述的是拆分前的混合架构，用于历史追溯和迁移参考。
> 当前开发请优先参考：`doc/project_overview.md`、`doc/kms-split-implementation-plan.md`、`kms-generate/README.md`、`kms-updatedel/README.md`。
> 仓库中的旧目录已重命名为 `legacy-kms/` 和 `legacy-kms-go/`。

## 项目简介

这是一个基于国密算法的**密钥管理系统（Key Management System，KMS）**，采用前后端分离 + 区块链存证的多层架构，主要用于密钥的全生命周期管理（生成、更新、回收），并将关键操作上链存证（FISCO BCOS）。

---

## 仓库结构一览

```
kms-code/
├── legacy-kms/      ← 历史 Java 后端（若依框架 + 自定义业务模块）
├── legacy-kms-go/   ← 历史 Go 前置服务（密钥生成 + Kafka 转发）
├── kms-ops/         ← 运维部署配置（Docker Compose + 各组件挂载）
├── kmsops存档/       ← 存档文件（FISCO 节点、jmeter、wrk 压测工具）
└── kms-ops.tar      ← 整体运维目录的归档包（~1.1GB）
```

---

## 各子项目详解

### 1. `legacy-kms/` — 历史 Java 后端（主业务服务）

**技术栈**：Spring Boot 2.5.15 + RuoYi 3.8.8 + MyBatis + Redis + Kafka + FISCO BCOS Java SDK

**Maven 多模块结构**：

| 模块 | 说明 |
|------|------|
| `ruoyi-admin` | 启动入口 + 所有自定义业务的 Controller/Service/Domain |
| `ruoyi-system` | 系统管理模块（用户/角色/菜单等若依标准功能） + 权限申请模块 |
| `ruoyi-framework` | 安全框架、过滤器、缓存配置等基础设施 |
| `ruoyi-common` | 通用工具类、注解、基础 Domain |
| `ruoyi-quartz` | 定时任务（用于权限到期自动回收） |
| `ruoyi-generator` | 代码生成器（若依标准模块） |

**自定义核心业务模块**（位于 `ruoyi-admin`）：

- **`keymanage`** — 密钥管理核心
  - `KeymanageController` — 密钥查询/管理 REST API
  - `RequestController` — 接收 Go 服务的密钥操作请求（Enroll/Update/Revoke）
  - `KeyEvidence` — FISCO BCOS 智能合约 Java 绑定（密钥存证）
  - `FiscoBcosService` — 区块链存证服务
  - `KafkaConsumer` / `ChainConsumer` — Kafka 消息消费者（处理密钥操作请求）
  - `Sm2CalculationService` — 国密 SM2 运算服务
  - `ECCGenerator` / `SSCLGenerator` — 密钥生成器（ECC + 国密）
  - `Requestor` / `RequestConsumer` — 异步请求处理

- **`keyuser`** — 密钥用户管理
  - `KeyUserController` / `KeyUserServiceImpl` — 密钥用户 CRUD

- **`permission`** — 权限申请流程
  - `PermissionRequestController` — 权限申请审批 API
  - `IPermissionRequestService` / `PermissionRequestServiceImpl` — 业务逻辑
  - `PermissionRevokeTask` — 定时任务：权限到期自动回收

**数据库初始化脚本**（`legacy-kms/sql/`）：

| 脚本 | 说明 |
|------|------|
| `1.sql` | 若依基础表结构 |
| `2.sql` | 若依基础数据（菜单/字典等） |
| `3.sql` | KMS 业务表（密钥表、用户表等） |
| `4.sql` | 密钥领域/用户数据初始化 |
| `5.sql` | 权限申请相关表 |
| `6~8.sql` | 权限菜单扩展 |

---

### 2. `legacy-kms-go/` — 历史 Go 高性能前置服务

**技术栈**：Go 1.25.5 + Fiber v2（高性能HTTP框架）+ Kafka（IBM/sarama）+ 国密 SM2（tjfoc/gmsm）+ Sonic（快速JSON）

**目录结构**：

| 目录/文件 | 说明 |
|-----------|------|
| `cmd/` | 程序入口（main.go） |
| `config/` | 配置加载 |
| `controllers/request_controller.go` | HTTP 接口层：EnrollKey / UpdateKey / RevokeKey / ReenrollKey |
| `service/key_service.go` | 业务逻辑：密钥生成（SM2/ECC 本地计算）+ Kafka 消息发送 |
| `service/generator/` | 密钥生成算法实现 |
| `models/keymanage.go` | 数据模型 |
| `utils/` | 工具函数 |
| `key-service-v1` | 编译产物（二进制可执行文件） |

**核心职责**：
- 接收外部密钥操作 HTTP 请求（Enroll/Update/Revoke）
- **EnrollKey**：本地使用国密 SM2 算法生成密钥，通过 Kafka 发送给 Java 后端持久化、存证
- **UpdateKey / RevokeKey**：轻量级转发，直接通过 Kafka 发消息，Java 后端处理实际逻辑
- 利用 Fiber 高并发能力作为入口网关，减轻 Java 端压力

---

### 3. `kms-ops/` — 运维部署配置

**技术栈**：Docker + Docker Compose + Nginx + Kafka + MySQL + FISCO BCOS

**目录结构**：

| 目录 | 说明 |
|------|------|
| `front/` | Vue3 前端静态资源 |
| `kms-java-backend/` | Java 后端程序（ruoyi-admin.jar + 配置文件） |
| `kms-go-backend/` | Go 服务程序 |
| `fisco/` | FISCO BCOS 区块链节点 + WeBASE-Front + 智能合约 |
| `kafka/` | Kafka + ZooKeeper 数据目录 |
| `mysql/` | MySQL 数据目录 + 初始化脚本 |
| `nginx/` | Nginx 配置（反向代理） |
| `wrk/` | wrk 压测工具 |
| `scripts/init-FBchain.sh` | FISCO 链初始化脚本 |
| `docker-compose.yml` | 完整部署编排文件 |

---

### 4. `kmsops存档/` — 历史存档

| 内容 | 说明 |
|------|------|
| `fisco-v0/` | 早期 FISCO 节点配置存档 |
| `fisco.tar` | FISCO 节点完整打包（~470MB） |
| `jmeter.zip` | JMeter 压测工具（~185MB） |
| `wrk.zip` | wrk 压测工具（~230MB） |

> ⚠️ 这些大型归档文件仅为存档用途，不参与日常开发，可考虑移出版本管理。

---

## 系统整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端（Vue3 + RuoYi Vue3）                  │
│                     由 Nginx 反向代理提供服务                      │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP
            ┌──────────────▼──────────────┐
            │    Go 前置服务（Fiber）        │  ← 密钥生成（SM2/ECC）
            │    /enroll /update /revoke   │
            └──────────────┬──────────────┘
                           │ Kafka 消息
            ┌──────────────▼──────────────┐
            │    Java 后端（Spring Boot）   │  ← 业务逻辑、持久化、权限管理
            │    RuoYi + 自定义 KMS 模块    │
            └──────┬───────────┬──────────┘
                   │           │
          ┌────────▼──┐   ┌────▼────────────┐
          │  MySQL    │   │  FISCO BCOS 链   │  ← 密钥存证（不可篡改）
          │  Redis    │   │  WeBASE-Front    │
          └───────────┘   └─────────────────┘
```

---

## 关键技术点

| 技术点 | 实现方式 |
|--------|---------|
| 密钥生成 | Go 本地使用 SM2（国密）/ ECC 算法计算，速度快 |
| 异步解耦 | Go → Kafka → Java，削峰填谷 |
| 区块链存证 | Java SDK 调用 FISCO BCOS 节点，关键操作上链 |
| 权限管理 | 若依标准 RBAC + 自定义权限申请/审批/自动回收流程 |
| 身份认证 | JWT Token + Spring Security |
| 定时任务 | Quartz 调度 `PermissionRevokeTask` 自动过期回收 |
| 前端 | RuoYi-Vue3（Vue3 + Element Plus） |

---

## 开发/部署说明

1. **数据库初始化**：按顺序执行 `legacy-kms/sql/1.sql` → `5.sql`（共5个）
2. **区块链环境**：使用 `kms-ops/fisco/build_chain.sh` 搭建 FISCO 节点
3. **完整部署**：使用 `kms-ops/docker-compose.yml` 一键启动所有服务
4. **参考文档**：`legacy-kms/doc/若依环境使用手册.docx`
