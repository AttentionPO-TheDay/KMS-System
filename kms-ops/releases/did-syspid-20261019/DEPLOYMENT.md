# DID SysPid 与诊断更新（2026-10-19）

只更新 `kms_fabric_did` 镜像；不修改业务前端、Django、FISCO 服务、Compose 配置、
数据库、身份挂载或现有内部令牌。DID 保持 DISABLED，三个写入开关保持 false。

包含之前实现的 SysPid 接口、原交易核对/显式恢复、SM2 管理密钥及持久化代码、
完整供应方 SDK 依赖、日志实现、脱敏诊断工具和操作说明。服务器只部署程序，
本地 `syspid-kmsdid` 中的原交易记录/管理私钥不迁移；等待供应方修复 TLS 配置后，
还需明确选择并配置持久化目录和受限连接材料，才能在服务器执行真实链调用。
不能在服务器另建同一 SysPid 的身份来替代本地原交易。

镜像沿用现有 Linux 基础层，在独立路径加载新版程序及固定 Linux Zulu JRE 8u302，
不加载旧 `/app/lib`，不修改宿主机 Java。JRE 来自 Azul 官方 CDN，其 metadata API
包 UUID 为 `6faf2f16-6d0a-484a-b88c-321b85c43ed5`，官方 SHA-256：

```text
9a0d0eb753c3592faca48d5e9b84bcf5b92301fd09081b191623cb8e478349d7
```

使用旧版 Java 是供应方国密依赖的兼容性约束，不代表建议其他服务使用旧 JRE。
Bridge 仍只开放容器内网端口，无公网映射；后续应由供应方升级依赖以支持受维护运行时。

服务器发布：`bash /home/rbf/kms-sys/releases/did-syspid-20261019/apply.sh`。
发布前验证 SHA-256、现有禁写状态及 Compose 环境一致性，备份旧镜像和受限容器快照。
先在禁网容器内执行 43 项 Java 离线测试，再执行 3 项脚本测试。
发布后验证主 JAR 摘要、新路由的鉴权/禁写响应、HTTPS 页面及其他容器未变更。
测试请求不会进入供应方 SDK 或生成密钥/交易。验收失败自动回滚 DID 镜像。

手动回滚（不恢复或删除任何数据）：

```bash
docker tag kms-fabric-did:before-syspid-20261019 kms-fabric-did:local
docker compose -p kms-ops \
  -f /home/rbf/kms-sys/docker-compose.yml \
  -f /home/rbf/kms-sys/docker-compose.fisco-enabled.yml \
  --profile fabric-did up -d --no-deps --no-build --force-recreate fabric-did-bridge
```

`backup/snapshot.json` 含环境凭据，不能对外发送。`payload/module/` 只含程序、依赖、工具、公开目标参数和文档，不含 YAML、私钥或运行记录。
