# Fabric 国密 DID 离线接入交付与实链联调入口

## 当前结论

**已实现接入适配，不等于已替换到在线 Fabric。** 实际 connection、MSP/TLS 身份和通道/链码参数、可读取 DID 尚未提供；本轮不连接真实 Fabric、不提交真实 DID、不批量迁移现有节点。

默认 `KMS_CHAIN_BACKEND=legacy`，原 FISCO/Web3 代码、历史配置和交易记录保留。选择 `fabric-did` 时在旧 SDK 构造/部署/写入前拒绝，禁止悄悄回退；当前 DID 能力为读取和经批准的应用专属 create-only 绑定，当前节点可变投影、DID 更新/停用及完整旧生命周期事件等价均为 **UNSUPPORTED**。

## 代码与依赖

- `kms-fabric-did/`：独立 Java 8 进程、内部认证、严格 metadata、懒加载供应方 SDK、prepare/submit/verify、无配置诊断；完整 API 见该模块 README。
- `jarFile/`：原供应方 Maven 文件仓库，不修改 JAR、不把定制 SDK 换成普通 Fabric 包。`gmssl` 是 POM 聚合依赖，不应补造 JNI。
- `kms-distribute/dvadmin/backend/pqkds/chain_backend.py`：唯一选择器；未知配置拒绝，不默认回旧链。
- `chain_binding_service.py` / `fabric_did_client.py` / `ChainKeyBinding`：真实登记事务的 durable outbox 与独立来源证据，不挪用旧 Transaction。
- `node_key_registry` 的首次登记/轮换/回收事务记录公开量任务；链不可用不重生业务私钥，也不把 ACTIVE 与“已上链”混同。
- 两个 Java 服务及旧 Python Web3/BlockchainKDS/初始化脚本均加防误写闸门；旧内部摘要事件接口在 Fabric 模式明确不等价。
- 公钥详情额外显示 `chainBinding`；`CONFIRMED` 是交易有效且 metadata 回读一致，不是提交函数返回字符串。

## 绑定与交易确认

metadata 为规范 UTF-8 JSON，字段包括 namespace/schemaVersion、nodeId、algorithm、逻辑 keyId、keyVersion、完整公钥、登记表字符串 SHA256、状态、事件、修订号和稳定记录时间。白名单构造，不含私钥、SM4 明文、MSP 密钥或设备凭据。

业务四算法公钥和 DID 管理 SM2 公钥不是同一字段。Bridge 使用外置稳定管理公钥与已授权 MSP 交易身份，不为每次提交生成新管理者。

同节点事件按 sequence 处理：

1. 登记数据库事务中写 outbox；回滚时任务也回滚。
2. 显式 worker prepare，保存原 DID/nonce/txId/metadata/digest。
3. 提交前持久化阶段标记；提交超时先查原 txId，不凭回包丢失重写。
4. `CONFIRMED` 要求 provider/chainId/DID/txId/digest 对应原计划，交易 valid=true，metadata 精确相同；错误/不确定不能伪装成功。
5. 同节点失败队头阻挡后续；不阻挡其他节点。租约与回写 token 防旧 worker 覆盖。

create-only DID 的当前格式为 `did:<methodId>:<namespace>:binding:<metadataDigest>`，须先由链方确认。查询业务节点的最新公钥可使用本地绑定索引返回 DID，再读链上记录；本轮不声称链码已支持按 nodeId 查最新投影。外部并发写者/CAS/版本事件权限仍需链方确认。

## 配置与部署

基础环境新增字段见 `kms-ops/.env.example`。默认不开启，不应修改现有 BlockchainConfig.contract_address：其旧 save 行为会清交易和重置节点。

```powershell
mvn -f kms-fabric-did/pom.xml clean package
node tools/verify-fabric-bridge-offline.mjs
```

Bridge 是 thin JAR，部署必须同时带 `target/lib/`，否则签名 provider 与运行依赖缺失。本轮已准备 `kms-ops/runtime/fabric-did/app.jar` 和 `lib/`，没有替换现有服务 JAR。

可选部署：

```powershell
docker compose -f kms-ops/docker-compose.yml -f kms-ops/docker-compose.fabric-did.yml --profile fabric-did config --quiet
# 配置及依赖准备好且取得部署授权后，才启动可选进程：
docker compose -f kms-ops/docker-compose.yml -f kms-ops/docker-compose.fabric-did.yml --profile fabric-did up -d --build fabric-did-bridge
```

初次离线交付时 Docker daemon 未运行；用户启动 Docker 后，提交前已补建独立 Bridge 镜像，并用仅本次创建的临时容器完成 **5/5** 检查（启动、认证、未配置、禁止写入、独立 Java 8）。临时容器已清理，未改现有业务容器或启动真实链；Compose 配置也已验证。

SDK 固定读取工作目录父目录配置；进程在 `/run/fabric-did/work`，实际材料只读挂载到 `/run/fabric-did/`。`kms-ops/fabric-did-secrets/` 默认只有 README 和空 work 目录，真实文件被 Git 与本机构建上下文排除，不进入镜像/前端/日志。

本机 8u152 已通过离线 JVM/HTTP 行为测试，不代表国密 TLS 兼容。实链按链方建议使用并验证 Zulu 8u302+，不得通过关闭 TLS 校验解决错误。

## 迁移与任务处理

新迁移：`pqkds/migrations/0026_chain_key_binding.py`。本轮未应用到现有数据库、未删除/修改旧交易或配置。

迁移审核并在测试环境验证后才执行：

```powershell
# 以下命令待运行环境恢复和数据库变更确认后执行，不是本轮已执行证据。
docker exec -w /backend dvadmin3-django python manage.py migrate
docker exec -w /backend dvadmin3-django python manage.py process_chain_bindings --limit 100
```

worker 默认 legacy 不处理 Fabric 队列；选中 Fabric 但缺参数明确 NOT_CONFIGURED。空 chainId 老任务不自动改成新链证据；切换新 chainId/namespace、准备响应丢失或不确定提交须明确核对/处置，不能凭改环境变量伪造确认。

## 本轮验证分层

- DID Bridge：17 项离线单测，含 fake SDK 与真实 loopback HTTP prepare→submit→verify。假链只存在于测试源码，不是生产模拟确认模式。
- 主会话实际启动独立 JVM：关闭与未配置两种状态共 8 项 HTTP 检查，认证/禁止读取/不假连通通过。
- 现有 Java：生命周期 18 项、生成 6 项，包含之前 Demo 测试和新增 8 项链切换保护，clean package 均成功。
- Python：隔离虚拟环境，**45/45** 内存 SQLite 真实模型/约束/登记事务、模拟 Bridge 和本机 HTTP 测试，加 **9/9** 旧入口保护；不读取 application.settings、不连接现有 MySQL。SQLite 不证明 MySQL 并发锁语义。删除源节点/密钥仍可保留公开量证据，未提交孤儿任务明确失败，不向链补写；旧 keyRef 不能借给重建后的不同密钥。
- 前端生产构建/大小写与 Compose 静态配置验证通过；由于 Docker 未运行，本轮没有部署/驱动新的完整前后端 UI，不能冒充已回归运行中系统。

## 链方仍需提供

1. 原始完整依赖若新增/变更：定制版本及传递依赖仓库/校验信息，不仅 SDK 主 JAR。
2. 实际 connection.json、应用 MSP enrollment 证书/匹配私钥、TLS CA/GM 配置；实际 channelName、mspId、chaincodeId、methodId。
3. 一个测试链既有 DID **原样字符串**，先验证读取；读取失败/不明确状态不能当作“无此 DID”而覆盖。
4. metadata 是否允许自定义 JSON、最大 UTF-8 字节数、保留/查询还原语义；DID 标识格式、create-only/停用后重建规则。
5. DID holder/controller 权限和更新提案签名方式、交易 valid 与 payload 归属查询、单写者/CAS 政策。

后续顺序：配置诊断 → 既有 DID 只读 → 另获自有测试命名空间写入授权 → 公钥/版本/状态逐字回读与交易验证 → 再确定正式切换及剩余生命周期能力。不覆写链方给的既有只读 DID，不开发新的业务链码，不以离线 fake 的结果宣称实链成功。
