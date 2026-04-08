# kms-acceptance front

轻量验收前端，用于配置测试场景、触发后端执行 `wrk`，并查看历史结果。

## 启动

```bash
npm install
npm run dev
```

默认前端端口 `18100`，会将 `/api` 代理到 `http://127.0.0.1:18090`。
