# kms-acceptance

KMS 验收与压测系统。

## 当前定位

Demo 管理端唯一的验收入口。页面只展示八项验收结论，普通环境不再作为验收入口。

## 当前目录

1. `front/`：验收矩阵，触发性能/攻击用例，录入节点侧预分配证据
2. `backend/`：Go 后端，负责执行 `wrk`、安全用例、阈值判断和证据持久化

## 当前内置验收项

1. 无证书密钥生成速率 > 100000 TPS（SSCL 最快路径）
2. 预分配密钥速率 > 50 条/秒（节点侧 SM4 + Kyber + Falcon）
3. 密钥更新速率 ≥ 5000 TPS
4. 异常密钥回收速率 ≥ 5000 TPS
5. 密钥最终回收率 > 98%
6. 密钥生成攻击防御 ≥ 3 类
7. 量子威胁模拟防御 ≥ 3 类
8. 网络攻击防御 ≥ 5 类

## 当前接口口径

后端默认监听 `9090`，当前接口包括：

1. `GET /api/health`
2. `GET /api/scenarios`
3. `GET /api/runs`
4. `GET /api/runs/{id}`
5. `POST /api/runs`
6. `GET /api/security/runs`
7. `POST /api/security/runs`
8. `GET /api/proof/runs`
9. `POST /api/proof/runs`
10. `GET /api/acceptance/criteria`
11. `GET /api/acceptance/evidence`
12. `POST /api/acceptance/evidence`

## 当前口径说明

1. 前端开发环境默认将 `/acceptance-api` 代理到 `http://127.0.0.1:9090`
2. 网关部署环境通过 `/acceptance-api/` 转发到验收后端
3. 生成、更新、回收场景默认直接压 Go 接口，并统一携带 `X-Internal-Token`
4. 更新与回收默认复用生成系统最新产生的 key 池，不再使用固定 `keyId`
5. 更新完成率按生命周期 Java 内部接口核验最终 `chainStatus=1`，回收率按最终 `status=3` 计算
6. 预分配证据由节点侧产生，管理端只保存吞吐值、时间和证据说明，不接触节点私钥
7. 量子项目是协议层威胁模拟，不宣称真实量子计算机实测

## 参考文档

1. `kms-acceptance/front/README.md`
2. `kms-acceptance/backend/README.md`
3. `doc/project_overview.md`
