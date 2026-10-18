# 服务器部署记录

2026-10-14，服务器`expert-machine`，目录`/home/rbf/kms-sys`。

- 更新服务：`dvadmin3-django`、`dvadmin3-key-reclaimer`、`nginx`。
- 迁移：`pqkds.0037_group_key_agreement`执行成功。
- 数据库备份：服务器发布目录内`database-before.sql`，权限600，不上传Git。
- 旧镜像标签：`kms-dvadmin3-django:before-group-agreement-20261014`、`kms-gateway-nginx:before-group-agreement-20261014`。
- 新镜像标签：上述镜像的`group-agreement-20261014`，并同步为`local`。
- 保留服务器Compose、HTTPS证书和访问模板挂载，不改链或数据卷。
- HTTP和HTTPS节点页面、验收页面均返回200，网关ping正常；匿名协商请求返回业务401。前端入口哈希与本次构建一致，上传SHA256校验通过。
- 修复Windows打包静态文件权限导致的403：镜像内目录755、静态文件644。
- 尚未进行生产三节点完整业务联调；需真实节点、两两已确认基础会话及各原设备上的本地密钥。

入口：沿用原服务器地址，节点侧“会话管理 → 多方协商”。

`apply.sh`为单次发布脚本，已有备份时拒绝重跑。仅回退镜像不会删除新增表；无需反向迁移或恢复数据库。
