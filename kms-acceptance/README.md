# kms-acceptance

KMS 验收与压测系统。

## 当前定位

用于统一执行压测、记录结果，并辅助判断当前系统是否达到阶段性验收标准。

## 当前目录

1. `front/`：验收前端，负责配置测试、触发测试、查看历史结果
2. `backend/`：Go 后端，负责执行 `wrk`、解析输出、保存测试记录

## 当前内置验收项

1. 密钥生成 TPS
2. 密钥更新 TPS
3. 密钥回收 TPS
4. 密钥回收率
5. 生成系统 3 类真实攻击
6. 更新与回收系统 5 类真实攻击

## 当前接口口径

后端默认监听 `9090`，当前接口包括：

1. `GET /api/health`
2. `GET /api/scenarios`
3. `GET /api/runs`
4. `GET /api/runs/{id}`
5. `POST /api/runs`

## 当前口径说明

1. 前端开发环境默认将 `/acceptance-api` 代理到 `http://127.0.0.1:9090`
2. 网关部署环境通过 `/acceptance-api/` 转发到验收后端
3. 生成、更新、回收场景默认直接压 Go 接口，并统一携带 `X-Internal-Token`
4. 更新与回收默认复用生成系统最新产生的 key 池，不再使用固定 `keyId`
5. 回收率当前按生命周期 Java 内部接口核验最终 `status=3` 计算
6. 安全区现在不是静态展示，前端可直接触发真实攻击并查看请求明细

## 参考文档

1. `kms-acceptance/front/README.md`
2. `kms-acceptance/backend/README.md`
3. `doc/project_overview.md`
