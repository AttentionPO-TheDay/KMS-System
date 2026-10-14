# 节点 FISCO 交易哈希修复

此前节点存证 prepare 错把 SDK 的未签名数据哈希当作 txId。FISCO BCOS 2.x 默认按包含签名的完整 RLP 交易哈希索引交易；提交后回执因哈希不一致被拒绝。随后 Java 的通用错误响应被 Django 记作 FISCO_RESPONSE_IDENTITY_MISMATCH。

修复使用同一 CryptoSuite 对完整已签名 RLP 计算哈希，再持久化并提交相同签名交易。新的离线测试使用真实 SDK 签名，验证签名数据哈希不等于真实交易哈希。Java 共 12 项测试通过；恢复脚本 5 项隔离 SQLite 测试通过。

只更新 updatedel-java 镜像，不重建合约、不改版本、不更换密钥、不改 .env、Compose、账户或 HTTPS。恢复脚本仅查询已有交易回执，核验成功后才修复本地证据记录；不会调用 prepare/submit 或输出签名交易。完整签名交易仍保留。

## 上传与更新

将本目录 4 个文件上传到 `~/kms-sys/`。校验清单使用独立名称，避免误用旧 SHA256SUMS。

```bash
cd ~/kms-sys
sha256sum -c SHA256SUMS-node-fisco-hashfix
# 全部 OK 后才继续。
sudo docker tag kms-updatedel-java:local "kms-updatedel-java:before-hashfix-$(date +%Y%m%d-%H%M%S)"
sudo docker load -i kms-node-fisco-hashfix-images.tar.gz &&
sudo docker compose -f docker-compose.yml -f docker-compose.fisco-enabled.yml \
  --profile fabric-did up -d --no-deps --force-recreate --no-build updatedel-java
```

等待 Java 启动完成后，先只读查询修正哈希对应的回执：

```bash
sudo docker exec -i -w /backend dvadmin3-django python - < recover-node-fisco-hash.py
```

应显示每条真实回执的 `status: CONFIRMED`、`txId` 和 `blockHeight`，`applied: false`（只读模式）。如果连接尚未就绪，可以稍后再查询。未知/失败回执不会改库；不应强制修改为成功或删除原签名交易。

确认输出后执行恢复：

```bash
sudo docker exec -i -w /backend dvadmin3-django python - --apply < recover-node-fisco-hash.py
sudo bash deploy.sh verify
sudo docker exec -w /backend dvadmin3-django python manage.py shell -c 'from pqkds.models import ChainKeyBinding; print(list(ChainKeyBinding.objects.filter(provider="FISCO").order_by("-id").values("algorithm","key_id","key_version","status","tx_id","block_height","transaction_valid","metadata_matches","last_error")[:20]))'
```

`--apply` 也会再次严格核验链标识、公开材料摘要、numeric keyId、交易哈希和正数区块高度；Java 同时验证交易发送者、目标合约、ABI 参数和 UploadSuccess 事件。并发修改过的记录不会被覆盖。

ECDSA 链恢复候选哈希使用 Keccak-256；若部署为 SM 链，此脚本不会猜测或强行确认，需另行支持 SM3。先前已 FAILED 的任务不会自行重试，新登记任务使用本次修复后的交易哈希。

本地检查不替代服务器回执。恢复后保留原密钥和版本（包括已有 FALCON_CL_V1 版本 3）；之后主动生成的新密钥仍是新 key_id、版本 1。
