# 节点密钥自动 FISCO 存证增量更新

本目录文件全部上传到服务器 `~/kms-sys/`。不要上传源码中的 .env、证书、账户、数据目录或配置备份；不替换服务器基础 Compose 和 HTTPS 配置。

包含四个镜像：generate-java、updatedel-java、dvadmin3-django、gateway-nginx。FALCON_CL_V1 主动生成新 key_id、版本 1；只有更新保留 key_id 并递增版本。SM2、SSCL、KYBER、FALCON、FALCON_CL_V1 的节点公钥登记后自动排队存证。超过 8192 UTF-8 字节的公钥只上链 SHA-256 摘要，完整公钥仍用于分发。私钥包只留浏览器本机。

## 更新

先暂停浏览器密钥操作。必须保留现有 `docker-compose.fisco-enabled.yml`；脚本复用其中的合约和 Java 账户，不部署新合约、不改 .env、不重建数据库或链节点。

```bash
cd ~/kms-sys
sha256sum -c SHA256SUMS
# 校验全部通过后再继续；失败必须停止。
stamp=$(date +%Y%m%d-%H%M%S)
for image in kms-generate-java kms-updatedel-java kms-dvadmin3-django kms-gateway-nginx; do
  sudo docker tag "$image:local" "$image:before-node-fisco-$stamp"
done
sudo docker load -i kms-node-fisco-images.tar
sudo python3 enable-node-fisco.py --activate --backfill
sudo bash deploy.sh verify
```

启动会自动执行新增的 0035 迁移（增加区块高度字段，不清库）。`--backfill` 为已有 ACTIVE 节点密钥补存证任务，不生成密钥、不增加版本。后续生成登记自动处理，无需反复执行 backfill。

若脚本报告迁移等待超时，先检查 Django 启动日志，确认迁移成功后再次运行激活命令。若重新运行旧 `connect-existing-fisco.py`，须再运行本脚本恢复新增的节点存证开关。

## 确认真实上链

沿用原浏览器、原地址 `https://10.112.125.22:8443/updatedel/`，刷新，不清理站点数据。生成页应显示“上链存证”、交易哈希和区块高度。只有回执验证通过才显示“已上链”。

安全只读查询（不输出公钥巨包、签名交易或私钥）：

```bash
sudo docker exec -w /backend dvadmin3-django python manage.py shell -c 'from pqkds.models import ChainKeyBinding; print(list(ChainKeyBinding.objects.filter(provider="FISCO").order_by("-id").values("algorithm","key_id","key_version","status","tx_id","block_height","transaction_valid","metadata_matches","last_error")[:20]))'
```

应看到 `CONFIRMED`、非空交易哈希、正数区块高度，以及两个验证标志均为 True。PENDING / PREPARED / SUBMITTED / PENDING_VERIFICATION 是待确认，不等于失败；FAILED 需要检查原因。HTTP 健康检查只证明服务可访问，不能替代业务回执。

本次链上记录是按 key_id 和版本独立的公钥登记证据，不代表链上同步回收/更新后的当前状态；本次不启用 DID 或旧 Django/Web3 写入。

本地回归通过不代表服务器已上链成功，须部署后核验上述真实回执。保留镜像标签和脚本生成的权限受限 overlay 备份，不把备份发给客户端。旧前端不能直接读取新增本机密文字段，禁止清除浏览器数据来回滚。
