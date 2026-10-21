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
5. `ACCEPTANCE_INTERNAL_TOKEN`（或 `INTERNAL_TOKEN`）：内部服务调用 token。
   **无默认值**，必须与 `kms-ops/.env` 中的 `INTERNAL_TOKEN` 一致
   （历史默认值 `kms-generate-internal-secret-2026` 为公开值，已移除）。
   直接调用 Go 入站层的压测还必须携带 `X-Kms-User`，否则会被 401 拒绝。
6. `ACCEPTANCE_GENERATE_KEY_POOL_URL`：生成 Java 内部 key 池查询接口
7. `ACCEPTANCE_LIFECYCLE_VERIFY_URL`：生命周期 Java 最终状态核验接口
8. `ACCEPTANCE_USER`：验收用户，默认 `acceptance_user`
9. `ACCEPTANCE_REVOKE_VERIFY_WAIT_SECONDS`：回收后等待核验秒数，默认 `30`
10. `ACCEPTANCE_KEY_POOL_LOOKBACK_MINUTES`：查询最近生成 key 池的回看窗口分钟数，默认 `120`
11. `ACCEPTANCE_LIFECYCLE_REQUIRED_KEYS`：旧版轮换压测取池参数；当前更新场景固定使用 6000 把，不受该参数影响
12. `ACCEPTANCE_UPDATE_VERIFY_ENABLED`：保留的旧版链状态核验配置；当前固定数量更新始终逐钥核验版本实际变化
13. `ACCEPTANCE_UPDATE_VERIFY_TARGET`：更新最终完成率阈值，默认 `98`（百分比）
14. `ACCEPTANCE_GENERATE_JAVA_BASE_URL`：生成 Java 服务基础地址，默认 `http://127.0.0.1:9081`
15. `ACCEPTANCE_LIFECYCLE_JAVA_BASE_URL`：更新回收 Java 服务基础地址，默认 `http://127.0.0.1:9082`
16. `ACCEPTANCE_ATTACK_USER_NAME` / `ACCEPTANCE_ATTACK_USER_PASSWORD`：普通用户攻击账号
17. `ACCEPTANCE_ATTACK_ADMIN_NAME` / `ACCEPTANCE_ATTACK_ADMIN_PASSWORD`：管理员账号
18. `ACCEPTANCE_ATTACK_FOREIGN_USER`：被攻击的 foreign user，默认 `admin`
19. `ACCEPTANCE_ABNORMAL_REVOCATION_URL`：隔离异常样本检测与自动回收内部接口，
    Compose 指向 Django 的 `/api/pqkds/internal/acceptance/abnormal-revocation/`。
    `revoke-tps` 不再依赖 wrk 或生成池，按实际异常回收数量和扫描时间计速，且强制核验对照和依赖失效。

> 说明：第 17、18 项目前为**未使用的参数**——命令行会解析并转发，
> 但后端没有任何函数读取它们（越权/foreign user 场景在
> `securityCases.js` 中仅有注释形式）。保留是为了兼容既有调用脚本。

## 说明

1. 当前内置 4 个 ready-to-run 场景：生成 TPS、更新 TPS、回收 TPS、回收率
2. 实际默认压测参数以 `main.go` 为准：
   - 生成：`2 threads / 340 connections / 1s`（`TargetTPS` 100000）
   - 更新：固定 6000 把不同的已有 SM2 验收密钥，每把提交一次，默认 50 个并发请求，不使用 wrk 或固定 5 秒窗口（`TargetTPS` 5000）。最多等待 60 秒核验数据库版本递增及材料指纹变化；排队、查询计入速率，上链由持久化任务异步处理。
   - 异常回收速率、回收率：各自构造 6000 把隔离异常样本和 4 把对照，调用生产扫描器，无需 wrk，每批最多 5000 条。
   前端表单初始值为 `12/400/30`。
   （早前本文档写的 `16/2000/60s` 与 `12/800/60s` 与代码不符。）
3. 更新加载最新 6000 把有效 SM2 验收密钥，数量不足明确报错；SSCL 生成压测的时间窗口不限制独立的 SM2 更新池。异常回收速率与回收率不依赖生成压测。
4. 异常回收率 = 最终回收成功数 / 实际发起回收密钥数，要求 ≥98%，允许实测 100%；实际发起数来自扫描候选集并按密钥去重，失败计入分母，未发起单独展示。正常及仅告警对照排除，误回收或关联失效不完整均不得通过。速率独立验收，不按速率或固定秒数截断。
5. 安全攻击接口当前可执行生成 3 类攻击、更新/回收 5 类攻击和量子模拟 3 类攻击，结果会回填到前端安全卡片
