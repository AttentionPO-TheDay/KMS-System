# KMS Generate Front

> **已退役**：本前端不再构建、也不再由网关提供（`/generate/` 现返回 404），详见 [RETIRED.md](./RETIRED.md)；下方内容仅作历史存档。

密钥生成系统管理员前端，基于 RuoYi-Vue3 构建。

## 当前定位

1. 作为生成系统管理员后台入口
2. 保留算法图解与演示、生成记录、公共参数、权限审批、系统管理等能力
3. 普通用户主入口已经迁移到 `kms-user`

## 当前主要路由

1. `/login`
2. `/register`
3. `/index`
4. `/algorithm-demo`
5. `/generate/keygenerate/index`
6. `/generate/history/index`
7. `/generate/commonparam/index`
8. `/query/key-list`
9. `/query/public-keys`
10. `/query/blockchain`
11. `/query/key-users`
12. `/permission/request/index`
13. `/userKeys`
14. `/publickeys`
15. `/user/profile`

## 开发配置

1. Vite 开发端口：`82`
   （此前为 `81`，与 `kms-user`、`kms-updatedel` 冲突导致三者无法同时启动；
   现分配为 kms-user 81 / kms-generate 82 / kms-updatedel 83 / kms-acceptance 5176）
2. 开发环境 `VITE_APP_BASE_API='/generate-api'`
3. 当前 `vite.config.js` 内置 `/generate-api -> http://localhost:9081` 代理
4. `vite.config.js` 内含 `@tokens` 别名，指向仓库根目录 `design-tokens/`（共享设计令牌）

## 说明

1. 页面代码按 `/generate-api` 作为业务 API 前缀
2. 管理员端算法说明已经合并为统一的 `/algorithm-demo` 页面
3. 本地直接启动前端时会直接转发到生成系统 Java 后端 `9081`
4. 生产构建基路径为 `/generate/`

## 启动和构建

```bash
npm install
npm run dev
npm run build:prod
```
