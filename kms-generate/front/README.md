# KMS Generate Front

密钥生成系统管理员前端，基于 RuoYi-Vue3 构建。

## 当前定位

1. 作为生成系统管理员后台入口
2. 保留生成记录、公共参数、权限审批、系统管理等能力
3. 普通用户主入口已经迁移到 `kms-user`

## 当前主要路由

1. `/login`
2. `/register`
3. `/index`
4. `/generate/keygenerate/index`
5. `/generate/history/index`
6. `/generate/commonparam/index`
7. `/permission/request/index`
8. `/userKeys`
9. `/publickeys`
10. `/user/profile`

## 开发配置

1. Vite 开发端口：`81`
2. 开发环境 `VITE_APP_BASE_API='/generate-api'`
3. 当前 `vite.config.js` 仅内置 `/dev-api -> http://localhost:80` 代理

## 说明

1. 页面代码按 `/generate-api` 作为业务 API 前缀
2. 如果本地直接启动前端而不经过网关，需要自行补齐对应代理，或通过统一网关联调
3. 生产构建基路径为 `/generate/`

## 启动和构建

```bash
npm install
npm run dev
npm run build:prod
```
