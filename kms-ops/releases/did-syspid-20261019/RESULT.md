# 服务器部署结果（2026-10-19）

已部署到 `expert-machine`（`10.112.125.22`），发布目录：
`/home/rbf/kms-sys/releases/did-syspid-20261019`。

- DID 容器：`kms_fabric_did`，运行正常，复查时 RestartCount=0。
- 新镜像：`kms-fabric-did:syspid-20261019`，同时更新 `kms-fabric-did:local`。
- 镜像 ID：`sha256:8cf3ab805bc954c1bf8bf127ef156f4d2be667627ba967cdb1f28f6bd97c2eef`。
- 主 JAR SHA-256：`8e714fd7183f23a5bc2ef462a2a49dac65b299126c79b3bc6e7c9fc6bdb7eb59`，与本地构建一致。
- 隔离 Linux Zulu JRE 8u302，未更改宿主机或其他容器 Java。
- 服务器禁网容器中的 43 项 Java 测试通过，3 项脚本测试通过。
- 新 SysPid 路由、内部令牌鉴权、禁写闸门、CLI 入口验证通过。
- HTTPS `/ping`、`/updatedel/demo`、`/acceptance/` 返回 200，证书校验通过。
- 其他 16 个 KMS 容器的 ID、启动时间、状态与发布前一致。
- 旧镜像已保留为 `kms-fabric-did:before-syspid-20261019`；回滚命令见 DEPLOYMENT.md。

服务器原有 DID 禁用状态和身份挂载保持不变。没有迁移本地管理私钥或原交易记录，
没有配置或提交新的 DID 身份，没有触发供应方链访问或重试，也没有改动 FISCO 路由。
等待供应方解决 TLS 证书名称问题后，再配置受限连接材料和持久化目录并另行启用。
