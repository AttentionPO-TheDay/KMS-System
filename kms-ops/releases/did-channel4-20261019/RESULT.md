# 发布结果：已重建候选，待服务器 gRPC 查询通过后切换

日期：2026-10-19（Asia/Shanghai）。本机通道4上链与独立回读已成功，本发布不新增链记录。

## MySQL 修复后的再次验证

用户修复 MySQL 后，于 2026-10-19 17:14（Asia/Shanghai）再次查询：MySQL 和两个 Java 服务均 running。
服务器灰度查询仍在 68.90 秒后返回 HTTP200、`PENDING_VERIFICATION / DID_READ_FAILED`，
`transactionValid` 和 `metadataMatches` 均为 null；SDK 仍报 `UNAVAILABLE / Connection timed out`。
本机同期回读原交易仍为 `CONFIRMED / true / true`。鉴权与禁写闸门检查通过；未正式切换，未新增链交易。
本次临时容器已退出。结果见本目录 `mysql-fixed-retry-result.json`，本地副本位于 `output/did-parameters/`。

## 已完成

- 程序包、最新主JAR、完整依赖、原身份材料和管理密钥/交易计划已传服务器，摘要核对通过。
- 身份目录0700，文件0600，不进入镜像或Git，不公开私钥或令牌。
- 回滚镜像 `kms-fabric-did:before-channel4-20261019` 已保留。
- 本机及服务器60项Java禁网测试通过，另有3项Python测试通过。
- 新增严格的Windows/Linux PEM换行兼容：只允许同一MSP、同一证书的LF/CRLF创作者序列化核验。
- 原证书与nonce的SM3重算：CRLF匹配原txId，LF不匹配；修复后的生产匹配函数在服务器禁网实参核验中通过。
- 创建/重试仍要求当前SDK产生原txId，否则返回 `SYSPID_SIGNER_SERIALIZATION_CHANGED`，不会偷偷发出另一笔交易。
- 可查询参数保存在本地 `output/did-parameters/DID_QUERY_PARAMETERS.md`，服务器本目录 `query-parameters.json`。
- TLS临时探针与身份序列化探针归档至本机 `.omc/did-archive/20261019`，可恢复，未删除交易或管理密钥。

## 最新重试（服务器 IP 已为 10.129.114.144）

- 候选镜像已从最新修复 JAR 重建，JAR SHA-256 为 `7b0c1e1c9d6b81fd5964811fd7c30f23564423b38e03fda391be23b679ad9c3a`。
- 重建后 60 项 Java 禁网测试、3 项 Python 测试通过。
- 服务器主机与容器到两个公网端口的 TCP 均通过；容器内国密 TLS 探针严格校验供应方 CA 及节点主机名，两个节点均 `TLS_IDENTITY_VERIFIED`。
- 同时本机按现有运行脚本再次只读回读原交易，结果 `CONFIRMED / transactionValid=true / metadataMatches=true`。
- 服务器实际查询返回 HTTP 200，但业务状态为 `PENDING_VERIFICATION`，交易及文档匹配结果均为 null，错误 `DID_READ_FAILED`。
- SDK 错误为 gRPC `UNAVAILABLE / io exception / Connection timed out`，等待通道配置及 peer 查询响应超时；不能认定是证书或链记录错误。
- 禁用 Netty native transport 的临时 Java NIO 对比仍超时；仅绑定 127.0.0.1 的 host-network 临时容器也未查询成功，尚无证据将问题归因于 Docker bridge。
- 正式 DID 容器保持原 disabled 镜像，三个写开关关闭。没有提交新交易，所有临时 DID 容器已退出。
- 另按用户要求完成新 IP 的网关端口、Nginx、TLS 与 4 个服务白名单更新，见相邻 `server-ip-20261019/RESULT.md`。恢复 DID 发布需保留旧基线并另建本次基线，门户检查改用新 IP。

## 首次部署的历史阻碍（当前 TCP/TLS 已恢复）

服务器主机与灰度容器均无法连接供应方公网节点，而当前电脑可以连接：

```text
122.224.205.114:18134  orderer-1-baas1  server TCP timeout; local PC reachable
122.224.205.114:18139  peer-1-baas1     server TCP timeout; local PC reachable
```

YAML中的内网备选地址 `192.168.11.234:30036`、`:30039` 从服务器也连接超时。
需由服务器/网络管理员及供应方确认路由、服务器出站策略或供应方入口白名单；
没有据此确定是哪一侧阻断，没有更改服务器防火墙或建立旁路隧道。

初次灰度在原交易校验中被409拦截；该跨平台问题已修复并上传最新JAR，但正式切换仍等待网络。
首次失败时镜像尚未包含最新修复；最新重试已重建，详见上文。

## 首次部署时的生产保护状态（历史）

- 正式 `kms_fabric_did` 的容器ID/镜像未变，仍保留原disabled配置。
- 其他16个容器的ID、启动时间、状态与发布前完全相同。
- 新Compose覆盖文件尚未安装，`applied`标记不存在。
- 临时灰度和诊断容器已退出；没有新增链上交易、没有重建SysPid或管理密钥。
- 原门户 `/ping`、`/updatedel/demo`、`/acceptance/` 以原CA进行TLS校验后均HTTP200。
- 受限备份 `backup/snapshot.json` / `backup/canary.env` 不得外发。

## 后续步骤

1. TCP/TLS 已通过，继续定位服务器 SDK gRPC 超时；未查明前保持正式 DID disabled。
2. 保留现有身份、备份及原交易，不直接重复运行一次性 `apply.sh`。
3. 候选镜像已重建，沿用原 `before-channel4-20261019` 回滚点；刷新发布基线并修正门户检查 IP。
4. 用现有 `backup/canary.env` 启动同配置、默认禁写的独立灰度容器，执行 `check_deployment.py canary`。
5. 只有灰度实时回读原交易为CONFIRMED后，安装覆盖文件、仅重建 `fabric-did-bridge`，运行after检查。
6. 执行 `query_confirmed.py --save` 留存服务器实时核验结果；不能把本机成功凭证冒充服务器实时查询。
