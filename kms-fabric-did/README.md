# 独立 Fabric 国密 DID Bridge

独立 Java 8 JVM，复用 `../jarFile` 的供应方定制 DID/Fabric SDK，不与现有 FISCO 服务共享 provider 或 SDK singleton。
**本轮交付是离线适配，不是实链连通证明；默认关闭、默认禁止写链。** 生产源码没有模拟链或自动确认开关。

## 构建与依赖

```sh
mvn -f kms-fabric-did/pom.xml clean package
mvn -f kms-fabric-did/pom.xml dependency:tree "-DoutputFile=target/dependency-tree.txt"
```

主程序为 `target/kms-fabric-did-1.0.0.jar`，必须连同 `target/lib/` 部署。使用 thin JAR，是为了保留国密/JCE provider 的原始签名 JAR 与服务描述文件；不能只复制主 JAR，也不能自行合并/删除签名后冒充已验证运行包。

固定供应方坐标：

- `com.yunphant:did-sdk-gm:1.1.1`
- `org.hyperledger.fabric:fabric-gateway-java-gm:2.2.0-did-gm-SNAPSHOT`
- `org.hyperledger.fabric-sdk-java:fabric-sdk-java-gm-slf4j:2.2.13-did`
- `com.yunphant:kms-core:1.0-DID`

本地 Maven 文件仓库指向原始 `jarFile/`。普通传递依赖允许 Maven 下载；不将上述定制包换成标准 Fabric 版本，不修改供应方 JAR。`gmssl` 的 `packaging=pom` 是聚合依赖，不应猜测补建 JNI/JAR。

本机 Java 8u152 可编译和执行离线 HTTP 测试；**国密 TLS/provider 的真实运行兼容性未验证**。链方文档建议 Zulu Java 8u302+，应在该运行环境进行后续授权联调。

## 配置与目录约束

`config/bridge.env.example`、`config/fabric.config.properties.example` 和 `config/gm-sdk.properties.example` 都不含实际地址、组织、证书或私钥。

SDK 硬编码读取 `user.dir` 的父目录下的 `fabric.config.properties`，且国密配置是静态全局。建议部署布局：

```text
/run/fabric-did/
  fabric.config.properties    # 链方实际参数；只读挂载
  gm-sdk.properties           # 只读挂载
  connection.json             # 链方实际连接描述、TLS CA 等；只读挂载
  application-cert.pem        # 已授权的 MSP enrollment 证书；只读挂载
  application-key.pem         # 对应 MSP 私钥；只读挂载，不进镜像或 Git
  controller-public.pem       # 稳定 DID 管理 SM2 公钥 PEM；只读挂载
  work/                       # JVM 工作目录，无凭据自动复制
/app/
  app.jar
  lib/                        # 保留原始依赖文件
```

从 `/run/fabric-did/work` 运行：

```sh
java -DfabricSDK.configuration=/run/fabric-did/gm-sdk.properties -jar /app/app.jar
```

环境中的 `FABRIC_DID_PROPERTIES_FILE` 必须显式等于 `/run/fabric-did/fabric.config.properties`。配置中的相对文件路径以 JVM 工作目录为基准，而非以属性文件为基准；建议使用实际只读挂载的绝对路径。缺失或路径布局错误均返回 `NOT_CONFIGURED`，报告仅包含字段名，不输出凭据路径或内容。

- `KMS_CHAIN_WRITES_ENABLED=false`：全局暂停（默认）。缺失、`false`、空值及其他非法值均暂停；只有明确 `true`（大小写不敏感，不接受数字/yes/前后空白）放行。该闸门独立于所有 `FABRIC_DID_*` 开关；暂停时 prepare/submit 首先返回 HTTP 503 / `CHAIN_WRITES_PAUSED`，先于配置检查与 SDK 初始化/交易创建，即使已缓存 SDK 或存在旧 prepare 计划也不能绕过。读取/验证仍按原认证和本地配置要求执行，不抹去历史交易与绑定证明。
- `FABRIC_DID_ENABLED=false`：完全关闭，SDK 不初始化。
- `FABRIC_DID_WRITE_ENABLED=false`：不允许提交；全局闸门为 true 且有效配置下可以 prepare/读取/验证。
- `FABRIC_DID_CREATE_POLICY_APPROVED=false`：即使允许写，仍不能提交。只有链方确认应用专属 DID 标识格式、JSON metadata/长度/权限和 create-only 语义后，才由操作人员显式批准。
- `FABRIC_DID_METHOD_ID` **没有默认值**，必须由链方提供，不能借用其他应用 DID。
- `FABRIC_DID_CHAIN_ID` 是应用侧来源标签，不假装是链节点自动认证出的网络标识。
- `FABRIC_DID_HOST` 默认 `127.0.0.1`；容器内如设 `0.0.0.0`，应仅在内部网络暴露，不发布公网端口。
- `INTERNAL_TOKEN` 未设时内部入口全部 fail closed。请求通过 `X-Internal-Token` 认证。

`/health` 和认证状态均提供 `chainWriteState`（全局闸门关闭时为 `PAUSED`）与有效 `writeEnabled`（要求全局放行、启用、配置齐备、本地写开关和策略批准均成立）。暂停且配置齐备时状态为 `READY_READ_ONLY`，原 `DISABLED`/`NOT_CONFIGURED` 诊断仍保留；这些字段不修改历史 `CONFIRMED` 证据。

状态中的 `READY`/`READY_READ_ONLY` **只表示本地配置与开关状态**，不表示网络、证书、metadata 链码能力已验证；`capabilities.networkChecked=false` 明确表达这一点。应用启动、`/health` 和状态入口均不会构造 SDK；首次有效配置的授权 SDK 操作才懒加载。

## 内部 HTTP 契约

所有成功响应为 `{code:200,msg:"ok",data:{...}}`。错误使用真实 HTTP 状态，同时响应 `{code:<httpStatus>,msg:<稳定安全信息>,data:{errorCode:<稳定码>}}`；不输出原始 SDK 异常或凭据路径。

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/health` | 无认证存活检查，关闭/缺配置也可运行 |
| GET | `/internal/fabric-did/status` | 认证配置诊断、开关与能力 |
| GET | `/internal/fabric-did/did?did=<urlencoded literal>` | 按原样读取 DID，不改写 DID 方法或 ID |
| POST | `/internal/fabric-did/bindings/prepare` | 分配 nonce/txId、规范化绑定，**不提交** |
| POST | `/internal/fabric-did/bindings/submit` | 使用 durable outbox 已保存的计划提交 create-only 记录 |
| POST | `/internal/fabric-did/bindings/verify` | 验证原 txId 有效并精确回读 DID metadata |

### 绑定 metadata

prepare 接收下列全部字段。未知字段、重复 JSON 字段、业务私钥/SM4/设备凭据/MSP 字段不接受。`nodeId`/`eventId`/逻辑 `keyId` 为字符串；版本/修订号为正整数；公钥是登记表已标准化的存储字符串，桥接不再解码 hex/base64。

```json
{
  "schemaVersion": 1,
  "namespace": "kms-key-binding-v1",
  "eventId": "offline-event-001",
  "nodeId": "offline-node-001",
  "algorithm": "KYBER",
  "keyId": "offline-logical-key-001",
  "keyVersion": 1,
  "publicKey": "04aabbcc",
  "publicKeyHash": "登记表字符串的SHA256小写hex，不是解码公钥的哈希",
  "status": "ACTIVE",
  "revision": 1,
  "eventType": "REGISTERED",
  "recordedAt": "2026-10-09T10:15:00.123456"
}
```

这段仅为字段说明，不是可直接提交的密钥或哈希。四算法只接受 `SM2/SSCL/KYBER/FALCON`，不把 round-3 Kyber 改名为 ML-KEM。状态只接受 `ACTIVE/RETIRED/REVOKED`，事件只接受 `REGISTERED/ROTATED/REVOKED`；撤销事件和撤销状态必须对应。`recordedAt` 必须来自稳定 DB 记录，不用每次重试的当前时间。

metadata 为按键排序、无空格、保留 Unicode 的 UTF-8 JSON；`metadataDigest=SHA256(metadata UTF8)`。`publicKeyHash=SHA256(publicKey存储字符串 UTF8)`，必须与登记表原值一致。

确定性不可变 DID 策略：`did:<链方methodId>:<namespace>:binding:<metadataDigest>`。绑定内容、版本、状态、事件变化生成新的应用专属记录，不更新/覆盖既有 DID；格式必须经链方确认后才启用写入。

### prepare / submit / verify

prepare 的 `data` 包括：

```text
provider: FABRIC_DID
chainId, did, txId, nonce
metadata: 规范 JSON 字符串
metadataDigest: 小写 SHA256 hex
binding: 完整绑定对象
prepared: true
status: PREPARED
latestProjection: {status: UNSUPPORTED}
```

**调用方必须在持久化 outbox 中保存上述 txId/nonce/metadata/digest/DID 后再提交。** Bridge 不充当数据库，不保存业务私钥、不自动补建 outbox。prepare 本身只创建 SDK transaction context，不调用 createDidDocument/submit；重试应复用已保存计划，不重复 prepare。

submit 接收完整 prepare `data`（包括 `binding`），重新计算 metadata、digest、DID，并用原 nonce 和固定 MSP 身份计算 SDK transaction ID，拒绝篡改或错误 nonce/txId。存在完全相同的记录时只验证，不重新创建；冲突/停用记录不覆盖。新提交完成后也只返回 `PENDING_VERIFICATION`。

verify 请求：

```text
{did, txId, metadataDigest, expectedMetadata: <绑定对象或规范 JSON 字符串>,
 provider?: FABRIC_DID, chainId?: <来源标签>, nonce?: <原nonce>, binding?: <绑定>}
```

verify 重新验证 expectedMetadata 的严格 schema、publicKeyHash、摘要和应用专属 DID。返回：

```text
{provider, chainId, did, txId, metadataDigest,
 transactionValid: true|false|null,
 metadataMatches: true|false|null,
 status: CONFIRMED|PENDING_VERIFICATION|FAILED,
 errorCode: <错误码或null>}
```

只有原 txId 交易验证有效 **并且** 回读 ID、未停用状态及 metadata 字符串完全一致，才是 `CONFIRMED`。未知交易/暂时无法回读为待核对，无效交易或字段不一致为失败。提交异常返回 `SUBMISSION_OUTCOME_UNKNOWN` 和原 txId；**超时不能重新生成 nonce 或盲目重发，后续先 verify**。Bridge 的事务验证 API 只提供交易有效性，不提供交易 payload 归属证明；来源关联依赖可信内部调用方的 durable prepare 记录，不能用任意外部 txId 作为证明。

### 供应方 SDK 的真实语义与能力边界

- `DidHandler.createDidDocument(DocumentReq,nonce)` 返回 req.id；它忽略 `DidService` 的链码 String 返回载荷。两种返回都**不是 txId 或交易成功证明**。
- `genTxId()` 提供 txId 与原 nonce；`sendSignedProposal(...)` 返回 void；交易最终有效性由 `getTransactionStateById(txId).getValid()` 查询。
- SDK `DocumentReq.publicKey` 必须是稳定管理 SM2 PEM，不是业务四算法公钥。create 使用配置中的稳定 MSP enrollment 身份签交易，文档 controller 为自身 DID；供应方实际 role 为 `HOLDER`，枚举没有 `OWNER`，不能伪造“已具备 Owner 角色”的结论。
- 更新/停用需要供应方 proposal 和应用控制者签名。实际 `Kms.sign` 的 UTF-8/SM3 hex 签名载荷不能擅改。本轮不实施更新/停用/最新节点投影，不生成临时管理签名密钥；这些能力明确为 `UNSUPPORTED`，不声称完整生命周期等价。
- SDK 错误码 400001 本身含“不存在或已注销”，无法仅凭该码区分；桥接返回 `NOT_FOUND_OR_DEACTIVATED`，绝不将所有错误压成 false。返回 Document 时可独立报告 `DEACTIVATED`；其他网络/链码错误为 `DID_READ_FAILED`。create-only 路径仅在已批准的自有确定性命名空间使用；已返回的停用文档不会覆盖。
- 本进程提交串行，但链码无已确认 CAS，不能抵御外部写者并发。联调前必须确认应用单授权写者政策，不能部署多个写入副本后声称具备分布式锁。

## 离线验证与后续联调

`BridgeOfflineTest` 使用测试源码内的 FakeDidSdk，覆盖四算法规范 metadata、稳定管理公钥、nonce/txId、prepare 无提交、幂等/冲突、篡改/私密字段拒绝、错误 DID/停用/交易无效不确认、超时待核对，以及真实 loopback HTTP 的健康、认证、缺配置和 prepare→submit→verify。测试临时文件明确是非真实身份，不修改现有 DB，不连接任何 Fabric 节点。

后续链方须提供实际 connection.json、MSP enrollment 证书/私钥、TLS CA、channelName/mspId/chaincodeId/methodId、既有只读 DID、metadata JSON/长度/字段保留规则、创建/更新/签名权限、交易查询语义、单写者/CAS 政策。

联调顺序：先关闭写入启动并只读链方原样 DID；再单独获准创建应用专属测试记录，保存 nonce/txId，验证 metadata 逐字还原和交易有效性；全部通过后再申请正式切换。**不能根据离线 fake 的 CONFIRMED 宣称实链成功。** 本模块不自动迁移旧 DID、不修改旧 BlockchainConfig、不清理旧 Transaction，不回退写 FISCO/Web3。
