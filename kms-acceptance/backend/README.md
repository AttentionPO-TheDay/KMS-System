# kms-acceptance backend

轻量验收后端，负责调用 `wrk` 执行压测，并通过 `security/security_test.sh` 执行真实攻击场景。

## 启动

```bash
go mod tidy
go run .
```

## 当前接口

默认监听 `9090`，当前接口包括：

1. `GET /api/health`
2. `GET /api/scenarios`
3. `GET /api/runs`
4. `GET /api/runs/{id}`
5. `POST /api/runs`
6. `GET /api/security/runs`
7. `POST /api/security/runs`
8. `GET /api/proof/runs`
9. `POST /api/proof/runs`

## 环境变量

1. `PORT`：服务端口
2. `WRK_PATH`：`wrk` 可执行文件路径，未配置时会尝试自动发现
3. `ACCEPTANCE_GENERATE_BASE_URL`：生成压测默认基础地址
4. `ACCEPTANCE_LIFECYCLE_BASE_URL`：生命周期压测默认基础地址
5. `ACCEPTANCE_INTERNAL_TOKEN`：内部服务调用 token。
   **无默认值**，必须与 `kms-ops/.env` 中的 `INTERNAL_TOKEN` 一致
   （历史默认值 `kms-generate-internal-secret-2026` 为公开值，已移除）。
   直接调用 Go 入站层的压测还必须携带 `X-Kms-User`，否则会被 401 拒绝。
6. `ACCEPTANCE_GENERATE_KEY_POOL_URL`：生成 Java 内部 key 池查询接口
7. `ACCEPTANCE_LIFECYCLE_VERIFY_URL`：生命周期 Java 最终状态核验接口
8. `ACCEPTANCE_USER`：验收用户，默认 `acceptance_user`
9. `ACCEPTANCE_REVOKE_VERIFY_WAIT_SECONDS`：回收后等待核验秒数，默认 `30`
10. `ACCEPTANCE_KEY_POOL_LOOKBACK_MINUTES`：查询最近生成 key 池的回看窗口分钟数，默认 `120`
11. `ACCEPTANCE_LIFECYCLE_REQUIRED_KEYS`：更新/回收强制使用的 key 池大小，默认按目标 TPS * 时长估算
12. `ACCEPTANCE_GENERATE_JAVA_BASE_URL`：生成 Java 服务基础地址，默认 `http://127.0.0.1:9081`
13. `ACCEPTANCE_LIFECYCLE_JAVA_BASE_URL`：更新回收 Java 服务基础地址，默认 `http://127.0.0.1:9082`
14. `ACCEPTANCE_ATTACK_USER_NAME` / `ACCEPTANCE_ATTACK_USER_PASSWORD`：普通用户攻击账号
15. `ACCEPTANCE_ATTACK_ADMIN_NAME` / `ACCEPTANCE_ATTACK_ADMIN_PASSWORD`：管理员账号
16. `ACCEPTANCE_ATTACK_FOREIGN_USER`：被攻击的 foreign user，默认 `admin`

> 说明：第 15、16 项目前为**未使用的参数**——命令行会解析并转发，
> 但后端没有任何函数读取它们（越权/foreign user 场景在
> `securityCases.js` 中仅有注释形式）。保留是为了兼容既有调用脚本。

## 说明

1. 当前内置 4 个 ready-to-run 场景：生成 TPS、更新 TPS、回收 TPS、回收率
2. 实际默认压测参数以 `main.go` 为准：
   - 生成：`2 threads / 340 connections / 1s`（`TargetTPS` 100000）
   - 更新、回收、回收率：`2 threads / 50 connections / 5s`（`TargetTPS` 5000）
   前端表单初始值为 `12/400/30`。
   （早前本文档写的 `16/2000/60s` 与 `12/800/60s` 与代码不符。）
3. 更新与回收会自动加载最近一次生成压测之后的 key 池，不再使用固定 `keyId`
4. 回收率按最终状态核验，不再依赖 Go 接入层 `/lifecycle/metrics` 的累计计数
5. 安全攻击接口当前可执行生成 3 类攻击与更新/回收 5 类攻击，结果会回填到前端安全卡片
