# SysPid 标识上链

本入口调用供应方国密 DID SDK，目标为供应方 Fabric DID 链，**不调用 FISCO**，不上传现有节点的业务公钥。它与原 `bindings/*` 业务公钥绑定入口相互独立，不改变现有密钥生成、分发或更新流程。

## 已确认的链选择

- `channelName=didchannel4`
- `chaincodeId=didchaincode4`
- `methodId=yunId`，大小写固定，不在每次请求时随机生成。
- `ordererName=orderer-1-baas1`，公网 `122.224.205.114:18134`，保留原 CA 和 TLS 名称校验。
- `peer-1-baas1`，公网 `122.224.205.114:18139`；`userName=peer-1-baas1`，`mspId=baas1`。
- 已使用的 SysPid 参数保存在项目根目录 `output/did-parameters/controller-public-key.hex.txt`。

以上固定选择另存于 `config/syspid-target.properties`。已上链成功，并通过独立回读复核：
`CONFIRMED`、`transactionValid=true`、`metadataMatches=true`。
查询参数与命令见 `../output/did-parameters/DID_QUERY_PARAMETERS.md`；
非敏感凭证见 `../output/did-parameters/channel4-confirmed-result-20261019.json`。

## 请求与执行

### 用户密钥生成的独立 SysPid

用户密钥／批量生成入口需要每次返回独立 SysPid，不复用上面的历史固定标识。内部新增：

```http
POST /internal/fabric-did/sys-pids/prepare
X-Internal-Token: <内部令牌>
Content-Type: application/json

{"requestId":"<已持久化或需重试复用的UUID>"}
```

此接口需与上链相同的显式写入授权。它使用供应方 SM2 密钥生成器，取新管理公钥的 SubjectPublicKeyInfo DER 十六进制作为该次 SysPid，在受限目录保存管理私钥、请求映射及原 txId/nonce，返回 SysPid、DID、txId 和 PREPARED，不提交交易。相同 requestId 在重启后仍取得原标识；不同请求分配不同标识。响应不返回管理私钥和 nonce。

随后以原 SysPid 调用下述 onchain，一次提交后仅查询原交易。用户生成服务的实现入口为 `kms-generate/go-backend/service/fabric_did.go`，以 `FABRIC_DID_KEYGEN_ENABLED=true` 显式启用。SysPid 和请求ID随生成记录写入 Kafka／MySQL，生成响应提供 `sysPid` 与 `didOnchain`；调用者使用 `GET /generate/did/query?sysPid=...` 查询，接口校验当前用户的记录归属。

本接口的链上 metadata 仍是 SysPid 原文；业务密钥与该标识的映射在本地生成记录中。查询成功证明该次 DID 标识的交易和文档已确认，不额外声称链上文档包含业务密钥全部内容。

认证方式与既有 Bridge 相同：请求头 `X-Internal-Token`，不对公网暴露。

```http
POST /internal/fabric-did/sys-pids/onchain
Content-Type: application/json
X-Internal-Token: <已有内部令牌>

{"sysPid":"<整行十六进制 ASN.1 DER 序列>"}
```

只允许 `sysPid` 字段，拒绝私钥、业务 keyId、公钥覆盖参数以及非 DER 编码。处理流程：

1. 按供应方规则生成 `did:{methodId}:{channelName}:zhxun-test{sysPid}`；方法和通道读取自 `fabric.config.properties`，并校验 methodId 与 Bridge 环境一致。
2. 调用供应方 `KmsServiceImpl.genKey()` 生成独立 SM2 DID 管理密钥对，不使用现有业务节点密钥。
3. 组装 `DocumentReq{id, alsoKnownAs="ZHXUN_DID", publicKey=<生成的SM2公钥PEM>, metadata=sysPid}`。metadata 不包装 JSON，不替换成业务公钥或摘要。
4. 调用 `DidHandler.genTxId()` 获取 txId/nonce，校验二者对应关系；在提交前持久化交易计划及管理私钥。
5. 调用 `DidHandler.createDidDocument(request, nonce)`，然后查询原 txId 的有效性并回读 DID 文档。

生成的管理私钥只保存在进程所有者可访问的本地目录中，不写入 metadata，不进入 HTTP 响应。保留此私钥是为了避免 DID 创建后失去后续管理所需材料；本入口本身不实现吊销或更新。

## 结果和重试

- `CONFIRMED`：原交易有效，且回读 DID、metadata、alsoKnownAs、管理公钥一致且未停用。
- `PENDING_VERIFICATION`：尚无法确认交易或文档。SDK 返回 DID 字符串不等于成功回执。
- `FAILED`：交易无效，或回读文档不一致/已停用。
- `EXISTS`：链上已有同一标识，但本地没有创建交易记录；不再写入，也不伪造 txId。

提交超时返回原 txId 与待核对状态；后续使用相同请求调用：

```http
POST /internal/fabric-did/sys-pids/verify
Content-Type: application/json
X-Internal-Token: <已有内部令牌>

{"sysPid":"<原sysPid>"}
```

同一标识重试、进程重启后再次请求都会复用已持久化记录。已开始提交的交易只核对，**不自动生成新密钥、新 nonce 或重发**。全局暂停写链时 verify 仍可使用。本地没有记录的 verify 返回 `SYSPID_RECORD_NOT_FOUND`。

另有操作员显式使用的 `retry` 单次命令：仅在账本明确返回原 txId 的 `Entry not found in index`、文档也未查到且交易未确认/未判无效时，才允许恢复原计划；复用原管理公钥、txId、nonce，并递增记录中的 retryCount。网络错误或查询不确定不能触发恢复；普通 HTTP onchain 请求仍不会自动重发。

## 配置和持久化

沿用 `config/bridge.env.example`、`fabric.config.properties.example` 和 `gm-sdk.properties.example` 的 SDK 配置与身份材料约束。除现有 SDK 配置外，需要设置：

```text
FABRIC_DID_SYSPID_RECORDS_DIR=<专用可写持久化目录>
```

此目录不可放在只读证书挂载中，不可作为静态文件目录或提交 Git。每个链/标识单独建子目录，保存：

- `record.json`：原 txId、nonce、DID、sysPid、生成的管理公钥及提交计划状态。
- `verification.json`：最近一次交易/文档核对结果；以此文件查看最新确认状态，而不是把 record.json 中的待核对标记当最终状态。
- `controller-private.pem`：对应的管理私钥，仅本地保存，需作为敏感材料保护和备份。
- `record.lock`：避免同一持久化目录的多个进程并发提交。

此目录在 Linux 设置为 0700，Windows 设置为仅所有者访问的 ACL。未配置存储或提交前保存失败时，拒绝发交易。不同目录/不同主机不共享锁，不能据此宣称具备链上 CAS。

`KMS_CHAIN_WRITES_ENABLED`、`FABRIC_DID_ENABLED`、`FABRIC_DID_WRITE_ENABLED`、`FABRIC_DID_CREATE_POLICY_APPROVED` 均须明确设为 true 才允许上链。仅这一功能需要开启时，不要顺带更改原业务链路的路由选择。

默认 Docker 可选服务禁止写链。通道4服务器部署使用独立覆盖文件启用只读查询，写开关仍为 false。
运行 SysPid 写入需另行明确授权；不得因查询部署顺带开启业务批量上链。

## 单次命令调用

构建 `mvn -f kms-fabric-did/pom.xml package` 后，部署主 JAR 与完整 `target/lib/`，加载上述环境，在 SDK 要求的 `work/` 工作目录运行。

PowerShell（将下列路径替换为实际绝对路径）：

```powershell
java '-DfabricSDK.configuration=C:/did-runtime/gm-sdk.properties' `
  -cp 'C:/kms-fabric-did/target/kms-fabric-did-1.0.0.jar;C:/kms-fabric-did/target/lib/*' `
  com.kms.fabricdid.SysPidCommand onchain C:/kms-code/output/did-parameters/controller-public-key.hex.txt
```

Linux：

```sh
java -DfabricSDK.configuration=/run/fabric-did/gm-sdk.properties \
  -cp '/app/app.jar:/app/lib/*' com.kms.fabricdid.SysPidCommand \
  onchain /data/controller-public-key.hex.txt
```

核对时只将 `onchain` 改为 `verify`，保持同一参数文件、配置与持久化目录。命令退出码：0 为已确认或已存在，2 为待核对，1 为失败；以输出的具体 `status` 为准。

## 验证范围

本地测试覆盖实际 SM2 密钥生成/签验、文档字段、参数校验、内部认证、写入闸门、先记录后提交、私钥不进入响应、记录冲突、重启重试与未知结果不重发。测试链读写使用测试源码内的 FakeDidSdk，不代表供应方实链已写入。真实链提交需在实际配置与授权明确后执行，以真实 txId 和回读结果为准。

## 历史联调记录（已解决，不作为当前配置）

当前有效目标为通道4、orderer-1；本节保留通道3及早期失败诊断以便追溯。

- 固定 methodId 为用户确认的 `kmsdid`，不是每次随机生成。
- 来源为 `sdk_java_new.yml`；该文件两个公网 url 缩进到节点同级，只在独立连接副本中修复。运行副本仅选公网 orderer-0-baas1 和 peer-1-baas1，TLS 证书及名称覆盖保留供应方原值。
- Java 8u152 在国密库初始化阶段缺少内部方法，Java 8u481 在 TLS 阶段缺少内部方法；隔离 Zulu JRE 8u302 后，peer 和 orderer 只读访问通过。未修改系统默认 Java。
- 运行时下载自 `https://cdn.azul.com/zulu/bin/zulu8.56.0.21-ca-jre8.0.302-win_x64.zip`，SHA-256 为 `4885567e6ca047e437b55c42919c20979bbe02cca2a3b66916e84b2b3f5df35c`。
- 新增 SDK 异常兼容：String 构造的 `DidSdkException` 可能 errorCode/errorMsg 均为空，仅 message 为 `400001|DID不存在`；严格识别该已知码，不把所有异常都当不存在。
- 创建请求的 evaluate 模拟被合约接受，且成功读取 orderer 通道配置；**这两项均为非提交检查，不是上链成功证明**。
- 真正提交及一次受控恢复均返回 `900000|区块链异常: Failed to send transaction to the orderer`。只使用一套新生成管理密钥、一组 txId/nonce。
- 原 txId 为 `165ebf6613c74422c90ada71e88c47b6d4e1fb2420ab8cec5ad62b732b58a660`，账本查询返回 `Entry not found in index`，DID 尚未查到，状态仍为 `PENDING_VERIFICATION`。
- 需要供应方协助确认 AtomicBroadcast/Broadcast 公网映射、orderer 错误日志以及该身份对 didchannel3 的写入权限。没有据此断言一定是权限问题或服务器故障。

受限运行目录为 `kms-ops/fabric-did-secrets/syspid-kmsdid`，包含身份及独立 DID 管理私钥、原交易计划，已由 Git 忽略。不要对外发送该目录，不要删除后重新生成交易。公开结果保存在项目根目录 `output/did-parameters/chain-submission-result.json`。

准备新的本机运行目录（目标目录必须不存在；只落盘，不连接网络）：

```sh
java -cp '<主JAR与完整lib的classpath>' com.kms.fabricdid.PrepareSysPidRuntime \
  '<sdk_java_new.yml绝对路径>' '<新的受限运行目录>' \
  didchannel3 didchaincode3 kmsdid '<sysPid参数文件绝对路径>'
```

Windows classpath 以分号分隔，Linux 以冒号分隔。准备工具保存的写开关默认为 false。

查询原交易使用下列命令；`check` 查询 DID，`network-check` 读取 orderer 配置，`preflight` 仅 evaluate 模拟创建，`verify` 核对原交易。只有显式 `onchain` 或 `retry` 子进程临时开启写入，其他服务的环境和默认开关均不改变。

```sh
python kms-fabric-did/tools/sys_pid.py verify \
  --runtime kms-ops/fabric-did-secrets/syspid-kmsdid \
  --sys-pid-file output/did-parameters/controller-public-key.hex.txt \
  --java '<兼容的java可执行文件绝对路径>'
```

## 提交错误诊断

2026-10-17 用户确认后，对原交易仅受控重试一次，新日志捕获
`SSLHandshakeException: No subject alternative DNS name matching orderer-0-baas1 found.`。
本次提交失败明确发生在 TLS 主机名校验阶段，不能再仅笼统归为未知链异常；
目标名设置与供应方 YAML 一致，下一步需核对公网端口实际映射和服务端证书 SAN。
未关闭 TLS 校验、未改链配置，仍未获得链上成功确认。对外可用的简要记录见
`../output/did-parameters/retry-diagnostic-20261017.md`。

已补齐与 SLF4J API 匹配的 `slf4j-simple 1.7.30`，Commons Logging 统一通过
`jcl-over-slf4j` 转接，并排除重复的 `commons-logging` 实现。重新打包部署时应替换完整
`lib` 目录，不能把旧 `commons-logging` 或其他 SLF4J binding 混入新依赖。
不修改供应方 JAR、原上链调用、TLS 校验或任何链端配置。

默认只记录 WARN/ERROR。SDK 的 OrdererClient 在包装异常之前记录传输错误和异常，
Channel 记录广播响应的状态和说明；这些日志不再因缺少 binding 而被 NOP 丢弃。
DidService 仅用错误消息构造新异常，已丢掉的 cause 无法从外层恢复；因此必须同时保留
底层日志和外层异常报告，不能仅依赖 `DidSdkException.getCause()`。

每次通过 `tools/sys_pid.py` 执行时，在受限运行目录下新建
`diagnostics/<UTC时间>-<操作>-<随机后缀>/`，终端 JSON 的 `diagnostics` 字段指向该目录：

- `sdk.log`：带时区时间戳的 SDK WARN/ERROR 与命令输出；落盘前屏蔽 PEM、常见私钥/令牌字段及环境中的令牌值。
- `exceptions.json`：发生可捕获异常时生成，按事件保留最多 16 次失败；包含原因链、suppressed 异常、有限堆栈、可见的 gRPC 状态码。没有异常时该文件可以不存在。不保存 gRPC trailers。
- `result.json`：本次结果，包含超时结果。诊断目录不覆盖以前的记录；原操作的 `<operation>-result.json` 仍保留最近一次正常返回结果，超时以本次目录为准。

诊断材料只保存在受限本机目录，不作为 HTTP 响应或静态文件发布。原始身份和私钥目录
仍不可对外发送；脱敏后的日志也应人工复核再交给供应方。

只读 `verify` 可以验证诊断链路，但不能重现 Broadcast 写入故障。旧提交没有保存的
底层原因无法事后还原；需经操作员明确确认后执行一次原交易的受控 `retry` 才能捕获
当前提交错误。补齐日志和测试期间不自动执行 `retry`，不生成新的 txId/nonce/管理密钥。

## 通道4配置切换（2026-10-19）

提供方新参数为 `channelName=didchannel4`、`chaincodeId=didchaincode4`、
`methodId=yunId`、`userName=peer-1-baas1`、`mspId=baas1`，大小写原样保留。
新来源为 `无证书课题项目did演示环境网络-didadminSDK文件/sdk_java.yml`，
SHA-256 为 `cf370005b37c6a5138df931765826219ecc32221803521b7e71cb577f54057e8`。
该文件补齐了通道4的 peer；所选应用证书、私钥和 TLS CA 与通道3运行资料一致。

配置生成工具新增四参数形式：

```sh
java -cp '<主JAR与完整lib的classpath>' com.kms.fabricdid.PrepareSysPidRuntime \
  '<sdk_java.yml绝对路径>' '<新的受限运行目录>' \
  '<kms-fabric-did/config/syspid-target.properties绝对路径>' '<sysPid参数文件绝对路径>'
```

目标参数文件记录提供方身份及此前已提供的公网映射。新 YAML 的节点地址为内网
`192.168.11.234:30034`、`192.168.11.234:30039`；本次本机 TCP 检查超时。
此前公网 `122.224.205.114:18134`、`:18139` 可连接，但这不等于 TLS 或上链成功。
生成器只修改运行副本的 URL，不修改原 YAML、TLS CA、主机名覆盖或校验设置。
原六参数形式仍兼容；新形式验证必需身份参数、MSP 一致性及 grpcs 地址。

通道4使用独立目录 `kms-ops/fabric-did-secrets/syspid-yunId-channel4`，不得迁移或覆盖
通道3的 txId、nonce、管理密钥和记录。生成后的写开关仍为 false；只有显式 `onchain`
子进程临时开启写入。用户本轮已授权修改并重新测试提交；真实结果以该新通道的交易核验为准。

本次新增 7 项配置生成回归测试，合计 50 项 Java 测试和 3 项 Python 测试通过。
新通道 orderer 配置读取及 DID 查询可用；一次真实提交仍报同一 TLS SAN 名称不匹配，
随后核验未查到交易与 DID，未自动重试。新 txId 为
`c8d71eb02674be41eab59a05a3909faa895d53aff6658cc7e88dad5d29d3faaf`。
完整非敏感记录见 `../output/did-parameters/channel4-submission-20261019.md`。

随后用户确认公网映射：peer-1 为 `:18139`，orderer-0 为 `:18134`，与本次运行副本一致。
只读国密 TLS 探针实测 `:18134` 返回的证书 DNS SAN 却为 `orderer-1-baas1`；
使用原供应方 CA 与该 SAN 名称时，严格 TLS 握手通过。`:18139` 返回的 SAN 为
`peer-1-baas1`，与配置一致，严格握手同样通过。此证据定位到 orderer 端证书身份不一致，
不单凭证书断言端口实际对应 orderer-1。未修改业务配置或重试交易；待提供方确认正确 TLS 名称。

### 最新结果：orderer-1 已上链成功

用户随后明确授权使用 `orderer-1-baas1` 上传。目标配置新增 `ordererName`，生成器校验通道
orderer 列表并选用 YAML 中相应节点的 TLS 设置；默认值仍保留原六参数调用的兼容行为。
运行副本切换到 orderer-1，原 CA 与公网地址保留，原连接文件已备份，未关闭 TLS 校验。
52 项 Java 测试与 3 项 Python 测试通过。

对同一 txId `c8d71eb02674be41eab59a05a3909faa895d53aff6658cc7e88dad5d29d3faaf`
先核验，再受控重试一次；没有生成新管理密钥或 nonce。重试结果与随后独立 JVM 只读复核
均为 `CONFIRMED`、`transactionValid=true`、`metadataMatches=true`。
运行目录默认写开关保持 false，旧通道3记录未修改。
结果副本：`../output/did-parameters/channel4-confirmed-result-20261019.json`。

### 服务器部署状态

最新程序与受限身份材料已上传 `/home/rbf/kms-sys/releases/did-channel4-20261019`。
灰度检查发现并修复Windows/Linux证书PEM换行导致的原交易ID校验差异；60项Java测试通过。
核验只兼容同一MSP/同一证书的LF与CRLF序列化，不忽略nonce校验；创建/重试仍强制SDK产生原txId。
服务器到供应方 `122.224.205.114:18134/18139` 连接超时，而本机正常，正式服务尚未切换。
详细状态见该发布目录 `RESULT.md`；网络开通后先灰度实时回读，再部署。
