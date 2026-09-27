# 三子系统重构方案（设计文档，未实施）

> 状态：**设计稿**。本文只描述改造方案，不含任何已执行的代码改动。
> 日期：2026-09-26
> 相关文档：`doc/kms-restructure-plan.md`、`doc/frontend-role-boundary.md`

---

## 1. 背景与目标

课题要求系统划分为三个子系统：**密钥生成 / 密钥更新与回收 / 密钥分发**。系统名为「无证书密钥的生命周期管理」。

### 1.1 现状核查（经代码核实）

用户对现状的三个判断基本成立：

**① 三个子系统有目录边界，但没有独立性**

- 共享同一个 `kms` 库
- 「更新与回收」模块自带一份密钥生成实现（`EccKeyGenerator` / `SsclKeyGenerator`），不调用生成子系统
- `KgcMasterSecret`（无证书体系的信任根）在两个 java-backend 里各有一份拷贝（当前内容一致，未分叉）

**② 登录是三套，互不相通**

| 前端 | 登录态 | 说明 |
|---|---|---|
| `kms-user/front` | Cookie `Admin-Token` | 唯一登录入口 |
| `kms-updatedel/front` | 同一 Cookie | 守卫逻辑独立，无 token 时整页跳用户前台 |
| `kms-distribute/.../web` | sessionStorage 里的 JWT `token` | **另一套身份** |
| `kms-acceptance/front` | **无登录** | 裸 fetch，后端用固定凭据替代身份 |

**③ 用户端无法生成 CL-Kyber / CL-Falcon**

- 前端把它们标为 `demo_generated` 并送空 `uA`（`GenerateView.vue:505-506`）
- 后端 `_kms_generate_record_for_algorithm` 直接本地生成，返回 `keyId: null`，不入用户密钥表
- `strict_certificateless` 在 Go 与 Django 两处被显式拒绝

### 1.2 本次目标

- 删除登录，固定单一内置用户，直接进入系统
- 合并为一个前端，统一入口、菜单分三区
- 逻辑上分三个子系统，物理上一套部署
- 删除：系统管理模块、权限审批流、分发自带后台
- 保留：验收测试台、操作日志
- **分发子系统本次不改**（用户尚未确定"分发什么密钥"）

---

## 2. 关键设计决策

### D1：删登录 = 自动登录，不是"删掉认证"

**这是唯一可行路径，不是偏好。**

**用户视角**：永远看不到登录页，打开即进入系统。
**实现视角**：后端认证保持不变。

做法：前端启动时自动用内置账号调一次 `/login`，拿到真实 token 存进 Cookie（沿用既有的 `Admin-Token`），再走原有流程。

#### 为什么不能真的把认证删掉

查证后的硬约束链：

```
kms-generate/go-backend/middleware/verified_user.go:21-31   拒绝空的 X-Kms-User 头
        ↑
generate/client/GoBackendClient.java:194                    写入该头
updatedel/client/GoBackendClient.java:96-107                从登录会话推导用户名
        ↑
登录会话（TokenService + Redis）
```

**没有会话就没有 `X-Kms-User`，密钥生成 / 更新 / 回收三个子系统全部 401。**

#### 为什么保留身份层比删掉它更安全

`SecurityUtils.getUserId()` 不只是会话查询，它同时是：

- `LifecycleKeyController.java:44-45,65,85,220-230` 的**密钥归属校验**
- `isCurrentAdmin()` 门禁
- `KeyValueSanitizer` **按属主脱敏**的输入

删掉它需要逐处改造，且极易引入越权——`doc/kms-restructure-plan.md:988` 记录过这类缺陷已修复过一次。

#### 代价

内置账号口令会打进前端 JS 产物。演示系统可接受，但**答辩时必须如实说明，不要宣称"系统有认证"**。

---

### D2：单一身份的安全后果（必须知情）

`kms.keymanage.user_id` 是 `NOT NULL` 且有指向 `kms.sys_user` 的**真实外键**（`kms-ops/mysql/init/03.sql:6,36`）。因此：

- 用户表**必须保留**——删了密钥插入直接失败
- 密钥"属于谁"在数据层是真实的

固定单一内置用户后：

- 该身份能看到**全部**密钥材料，`KeyValueSanitizer` 的按属主脱敏失去意义
- 其他用户的密钥要么不可见（按 `userId` 过滤），要么全部可见（不过滤）

**这是一次真实的安全降级。** 演示场景可接受，但必须说清楚。

**缓解**：内置用户优先选当前演示密钥的属主。已核实本地演示数据中 `yx`（user_id=2）名下有 20 把 SM2 + 4 把 SSCL——以它作内置用户，演示数据不会"消失"。

---

### D3：前端合并目标 = `kms-updatedel/front`

两个前端**技术栈完全相同**：

| | kms-user/front | kms-updatedel/front |
|---|---|---|
| vue | 3.4.31 | 3.4.31 |
| vue-router | 4.4.0 | 4.4.0 |
| pinia | 2.1.7 | 2.1.7 |
| element-plus | 2.7.6 | 2.7.6 |
| axios | 0.28.1 | 0.28.1 |

同源 RuoYi-Vue3，合并是机械工作。

选 `kms-updatedel` 作壳：更大（167 vs 128 个源文件）、有完整的 Layout / 侧边栏 / 菜单基础设施。`kms-user` 只有 15 个视图，真正要移植的业务页 **6 个**。

---

### D4：菜单三区 = 重组 `sys_menu` 数据，不重写页面

菜单是数据库驱动的（`sys_menu` → `/getRouters` → 前端动态路由）。"分三区"主要是**写一个新的菜单 SQL 脚本**，页面组件本身大多不动。

---

### D5：分发子系统本次只做入口归位

用户明确"还没明确分发的到底是什么密钥"。因此本次：

- 把分发相关页面归入「密钥分发」区
- 下线 `/distribute/` 自带后台（它有自己的登录态，与"删除登录"直接冲突）
- **不动** `pqkds` 的任何业务逻辑

---

## 3. 与既有决策的冲突

### D9（登录分流）被本次取代

`doc/frontend-role-boundary.md:322-330` 的 D9 规定：

> 只有一个登录入口（kms-user），登录后按 `role_level` 分流；管理端不是入口。

本方案**删除登录**，与 D9 直接冲突。需要在实施前明确记录"D9 被本次重构取代"及取代理由，**不要默默覆盖**。

---

## 4. 实施步骤

> 顺序有依赖：先合并前端 → 再删登录 → 最后重排菜单（菜单指向的路由必须已存在）。

### 阶段 1 · 前端合并

#### 1.1 移植用户前台的业务页

从 `kms-user/front/src/views/` 移植 6 个业务页 + 3 个 profile 子页：

| 源 | 去向 |
|---|---|
| `generate/GenerateView.vue` | 密钥生成 |
| `lifecycle/LifecycleView.vue` | 更新与回收 |
| `distribute/DistributeView.vue`、`distribute/SymmetricKeysView.vue` | 分发 |
| `workbench/WorkbenchView.vue`、`logs/MyLogsView.vue` | 工作台 / 我的日志 |

配套移植 `kms-user/front/src/services/`（`generate-api.js` / `lifecycle-api.js` / `logs-api.js` / `user-distribution-api.js` / `permission-api.js`）与 `config/api-bases.js`。

⚠️ 两边都用 `@/` 别名指向各自 src。`kms-updatedel` 已有 `api/` 目录，建议 services 放进 `api/user/` 而非新造 `services/`。

#### 1.2 处理路由与权限指令冲突

- `kms-updatedel/front/src/permission.js`：删掉 `roleLevel` 分流（`isAdminLevel` 判断与 `window.location.replace(userConsoleUrl())`），改为直接放行
- `kms-updatedel/front/src/config/app-bases.js`：`userConsoleUrl` / `userLoginUrl` 不再需要
- 移植页若用了 `v-hasPermi` / `v-hasRole`，需确认内置用户有对应权限，或改用 `*:*:*`

#### 1.3 收敛前端入口

仓库有 **6 个前端目录，但只有 4 个在构建**（`kms-ops/build-local.sh:214-217`）：

| 目录 | 状态 |
|---|---|
| `kms-user/front` | 构建 → 本次合并后退役 |
| `kms-updatedel/front` | 构建 → 合并目标 |
| `kms-acceptance/front` | 构建 → **保留** |
| `kms-distribute/.../web` | 构建 → 本次下线 |
| `kms-generate/front` | **已退役**，网关显式 404（`nginx.conf:179`），见 `kms-generate/front/RETIRED.md` |
| `kms-distribute/front` | **从未构建**，不在 build 脚本里 |

改动：

- `kms-ops/nginx/nginx.conf`：删除 `location /user/`（第 324 行）与 `location /distribute/`（第 301 行）
- `kms-ops/build-local.ps1` 与 `build-local.sh`：停止构建 `kms-user/front` 与 `kms-distribute/.../web`
- `kms-ops/build/nginx.Dockerfile`：删除 `COPY front/user/` 与 `COPY front/distribute/`

⚠️ `kms-acceptance/front` **本来就没有登录**，不要纳入删登录范围。

**已核实的无风险项**：`/distribute/` 下线不会留下孤儿路由。分发前端的 API 基址是 `VITE_API_URL=/pqkds-api`（`.env.production`），与 `VITE_PUBLIC_PATH=/distribute/` 分离；删掉 `location /distribute/` 后，`/pqkds-api/` 仍被管理端节点管理页使用、必须保留。

#### 1.4 删登录页

- `kms-updatedel/front/src/views/login.vue`、`register.vue`
- `kms-user/front/src/views/login.vue`、`register.vue`（随整个前端退役）

### 阶段 2 · 删登录，固定内置用户

#### 2.1 内置账号

复用已存在的 demo 用户（`17_add_demo_test_user.sql` / `19_add_acceptance_user.sql`）。**不新增表、不新增字段。**

#### 2.2 前端自动登录

- `kms-updatedel/front/src/store/modules/user.js`：`getToken` 为空时自动调 `login()` 并缓存 token
- `permission.js`：白名单与跳转逻辑简化为"无 token → 自动登录 → 继续"
- 顶栏用户下拉（退出登录/个人中心）删除或改为只显示用户名
- 同步更新 `tools/lib/captcha.mjs`（见 §5）

#### 2.3 后端不动

generate-java / updatedel-java 的 Spring Security（`SecurityConfig.java:117,126`）、`TokenService`、Django 登录接口**全部保留**。这是本方案低风险的关键。

**两个已知干扰项**：

- `SmartSecurityFilter.java:27-110` 按 404/UA 模式**封 IP 30 分钟**。与登录无关但删登录后仍生效，会干扰自动化测试
- `nginx.conf:261-267` 已把 Django 的 `/pqkds-api/api/login/` 与 `/api/token/` 封成 403，但 `signIn`（`:233-239`）与 `signOut`（`:269-275`）仍在代理

### 阶段 3 · 删权限审批流

**依据**：`PermissionRequestService.java:74` 明确注释「刻意**不**调用 `sysUserMapper.updateRoleLevel(...)`」——审批通过**不授予任何权限**。真正的判定是 `hasActiveTemporaryPermission(userId)`。且 `submit` 注释写明「本域只有 AUTO_UPDATE 一个功能」。单用户下变成"自己申请自己批"。

删除清单：

- 后端：`PermissionRequestController` / `PermissionRequestService` / `PermissionRequestMapper` / `PermissionRequest`（`kms-updatedel/java-backend`）
- 前端：`views/permission/request/index.vue`、用户前台的申请按钮
- 权限判定：`LifecycleKeyController` 里的 `hasActiveTemporaryPermission` 调用改为直接放行
- 数据表：`permission_request`（保留建表脚本，部署脚本不再引用）

**保留**：`sys_oper_log`（操作日志）及其页面。

### 阶段 4 · 菜单三区重组

新增 `kms-ops/mysql/init/30_three_subsystem_menus.sql`，沿用 20/21/26/29 的写法（`INSERT ... ON DUPLICATE KEY UPDATE`，幂等）。

目标结构：

```
密钥生成
  ├─ 密钥生成          (移植来的 GenerateView)
  └─ 生成历史          (已有 views/generateHistory)

密钥更新与回收
  ├─ 密钥更新          (views/keyupdate)
  ├─ 密钥回收          (views/keydelete)
  ├─ 密钥自动更新      (views/keyautoupdate)
  └─ 公共参数          (views/commonParam)

密钥分发
  ├─ 分发总览          (views/distOverview)
  ├─ 密钥池            (views/keypool)
  ├─ 会话密钥          (views/sessions)
  ├─ 分发日志          (views/distlogs)
  ├─ 区块链存证        (views/chain)
  └─ 节点管理          (views/nodes)

（保留）
  ├─ 密钥查询 / 公共密钥 / 用户密钥池   (views/query/*)
  ├─ 算法说明          (views/algorithm/*)
  ├─ 操作日志          (views/monitor/operlog)
  └─ 验收测试台        (views/testing/*)
```

**删除的菜单**（保留后端与表，只去入口）：

- 系统管理整组：用户 / 角色 / 菜单 / 部门 / 岗位 / 字典 / 参数 / 通知
- 权限审批
- 个人中心（`/user/profile`，无多用户后无意义）

⚠️ `sys_menu` **表本身必须保留**——侧边栏完全由它驱动，删表等于删掉整个导航。

### 阶段 5 · 清理

- 删除 `kms-user/front` 整个目录（已移植完毕）
- 删除 `kms-distribute/extracted/ruoyi (2)/web`（分发自带后台，已下线）
- 更新受影响的文档：`fisco-chain-and-node-page-runbook.md` 的页面表、`kms-restructure-plan.md` 的目标架构章节

---

## 5. 21 个测试脚本的隐性成本（最易低估）

`tools/` 下有 **21 处** `document.cookie = 'Admin-Token=...'` 注入点，token 由 `tools/lib/captcha.mjs:65-80` 获取（带验证码，答案从 Redis 读）：

```
_probe-dropdown.mjs:25 · verify-workbench-shape.mjs:54 · verify-ui.mjs:46,78
verify-pages-smoke.mjs:110,135 · verify-node-page.mjs:116 · verify-node-keys-autogen.mjs:91
verify-node-crud.mjs:75 · verify-node-batch-falcon.mjs:92 · verify-manual-rotation.mjs:166
verify-key-file-ui.mjs:90 · verify-falcon-pool.mjs:84 · verify-distribute-ui.mjs:83
verify-browser-decrypt.mjs:82 · verify-admin-pages.mjs:162,361 · shot-admin.mjs:45
probe-router-base.mjs:45 · peek2.mjs:25 · measure-overflow.mjs:46 · dump-admin-sidebar.mjs:34
```

自动登录一旦改变 token 获取方式，这 21 个脚本**全部失效**。

**缓解**：把 token 获取收敛到 `tools/lib/captcha.mjs` 单一入口，改造时只更新它，21 个脚本本身不动。

---

## 6. 风险清单

| 风险 | 说明 | 应对 |
|---|---|---|
| 自动登录口令在前端可见 | 打进了 JS 产物 | 答辩如实说明；或加一个后端"免鉴权取 token"端点（仍非真认证，但口令不进产物） |
| **单一身份的密钥可见性塌缩** | §2，真实安全降级 | 选当前演示数据属主作内置用户；答辩主动说明 |
| **21 个测试脚本** | §5，最易低估 | token 获取收敛到 `lib/captcha.mjs` |
| `SmartSecurityFilter` 封 IP | 按 404/UA 封 30 分钟 | 跑验证脚本时注意，必要时临时调参 |
| 移植页面的隐藏依赖 | 可能依赖 `kms-user` 的 `utils`/`directive`/`store`（其 `hasPermi`/`hasRole` 有 22 处使用） | 逐页移植后立刻冒烟；diff 两侧 `src/utils/` 与 `src/directive/` |
| 菜单删多了失去导航 | `sys_menu` 表驱动侧边栏 | 脚本幂等 + 可回滚（先备份）；表本身绝不能删 |
| 删除系统管理后无法自助改菜单 | 菜单管理页被删 | 菜单 SQL 必须写好且可重复执行 |
| 分发能力本次未改 | 用户尚未确定分发什么密钥 | CL-Kyber/CL-Falcon 用户端链路**仍不通**，需另立一轮 |

---

## 7. 明确不做的事

- 不改分发子系统的业务逻辑（用户未定）
- 不拆后端服务、不拆数据库（"逻辑三个、物理一套"）
- 不修用户端 CL-Kyber / CL-Falcon 生成链路（另立一轮）
- 不动 `KgcMasterSecret` 双拷贝问题（范围外，建议后续收敛）
- **不为 `kms_adapter.py` 排任何工期**——已核实是死代码：未挂进 `pqkds/urls.py`（那里的 import 实际解析到 `views.py`），`docker-compose.yml:456-465` 明确记录全仓库无任何代码发送它的 `X-KMS-Service-Token` 头。容易与活着的 `kms_service_client.py` 混淆

---

## 8. 验证方式

沿用仓库既有的真浏览器验证模式（`tools/verify-*.mjs`，CDP 驱动 headless Chrome）。判据是**渲染后的 DOM**，不是 HTTP 状态码——这一页的故障史全是"接口 200 但页面上什么都没有"。

### 新增：`tools/verify-three-subsystems.mjs`

1. 直接访问根路径 → **不出现登录页**，直接进系统
2. 侧边栏存在三个顶层分组，且分组内菜单数正确
3. 已删页面（`/system/user`、`/permission/request`）**不可达**
4. 三个分区的代表页各能渲染（生成 / 密钥更新 / 密钥池）
5. 新建一把密钥 → 能在「密钥查询」看到，确认内置用户归属正确

### 回归（既有脚本，须全绿）

```bash
node tools/verify-pages-smoke.mjs        # 31 页，需按新菜单更新期望列表
node tools/verify-node-keys-autogen.mjs  # 28 项
node tools/verify-node-batch-falcon.mjs  # 21 项
node tools/verify-node-crud.mjs          # 7 项
```

---

## 9. 遗留问题（超出本次范围）

1. **用户端 CL-Kyber / CL-Falcon 生成链路不通**——前端送空 `uA`、后端不入库、`strict_certificateless` 被拒。要修需三件事：① 用户端生成并携带份额；② Django 侧改调生成系统而非本地生成；③ 生成系统支持 PQ enroll（`GenerateKeyServiceImpl.generateKeyValue()` 目前只处理 SM2/SSCL，其余直接抛 `IllegalArgumentException`）
2. **`KgcMasterSecret` 双拷贝**——无证书体系的信任根在两个模块各一份，当前一致但无同步机制。轮换主密钥要改两处
3. **「更新与回收」自带生成实现**——`EccKeyGenerator` / `SsclKeyGenerator` 与生成侧重复。`generate-go` 已预留 `REENROLL_KEY` 接口，应收敛过去
4. **节点腿的 KGC 不是 KGC**——`falcon_certificateless_strict_optimized.py` 的 `sk_KGC = pk_KGC = A`，且 `D_id` 由 `sha256(user_id)` 确定性派生（公开可算）。用户腿（Java，有版本化的 `ms`）是真 KGC，节点腿不是
5. **分发子系统的主语问题**——系统名是「无证书密钥的生命周期管理」，但「密钥分发」分的是 SM4 载荷密钥，无证书密钥在其中是工具而非主角。CL 语义上的"密钥分发"（部分私钥交付）实际发生在生成子系统内
