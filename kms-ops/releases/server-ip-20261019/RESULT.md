# 服务器 IP 访问配置已更新

日期：2026-10-19（Asia/Shanghai）。新地址为 `10.129.114.144`。

- 业务演示页：<https://10.129.114.144:8443/updatedel/demo>
- 验收页：<https://10.129.114.144:8443/acceptance/>
- HTTP 80/8088 均以 308 跳转到新 IP 的 HTTPS 8443。
- 已更新 Docker 网关端口发布、挂载的 Nginx 模板、4 个后端服务的 Host/Origin 白名单。
- 新站点证书 SAN 为 `IP:10.129.114.144`；原证书与私钥保留在原目录。
- 无需重建镜像：当前网关从挂载模板生成 Nginx 配置；已重建网关及 4 个需更新环境变量的客户端服务。
- 从服务器与用户电脑均以新证书严格验证 TLS，`/ping`、`/updatedel/demo`、`/acceptance/` 均 HTTP 200。
- 其他容器 ID 保持不变，未修改数据库或链上业务数据。

服务器配置：`/home/rbf/kms-sys/docker-compose.yml`。
新模板与 TLS：`/home/rbf/kms-sys/server-access-ip-20261019`。
受限备份：`/home/rbf/kms-sys/releases/server-ip-20261019/backup`，包含服务凭据，不外发。
可分发的公有证书：本目录 `kms-server-10.129.114.144.crt`。

证书 SHA-256 指纹：
`72:EA:C1:07:8C:5D:E5:49:B7:F2:0D:35:28:7F:AE:6C:C5:58:A1:21:E7:D4:AA:17:AA:54:84:23:6A:33:38:C9`。

## 浏览器本机密钥的入口变化

用户确认原生成节点A材料的地址为 `https://10.112.125.22:8443/updatedel/demo`。
改用新IP后，浏览器origin发生变化，即使同一浏览器配置也不能共享IndexedDB中的节点私钥。
新站点的页面200和证书有效不代表原本机密钥已迁移。代码使用 `kms-demo-node-keystore`，
保护密钥为不可导出的CryptoKey；不能只复制密文或安装HTTPS证书来恢复。
原站点数据是否仍在，尚未检查浏览器数据库；不得宣称私钥已经丢失。保留原浏览器资料，
后续按受控恢复旧入口或明确迁移方案处理，不自动重建密钥或覆盖已登记公钥。

## MySQL 故障历史

更新：用户随后已修复 MySQL；2026-10-19 17:14（Asia/Shanghai）再次检查 MySQL 和两个 Java 服务均 running。
下述内容保留为此次 IP 修改时的故障记录，已不代表当前容器状态。

MySQL 在此次修改前已反复重启，日志为 `io_setup() failed with EAGAIN`、
`Cannot initialize AIO sub-system`。系统 AIO 已使用 64184/65536，剩余额度不足。
依赖该数据库的两个 Java 服务也仍在重启。此次更新已恢复页面访问，不能据此宣称全部业务接口恢复。
未在本次 Nginx/IP 修改中调整内核限制或数据库设置。
