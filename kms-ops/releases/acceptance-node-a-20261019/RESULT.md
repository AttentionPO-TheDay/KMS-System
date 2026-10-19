# 验收安全测试节点修复结果

2026-10-19 19:20（Asia/Shanghai）已部署并通过服务器复测。

问题：安全执行器默认进入不存在或不可进入的 `demo-0`，在发起攻击校验前退出，验收台显示“需复核”。用户确认现有测试节点名为 `A`、`B`、`C`。

修改：`system_security.go` 默认测试节点改为 `A`；Compose显式传递 `ACCEPTANCE_SECURITY_NODE_ID=${ACCEPTANCE_SECURITY_NODE_ID:-A}`，可按需配置为B/C。只使用既有节点和独立临时会话，不创建节点或生成、更新、回收密钥。回归覆盖默认A、配置B/C及节点不可用时停止测试。

验证：本机 `go test ./...` 通过；服务器通过实际Demo网关、独立管理员会话执行三个安全用例。

| 测试 | 返回业务错误码 | 结果 |
| --- | --- | --- |
| 伪造生成节点身份 | INVALID_PARAMETER | 通过 |
| 未授权算法替换 | KEYGEN_SCHEME_INVALID | 通过 |
| 生成请求格式破坏 | INVALID_PARAMETER | 通过 |

三个结果均为 `status=completed, verdict=blocked, passed=true`；每项的合法节点读取均正常。这里blocked表示非法请求被拦截，即防护测试成功。

后续补测：另外3项参数校验和5项会话/权限校验共用同一节点A配置，8/8通过；安全探针累计11/11。结果见 `other-security-verification.json`，其他测试的节点依赖与限制见 `OTHER_TESTS_AUDIT.md`。本次补测未重建服务或执行密钥压测。

非敏感证据：`verification.json`、`deployment-result.json`。核对运行中二进制SHA256为 `df6b0c68b57a5a507eb428eb7154cdc7b18ae344da55758d2e83d178a320f341`。

部署根目录：`/home/rbf/kms-sys/releases/acceptance-node-a-20261019`。仅重建 `kms_acceptance_backend`，镜像为 `kms-acceptance-backend:node-a-20261019`；另外16个KMS容器ID/启动时间保持不变。旧镜像标签 `kms-acceptance-backend:before-node-a-20261019`、原Compose和审计目录保存在受限backup中。不要输出backup配置或运行环境。

旧IP的 `/updatedel/demo` 与新IP的 `/acceptance/` 均通过严格TLS验证并返回HTTP200。浏览器旧入口映射保持不变。DID正式状态不受此次部署影响。

页面结果按Demo会话隔离。本次自动复测证据来自独立会话；用户应刷新验收台，在当前管理员会话分别执行三种测试并刷新看板，生成自己会话的最新结果。

发布过程中发现服务器Compose实际为JSON，已适配；第一次核验脚本漏等preparing状态，触发409，发布自动回滚。修正等待逻辑后最终部署和三项验证全部通过。原备份未覆盖；重试前的核验日志保留在服务器发布目录。
