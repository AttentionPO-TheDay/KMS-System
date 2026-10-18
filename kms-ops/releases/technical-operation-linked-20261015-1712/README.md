# 业务执行阶段联动前端发布

发布范围：updatedel 前端。预分配逐条计数及分批回执、现场分发与预分配取用路径、更新生成/封存/自检/登记/版本对账，全部由现有调用边界驱动。移除静态技术卡片、独立演示按钮及旧说明条。

服务器：expert-machine，项目 /home/rbf/kms-sys。仅重建 Nginx 网关，沿用旧镜像保留其他前端及旧静态资源。不运行迁移、不更新后端、不修改业务数据。

部署前已通过实际页面处理函数隔离测试、真实本地 SM2 生成更新回归、桌面浏览器验证和生产构建。部署脚本校验包摘要、当前镜像与入口摘要；切换失败自动恢复旧网关镜像。

回滚镜像：kms-gateway-nginx:before-technical-operation-linked-20261015-1712。

已部署核验：Nginx 配置检查通过；/updatedel/ 与 /updatedel/demo 返回 HTTP 200，线上入口 SHA256 与本地一致，为 e5a7cab019410576e51b6d149ed85460e26f56fb4c336ecd265cab4a52dc4881。三个业务页面、执行流程组件及主入口共五个 JS 资源线上摘要逐一匹配。六个受检后端/数据库容器 ID 与启动时间未变；原授权页静态资源仍保留。未执行线上预分配、分发或换钥操作，未改变业务数据。

只读复核：在仓库根目录运行 `node kms-ops/releases/technical-operation-linked-20261015-1712/verify-online.mjs`。完整部署输出：`tmp/technical-operation-deploy.log`。
