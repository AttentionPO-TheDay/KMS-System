# 密钥材料分离与上链保护增量更新

只更新 `kms-generate-java:local`、`kms-updatedel-java:local`、`kms-gateway-nginx:local`。不要覆盖服务器 `.env`、Compose、证书、账户或链数据。

## 实现与验证

- FALCON_CL_V1 完整真实公钥保留用于分发；PUBLIC 不含 PRIVATE 的 D_id/S_id。
- 私钥只在浏览器 IndexedDB 的 `encryptedKeyPackage` 字段中以 AES-256-GCM 封存，不上传服务器。旧 iv/sealed 记录可直接解封，续期时升级布局，不重新生成密钥。
- Java uploadKey/rotateKey 在 ABI 编码前检查 UTF-8 长度；公钥材料超过 8192 字节转为 `sha256:<64位hex>`，其他文本参数超限拒绝。摘要针对传入公钥字符串的 UTF-8 字节，不是解码后的矩阵。
- 两端 Java 共 10 项回归、前端专用 6 组检查、现有密码回归 27/27 通过。专用检查使用合成矩阵和进程内 fake IndexedDB，不登记生产节点。
- 两个 Java clean package、前端生产构建和三个 amd64 镜像构建通过。镜像内 JAR/前端入口哈希与本次产物一致，两端 JAR 含 ChainPublicMaterial.class。
- 无数据库迁移、合约重部署或历史记录改写。本更新不会自动补登记历史初始化密钥；尚未验证服务器实际业务交易回执。

## 服务器更新

将本目录 tar 与 SHA256SUMS 上传到 `~/kms-sys/`，短暂停止浏览器密钥操作。校验失败必须停止。

```bash
cd ~/kms-sys
sha256sum -c SHA256SUMS

# 保存旧镜像，记下时间戳。
stamp=$(date +%Y%m%d-%H%M%S)
sudo docker tag kms-generate-java:local "kms-generate-java:before-material-$stamp"
sudo docker tag kms-updatedel-java:local "kms-updatedel-java:before-material-$stamp"
sudo docker tag kms-gateway-nginx:local "kms-gateway-nginx:before-material-$stamp"

sudo docker load -i kms-chain-material-images.tar

# 保留服务器已有 FISCO overlay，只重建三个应用容器。
sudo docker compose -f docker-compose.yml -f docker-compose.fisco-enabled.yml \
  --profile fabric-did up -d --no-deps --force-recreate \
  generate-java updatedel-java nginx

sudo bash deploy.sh verify
sudo docker compose -f docker-compose.yml -f docker-compose.fisco-enabled.yml \
  --profile fabric-did ps
```

若服务器没有 `docker-compose.fisco-enabled.yml`，停止并检查，不要省略该文件启动。命令复用服务器 HTTPS、白名单和挂载配置，不重启数据库/区块链。

更新后在同一浏览器、同一 HTTPS 地址刷新页面，确认已有密钥可继续使用。不要清除站点数据或重新初始化。然后核验一笔实际业务 FISCO 回执：成功状态、哈希/区块高度、大公钥的链上 sha256 摘要。HTTP 健康检查不等于密钥上链成功。

回滚须注意：旧前端不识别新密文字段。发生新记录封存或旧记录续期后，不能只回退网关镜像；旧前端必须补新布局兼容读取，不能清除本机数据解决。Java 镜像可用保存的 before-material 标签恢复，但会撤回本次长度保护。

镜像 ID：

```text
generate-java  sha256:7bd124d89f099de0c1487b2068594be284727d3af8f415fb6d5fdc511448b56c
updatedel-java sha256:d9eb2914d78eb346cf7605d666132cc0b4701421be192db12d1216faa52b980c
gateway       sha256:4af221e6b097cdb035794d68c0c69c696cd2397366a5316d7b68c028f13068e6
```
