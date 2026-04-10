# kms-acceptance front

轻量验收前端，用于配置测试场景、触发后端执行 `wrk`，并查看历史结果。

## 启动

```bash
npm install
npm run dev
```

## 当前配置

1. 默认前端端口：`5176`
2. 开发环境将 `/acceptance-api` 代理到 `http://127.0.0.1:9090`
3. 生产构建基路径为 `/acceptance/`
4. 页面默认展示后端下发的 ready-to-run 场景：生成 10 万 TPS、更新 5000 TPS、回收 5000 TPS、回收率核验
