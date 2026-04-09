# kms-acceptance backend

轻量验收后端，负责调用 `wrk` 执行压测、汇总结果并保存测试历史。

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

## 环境变量

1. `PORT`：服务端口
2. `WRK_PATH`：`wrk` 可执行文件路径，未配置时会尝试自动发现
3. `ACCEPTANCE_GENERATE_BASE_URL`：生成压测默认基础地址
4. `ACCEPTANCE_LIFECYCLE_BASE_URL`：生命周期压测默认基础地址

## 说明

1. 当前内置 4 个场景：生成 TPS、更新 TPS、回收 TPS、回收率
2. 回收率目前按 `kms-updatedel` 的 `/lifecycle/metrics` 计算受理回收率
3. 若要切换到最终业务回收率，应在 Java 业务侧补充真实统计接口后再调整逻辑
