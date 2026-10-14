# 分发侧信道风险缓解与验证

本轮在现有信封格式、算法版本和私钥本地保存的架构内补充防护。没有把这些措施标成完整的抗侧信道认证，也没有添加页面技术解释块。

## 已修改

- SM4-GCM 只接受完整 16 字节认证标签；缺失、截短、超长标签明确失败。比较完整遍历，不按首个不匹配字节提前退出。
- GHASH 的位乘法用掩码代替输入相关分支。SM4 的 S 盒仍是查表实现，因此不能宣称整个 SM4 具有常数时间行为。
- 节点解封失败统一为 `NODE_ENVELOPE_UNWRAP_FAILED`，不附带原异常 cause、恢复出的密钥摘要或密码学中间错误。
- 用户腿解封失败也使用统一信息，只有解封及摘要校验都通过后才显示密钥。取不到本机密钥等运算前的操作提示保留。
- 清理自己持有的临时私钥副本、共享秘密、KEK、SM4 轮密钥、部分中间值及发送/接收页面临时会话密钥；HMAC 持有证明完成后清理读回的临时密钥。
- Nginx 对节点分发、信封验签/恢复/签名以及会话确认的 POST 请求，按网关所见源 IP 限制为 10 次/秒、突发 20，超出返回 HTTP 429。Standalone 两条 API 前缀和本机 Demo 前缀共用预算；GET 轮询和其他 API 不计入。

不将调用方的持久密钥或输入缓冲区当作临时值清除。JavaScript 中的字符串、BigInt、JIT/GC 副本、密码库内部内存和 WebCrypto 内存不在这种最佳努力清理的保证范围内。

限流仅减少经过网关的在线探测及滥用；它不能阻止持有密文的攻击者离线探测，也不能限制浏览器本地的私钥运算。多人共用 NAT 时共享 IP 预算，服务器部署后需按正常并发量评估限额。直接访问后端会绕过网关限制，后端端口应保留为内部入口。

## 功能与兼容性验证

在 `kms-updatedel/front` 运行：

```sh
npm run verify:crypto
npm run verify:distribution-security
npm run verify:probe-limit
npm run build:prod
```

- `verify:crypto` 使用运行中 Django 容器的原生密码实现与前端互通，不修改生产节点或业务数据库；本轮 27/27。
- `verify:distribution-security` 使用仅存于本进程内存的测试密钥，调用真实 provider，覆盖三种分发封装、完整标签逐字节篡改、截短/超长标签、统一错误、恢复错误长度、失败摘要不暴露及成功/异常路径私钥副本清理；本轮 46 项通过。
- `verify:probe-limit` 使用两个临时容器、独立 Docker 网络和模拟后端验证真实 Nginx 配置；不调用生产 API 或数据库。需本机已有 `kms-gateway-nginx:local` 镜像。脚本结束删除自己创建的容器和网络。

## 时序探针

```sh
# 相同密文、相同长度的非法标签，分别篡改首字节和末字节。
npm run probe:distribution-timing -- --profile sm4-tag --samples 10000 --rounds 3 --output ../../kms-ops/tests/out-distribution-sidechannel/sm4-tag.json

# 固定密钥与随机密钥，对同长度载荷执行真实 SM4-GCM 加密。
npm run probe:distribution-timing -- --profile sm4-key --samples 10000 --rounds 3 --output ../../kms-ops/tests/out-distribution-sidechannel/sm4-key.json

# 经过真实 BrowserCryptoProvider 的 Kyber 解封，再做 SM4-GCM 认证失败。
npm run probe:distribution-timing -- --profile kyber-envelope --samples 10000 --rounds 3 --output ../../kms-ops/tests/out-distribution-sidechannel/kyber-envelope.json
```

标签/密钥分组随机交错；密钥、标签等输入在测量前准备，热身后采样，统计保留全部样本。报告包含 Node/V8、CPU、依赖锁定版本、各组样本数/均值/方差及 Welch t。三轮分别记录，不能挑一轮通过结果覆盖其他轮。

每组少于 10000 样本标为 `exploratory_small_sample`，不判定通过；达到样本下限后 `|t| >= 4.5` 标为检测到差异且进程退出码为 2。零方差等无法统计的情况标为 `inconclusive`，不当作通过。阈值只是诊断筛查规则，检测到差异不能单凭 t 值推断可恢复私钥；未检测到差异也不能证明无泄露。

退出码 0 只表示诊断脚本完成且没有达到差异退出条件，不能作为“抗侧信道验收通过”的 CI 判据，必须读取各轮状态和样本数。

本机实测：`sm4-key` 和 `sm4-tag` 各每类 10000 样本、3 轮，均未达到差异阈值；Kyber 仅做每类 40 样本的脚本烟测。报告保留于 `kms-ops/tests/out-distribution-sidechannel/`（忽略的测试产物目录）。这些测试测的是 Node/V8 的代码路径，不是目标浏览器或设备的认证报告。

目标服务器应在空闲 CPU、固定运行环境下重复采样（Linux 可使用 `taskset` 固定 CPU），记录环境和所有结果。缓存、功耗、电磁分析以及 SM2 私钥运算、Falcon 签名的系统性时序评估仍需专门验证；当前 SM2 私钥相关点加分支和 SM4 查表风险仍保留。

## 部署状态（2026-10-10）

源码、生产前端构建、Nginx 镜像构建及隔离限流测试完成。正式 `kms_gateway` 已切换到新镜像，HTTPS `/ping` 与本机 Demo 页面均返回 200，运行中的 `nginx -t` 通过。本轮没有重建 Django/Java/Go 后端或执行数据库迁移。工作区同时存在其他异常回收功能改动；这些功能不属于本轮验证结论，仍需其负责的工作核查前后端部署状态。

发布镜像另保留标签 `kms-gateway-nginx:sidechannel-review-20261010`，镜像 ID `sha256:32fed65b4098e92e0fe8e202d025d1032b07dffd3a332e090e3fdd930598d72a`。切换前容器记录的旧镜像 ID `sha256:0bb0b4944537b669fd7242c210a7e2b38c4b5379a349b14230467190ae63b42a` 已无法通过 Docker 镜像操作引用，按 ID 回滚尝试未执行成功；旧镜像不可用原因未确定。后续发布必须先给旧镜像增加明确保留标签并验证可引用，不能只记录容器镜像 ID。

本轮未提交或推送远端。顶层 `backend/` 不属于本轮改动或提交范围。
