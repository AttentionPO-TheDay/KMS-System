# Falcon 状态及预分配发送方材料修复

仅更新 Django 的五个 Python 文件及 updatedel 前端，不进行数据库迁移。
镜像基于当前线上版本增量构建，旧前端资源保留，切换失败自动回滚两项应用。

验证包括隔离 SQLite 测试、源文件摘要、HTTPS 入口摘要、后端鉴权响应及真实节点的 Falcon 状态只读检查。

发布后各节点浏览器 Ctrl+F5。不要清除站点数据。
旧预分配批次没有保存发送方 K 的副本，不能恢复；请在原节点浏览器重新预分配，再建立新会话。
新批次的发送方副本仅在本机加密保存，服务端不返回明文密钥。

回滚（服务器）：

```bash
docker tag kms-dvadmin3-django:before-pool-sender-falcon-20261015-1807 kms-dvadmin3-django:local
docker tag kms-gateway-nginx:before-pool-sender-falcon-20261015-1807 kms-gateway-nginx:local
docker compose -p kms-ops -f /home/rbf/kms-sys/docker-compose.yml -f /home/rbf/kms-sys/docker-compose.fisco-enabled.yml --profile fabric-did up -d --no-deps --no-build --force-recreate dvadmin3-django nginx
```
