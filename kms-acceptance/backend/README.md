# kms-acceptance backend

轻量验收后端，负责调用 `wrk` 执行压测、汇总结果并保存测试历史。

## 启动

```bash
go mod tidy
go run .
```

默认监听 `18090`。

## 环境变量

- `PORT`: 服务端口
- `WRK_PATH`: `wrk` 可执行文件路径，未配置时会尝试自动发现

## 说明

- 当前内置 4 个场景：生成 TPS、更新 TPS、回收 TPS、回收率
- 回收率目前按 `kms-updatedel` 的 `/lifecycle/metrics` 计算受理回收率
- 若要切换到最终业务回收率，应在 Java 业务侧补充真实统计接口后修改 `MetricKind`
