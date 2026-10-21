# 服务器地址恢复为 10.112.125.22

2026-10-20 已在原服务器 `/home/rbf/kms-sys` 完成切换。

- 密钥平台：<https://10.112.125.22:8443/updatedel/demo>
- 验收平台：<https://10.112.125.22:8443/acceptance/>
- Docker 网关发布地址由 `10.129.114.144` 改为 `10.112.125.22`，发布端口仍为 80、8088、8443，原回环端口绑定保留。
- 与备份逐项对比，Compose 配置只有 `services.nginx.ports` 三个 `host_ip` 值发生变化。
- 现有 Nginx 模板、TLS 证书、Host/Origin 白名单已支持当前 IP，继续使用。未重建镜像，仅重建 `nginx` 服务；未操作数据库和上链业务。
- 服务器端及 Windows 用户电脑均禁用代理、严格验证 TLS 后，`/ping`、`/updatedel/demo`、`/acceptance/` 和 `/demo-api/lifecycle/demo/context` 返回 HTTP 200，会话配置为 `DEMO`。
- 80/8088 的 HTTP 请求均以 308 跳转至 `https://10.112.125.22:8443`。
- 桌面“KMS旧入口恢复”及工作区源脚本已同步连接 `10.112.125.22`，不再转发至 `10.129.114.144`。保留原 Profile 5/6/7、原站点地址与浏览器密钥数据。两份脚本的 `-CheckOnly -AllNodes` 均通过，证书已信任，无须重新安装。
- 未启动、关闭用户 Chrome。若已有 Chrome 进程仍带上一版 IP 映射，保存工作并完全退出 Chrome 后，再通过已更新的桌面入口进入。

服务器备份与执行结果：`/home/rbf/kms-sys/releases/server-ip-return-20261020-210631-404893`。备份包含 Compose 服务配置，只保留在服务器受限目录，不分发。

证书 SHA-256 指纹保持：`13:0A:20:51:D9:68:A4:6E:DE:55:02:0E:2A:E9:A5:B7:72:7F:6C:6C:A2:DD:B5:DE:30:21:A6:03:8A:D0:38:DB`。

即时执行快照显示其他 82 个容器 ID 与启动时间未变。随后独立核验发现非 KMS 的 `zeek` 容器自行重启，容器 ID 未变；因此仅声明本次操作只重建 KMS 网关，不声明整台服务器所有进程持续无重启。

证据文件：`server-result.json` 为服务器即时验收，`client-verification.json` 为本机严格 TLS 访问及 HTTP 重定向验收。独立只读复核已确认配置差异、绑定、Nginx 语法与上述路由。
