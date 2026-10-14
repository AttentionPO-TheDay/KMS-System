# 管理端密钥数据四页优化

仅更新 `kms-dvadmin3-django:local` 和 `kms-gateway-nginx:local`。
不上传源码、.env、私钥、证书或数据，不覆盖服务器 Compose、FISCO 配置或链数据；保留上一轮 Java 交易哈希修复。

## 更新内容

- 密钥总览、预分配池、会话数据、分发批次统一紧凑布局：全量统计、筛选、真实后端分页、展开详情。
- 密钥总览默认显示有效节点密钥，可切换历史版本；展示已保存的上链核验状态、交易哈希、区块高度，不发起链写入。
- 独立验收压测记录页签，只读取 `kms.keymanage` 中验收账户且 `key_domain=acceptance` 的记录，不混入节点长期密钥统计。
- 数据量动态增长，不再截断为 200 条。每页 20/50/100 条。
- 只查询元数据，不返回密钥、公钥矩阵、密文包或解封材料。源不可用显示错误而非假装零条。

## Windows PowerShell 上传

```powershell
cd C:\Users\AllenR\Desktop\kms-code\kms-ops\releases\admin-data-20261013
scp kms-admin-data-images.tar.gz SHA256SUMS-admin-data README-admin-data.md expert-machine:/home/rbf/kms-sys/
```

只需以上三个文件。无需上传未压缩的 `.tar`。

## 服务器更新

先校验；所有文件 OK 才继续。以下针对现有已启用 FISCO overlay 的部署。

```bash
cd ~/kms-sys
sha256sum -c SHA256SUMS-admin-data
```

备份当前两镜像的标签；备份失败不要继续 load：

```bash
stamp=$(date +%Y%m%d-%H%M%S)
sudo docker tag kms-dvadmin3-django:local "kms-dvadmin3-django:before-admin-data-$stamp" &&
sudo docker tag kms-gateway-nginx:local "kms-gateway-nginx:before-admin-data-$stamp" &&
echo "Rollback tag suffix: before-admin-data-$stamp"
```

记录该标签后执行（任何一步失败应停止，不继续执行后续步骤）：

```bash
sudo docker load -i kms-admin-data-images.tar.gz &&
sudo docker compose -f docker-compose.yml -f docker-compose.fisco-enabled.yml \
  --profile fabric-did up -d --no-deps --force-recreate --no-build dvadmin3-django nginx
```

等待后端启动就绪后：

```bash
sudo bash deploy.sh verify
sudo docker compose -f docker-compose.yml -f docker-compose.fisco-enabled.yml --profile fabric-did ps dvadmin3-django nginx
```

通过原网址 `https://10.112.125.22:8443/updatedel/` 登录管理端，强制刷新浏览器（Ctrl+F5）。核查四页、验收页签、筛选和翻页。不要执行 `down`、`--backfill`、清库或重新部署合约。

验收统计需要 Django 数据库账户拥有 `kms.keymanage` 的读取权限；当前 Docker 包使用同一 MySQL root 账户，已具备该权限。若远端改为受限账户，应由管理员授予该表 SELECT 权限；无权限时页面会明确报错，不应当作零条。

首次读取十万以上记录的总数可能较慢；HTTP 压测速率不等于最终入库或上链完成速率。验收记录不归属于 `demo-0` 节点。

## 回滚

将下面时间戳替换为上面记录的实际值；不修改数据库或配置：

```bash
sudo docker tag kms-dvadmin3-django:before-admin-data-实际时间戳 kms-dvadmin3-django:local &&
sudo docker tag kms-gateway-nginx:before-admin-data-实际时间戳 kms-gateway-nginx:local &&
sudo docker compose -f docker-compose.yml -f docker-compose.fisco-enabled.yml \
  --profile fabric-did up -d --no-deps --force-recreate --no-build dvadmin3-django nginx
```

## 本地验证范围

SQLite 内存数据库：321 条密钥/池项/会话、601 分发批次、验收数据隔离和管理门禁。
隔离 MySQL 8：JSON 聚合、分页、去重、长接收节点列表筛选、跨库验收查询及参数化搜索。
浏览器合成元数据检查：四页、独立验收页签、历史切换、详情、错误/空态，以及 1500/768/390 像素布局。
节点 FISCO/Fabric 存证及哈希恢复离线回归。生产构建与镜像文件哈希核对。
本地检查不代表远端已部署；更新后需按上述命令核验。
