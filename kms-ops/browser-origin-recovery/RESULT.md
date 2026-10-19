# 浏览器旧入口恢复结果

2026-10-19，用户确认“成功了”。已使用原Chrome节点A配置（Profile 5）打开原入口，并连接新服务器。

- 固定入口：`https://10.112.125.22:8443/updatedel/demo`。
- 实际目标：`10.129.114.144:8443`，由专用Chrome启动参数映射。
- 后续入口：桌面“KMS旧入口恢复”快捷方式，默认带 `-AllNodes`，一次打开原节点A/B/C三个配置。已带恢复映射的Chrome可复用；其他Chrome进程需先退出。
- 新站点公有证书覆盖新旧IP，SHA256为 `130A2051D968A46EDE55020E2AE9A5B7727F6C6CA2DDB5DE3021A6038AD038DB`。当前用户Root信任库实测已安装，正式浏览器未忽略TLS错误。
- 原浏览器数据未清理、未复制或重新生成密钥；未覆盖服务端公钥，未提交链交易。
- 已确认旧origin数据库目录元数据存在于Default及Profile 5/6/7；用户确认节点A成功后要求三节点同时使用，已启动原Profile 5/6/7，Windows窗口枚举实测visibleChromeWindows=3、kmsPageWindows=3。节点B/C内部密钥未独立核验。
- 桌面快捷方式已修复PowerShell路径并验证目标存在，CMD使用PATH中的pwsh.exe。

新IP的网页与旧IP属于不同origin；需要原密钥时保持旧入口。此次恢复不改变服务器DID的部署状态。
