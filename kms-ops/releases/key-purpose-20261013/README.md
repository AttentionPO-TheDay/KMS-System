# 分发保护密钥与会话签名密钥分离

本包替代上一轮 chain-material-20261013 更新包，包含两个已验证的 Java 镜像和本轮新版网关镜像。无需重复上传上一轮 tar。

## 页面与行为

- 节点“密钥生成”页面：KYBER、SSCL、SM2、FALCON_CL_V1，格加密按钮使用真实的 FALCON_CL_V1 流程，不再生成标准 Falcon 签名密钥。
- 节点“密钥分发 → 会话管理 → 会话签名密钥”：独立生成/登记标准 Falcon 核心的 FALCON 签名材料，沿用现有双份额来源校验，仅用于信封签名与验签。
- 现有 FALCON/FALCON_CL_V1 记录保持各自标识，不转换、不删除。已有格加密生产密钥经用户确认后按原 key_id 更新到下一版本；本机不匹配或能力未启用时阻断，不降级成标准 Falcon。
- 初始化仍保持原有全套密钥规则，本轮只拆分日常主动生成入口。两种私钥均继续只在浏览器本机封存，服务端存公钥与登记元信息。
- 保留上一轮私钥专用密文字段、旧记录兼容和 Java 8 KiB 上链摘要保护。不自动补登记历史初始化密钥，不代表服务器已产生成功上链回执。

## 验证

用途策略、Vue 编译、实际页面生成处理函数的算法路由、格加密显式轮换/取消检查通过；初始化算法兼容检查通过；本机密文包 6 组检查通过。浏览器隔离 UI 测试实际点击两个生成按钮，分别确认 FALCON_CL_V1 与 FALCON 请求并验证会话列表返回；接口为 TEST_ONLY 模拟，不生成生产密钥。前端生产构建及网关镜像构建通过，镜像入口哈希与产物一致。

## 服务器更新

只上传本目录 `kms-key-purpose-images.tar` 和 `SHA256SUMS` 到 `~/kms-sys/`。不要覆盖服务器 .env、Compose、HTTPS 证书、FISCO 账户或链数据。暂停浏览器密钥操作，逐步执行：

```bash
cd ~/kms-sys
sha256sum -c SHA256SUMS
# 若不是 OK，停止，不执行下面命令。

sudo docker load -i kms-key-purpose-images.tar
sudo docker compose -f docker-compose.yml -f docker-compose.fisco-enabled.yml \
  --profile fabric-did up -d --no-deps --force-recreate \
  generate-java updatedel-java nginx
sudo bash deploy.sh verify
```

如果服务器不存在 docker-compose.fisco-enabled.yml，停止检查，不要省略它启动；否则可能丢失已有的 FISCO 写入开关。上述命令复用现有服务器端配置，不重建数据库或链节点。

更新后用原浏览器、原 HTTPS 地址刷新，不清理站点数据。检查生成页和会话签名页各自的算法、已有材料对账状态。真实生成/登记后如需确认上链，还须检查业务交易回执，HTTP 健康检查不能替代。

网关镜像 ID：`sha256:0e5898ad435fec945e337123c106b15340faee4c100885722587d3421797acab`。

注意：旧版前端不识别新本机密文字段，不能直接回退旧网关后清除站点数据；如需回滚应先为旧前端补兼容读取。
