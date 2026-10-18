# 泄露分析节点入口精简升级

此包仅更新 Nginx 前端镜像：节点侧移除“用户密钥”类型切换，始终查询自身节点密钥；管理员入口保留。业务数据、后端和数据库不变。

前提：服务器已经部署 `node-diagnostics-ui-20261014` 后端诊断包及其域管理前置包。此包不包含 Django 或 Java，不能替代上述后端升级。

## 需要上传的四个文件

- `kms-leak-analysis-nginx.tar.gz`
- `SHA256SUMS-leak-analysis`
- `apply-leak-analysis.sh`
- `README-leak-analysis.md`

在本地 PowerShell 执行：

```powershell
Set-Location C:\Users\AllenR\Desktop\kms-code\kms-ops\releases\leak-analysis-node-only-20261014
scp kms-leak-analysis-nginx.tar.gz SHA256SUMS-leak-analysis apply-leak-analysis.sh README-leak-analysis.md expert-machine:/home/rbf/kms-sys/
```

## 服务器执行

```bash
ssh expert-machine
cd /home/rbf/kms-sys
bash apply-leak-analysis.sh
bash deploy.sh verify
```

脚本先校验 SHA256，再保存旧 Nginx 镜像标签并载入新镜像，只重建 nginx。不执行 down、不清库、不删除卷；网关重建期间可能短暂不可访问。

完成后 Ctrl+F5 刷新浏览器：节点侧泄露关联分析页没有“用户密钥”选项，输入自己的 keyId 后点击分析；管理员仍可选择两种密钥类型。尚未由 Codex 上传或部署。

回滚（将时间戳替换为应用脚本输出的值）：

```bash
docker tag kms-gateway-nginx:before-leak-analysis-时间戳 kms-gateway-nginx:local
docker compose -f docker-compose.yml -f docker-compose.fisco-enabled.yml --profile fabric-did up -d --no-deps --force-recreate --no-build nginx
```
