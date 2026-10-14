# 域管理与预分配池图标部署

本包更新 `updatedel-java` 和 `nginx`。不覆盖服务器 .env、Compose、FISCO overlay、TLS、数据卷，不启动生成/更新/回收测试。

## Windows 上传

```powershell
cd C:\Users\AllenR\Desktop\kms-code\kms-ops\releases\domain-management-20261014
scp kms-domain-management-images.tar.gz SHA256SUMS-domain-management 55_restore_domain_management.sql apply-domain-management.sh README-domain-management.md expert-machine:/home/rbf/kms-sys/
ssh expert-machine
```

## 服务器执行

```bash
cd /home/rbf/kms-sys
sha256sum -c SHA256SUMS-domain-management
sudo bash apply-domain-management.sh
```

脚本会先校验文件与数据库连接、备份相关菜单行、给旧镜像打回滚标签，随后加载新镜像、执行幂等菜单 SQL，只重建 `updatedel-java` 与 `nginx`。任何一步失败立即停止。它不删除数据库、节点或密钥，不执行 compose down。

菜单 SQL 恢复管理员的 9461 域管理入口和 9482 图标。已有数据库不会自动运行 init 目录的新脚本，因此必须执行本包脚本。

Java 启动就绪后：

```bash
sudo bash deploy.sh verify
sudo docker compose -f docker-compose.yml -f docker-compose.fisco-enabled.yml --profile fabric-did ps updatedel-java nginx
```

浏览器 Ctrl+F5，退出演示身份再进入管理员视图，以重新加载菜单。检查预分配池图标和“节点管理 → 域管理”。节点归属只在你明确点击保存后调整。已有节点域变更不会改变历史分发快照。

## 与上一个工作台包的关系

网关包含最新工作台和域管理前端；本包不包含 Django 镜像。若 `node-workbench-20261014` 尚未部署，请先按其说明部署 Django/网关，再执行本包；不要随后再加载旧网关覆盖本包。

## 回滚

记录更新脚本输出的 `before-domain-时间戳`。将两个旧镜像重新 tag 为 `:local`，再用同样 Compose 参数只重建 `updatedel-java nginx`。菜单快照在服务器 `domain-management-backup-时间戳/menu-rows.sql`；它可能包含角色信息，权限为 600，勿公开上传。SQL 是幂等、非破坏性菜单变更，通常回滚镜像即可。

本包已通过管理员 Java 菜单投影测试、前端生产构建、隔离浏览器验证、域分类与历史快照测试，以及压缩镜像包加载验证。尚未自动上传或部署到服务器。
