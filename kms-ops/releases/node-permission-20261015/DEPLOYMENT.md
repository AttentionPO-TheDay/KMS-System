# 节点权限入口与现场分发提示修复

新增、编辑节点可设置 L1/L2/L3；节点列表展示等级。现场分发等级不足返回独立业务错误码，保留身份映射和通信授权检查。

基于发布前线上镜像增量构建，仅替换 Django 的 api_contract.py、node_self_views.py 以及 updatedel 前端。无数据库迁移，不调整节点等级，不生成或删除业务材料。旧静态资源保留，切换失败自动回滚。

发布后：管理员 Ctrl+F5，在「节点管理 → 编辑 → 权限等级」选择 L2（生成、分发）或 L3（再包含更新、回收），保存后让节点重试。不要清除浏览器站点数据，本机私钥保存在浏览器中。

## 回滚

```bash
docker tag kms-dvadmin3-django:before-node-permission-20261015 kms-dvadmin3-django:local
docker tag kms-gateway-nginx:before-node-permission-20261015 kms-gateway-nginx:local
docker compose -p kms-ops -f /home/rbf/kms-sys/docker-compose.yml -f /home/rbf/kms-sys/docker-compose.fisco-enabled.yml --profile fabric-did up -d --no-deps --no-build --force-recreate dvadmin3-django nginx
```
