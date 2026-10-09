# 外置 Fabric DID 测试链材料

本目录当前只有说明和空工作目录，不包含真实连接/身份配置。不要把文档示例网络当测试链。

后续由链方提供并通过受控渠道放置：

- `fabric.config.properties`：实际 `channelName/mspId/chaincodeId/methodId` 和文件路径；
- `gm-sdk.properties`、`connection.json`、TLS CA 配置/证书；
- 应用专用 MSP enrollment 证书及匹配私钥（不是擅自复用 peer 节点身份）；
- 稳定 DID 管理 SM2 公钥 `controller-public.pem`；
- 如需 DID 更新，另行确认管理私钥/提案签名规则及权限。本轮更新/停用不冒充支持。

所有真实文件均被本目录 `.gitignore` 排除；不要粘贴私钥到对话或日志。使用只读挂载，主 JAR/lib 不放这里。
`work/` 必须保留为进程工作目录，SDK 从它的父目录读取配置。文件内部应使用容器内实际绝对路径。

先提供可只读验证的完整 DID 原样字符串。只有读取得到正确文档、链方明确允许 metadata JSON 及长度/命名空间/创建语义、并获得测试写入授权后，才能打开写开关。

没有配置、开启状态或健康 HTTP 200 都不代表已经连通 Fabric；见 `kms-fabric-did/README.md` 的分层验证说明。
