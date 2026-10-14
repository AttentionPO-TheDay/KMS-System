# 节点诊断与界面精简升级

适用前提：已部署 domain-registry-20261014 域管理包。此包包含 Django、Nginx 两个镜像，不含 Java，不新增迁移或 SQL。

本次变更：节点自身长期密钥只读一致性检查、关联分析；未查询/失败不显示成功；删减页面解释段；预分配、更新、分发加入可折叠技术图解。原生成、更新、回收、分发业务流程与真实数据保持不变。技术图解不是算法执行证据或安全证明。

保留必要错误、设备密钥恢复、不可逆操作与实验算法安全警告。节点诊断仅检查登记公钥摘要、适用算法的生产公钥、槽位和到期情况，不代表分布式安全证明。

## 上传

在本地 PowerShell 执行：

```powershell
Set-Location C:\Users\AllenR\Desktop\kms-code\kms-ops\releases\node-diagnostics-ui-20261014
scp kms-node-diagnostics-images.tar.gz SHA256SUMS-node-diagnostics apply-node-diagnostics.sh README-node-diagnostics.md expert-machine:/home/rbf/kms-sys/
```

## 服务器应用

```bash
ssh expert-machine
cd /home/rbf/kms-sys
sha256sum -c SHA256SUMS-node-diagnostics
bash apply-node-diagnostics.sh
bash deploy.sh verify
```

脚本先验证文件和旧域表，再保存旧镜像标签，载入镜像并仅重建 Django、key-reclaimer、Nginx。不执行 down、不删除卷、不初始化业务数据。应用后重新进入 Demo 并刷新浏览器。

核验：节点输入自己的 keyId，输入时不出现分析结论；点击检查/分析得到真实记录；他人或不存在 keyId 显示错误且没有成功结论；管理员原分析入口仍保留。

回滚：使用脚本输出的时间戳，将 `kms-dvadmin3-django:before-node-diagnostics-时间戳` 和 `kms-gateway-nginx:before-node-diagnostics-时间戳` 分别 tag 回 `:local`，再以相同 compose 参数重建上述三个服务。无数据库改动需要回滚。

本包未由 Codex 部署到服务器。
