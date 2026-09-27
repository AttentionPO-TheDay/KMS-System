# KMS 系统重构实施计划

> 版本：v2
> 范围：角色与登录分流、用户侧页面收敛、对称层 AES-256 → SM4、用户侧分发链路、管理端菜单聚合
> 编写依据：全部结论均来自对当前代码与运行库的实读，关键处标注文件与行号
>
> **进度**：P0-A / P0-B / P0-C 三项前置实验 ✅ ｜ **P1 ✅** ｜ **P2 ✅**（验证小节全通过）
> ｜ **P3 ✅** ｜ **P4 ✅** ｜ **P5 ✅**（第 1、2、3、4、5、6、7 步均已完成）
> ｜ 另：用户要求插队的"`/generate/` 下线 + 三个安全项" ✅ 已完成（见 §8.2）

## 0.4 各阶段验证结论汇总（收口）

| 阶段 | 验证小节 | 证据 |
|---|---|---|
| P0-B | 服务端能否解开用户信封 | `kms-ops/experiments/p0b-server-side-decrypt/REPORT.md` —— **不能**（`u` 从不离开客户端），Q7 成立 |
| P0-C | KMS 公钥兼容 | `kms-ops/experiments/p0c-kms-pubkey-compat/REPORT.md` —— 无 SM2 实现；`key_value` 为 `varchar(1024)` |
| P1 | 登录分流 + 页面增删 | `tools/verify-p1.mjs` **36/36** |
| P2 | SM4 向量 + 端到端 + 旧数据可读 | `test_sm4_crypto.py` **19/19**；`test_sm4_pool_integration.py` **4/4** |
| P3 | 分发链路 + 用户腿信封 | 封装注册表 **38/38**；SM2 底座 **32/32**；浏览器侧 SM3/SM2 **19/19**；密钥文件 **22/22**；加密目标点 **12/12**；用户腿端到端 **15/15**；**节点腿"两条腿同一把 K" 17/17**；浏览器解封端到端 **8/8** |
| P4 | 菜单逐项可打开且无 401 | 管理端巡检 **32/32**；用户前台 **9/9**；前端冒烟 **4 端通过**；侧边栏 30 项 + iframe 实测 `src=/distribute/` |
| P5 | check.ps1 全绿 + 工作台 4 KPI/5 图表且有数据 + 关联分析有足迹 | `check.ps1` **All checks passed**；工作台 **KPI 4 / 图表 5**（分发图「共 11 条」）；关联分析 **5 把密钥各 1 条足迹**；`/distribute-api/*` **404**；重打包产物校验通过 |

**结论：五个阶段的验证小节全部跑通。**

### 0.5 已知遗留（均非阶段验证项，不影响上述结论）

| 项 | 说明 | 为何未做 |
|---|---|---|
| **Q11**：是否整体下线 `kms-distribute` Java 容器 | **✅ 已完成**（你已确认）—— 见下 §P5-Q11 | 端口先收口、再整体下线，两步分开做 |
| P2 收尾①：`*_aes_session_encryption.py` → `*_sm4_session_encryption.py` | 纯改名（牵动 import），功能无影响；模块 docstring 已标注"名字是历史遗留" | 计划本身把它排在 P2 最后；改名会触及正在工作的池路径，收益仅是可读性 |
| P2 收尾②：归档 `benchmark_*` / `ablation_experiment.py` 等实验脚本 | 明确其不参与运行 | 纯标注工作 |
| P4-5：`/updatedel/` → `/admin/` | 计划原文即"**视情况**" | 需要同步 nginx / vite base / `.env` / 缓存策略，且要重跑冒烟；收益是路径更贴切 |
| 工具：`verify-admin-pages.mjs` 的内容量阈值 20 偏低 | ~~配错地址的 frame 页（34 字符告警）也能过~~ → **✅ 已修复**：改为"内嵌页必须真的渲染出 iframe"，并**验证过它会咬人** | — |
| Falcon-1024 在当前镜像不可用 | 磁盘上无 `falcon1024` 库 | 不影响 D16（节点腿默认 Kyber） |
>
> **本版本相对 v1 的三处实质性修正**（均来自运行时实验，不是措辞调整）：
> 1. **§3.2.3「加密目标点」**：v1 写的"加密必须用 `finalPublicKey`"**是错的**。
>    P0-B 用可执行实验证明 `W_A` 没有对应私钥，按原文实现会得到**谁都打不开**的信封；
>    正确目标是 `P_A = W_A + λ·P_pub`（系统里已有现成实现）。见 R16。
> 2. **§8 R1 关闭、新增 R2'**：v1 把"主 KMS 公钥与分发模块 KGC 参数不兼容"列为最高风险，
>    P0-C 证明**这个比较对象根本不存在**（主 KMS 不生成格密钥）；真正的阻塞项是
>    **运行时完全没有 SM2 实现**，P3 必须先补密码学底座。
> 3. **§8 新增 R17/R18/R19/R20**：`ms` 是公开默认值且可被只读接口反推；
>    `key_value` 的明文外泄面比 v1 描述得广（v1 说"列表接口已脱敏"，实测并非如此）。

---

## 0. 文档说明

### 0.1 本计划取代的既有决策

仓库内已有 `doc/frontend-role-boundary.md`（前端与角色边界规划）。本计划**部分取代**它，冲突处以本计划为准：

| 既有文档条目 | 处置 | 原因 |
|---|---|---|
| §1.3「账号体系统一，前端界面按角色分层」 | **继承** | 与本次"主身份源 `kms.sys_user`"一致 |
| §4.3 `role_level` 0/1/2 分层 | **继承并简化** | 见 §3.4 |
| §4.4 两类可申请功能 | **改为 1 类** | `查看公共密钥列表` 本次删除，仅保留 `密钥自动更新` |
| §5.1 用户菜单含「权限申请/我的申请记录/权限回退」独立页 | **取代** | 改为「密钥更新」页内的按钮 + 弹窗 |
| §5.2–5.4 各系统保留独立管理员后台 | **取代** | 改为**单一管理控制台**，按菜单聚合 |
| §6.2「为管理员登录后提供明确的系统后台跳转入口」 | **明确废弃** | 该条正是本次要求取消的"额外按钮跳转" |

### 0.2 已确认的决策（基线，不再讨论）

| # | 决策 |
|---|---|
| D1 | 用户侧 `PUBLIC_KEY_LIST`（查看公共密钥列表）**整功能删除** |
| D2 | 「权限管理」独立页**删除**，申请入口改为「密钥更新」页内的按钮 + 弹窗表单 |
| D3 | 对称层 AES-256 **全部替换为 SM4**；对称层只保留 SM4 |
| D4 | 非对称层 **SM2 / SSCL / CL-Kyber / CL-Falcon 四种全部保留** |
| D5 | 用户从**自己的非对称密钥库**中选一把密钥，交分发模块用它加密 SM4 密钥后分发 |
| D6 | 分发对象**同时包含所选节点与用户本人** |
| D7 | 主身份源 = `kms.sys_user` |
| D8 | 对称密钥时限**固定 24 小时**，不做多档配置 |
| D9 | 登录后按角色进入各自界面，取消"同一页面 + 跳转按钮" |
| D10 | **节点腿保留后量子（Kyber/Falcon），节点侧一行不改**；只新增"用户腿"逻辑。明确接受"节点那一份是后量子而非国密"这一代价（原 §3.1 方案 A） |
| D11 | 删除旧分发链路后，**`kms-distribute` Java 服务（8083）一并下线** → 部署镜像 8 → 7（§3.6.4） |
| D12 | 主 KMS 的 AES 生成路径（`LifecycleService.generateAesKey`）**删除**，不改为 SM4（§3.5.1） |
| D13 | `role_level` **收成 2 级**（0 管理员 / 2 普通用户），与角色模型严格对齐（§3.4） |
| D14 | 「我的操作日志」**含操作日志与登录日志**，按令牌中的 `user_id` 强制过滤（Q8） |
| D15 | 单次分发**最多选择 10 个节点**（§3.2） |
| D16 | 节点腿默认封装算法 = **Kyber**，由节点管理的「默认封装算法」字段配置（§3.1 附带小项） |
| D17 | **用户腿可选算法收窄为 SM2 / SSCL**（Q12 选 (a)）。CL-Kyber / CL-Falcon 仍可生成与保管，但**不得用于分发**；且此限制必须在**服务端强制**，不能只靠前端下拉过滤（§3.2.4） |

---

## 1. 现状核对（差距分析）

### 1.1 对称层：不是"改算法"，是"从零新增 SM4"

必须先纠正一个事实：**系统里从来没有 SM4**。全仓库搜 `SM4` 仅 8 处命中，全部是误报（base64 密钥块、SVG 路径、X.509 证书）；搜 `gmssl`/`CryptSM4`/`MODE_SM4` 在 `kms-distribute` 全树**零命中**。

> **补充（P2 前置实测，2026-09）**：上面说的是"系统没**用**过 SM4"。
> 就"能不能用"而言有个好消息：容器内**已经装了** `cryptography 50.0.1`，
> 它自带 `algorithms.SM4`，且**通过了 GB/T 32907-2016 的两个标准向量**（含 10⁶ 次迭代）。
> 所以 P2 **不需要新增依赖、不需要重建镜像**。详见 §7 的「P2 前置结论」。
> （`gmssl` 确实不存在，但那只影响 P3 的 SM2，与 SM4 无关。）

当前对称密钥的真实构造（`pqkds/key_pool_service.py`）：

```
L115  aes_key = os.urandom(32)                       ← AES-256，32 字节
L119  kem_ct, shared_secret = kyber.encrypt(pk)      ← Kyber 封装
L124  AES-GCM(kem_key).encrypt(aes_key)              ← DEM 层
```

| 项 | 现状 | D3 要求 |
|---|---|---|
| 载荷算法 | AES-256（32 字节密钥） | **SM4（16 字节密钥）** |
| 封装算法 | `kyber_kem` / `falcon_lattice` | 保留（4 种非对称） |
| 时限 | `KeyPoolService.DEFAULT_EXPIRY_HOURS = 24`（`key_pool_service.py:33`） | **维持 24h，不改** |
| 密钥池表 | `falcon_kds.dvadmin_pqkds_pre_distributed_keys` | 需扩展，见 §4 |

**结论**：D3 是**新增实现 + 全量替换**，工作量集中在分发模块内部，不含外部节点改造（理由见 §1.4）。

#### 1.1.1 AES 触碰点全清单（P2 的实际工作面）

**分发模块内**（`kms-distribute/extracted/ruoyi (2)/backend`，按命中数排序）：

| 分类 | 文件 | 说明 |
|---|---|---|
| **生产运行路径**（必须改） | `pqkds/key_pool_service.py`（45） | 密钥池生成，SM4 替换主战场 |
| | `pqkds/views.py`（71） | 多处内联 AES 加解密 |
| | `pqkds/node_service.py`（47） | 节点侧密钥处理 |
| | `pqkds/falcon_aes_session_encryption.py`（23） | 格加密 DEM 层 |
| | `pqkds/kyber_aes_session_encryption.py`（15） | KEM+DEM 的 DEM 层 |
| | `pqkds/kyber_session_key_service.py`（16） | 会话密钥 |
| | `pqkds/crypto_utils.py`（16） | 通用密码工具 |
| | `pqkds/real_crypto_with_fallback.py`（27） | 带降级的真实实现 |
| | `pqkds/key_update_service.py`（9） | 密钥更新 |
| | `pqkds/key_pool_local_storage.py`（1） | 节点本地 JSON 落盘格式 |
| | `pqkds/certificateless_kyber_strict.py`（22） / `kgc_service.py`（7） / `models.py`（7） | 需核对 |
| **测试/实验脚本**（可不改，但要确认不参与运行） | `benchmark_key_pool.py`（23）、`pqkds/ablation_experiment.py`（9）、`pqkds/performance_benchmark_test.py`（3）、`pqkds/benchmark_keygen_*.py` | 建议直接标注或归档 |
| 迁移文件 | `pqkds/migrations/0001_initial.py`（7） | 只含字段注释，不改 |

**分发模块之外**：全仓库仅 **1 处**——`kms-updatedel/java-backend/.../LifecycleService.java`：

```
L355  if ((encrytType.contains("对称") || "AES".equals(encrytName)) && "AES".equals(encrytName))
L384  private String generateAesKey()  { KeyGenerator.getInstance("AES"); init(256); ... }
```

即主 KMS 的**密钥更新**路径支持 `encryt_name='AES-256'`，更新时会重新生成一把 AES-256 密钥（32 字节 → 64 hex）。`kms-generate`、`kms-user`、`kms-acceptance`、`security/` **零命中**。

**运行库实测**（`kms.keymanage` 按算法分组）：

| encryt_type | encryt_name | 条数 |
|---|---|---|
| 无证书非对称加密 | SM2 | 17 |
| 无证书非对称加密 | SSCL | 4 |
| AES | AES-256 | **1** |

且该唯一 AES 行的 `key_value` 长度仅 **9**、`ua` 为 `NULL`——是**演示种子数据，不是真实密钥材料**。

> 由此得 Q9：主 KMS 这条 AES 生成路径是**改成 SM4** 还是**直接删除**？按"对称密钥完全放在分发模块"的口径，删除更干净且只需清理 1 行演示数据。

### 1.2 分发链路：不是"改流程"，是"新增子系统"

当前用户侧「分发」页（`kms-user/front/src/views/distribute/DistributeView.vue`）是**只读记录查询页**：只显示分发记录（记录ID／密钥名称／用户名／加密算法／分发类型／分发状态）+ 筛选 + 自动刷新 + Excel 导出。**没有任何"选择节点并分发"的操作入口。**

现有密钥池的参与者模型与 D5/D6 不一致：

| 维度 | 现状（`models.py:342-346`） | D5/D6 要求 |
|---|---|---|
| 参与者 | `node1` → `node2` 两个节点外键 | **用户** → 所选若干**节点** + **用户本人** |
| 加密对象 | 接收**节点**的公钥 | **用户自选的非对称密钥**（4 种之一） |
| 方向 | 单向，双向需建两个池 | 一次分发覆盖 N 节点 + 1 用户 |
| 用户维度 | **完全没有**（`Node` 模型无任何 user 外键） | 用户选定可通信节点 |

**结论**：需新建"用户 ↔ 节点授权"与"用户侧密钥信封"两张表 + 新的分发接口 + 新的用户页面。

### 1.3 非对称层：四种算法在分发侧只有两种可用

`kms_adapter.py:108-115` 明确写着：

```python
'sm2':  { 'available': False, 'phase': 'frontend_local_simulation_only' },
'sscl': { 'available': False, 'phase': 'frontend_local_simulation_only' },
```

四种算法"能否加密一把 16 字节的 SM4 密钥"的**能力矩阵**（这是 D5 能否落地的关键）：

| 算法 | 类型 | 能否直接加密 16B 密钥 | 依据 |
|---|---|---|---|
| **SM2** | 椭圆曲线公钥加密 | ✅ 可以，16B 远低于 SM2 加密长度上限 | 主 KMS 已实现；分发侧**未实现** |
| **SSCL** | 无证书 SM2 类（`t_A = w + λ·ms mod n`） | ✅ 可以，同为 EC 上的加密改造 | 主 KMS 已实现；分发侧**未实现** |
| **CL-Kyber** | **KEM**（密钥封装） | ⚠️ 不是加密：需 encaps → 共享密钥 → 用共享密钥包裹 SM4 密钥（KEM+DEM） | `key_pool_service.py:119-125` 已是该套路 |
| **CL-Falcon** | **无证书格加密**（不是签名） | ✅ 可以，`fast_encrypt(A,B,H_id,U_id,payload,...)` 直接加密 | `falcon_aes_session_encryption.py:291` |

> ⚠️ 澄清一处易误解：`FalconAESSessionKeyEncryption` 并非用 Falcon 签名算法去"加密"，而是在 Falcon 格参数（n, m, q=12289）上实现的**无证书格加密方案**，能把载荷直接加密。它是可用的。

**结论**：D4 + D5 组合下，**SM2 与 SSCL 的加密能力需要在分发模块新建**（当前只有 Kyber/Falcon 两套格密码）。这是本计划最大的新增代码——但按 **D10**，它**只作用于用户腿**；节点腿继续复用现成的 Kyber/Falcon，其代码路径一行不改。

### 1.4 关键利好：节点是服务端模拟的，没有独立节点代码

`key_pool_local_storage.py` 头部注释与实现表明：

```
节点从 KDS 下载加密的密钥池数据包后，用自己的 Kyber 私钥解密，
将明文 AES 会话密钥保存到本地 JSON 文件。
  backend/node_key_pools/{node_id}/pool_{pool_id}.json
```

即：节点 = `Node` 表记录（`ip_address`/`port` 仅为元数据）+ 服务端本地 JSON 文件。**不存在需要单独发版的外部节点程序。**

**意义**：D3 的 SM4 替换**不涉及任何外部系统改造**，风险与工期大幅收敛。替换点就是 `key_pool_service.py`、`key_pool_local_storage.py` 以及两个 `*_aes_session_encryption.py`。

### 1.5 页面差距

**用户侧**（现 `kms-user/front`，路由表 6 个业务页：workbench / generate / lifecycle / distribute / permissions / profile）：

| 目标页面 | 现状 | 动作 |
|---|---|---|
| 总览 | `workbench/WorkbenchView.vue`（保留，你已认可数据） | **调整**：去掉 `PUBLIC_KEY_LIST` 卡片 |
| 非对称密钥生成 | `generate/GenerateView.vue` | **调整**：删掉"公钥列表" Tab |
| 更新与回收 | `lifecycle/LifecycleView.vue` | **调整**：新增"申请自动更新权限"按钮 + 弹窗 |
| 分发 | `distribute/DistributeView.vue`（只读记录页） | **重做**：选节点 + 选自己的非对称密钥 + 分发 |
| 对称密钥查看 | 无 | **新增** |
| 我的操作日志（仅本人） | 无 | **新增** |
| 权限管理 | `permissions/PermissionView.vue` | **删除** |
| 查看所有密钥 | 生成页内的公钥列表 Tab | **删除** |

**管理侧**（现 `kms-updatedel/front`，24 页）：需新增「区块链管理」「节点管理」「测试页面」，并删除「密钥生成」。

### 1.6 登录与角色分流

现状：`kms-user` 与 `kms-updatedel` 是**两套独立 Spring Boot 应用**，各有 `/login`；管理员靠 `Navbar.vue:80-85` 的按钮 `window.location.href = origin + '/updatedel/'` 跳转——**正是 D9 要取消的形态**。

角色判定已具备：`getInfo()` 返回 `user.roleLevel`（`store/modules/user.js:53`），`isAdmin = roleLevel <= 0`。

### 1.7 身份与权限

- `kms` 库：`sys_user` / `sys_role` / `sys_menu` / `permission_request` —— **主身份源（D7）**
- `falcon_kds` 库：**另一套完整 RBAC**（`dvadmin_system_users` / `dvadmin_system_role` / `dvadmin_system_menu` / `dvadmin_system_dept`）
- 两库之间**当前无任何关联字段**

---

## 2. 目标架构

```
                     ┌──────────────────────────────┐
   登录（唯一入口）  │  kms.sys_user  ← 主身份源 D7  │
                     └──────────────┬───────────────┘
                                    │ roleLevel
                    ┌───────────────┴────────────────┐
                    ▼                                ▼
        ┌───────────────────────┐      ┌──────────────────────────────┐
        │ 普通用户  /user/      │      │ 管理员  /admin/              │
        │ 总览                  │      │ 总览                         │
        │ 非对称密钥生成        │      │ 全部资产查看（密钥查询）     │
        │ 更新与回收(+申请按钮) │      │ 无证书密钥更新与回收         │
        │ 分发(选节点+选密钥)   │      │ 区块链管理  ← 聚合 pqkds     │
        │ 对称密钥查看  ★新     │      │ 节点管理    ← 聚合 pqkds     │
        │ 我的操作日志  ★新     │      │ 权限审批 / 日志审计          │
        └───────────────────────┘      │ 测试页面    ← 聚合 acceptance│
                                       │ 系统管理                     │
                                       └──────────────────────────────┘
```

**聚合方式（推荐）**：管理端以 `kms-updatedel` 为统一壳（它已是"你喜欢的那套"设计令牌栈），
跨应用页面通过 RuoYi 自带 `InnerLink`（iframe）先嵌入，稳定后再逐个用 API 重画。
理由：优先达成"菜单栏里能看到"，避免一上来就重写 1845 行的节点管理页（TS 栈与壳不同）。

---

## 3. 关键设计决策（已全部拍板）

### 3.1 SM4 与"抗量子"的叙事冲突（**已定：方案 A**）

对称层换 SM4 后，用户腿由 **SM2 加密 SM4 密钥**——SM2 是**经典密码，不抗量子**；
而分发模块的立身之本与命名（`falcon_kds`、Kyber/Falcon）都是**抗量子**。二者并存需要明确取舍。

**决策（D10）：取方案 A。**

| 选项 | 含义 | 结论 |
|---|---|---|
| **A ✅ 采纳** | 节点腿保留 Kyber/Falcon 抗量子封装（**节点侧零改动**）；用户腿用所选非对称密钥（4 选 1） | 两腿算法可不同；节点侧现有格密码资产全部复用 |
| B ❌ 否决 | 全链路国密，节点也换 SM2 | 需给每个节点新发 SM2 密钥、改 `Node` 模型、重做节点密钥更新/会话失效；**封装器反而从 4 个增至 5 个**，且与"抗量子"命名矛盾 |
| C ❌ 冗余 | 按分发对象自动选 | 实质等价于 A，仅表述差别 |

**已确认接受的代价**：节点那一份密文是后量子（Kyber/Falcon）而非国密；只有用户那一份是国密（SM2/SSCL）。

**由此锁定的实现形态**——一套分发流程 + 按算法分叉的单点封装器：

```python
# D17：kyber/falcon 仅供【节点腿】；sm2/sscl 仅供【用户腿】
WRAPPERS = {
    'sm2':       Sm2Wrapper(),        # 新增
    'sscl':      SsclWrapper(),       # 新增
    'cl_kyber':  KyberWrapper(),      # 已存在，直接复用
    'cl_falcon': FalconWrapper(),     # 已存在，直接复用
}
USER_LEG_ALGORITHMS = {'sm2', 'sscl'}          # 服务端强制白名单（§3.2.4）

def distribute(user, source_key, node_ids):
    if source_key.algorithm not in USER_LEG_ALGORITHMS:      # R11：必须服务端拦
        raise BadRequest('该算法不可用于分发')
    sm4_key = sm4.generate_key()                              # 只有一套
    for node in authorized_nodes(user, node_ids):             # 节点鉴权
        WRAPPERS[node.wrap_algorithm].wrap(sm4_key, node.public_key)
    WRAPPERS[source_key.algorithm].wrap(sm4_key, source_key.final_public_key)  # 用 finalPublicKey
```

分发主流程内**不出现任何 if/else 分支**，算法差异全部收敛到 `wrap()/unwrap()` 一对函数里。
注意：现有 `key_pool_service.py:40,184` 已经是"Kyber / Falcon 两分支"形态，本决策**不新增形态**，只是把分支改为注册表查表。

**KEM 与直接加密的差异由 `wrap()` 吸收**：Kyber 是 KEM，封 16 字节密钥需两步（encaps 出共享密钥 → 再用它包 SM4 密钥）；SM2/SSCL/CL-Falcon 为直接加密一步到位。密文本就是 JSON 串，现有格式 `{kem_ciphertext, encrypted_aes_key, nonce, tag}` 已能容纳两种形态。

**附带小项（P3 内处理，不阻塞）**：节点同时持有 Kyber 与 Falcon 两把密钥（`models.py:79-84`），
"封给节点用哪把"由节点管理里新增的**默认封装算法**字段决定（管理员配置，默认 `kyber`）。

### 3.2 一个 SM4 密钥要产生 N+1 份密文

同一把 SM4 密钥分发给 N 个节点 + 1 个用户，各方公钥不同，**必须各自加密一份**：

```
SM4 密钥 K（16B）——全系统只有这一把，N+1 份密文解出来的是同一个 K
  ├─ Envelope(node_1) = Wrap(K, pk(node_1),  算法=kyber_kem|falcon_lattice)
  ├─ Envelope(node_2) = Wrap(K, pk(node_2),  算法=...)
  ├─ ...
  └─ Envelope(user)   = Wrap(K, pk(user_key), 算法=SM2|SSCL|CL-Kyber|CL-Falcon)   ← D5
```

#### 3.2.1 谁能解开哪一份（常见疑问：用户选了 SM2，节点还能解吗？）

**能，但节点用的不是用户那把 SM2 密钥，而是节点自己的密钥。**

```
                       SM4 密钥 K
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
   node_A 那份         node_B 那份        用户自己那份
   用 node_A 的        用 node_B 的        用用户选的 SM2
   Kyber 公钥封装       Kyber 公钥封装      公钥加密
        │                  │                  │
        ▼                  ▼                  ▼
   node_A 用自己的     node_B 用自己的    用户用自己的
   Kyber 私钥解        Kyber 私钥解        SM2 私钥解
        ✅                 ✅                 ✅
```

| 问题 | 答案 |
|---|---|
| 被选中的节点能解出对称密钥吗？ | **能**，用自己的 Kyber（或 Falcon）私钥解**自己那一份** |
| 用户选 SM2 会影响节点解密吗？ | **完全不影响**。用户选什么算法只决定**用户那一份**怎么加密 |
| 节点 A 能解开节点 B 的那份吗？ | **不能，也不应该能**——否则任一节点即可窃取全网密钥 |
| 为什么用户也要一份？ | 用户要与节点用**同一把 SM4** 通信，双方都必须持有 K。用户那份走国密 SM2、节点那份走抗量子 Kyber，**两条腿算法不同，但解出的 K 是同一把**——这正是 D10 方案 A 能成立的根本原因 |

#### 3.2.2 这套设计成立的前提（**已部分证伪，见 §3.2.3**）

无证书体制下，服务端（KGC）持有主密钥 `ms`，客户端持有本地私钥分量 `d_client`。
"用户那份只有用户能解"**成立的前提是：服务端仅凭自己手里的材料无法解出用户信封**。

若不成立，则 Q7「管理员不得查看对称密钥明文」形同虚设——服务端可以直接解密。

> **⚠️ P0-A 静态分析已给出部分答案（详见 §3.2.3）**：
> **对 CL-Kyber / CL-Falcon，前提不成立**——完整私钥就明文存在 `keymanage.key_value` 里，服务端必然能解密。
> **对 SM2 / SSCL 仍需运行时验证**（服务端持有 `t_A`、客户端持本地分量，是否足以解密待实验）。
> 已据此收窄用户腿可选算法为 SM2 / SSCL（**D17**，细则见 §3.2.4）。

N 越大存储与 CPU 越大。需确认**单次分发允许选择的最大节点数**（已定：**10**，见 Q5）。

#### 3.2.3 四种算法的密钥材料存放位置与格式（**P0-A 静态结论，已核实**）

| 算法 | `keymanage.ua` | `keymanage.key_value` 内容 | 私钥在哪 | 服务端能否解开该公钥加密的信封 |
|---|---|---|---|---|
| **SM2** | 130 hex，SM2 曲线点（`04` 前缀） | `{"partialKey": t_A(64hex), "finalPublicKey": "04"+W_A(128hex)}` | **分片**：服务端持 `t_A`，客户端持本地分量 | ⏳ 待运行时验证（P0-B） |
| **SSCL** | 130 hex，同 SM2 | `{"SSCLKey":"04"+M(128hex), "SSCLEA": ms·wA(64hex), "SSCLDomain":"A"}` | **分片**，同上 | ⏳ 待运行时验证（P0-B） |
| **CL-Kyber** | —（走 demo 记录） | demo 响应整体 JSON，内含 `key_material_or_reference.private_key`（`kyber_private_key` + `cl_private_key`） | ⚠️ **明文完整私钥就在库里** | ❌ **能**（无需实验即可判定） |
| **CL-Falcon** | —（走 demo 记录） | 同上，内含 `falcon_sk` + `D_id` / `S_id` | ⚠️ **明文完整私钥就在库里** | ❌ **能**（无需实验即可判定） |

**依据（关键代码路径，已逐处核实）**：

```text
Go   key_service.go:226-235
       km.DemoRecordID = demoResp.Data.DemoRecordID
       keyValue, _ := json.Marshal(demoResp.Data)     ← 把「整个 demo 响应体」当 keyValue
       km.KeyValue = string(keyValue)

Django  views.py:470
          'key_material_or_reference': _kms_record_material(result, algorithm)
        views.py:116-128
          'KYBER'  → {'public_key': …, 'private_key': kyber_private_key | cl_private_key}
          'FALCON' → {'public_key': falcon_pk, 'private_key': falcon_sk}
        optimized_keygen_service.py:291-300 / :52-70   ← 返回含完整私钥材料

Java  GenerateKeymanageCompatController.java:103-105
        keymanage.setKeyValue(keyValue)                → 经 Kafka Consumer 落库
```

**结论 1（安全性，重要）**：**Q7「管理员不得查看对称密钥明文」对 CL-Kyber / CL-Falcon 在密码学上不成立**——
服务端持有完整私钥，任何能读到 `key_value` 的人都能解开用该公钥加密的用户信封。
对这两类算法，Q7 只能退化为"界面与权限层面的遮挡"，不构成真实的机密性保护。

> 这也与"无证书"的初衷相悖：无证书体制的意义正是 KGC **不**持有完整私钥。
> 而当前 PQ 路径把 `kyber_private_key` / `falcon_sk` 完整落库了。

**结论 2（好消息）**：列表接口**已经做了脱敏**——`GenerateController.java:75-93` 另建对象、
只回填 `item.setKeyValue(extractPublicValue(...))`，不透出私钥。所以**现有 UI 不会泄露**，
问题只在"库里存了明文私钥"这一层。

**结论 3（D5 的直接影响 → 已由 Q12 / D17 处置）**：
因为 PQ 私钥明文落库，"用户那份只有用户能解"对 CL-Kyber / CL-Falcon **无法成立**，
故**用户腿可选算法收窄为 SM2 / SSCL**，细则见 §3.2.4。

**结论 4（P3 必须落实：加密目标点）**：SM2 的 `key_value` 里同时有 `partialKey`（`t_A`，私钥分量）
与 `finalPublicKey`（`W_A`，完整公钥）。~~**加密必须用 `finalPublicKey`**~~
**→ 本条经 P0-B 实验证伪，已作废，正确结论见下方"⚠️ 加密目标点"一节。**

> ### ⚠️ 加密目标点：本节原先写错了，按原文实现会做出"谁都打不开"的信封
>
> P0-B 用可执行实验（`kms-ops/experiments/p0b-server-side-decrypt/`）逐点验证了
> 用户私钥为 `d_A = (t_A + u) mod n`（`u` 是浏览器本地标量）之后，得到下表：
>
> | 加密到哪个点 | 用户能解？ | 服务端能解？ | 结论 |
> |---|---|---|---|
> | `P_pub`（KGC 主公钥） | ❌ | **✅** | **绝对不能用** —— Q7 直接失效 |
> | `t_A · G` | ❌ | **✅** | **绝对不能用** |
> | `W_A`（`finalPublicKey`） | **❌** | ❌ | 原文写的这个 —— **信封没人能打开，连用户自己也不行** |
> | **`P_A = W_A + λ·P_pub`** | **✅** | ❌ | **唯一正确解，P3 必须用这个** |
>
> 关键点：`d_A` 与 `P_A` 是一对**无证书体制下的实际加解密密钥对**，
> 而 `W_A` 只是其中一半。把 `W_A` 当加密目标，等于用了一个没有对应私钥的公钥。
>
> **好消息**：该点**系统里已经算过了** —— `UpdatedelChainService.java:354` 就在算它。
> P3 直接复用，不要另写一份推导。
>
> **P3 必须加一条单测**：断言"信封的加密目标点 == `W_A + λ·P_pub`"，
> 并把"用 `W_A` 加密后用户能解开"列为**必须失败**的用例。
> 记为风险 **R16**，并在 §7 P3 里作为第一步。

#### 3.2.4 用户腿算法收窄的执行细则（D17 / Q12）

| 层面 | 要求 |
|---|---|
| **服务端（强制，关键）** | `POST /key-pool/distribute-to-user/` 必须校验 `source_key_id` 对应密钥的 `encryt_name ∈ {SM2, SSCL}`，否则返回 400。**仅靠前端过滤不算数**——否则直接构造请求即可拿到用 PQ 公钥封装的信封 |
| **前端** | 「分发」页的非对称密钥下拉只列出当前用户的 SM2 / SSCL 密钥 |
| **UX 说明** | 下拉旁给出说明：CL-Kyber / CL-Falcon 密钥不可用于分发。否则用户会困惑"我明明有 Kyber 密钥为什么选不了" |
| **`WRAPPERS` 注册表** | 仍保留 4 个实现——`kyber` / `falcon` 供**节点腿**使用，`sm2` / `sscl` 供**用户腿**使用。收窄只作用于"用户腿的可选项"，不删实现 |
| **存量 PQ 密钥** | 保留、可查看、可更新/回收（D4 不变），只是不参与分发 |

> **连带影响（重要）**：收窄之后，**用户信封的机密性完全押在 SM2 / SSCL 上**。
> 因此 **P0-B 从"验证项"升级为 Q7 的唯一支柱**：若实验发现服务端连 SM2/SSCL 的信封也能解开，
> 则**已无任何算法能提供真实机密性**，Q7 将整体失效，必须改为"用户私钥永不出客户端"的构造。
> 此项记为风险 **R10**（§8）。

### 3.3 跨库取公钥的两种方式

用户公钥在 `kms.keymanage`（`kms` 库），节点与密钥池在 `falcon_kds` 库。

| 方式 | 说明 | 评价 |
|---|---|---|
| **a. 服务接口**（推荐） | 主 KMS 暴露内网接口按 `key_id` 返回用户公钥；分发模块带服务令牌调用 | 已有同款机制：`kms_adapter.py` 的 `X-KMS-Service-Token` 鉴权，直接扩展即可；库归属清晰 |
| b. 直连跨库读 | 分发模块直读 `kms` 库 | 快，但两库强耦合，且绕过权限校验 |

建议 **a**。

### 3.4 `role_level` 收成 2 级（**已定**）

现状与既有文档均为 **0=管理员 / 1=中级用户 / 2=普通用户**。
`role_level <= 1` 当前**唯一的用途**就是放行 `PUBLIC_KEY_LIST`（`GenerateView.vue:411`、`PermissionView.vue:225-230`）。

**决策（Q2）：收成 2 级** —— 与你的角色模型（管理员 / 普通用户）严格对齐。

| 级别 | 含义 |
|---|---|
| `0` | 管理员 |
| `2` | 普通用户 |

**需要改动的 `roleLevel` 比较点**（全部收拢到"是否 `<= 0`"这一个判据）：

> **实施补充（P1 实测）**：原表只列了 7 处，实际比它多。P1 已按下表逐处改完，
> 并新增了两个共享判据模块（`src/utils/role.js`：`isAdminLevel` / `roleLevelText`），
> 两个前端各一份，避免再出现散落的 `=== 1` 分支。

| 位置 | 原值 | 改为 |
|---|---|---|
| `Navbar.vue` `isAdmin` | `<= 0` | **整段删除**（D9 取消跳转按钮） |
| `WorkbenchView.vue` `levelText` | `{0:'管理员',1:'中级用户',2:'普通用户'}` | `roleLevelText(...)` |
| `WorkbenchView.vue` AUTO_UPDATE 永久放行 | `<= 0` | `isAdminLevel(...)`（等价） |
| `WorkbenchView.vue` PUBLIC_KEY_LIST | `<= 1` | **随 D1 整段删除** |
| `GenerateView.vue` PUBLIC_KEY_LIST（2 处） | `<= 1` | **随 D1 整段删除** |
| `GenerateView.vue` `roleText` | 3 级映射 | `roleLevelText(...)`（并修掉 `profile.roleLevel` 从未赋值导致恒显"未知"） |
| `LifecycleView.vue` 自动更新永久放行 | `<= 0` | `isAdminLevel(...)` |
| `LifecycleView.vue` `roleText` | 3 级映射 | `roleLevelText(...)` |
| `PermissionView.vue` | `<=1` / `<=0` | 该页按 D2 删除 |
| `kms-updatedel` `permission.js` 路由守卫 | `roleId === 1 \|\| === 2` | `isAdminLevel(roleLevel)`，非管理员整页跳回用户前台 |
| `kms-updatedel` `views/userKeys/index.vue` | `roleLevel <= 1` 控制「公共密钥」Tab | 该 Tab 随 D1 删除；页面改为纯资产视图 |
| `kms-updatedel` `views/query/businessUsers/index.vue` `roleText`/`roleTagType` | 3 级映射 | 共享判据 |
| `kms-updatedel` / `kms-user` `system/user/profile/index.vue` `getRoleName` | `=== 1` 分支 | 共享判据 |
| `kms-updatedel` `views/permission/request/index.vue` | 4 处 3 级标签 | 抽成 `levelText` / `levelTagType` 两个本地函数 |

**存量数据迁移**：`kms.sys_user` 中 `role_level = 1` 的账号全部改为 `2`（`21_*.sql`）。
**实测影响面为 0**：运行库 6 个账号只有 `0`（2 个）与 `2`（4 个），无 1 级账号。

> **另一处顺带修掉的隐患（重要，且原文档一度判断错了）**：临时授权不得改写 `role_level`。
>
> 全仓库原来有**两处**会改写它，本计划早期只发现了第一处：
>
> 1. 生成域 `PermissionRequestServiceImpl.approve()` 的
>    `updateUserRoleLevel(userId, requestLevel)` —— 随 D1 删除整套子系统而移除；
> 2. **更新域的 `PermissionRequestService`**：`approve()` 调用
>    `sysUserMapper.updateRoleLevel(userId, request.getRequestLevel())`，
>    `rollback()` 则写 2、或在"还有其它已通过申请"时写 **1**。
>    （早期漏掉它是因为按 `updateUserRoleLevel` 这个名字去搜，
>    而这里是 `updateRoleLevel`，且 `getRequestLevel()` 与 `requestLevel` 大小写不同。）
>
> 第 2 处是真缺陷，P1 已修：
> - 审批通过会把普通用户写成 `role_level = 0`，而 **D9 的分流判据正是 `role_level <= 0`**
>   → 用户拿到「自动更新」临时权限后，下次登录会被直接送进**管理控制台**；
> - 回退会写 `1`，而等级 1（中级用户）已随 D1 废弃 —— 等于凭空造出一个非法等级。
>
> 修法是**彻底不动 `role_level`**：临时权限本来就由 `permission_request` 表判定
> （服务端 `LifecycleKeyController.canManageAutoUpdate()` 走
> `hasActiveTemporaryPermission(userId)`，前端读 `status=1 且 is_temp=1` 的记录）。
> 同时删掉了已成死代码的 `SysUserMapper.updateRoleLevel` 及其 XML 语句 ——
> 留着一个能静默改写权限等级的方法本身就是隐患。
>
> 现在 `role_level` 是**纯静态的账号属性**，只由注册/管理员改角色时决定。
> P1 已用端到端用例固定这条不变量（见 §7 P1 的 `verify-p1.mjs`：授权前后 role_level 必须都是 2，
> 同时证明临时权限**仍然生效** —— 排除"功能被改坏"这种假通过）。

**同步更新** `doc/frontend-role-boundary.md` §4.3（该文档现描述 3 级模型，需改为 2 级并标注被本计划取代）。

### 3.5 管理端菜单增删（**已定**）

- 删除「密钥生成」——管理员不生成，只查看（你的原话："生成它不需要"）
- 「算法说明」3 页（算法图解与演示／更新回收速览／轮换计算揭秘）**保留**（Q3）

#### 3.5.1 主 KMS 的 AES 生成路径：删除（Q9 / D12）

**它是什么**：`kms-updatedel/java-backend/.../LifecycleService.java` 的 `generateKeyValue()` 方法，
在**一把密钥被"更新"时**按算法类型重新生成密钥材料，分四个分支：

| 分支 | 行为 |
|---|---|
| `encrytName == "AES"` | → `generateAesKey()`（`:384-398`）用 `KeyGenerator.getInstance("AES")` 生成 32 字节密钥 |
| `SM2` | → `eccKeyGenerator.generate(...)` |
| `SSCL` | → `ssclKeyGenerator.generate(...)` |
| 其他（PQ 类） | 抛异常（`:379-381`，刻意不静默返回旧值） |

所谓"主 KMS 的 AES 生成路径"就是**第一个分支 + `generateAesKey()`**。

**为什么建议删除而不是改成 SM4**：

1. **界面上根本走不到它**——已核查全部 5 个前端，AES 只出现在两处：分发模块的**说明文案**
   （"Kyber KEM + AES-256-GCM"），以及 `legacy-kms/RuoYi-Vue3-master`（旧版参考工程，**不构建、不发布**，
   内有 6 处 `{label:'AES', value:'AES'}` 下拉项）。当前系统**没有任何页面能产生 AES 密钥**。
2. **运行库里只有 1 行** AES 记录（`key_id=1`，`key_value` 长度仅 9，`ua` 为 NULL）——演示种子数据。
   即该分支实际是**只有那 1 行历史数据能触达的死代码**。
3. **改成 SM4 会与你的架构原则冲突**：你已明确"对称密钥完全放在分发模块"。
   若把主 KMS 这条路径改成 SM4，等于在主 KMS 里再养一套对称密钥生成能力。
4. D3「AES-256 全部替换为 SM4」在这个场景下**自然满足**——因为主 KMS 不再产生任何对称密钥了。

**动作**：删除 `generateAesKey()` 与 `AES` 分支；`keymanage` 中那 1 行演示数据一并清理；
`generateKeyValue()` 的兜底异常保持原样（对未知算法显式失败），确保不会再出现"版本号变了、密钥材料没变"。

### 3.6 两套"分发"实现的收敛（**已定：删除旧的，但需先迁移两个消费方**）

系统内存在两个同名概念：

| 实现 | 位置 | 对象 | 数据 |
|---|---|---|---|
| **旧**：分发记录 | `kms-distribute/java-backend` `KeyDistributeController`（`/distribute-api/distribute/record/*`） | 非对称密钥（`keymanage` 行） | `kms.key_distribute_record` |
| **新**：密钥池分发 | `pqkds` Django（`/pqkds-api/key-pool/`） | 对称密钥（节点间） | `falcon_kds.dvadmin_pqkds_pre_distributed_keys` |

#### 3.6.1 关键发现：旧"分发记录"其实是**派生投影**，不是独立系统

`DistributeKafkaConsumer.java:51-57` 表明，它**不消费任何专属 topic**，而是监听主 KMS 现成的四个 topic：

```java
topics = { "${kms.kafka.generate-topic:key_generate_log}",
           "${kms.kafka.update-topic:key_update_log}",
           "${kms.kafka.revoke-topic:key_revoke_log}" }
// 另有 chain-result-topic: key_chain_result
```

再用 `resolveDistributeType()`（`:341-348`）把生命周期事件**重新贴标签**成"分发类型"：

| 主 KMS 真实事件 | 被派生出的"分发类型" |
|---|---|
| `ENROLL_KEY` / `key_generate_log` | 初始分发 |
| `UPDATE_KEY` / `key_update_log` | 更新分发 |
| `REVOKE_KEY` / `key_revoke_log` | 回收后补发 |

也就是说：**旧的"分发"并没有真的分发任何东西**，它只是把"生成/更新/回收"改了个名字记一笔。
而 D5/D6 的新分发是**真实行为**（SM4 密钥真的送到节点与用户）。

**这从概念上支持删除**——但删除前必须处理它的两个真实消费方（见 3.6.2），否则会连带丢功能。

#### 3.6.2 删除前必须迁移的两个消费方（否则展示位会断，且新数据不会自动接上）

> 澄清一个容易误读的点：**新分发一定会产生数据，问题不在"有没有数据"，而在"数据怎么接过去"。**
> 旧展示位读的是 `kms` 库的 `key_distribute_record`（经 `kms-distribute` Java 服务 + `/distribute-api/`），
> 而新分发写在 **`falcon_kds` 库**（经 Django + `/pqkds-api/`）——**两个库、两个服务、两个接口**，
> 不换代码就永远读不到新数据；旧表一删则直接报错。所以必须先改指向，再删旧链路。

| # | 消费方 | 现状 | 迁移动作 |
|---|---|---|---|
| 1 | **用户工作台第 3 张卡片「分发记录」** + **第 5 张图「分发状态分布」**（该页已确认必须保留，见 §3.6.5） | KPI 定义 `WorkbenchView.vue:329-334`（`distributeTotal` / `distributeSucceeded`）；图表 `:386-395,821`；数据来自 `:175,608-622` 的 `listDistributeRecords()` | 改读 §4.4 **分发批次表**（新数据是真实分发，比旧派生数据更有意义） |
| 2 | **管理端「密钥关联分析」的分发足迹** | `LifecycleService.java:109-125` `getAssociationAnalysis()` 直接 SQL 查 `key_distribute_record` 填 `setDistributeFootprints()` | 改查 §4.4 批次表（按 `source_key_id` 关联） |
| 3 | **健康检查** | `kms-ops/check.ps1:83` `Test-MySqlTable "key_distribute_record"` | 换为新表检查 |

#### 3.6.3 删除清单

| 类别 | 条目 |
|---|---|
| Kafka | `DistributeKafkaConsumer.java`（**仅删此消费者**；四个 topic 是主 KMS 命脉，**保持不动**） |
| Java 代码 | `KeyDistributeController` / `KeyDistributeDashboardController` / `IKeyDistributeService`(+Impl) / `IKeyDistributeDashboardService`(+Impl) / `KeyDistributeMapper`(+`DashboardMapper`) / `KeyDistributeRecord` / `KeyDistributeFeignClient` / `DashboardOverview` / `DashboardSummary` / `DashboardTrendPoint` / `DashboardDistributionItem` / 两个 Mapper XML |
| 网关 | nginx `location /distribute-api/` + `upstream distribute_java_backend` |
| 前端 | `kms-user/front/src/services/distribute-api.js`、`config/api-bases.js` 的 `distributeApi`、vite 代理 `/distribute-api` |
| 数据库 | `kms.key_distribute_record` 表、`kms-ops/mysql/init/10_key_distribute_record.sql`、`kms-distribute/sql/key_distribute_record.sql` |
| 其他 | `kms-distribute/front`（已废弃前端）中的分发记录页；`legacy-kms/` 中 `keymanageServiceImpl.java:60` 的同类查询 |

#### 3.6.4 连带结果：`kms-distribute` Java 服务（8083）将无任何消费方 → 建议整机下线

删除后 `/distribute-api/` 不再有调用方。而 `kms-distribute/java-backend` 剩下的只有 RuoYi 系统管理控制器
（`SysUserController` 等），这些接口**没有任何前端在调**（`/distribute/` 前端是 django-vue3-admin，走 `/pqkds-api/`）。

**因此建议连该服务一起下线**，收益是可量化的：

- 部署镜像 **8 个 → 7 个**（少一个 Spring Boot 镜像）
- 少一个 JVM 容器（端口 8083、内存占用）
- `docker-compose.yml` 少一个 service、`ship.ps1` 少一次 `docker save`
- `kms-nginx-update.tar` 之外的完整包体积下降

> 此项列为 **Q11** 待确认。若同意，则 §7 增加一个 P5 子任务；若暂不下线，则保留容器但移除 `/distribute-api/` 路由。

#### 3.6.5 用户工作台元素去向对照表（**该页为保留页，不得丢元素**）

你已明确这张工作台页面"很好"、要保留。按 D1/D2/D4/Q4/Q9，页面上每个元素的去向如下：

| 页面元素 | 数据源 | 处置 |
|---|---|---|
| KPI「我的密钥」 | `loadGenerate()` → keymanage | ✅ 不动 |
| KPI「有效密钥」 | `loadLifecycle()` | ✅ 不动 |
| KPI「分发记录 31」 | `loadDistribute()` → **旧分发链路** | ⚠️ **改数据源**（前端换接口 + 后端新增按批次聚合的接口），不得删除（§3.6.2-1） |
| KPI「待审批申请」 | `loadPermission()` → `permission_request` | ✅ 保留；但语义收窄为仅「密钥自动更新」申请（D1 删掉另一项） |
| 图「近 7 天密钥生成趋势」 | `generateKeys` | ✅ 不动 |
| 图「密钥算法分布」 | `generateKeys` 按 `encrytName` 分组 | ✅ 不动；其中 **AES-256 扇区**会随 Q9 删除那条演示数据而消失 |
| 图「密钥状态分布」 | `loadLifecycle()` | ✅ 不动 |
| 图「上链状态分布」 | `loadLifecycle()` | ✅ 不动 |
| 图「分发状态分布 共 31 条」 | `loadDistribute()` → **旧分发链路** | ⚠️ **改数据源**，不得删除（§3.6.2-1） |
| 区块「权限申请」→「查看公共密钥列表 · 已具备」 | `PUBLIC_KEY_LIST` | ❌ **删除**（D1） |
| 侧边栏「权限管理」 | 该页本身 | ❌ **删除**（D2），申请入口迁至「更新与回收」页 |
| 侧边栏「分发下载」 | 只读记录页 | 🔄 **重做为**「选节点 + 选密钥 → 分发」（§6.1） |

> **硬性约束**：改写完成后，该页面的 KPI 数量（4）与图表数量（5）**必须保持不变**，
> 只是「分发记录」与「分发状态分布」的数据源由旧派生投影换成新的真实分发批次。
> 此项列入 P5 的验收条件。

> **语义变化提醒**（唯一非显而易见的一点）：现在卡上的 `31` 是**事件派生**出来的——生成/更新/回收各记一笔，
> 20 把密钥就产出 31 条"分发记录"，它并不代表真的分发了 31 次。换成真实批次后，该数字**会先变成 0**，
> 再随用户实际点击分发而增长。建议同时把卡片标题由「分发记录」改为「**分发批次**」，让文案与含义一致。
> （若希望保留历史观感，可选择性地把旧记录一次性回填进批次表，但会把旧的虚高语义一并带入，不推荐。）

---

## 4. 数据模型改动

### 4.1 扩展 `dvadmin_pqkds_pre_distributed_keys`（密钥池）

现状字段：`pool_id` / `key_index` / `node1` / `node2` / `algorithm` / `encrypted_key_data` / `key_hash` / `status` / `expires_at`

**问题**：`algorithm` 现在**只有一个字段**，语义是"用哪种格密码封装"。D3+D4 后需要**区分载荷算法与封装算法**。

```sql
ALTER TABLE falcon_kds.dvadmin_pqkds_pre_distributed_keys
  ADD COLUMN payload_algorithm  VARCHAR(20) NOT NULL DEFAULT 'aes_256'  COMMENT '载荷算法，替换后为 sm4',
  ADD COLUMN wrapping_algorithm VARCHAR(20) NULL                        COMMENT '封装算法：kyber_kem/falcon_lattice/sm2/sscl',
  ADD COLUMN source_key_id      BIGINT      NULL                        COMMENT '用户所选非对称密钥的 keymanage.key_id',
  ADD COLUMN recipient_type     VARCHAR(10) NOT NULL DEFAULT 'node'     COMMENT 'node/user',
  ADD COLUMN recipient_user_id  BIGINT      NULL                        COMMENT 'recipient_type=user 时的 kms.sys_user.user_id（逻辑引用，不建外键）';
```

`algorithm` 字段保留不删（兼容既有数据），新逻辑一律读写 `wrapping_algorithm` + `payload_algorithm`。

### 4.2 新建：用户 ↔ 节点授权表（即"节点鉴权"）

`Node` 模型当前**没有任何 user 外键**，D5 要求用户只能选择"自己有权的节点"。新建：

```sql
CREATE TABLE falcon_kds.dvadmin_pqkds_user_node_authorizations (
  id            BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id       BIGINT      NOT NULL COMMENT 'kms.sys_user.user_id（逻辑引用）',
  node_id       BIGINT      NOT NULL COMMENT 'dvadmin_pqkds_nodes.id',
  status        VARCHAR(10) NOT NULL DEFAULT 'active' COMMENT 'active/revoked',
  granted_by    VARCHAR(64) NULL     COMMENT '授权管理员',
  granted_at    DATETIME    NOT NULL,
  revoked_at    DATETIME    NULL,
  remark        VARCHAR(500) NULL,
  UNIQUE KEY uk_user_node (user_id, node_id),
  KEY idx_user_status (user_id, status)
) COMMENT='用户可通信节点授权（节点鉴权）';
```

### 4.3 新建：用户对称密钥信封表（"对称密钥查看"页的数据源）

不复用 `pre_distributed_keys`——该表的 `node1`/`node2` 均 `NOT NULL`，用户侧无 `node2`，硬塞会导致大量可空外键。独立建表：

```sql
CREATE TABLE falcon_kds.dvadmin_pqkds_user_key_envelopes (
  id                 BIGINT AUTO_INCREMENT PRIMARY KEY,
  batch_id           VARCHAR(64)  NOT NULL COMMENT '一次分发动作的批次号',
  user_id            BIGINT       NOT NULL COMMENT 'kms.sys_user.user_id',
  key_hash           VARCHAR(64)  NOT NULL COMMENT 'SM4 密钥 SHA256，用于核对，不存明文',
  encrypted_key_data TEXT         NOT NULL COMMENT '用用户所选非对称密钥加密后的 SM4 密钥（JSON）',
  wrapping_algorithm VARCHAR(20)  NOT NULL COMMENT 'SM2/SSCL/CL-Kyber/CL-Falcon',
  source_key_id      BIGINT       NOT NULL COMMENT '用户所选非对称密钥 keymanage.key_id（D17：仅允许 SM2/SSCL）',
  status             VARCHAR(20)  NOT NULL DEFAULT 'unused' COMMENT 'unused/used/expired',
  expires_at         DATETIME     NOT NULL COMMENT '固定 24h（D8）',
  created_at         DATETIME     NOT NULL,
  KEY idx_user_expire (user_id, expires_at),
  KEY idx_batch (batch_id)
) COMMENT='分发到用户本人的对称密钥信封';
```

### 4.4 新建：分发批次表（可选但建议）

一次"选节点 + 分发"动作需要可追溯（哪些节点、用哪把用户密钥、成功几个）：

```sql
CREATE TABLE falcon_kds.dvadmin_pqkds_distribution_batches (
  id                 BIGINT AUTO_INCREMENT PRIMARY KEY,
  batch_id           VARCHAR(64) NOT NULL UNIQUE,
  user_id            BIGINT      NOT NULL,
  source_key_id      BIGINT      NOT NULL COMMENT '用户所选非对称密钥',
  wrapping_algorithm VARCHAR(20) NOT NULL,
  node_ids           TEXT        NOT NULL COMMENT 'JSON 数组',
  node_success_count INT         NOT NULL DEFAULT 0,
  user_envelope_ok   TINYINT(1)  NOT NULL DEFAULT 0,
  status             VARCHAR(20) NOT NULL COMMENT 'pending/partial/success/failed',
  created_at         DATETIME    NOT NULL
) COMMENT='用户发起的对称密钥分发批次';
```

### 4.5 身份打通（D7）

`falcon_kds` 侧新增的表一律用 `user_id` **逻辑引用** `kms.sys_user.user_id`，**不建跨库外键**（MySQL 跨库外键不可行）。
`dvadmin_system_users` 退化为"节点侧附属信息"，不再作为登录身份源；其登录入口在管理端聚合后应关闭（见 §7 P4）。

---

## 5. 接口清单

### 5.1 新增（分发模块 Django，走 `/pqkds-api/`）

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/user-nodes/` | 当前登录用户被授权的节点列表（仅返回自己的） |
| POST | `/key-pool/distribute-to-user/` | **核心**：入参 `{ source_key_id, node_ids[], count }` → 生成 N+1 信封 + 批次记录。**必须校验** `source_key_id` 的 `encryt_name ∈ {SM2, SSCL}`（D17）与 `node_ids` 均在该用户的节点授权内 |
| GET | `/user-symmetric-keys/` | 我的对称密钥列表（含剩余有效期） |
| GET | `/user-symmetric-keys/{id}` | 单条详情 |
| GET | `/distribution-batches/` | 我的分发批次记录 |

**鉴权硬要求**：以上接口的 `user_id` **一律取自令牌，禁止从请求参数取**，否则可越权查看他人对称密钥。

### 5.2 新增（主 KMS，供分发模块服务令牌调用）

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/lifecycle-api/internal/user-key/{keyId}` | 按 key_id 返回用户非对称公钥 + 算法名（供封装 SM4 用） |
| GET | `/lifecycle-api/lifecycle/operation-record/mine` | 当前用户的操作日志（仅本人） |

沿用 `kms_adapter.py` 既有的 `X-KMS-Service-Token` + `X-KMS-Service-ID` 双头鉴权与 `hmac.compare_digest` 校验。

### 5.3 修改

| 位置 | 改动 |
|---|---|
| `key_pool_service.py` `generate_kyber_pool` / `generate_falcon_pool` / `generate_distributable_pool` | DEM 层 AES-256-GCM → **SM4**；密钥 32B → 16B |
| `falcon_aes_session_encryption.py` / `kyber_aes_session_encryption.py`(+`_optimized`) | 类名与内部 AES 调用改 SM4；**建议改名为 `*_sm4_session_encryption.py`** |
| `key_pool_local_storage.py` | 本地 JSON 中 `key_hex` 由 64 hex → 32 hex；注释中 "AES 会话密钥" 改 "SM4" |
| `models.py` `PreDistributedKey` | 增加 §4.1 字段；`ALGORITHM_CHOICES` 语义拆分 |
| `kms_adapter.py` `capabilities` | `sm2`/`sscl` 由 `available: False` 改为真实可用 |
| 新增 SM2/SSCL 封装实现 | 见 §1.3，**这是最大新增项** |

---

## 6. 页面与菜单清单

### 6.1 用户侧（`kms-user`）

| 路由 | 页面 | 动作 |
|---|---|---|
| `/workbench` | 总览 | **整页保留、不重画**（已确认）。仅两处改动：① 去掉 `PUBLIC_KEY_LIST` 权限卡片（`WorkbenchView.vue:289,422-425,629-639`）；②「分发记录」KPI 与「分发状态分布」图改数据源。逐元素对照见 §3.6.5 |
| `/generate` | 非对称密钥生成 | 保留，删公钥列表 Tab（`GenerateView.vue:205-236` + `publicKeys`/`approvedPublicRequestId` 逻辑） |
| `/lifecycle` | 更新与回收 | 保留 + 新增「申请自动更新权限」按钮与弹窗（迁移原 `PermissionView` 的提交/回退逻辑） |
| `/distribute` | 分发 | **重做**：节点多选（限自己有权，上限 10） + 自己的非对称密钥下拉（**仅 SM2 / SSCL**，D17，旁附不可选 PQ 的说明） + 分发按钮 + 批次结果 |
| `/symmetric-keys` | 对称密钥查看 | **新增**：算法(SM4)／密钥哈希／封装算法／来源密钥／过期时间／剩余有效期／状态 |
| `/my-logs` | 我的操作日志 | **新增**：按 `user_id` 过滤，含操作类型／对象／时间／结果／链上信息 |
| `/permissions` | 权限管理 | **删除** |
| `/user/profile` | 个人中心 | 保留 |

### 6.2 管理侧（`kms-updatedel` 作统一壳）

| 菜单组 | 子项 | 来源 |
|---|---|---|
| 总览 | 总览仪表盘 | 已有 |
| 资产查询 | 用户密钥查询／公钥查询／用户密钥池／密钥用户管理 | 已有（满足"可查看所有资产"） |
| 密钥生命周期 | 密钥更新／密钥回收／密钥自动更新 | 已有 |
| 分发与区块链 | **区块链管理**／**节点管理** | **聚合** `pqkds/blockchain`、`pqkds/nodes` |
| 用户与节点授权 | **节点鉴权配置**（§4.2 的维护界面） | **新增** |
| 权限与审计 | 权限审批／操作日志／登录日志 | 已有（`PUBLIC_KEY_LIST` 审批项移除，只剩自动更新） |
| 测试 | **测试页面**（压测／安全测试／其他） | **聚合** `/acceptance/#/load-test`、`#/security`、`#/others` |
| 系统管理 | 用户／角色／菜单／部门／字典／参数／通知／岗位 | 已有 |
| ❌ 删除 | 密钥生成 | D-原文"生成它不需要" |
| 算法说明 | 算法图解与演示／更新回收速览／轮换计算揭秘 | 已有，**保留**（Q3） |

### 6.3 登录与角色分流（D9）

1. **唯一登录入口**，登录后调 `getInfo()` 取 `roleLevel`
2. `roleLevel <= 0` → 跳 `/admin/`（管理控制台）；否则 → 跳 `/user/workbench`
3. **删除** `kms-user/front/src/layout/components/Navbar.vue:12-34,80-91` 的"进入管理控制台"按钮
4. 建议把管理端路径由 `/updatedel/` 改为 `/admin/`，与角色语义一致；需同步 nginx `location`、vite `base`、`.env`、书签
   （**注意**：`base` 改动会让产物路径变化，必须连同 nginx 缓存策略一起改，见 `kms-ops/README.md`）
5. **未登录直访**：两端口都保留各自登录页，但互相跳转

---

## 7. 分阶段实施

> 原则：每阶段独立可验证、可回滚；高风险项（§1.3 密钥格式兼容）前置为"验证实验"而非直接开发。

### P0 · 前置验证实验（必须先做）

#### P0-A · 静态部分 ✅ 已完成（结论见 §3.2.3）

不需要 Docker，已通过读代码确定四种算法的密钥格式与私钥存放位置。**核心产出**：

- SM2 / SSCL：公钥统一为 130 hex 的 SM2 曲线点；加密要用 `finalPublicKey` 而非 `ua`
- **CL-Kyber / CL-Falcon：完整私钥明文存在 `keymanage.key_value` 里** → 服务端必然能解密 → **Q7 对这两类算法不成立**
- 列表接口已有脱敏，UI 不泄露

#### P0-B · 运行时部分（**需要 Docker**）· ✅ 已完成

报告：`kms-ops/experiments/p0b-server-side-decrypt/REPORT.md`
（5 个可运行脚本 + 原始 stdout 证据 + 真实库行转储；未改动任何仓库文件、未写库）

| 子项 | 内容 | 结论 |
|---|---|---|
| B-1 | **SM2 / SSCL：服务端（`ms` + `key_value` 中的 `t_A` / `SSCLEA`）能否解开用户信封？** | ✅ **"不能"** —— **已执行**（正/负对照）**＋代码阅读** |
| B-2 | ~~CL-Kyber / CL-Falcon 能否解密~~ | ✅ 已由 P0-A 判定为"能"（该类密钥完整私钥明文落库）|

**结论：Q7 成立，R10 解除。** 机密性的唯一支点是"浏览器本地标量 `u` 永不出客户端"：

- SM2：`d_A = (t_A + u) mod n`。服务端有 `t_A`、`W_A`、`U_A`（`ua` 列）以及 `ms`/`λ`，
  **唯一缺的输入就是 `u = dlog_G(U_A)`**，它从不传输、不落库。
- SSCL：`sk = u + c₀·m`。**整个"域"那一半都在服务端**（服务端存 `SSCLEA = c₀`
  与份额 `(m, m_y)`，浏览器那步拉格朗日插值可证明只是把存着的 `SSCLEA` 取回来），
  所以 SSCL 的机密性**同样**只押在那一个 `u` 上。
- **为什么"不能"这个否定结论可信**：正对照能正常解密，且与 `gmssl` 双向互通；
  SM2 的推导恒等式在 **17/17 条真实库行**上验证通过；22 个"服务端可推导的候选标量"
  在活密钥上全部失败、15 个在真实库行（`key_id=4`）上全部失败；
  一个能把故意弱化成 32 位的 `u` 在 2.75 秒内破解的 BSGS 求解器，
  对真实的 `u` 需要约 2¹²⁸ 次群运算（按实测 38.7k ops/s 约 8.8×10³³ 秒）。

**必须守住的红线与回归用例**：一旦有任何一处把 `u` / 浏览器端 `privateKey`
发给服务端或写进日志，Q7 立刻失效。→ 加一条**断言式回归用例**：扫描所有出站请求体，
断言其中不含客户端本地份额。记为 **R1'**。

**P0-B 额外查出的四件事（计划原先没有，按严重度排序）**

1. **`ms` 是硬编码的公开默认值，而且就是线上生效值**：
   `6BDD93B210F79415FE0F6388C1C932C208319FF7D7E99C972B3535C9F19A9FF9`
   （`kms-generate/go-backend/config/config.go:44,48`、`KgcMasterSecret.java:32-33`；
   `KGC_MASTER_SECRET` 在**所有容器里都是空的**）。更糟的是它
   **可以只用一个只读 API 调用反推出来**：`POST /generate/request/PARTIAL_KEY`
   带 `key_use=演示计算` 会回吐 `kgcRandomW + kgcLambda`
   （`sm2_generator.go:181-194`），于是 `ms = (t_A − w)·λ⁻¹`；
   又因为 `ms·G` 等于 `/comparam` 返回的 `PPub`，得到独立交叉验证。
   **影响**：KGC 被完全攻破（可为任意身份伪造部分私钥），
   **但不影响信封机密性**（信封靠的是 `u`）。记为 **R17**。
2. **加密目标点**（已在 §3.2.3 展开）：只有 `P_A = W_A + λ·P_pub` 既用户可解又服务端不可解。
   本计划原文写的 `finalPublicKey`（= `W_A`）会让信封**谁都打不开**。记为 **R16**。
   > 我已经独立复核过这条：`UpdatedelChainService.java:354` 正是
   > `wA.add(pPub.multiply(lambda))`，而
   > `d_A·G = (w + λ·ms + u)·G = (w·G + u·G) + λ·ms·G = W_A + λ·P_pub`
   > —— 与 `EccKeyGenerator` 的 `W_A = w·G + U_A`、`λ = SM3(W_A‖H_A)` 完全吻合。
   > 数学成立，原文确实错了。
3. **脱敏结论需要更正**：P0-A 说"列表接口已脱敏，UI 不泄露"，那是基于
   `GenerateController.extractPublicValue` —— 而 `public-list` 删除后该方法在本计划内一度不存在。
   P0-B 实测：`/generate/key*` 与 `/lifecycle/keymanage*` 的**列表/详情接口都会原样返回 `key_value`**
   （管理员能看到所有用户的行），`key_generate_log` / `key_chain_task` 两个 Kafka topic
   **在已发布的 9092 端口上明文携带 `key_value` + `ua`**；`legacy-kms` 会把
   `kgcRandomW` / `kgcLambda` 写进 `key_value`（`keymanageServiceImpl.java:330-331`）；
   AES 行的 `key_value` 就是**明文对称密钥**（活行值为 `s3cr3tK3y`）；
   MySQL 3307 用仓库里的 root 口令直接可连。记为 **R18**。
   **注意**：以上没有一条泄露 `u` —— 这正是上面两个"不能"结论成立的原因。
4. **两个功能性缺陷**：
   - SSCL 已发布的公共份额**在每次进程启动时重新生成且从不持久化**，
     所以库里那 4 行 SSCL 已经与今天的 `/comparam` 对不上（客户端算出的
     `domainPrivate` 会与链上的 `P_A` 不一致）。记为 **R19**。
   - 22 行里有 **16 行共用同一个 `ua`**，即一个会话的 `u` 在保护多把密钥。记为 **R20**。

#### P0-C · 运行时部分（**需要 Docker**）· ✅ 已完成

**KMS 生成的公钥能否被分发模块直接用于封装 16B 载荷？**

报告：`kms-ops/experiments/p0c-kms-pubkey-compat/REPORT.md`
（一命令复现：`kms-ops/experiments/p0c-kms-pubkey-compat/run_experiment.ps1`，7 项探针全通过）

| 算法 | 分发模块已有封装实现？ | 能接受 KMS 生成的公钥？ | 16 字节往返 |
|---|---|---|---|
| AES-256 | 有（AES-GCM） | n/a（该行 `key_value` 是字面量 `s3cr3tK3y`） | 成功（先哈希占位值） |
| **SM2** | **无** | **无路径** | **不可能 —— 运行时根本没有 SM2 实现** |
| **SSCL** | **无** | **无路径** | **不可能 —— 同上** |
| CL-Falcon | 有（`fast_encrypt`，纯 NumPy） | 仅接受 pqkds 形状的密钥 | 成功（逐字节一致） |
| CL-Kyber | 有（真 CRYSTALS-Kyber KEM + CL 矩阵方案） | 仅接受 KEM 字节串 | 成功（512/768/1024） |
| CL-Kyber/CL-Falcon **来自主 KMS** | — | **不存在这种密钥** | N/A |

**三条改变计划的结论**

1. **R1 是空的**（不是"通过"，是"不成立"）。Go 服务**不生成格密钥**——它回调
   `pqkds` 本身、只存一个元数据 blob；Java 服务对非 SM2/SSCL 直接拒绝
   （`仅支持 SM2 和 SSCL 算法`）。运行库中 CL-Kyber/CL-Falcon 行数为 **0**
   （实际 distinct 集合为 `AES-256 / SM2 / SSCL`）。所以"两套 KGC 格参数是否兼容"
   这个比较对象根本不存在，R1 关闭。
2. **真正的阻塞项是 SM2/SSCL 零实现**：容器内没有 `gmssl`、没有 SM3、
   `cryptography 50.0.1` **有 SM4 但无 SM2**（`ec.SM2` 不存在）、
   `pycryptodome 3.20.0` 既无 SM3 也无 SM4；pqkds 自己的
   `kms_adapter.py:108-115` 也早写明 `sm2/sscl: available=False`。
   → P3 必须先补密码学底座：**新增 `gmssl-python`（需重建镜像）**，或
   **在现有手写点运算层之上自实现 SM3 + ECIES**。
   工期：**SM2 = M（2–4 天）；SSCL = S（0.5–1 天）**，因为 SSCL 的封装目标点
   **已可从存量数据推导**（`P_A = u_A + (e_A·m mod n)·G`，实测 4/4 为合法曲线点），
   缺的只是密码器本身。
3. **真正的不兼容是存储宽度**：`kms.keymanage.key_value` 是 `varchar(1024)`，
   而一条 CL-Falcon/CL-Kyber 记录有 3,119–3,534 字符 → 在生效的
   `STRICT_TRANS_TABLES` 下会直接 **ERROR 1406** 插入失败；
   一把 Falcon 公钥 17,050,904 字符（超限 16,651 倍）。
   Kyber-512 的 KEM 公钥 base64 也有 1,068 字符 > 1024。
   → 缓解办法（报告已验证可行）：**PQ 密钥不要写进 `key_value`**；
   `falcon_kds.dvadmin_pqkds_nodes.{kyber,falcon}_public_key` 本来就是 `longtext`，
   把材料存那里、`key_value` 只留 `node:<id>:falcon_public_key` 这样的引用
   （`views.py:_kms_key_reference` 已经是这个思路）。

**顺带确认的事实（对 P3 直接有用）**

- `SSCLKey` **不是椭圆曲线点** —— 那个 `04` 只是格式标签，两半都是标量；
  而 SM2 的 `finalPublicKey` 实测 **17/17 都是合法曲线点**。
  所以 P3 里 SM2 可以直接用 `finalPublicKey` 做加密目标，SSCL 不行，
  要按上面的公式先算出 `P_A`。
- 节点腿：用**真实存在的磁盘密钥池**
  （`/backend/node_key_pools/1/pool_pool_dist_6dd49de1ab29273d.json`）
  跑 `fast_encrypt`/`fast_decrypt` 16 字节往返 **成功**，含 FCTV2 序列化路径与生产服务方法；
  池完整性 `key_hash == sha256(raw bytes)` 50/50 通过。
  **但两个池都已过期约 137 天且从未被消费** —— P3 联调前需要先重新生成池。
  库中与磁盘上**都不存在 Falcon 池**，Falcon 节点腿只有合成验证。

**P0-C 明确未验证、需要单独评审的两件事**（报告作者主动标注，不要当成绿灯）

- `pqkds` 的格 KGC **安全性未评估**，且有两处可疑：
  `D_id` 由 `sha256(user_id)` 确定性派生（"部分私钥"可被任何知道 user_id 的人算出）；
  `kgc_keys = {'sk_KGC': A}` 把主密钥设为**公开**矩阵。往返测试通过只是功能结论。
- 报告中的 **ERROR 1406 结论是推断**（按列宽 + 读到的 `@sql_mode` 推出，未真的 INSERT）；
  Go→pqkds 的委托是**进程内复现**，未走 HTTP（为避开操作日志写入）。
- 另发现一处真实缺陷（两行可修）：`FalconCrypto` 是死代码，因为
  `FALCON_512_DLL` 常量漏了 `falcon512/` 子目录；该文件其实是 ELF 只是名叫 `.dll`，
  按正确路径加载后 Falcon-512 签名/验签往返正常。Falcon-1024 的 ELF 缺失，无法测试。


### P1 · 登录分流 + 用户侧页面增删（低风险，直接响应诉求）· ✅ 已完成

1. 删除 `PUBLIC_KEY_LIST` 全链路
   - 前端：`permission-api.js` 的权限项、工作台权限卡片项、生成页「公钥列表」Tab、
     生成页汇总卡里的「公共密钥权限」卡与 `/permissions` 链接
   - 后端（**范围比原计划大**）：生成域整套权限申请子系统整体删除 ——
     `PermissionRequestController`、`PermissionRollbackTask`、`PermissionRequest`、
     `PermissionRequestMapper`(+XML)、`IPermissionRequestService`、
     `PermissionRequestServiceImpl`、`GenerateController.publicList`
2. 删除「权限管理」页（`views/permissions/` 目录连同路由一并删除）；
   申请入口迁为「更新与回收」页的**按钮 + 弹窗**（`openPermissionDialog` / `submitPermission`），
   并把原先"去权限页申请"的提示文案全部改为"点击上方按钮"
3. 新增「我的操作日志」页 `views/logs/MyLogsView.vue`（三个 Tab：密钥操作 / 操作日志 / 登录日志）
4. 登录后按 `roleLevel` 分流；删除 Navbar 跳转按钮
5. 管理端菜单删「密钥生成」（`mysql/init/21_*.sql`）

**实施中偏离原计划的地方（都有原因）**

| 偏离 | 原因 |
|---|---|
| **新增 `MyLogController`（3 个接口）而不是复用 `/monitor/*`** | RuoYi 自带的 `/monitor/operlog`、`/monitor/logininfor` 都要管理员权限标识，且**允许调用方自填 `operName`/`userName`**；直接放开等于让任何登录用户读他人日志 |
| **在 `SysOperLogMapper.xml` / `SysLogininforMapper.xml` 各加一个"等值"条件** | 原 XML 的 `operName`/`userName` 走的是 `LIKE '%x%'`。实测库中 `test` 有 1 条登录日志、`test01` 有 13 条 —— 用 LIKE 过滤会让 `test` 读到 `test01` 的全部记录。改为 `params.operNameExact` / `params.userNameExact` 等值匹配，值由服务端从令牌注入 |
| **新增 `GET /generate/key/public-assets`（管理员专用）** | 删掉 `public-list` 把管理端「公钥查询」页打断了（该页正是打这个接口）。管理端需要"查看所有资产"（§6.2），故补一个**仅管理员、只回公钥**的接口。它比被删的旧接口更严：旧接口是"申请即得"，新接口只认 `role_level <= 0`，且**对格算法一律不回 `keyValue`**（那里面是完整私钥） |
| **`userKeys` 页同时删掉「密钥生成」按钮与表单弹窗** | 既删了「密钥生成」菜单却留着同页的生成按钮，等于"菜单没了功能还在"。该页因此变成纯资产视图，保留「更新」 |
| **管理端准入判据由 `role_id === 1 \|\| === 2` 改为 `role_level <= 0`** | 原判据把 `role_id=2`（普通角色）也放行，而普通用户恰好持有它 —— 等于对普通用户开放整个管理端；且 `test01`/`user01` 持有的 `role_id=3` 在 `sys_role` 里根本不存在。这是 P1 顺手修掉的一个真实越权面 |
| **修 `kms-ops/build-local.ps1` 的 `mvn package` → `mvn clean package`** | 本次实际踩到：删除源文件后 `target/classes` 里的旧 `.class` 会被重新打进 jar，导致「代码已删、接口还在跑」。`generate-java` 一度仍在响应 `/permission/request/list` 就是这个原因 |
| **修掉"临时授权改写 `role_level`"的真缺陷** | 更新域 `PermissionRequestService.approve()` 会把申请人写成 `role_level=0`（D9 之后 = 下次登录被送进管理控制台）；`rollback()` 会写已废弃的 `1`。已彻底移除该副作用，并删掉死掉的 `SysUserMapper.updateRoleLevel`。详见 §3.4 的说明 |
| **`PermissionRequestService.submit()` 由服务端固定 `requestLevel`** | 原来不设置它 → `NULL` 写进 NOT NULL 的 `request_level` 列 → 调用方漏传一个字段就只得到一句笼统的"系统内部错误"。本域只有 AUTO_UPDATE 一个功能，目标等级固定为 0，本就该由服务端定 |
| **给 `verify-admin-pages.mjs` 补"落到 404 兜底页即判失败"** | 该脚本原先只采集运行时错误，而"路由写错、页面其实没打开"是**干净渲染**，零错误 —— 巡检会把 4 个实际没打开的页面报成 ok。本次就是这么发现并修正的 |
| **`doc/frontend-role-boundary.md` 的 §4.3 / §4.4 / §6.2 就地标注被取代** | 该文档描述的是 3 级模型、双申请项、以及"给管理员一个跳转按钮"—— 三条都与 Q2/D1/D9 相反，不标注会误导后来者 |
| **一并修复遗留的 `kms-generate/front`（服务在 `/generate/`）** | 该应用仍被 nginx 提供、仍被 `check.ps1` 断言 200，但它的多个页面直接调用被删掉的两个接口，P1 之后会当着用户的面报错：`/generate/key/public-list`（公钥列表 Tab 与公钥查询页）、`/generate-api/permission/request/*`（整个「系统权限审批」页）。**不能留下一个可达但坏掉的界面**，故按与 `kms-updatedel/front` 完全相同的方式修复（改接口路径、删掉已无常量语义的页面与入口）。 |

> **关于 `/generate/` 应用的建议（尚未执行，需你拍板）**：`kms-generate/front` 现在是一个
> **与统一管理端高度重复的遗留应用** —— `kms-updatedel` 早已把它的页面合并进来
> （仓库里还留着 `kms-updatedel/front/src.bak-premerge/` 作为痕迹），§0.1 也明确"改为单一管理控制台"。
> P1 只做到"不让它坏"，**没有下线它**。建议在 **P4/P5** 里连同以下动作一起处理：
> 移除 nginx `location /generate/`、从 5 端前端构建里去掉它、同步 `check.ps1` 与 `ship.ps1`，
> 并按 **R8** 的注意事项重跑 `tools/smoke-frontends.mjs`。这样前端交付物会从 5 端降到 4 端。

**验证结果（全部实测通过）**

| 脚本 | 结果 |
|---|---|
| `tools/verify-p1.mjs`（本次新增，**36 项断言**） | **36 / 36** |
| `tools/verify-admin-pages.mjs 9222 <out> admin` | **27 / 27**（含 4 个看板快捷入口跳转实测） |
| `tools/verify-admin-pages.mjs 9222 <out> user`（本次扩展支持用户前台） | **8 / 8**，含两条 P1 专有断言：`/permissions/index` → 404、管理员访问 `/user/workbench` → 被整页重定向到 `/updatedel/index` |
| `tools/verify-admin-pages.mjs 9222 <out> generate`（本次扩展支持遗留生成端） | **12 / 12**（该应用被 P1 删掉的接口打断后已修复） |
| `tools/smoke-frontends.mjs` | 5 端全部通过 |
| `tools/verify-workbench-shape.mjs`（本次新增） | **通过**：KPI **4 张**（我的密钥 / 有效密钥 / 分发记录 / 待审批申请）、图表 **5 张**（近 7 天密钥生成趋势 / 密钥算法分布 / 密钥状态分布 / 上链状态分布 / 分发状态分布），5 个 canvas 全部渲染。这条是 §3.6.5 的硬性约束，P1 改过 `WorkbenchView` 故必须实测 |
| `kms-ops/check.ps1` | 19 / 19 |

> `verify-p1.mjs` 里有几条断言特意写成"能咬人"的形式，而不是走过场：
> - 越权注入：普通用户把 `userId=1` / `operName=admin` / `userName=admin` 塞进查询串，
>   断言返回结果里**没有一行**属于他人；
> - LIKE 回归：用真实的 `test` vs `test01`（13 条）数据碰撞，断言 `test` 只看到自己的；
> - 反向对照：同时断言 `test` **确实能读到自己的**日志，避免"接口坏了返回空"被误判成通过；
> - `public-list`：因该路径会被 `GET /generate/key/{keyId}` 捕获而报参数类型错（HTTP 200 + code 500），
>   故断言的是"**不返回任何密钥列表**"而不是"返回 404"；
> - **拒绝理由要具体**：判断"权限被拦"时不只看 `code=500`，还要求消息里出现
>   `没有自动更新操作权限` —— 否则"因为别的原因报 500"（例如 keyId 为空）会被错当成拦截成功。
>   这一条是实测踩出来的：早期版本就因为只看 code，让 `keyId 不能为空` 冒充了"权限拦截"；
> - **前置失败即短路**：测试密钥没建出来时，跳过依赖它的审批断言，而不是继续产出一串假 OK；
> - **role_level 不变量**：审批通过/回退后都必须仍是 2，**同时**断言临时权限确实生效过 ——
>   两条一起看才能排除"把功能改坏了所以 role_level 没变"这种假通过。

> `verify-p1.mjs` 里有几条断言特意写成"能咬人"的形式，而不是走过场：
> - 越权注入：普通用户把 `userId=1` / `operName=admin` / `userName=admin` 塞进查询串，
>   断言返回结果里**没有一行**属于他人；
> - LIKE 回归：用真实的 `test` vs `test01`（13 条）数据碰撞，断言 `test` 只看到自己的；
> - 反向对照：同时断言 `test` **确实能读到自己的**日志，避免"接口坏了返回空"被误判成通过；
> - `public-list`：因该路径会被 `GET /generate/key/{keyId}` 捕获而报参数类型错（HTTP 200 + code 500），
>   故断言的是"**不返回任何密钥列表**"而不是"返回 404"。

### P2 · 对称层 AES-256 → SM4（中风险，独立可测）· 🔄 进行中

**已完成**（逐项对应下面的编号）：

| 编号 | 内容 | 状态 |
|---|---|---|
| 1 | `pqkds/sm4_crypto.py`：`SM4Crypto`（SM4-GCM）+ `LegacyAESCrypto`（读历史）+ `PayloadCipher`（按长度/信封标记分派）。**用容器自带的 `cryptography`，无需新增依赖** | ✅ |
| 1 | `backend/tests/test_sm4_crypto.py`：**19 项**，含 GB/T 32907-2016 两个标准向量（单块 + 10⁶ 迭代）与全部认证失败用例 | ✅ 19/19 |
| 2 | `crypto_utils.AESCrypto` 改为委托 `PayloadCipher` —— 一处改动即覆盖 `CryptoUtils` / `kgc_service` / `key_update_service` / `real_crypto_with_fallback` | ✅ |
| 2 | `key_pool_service.py` **三处生产写入点**（kyber 池 / falcon 池 / 可分发池）：载荷密钥 32B → 16B，KEK 由共享秘密派生，信封加 `payload_algorithm` | ✅ |
| 2 | `views.py` **三处读写点**按信封标记分派 SM4 / 历史 AES | ✅ |
| 2 | `kyber_aes_session_encryption.py` 整体重写为 SM4（保留历史 AES 读取分支） | ✅ |
| 2 | `node_service.py`：`real_aes` 改为按长度分派（**旧实现硬性要求 ≥32 字节，SM4 会直接报错**）；`encrypt_message` 切 SM4 | ✅ |
| 3 | `key_pool_local_storage.py`：明确 32/64 字符双长度，新增 `payload_key_of()` 校验并在取用点跳过损坏条目 | ✅ 100 条真实历史条目全部可读 |
| 5 | `payload_algorithm` 列 + `0003`/`0004` 迁移（按**信封内容**回填，不按时间切） | ✅ 已应用 |
| 6 | D12：删除 `LifecycleService.generateAesKey()` 与 AES 分支 + `22_*.sql` 清理那行明文对称密钥 | ✅ |
| — | 集成自测 `backend/tests/test_sm4_pool_integration.py`：新数据走 SM4、**历史 AES 信封仍可解** | ✅ 4 组通过 |

**剩余**：

| 编号 | 内容 |
|---|---|
| 4 | 文件/类名重命名：`*_aes_session_encryption.py` → `*_sm4_session_encryption.py`（牵动 import；当前已在模块 docstring 里标注"名字是历史遗留"，功能无影响，故放在最后做） |
| 7 | 归档/标注测试与实验脚本（`benchmark_key_pool.py`、`ablation_experiment.py`、`performance_benchmark_test.py`、`certificateless_kyber_node_keygen.py`），明确其不参与运行 |

**验证**：SM4 测试向量 ✅；分发 → 本地落盘 → 解封回读端到端 ✅；**旧 AES 密钥池数据仍可读取与使用** ✅（拿磁盘上真实存在的 100 条历史条目实测）。

> 原始七步清单（供对照，已不重复展开）：引入 SM4 实现并先写国标向量单测 → 替换生产路径 DEM 层
> （32B→16B）→ 本地 JSON 双长度兼容 → 类名同步 → 数据库 `payload_algorithm` → 删 `generateAesKey()`
> → 归档实验脚本。工作面全清单见 §1.1.1。

#### P2 前置结论（已实测，**显著降低本阶段风险**）

P0-C 与本次补充验证确认：**容器内已有的 `cryptography 50.0.1` 自带 SM4，P2 不需要新增依赖、不需要重建镜像。**

实测（在 `dvadmin3-django` 容器内直接跑，结果如下）：

| 检查项 | 结果 |
|---|---|
| `cryptography` 版本 / `algorithms.SM4` 是否存在 | `50.0.1` / **存在** |
| **GB/T 32907-2016 附录 A.1** 单块向量（`key == 明文 == 0123…3210` → `681edf34d206965e86b3e94f536e4246`） | ✅ **完全一致** |
| **GB/T 32907-2016 附录 A.2** 10⁶ 次迭代向量 → `595298c7c6fd271f0402f804c33d3f66` | ✅ **完全一致** |
| ECB / CBC 往返 | ✅ |
| **GCM 往返 + 篡改必被检出** | ✅（`modes.GCM` 与 SM4 组合可用） |
| 密钥长度约束 | 仅接受 **16 字节**（8/24/32 全部拒绝）——正好对应"密钥 32B → 16B"的改动 |
| `gmssl` / `Crypto`(pycryptodome) | 均**不存在**（`Crypto` 实际是 `cryptodomex` 的命名空间） |

两点推论：

1. **P2 的密码学部分可以直接开工**，用 `cryptography` 的 `algorithms.SM4`，
   配 `modes.GCM` 即可替代原来的 AES-256-GCM（`key_pool_service.py:124`）。
   原本担心的"要装 `gmssl`、要重建镜像"只对 **P3 的 SM2** 成立，与 P2 无关。
2. 密钥长度从 32B 改成 16B 时，`algorithms.SM4` **会主动拒绝**非 16 字节输入，
   所以"漏改一处仍传 32 字节"会在调用点立刻抛异常，而不是静默降级 —— 这对 P2 是好事。

> 注意：GB/T 32907-2016 的两个向量是我在容器里**实跑比对**过的，不是抄文档。
> 建议 P2 把这两个向量直接固化成单测（§9.2 的"SM4 正确性"项），
> 这样以后换库或升级 `cryptography` 时会立刻暴露不兼容。

### P3 · 分发链路（核心新功能，依赖 P0/P2）· 🔄 进行中

**进度**

| 步骤 | 状态 | 说明 |
|---|---|---|
| 0b 用户侧密钥文件（导出/导入） | **✅ 已完成并验证** | 见下方 §P3-0b |
| 0 固定加密目标点 `P_A` | **✅ 已完成并验证** | 见下方 §P3-0 |
| R2' SM2/SSCL 密码学底座 | **✅ 已完成并验证** | 见下方 §P3-R2' |
| 1 三张新表 + 迁移 | **✅ 已完成** | `0005_add_user_distribution_tables` 已应用：`user_node_authorizations` / `user_key_envelopes` / `distribution_batches` 三表建成；`pre_distributed_keys` 补上 `wrapping_algorithm` / `source_key_id` / `recipient_type` / `recipient_user_id`（`algorithm` 按计划保留不删） |
| 2 `WRAPPERS` 注册表 | **✅ 已完成并验证** | `pqkds/wrappers.py`。**节点腿零改动**（D10）：`KyberWrapper`/`FalconWrapper` 只做**委托**，不重写既有池生成路径 —— P0-C 已验证那条路径能正确往返 16 字节载荷，重写只会引入回归 |
| 3/4 `Sm2Wrapper` / `SsclWrapper` | **✅ 已完成并验证** | 见下 §P3-3/4 |
| 5 D17 服务端收窄 | **✅ 已在两处完成** | ① 主 KMS 的 `UserPublicKeyService` 只放行 SM2/SSCL；② 分发侧 `assert_user_leg_allowed()` 白名单 |
| 7 用户公钥接口（§5.2） | **✅ 已完成** | 见 §P3-0 |
| **前置：D7 身份桥接** | **✅ 已完成（计划漏掉的关键一步）** | 见下 §P3-身份桥接 |
| 6 节点默认封装算法字段 | 待做 | |
| 8 四个用户接口 | **✅ 已完成并验证** | 见下 §P3-8 |
| 9 用户页面（分发页重做 + 对称密钥查看） | **✅ 已完成并验证** | 见下 §P3-9 |
| 10 管理端节点鉴权页 | **✅ 已完成并验证** | 见下 §P3-10 |
| 6 节点侧实际投递接线 | **✅ 已完成并验证** | 见下 §P3-6 |
| — 浏览器侧解开信封 | **✅ 已完成并验证** | 见下 §P3-浏览器侧解封 |

#### §P3-浏览器侧解封（已完成）

**P3 的最后一块，现已闭环。**

**为什么必须自己实现**：浏览器**没有 SM3**（WebCrypto 只提供 SHA 系列），
而 SM2 公钥解密需要它做 KDF 与 C3 完整性校验。让服务端代解是**不可接受**的替代 ——
那要把 `d_A` 发上去，直接放弃"服务端也解不开"这条保证（R1' 红线）。

**实现**：
- `kms-user/front/src/utils/sm3.js` —— SM3（GB/T 32905-2016），纯 JS
- `kms-user/front/src/utils/sm2-envelope.js` —— SM2 解密（C1‖C3‖C2）+ KDF + C3 校验；
  曲线参数**可注入**（原因见下）
- `SymmetricKeysView.vue` —— 「解开」按钮 + 结果展示（含指纹比对）

**★ 验收：`tools/verify-sm3-sm2-js.mjs` —— 19 / 19**

交付的是自己写的密码学代码，所以**不能只测往返一致**（自洽但错误的实现也能往返一致）。
这里用国标原文向量钉死：

| 断言 | 结果 |
|---|---|
| SM3("abc") 与 SM3("abcd"×16) 与 GB/T 32905-2016 附录 A **完全一致** | ✅ |
| ★ **用国标附录密文反解出原文 `"encryption standard"`（逐字节）** | ✅ |
| ★ **浏览器侧实现解开服务端真实封出的信封**（跨语言互通） | ✅ |
| 篡改密文 → `Sm2IntegrityError`；换私钥 → `Sm2IntegrityError` | ✅ |
| 分组边界（55/56/63/64/65/119/120/128 字节）与非法输入 | ✅ |

**★ 一个容易致命的坑（已写成断言）**：GB/T 32918.4 附录 A.2 示例2 跑在
**它自己的测试曲线**上（p = 8542D69E…），**不是生产用的 sm2p256v1**（p = FFFFFFFE…）。
直接拿生产曲线去解国标密文必然失败。因此曲线参数做成可注入，
并断言"附录的 C1 在 sm2p256v1 上**不是**合法点"—— 把这条事实固化下来，
免得日后有人"简化"掉曲线注入再把国标测试删掉。

**★ 端到端（真实浏览器）：`tools/verify-browser-decrypt.mjs` —— 8 / 8**

链路：密钥文件 → 本机密钥环 → 页面「解开」→ 显示密钥 + **指纹与库中记录一致**。
（同样要求"指纹一致"而非只看"显示了 32 位十六进制"—— 后者任何值都满足。）

> **实施中修掉的一个自身缺陷**：解密结果渲染在**详情弹窗**里，
> 而从列表行点「解开」并不会打开那个弹窗 —— 于是值算出来了却没有地方显示，
> 现象是"点了没反应、也没有报错"。已让从列表行解密时一并打开弹窗。

#### §P3-6 节点腿接线（已完成，17/17）

**先修掉了 R14（它一直在阻断整条节点密钥链路）。**

`FALCON_512_DLL = BASE_DIR / "falcon" / "falcon512.dll"` **少了一层目录** ——
真实库在 `/backend/falcon/falcon512/falcon512.dll`，而 `_load_falcon_dll()` 在
`variant == 512` 时**只试这一个路径**（1024 分支反而试了多个），
于是 **Falcon 在本项目里从来没加载成功过**。

连带影响比"Falcon 用不了"更大：`node_service.update_kyber_keys()` 途中要用 Falcon，
所以**连更新 Kyber 密钥都会失败**，报 `Falcon DLL加载失败: No working Falcon DLL found for variant 512`
—— 看起来像 Falcon 的问题，实际把**节点密钥生成整条路**堵死了，
而节点腿分发的第一步正是节点要有 Kyber 密钥。已改为候选路径列表；
验证：Falcon-512 现在可 `generate_keypair()`（pk=897 / sk=1281）并签名验签，
两个演示节点随后成功生成真实 Kyber 密钥对（pk=1068 / sk=2176）并上链。

> Falcon-1024 仍不可用（磁盘上没有它的库）。不影响 D16（默认 Kyber），但 1024 在当前镜像无法验证。

**接线内容**：
- `models.py`：`PreDistributedKey.node2` 改为**可空** —— 该表原本只表达节点间预分配
  （两个节点都不能少），而用户发起的分发只有**一个**收件节点。
  计划 §4.3 另建 `user_key_envelopes` 绕开了这个约束，但**节点那一份仍需落脚处**。
- `wrappers.wrap_for_node()` / `open_node_envelope()`：**复用 `generate_distributable_pool`
  里同一套配方**（KyberCrypto 变体判定 + KEK 派生 + SM4-GCM），既有读取端无需改动即可解开（D10）。
- `distribute_to_user()`：同一份里，用户腿与**每个节点**封的是**同一把 `payload_key`**。
  批次成功数改为按**真实封装成功数**统计，全部成功才记 `success`。

**★ 验收（`kms-ops/tests/verify_node_leg_e2e.py`，17/17）**

D10 成立与否的唯一判据是：**两条腿必须解出同一把 K**。
"两条腿各自都能解开"**不算通过** —— 若实现里各生成一把 K，两边都能解开自己的信封，
但用户发给节点的消息节点根本解不开。所以脚本解开两条腿后**逐字节比对**：

| 断言 | 结果 |
|---|---|
| 用户腿（SM2 国密）解封 → K_user，哈希与库中一致 | ✅ |
| 节点腿（Kyber 抗量子）解封 → K_node，哈希与库中一致 | ✅ |
| **★ K_user == K_node**（4 组比对） | ✅ **全部一致（16 字节）** |
| 陌生节点私钥解不开 | ✅ |
| 批次状态为 `success`（而非如实记 `partial`） | ✅ |

**实施中修掉的一个自身缺陷**：表上有 `(pool_id, key_index)` 唯一约束，
而我最初用外层循环下标当 `key_index`，一批里「份数 × 节点数」会产出多条同号记录，
撞唯一键报 `IntegrityError 1062`（听起来像数据脏，实际是编号规则错了）。
已改为批次内全局递增计数。

#### §P3-10 管理端「节点鉴权」（已完成）

**后端**（`pqkds/admin_node_authorization_views.py`）：

| 接口 | 说明 |
|---|---|
| `GET /pqkds-api/admin/users/` | 账号列表（**代理**主 KMS 内部接口，内部令牌不下发浏览器） |
| `GET /pqkds-api/admin/node-authorizations/` | 授权列表（按 userId / nodeId / status 过滤） |
| `POST /pqkds-api/admin/node-authorizations/` | 授权 |
| `POST /pqkds-api/admin/node-authorizations/<id>/revoke/` | 撤销 |

**前端**（`kms-updatedel/front/src/views/nodeauth/index.vue` + `api/nodeauth/nodeauth.js`）
+ 菜单 `25_add_node_authorization_menu.sql`。

**权限**：`roleLevel <= 0`（D9/D13），判定在**读取任何数据之前**；
`roleLevel` **取不到时按最小权限处理（拒绝）**。
实测：普通用户 **403**、无令牌 **401**、返回**不含口令哈希**。

**两个刻意的设计**：
1. **软撤销**（`status='revoked'`）而非删除 —— 撤销是安全事件，
   "曾经授权给谁、何时收回"对审计很重要；用户侧只认 `active`，撤销立即生效。
2. **`(user, node)` 唯一**：重复授权幂等；**已撤销的重新激活而非新增行** ——
   同一对出现多行会让"到底有没有权限"取决于遍历顺序。
   `granted_by` 取自**令牌里的用户名**，不取请求参数。

**实测**：授权 `created=true`/`grantedBy=admin`；重复授权幂等；撤销、重复撤销均幂等；
撤销后重新授权 `created=false` + `status=active` + `revokedAt=null`（正确"复活"）。

**端到端验证（浏览器）**：侧边栏出现「节点鉴权」→ 点击进入 → 页面含「新增授权」→
表格 **2 行** → **无 console 错误**。

> **★ 踩到并记下的两个坑（都表现为"菜单没生效"）**
> 1. **只插菜单、不插 `sys_role_menu`**：页面能通过 URL 打开、接口全正常，
>    但侧边栏里没有它 —— 现象像菜单坏了，实际是权限关联缺失。
> 2. **顶层不能直接放 `menu_type='C'`**：RuoYi 的 `getRouters` 按"顶层目录(M) → 挂子菜单(C)"
>    组织，顶层放 `C` 不会进菜单树。必须照 9001（目录）+ 5000（页面）的两级形状。
>    另外**单子目录会被折叠显示**，用户看到的其实是子项的名字，所以两者同名才不会让人困惑。

**同时新增**：KMS 内部接口 `GET /internal/lifecycle/users`（账号列表，**不含口令哈希**）。
按 §5.2 的取向由分发模块代理转发，而不是让 Django 跨库读 `kms.sys_user` ——
"谁能读账号列表"这件事应当由**拥有身份的那一侧**决定。

#### ★ 补上了巡检的一个真实盲区

`verify-admin-pages.mjs` 原先只检查"能渲染 + 无 console error"。
但组件在 setup 阶段抛错时 **Vue 会把错误吞掉**，页面渲染为空白却没有任何 console error ——
巡检于是爽快地报 `ok`。这个盲区**真的发生过两次**（响应形状没对齐导致表格空、
一次区间删除误伤 import 导致整页空白）。

现已在 `visit()` 里加入 `mustInclude` **标志性文本断言**，并：
- 给每条用户前台路由写明必须出现的文案；
- 补登记了 `/symmetric-keys/index`（原先漏登记，巡检根本看不见这个新页面）。

**并且验证了这条断言真的会咬人**：故意给"个人中心"注入一个不存在的标志词 →
巡检报 `content: 页面缺少标志性内容` 并计为失败；还原后 9/9 通过。
（覆盖率同时从 8 页升到 9 页。）

#### §P3-9 用户页面（已完成）

| 页面 | 状态 |
|---|---|
| `views/distribute/DistributeView.vue` | **✅ 已重做**。原来是**只读记录页**（只能看历史 + Excel 导出），现在是真正的分发操作页：节点多选（限自己有权、上限 10）、非对称密钥下拉（仅 SM2/SSCL）、份数、分发、批次结果。菜单名「分发下载」→「密钥分发」。**实测：批次表格 2 行、无 console 错误** |
| `views/distribute/SymmetricKeysView.vue` | **✅ 已建**。列信封 + 剩余有效期 + 本机密钥状态 + 详情弹窗（含密钥指纹）。**实测：表格 4 行、计数标记一致、无 console 错误** |
| 服务层 `services/user-distribution-api.js` | ✅ 四个接口 + 路由 + 菜单已接 |

**★ 修掉的两个"静默空白"缺陷（这类问题的共同特征是：页面空着，但控制台干净、不报任何错）**

1. **响应形状不对齐**：`requestJson` 返回的是**响应体本身**，但两个后端形状不同 ——
   RuoYi 系（generate/lifecycle）把列表放 `rows`/`total`，分发模块（Django）把载荷包在 `data` 里。
   页面按 `rows` 取值就静默拿到 `undefined`。已在服务层加 `unwrap()` 一次性对齐。
2. **我自己的编辑把组件掏空了**：一次用 `IndexOf('/**')` 到 `IndexOf('function remainingText')`
   做区间删除时，起点落在了**模块文档注释**上，于是连同全部 `import` 与状态声明一起删掉，
   setup 直接抛 `ref is not defined` → 整个页面渲染为空。
   **教训**：按"从某处到某处"整段删代码时，起点用一个**唯一的、结构性的锚点**（如 `import` 行本身），
   不要用一个在文件里出现多次的符号（`/**` 在注释里到处都是）。

> **为什么巡检没抓到这两个问题**：`verify-admin-pages.mjs` 检查的是"能渲染 + 无 console error"。
> 组件抛错后页面**确实是干净的**（Vue 把错误吞了，没有 console error），
> 所以两页都报 `ok`。**这是巡检的一个真实盲区** —— 下一轮应补一条"页面必须出现特定标志性文本/表格行"的断言，
> 而不只是"没报错"。

**⚠️ 尚未实现：浏览器侧解开信封**

「对称密钥查看」页**没有**"解开"按钮，弹窗里如实说明了原因：

> 浏览器**没有 SM3**（WebCrypto 不提供），而 SM2 解封需要 SM3 做 KDF 与 C3 校验，
> 因此必须自实现一套 SM3 + 椭圆曲线运算，并像服务端那份一样用**国标向量**验证过才能上线。
>
> **不会**改成让服务端代解 —— 那要求把 `d_A` 发给服务端，
> 直接违反"用户私钥不出客户端"这条不变量（R1' 红线）。

**服务端侧的解封链路已通过端到端验收（15/15）**，所以待补的只有浏览器侧这一份实现。

#### §P3-8 四个用户接口（已完成，端到端 15/15）

`pqkds/kms_service_client.py`（出站调主 KMS）+ `pqkds/user_distribution_views.py`（四个接口）。

| 接口 | 路径 |
|---|---|
| 我被授权的节点 | `GET /pqkds-api/user-nodes/` |
| **分发（核心）** | `POST /pqkds-api/key-pool/distribute-to-user/` |
| 我的对称密钥 | `GET /pqkds-api/user-symmetric-keys/` 及 `/<id>/` |
| 我的分发批次 | `GET /pqkds-api/distribution-batches/` |

**三条硬要求在服务端强制**：`user_id` 取自令牌自省（§P3-身份桥接）、节点必须在该用户授权内（D5）、
算法必须是 SM2/SSCL（D17，**主 KMS + 分发侧两处**纵深防御）。

**★ 端到端验收：`kms-ops/tests/verify_user_leg_e2e.py` —— 15 / 15**

这是整条链路唯一有意义的终极断言。脚本自己生成**已知的** `u`，因此能算出 `d_A`，
从而真正解开分发给自己的信封：

| 断言 | 意义 |
|---|---|
| ★ 服务端回显的 `P_A` == 脚本算出的 `d_A·G` | 封的确实是用户能解的点 |
| ★ 解封得到的 SM4 密钥**哈希与库中记录一致** | 解出来的**正是那把**密钥，不是"某 16 个字节" |
| 解出来的载荷密钥是 16 字节 | D3 的 SM4 落地生效 |
| 用陌生私钥解封**失败** | 信封确实只对 `d_A` 开放（否则等于没加密） |

**负例（实测）**：越权节点 → 403、不存在的密钥 → 400、超 10 个节点 → 400（D15）、
空节点 → 400、跨用户查信封 → **404**（而非 403：不泄露"存在但不属于你"）。

> **实施中修掉的两个自身缺陷**
> 1. **路由顺序**：我的路径原本排在 DRF `router` 之后，而 router 为 `key-pool` 生成的
>    详情路由 `key-pool/<pk>/` 会把 `key-pool/distribute-to-user/` 吃掉（pk 当成
>    `"distribute-to-user"`）→ 请求落到 `KeyPoolViewSet`，**HTTP 200 但字段全 undefined**。
>    现象是"接口通了但没数据"，很难反查到路由顺序。已移到 router 之前。
> 2. **谎报节点投递成功**：初版把 `node_success_count` 记成"选中了几个节点"、
>    `status` 记成 `success`，而节点侧投递**尚未接线**。已改为如实记 0 + `partial`。
>    谎报的代价很具体：批次列表显示"全部成功"而节点上什么都没有，排查会被引向错误方向。

> **实测发现的数据前置**：`dvadmin_pqkds_nodes` 表是**空的**（节点由应用侧注册，演示环境没人建过），
> 因此验收前先建了 2 个演示节点并给 `yx` 授权。
> **注意**：`Node` 的正式注册应走 `node_service.register_node`（会生成 Kyber/Falcon 密钥），
> 本次为验接口只建了最小行；节点腿真正投递前需要补这一步。

#### §P3-身份桥接（实施中发现，计划未列）

**发现**：§5.1 要求"四个用户接口的 `user_id` 一律取自令牌，禁止从请求参数取"，
但实测 `pqkds/views.py` 的视图**全部是 `@permission_classes([AllowAny])`** ——
**分发模块今天根本拿不到用户身份**。这不是"实现细节"，而是那四个接口的**硬前置**：
没有它，要么做不出来，要么只能信前端传来的 `user_id`（即可越权查看他人对称密钥）。

**做法**：在主 KMS 加自省接口 `GET /internal/lifecycle/introspect`。

- **双重校验**：`X-Internal-Token`（服务间，证明"调用方是分发模块"）
  **+** `Authorization`（用户令牌，证明"用户是谁"）。两者缺一不可 ——
  只有服务令牌的话，任何拿到它的人都能冒充任意用户。
- **为什么不让分发侧自己验签**：那要把 JWT 签名密钥复制一份到 Django，
  身份源就变成两处；而 D7 明确 `dvadmin_system_users` 退化为"节点侧附属信息"、
  不再作为登录身份源。走自省则**只有 KMS 一处**解释令牌。
- 令牌无效是**预期内输入**，返回 `ok=false` + `TOKEN_INVALID` 而不是 500，
  让分发侧能把"未登录"与"服务异常"分开处理。
- `roleLevel` 取不到时留空，让分发侧按**最小权限**处理，而不是默认放行成管理员。

**验证**（实测）：

| 场景 | 结果 |
|---|---|
| 合法用户令牌 | `{"ok":true,"userId":2,"userName":"yx","roleLevel":2}` |
| 不带用户令牌 | `{"ok":false,"errorCode":"TOKEN_INVALID",...}` |
| 伪造令牌（含结构正确但签名错） | 同上，`TOKEN_INVALID` |
| 无服务令牌 | `{"msg":"invalid internal token","code":500}`（被拒） |

> **实施中修掉的一个自身缺陷**：最初的写法是**成功时包 `data`、失败时直接返回顶层对象**，
> 结果调用方按 `data` 取值，失败时拿到 `undefined`，反而看不出失败原因。
> 现已收敛为统一形状 `{data: {...}}`（`wrapData()`）——
> 这类"响应形状不一致"的坑，症状是下游 `undefined`，很难倒查到接口本身。

#### §P3-3/4 封装注册表与用户腿封装器（已完成）

`pqkds/wrappers.py`：

- 四种算法收进一张表（`WRAPPERS`：SM2 / SSCL / KYBER / FALCON），
  分发主流程因此只需写一次"给谁封、用哪把公钥"，不必在每个分支重复 KEM+DEM 编排；
- `normalize_algorithm()` 吃下历史上的各种写法（`kyber_kem` / `CL-Kyber` / `Kyber` …），
  避免调用方各写一套判断；
- **D17 在服务端强制**：`assert_user_leg_allowed()` 是接口层入口，
  且 `build_user_envelope()` **先校验算法、再触碰密钥材料** —— 越权请求连公钥都用不上；
- **`algorithm` 与 `key_system` 是两个字段**。前者是密码算法（SM2/SSCL 都是 `'sm2'` 公钥加密），
  后者是密钥体系（`'sscl'`）。混用会让 `SM2Crypto.decrypt` 的算法校验直接失败 ——
  **这个坑是本模块自己的测试抓出来的**，已写成注释留在代码里。

**验证**：`backend/tests/test_wrappers.py` —— **38 / 38**

| 断言 | 意义 |
|---|---|
| ★ 用 `d_A` 解封得到**同一把** SM4 载荷密钥 | 用户腿端到端走通 |
| ★ 解封得到的密钥能**直接解开 SM4 密文** | 证明"封装"是有意义的，而不只是字节往返 |
| ★ 拒绝发生在**触碰密钥材料之前** | 故意传非法公钥：抛的是"算法不允许"而非"公钥非法"，证明前置校验生效 |
| SM2 / SSCL 各一条端到端 | 两条分支都覆盖 |
| 未知算法 vs 不允许的算法报不同的错 | 语义区分：`AES` 报"未知算法"，`kyber` 报"仅支持 SM2/SSCL" —— 混为一谈会让人误以为 AES 曾被支持 |
| 点不在曲线上 / 用错私钥 / 篡改密文 | 全部明确失败，不返回垃圾 |

#### §P3-0 加密目标点（已完成，R16 闭环）

**做法**：把 `P_A` 的推导提为**全系统唯一一份**，并对外提供接口。

- `UpdatedelChainService.calculatePA(Keymanage)` 由 private 提为 **public**，并补上完整 javadoc
  说明"这是唯一一份推导，切勿另写第二份"（计划 §3.2.3 明确要求复用而非重写）。
  SM2 走 `P_A = W_A + λ·P_pub`（`ms` 按记录的 `ms_key_id` 取）；
  SSCL 走 `P_A = u_A + (e_A·m)·G`，`e_A` 取自记录的 `SSCLEA` —— **天然不受 ms 轮换影响**。
- 新增 `UserPublicKeyService`：只做转发与状态判定，**绝不自己再推一遍**。
  同时承担 **D17 的服务端收窄**：非 SM2/SSCL、已回收、算不出来的密钥一律 `ok=false`。
- 新增内部接口 `GET /internal/lifecycle/user-public-key?keyId=`（§5.2），
  鉴权复用 `X-Internal-Token`（与 Go↔Java 同一把）。**计划原文写的"服务令牌"在本仓库没有
  KMS 侧实现** —— 既有的 `X-KMS-Service-Token` 只用于入站保护 pqkds 自己的接口；
  为不新造并行凭据体系，复用已有通道，已在该接口 javadoc 里写明。
- **绝不回退到 `finalPublicKey`**：算不出 `P_A` 时显式返回 `PA_CALC_FAILED`。
  静默回退会把"算不出来"变成一个更难查的"用户解不开"。

**验证**：`tools/verify-pa-target.mjs` —— **12 / 12**

| 断言 | 意义 |
|---|---|
| **★ `P_A == d_A · G`**（脚本自留本地份额 `u`，`d_A = (t_A + u) mod n`，`d_A·G` 在 Node 里独立计算） | **决定性证据**：服务端给的正是用户私钥对应的公开点，用户确实能解开 |
| **★ `P_A != W_A`（finalPublicKey）** | R16 的直接证据：两者确实不同；计划原文写的那一个会让信封谁都打不开 |
| 用 `W_A` 作为目标算不出 `d_A·G` | 反向证据：`W_A` 结构上就不是可用目标 |
| 不带令牌 / 错误令牌 / 不存在的密钥 | 鉴权与服务端错误码正确（注意 RuoYi 把错误放在 HTTP 200 的 body.code 里） |
| SSCL 分支同样返回合法 `P_A` | 覆盖另一条分支 |

#### §P3-R2' SM2/SSCL 密码学底座（已完成）

**风险已大幅下降**：原计划担心"容器内没有 SM2，需引入 `gmssl` 并重建镜像"。
实测发现容器自带的 `cryptography 50.0.1` **已有 `hashes.SM3` 且通过 GB/T 32905-2016 向量**，
因此**不需要新增依赖**；缺的只是椭圆曲线运算，已用纯 Python 补齐（`pqkds/sm2_crypto.py`）。

**测试：32 / 32**（`backend/tests/test_sm2_crypto.py`）

| 项 | 结论 |
|---|---|
| **标准向量** | **真实公开向量**：GB/T 32918.4-2016 附录 A.2 示例2（`tlcp.snca.com.cn` 原始中文扫描件）。`C1`/`C3`/`C2`、`t`、`(x2,y2)` **逐字节匹配** |
| **一个关键陷阱** | 该附录示例跑在**它自己的一条测试曲线**上（`p = 8542D69E…`），**不是生产的 sm2p256v1**（`p = FFFFFFFE…`）。因此曲线参数做成显式 `CurveParams` 并带自检（G 在曲线上、`[n]G = O`），测试注入附录曲线跑端到端 |
| **密文顺序** | **`C1‖C3‖C2`**（GB/T 32918.4 §6.1 A8）。⚠️ 流传的英文版 PDF 写成 `C1‖C2‖C3`，是**翻译错误**——它自己的示例都印的是 C3 在前。已用测试钉死 |
| **互通性（真实证据）** | 在 p0b 实验既有的 venv 里用 **gmssl 3.2.2** 跑了 **200/200**：双向解密 + **固定 k 下密文逐字节相同**（10 种长度） |
| **独立性检查证明什么** | 证明与独立实现互通、且布局/KDF/C3 完全一致；**不证明** gmssl 是可信预言机（见下） |
| **⚠️ 发现 gmssl 真实缺陷** | `gmssl.sm2.CryptSM2._kg` 约 **1/12 次**返回**不在曲线上**的 128 位十六进制值，或抛 `TypeError`（`_convert_jacb_to_nor` 返回 `None` 未被检查）。已抓到可复现反例。**因此绝不能因此把 gmssl 采纳为依赖** —— 它只能作为"结果需校验"的交叉核对工具 |
| 性能 | encrypt ≈ **2.4 ms/op**、decrypt ≈ **1.4 ms/op**（32 字节载荷）；首次调用一次性 ~10–30 ms 建表 |

> 这条对 R2 的定位也有影响：**不要**为了"补国密"而引入 gmssl —— 它本身有正确性缺陷。
> 现有实现已经过国标向量与互通双重验证，保持在自研实现上更稳妥。

#### §P3-0b 用户侧密钥文件（已完成）

**问题**：用户要解开信封就必须持有该密钥自己的 `d_a`，而它此前只存在于「生成后的弹窗」里，
靠用户手抄；服务端只有 KGC 分片。存量那批密钥正是因为这一点才全部失效（§8.1.3）。

**实现**：
- `kms-user/front/src/utils/key-file.js` —— 文件格式与校验：
  `{version, kind, key_id, user_id, algorithm, created_at, private_share, public_key, checksum}`。
  校验和是 SHA-256，覆盖**规范化**后的字段（固定顺序、紧凑 JSON），
  因此字段顺序/缩进/日后新增无关字段都不会让旧文件失效。
  比用户给的最小字段集多了一个 `public_key`（= `P_A`，**不是秘密**）——
  导入时用它核对"这份私钥确实对应记录里那把公钥"，避免导错文件后静默用错密钥。
- `kms-user/front/src/store/modules/keyring.js` —— 本机密钥环（localStorage，按 `key_id` 索引）。
  同一 `key_id` 但私钥不同时**拒绝自动覆盖**并报错：悄悄覆盖会让"为什么解不开"变成一个查不出来的问题。
- `kms-user/front/src/components/KeyFileImport/index.vue` —— 导入界面（选文件 / 粘贴内容两条路）。
- `GenerateView.vue` —— 生成结果弹窗新增「下载密钥文件」，导出后同时写入本机密钥环
  （下载是持久凭据，密钥环让当前浏览器立刻可用）。

**安全边界（已写进代码注释）**：校验和是**完整性**校验而非真实性证明（无秘密参与，
任何人都能重算）；`private_share` 目前明文存放，后续增强才用口令派生密钥加密；
**这些内容绝不发给服务端**（R1' 红线，有回归用例守着）。

**验证**：

| 测试 | 结果 |
|---|---|
| `tools/verify-key-file.mjs`（格式与校验逻辑） | **22 / 22**：篡改 private_share / key_id / user_id 全部被校验和拦下；缺校验和、截断 JSON、kind/version 不对、字段格式非法一律拒绝；字段乱序与多余字段仍能通过（证明规范化生效） |
| `tools/verify-key-file-ui.mjs`（真实浏览器） | **8 / 8**：合规文件导入成功并写入 localStorage；**被篡改文件明确报错且密钥环未被污染**；刷新页面后仍在，界面显示「已导入 N 把」 |

> 之所以要两条：前者测纯函数，后者测"接到界面上之后还成立"——
> 历史上已经吃过一次亏（`verify-keyvalue-redaction.mjs` 曾因字段命名不同而全部假通过）。

> D10 已定：**节点腿零改动**，本阶段只新增"用户腿"。现有 `generate_kyber_pool` /
> `generate_falcon_pool` 保持行为不变，仅将其分支收敛进 §3.1 的 `WRAPPERS` 注册表。

0. **（新增，P0-B 结论驱动）先固定用户腿的加密目标点。**
   目标必须是 `P_A = W_A + λ·P_pub`，**不是** `finalPublicKey`（§3.2.3 的 ⚠️ 一节 / R16）。
   复用 `UpdatedelChainService.java:354` 已有的算式，不要另写一份推导。
   先写两条单测再写业务代码：
   - 断言加密目标 == `W_A + λ·P_pub`；
   - 断言"用 `W_A` 直接加密"这条路径**不能被当成可用实现**（用户解不开）。
   同时补 **R1' 的回归用例**：出站请求体不得出现浏览器本地份额 `u` / `privateKey`。

0b. **（新增，用户明确要求）把用户侧密钥的保存与恢复机制补完整。**
   P3 不能只解决"测试能跑通"，必须正面解决一个事实：**用户要能解开信封，
   就必须持有该密钥自己的 `d_A`**。而现有 UX 只是弹窗让你自己复制 —— 不可靠，
   也导致存量那批密钥的用户侧份额事实上丢失（见 §8.1.3）。

   第一版流程（用户给定）：

   ```
   生成用户密钥
       ↓
   生成 d_a
       ↓
   浏览器生成密钥文件
       ↓
   用户下载并自行保存
       ↓
   服务器只保存服务器侧份额与公开信息
       ↓
   解密时重新导入用户密钥文件
   ```

   密钥文件格式（带校验和，防止手改/截断后静默用错）：

   ```json
   {
     "version": 1,
     "key_id": "...",
     "user_id": "...",
     "created_at": "...",
     "private_share": "...",
     "checksum": "..."
   }
   ```

   后续增强（不在第一版）：把 `private_share` 用**用户口令派生的密钥**加密，
   而不是直接明文保存。

   验收要点：
   - 导出 → 刷新页面 → 导入 → 能用该密钥解开信封（完整往返）；
   - 校验和不匹配时必须**明确报错**，不允许"尽力而为"地用错密钥；
   - 服务端**任何接口都不得接收或落库 `private_share`**（与 R1' 同一条红线）；
   - 与 `key_material_state` 联动：导入了密钥文件的记录才应显示为可用于解密。
1. 建 §4.2/4.3/4.4 三张表 + 迁移
2. **抽出 `WRAPPERS` 注册表**，把现有 Kyber/Falcon 两分支改为查表（纯重构，行为不变，先跑通回归）
3. **补密码学底座（R2'）**：容器内不存在 SM2 实现，必须先加
   `gmssl-python`（需重建 Django 镜像）或在现有手写点运算层上自实现 SM3 + ECIES。
   工期 SM2 = M（2–4 天）、SSCL = S（0.5–1 天）
4. 新增 `Sm2Wrapper` / `SsclWrapper`（§1.3 的最大新增项；建议先只做 SM2 打通，SSCL 紧随）
   - SM2 的加密目标已在第 0 步固定为 `P_A`
   - SSCL 的封装目标点**已可从存量数据推导**：`P_A = u_A + (e_A·m mod n)·G`
     （P0-C 实测 4/4 为合法曲线点），缺的只是密码器本身
5. **落实 D17 收窄**（§3.2.4）：分发接口服务端校验 `source_key_id` 属 SM2/SSCL（**不只前端过滤**）+ 前端下拉只列这两类 + 旁附说明
6. 节点管理新增「默认封装算法」字段（默认 `kyber`，D16）
7. 主 KMS 暴露 §5.2 的用户公钥接口（服务令牌鉴权）；**返回的必须是 `P_A`**
   （§3.2.3 结论 4 已由 P0-B 修正；`ua` 与 `finalPublicKey` 都不是加密目标）
8. 实现 §5.1 四个用户侧接口（`user_id` 只取令牌）
9. 用户侧「分发」页重做 + 「对称密钥查看」页新增
10. 管理端「节点鉴权配置」页

**验证**：
- 1 用户 + 2 节点端到端 → 产生 **3 份信封**，逐份解封得到**同一把 SM4 密钥**（比对 `key_hash`）
- 节点腿回归：改造前后 `generate_kyber_pool` / `generate_falcon_pool` 产出的密文可互相解封（证明重构未改行为）
- **D17 负向用例**：直接构造请求用 CL-Kyber / CL-Falcon 的 `key_id` 调分发接口 → **必须 400**（证明服务端而非前端在拦）
- **加密目标负向用例（R16）**：用 `W_A` 作为加密目标生成的信封 → 用户**必须解不开**（证明第 0 步的单测确实在守）
- **`u` 不外泄（R1'）**：抓取分发全流程的所有出站请求体，断言不含客户端本地份额
- **节点越权用例**：分发到自己未被授权的节点 → 必须 403；超过 10 个节点 → 必须 400
- 越权用例：用 A 的令牌读 B 的对称密钥 → 必须 403；不带令牌 → 401

### P4 · 管理端菜单聚合 · 🔄 进行中

**进度**

| 项 | 状态 |
|---|---|
| 1 菜单模型加「分发与区块链」「测试」两组 | **✅ 菜单已建**（`26_aggregate_admin_menus.sql`），**实测侧边栏 30 项，含全部分发/测试条目** |
| 2 区块链管理／节点管理用 `InnerLink` 嵌入 pqkds | **🔄 未打通** —— 见下 |
| 3 测试页面嵌入 `/acceptance/#/...` | **🔄 同上** |
| 4 统一登录态传递 + 关闭 pqkds 自带登录入口 | 待做（**安全项，不可省**） |
| 5 `/updatedel/` → `/admin/` | 待定（计划原文即"视情况"） |

**已完成**：`26_aggregate_admin_menus.sql` 建了两个目录 + 四个外链条目
（分发控制台 / 区块链浏览器 / 节点管理 / 验收测试台），并按既有约定
（`is_frame=1` + `component='InnerLink'` + `path` 写完整 URL）配置，含角色映射。

**验证**：侧边栏实测 **30 项**，`分发控制台 | 区块链浏览器 | 节点管理 | 验收测试台` 全部出现。
**点击「分发控制台」→ `iframe=1`、`src=/distribute/`** —— 嵌入真的生效了。
管理端巡检 **32 / 32 通过**。

#### ★ 内嵌机制：`InnerLink` 为什么不行，以及怎么修的

**根因（精确定位）**：RuoYi 的 `InnerLink` 走后端 `MetaVo` 的 4 参构造，而那里有一句
```java
if (StringUtils.ishttp(link)) { this.link = link; }
```
—— **只有 http(s) 绝对地址**才会被写进 `meta.link`。
而 `isInnerLink(menu)` 同样要求 `isFrame == "0"` **且** path 是 http 地址。

我们要嵌的是**同源路径**（`/distribute/`、`/acceptance/`），于是 `meta.link` 恒为 `null`，
前端不渲染 iframe → 白屏。**`InnerLink` 是给"外链"用的，不是给"同源子应用"用的**；
硬要用它就得把 `http://<主机>/distribute/` 写死进菜单，换个访问域名就废。

**修法**：新增本地组件 `views/frame/index.vue`，从 `route.query.url` 取目标地址渲染 iframe。
菜单改成 `component='frame/index'`、`path` 为路由片段、`query` 带目标地址、`is_frame='0'`。

**登录态怎么传**：同源 iframe **共享 Cookie**，主 KMS 的令牌就在 `Admin-Token` 里，
被嵌页面发出的同源请求天然带着它 —— **不需要在 URL 里塞令牌**
（塞进 URL 会被网关日志、浏览器历史、Referer 记录下来，是更差的做法）。
组件里同时限制只接受以 `/` 开头的同源路径，避免它退化成开放的 iframe 容器。

> **两个坑，都是"看起来像功能坏了、其实是调用方式不对"**
> 1. **菜单的 `query` 字段要写 JSON**（`{"url":"/distribute/"}`），不是查询串（`url=/distribute/`）。
> 2. **`query` 只在"从侧边栏点进去"时才生效** —— 直接敲 URL 打开，`route.query` 是空的。
>    我一开始就是直接导航去测的，看到"内容区 34 字符、无 iframe"，
>    而 34 字符恰好是组件里那句"该菜单没有配置要嵌入的地址"的提示 ——
>    **页面其实在正常工作，只是我没从菜单点进去**。

> ⚠️ **一个关于我自己的断言的保留**：内容量阈值取的是 20 字符，
> 而上面那句"未配置地址"的告警有 34 字符 —— 也就是说
> **一个配错地址的 frame 页仍能通过"内容区非空"检查**。
> 所以"巡检 32/32"**不能**证明 iframe 渲染正确；
> 这一条的决定性证据是上面那次点击测试（`iframe=1`）。阈值应调高或改为"必须存在 iframe"。

**未做**：`is_frame`/`query` 的写法已记在上面的迁移文件里；
`/updatedel/` → `/admin/`（计划原文即"视情况"）未动。

#### ★ 已关闭 pqkds 自带登录入口（P4 第 4 项的前半，安全项）

实测确认 `/pqkds-api/api/login/` 与 `/pqkds-api/api/token/` **都是活的**
（返回"账号/密码错误"而非 404），可用账号口令换取**分发模块自己的 JWT**。

而它认的是 `dvadmin_system_users` —— 与主 KMS 的 `kms.sys_user` **是两张不同的表**。
所以这不只是"第二个入口"，而是**一整套并行的身份体系**：
谁能登录、谁是管理员，在那边完全另说。D7 要把这张表降级为"节点侧附属信息"、
D9 要求"只有一个登录入口"—— 只要这两个端点还在，两条都被绕过。

已在 nginx 精确匹配返回 **403**。**验证**：

| 检查 | 结果 |
|---|---|
| `/pqkds-api/api/login/` | **403** |
| `/pqkds-api/api/token/` | **403** |
| `/pqkds-api/admin/users/`（走主 KMS 令牌） | 200，6 条 |
| `/pqkds-api/admin/node-authorizations/` | 200，2 条 |
| `/pqkds-api/user-symmetric-keys/` | 200，19 条 |

即：**关掉了并行身份入口，且没有影响任何走主 KMS 令牌的接口**。

> 另外两个登录端点（`apiLogin/`、`token/refresh/`）经探测是 **404** ——
> nginx 的路径映射到不了它们。所以不是"防了一个本来不存在的东西"，
> 但也确实只需要关这两个。

#### ★ 补上管理端的内容量断言

`verify-admin-pages.mjs` 现在对**没有登记标志性文案**的路由（管理端菜单是后端动态下发的，
没法逐页手工登记）量 **`.app-main` 内容区**的文本量，低于 20 字符即判"白屏"。

关键取舍：量的是**内容区**而**不是** `document.body` ——
后者含侧边栏与顶栏，即使内容区整个白屏也有一大段导航文字，那样的检查等于没做。

**这条断言上线后立刻抓到 4 个此前一直报 ok 的空白页**（就是上面那 4 个）。
用户前台 9/9 仍全绿（那边是标志性文案断言）。

**下一步**：确认 `meta.link` 的生成位置（前端 `filterAsyncRouter` 或后端菜单服务），
或改用"新建本地组件包一个 iframe"绕开该机制；之后再做 iframe 的登录态传递。

**未打通的部分（如实记录）**：点击「分发控制台」后地址变为
`/updatedel/distchain/distribute`、**iframe 数为 0** —— 说明该 URL 被当成**相对子路由**处理，
而不是外部链接。`InnerLink` 机制要求路由带 `meta.link`，
而当前后端返回里没有把 `path` 映射成 `meta.link`，所以前端只把它当作普通子路径。

> **顺带排掉的一个坑**：把目录行的 `is_frame` 改成 `0` 会让**整个侧边栏渲染为空** ——
> 目录行不是链接，但这个应用的路由构建对它有依赖。目录行必须保持 `is_frame=1`。

**下一步**：确认 `meta.link` 的生成位置（前端 `filterAsyncRouter` 或后端菜单服务），
或改用「新建一个真正的本地组件包一个 iframe」的方式绕开该机制；
之后再做第 4 项（iframe 令牌传递 + 关闭 pqkds 登录入口）。

> **第 4 项不能省**：`/distribute/` 自带一套独立登录。只要它仍可被外部直接访问，
> 就存在"绕过主 KMS 的登录与角色判定"的入口 —— 那与 D9 的分流设计直接冲突。
> 若 iframe 嵌入一时做不通，**至少要先把它对外关掉**（比聚合更优先）。

### P5 · 收敛与清理 · 🔄 进行中（第 1 步已完成）

> 顺序很重要：**先迁移消费方，再删除**，否则工作台图表与密钥关联分析会立刻报错。

| 步骤 | 状态 |
|---|---|
| 1 **迁移三个消费方** | **✅ 已完成并验证**（见下） |
| 2 执行删除清单 | **✅ 已完成并验证**（见下 §P5-2） |
| 3 按 Q11 决定是否下线 `kms-distribute` Java 服务（8083） | **✅ 门户已收口**（不再发布任何端口）；**整机是否下线仍待 Q11 定夺** |
| 4 `dvadmin_system_users` 独立登录入口下线（D7） | **✅ 已完成**（见 §P4：两个登录端点已 403） |
| 5 `legacy-kms/` 中引用 `key_distribute_record` 的残留查询清理 | **✅ 已完成** |
| 6 下线遗留的 `/generate/` 应用 | ✅ 已完成（先前插队项） |
| 7 重新打包 `kms-ops/dist` | **🔄 执行中**（后台 `ship.ps1`） |

#### §P5-2 删除清单执行结果

| 类别 | 实际动作 |
|---|---|
| Java 代码 | **删 17 个文件**（14 个 `.java` + 2 个 Mapper XML + 1 个 Kafka 消费者）—— 与计划清单逐项核对过 |
| Kafka | `DistributeKafkaConsumer.java` 已删；**四个 topic 未动**（它们是主 KMS 命脉） |
| 网关 | `location /distribute-api/` 改为**显式 `return 404`**；`upstream distribute_java_backend` 已移除 |
| 前端 | `services/distribute-api.js` 删除；`apiBases.distributeApi` 删除；vite 代理 `/distribute-api` 删除并改为 `/pqkds-api` |
| 数据库 | `kms.key_distribute_record` **已 DROP**（删前把 77 条记录 `mysqldump \| gzip` 归档到容器 `/tmp`）；两个建表 SQL 删除 |
| 其他 | `legacy-kms` 的 `keymanageServiceImpl` 同源查询**已迁移**（与 updatedel 那份一致），不是留着指向已删表 |

**验证**（实测）：

| 检查 | 结果 |
|---|---|
| `/distribute-api/distribute/record/list` | **404**，且**不含门户 HTML**（`<div id="app">` 为 false） |
| `/distribute-api/anything` | **404** |
| 新链路 `/pqkds-api/distribution-batches/` | **200，11 条** |
| 前端冒烟（4 端） | 全部通过 |
| 工作台 | KPI 4 张 / 图表 5 张 |
| 用户前台巡检 | 9 / 9 |
| `check.ps1` | All checks passed |
| Java 残留引用 | **0 处**（删完即扫，无编译失败风险） |

> **★ 显式 404 而不是"留空"**：留空会落到默认 location 的 `try_files`，
> 于是 `/distribute-api/anything` 会**返回 200 的门户首页 HTML** ——
> 调用方拿到 200 会以为接口还在，只是数据不对。
> 这个坑在 `/generate/` 退役时踩过一次，这次直接按同样的方式处理。

> **两个连带修掉的地方**（不修就会变成"全新库上跑不通的迁移脚本"）：
> ① `24_reset_legacy_key_data.sql` 里还在 `SELECT ... FROM key_distribute_record`，
> 表删掉后该脚本在全新库上会直接报"表不存在"；
> ② `check.ps1` 原来检查的就是这张表 —— 已改为检查三张新表
> （并给 `Test-MySqlTable` 加了 `-Database` 参数，因为它原先写死 `-D kms`）。

> **⚠️ 一个仍未处理、且值得优先处理的点**：`kms_distribute_java` 容器
> **仍在运行，并以 `0.0.0.0:8083` 对外发布**。它现在已经没有任何消费方
> （路由已删、Java 代码已删），却还占着一个对外端口。
> 这与先前把 mysql/kafka/redis 收到 `127.0.0.1` 是同一条原则：
> **没有消费方的服务不该继续对外可达**。Q11 无论怎么定，这一步都该做。

#### §P5-3 旧分发服务端口收口（已完成）

上面那条已处理。取舍是**收口端口、暂留容器** —— 这样既不把"没有消费方的服务"
继续暴露在网络上，也不替 Q11（是否整机下线）做决定。

- `docker-compose.yml` 移除 `ports: ["8083:8083"]`，并写了说明；
  容器间仍可用服务名 `kms-distribute:8083` 访问，**宿主机与外部网络不再可达**
- `check.ps1` 新增 `Test-NoPublishedPort` 断言 —— 比 `Test-LoopbackOnly` 更强：
  后者只管"有没有绑到非回环"，而这里期望**根本没有端口映射**。
  用独立断言表达，免得日后有人"顺手"把它发布回来

**验证**：`docker port kms_distribute_java` 输出为空；从宿主访问 `/` 与 `/actuator/health`
均**连接失败**；容器仍在运行（Q11 未预判）；`check.ps1` 输出
`[OK] kms_distribute_java 未发布任何端口` 且 All checks passed。

> **Q11 待你定夺**：是否连容器一起下线。收益是部署镜像 **8 → 7**、
> 少一个 JVM 容器与一次 `docker save`。我**没有**替你做这个决定，
> 因为它会改动交付物清单（`ship.ps1` / compose / 镜像数量），
> 属于"影响外部约定"的变更，不适合由我单方面拍板。

#### §P5-Q11 旧分发服务整体下线（已完成）

**分两步做的**，这个顺序是有意的：

1. **先收口端口**（Q11 未定时就做了）—— 让一个"没有消费方"的服务先变得不可达；
2. **再整体下线**（你确认后）—— 删 service、镜像与构建入口。

把两件事分开，是为了避免"要不要留着它"这个决定，把"它还在对外暴露"这件更要紧的事
一起拖住。

**改动清单**：

| 位置 | 动作 |
|---|---|
| `docker-compose.yml` | 删除整个 `kms-distribute` service（含 ports / environment / depends_on） |
| `ship.ps1` | 镜像清单去掉一项；`8 个应用镜像` → `7 个`（两处硬编码文案同步） |
| `deploy.sh` | 镜像清单去掉一项 |
| `start.sh` | 去掉 `runtime/distribute-java` 目录、jar 存在性检查、服务启动项 |
| `build-local.ps1` / `.sh` | 去掉旧服务的 Maven 构建与 jar 拷贝 |
| `build/distribute-java.Dockerfile` | **删除** |
| `runtime/distribute-java/` | **删除** |
| `check.ps1` | 去掉 `Test-NoPublishedPort -Container kms_distribute_java`（容器已不存在）；**保留函数本身** |
| 容器与镜像 | `docker stop` + `rm` + `rmi kms-distribute-java:local` |

**⚠️ 刻意保留的**：`kms-distribute/extracted/ruoyi (2)/web`（即 `/distribute/` 前端）
与它的构建步骤 —— **管理端「分发与区块链」那 4 个菜单正以 iframe 内嵌它**，
一起删会让那 4 个菜单白屏。`build-local.ps1` / `.sh` 里都留了注释说明这一点。

**验证**：

| 检查 | 结果 |
|---|---|
| `docker compose config --quiet` | exit 0（配置合法） |
| 应用镜像数 | **7**（原 8），且清单里不再有 `kms-distribute-java` |
| 容器 | 12 个，`kms_distribute_java` 已消失 |
| `check.ps1` | All checks passed（三条回环断言仍在） |
| 前端冒烟 / 巡检 | 4 端通过 / 管理端 **32/32**、用户前台 **9/9** |
| 工作台 | KPI 4 / 图表 5 |
| `/distribute-api/` | **404** |
| 新链路 | 200，13 条 |

> ⚠️ **注意 `ship.ps1` 里的 `8 个应用镜像` 是硬编码文案**（两处）。
> 只改 `$images` 数组而漏掉文案，产物说明与实际就不一致了 —— 这类"数字写在两个地方"
> 的地方在删服务时最容易漏。

#### ★ 顺带修掉一个真实的用户可见缺陷：内嵌页刷新即失效

写 iframe 断言时发现：内嵌页的目标地址原本**只来自菜单的 `query`**，
而 `query` **只在"从侧边栏点进去"时才出现在 URL 上**。
于是**直接敲地址、点书签、或按 F5 刷新**时 `route.query.url` 是空的，
页面会显示"该菜单没有配置要嵌入的地址"，内嵌内容整个消失。

**"刷新后页面变了样"属于很难被当成 bug 报上来的故障**，但它确实是个缺陷。
已在 `views/frame/index.vue` 里按路由末段加了兜底映射（`query` 仍优先），
**刷新与书签现在都能正常显示**。

> 这个缺陷是**新断言逼出来的**：断言一上线就报 4 个失败，
> 我一度以为是断言写错了 —— 查下去才发现是页面真的在那种进入方式下坏了。

#### §P5-1 三个消费方迁移（已完成）

**顺序是对的**：先迁移，再删。旧表 `kms.key_distribute_record` 同时是这三个地方的数据源，
先删就会立刻炸 —— 而计划 §3.6.5 把"工作台 5 张图表均有数据"列为**硬性约束**。

| 消费方 | 改动 | 验证 |
|---|---|---|
| ① 用户工作台「分发状态分布」 | `WorkbenchView.loadDistribute()` 改调 `listDistributionBatches`（批次表） | **实测「共 11 条」、KPI「分发记录 11」、「分发成功 8 条」** |
| ② 管理端「密钥关联分析」分发足迹 | `LifecycleService.getAssociationAnalysis()` 改查 `falcon_kds.dvadmin_pqkds_distribution_batches`（按 `source_key_id` 关联，LEFT JOIN `sys_user` 取用户名） | **实测 5 把密钥各返回 1 条足迹**，字段名与旧版一致 |
| ③ 健康检查 | `check.ps1` 改查三张新表 | **实测 7 张表全部 OK，All checks passed** |

**★ 一个不是"换个接口"就完事的地方**：新批次表的状态是**字符串**
（`success` / `partial` / `pending` / `failed`），而工作台那张图的
`DISTRIBUTE_STATUS_META` 按**数字码**（`2/1/0/3`）分组。直接换接口的话
`groupCount` 一个都匹配不上 —— **图会"成功渲染但永远为空"**，
这种失败比报错更难发现（它看起来就像"最近没有分发"）。
因此在数据加载层做了映射，图表代码一行未动。

**★ 另一个坑**：`check.ps1` 的 `Test-MySqlTable` 原本**写死 `-D kms`**，
而新表在 `falcon_kds`。直接换表名会得到"表不存在"——**表其实好好的，只是查错了库**。
已给该函数加上 `-Database` 参数（默认 `kms`）。

**同时保持了向后兼容**：分发足迹的字段名沿用旧的
（`distribute_time` / `user_name` / `distribute_type` / `distribute_status`），
因此 DTO 与前端都不用改 —— 消费方迁移应当对上层透明。
5. `legacy-kms/` 中引用 `key_distribute_record` 的残留查询一并清理
6. ✅ **已完成：下线遗留的 `/generate/` 应用**（`kms-generate/front`）：P1 曾把它修成"不坏"，但它与统一管理端
   高度重复。已移除 nginx `location /generate/`（网关现对 `/generate/` 显式返回 **404**，否则会回落到
   默认 location 的 `try_files` 变成 200 的门户首页）、已从 `build-local.ps1` / `build-local.sh`
   与 `build/nginx.Dockerfile` 中去掉（含 `start.sh` 里对 `front/generate/index.html` 的启动前置）、
   已同步 `check.ps1` / `tools/smoke-frontends.mjs` / `tools/verify-admin-pages.mjs`
   （后者的 generate 模式整体删除）；`ship.ps1` 本就不打包 `front/`（前端在网关镜像内），
   其镜像清单里的 generate **后端**镜像照旧保留。
   **未动**：`/generate-api/` 路由与 `generate-java` / `generate-go` 服务（统一管理端仍要调用）。
   源码目录保留，并新增退役说明 `kms-generate/front/RETIRED.md`。
   前端交付物 **5 端 → 4 端**；`tools/smoke-frontends.mjs` 已按 4 端重跑通过（见 R8）
7. 重新打包 `kms-ops/dist`（`ship.ps1`）。前端改动只影响网关镜像，用增量包 `kms-nginx-update.tar` 即可

**验证**：`check.ps1` 全绿；**用户工作台 KPI 仍为 4 张、图表仍为 5 张且均有数据**（§3.6.5 硬性约束）；密钥关联分析仍有分发足迹；`tools/smoke-frontends.mjs` 通过（注意 `distribute` 与 `/generate/` 的路由调整后需重跑）。

> **前端交付物数量：5 端 → 4 端**（P5 第 6 项的验收口径）。退役后对外提供的只剩
> `/updatedel/`、`/distribute/`、`/user/`、`/acceptance/` 四端（`/lifecycle/` 是 `/updatedel/` 的
> 301 跳转，不计入）。实测：四端均 `200`，`/generate/` 返回 `404`（已退役），
> `/generate-api/generate/ping` 仍为 `200`（证明只下线了前端、没有误伤 generate 后端路由）。

---

## 8. 风险清单

| # | 风险 | 等级 | 应对 |
|---|---|---|---|
| R1 | ~~主 KMS 生成的 4 种公钥与分发模块 KGC 参数**可能不兼容**~~ → **P0-C 已判定"不成立"**：主 KMS 根本不生成格密钥（Go 侧回调 pqkds 只存元数据；Java 侧对非 SM2/SSCL 直接拒绝），运行库 CL-Kyber/CL-Falcon 行数为 0，比较对象不存在 | **已关闭** | 无需应对。真正的阻塞项改记为 R2' |
| R2' | ~~运行时完全没有 SM2 实现~~ → **✅ 已修复**：`cryptography` 自带 `hashes.SM3`（通过 GB/T 32905-2016 向量），EC 运算以纯 Python 补齐（`pqkds/sm2_crypto.py`），**未新增任何依赖、未重建镜像** | **高 → 已关闭** | 32/32 测试，含**真实公开国标向量逐字节匹配**与 **gmssl 双向互通 200/200**。⚠️ 副产物：发现 gmssl 自身有正确性缺陷（约 1/12 次返回不在曲线上的点），**故不要改用它** —— 见 §P3-R2' |
| R2 | SM2/SSCL 封装在分发侧为零实现 | 高 | 见 R2'；**先只做 SM2 打通，SSCL 紧随** |
| R12 | `kms.keymanage.key_value` 是 `varchar(1024)`，而 CL-Falcon/CL-Kyber 记录有 3,119–3,534 字符 → 生效的 `STRICT_TRANS_TABLES` 下 **ERROR 1406**；Falcon 公钥 17,050,904 字符（超限 16,651 倍）；Kyber-512 KEM 公钥 base64 1,068 字符 | 中（当前无 PQ 密钥生成路径，故尚未触发） | PQ 密钥不写 `key_value`；改存 `dvadmin_pqkds_nodes.{kyber,falcon}_public_key`（本就是 `longtext`），`key_value` 只留 `node:<id>:<field>` 引用 |
| R13 | `pqkds` 格 KGC 的安全性未评估，且两处可疑：`D_id` 由 `sha256(user_id)` 确定性派生（部分私钥可被任何知道 user_id 的人算出）；`kgc_keys = {'sk_KGC': A}` 把主密钥设为**公开**矩阵 | **高（新发现，需单独评审）** | P0-C 只验证了功能往返，**绿色往返不等于安全**。节点腿算法在上线前应单独做一次密码学评审；在此之前不要把格方案的"抗量子"当作已证性质对外表述 |
| R14 | `FalconCrypto` 是死代码：`FALCON_512_DLL` 常量漏了 `falcon512/` 子目录（该文件其实是改名 `.dll` 的 ELF，在 Linux 上按正确路径可加载）；Falcon-1024 的 ELF 缺失 | 低 | 两行修正常量的路径；Falcon-1024 需要补齐二进制或明确不支持 |
| R15 | 节点密钥池**已全部过期约 137 天且从未被消费**（`key_pool_local_storage` 的两池均为 `kyber_kem`，50 把）；库中与磁盘上都不存在 Falcon 池 | 中 | P3 联调前先重新生成池；Falcon 节点腿目前只有合成验证 |
| R3 | 双库双身份，`user_id` 语义易错 | 高 | 统一以 `kms.sys_user.user_id` 为准；新增表全部逻辑引用；接口 `user_id` 只取令牌 |
| R4 | 对称密钥是**密钥材料**，越权即等于泄露 | **高** | §5.1 强制令牌取用户；管理端查看对称密钥**不放开**（Q7） |
| R5 | 管理端 iframe 嵌入导致登录态与样式割裂 | 中 | 优先生死线：菜单可打开；样式统一放到 P4 之后单独一轮 |
| R6 | SM4 替换破坏历史密钥池可用性 | 中 | 保留 `payload_algorithm`，新旧并存读取；先在测试库演练。**另有降险结论**：容器内 `cryptography 50.0.1` 自带 SM4 且通过 GB/T 32907-2016 两个标准向量，P2 无需新增依赖；`algorithms.SM4` 只接受 16 字节，漏改处会立刻抛错而非静默降级（见 §7 P2 前置结论） |
| R7 | `role_level` 收成 2 级需迁移存量 1 级账号，并改若干比较点 | 低 | **实测存量为 0**：库中只有 0 与 2（6 个账号），迁移为纯防御性语句。但比较点比原计划列出的 7 处更多，已按实际逐处改完（见 §3.4 补充） |
| R9 | ~~Q7 可能名不副实~~ → **已证实**：CL-Kyber / CL-Falcon 私钥明文落库，服务端必能解密 | **已定位** | 已由 **D17** 收窄用户腿为 SM2/SSCL 处置（§3.2.4） |
| R10 | 收窄后**用户信封的机密性完全押在 SM2/SSCL 上**；若服务端连这两类也能解开，则已无算法可提供真实机密性 | **高** | **P0-B 是唯一支柱**；静态分析（服务端只有 `t_A`、`w` 不出浏览器）指向"解不开"，但须由 P0-B 用可执行证据固定 |
| R11 | 仅靠前端过滤可选算法，直接构造请求即可绕过 | 中 | §3.2.4 要求服务端强制校验；P3 已列**负向用例**验证 |
| R1' | **`u` 一旦出客户端，Q7 立即失效**（P0-B 的否定结论唯一支点） | **高** | 加断言式回归用例：扫描所有出站请求体，断言不含浏览器本地份额 `u` / `privateKey`；代码评审清单固化 |
| R16 | **加密目标点**：本计划原文写"用 `finalPublicKey`"是**错的** —— `W_A` 没有对应私钥，加密到它等于做出"谁都打不开"的信封（连用户自己也不行）。正确目标是 `P_A = W_A + λ·P_pub` | **高（已定位并修正 §3.2.3）** | P3 第一步：复用 `UpdatedelChainService.java:354` 的现成计算；加单测断言"加密目标 == `W_A + λ·P_pub`"，且"用 `W_A` 加密后用户能解开"必须是**失败**用例 |
| R17 | **`ms` 是硬编码公开默认值且为线上生效值**（`KGC_MASTER_SECRET` 全容器为空），并可**从单个只读 API 调用反推**（`PARTIAL_KEY` + `key_use=演示计算` 回吐 `kgcRandomW`/`kgcLambda`）→ KGC 完全攻破：可为任意身份伪造部分私钥 | **高 → ✅ 已修复** | ① Java 与 Go 两侧**去掉静默回退**：未配置/为空/等于演示值一律**拒绝启动**（实测 Go panic、Java 在 Bean 创建阶段抛 `IllegalStateException`）；② `kms-ops/.env` 轮换为真实随机值（gitignored）；③ **查出更深的根因**：真正生成部分私钥的 `generate-go` **在 compose 里从未被注入**该变量（已补齐）；④ `updatedel-go` 反向收回（它根本不读该值，最小权限）；⑤ 删除 `演示计算`/`前置构建` 的 `kgcRandomW`/`kgcLambda`/`kgcMx` 回吐；⑥ `check.ps1` 增加"已配置 + 非演示值 + 格式合法"断言。**轮换代价见下方专节** |
| R18 | **`key_value` 明文外泄面**：列表/详情接口原样返回 `key_value`；Kafka 明文携带；`legacy-kms` 写入 KGC 中间量；AES 行的 `key_value` 就是明文对称密钥；MySQL 3307 可直接连 | **高 → ✅ 已修复** | ① 新增 `KeyValueSanitizer`（两个模块各一份）：**列表一律不带材料**、详情按"属主 + SM2/SSCL"决定、其余降级为显式 `{"redacted":true,…}` 信封；覆盖 7 个接口；② **`/analysis/{keyId}` 曾是绕过列表脱敏的后门**（DTO 内嵌整条 Keymanage），已一并处理；③ Kafka 载荷移除**明文口令** `raw_password`（消费端本就忽略它）；④ 9092/3307/6379 **收到回环**（`check.ps1` 增加断言）；⑤ 删除明文对称密钥那行（`22_*.sql`）+ D12 代码分支。验证：`tools/verify-keyvalue-redaction.mjs` **13/13** |
| R19 | SSCL 已发布的公共份额**每次进程启动重新生成且不持久化** → 库中 SSCL 行与 `/comparam` 不一致 | **中 → ✅ 已修复（且发现的问题更大）** | 根因不止"不抗重启"：**三份 SSCL 实现各自随机一条多项式**，而 `/comparam` 只由 Go 提供 → Java 生成的材料与发布的点**不共线**，客户端插值必然得到垃圾（即生命周期更新出来的 SSCL 密钥本来就不可用）。现三份统一改为**从 `ms` 确定性派生**（SM3 + 固定 label，逐字节等价）；Go 侧新增确定性/标签钉死/客户端插值/KAT 四类测试，并完成**跨语言等价验证**（Go vs Java vs 独立第三方实现，33 个数值 0 差异）。实测：重启后 `/comparam` 逐字节不变；Java 生成的 `SSCLEA` 能被浏览器插值算法精确还原（`tools/verify-sscl-params.mjs` **7/7**） |
| R20 | 密钥里多行共用同一个 `ua` → 一个会话的 `u` 在保护多把密钥 | **中 → 部分修复** | ① 演示数据集已重新登记，**8 把密钥 8 个互不相同的 `ua`**（`kms-ops/tests/seed-demo-keys.mjs` 内实现了 sm2p256v1 标量乘以生成各自独立的本地份额）；② 但"浏览器端每次刷新重新生成 `u`"这个根因仍在前端流程里，由 **P3 的密钥文件机制（§7 P3 步骤 0b）** 一并解决 —— 用户导出/导入自己的 `d_a` 之后，`ua` 与 `u` 才真正一一对应且可长期持有 |
| R8 | `/updatedel/` 改名 `/admin/` 牵动 nginx/vite/缓存 | 低 | 单独一次改动，改后重跑 `tools/smoke-frontends.mjs` |

---

### 8.1 `ms` 版本化：轮换不再破坏历史可审计性

**旧结论已作废。** 本节原先写的是"轮换 `ms` 会作废历史 `P_A`，需重新登记"，
现在改为**版本化密钥集**，轮换只影响"新记录用哪把密钥"，不再破坏历史。

#### 8.1.1 配置形态

| 环境变量 | 含义 |
|---|---|
| `KGC_MASTER_SECRET` | 当前**启用**的密钥（新记录一律用它签发） |
| `KGC_MASTER_SECRET_ID` | 启用版本的版本号，如 `ms_v2` |
| `KGC_MASTER_SECRET_RETIRED` | 已退役但**必须保留**的密钥，JSON 映射 `{"ms_v1":"<hex>"}` |

轮换步骤：把当前密钥追加进 `RETIRED`，再换 `KGC_MASTER_SECRET` 并递增 `_ID`。
退役密钥**只用于历史复算** —— `getActive()` 不会返回它，因此不可能被用来签发新记录。

#### 8.1.2 记录侧的三个版本字段（`kms.keymanage`）

| 字段 | 取值 | 作用 |
|---|---|---|
| `ms_key_id` | `ms_v1` / `ms_v2` | 由哪一版 `ms` 签发；**复算 `P_A` 时按它取密钥** |
| `algorithm_version` | `v0_random_sscl_domain` / `v1_derived_sscl_domain` | 算法参数版本。与 `ms_key_id` 正交：同一把 `ms` 下算法实现也可能换代 |
| `key_material_state` | `active` / `legacy_unusable` | 材料是否仍**可用于解密** |

`UpdatedelChainService` 与 `GenerateChainServiceImpl` 复算 `P_A` 时都改为
`KgcMasterSecret.getById(record.msKeyId)`；`ms_key_id` 为空按 `ms_v1` 处理
（早期记录没有这个字段）。**取不到的版本直接抛错并提示"补进 RETIRED"，
绝不静默回退到启用版本** —— 那会让历史记录算出错误的 `P_A` 且毫无提示。

#### 8.1.3 为 P3 铺路的那个发现

轮换过程中确认了一件对 P3 至关重要的事：**早期密钥的用户侧本地份额 `u` 从未持久化**
（浏览器每次刷新页面重新生成），因此那批密钥**从解密角度本来就不可用**。
这不是故障，而是密钥隔离设计生效的表现 —— 服务端若能自行恢复 `d_A`，
反而说明"用户私钥不出客户端"这条不变量失效了。

#### 8.1.4 存量数据：清空并重新登记（已执行）

用户确认这批数据"都是可以再做的"，因此选择**清空 + 重新登记**，
而不是逐条标记为 `legacy_unusable`：

* `24_reset_legacy_key_data.sql` —— 清空 `keymanage` 与 `key_operation_record` 与测试残留的权限申请；
  **保留** `key_distribute_record`（不含密钥材料，且是工作台「分发状态分布」的数据源，P5 会连旧链路一起删除）；
* `kms-ops/tests/seed-demo-keys.mjs` —— 通过**真实接口**重新登记 8 把演示密钥
  （SM2/SSCL 混合、3 个用户）。新记录一律带 `ms_v2` + `v1_derived_sscl_domain` + `active`；
* 每把密钥使用**各自独立的 `ua`**（脚本内实现了 sm2p256v1 的标量乘），
  顺带消除了 R20 里"多把密钥共用一个 `ua`"的问题。

> `key_material_state = legacy_unusable` 这个**机制保留**，只是当下没有被行携带。
> 日后若再出现"用户丢失本地份额"的密钥，仍可用它如实标记。

#### 8.1.5 验证

| 项 | 结果 |
|---|---|
| `kms-ops/tests/KgcEpochProbe.java`（版本化行为，14 项） | **14 / 14**：`ms_v1` 仍可取到且等于历史演示值、`ms_v2` 为启用版本、空 `ms_key_id` 按 `ms_v1` 处理、未知版本明确抛错且提示补救办法、演示值不能被当作启用密钥 |
| 清空后重新登记 | 8 条，`ms_key_id` 无 NULL、`ua` 8 个互不相同 |
| 工作台 | KPI 4 张 / 图表 5 张，且**有数据**（清空后重新登记，未破坏"必须有数据"这条硬约束） |
| 回归 | `verify-p1` 36/36、`verify-keyvalue-redaction` 13/13、`verify-sscl-params` 7/7、管理端 27/27、用户前台 8/8、`check.ps1` 全通过 |

#### 8.1.6 若旧 `ms` 已不可恢复（本次未走这条路径，留档）

万一某次轮换时旧密钥已经丢失，则那批记录**无法真正恢复原有验证能力**。
此时的正确处理是：写一次性迁移脚本按当前版本重算 `P_A` 并重新登记，
但**必须保留原记录**，并新增迁移记录（`original_record_id` / `original_chain_hash` /
`migration_reason` / `new_ms_key_id` / `new_chain_hash` / `migrated_at`）——
即"新增迁移记录，不篡改历史记录"。本次因为旧 `ms` 仍在源码中可恢复，走的是版本化路径。

### 8.2 本轮插队修复清单（用户要求优先处理）

| 项 | 状态 | 验证 |
|---|---|---|
| `/generate/` 遗留前端下线（前端交付 5 → 4） | ✅ | `/generate/` → 404、`/generate-api/` 仍 200、smoke 4 端通过、admin 27/27、user 8/8 |
| `ms` 硬化（R17） | ✅ | Go 三态（演示值 panic / 缺失 panic / 合法启动）、Java Bean 创建阶段失败、`演示计算` 不再回吐中间量、`check.ps1` 断言 |
| `key_value` 脱敏（R18） | ✅ | `tools/verify-keyvalue-redaction.mjs` 13/13 |
| 数据存储端口收到回环 | ✅ | `docker port` 三处均为 `127.0.0.1`，`check.ps1` 断言 |
| 明文对称密钥行 + D12 代码 | ✅ | `22_*.sql` 自检为 0，`LifecycleService` 的 AES 分支与 `generateAesKey()` 已删 |
| SSCL 域参数确定性（R19） | ✅ | Go 4 类新测试 + 跨语言等价（33 值 0 差异）+ `tools/verify-sscl-params.mjs` 7/7（含重启前后逐字节比对） |

> **实施中额外发现并修复的（计划里没有的）**
> 1. **`generate-go` 从未收到 `KGC_MASTER_SECRET`** —— 它才是真正生成部分私钥的服务，
>    所以"线上生效值是公开值"的根因就在这里（R17）。
> 2. **第三份 SSCL 实现**（`kms-generate/java` 的 `SSCLGenerator`）同样在随机多项式，
>    且经 `insertKey` 的兜底路径可达（R19）。
> 3. **`kyber_aes_session_encryption` 与 `node_service.real_aes` 会因 16 字节密钥直接报错** ——
>    旧实现硬性要求 `len(key) >= 32`，SM4 落地后必然炸；已改为按长度分派。
> 4. **`/analysis/{keyId}` 是绕过脱敏的后门**（R18）。
> 5. **`verify-keyvalue-redaction.mjs` 自身曾有一次假通过**：两个模块的 JSON 命名不同
>    （`keyValue` vs `key_value`），只读前者会让生命周期侧断言读到 `undefined` 而"通过"。
> 6. **`start.sh` / `build-local.sh` 硬依赖被下线的 `/generate/` 前端**，会直接 `exit 1`。

---

## 9. 验证方案

### 9.1 已具备（直接复用）

| 工具 | 覆盖 | 当前基线（P1 完成后实测） |
|---|---|---|
| `tools/verify-admin-pages.mjs [port] [outDir] [app]` | CDP 驱动逐页巡检，采集异常/console.error/≥400 响应/路由落点。**已泛化支持 `app=user`** | 管理端 **27/27**；用户前台 **8/8** |
| `tools/verify-p1.mjs [origin]` | P1 的纯 HTTP 验收：菜单/接口存废、越权注入、LIKE 误命中回归、D9 分流前提 | **24/24** |
| `tools/verify-workbench-shape.mjs [cdpPort]` | 实测工作台的 KPI 卡数与图表数（§3.6.5 硬性约束：4 张 KPI / 5 张图） | **4 / 5 通过** |
| `tools/smoke-frontends.mjs` | 5 端产物完整性、缓存头、MIME、gzip | 全部通过 |
| `kms-ops/check.ps1` | 网关 7 + Go 2 + Java 2 + 代理 3 + DB 5 | 19/19 通过 |

> 管理端基线由 28 降为 27，是因为「密钥生成」菜单已按 P1-5 删除 —— 少了一个页面，不是少了覆盖。

### 9.2 需新增

| 项 | 内容 | 状态 |
|---|---|---|
| 用户侧页面巡检 | 把 `verify-admin-pages.mjs` 泛化，覆盖 `kms-user` 全部路由 | ✅ **P1 已完成**（`app=user`，含 `/permissions` 已删除、管理员被 D9 重定向两条断言） |
| SM4 正确性 | 国标 SM4 测试向量单测（加解密 + GCM 认证失败用例） | P2 |
| 分发链路端到端 | 1 用户 + 2 节点 → 校验 N+1 信封解封出同一密钥 | P3 |
| 越权用例 | A 的令牌读 B 的对称密钥/批次 → 必须 403；不带令牌 → 401 | P3 |
| **D17 负向用例** | 用 CL-Kyber / CL-Falcon 的 `key_id` 调分发接口 → **必须 400**（证明是服务端在拦，不是前端） | P3 |
| **加密目标用例（R16，新增）** | 断言信封的加密目标 == `W_A + λ·P_pub`；且"用 `W_A` 加密后用户能解开"必须是**失败**用例 | **P3 第一步** |
| **`u` 不外泄用例（R1'，新增）** | 抓取分发全流程所有出站请求体，断言不含浏览器本地份额 | **P3**（可提前到 P2 一并加） |
| **节点鉴权用例** | 分发到未授权节点 → 403；节点数 > 10 → 400 | P3 |
| 兼容性 | 旧 AES 密钥池数据仍可读取与使用 | P2 |
| ~~P0-B 安全断言~~ | 服务端材料解不开 SM2/SSCL 用户信封 | ✅ **P0-B 已完成**，结论"解不开"（§7 P0-B） |

---

## 10. 决策清单（Q1–Q12，全部闭环）

| # | 问题 | 我的建议 |
|---|---|---|
| Q1 | ~~§3.1 节点腿算法：保留抗量子（A）还是全链路国密（B）？~~ | ✅ **已定：A**（D10 / §3.1） |
| Q2 | ~~§3.4 `role_level` 保留 3 级还是收成 2 级？~~ | ✅ **已定：收成 2 级**（D13 / §3.4） |
| Q3 | ~~§3.5 管理端「算法说明」3 页保留还是删除？~~ | ✅ **已定：保留** |
| Q4 | ~~§3.6 旧「分发记录」链路如何处置？~~ | ✅ **已定：删除**（含 3 个消费方迁移，见 §3.6.2 / §3.6.3） |
| Q5 | ~~§3.2 单次分发最多选几个节点？~~ | ✅ **已定：10**（D15） |
| Q6 | ~~§6.3.4 管理端路径是否由 `/updatedel/` 改为 `/admin/`？~~ | ✅ **已定：改为 `/admin/`** |
| Q7 | ~~管理端是否允许查看**明文/可解封**的用户对称密钥？~~ | ✅ **已定：不允许**，只展示哈希 / 封装算法 / 来源密钥 / 过期时间 / 状态 |
| Q8 | ~~用户侧「我的操作日志」的数据源？~~ | ✅ **已定：含操作 + 登录日志**，按令牌 `user_id` 强制过滤（D14） |
| Q9 | ~~主 KMS 的 AES 生成路径：**删除**还是改 SM4？~~ | ✅ **已定：删除**（D12 / §3.5.1） |
| Q10 | ~~节点腿用 Kyber 还是 Falcon 封装？~~ | ✅ **已定：默认 Kyber**，由节点管理「默认封装算法」字段配置（D16） |
| Q11 | ~~是否连 `kms-distribute` Java 服务（8083）一起下线？~~ | ✅ **已定：下线**（D11 / §3.6.4） |
| Q12 | ~~用户腿可选算法是否收窄？~~ | ✅ **已定：(a) 收窄为 SM2 / SSCL**（D17 / §3.2.4）。服务端强制校验，非仅前端过滤 |

> **Q1–Q12 全部闭环，无待定项。**
> **P0-A / P0-B / P0-C 三项前置实验均已完成**（结论见 §7 与 §3.2.3/§3.2.4）。
> **P1 已完成并全部验证通过**（§7 P1）。下一步：**P2**（对称层 AES-256 → SM4）。
>
> ⚠️ 进入 P2/P3 前请先读三处**被实验修正过的**结论：
> 1. §3.2.3 的「⚠️ 加密目标点」—— 原文写的 `finalPublicKey` 是错的，
>    正确目标是 `P_A = W_A + λ·P_pub`，照原文实现会做出**谁都打不开**的信封（R16）；
> 2. §8 的 **R2'** —— 运行时**完全没有 SM2 实现**，P3 要先补密码学底座，
>    这一步的工期（SM2 = M）此前没有计入；
> 3. §8 的 **R17/R18** —— `ms` 是公开默认值且可被只读接口反推；`key_value` 明文外泄面较广。

---

## 附录 A：本次调研确认的关键事实（含出处）

| 事实 | 出处 |
|---|---|
| 系统无 SM4 | 全仓库 `SM4` 8 处均为误报；`gmssl`/`CryptSM4`/`MODE_SM4` 在 `kms-distribute` 零命中 |
| 对称密钥为 AES-256 | `pqkds/key_pool_service.py:115` `os.urandom(32)`；`:124` AES-GCM |
| 时限 24h 且写死 | `key_pool_service.py:33` `DEFAULT_EXPIRY_HOURS = 24` |
| AES 仅存在于分发模块（外加主 KMS 一处） | 分发后端 23 个 .py 命中；`kms-generate`/`kms-user`/`kms-acceptance`/`security` 零命中 |
| 主 KMS 支持 AES 对称密钥生成 | `kms-updatedel/.../LifecycleService.java:355,384-398` |
| 运行库仅 1 行 AES 演示数据 | `SELECT encryt_type,encryt_name,COUNT(*) FROM kms.keymanage GROUP BY 1,2` → SM2 17 / SSCL 4 / AES-256 **1**（`key_value` 长 9，`ua` 为 NULL） |
| 密钥池表 | `pqkds/models.py:328-358` → `dvadmin_pqkds_pre_distributed_keys` |
| 池是节点单向 | `models.py:342-346` `node1`/`node2` 外键 |
| 节点无 user 关联 | `models.py:23-114` 全字段无 owner |
| Falcon 是格**加密**非签名 | `falcon_aes_session_encryption.py:291` `fast_encrypt(A,B,H_id,U_id,aes_key,...)` |
| SM2/SSCL 在分发侧未实现 | `kms_adapter.py:108-115` `available: False, phase: 'frontend_local_simulation_only'` |
| 节点为服务端模拟 | `key_pool_local_storage.py:1-27` 本地 JSON `node_key_pools/{node_id}/pool_{id}.json` |
| 用户「分发」页只读 | `kms-user/front/src/views/distribute/DistributeView.vue:1-75` |
| 可申请权限仅 2 项 | `kms-user/front/src/services/permission-api.js:30-43` |
| 角色为 3 级数值 | `store/modules/user.js:53`；`frontend-role-boundary.md:191-196` |
| 管理员靠按钮跳转 | `kms-user/front/src/layout/components/Navbar.vue:80-91` |
| 双库双身份 | `kms` 库 `sys_user`；`falcon_kds` 库 `dvadmin_system_users` 等 11 张 RBAC 表 |
| 已有服务令牌通道 | `kms_adapter.py:21-73` `X-KMS-Service-Token` + `X-KMS-Service-ID` |
| 区块链有 registerNode 合约 | `pqkds/blockchain_service.py:341-346` |
| 旧"分发记录"是派生投影，非独立系统 | `DistributeKafkaConsumer.java:51-57` 只监听主 KMS 现成四个 topic，`:341-348` 把生成/更新/回收事件贴标签成"分发类型" |
| 旧分发链路的两个真实消费方 | 工作台 `WorkbenchView.vue:175,608-622,821`；`LifecycleService.java:109-125` 分发足迹 |
| 健康检查依赖该表 | `kms-ops/check.ps1:83` |
| `kms-distribute` Java 服务将无消费方 | 删除后 `/distribute-api/` 无调用方；其剩余 RuoYi 控制器无任何前端使用（`/distribute/` 前端走 `/pqkds-api/`） |
| **PQ 完整私钥明文落库** | `key_service.go:231` `json.Marshal(demoResp.Data)` → `views.py:116-128` 含 `private_key` → `GenerateKeymanageCompatController.java:104` `setKeyValue` → Kafka 落库 |
| **列表接口已脱敏** | `GenerateController.java:75-93` 另建对象、只回填 `extractPublicValue(...)` |
| SM2/SSCL 公钥格式统一 | `ua` 为 130 hex 的 `sm2p256v1` 曲线点；`EccKeyGenerator.java:102-113` / `SsclKeyGenerator.java:107-118` 校验长度与曲线 |
| 加密须用 `finalPublicKey` | `EccKeyGenerator.java:50` 存 `finalPublicKey`（完整公钥 `W_A`）；`ua` 只是用户部分公钥 |
| SM2 私钥分片 | `EccKeyGenerator.java:49` 存 `partialKey`（`t_A`）；`SsclKeyGenerator.java:46-47` 存 `SSCLKey`/`SSCLEA` |
| 当前无 UI 可产生 AES 密钥 | 5 个前端仅在说明文案与 `legacy-kms`（不构建）中出现 AES |