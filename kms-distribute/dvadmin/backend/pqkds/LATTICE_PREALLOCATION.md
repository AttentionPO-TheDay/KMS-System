# 格预分配的三个功能测试

## 页面与操作顺序

1. `/acceptance/#/lattice/offline-trapdoor`：离线生成格陷门。
2. `/acceptance/#/lattice/basis-delegation`：快速委派格基向量，选择主参数和节点。
3. `/acceptance/#/lattice/parallel-sampling`：并行抽样短向量，选择委派材料、样本数和进程数。

三个页面各有独立的配置、预期结果、实测判定、执行记录和 JSON 证据导出。
进入方式沿用统一 Demo 管理员入口，身份、版本、CSRF 和任务租约由现有验收网关校验。

## 实际算法

参数档 `gadget-gpv-functional-v1`：n=16，q=65537，二进制 gadget 宽度17，主格矩阵16×576，节点扩展后16×580。

- 离线陷门：生成随机 Abar、短矩阵 R，构造 A=[Abar | G−Abar·R]。显式构造完整 q 元格核基 T，检查 A·T=0 mod q。构造行列式为 qⁿ；单元测试独立计算行列式和秩。
- 格基委派：将主公共矩阵摘要和节点编号绑定到扩展矩阵 B，使用主陷门抽样 A·X=−B mod q 的短原像，构造扩展格基 [[T,X],[0,I]]，验证 [A|B]·T_F=0 mod q。
- 短向量采样：使用格基的 QR/Gram-Schmidt 数据逐坐标执行整数离散高斯拒绝采样，随机源来自操作系统密码随机数。分布在12倍标准差处截尾；逐条验证 F·x=H(保护包) mod q 及范数约束。
- 并行执行：使用 spawn 多进程池绕开 Python GIL，每个任务独立使用系统密码随机源采样。每个 Django 工作进程至多持有一套采样池，工作进程各自只加载一次当前格基；更换材料时关闭旧池。1进程用于对照，2/4/8进程用于并行测试，记录实际进程标识、任务区间与峰值在途数量。

构造依据包括 GPV 的陷门原像采样方法和 gadget 格陷门/ExtBasis 方法。实现属于可运行的研究功能参数档，不是经标准化或安全认证的独立密码方案：

- 本参数档维度较小，不声明生产安全等级，也不宣称实现恒定时间或抗侧信道。
- ExtBasis 私有材料保留在 KMS 内部，不交给不受信任的节点；没有把它宣称为具备父陷门隐藏性的跨信任域委派协议。
- 新格关系证明是附加功能检查，不替代原有 Kyber、SM4 和 Falcon 的安全职责，不据此宣称任务书中的抗量子攻击指标已经达标。

参考：

- Gentry、Peikert、Vaikuntanathan，*Trapdoors for Hard Lattices and New Cryptographic Constructions*，STOC 2008，<https://eprint.iacr.org/2007/432>。
- Micciancio、Peikert，*Trapdoors for Lattices: Simpler, Tighter, Faster, Smaller*，EUROCRYPT 2012，<https://eprint.iacr.org/2011/501>。
- Cash、Hofheinz、Kiltz、Peikert，*Bonsai Trees, or How to Delegate a Lattice Basis*，EUROCRYPT 2010，<https://eprint.iacr.org/2009/351>。

## 与实际预分配的连接

以当前代码中的节点上传路径为准：节点本机生成并封装 SM4 会话密钥，使用 Falcon 签名后上传；服务端验证签名并管理保护包。

为接收节点准备委派材料后，`node_pool_preallocate` 在同一事务中对本批已验证的保护包执行并行采样，保存 `latticeProof` 和独立的 `lattice_preparation_id` 外键。格证明验证完毕后才提交入池；没有准备委派材料的节点沿用原有路径。

`KeyPoolService.consume_key` 在把池项转为 CONSUMED 前验证格证明。校验委派节点、公共参数摘要、保护包摘要、业务密钥摘要、模运算关系和范数；删除证明也会被独立外键检查识别。后续交付信封沿用现有格式和 Falcon 签名流程。

离线陷门和节点委派基以 AES-GCM 加密后存入新表，存储密钥从服务端秘密域分离派生。优先使用 `KMS_LATTICE_STORAGE_KEY`，否则使用现有 `INTERNAL_TOKEN`，至少32字符；没有公开默认值。轮换该秘密前需要迁移重加密已有陷门，不能直接更换后继续使用旧记录。

## 测试证据与计时

并行页面使用绑定节点的实际 Kyber 公钥构造16/32/64条保护包，在回滚事务中实际入库，调用业务共用的证明生成和取用函数，保存逐项公开证据后清理测试池项。它验证格采样、保护包绑定、入池和取用，不代表已经完成双方会话确认。

导出证据含公开矩阵、目标向量、短向量、范数、保护包规范序列化内容、摘要、工作进程及时间区间，可独立重算关系。私有陷门不出现在接口、浏览器或证据中。

采样总耗时与采样速率包含执行器排队、首次进程及格基加载、计算和进程通信。首次初始化与后续复用分别记录；计算及进程通信耗时单独列出，不隐藏初始化开销。此指标不代替包含网络通信、封装、验签和入库的完整预分配效率，也不自动用于 ≥50条/秒指标判定。

## 验证与迁移

- `python -m unittest pqkds.test_lattice_preallocation_math -v`
- `go test ./...`（验收后端目录）
- `npm run build`（验收前端目录）
- `tools/verify_lattice_django.py`：隔离 MySQL 表，真实 Kyber/SM4 恢复、真实 Falcon 签名上传、入池、篡改拒绝、取用及公开证据复算。外部授权查询使用已授权关系夹具，不将其计为鉴权测试。
- `front/tools/verify-lattice-live.mjs`：真实浏览器执行三个页面并检查1440/768/390宽度。

远端新增迁移 `0041_lattice_preallocation`，依赖实际已有的0038版本，包含两张新表和池项的可空外键。本地的0042为已有外部节点分支与格功能分支的迁移合并，不把外部节点分支顺带发布到远端。

发布和回滚均保留原始镜像、Compose 配置及验收审计文件。回滚镜像时保留新增的可空列和证据表，不自动删除数据。
