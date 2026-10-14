# 生成上链幂等修复

本包只更新 `kms-generate-java:local`，修复 Kafka 至少一次投递导致同一 `key_id` 重复调用 `uploadKey` 的问题。

修复逻辑：消费者收到任务后重新读取数据库最新记录；如果已经存在 `chain_status=1`、交易哈希和区块高度，则直接确认完成并跳过再次上链。这样不会再次触发合约 `key exists`，也不会把已成功状态覆盖为失败。

已确认的历史交易不会重新提交，链上数据和数据库不清理。当前已有的错误状态需要单独根据交易回执核验后恢复，不能盲目批量改状态。

## 上传

```powershell
cd C:\Users\AllenR\Desktop\kms-code\kms-ops\releases\generate-idempotency-20261014
scp kms-generate-idempotency-image.tar.gz SHA256SUMS-generate-idempotency README-generate-idempotency.md expert-machine:/home/rbf/kms-sys/
```

## 服务器操作

```bash
cd ~/kms-sys
sha256sum -c SHA256SUMS-generate-idempotency

stamp=$(date +%Y%m%d-%H%M%S)
sudo docker tag kms-generate-java:local "kms-generate-java:before-idempotency-$stamp"

sudo docker load -i kms-generate-idempotency-image.tar.gz

sudo docker compose -f docker-compose.yml -f docker-compose.fisco-enabled.yml \
  --profile fabric-did up -d --no-deps --force-recreate --no-build generate-java
```

只重建 `generate-java`，不会重启 FISCO、MySQL、Kafka 或 updatedel。Kafka 数据卷和消费组保留，未确认消息会继续消费。

检查：

```bash
sudo docker compose ps generate-java
sudo docker logs --tail=80 kms_generate_java
```

如果需要回滚：

```bash
sudo docker tag kms-generate-java:before-idempotency-实际时间戳 kms-generate-java:local
sudo docker compose -f docker-compose.yml -f docker-compose.fisco-enabled.yml \
  --profile fabric-did up -d --no-deps --force-recreate --no-build generate-java
```

不要执行 `down -v`、清库、重部署合约或重新提交已经存在的 keyId。

## 验证

Java 幂等回归测试 8 项通过；Maven 生产构建通过；生成镜像已在本地构建完成。
