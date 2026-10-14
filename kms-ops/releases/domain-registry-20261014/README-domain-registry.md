# 独立域管理与跨域分发升级

本包包含 Django、updatedel-java、Nginx 三个镜像，替代上一版只有域汇总的更新包。不覆盖服务器 Compose、.env 或链配置，不清库、不改已有节点域、不改历史分发快照。

## 功能

- 管理端域管理：新增唯一域标识、名称、说明，空域持久保存；为节点选择已登记域并保存。
- 节点列表：创建与编辑节点均使用已登记域。
- 节点发起分发页：显示双方域，提供“仅跨域”范围，排除同域与未指定域节点。仍走真实通信授权、密钥版本、封装与验签流程，不复制另一套分发协议。
- 管理端数据监管下增加“跨域分发记录”，读取全局安全元数据，节点仍只读本人批次。
- 数据迁移 0036 创建域表，回填既有节点域并保留默认 domain-1。

## 上传与执行

本机 PowerShell，在仓库根目录执行：

```powershell
scp kms-ops/releases/domain-registry-20261014/* expert-machine:/home/rbf/kms-sys/
ssh expert-machine
```

服务器执行：

```bash
cd /home/rbf/kms-sys
sha256sum -c SHA256SUMS-domain-registry
sudo bash apply-domain-registry.sh
sudo bash deploy.sh verify
```

脚本会备份相关菜单行、节点域归属元数据和旧镜像标签，然后载入镜像、执行 Django 迁移、应用两份幂等菜单 SQL，重建 Django、回收 worker、updatedel-java 与 Nginx。服务启动也会检查迁移。无需先部署上一版域管理包。升级窗口内暂停节点业务操作。

完成后重新进入 Demo 管理端并 Ctrl+F5，避免旧菜单缓存。

## 验收

1. 管理端新增 domain-2、domain-3；没有节点时应显示节点数 0。
2. 为两个节点分别选择不同域并保存，刷新确认归属仍在。
3. 节点端进入密钥分发 → 发起分发 → 仅跨域，只有异域且已指定域的节点可选。
4. 未授权先申请并审批，使用有效接收方密钥分发。管理端查看跨域记录；没有实际分发时显示空表，不能把空表当作验收成功。
5. 调整节点域后，旧批次的 sourceDomainId / targetDomainIds 和跨域类型不变。

本地验证使用独立 SQLite 内存数据库及浏览器 API 夹具；未向运行中的业务库写测试密钥，也未验证远端实际密码学分发结果。

## 回退

脚本输出旧镜像标签后缀。将三个 `:before-domain-registry-时间戳` 重新标记为各自 `:local`，再用同一 Compose 组合重建上述四个服务；菜单可从备份 SQL 恢复。新增域表可保留兼容旧版本，不要删除表、回退数据库卷或重置链。恢复菜单前审阅备份与当前菜单差异。
