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
