# KMS 生命周期系统前端

生命周期系统管理员前端，基于 Vue3 + Element Plus 构建。

## 当前定位

1. 作为生命周期系统管理员后台入口
2. 保留更新、回收、自动更新、权限审批和系统管理能力
3. 普通用户主入口已经迁移到 `kms-user`

## 当前主要路由

1. `/login`
2. `/index`
3. `/updatedel/keyupdate`
4. `/updatedel/keydelete`
5. `/updatedel/keyautoupdate`
6. `/updatedel/keyautoupdate/user`
7. `/permission/request/index`
8. `/user/profile`

## 开发配置

1. Vite 开发端口：`81`
2. 开发环境 `VITE_APP_BASE_API='/lifecycle-api'`
3. 当前 `vite.config.js` 仅内置 `/dev-api -> http://localhost:80` 代理

## 说明

1. 页面代码按 `/lifecycle-api` 作为业务 API 前缀
2. 如果本地直接启动前端而不经过网关，需要自行补齐对应代理，或通过统一网关联调
3. 生产构建基路径为 `/updatedel/`

## 功能模块

1. 密钥更新
2. 密钥回收
3. 密钥自动更新
4. 权限审批与回退

## 开发

```bash
npm install
npm run dev
npm run build:prod
```
