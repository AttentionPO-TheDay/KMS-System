# 节点工作台与生成语义修复

仅更新 `kms-dvadmin3-django:local` 和 `kms-gateway-nginx:local`。
此前已部署包保持为基线，本包不覆盖服务器 .env、Compose、FISCO overlay、TLS 或数据卷。

## 本次变化

- 初始化和后续生成统一纳入累计生成、算法分布、状态及近七天趋势，按算法/keyId 计数。更新仅增加版本，不增加逻辑密钥总数。
- 生成必须创建新 keyId、从 v1 开始；更新保留 keyId、版本递增。登记/自检失败重试仍复用原封存材料，不悄悄生成替代密钥。
- 使用完整登记索引，修复历史列表超过 200 条时可能误恢复旧材料的问题。
- 五张图表布局改为趋势/算法一行、三张状态图一行；分布使用横向条形，空数据与请求错误分别展示，适配手机宽度。
- 新汇总接口仅返回当前节点元数据，不返回公钥正文、私钥或密文。

## 上传（Windows PowerShell）

```powershell
cd C:\Users\AllenR\Desktop\kms-code\kms-ops\releases\node-workbench-20261014
scp kms-node-workbench-images.tar.gz SHA256SUMS-node-workbench README-node-workbench.md expert-machine:/home/rbf/kms-sys/
```

## 服务器更新

以下使用服务器现有 FISCO overlay。每一步失败立即停止，不执行后续步骤。

```bash
cd /home/rbf/kms-sys
sha256sum -c SHA256SUMS-node-workbench
```

先备份当前镜像标签，并记录输出的回滚标签后缀：

```bash
stamp=$(date +%Y%m%d-%H%M%S)
sudo docker tag kms-dvadmin3-django:local "kms-dvadmin3-django:before-node-workbench-$stamp" &&
sudo docker tag kms-gateway-nginx:local "kms-gateway-nginx:before-node-workbench-$stamp" &&
echo "Rollback suffix: before-node-workbench-$stamp"
```

加载并只重建后端与网关，不执行 down、不迁移历史密钥、不清理卷：

```bash
sudo docker load -i kms-node-workbench-images.tar.gz &&
sudo docker compose -f docker-compose.yml -f docker-compose.fisco-enabled.yml \
  --profile fabric-did up -d --no-deps --force-recreate --no-build dvadmin3-django nginx
```

等待后端就绪，然后：

```bash
sudo bash deploy.sh verify
sudo docker compose -f docker-compose.yml -f docker-compose.fisco-enabled.yml --profile fabric-did ps dvadmin3-django nginx
```

节点端 Ctrl+F5 强制刷新。使用你计划开展的正常业务操作验证：生成后 keyId 改变、版本为 1、累计数 +1；更新后同一 keyId 的版本 +1、累计数不变。不会自动生成测试业务密钥。

说明：当前生产槽位模型保持不变，新生成同算法的密钥后旧生产密钥会被取代，但仍计入累计生成；单个 keyId 的状态与存证图取最新版本。历史数据不重写。如果历史上错误操作已保存为同 keyId 的多个版本，本包不会把这些版本伪造成多把新密钥。

如需回滚，将上面记录的两个 `before-node-workbench-时间戳` 镜像重新 tag 为 `:local`，再执行相同的两服务重建命令。

## 已验证

6 项后端隔离 SQLite 测试；真实本地加密 SM2 连续生成/更新/重试回归；自动更新回归；浏览器 1500/768/390px、空数据、失败与恢复；生产构建；最终压缩包 docker load。
