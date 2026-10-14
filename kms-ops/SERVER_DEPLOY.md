# 全新服务器部署（镜像包）

## 本机打包

Windows PowerShell 7，在项目根目录执行：

```powershell
pwsh -File .\kms-ops\ship.ps1 -Rebuild -WithBaseImages
```

`-Rebuild` 从当前源码构建 Java、Go、前端与 DID SDK thin JAR/lib，再构建 Docker 镜像，不会启动或替换本机容器。构建需要 Maven、Go、Node/npm、Docker 及依赖下载网络。默认包含 DID，共 8 个应用镜像。不要仅复制 DID 主 JAR，国密 provider 必须保留原始签名依赖。

如已核对所有镜像为最新，可省略 `-Rebuild`。`-SkipImages` 仅用于验证配置包，不能单独作为完整部署交付。`-WithoutDid` 可显式排除 DID。

若 npm 出现自身模块缺失（例如 `make-fetch-happen/lib/cache/policy.js`），不是项目依赖错误。构建开始前会检查 npm 安装模块能否加载；可使用 `-NodeHome '完整 Node 安装目录'` 指定健康安装（该目录内有 node.exe 和 node_modules/npm），不改变全局 NVM。仅能执行 `npm --version` 不代表安装完整。

上传 `kms-ops/dist/` 内的 `kms-images.tar`、`kms-deploy.tar.gz`、`kms-base-images.tar`、`MANIFEST.txt`、`SHA256SUMS`。镜像包含所有应用代码，无须上传源码、node_modules 或本机数据库。

## 服务器安装

目标为 Linux amd64，安装 Docker Engine 和 Compose 插件。上传到新目录 `/opt/kms`，不要覆盖已有运行实例的配置：

```bash
cd /opt/kms
sha256sum -c SHA256SUMS
tar -xzf kms-deploy.tar.gz
chmod 600 .env
docker load -i kms-images.tar
docker load -i kms-base-images.tar
sudo bash deploy.sh check
sudo bash deploy.sh up
sudo bash deploy.sh verify
```

修改 `.env` 中开发口令/令牌后再启动。公网入口尚需按实际域名配置 HTTPS、Nginx server_name/跳转、Host/Origin 白名单与 Secure Cookie。默认仅回环访问，不应直接发布数据库、Redis、Kafka、链 RPC 或 DID Bridge。

## 全新数据与链

包不含 MySQL/Redis/Kafka 运行数据，不含 node*/data 或 log。FISCO 仅带启动二进制、节点配置、创世配置和证书，节点身份是现有配置，不代表新生成的身份。输出 `.env` 清空本机旧合约地址/账户私钥，合并后的 Compose 暂停链写入，不影响 Django migrate。新链启动不代表已有合约，需另外部署合约并审核启用写入。

数据库初始化保留菜单、角色等系统配置；历史示例密钥不初始化。此包不做数据迁移，亦不迁移浏览器 IndexedDB 私钥。

### 连接已经部署的 FISCO 合约

将 `connect-existing-fisco.py` 单独上传到服务器部署目录。无需重打包镜像，
不要再次运行会部署新合约的 `deploy-keyevidence.sh`。服务器需要 Python 3、
已启动的 `kms_fisco_console` 和 `dvadmin3-django`。

```bash
cd ~/kms-sys
sudo python3 connect-existing-fisco.py --contract <合约地址> --owner <部署账户地址>
# 审核完后再执行同一命令并添加 --activate
```

脚本查询真实合约 owner，并从指定 `fisco/console/account/ecdsa/<owner>.pem`
解析 secp256k1 账户、派生地址核对 owner；不打印私钥。它以 LF 和 0600 权限
更新 `.env`，保存权限受限的配置备份，写入独立 FISCO overlay，并针对服务器
`deploy.sh` 的两个 Compose 入口加入该 overlay，避免下次启动又关闭写入。
Compose 验证失败会恢复配置。不要发布 `.env`、账户 PEM 或配置备份目录。

`--activate` 只重建两个 Java 服务（`--no-deps --no-build`），开启生成及生命周期
存证消费者，可能处理既有队列。它不启动节点、不部署合约、不清空数据库。
Django 的独立旧 Web3 和 DID 写入保持原关闭状态，不以 FISCO 开关代替 DID 集成。
配置核对不等于业务上链成功；仍需用一条非敏感业务测试记录核对交易回执。

### 绑定服务器地址（含浏览器密钥功能所需 HTTPS）

将 `expose-server.py` 上传到部署目录（同目录保留 `connect-existing-fisco.py`）：

```bash
cd ~/kms-sys
sudo python3 expose-server.py --ip 10.112.125.22 --activate
```

只增加网关在指定 IP 的 80/8088/8443 绑定，保留回环入口及其余服务端口。
服务器 IP 的 HTTP 入口跳转到 `https://10.112.125.22:8443/updatedel/`。
脚本添加精确 Host/Origin 白名单，不使用通配符；保留原 FISCO overlay、
私钥配置和自定义 Docker 子网。无需重新构建镜像。应用 Compose 校验及一次性
Nginx 语法检查通过后，只重建网关及四个需要更新白名单的应用容器。

IP 对应的 TLS server 必须设为 443 的唯一 default_server，否则不发送 SNI
的 IP 客户端会收到镜像内 localhost 证书，使用正确 IP 证书的 `curl --cacert`
也会报自签名验证失败。脚本保留 localhost 的具名入口；重复运行时，白名单
未变化的应用不会重建，仅重建网关，并用证书校验检查 HTTPS `/ping`。

没有正式证书时生成有效期一年的自签名 IP 证书。将公开的 `kms-server.crt`
下载到客户端，核对脚本输出的 SHA-256 指纹，再通过客户端系统证书管理器
手动信任并重启浏览器。不要复制 `server-access/tls/server.key`、`.env` 或备份。
浏览器中应确认 `window.isSecureContext === true` 且 `crypto.subtle` 可用；
仅跳过证书警告不作为安全上下文验收。正式公网访问应换成受信任证书/域名。

`10.112.125.22` 是内网地址，需要客户端具备相应网络或 VPN 路由，端口绑定
不会自动建立公网映射。按实际客户端来源设置服务器及上游访问控制；Docker
发布端口可能绕过部分 UFW 规则，不能仅凭 UFW 状态断言已限制访问。
新 HTTPS 地址与原 localhost 是不同浏览器 origin，不会自动共享 IndexedDB 密钥。

## DID

包带 `kms-fabric-did:local`、内部 Bridge 服务、`fabric-did-secrets/` 配置样例和空 work 目录。`deploy.sh` 识别 `WITH_DID` 并启用服务 profile；没有该标记时保持普通服务启动方式。

实际 SDK 连接配置、证书/私钥不打入镜像或普通部署包，应通过受控方式另外放入 `fabric-did-secrets/`，只读挂载。文件内部使用 `/run/fabric-did/...` 容器路径，详见该目录 README。SDK 默认未启用，写链闸门关闭。Bridge 存活不是实链连通证明。

目前业务功能是 SDK 参数交接包生成/记录，不提交交易；不是接口文档中的 SysPid 标识上链。SysPid 样例和接口参数确认后再适配，不能把业务公钥代替 SysPid，也不能通过打开现有写开关冒充已对齐接口。

打包、启动、检查均不提交 DID 交易。
