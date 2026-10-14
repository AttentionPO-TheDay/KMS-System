# 验收密钥生命周期页面

更新三个镜像：`kms-updatedel-java:local`、`kms-acceptance-backend:local`、`kms-gateway-nginx:local`。
Java 保留已验证的 FISCO 签名交易哈希修复；不更新 Django 镜像，不清库、不回填、不重部署合约。

## 页面与数据口径

入口：验收台顶部「验收密钥生命周期」，或管理端验收压测记录中的链接。
网址：`https://10.112.125.22:8443/acceptance/#/lifecycle`。

- 更新测试：每把密钥的测试前后版本、状态与版本更新完成率。
- 异常回收测试：验收专用密钥的状态变化，不能解释成实际检测到泄漏。
- 最终回收率：初始有效、实际回收、仍未完成、缺失/未核验；严格大于 98% 才满足回收率目标。
- HTTP 成功 TPS 与实际状态完成率分别展示，不将已上链状态冒充更新成功。
- 支持按批次、ID、核查结果筛选，明细每页 20/50/100 条，动态总数无 200 条截断。
- 仅保存元数据快照，不保存密钥、公钥矩阵、密文包或浏览器私钥包。

升级后新执行的测试才有快照，不能补造旧历史。归档存在独立 Docker named volume `kms_acceptance_lifecycle`，容器重建仍保留。仅当前 ADMIN 会话和会话 revision 可读；退出、切换身份后旧归档不再显示。刷新读取归档，不重新回收，也不改动既有验收结论。

## PowerShell 上传

只上传以下四个文件，不上传源码、.env、TLS 私钥或服务器备份：

```powershell
cd C:\Users\AllenR\Desktop\kms-code\kms-ops\releases\acceptance-lifecycle-20261014
scp kms-acceptance-lifecycle-images.tar.gz install-lifecycle-audit.py SHA256SUMS-acceptance-lifecycle README-acceptance-lifecycle.md expert-machine:/home/rbf/kms-sys/
```

## 服务器升级

先检查空间并校验。任何一步失败都停止，不执行下一步。

```bash
cd ~/kms-sys
df -h . /var/lib/docker
sha256sum -c SHA256SUMS-acceptance-lifecycle
```

校验必须全部 OK。安装脚本需要 PyYAML，之前 FISCO 配置脚本已使用过同一依赖：

```bash
sudo python3 -c 'import yaml; print("PyYAML OK")'
sudo python3 install-lifecycle-audit.py
```

默认只读验证现有 Compose 和 FISCO overlay，只允许增加验收归档存储。备份当前镜像标签并记录输出的后缀：

```bash
stamp=$(date +%Y%m%d-%H%M%S)
sudo docker tag kms-updatedel-java:local "kms-updatedel-java:before-lifecycle-$stamp" &&
sudo docker tag kms-acceptance-backend:local "kms-acceptance-backend:before-lifecycle-$stamp" &&
sudo docker tag kms-gateway-nginx:local "kms-gateway-nginx:before-lifecycle-$stamp" &&
echo "Rollback suffix: before-lifecycle-$stamp"
```

载入成功后才激活：

```bash
sudo docker load -i kms-acceptance-lifecycle-images.tar.gz &&
sudo python3 install-lifecycle-audit.py --activate
```

脚本把归档卷合并进现有基础 Compose，并保存 0600 权限备份；保留现有 FISCO overlay、端口、TLS 和环境变量。仅重建 updatedel-java、acceptance-backend、nginx，不重启数据库或链节点。

等待 Java 启动就绪后执行：

```bash
sudo bash deploy.sh verify
sudo docker compose -f docker-compose.yml -f docker-compose.fisco-enabled.yml --profile fabric-did ps updatedel-java acceptance-backend nginx
```

浏览器 Ctrl+F5，使用管理员视角。分别执行新的更新、异常回收和最终回收测试，再到生命周期页面选择对应批次核查。核验窗口结束时尚未落库的任务会显示仍未完成，归档不会随后台后续完成自动改写。

不要执行 `down -v`、`--backfill`、清库或重新部署合约。不要将私有 Compose 备份上传到客户端。

## 回滚

将时间戳替换为上述记录值，恢复三镜像标签，再重建三个服务即可。保留新增归档卷，回滚无需删除数据或恢复私有配置：

```bash
sudo docker tag kms-updatedel-java:before-lifecycle-实际时间戳 kms-updatedel-java:local &&
sudo docker tag kms-acceptance-backend:before-lifecycle-实际时间戳 kms-acceptance-backend:local &&
sudo docker tag kms-gateway-nginx:before-lifecycle-实际时间戳 kms-gateway-nginx:local &&
sudo docker compose -f docker-compose.yml -f docker-compose.fisco-enabled.yml --profile fabric-did up -d --no-deps --force-recreate --no-build updatedel-java acceptance-backend nginx
```

## 本地验证

Go 全包回归、321 条逐密钥分页与分块查询、22 批归档分页、会话/revision/管理员隔离、缺失/重复/旧元数据、取消和不可核验结果；Java 元数据与 FISCO/8 KiB 材料限制回归 13 项；安装脚本 5 项（含真实 Compose 只读验证）；普通用户 named volume 写入；真实 Vue 浏览器合成数据验证三分类、筛选、分页、空态、错误态，以及 1500/768/390 像素布局；两个前端生产构建、镜像文件哈希和压缩包本地 load。

本地验证不表示远端已升级，也不代替远端实际压力测试。
