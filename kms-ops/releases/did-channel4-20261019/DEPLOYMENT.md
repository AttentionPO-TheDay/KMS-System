# DID 通道4服务器部署

当前状态：程序及身份材料已传服务器，正式切换被灰度检查拦截，尚未启用。
2026-10-19 重试：服务器与容器的公网 `18134/18139` TCP、国密 TLS 证书和主机名校验均通过；
Fabric SDK gRPC 查询仍超时，返回 `PENDING_VERIFICATION / DID_READ_FAILED`，尚未正式切换。
初次灰度另发现 Windows/Linux 证书 PEM 换行差异造成原交易校验失败，已补严格兼容与回归测试。
本目录已有 `backup`/`payload`，不要直接重复运行一次性 `apply.sh`；应保留原备份并恢复剩余发布步骤。

仅部署 `fabric-did-bridge`，不重启其他 KMS 服务。使用已验证的 `didchannel4` / `didchaincode4` /
`yunId`，orderer TLS 名称为 `orderer-1-baas1`，地址 `122.224.205.114:18134`；
peer 为 `peer-1-baas1`，地址 `122.224.205.114:18139`。保留供应方 CA 与 TLS 主机名校验。

服务器：`expert-machine`（`10.129.114.144`），部署根目录 `/home/rbf/kms-sys`。
本发布目录：`/home/rbf/kms-sys/releases/did-channel4-20261019`。

## 查询与日常管理

查询参数保存在本目录 `query-parameters.json`，不含令牌和私钥。
完成正式切换后，在服务器执行：

```sh
python3 /home/rbf/kms-sys/releases/did-channel4-20261019/query_confirmed.py
```

保存最近一次非敏感查询结果：

```sh
python3 /home/rbf/kms-sys/releases/did-channel4-20261019/query_confirmed.py --save
```

期望返回 `status=CONFIRMED`、`transactionValid=true`、`metadataMatches=true`，
交易 ID 为 `c8d71eb02674be41eab59a05a3909faa895d53aff6658cc7e88dad5d29d3faaf`。
脚本仅在内存读取已有容器令牌，访问内网核验接口，不提交新交易、不显示私钥或令牌。

若需要手动管理该服务，必须带新覆盖文件，防止回退到默认未配置状态：

```sh
docker compose -p kms-ops \
  -f /home/rbf/kms-sys/docker-compose.yml \
  -f /home/rbf/kms-sys/docker-compose.fisco-enabled.yml \
  -f /home/rbf/kms-sys/docker-compose.did-channel4.yml \
  --profile fabric-did ps fabric-did-bridge
```

## 运行与安全约束

- 镜像：`kms-fabric-did:channel4-20261019`，兼容标签 `kms-fabric-did:local`。
- 回滚镜像：`kms-fabric-did:before-channel4-20261019`。
- DID 服务启用查询，三个写开关仍为 false，不开启批量或自动上链。
- 原服务器内部令牌不变，不发布 DID 主机端口，仍使用 Docker 私有网络。
- 敏感材料位于 `/home/rbf/kms-sys/fabric-did-secrets/syspid-yunId-channel4`，目录0700、文件0600。
- 身份挂载只读；`work` 和 `records` 子目录可写，以保存核验记录和进程锁。
- 管理私钥和原交易计划从本机迁移，保留原 DID、txId、nonce 和管理密钥，不重建标识。
- 不要公开 `identity.tar.gz`、`backup` 或身份目录。它们不进入程序镜像或 Git。

## 发布验证

`apply.sh` 在独立内网 canary 容器中先验证链上记录，然后只替换正式 DID 容器。
最新程序应运行60项 Java离线测试、3项 Python测试，检查私有接口鉴权、禁写闸门、JAR 摘要、
门户 TLS 页面与其他16个服务的容器ID/启动时间均不变。失败时自动恢复原镜像和未启用配置。
本次服务器和网关已变更 IP；恢复发布前需刷新基线，保留最初备份，并将检查脚本的门户地址更新为新 IP。

回滚不会删除新身份或交易资料。如需主动回滚，先保留本次查询结果，然后将新覆盖文件归档，
把 `kms-fabric-did:before-channel4-20261019` 恢复为 `kms-fabric-did:local`，
使用原两个 Compose 文件仅重建 `fabric-did-bridge`。本发布不修改业务数据库、FISCO或其他容器。
