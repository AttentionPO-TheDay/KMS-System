# FISCO 链与节点管理：故障结论与运行手册

> 日期：2026-09-24　适用：`kms-ops/` 这套本地栈（Docker Desktop for Windows）
> 结论一句话：**共识从来没有坏过。** 卡住 KMS 的是"能连上链的客户端证书不存在"，
> 而"不出块"是因为链空载时**省略空块**——一发交易立刻落块。

---

## 1. 结论先行：三个被混在一起的现象，其实是三件独立的事

排查前大家看到的是一个症状："4 个节点都活着、都连着，但不出块，所以 KMS 写不了链"。
实测下来它是三件事叠在一起：

| # | 现象 | 真因 | 证据 |
|---|---|---|---|
| A | `getBlockNumber` 恒为 0，日志只有"生成 seal → 超时 → 换视图"，无 commit | **空块被省略**（`omitEmptyBlock: true`）。链上没有交易时不落块，PBFT 只做视图轮转。**这是正常行为，不是故障** | 部署合约那笔交易一到，高度立刻 0→1→2→3（§3） |
| B | KMS 记 `FISCO_NOT_READY`、宿主 `fetch failed` | **JSON-RPC 在容器内只监听 127.0.0.1**，发布到宿主的 8545 端口永远连不上 | 容器内 RPC 正常、宿主连接被拒（§2.2） |
| C | 就算节点出块，KMS 也连不上链 | **SDK 证书与链不是同一条 PKI**：链在跑 `CN=chain` (98:EB:D5…)，而 console/Java 后端用的是旧单节点链那套 (`CN=agency, OU=chain`)；工作区里**没有**对应 CA 私钥，谁都签不出被这条链接受的客户端证书 | 实测 `ssl handshake failed`；`openssl verify` 全部 FAIL（§2.3） |

**C 才是"KMS 写不了链"的根因，而它跟共识一点关系都没有。**
之前三轮都在攻共识，方向从一开始就偏了 —— 这一点值得记住：
"节点全连、创世一致、日志无 error" 只能证明**链自身**没问题，
不能证明**有人能连上它**。

---

## 2. 诊断过程（可复现）

### 2.1 先分清"链不健康"和"客户端连不上"

```bash
# 节点活着吗、peer 连上吗、共识状态如何（容器内直连 RPC）
docker exec kms_fisco_node0 bash /data/_rpc_probe.sh 8545
```

当时的输出里有两条关键信息：

```json
// getBlockNumber → 0x0，但共识状态说：
{"consensusedBlockNumber":1, "highestblockNumber":0, "connectedNodes":3,
 "currentView":819, "omitEmptyBlock":true, "txPoolSize":"0", "cfgErr":false}
```

`connectedNodes: 3`（对端全连）、`cfgErr: false`、`omitEmptyBlock: true`、
`txPoolSize: 0` —— **网络没问题、配置没问题、只是没有交易**。

### 2.2 宿主 `fetch failed` 的真身

```ini
# nodes/127.0.0.1/node0/config.ini
jsonrpc_listen_ip=127.0.0.1     # ← 容器内只监听回环
```

容器里跑 `curl 127.0.0.1:8545` 有应答，宿主连 `127.0.0.1:8545` 被拒 ——
因为发布出去的端口后面根本没有监听者。改成 `0.0.0.0` 后宿主立刻能查（§3 起一直可用）。

> 这一步很容易被误读成"链死了"。**判据是"在容器里查一次"**，
> 而不是"从宿主连不上就断定链有问题"。

### 2.3 证书谱系体检（决定性）

```bash
bash kms-ops/tests/fisco_cert_audit.sh   # 在 WSL 里跑
```

结果（节选）：

```
当前 4 节点链   node0/conf/ca.crt      subj = CN=chain,   O=fisco-bcos, OU=chain
                node0/conf/node.crt    iss  = CN=agency,  O=fisco-bcos, OU=agency
SDK（console）  ca.crt                 subj = CN=agency,  O=fisco-bcos, OU=chain   ← 不同的 PKI
kms-java-backend/conf/ca.crt           subj = CN=agency,  O=fisco-bcos, OU=chain   ← 与旧单节点链一致
签发关系校验: console/sdk.crt 不被当前链 CA 信任
```

再用 SDK 实测一次握手：

```bash
cd kms-ops/fisco/console
java -cp "lib/*;<编译输出>" SdkProbe conf/config.toml
# → ssl handshake failed: General OpenSslEngine problem.
#   Please make sure the certificate are correctly configured and copied.
```

**这条错误信息其实就是答案**，SDK 自己说了是证书。而 KMS 侧只把它记成
`FISCO_NOT_READY`，看起来像"链没出块"。

---

## 3. 修法：重建链，让 CA / 节点 / SDK 出自同一次构建

```powershell
pwsh -File kms-ops\scripts\rebuild-fisco-chain.ps1
```

脚本做了 6 件事（每一步都有注释说明为什么）：

1. 用 `fisco/build_chain.sh` 在 WSL 里生成 4 节点链（`-e` 用本地二进制，不联网下载）；
2. `tests/fisco_verify_newchain.sh` 自检：SDK 证书必须被**各节点的 channel CA** 信任；
3. 停旧容器、把旧链目录整体移到 `nodes/127.0.0.1.broken.<时间戳>`（保留现场，不删）；
4. 改写各节点 `config.ini`：
   - peer → `172.20.0.10N:3030N`（compose 的静态 IP，不依赖 DNS 解析）
   - `jsonrpc_listen_ip` → `0.0.0.0`（宿主才连得上）
5. **把 `sdk/*` 分发到 `fisco/console/conf/` 与 `kms-java-backend/conf/`**
   —— Java 后端镜像的 `/app/conf` 正是 `COPY fisco/console/conf/` 来的，
   这一步以前漏掉，正是 C 类故障的来源；
6. 重建并启动 4 个容器。

CA 私钥同时归档到 `kms-ops/fisco/cert/`（`ca.key` / `agency.key` / `agency/channel/ca.key`）。
**这是本次唯一能让"以后再签发 SDK 证书"成为可能的东西**，之前它丢了，
于是旧链只能整条废弃。⚠️ 仅限开发环境，勿随产物外发。

### 验证：一发交易立刻落块

```powershell
# 部署合约 + 写入（用 .env 里的 FISCO_PRIVATE_KEY，合约是 onlyOwner）
cd kms-ops/fisco/console
java -cp "lib/*;..\tests\_probe_out" DeployKeyEvidence conf\config.toml <FISCO_PRIVATE_KEY>
```

```
[deploy] 部署账户 = 0x58ae78e6f933b0d64dcde951ca05f270a2645796
[deploy] 部署后 blockNumber = 1     ← 交易一到就出块，共识本来就是好的
[deploy] uploadKey 状态 = 0x0  区块号 = 2  txHash = 0xe8f78247...
[deploy] changeKeyStatus 状态 = 0x0  区块号 = 3
CONTRACT_ADDRESS=0x740a25cad18527b15f7d6d5e3e0eafaa9567bfd6
```

部署出来的地址与 `.env` 里原有的 `FISCO_CONTRACT_ADDRESS` **完全一致**
（同一账户、nonce=0，地址可复现），所以 `.env` 的合约地址无需改动。

> **合约是 `onlyOwner`**：部署账户必须与 KMS 后端签名用的账户是同一个，
> 否则 `uploadKey/rotateKey` 会 revert，现象又是"上链失败"。
> 用 `FISCO_PRIVATE_KEY` 部署即可（脚本已如此）。

---

## 4. KMS 侧接线与端到端验证

```powershell
cd kms-ops
docker compose build generate-java updatedel-java      # 把新证书打进镜像
docker compose up -d --force-recreate generate-java updatedel-java
```

另外 `docker-compose.yml` 里两处改动：

| 改动 | 原因 |
|---|---|
| `KMS_LIFECYCLE_CHAIN_SYNC_ENABLED` / `..._CONSUMER_ENABLED` 默认 false → **true** | `application.yml` 默认本就是 true，compose 当年为绕开坏链压成 false。不改回来，更新/回收**永远不上链**，而现象只是"链上查不到" |
| 4 个节点端口发布改为 `127.0.0.1:...` | JSON-RPC 无认证，不该暴露给局域网（与 mysql/redis/kafka 的既有约定一致） |

**端到端结果**（真实交易，非模拟）：

| 步骤 | 入口 | 结果 |
|---|---|---|
| 生成 | `POST :8081/generate/request/ENROLL_KEY` | HTTP 200 |
| 入库 + 发链任务 | generate-java 消费 `key_generate_log` | `已发送上链任务到 key_chain_task，类型=ENROLL` |
| 上链 | `uploadKey` | `上链成功，txHash: 0x8c2d742f…, blockHeight: 4` |
| 库内字段 | `kms.keymanage` | `chain_status=1`、`block_height=4`、`chain_hash` 有值 |
| 更新 | `POST :8082/lifecycle/request/UPDATE_KEY` | `rotateKey` → 高度 5，version 1→2 |
| 回收 | `POST :8082/lifecycle/request/REVOKE_KEY` | `changeKeyStatus` → 高度 6，status=3 |

> ⚠️ **历史数据不可对账**：`key_id ≤ 70` 的记录是**旧链**时代的存证
> （`block_height` 64–68）。新链只有 1–6 号块，那些哈希在新链上查不到。
> 需要"链上可验证"的历史，得重新上链或明确标注为历史遗留。

---

## 5. 「节点管理」页：从"嵌别人的登录页"改成原生页面

### 5.1 故障是什么（有截图）

原配置把菜单指向 iframe：`component='frame/index'` + `query={"url":"/distribute/#/node"}`。
接口层一切正常，但渲染出来的是**分发模块自己的登录页**：

```json
// tools/verify-node-page.mjs 的输出
{ "frameSrc": "/distribute/#/node",
  "frameText": "抗量子分发系统 欢迎您！\n账号密码登录\n登 录" }
```

管理员已经登录管理端，点「节点管理」却要求再登一次 —— 而那个登录态与主 KMS 是两套。
**curl 永远发现不了这一点**，它只在渲染后出现。

### 5.2 修法

新增原生页面，复用管理端登录态，直接调 `/pqkds-api/nodes/*`：

| 文件 | 作用 |
|---|---|
| `kms-updatedel/front/src/views/nodes/index.vue` | 列表 / 新增 / 编辑 / 删除 / 批量删除 / 密钥概览 / **批量生成 Falcon** |
| `kms-updatedel/front/src/api/nodes/nodes.js` | 节点接口封装 |
| `kms-ops/mysql/init/27_node_management_page.sql` | 菜单 9103 改指 `nodes/index`，清空 `query` |
| `tools/verify-node-page.mjs` | 真浏览器验证（CDP），判据是**渲染后的 DOM** |
| `tools/verify-node-keys-autogen.mjs` | 验证"新建节点自动带齐三套密钥"与列表接口瘦身（28 项断言） |
| `tools/verify-node-batch-falcon.mjs` | 验证批量生成 Falcon **及单节点失败隔离**（21 项断言，含失败注入） |
| `tools/lib/mysql.mjs` | 验证脚本查库的统一入口（Windows 下 docker 绝对路径 + 不吞 stderr） |

**踩到的一个坑**：新页面第一次上线后接口 200、表格却空白。原因是
RuoYi 的响应拦截器要求 `code === 200`，而分发模块（dvadmin）的成功码是 **2000**
—— 成功响应被判成错误拒掉。所以 `api/nodes/nodes.js` 用**独立 axios 实例**，
只认 HTTP 状态码。这也解释了为什么同目录的「节点鉴权」页是好的：
它的接口是手写视图，返回的正是 `code: 200`。

### 5.3 边界（别误解）

- 这一页管的是**分发系统的业务节点**（`falcon_kds.dvadmin_pqkds_nodes` 表：谁可以向谁分发密钥），
  **不是 FISCO 链的记账节点**。因此它**不依赖链是否出块**，链挂了照样能用。
- 新增节点会调 `node_service.register_node()` 一并生成**三套**密钥：
  Kyber、国密（SM2 + SSCL）、Falcon（2026-09-26 起 Falcon 也自动生成，
  此前必须手动点「生成 Falcon 密钥」）。那是该节点之后参与节点腿分发的前提。
  **代价：注册从约 2 秒变成约 20 秒**，界面必须显示"生成中"并抑制重复提交。
  任一套生成失败只记日志、不阻断注册，页面上以就绪状态如实反映，
  并提供单节点「密钥」弹窗与「批量生成 Falcon」两处补生成入口。
- 服务端现状：分发模块的 `NodeViewSet` 把这些动作全放进了免鉴权白名单
  （`get_permissions`），即**接口不校验身份**。前端按登录态访问，
  但不要把"页面上看得见"当成"服务端已授权"。要收紧得改分发模块。
- ⚠️ **列表接口不带公钥本身**（2026-09-26 改）。`falcon_public_key` 实测 7.8MB/节点，
  原先 `NodeDetailSerializer` 把它一起返回，3 个节点就是 23.4MB —— 节点一多必然
  顶到 gunicorn 的 `timeout=120`。现在列表走 `NodeListSerializer`，只回
  `kyber_key_ready` / `falcon_key_ready` / `gm_key_ready` / `sscl_key_ready` 四个布尔值。
  加字段时**不要**把公钥加回列表；要看公钥请用 `/nodes/{id}/keys/`（回指纹，
  不回收 17MB 的 Falcon 公钥原文）。
- 另有一列 `falcon_lattice_params`（10.2MB/节点）已**停写**：全仓库无读取方，
  内容与 `falcon_private_key`、KGC 部分私钥重复；写它曾占掉 Falcon 生成流程
  11 秒里的大头。字段与历史数据保留，只是不再产生新的。

---

## 5.5 管理端另外三处故障（2026-09-24 第二轮，由用户截图引出）

用户反馈三条：「总览仪表盘界面不存在」「菜单栏里有两个节点鉴权」「节点鉴权页报错」。
实测下来前两条是**同一个根因**，第三条是另一类问题。

### 5.5.1 总览仪表盘被"顶掉"（路由重名）

**现象**：登录后本来该落在总览仪表盘，实际 `router.resolve('/index')` 只匹配到兜底
`/:pathMatch(.*)*` —— 页面打不开。

**根因**：后端 `getRouters` 按菜单 `path` **首字母大写**生成路由名。DB 菜单 9006
的 path 是 `index`，于是下发路由的 name 也叫 **`Index`**；而静态路由里仪表盘
（`/index`）的 name 恰好也是 `Index`。vue-router 4 在 `addRoute` 遇到重名时
**会先移除旧路由**，于是仪表盘那条被整个替换掉，`/index` 不复存在。

**修法**：`router/index.js` 里把仪表盘路由名改成 `Dashboard`。
这类撞名不该靠"记得别用某个名字"来避免，所以顺手在代码里写清了这条约定。

### 5.5.2 两个「节点鉴权」（静态路由与 DB 菜单重复注册）

**现象**：页签栏里两个一模一样的「节点鉴权」。

**根因**：`router/index.js` 开头明确写着"业务页只由 sys_menu 下发，避免前后端两份菜单叠加"，
但 P3-10 又把 `/nodeauth` **静态注册了一份**（注释原话："DB 菜单行同时插入，只为让它出现在侧边栏"）。
于是同一个路径有两条路由记录（静态的 `NodeAuthorization` + 下发的 `Index`）——
页签是**按路由记录**生成的，两条记录就是两个页签。

**修法**：删掉静态 `/nodeauth` 路由，业务页只留 sys_menu 一个来源。

> 这两条一起修，是因为它们互为表里：不删静态路由，撞名就还在；
> 只改名字不删重复，两个页签就还在。

### 5.5.3 节点鉴权页取节点列表必然报错

**现象**（用户截图）：左上角红条「加载节点列表失败：undefined」，
右上角红通知「获取节点列表成功…」。

**根因**：页面用 `@/utils/request` 取 `/pqkds-api/nodes/`，而分发模块对**同一个模块的两种信封并存**：

| 接口 | 返回 | 走 RuoYi request |
|---|---|---|
| `/admin/users/`、`/admin/node-authorizations/`（手写视图） | `code: 200` | 正常 |
| `/nodes/`、`/nodes/{id}/`（DRF ViewSet） | `code: 2000` | **成功也被判成错误** |

RuoYi 拦截器在 `code !== 200` 时弹 `ElNotification.error({title: 后端的 msg})`
并 `Promise.reject('error')` —— reject 的是字符串，所以调用方 `error.message` 得到
`undefined`。**那条红通知的标题就是后端返回的"获取节点列表成功…"**，等于把证据打在屏幕上。

**修法**：抽出共用客户端 `src/api/pqkds/http.js`（同时认 200 与 2000，
且 reject 真正的 `Error`），`api/nodes/nodes.js` 与 `api/nodeauth/nodeauth.js` 都用它。

顺带修掉一个显示缺陷：下拉标签渲染成「演示节点2（**undefined**）」——
接口字段是 `node_id`，模板读 `n.nodeId`，列表有数据而编号是 undefined，
很容易被当成"没取到数据"。已在 API 层统一成驼峰。

**实测（真浏览器）**：

| 检查 | 修前 | 修后 |
|---|---|---|
| 该页 toast | 一条 `[错误]` + 一条内容为"成功"的红通知 | **无** |
| 节点下拉 | 空 | `演示节点2（DEMO-NODE-02）`、`演示节点1（DEMO-NODE-01）`（2 项） |
| 侧边栏「节点鉴权」条数 | 2 | **1** |
| `/index` 解析 | `/:pathMatch(.*)*`（兜底） | `["", "/index"]`，渲染出 KMS 管理控制台 |
| 登录后落点 | `/nodeauth/index` | **`/index`（总览仪表盘）** |

### 5.5.4 「节点鉴权」已改名为「节点分发授权」（功能未动）

用户的疑问："节点鉴权指的是普通用户提高自己权限申请而已，现在感觉是区块链的节点呢。"

事实是**两个不同的功能，都在系统里，页面都正常**：

| 菜单 | 位置 | 干什么 | 后端 |
|---|---|---|---|
| **权限申请** | 权限与审计 → 权限审批 → 权限申请（`/audit/permission/request`） | **普通用户申请提高自己的权限等级**，管理员审批（通过/拒绝/回退） | `PermissionRequestController`，`/permission/request/*` |
| **节点分发授权**（原「节点鉴权」） | 顶层菜单（`/nodeauth/index`） | **管理员把"分发节点"授权给某个用户**，决定他能向哪些节点分发密钥（P3-10 / D5） | 分发模块 `/pqkds-api/admin/node-authorizations/*` |

用户确认按"改名、保留功能"处理，已做（migration `28_rename_nodeauth_menu.sql`）：

1. 菜单 9005/9006 更名为 **「节点分发授权」**（`menu_name` 是侧边栏与页签的文案来源）；
2. 页面标题同步改名，说明补齐为"管的是**哪个用户可以向哪些节点分发密钥**"；
3. 页面明确写出两点边界：这里的"节点"是**分发系统的业务节点**（演示节点 1/2），
   **不是区块链记账节点**，故与链是否出块无关；要找"用户提权申请"请去权限申请那一页；
4. 页头加「去「权限申请」」按钮，一键跳到 `/audit/permission/request`
   （实测可跳转，落点正确）—— 名字对不上时，代价是用户去错的页面找功能，
   然后以为系统缺了东西；给个直达入口比写一句说明更管用。

> **未采用的两个选项**（记录在此，免得日后重复讨论）：
> 把「权限申请」提为顶级菜单；或删除「节点分发授权」菜单。
> 后者会让管理员失去授节点权的入口，而节点腿分发对未授权节点仍会 403 —— 功能会真的缺一块。

---

## 5.6 分发模块：把「功能」复用进管理端（2026-09-24 第三轮）

用户要求（原话）："**我不要他的登录鉴权那套页面，我只需要你将他的分发功能模块复用到我的系统上来**"。

### 5.6.1 为什么不做 SSO

先做过判断：让分发模块复用管理端登录态（SSO）也能消掉登录墙，但它**只解决"能进去"**，
进去之后仍然是一个长得不一样的应用（自带侧边栏、主题、菜单），
下次照样会被问"这算融入我的系统了吗"。用户明确否掉了这条路。
所以走的是：**只复用它的功能与数据，页面用管理端自己的组件重写**。

### 5.6.2 复用了什么

分发模块的功能其实全在它的接口里，而接口本来就是开放可调的（`/pqkds-api/*`）。
原生页面直接调这些接口，用的是管理端的登录态 —— 因此**不存在第二个登录**。

| 管理端新页面 | 路由 | 做什么 | 接口 |
|---|---|---|---|
| 分发总览 | `/distchain/overview` | 节点/密钥池/会话/日志聚合 + 快速入口 | `/stats/overview/`、`/key-pool/stats/`、`/logs/`、`/nodes/` |
| 密钥池 | `/distchain/keypool` | 列表、**生成并分发**、补充、清理过期、删除 | `/key-pool/*` |
| 会话密钥 | `/distchain/sessions` | 会话元数据（只读） | `/session-keys/` |
| 分发日志 | `/distchain/distlogs` | 节点侧动作流水（含链上 tx） | `/logs/` |
| 区块链存证 | `/distchain/chain` | 密钥上链的 tx 哈希与块高 | `/lifecycle/keymanage/list` |
| 节点管理 | `/distchain/nodes` | 演示节点增删改（第二轮已完成） | `/nodes/*` |

菜单改动见 `kms-ops/mysql/init/29_distribution_native_pages.sql`：
9101「分发控制台」→「分发总览」，9102「区块链浏览器」→「区块链存证」，
新增 9104/9105/9106，两处 `query`（iframe 目标地址）一并清空。

**口径修正**：原「区块链浏览器」是分发模块自带的视图，默认 provider 是
**Ganache**（`http://127.0.0.1:7545`），与 KMS 实际使用的 **FISCO 链不是一条链**。
现在改成展示本系统真正写进 FISCO 的存证（`chain_status` / `block_height` / `chain_hash`），
对"哪些密钥真的上链了、在哪一笔交易里"这个问题更直接。

### 5.6.3 实测（真浏览器，非静态渲染）

| 页面 | 结果 |
|---|---|
| `/distchain/overview` | 原生渲染，`iframe=false`，KPI 有值（节点 2/2、密钥池 31） |
| `/distchain/keypool` | **31 行数据**，批次号/节点/算法/状态/哈希/过期时间都在 |
| `/distchain/sessions` | 原生空态（当前确实没有会话） |
| `/distchain/distlogs` | 原生空态（当前确实没有日志） |
| `/distchain/chain` | **29 行存证**，首行 keyId=72「已上链」块高 7、tx `0x112e3de3…` |
| 全部页面 | **toast 为空**（没有报错），**无 iframe**，**无登录页** |

**核心动作也实跑了**（不只是看渲染）：在「密钥池」界面里点「生成并分发」→
选发送方 `DEMO-NODE-02`、接收方 `DEMO-NODE-01`、数量 5 → 提交 →
服务端返回 `{success:true, pool_id:"pool_dist_cb9bb02c…", generated:5}`，
表格 **31 → 36 行**。

> 顺手修掉一个自己造的瑕疵：第一次我猜的返回字段是 `count/keys/total`，
> 实际是 `generated`，于是把一整串 JSON 当提示文案显示了出来。
> 功能没坏，但"能跑"和"对"是两件事，已改为按真实字段读取。

---

## 5.7 用户前台：表单「元素塌陷」与菜单缺图标（2026-09-24 第四轮）

### 5.7.1 元素塌陷：一条全局 CSS 误伤了 Element Plus 的标签

**现象**（用户截图）：密钥生成表单里标签与控件错位；宽屏下相邻两行的标签**叠印**在一起
（"算法类型"上压着"所属域"、"算法名称"上压着"自动更新"）；窄屏下变成标签一行、控件一行。

**根因**（实测，不是推测）：`kms-user/front/src/styles.css` 里有

```css
.form-grid label { display: grid; gap: var(--kms-space-2); ... }
```

这条是给**页面自己写的**普通 `<label>` 用的，但 Element Plus 的表单标签渲染出来
就是 `<label class="el-form-item__label">`，它也在 `.form-grid` 里 → 被一起命中：

* 标签内部变成**两行栅格**：第一行是必填星号 `*`，第二行才是文字
  → 文字下沉约一行，控件还停在原位，看起来就是"标签塌了"；
* 再叠加 `GenerateView.vue` 里的 `.generate-form :deep(.el-form-item) { margin-bottom: 0 }`，
  行距被抹平，相邻栅格行的标签就直接压在一起。

同一条漏还命中 `input`：`.form-grid input` 匹配到 el-input 内部的
`<input class="el-input__inner">`，又给它套了一层 border/padding
→ 输入框渲染成**双层边框**（截图里"密钥名称"那一格）。

**修法**：给这些规则加显式排除 —— `label:not(.el-form-item__label)`、
`input:not(.el-input__inner)`（含 `::placeholder` / `:focus` 两个变体）。
排障时用浏览器实测了 label 的 `display`：修前是 `grid`，修后是 `flex` —— 这就是判据。

**顺带加固**（即使别的页面再踩也不会压字）：

| 位置 | 改动 | 为什么 |
|---|---|---|
| `GenerateView.vue` | `.form-grid.two-col` 的 `minmax(220px→320px)`，并显式给 `row-gap: 16px` | 格子只有 220~240px 时，108px 标签 + 控件（el-select 最小 120px）放不下，控件会被挤到下一行 |
| 同上 | `.el-form-item__content { flex-wrap: nowrap; min-width: 0 }` | 控件宁可收缩也不折行 —— 折行才是"塌陷"的起点 |
| 同上（媒体查询） | 新增 `@media (max-width: 1200px) { .generate-layout { grid-template-columns: 1fr } }` | 原来只在 ≤960px 堆叠；961~1200px 区间右侧「本地材料」的文字会压到表单上（1024px 实测） |

**实测（四个宽度，判据是"标签与控件是否同一水平线"）**：

| 视口 | 修前 | 修后 |
|---|---|---|
| 1024 | 标签/控件错行 | 0 项错位，布局改为上下堆叠（表单 564px 全宽） |
| 1280 | — | 0 项错位，两列 534+320 |
| 1664 | — | 0 项错位，两列 829+415，表单 2 列 |
| 2080 | — | 0 项错位，两列 1107+553，表单 3 列 |

### 5.7.2 菜单缺图标：图标名写了一个不存在的

**现象**：侧边栏「对称密钥查看」只有文字、没有图标。

**根因**：路由写的是 `meta: { icon: 'key' }`，而该前端的图标集
（`src/assets/icons/svg/`）**没有 `key.svg`**。缺图标不报错，只是那个位置空着 —— 很难发现。

**修法**：改用已存在的 `lock`。顺手把全部路由的 icon 与图标集做了一次比对，
只有 `key` 这一个缺失；其余（dashboard/edit/time-range/download/log/user）都在。

**实测**：侧边栏 DOM 里该项现在挂着 `<use xlink:href="#icon-lock">`，尺寸 14px。

> 教训记在这里：**图标名不是自由文本**，写错既不报错也不告警。
> 新增菜单时应顺手比对 `src/assets/icons/svg/` 下的文件名。

---

## 5.8 「更新密钥」被"自动更新权限"误拦（2026-09-24 第五轮）

### 5.8.1 现象与根因

用户截图：在「更新与回收」里点「确认更新」，弹的是
**「当前用户没有自动更新操作权限」** —— 而他只是要改密钥的元数据。

根因在后端 `LifecycleKeyController.update`：

```java
// 原实现：只要请求里**出现** autoUpdate 字段，就要求自动更新权限
boolean touchesAutoUpdate = request.getAutoUpdate() != null
    && !request.getAutoUpdate().trim().isEmpty();
```

而两个前端的更新弹窗都带一个「自动更新」开关，提交时把开关的**当前值**一并送上
（`autoUpdate: '1'/'0'`，**恒非空**）。于是：

* 请求确实带了 `autoUpdate` → 后端判定"要改自动更新" → 要求权限；
* 用户既没有该权限、也没打算改自动更新 → 被拦，且报错内容与他做的事完全对不上。

### 5.8.2 修法（两处，缺一不可）

**前端**：更新弹窗去掉「自动更新」开关，并且提交时**不再带** `autoUpdate` 字段。
理由不只是"重复入口" —— 用户前台本页上方就有独立的「自动更新配置」区域，
管理端也有独立的「密钥自动更新」菜单；这个开关既重复又会污染请求。

**后端**：判定从"**字段出现**"改成"**值真的变了**"：

```java
if (lifecycleService.changesAutoUpdate(current, request.getAutoUpdate()) && !canManageAutoUpdate()) {
    return AjaxResult.error("当前用户没有自动更新操作权限");
}
```

`changesAutoUpdate` 用 `normalizeAutoUpdate` 归一化后再比，
避免 `'true'/'enabled'/'1'` 这类等价写法被误判成"变了"。
**防绕过的本意保留**：想借"顺手改个元数据"把自动更新打开，仍然会被拦。

### 5.8.3 验证：一放一拦，两条都要成立

只验"放行"会把权限检查验没；只验"拦截"说明不了原来的 bug 修没修。
脚本 `tools/verify-update-vs-autoupdate.mjs` 刻意用**不具备自动更新权限的普通用户**
（`acceptance_user`，role_level=2）来跑 —— 用管理员跑的话两条都会"通过"，等于什么都没验。

```
[OK] 以普通用户登录成功
[OK] 创建一把测试密钥  keyId=76
（该密钥当前 autoUpdate=0）
[OK] A1 只改元数据（不传 autoUpdate）→ 放行
[OK] A2 带上未变化的 autoUpdate → 放行（用户遇到的正是这一条）
[OK] A3 autoUpdate 用等价写法（'false' 等价于 '0'）→ 放行
[OK] B  真的把 autoUpdate 改成 1 → 仍被权限拦下   msg=当前用户没有自动更新操作权限
[OK] 清理测试密钥（回收）
结果: 7 通过 / 0 失败
```

界面侧同样实测（真浏览器）：

| 页面 | 弹窗表单项 | 开关数 | 提交结果 |
|---|---|---|---|
| 用户前台「更新与回收」 | 密钥ID/算法类型/算法名称/密钥名称/密钥用途/所属域 | **0** | toast「密钥更新成功」（不再是权限错误） |
| 管理端「密钥更新」 | 密钥ID/用户名/算法类型/算法名称/密钥名称/密钥用途 | **0** | — |

> 写这个脚本时踩了两个坑，都不是被测代码的问题，记下来省得下次再踩：
> ① 造测试密钥用的 UA 必须是**曲线上的合法点**，随手拼的十六进制会被拒
>    （"SM2 用户部分公钥不在曲线上"）；
> ② 这一层接口返回的是 **snake_case**（`key_id` / `auto_update`），
>    前端有归一化、脚本没有 —— 直接读 `data.keyId` 会得到 `undefined`，
>    看起来像"接口没返回数据"。

---

## 5.9 登录入口与验证码：为什么"有的登录页没有验证码"（2026-09-24 第六轮）

### 5.9.1 现象与事实

用户截图：`/updatedel/login?redirect=/index` 这个登录页**没有验证码**，而别处有；
并追问"难道登录页面现在还有好几套？"。

查下来**确实有两套登录页，而且验证码策略不一致**：

| 前端 | 登录页 | 登录接口 | 后端 | 验证码 |
|---|---|---|---|---|
| `/updatedel/`（管理控制台） | 自带 | `/updatedel-api/login` | updatedel-java | **关** |
| `/user/`（用户前台） | 自带 | `/generate-api/login` | generate-java | **开** |
| `/distribute/`（分发模块自带） | 自带 | Django 自己的 | dvadmin | 与主 KMS 无关（已无入口） |

不一致的根因是 `selectCaptchaEnabled()` 两个后端写得不一样：

```java
// kms-updatedel：先看环境变量
String captchaEnabledOverride = System.getenv("KMS_CAPTCHA_ENABLED");
if (StringUtils.isNotEmpty(captchaEnabledOverride)) return Convert.toBool(captchaEnabledOverride);
// kms-generate：**没有这一段**，只读 DB 的 sys.account.captchaEnabled
```

而 compose 只把 `KMS_CAPTCHA_ENABLED` 注入给 updatedel-java（默认 `false`），
`generate-java` 压根没这个变量 → 它读 DB 里的 `true`。
于是**同一个系统里，管理端登录不要验证码、用户前台要验证码**。

更要紧的是：**两套登录页本身就与设计相反**。两个前端的
`config/app-bases.js` 里都写着同一句话（D9）：

> 系统只有一个登录入口（本应用 / kms-user），登录后按 roleLevel 分流 ——
> 管理员进管理控制台，普通用户留在用户前台。

也就是说唯一入口本该是**用户前台**的登录页；管理端那套是自己遗留的，且被路由守卫
`next('/login?redirect=...')` 一直用着。两处漂移叠在一起，才出现"登录页有好几套、
验证码还不一样"的观感。

### 5.9.2 修法：入口收敛 + 开关收敛

**入口**：管理端未登录时不再渲染自己的登录页，整页跳到唯一入口（用户前台登录页）：

```js
// kms-updatedel/front/src/permission.js
window.location.replace(userLoginUrl())   // 原来是 next('/login?redirect=...')
```

管理员登录后由用户前台的守卫按 `roleLevel` 送回管理端（这条早已实现）。
两个应用同源、共用 `Admin-Token`，所以只登录一次。
路径集中在 `config/app-bases.js` 的 `userLoginUrl()`，不散写字符串。

**开关**：给 generate-java 补上**同一份** env 覆盖，compose 也给它注入同一个变量，
并把 `KMS_CAPTCHA_ENABLED` 显式写进 `kms-ops/.env` 与 `.env.example`（此前它是
compose 里一个隐式默认值 —— 没人知道"关掉验证码"是谁决定的，这正是问题说不清的原因）。

> ⚠️ **安全性说明**：开关初版被设成 `false`（理由：让 `tools/` 下的验收脚本能自动登录），
> 但用户随即指出登录页**应当有验证码** —— 那是把"配置不一致"错修成了"关掉安全项"。
> 现已取 **`true`**，两端同时生效。自动化不能靠关掉验证码来适应，
> 而应自己取答案（见 §5.9.4）。

### 5.9.4 打开验证码之后：让自动化自己去取答案

验证码一开，所有靠"裸登录"的脚本都会失败。这里的选择是**改脚本，不改产品**：
不在登录接口留"带内部令牌就免验证码"的后门 —— 那等于在认证入口开一个长期通道，
而验证码存在的意义正是挡暴力尝试。夹具只应存在于测试侧。

服务端把答案写在 Redis 的 `captcha_codes:<uuid>`（见 `CaptchaController`），
于是脚本：`/captchaImage` 拿 uuid → 从 Redis 读答案 → 带 `code`/`uuid` 登录。

| 载体 | 实现 |
|---|---|
| 宿主机脚本（`tools/*.mjs`） | `tools/lib/captcha.mjs`：`captchaFields()` / `login()`，用 `docker exec kms_redis redis-cli get` |
| 验收容器内（`security/security_test.sh`） | 自带 `redis_get()`：镜像里没有 redis-cli，用 bash 的 `/dev/tcp` 直接发 RESP `GET` |

已接入的脚本（共 12 个）：`verify-p1`、`verify-update-vs-autoupdate`、`verify-keyvalue-redaction`、
`verify-sscl-params`、`verify-pa-target`、`verify-ui`、`verify-workbench-shape`、
`verify-browser-decrypt`、`verify-key-file-ui`、`verify-admin-pages`、`verify-node-page`、`verify-node-crud`。

**实测**：

| 检查 | 结果 |
|---|---|
| 登录页（唯一入口 `/user/login`） | 出现「验证码」输入框与算式图；不填直接提交 → 客户端拦「请输入验证码」 |
| 填错验证码 | 服务端返回 `{"code":500,"msg":"验证码错误"}`（**证明服务端真的在强制校验**） |
| 用正确验证码登录（验收容器内实测） | HTTP 200 + token |
| 回归：`tools/verify-p1.mjs` | **36 通过 / 0 失败**（全部登录都过了验证码） |
| 回归：`tools/verify-update-vs-autoupdate.mjs` | **7 通过 / 0 失败** |

> 两个坑，都值得记：
> ① **Redis 里的答案是带引号的**：服务端用 Spring 的 `RedisTemplate`（JSON 序列化）写入，
>    字符串 `18` 存成 `"18"`。直接拿 `"18"` 提交会得到「验证码错误」，
>    现象像"答案取错了"，其实只是少剥了一层引号（`tools/lib/captcha.mjs` 与
>    `security_test.sh` 都已处理）。
> ② **不要用"填页面表单 + 点登录"的方式驱动登录**：登录页挂载时会自己取一张验证码，
>    uuid 存在它的表单状态里；脚本读不到那个 uuid，只能拿自己取的答案去填，
>    服务端按页面提交的 uuid 校验，必然失败。正确做法是宿主机取码登录后注入 Cookie
>    （`verify-node-page.mjs` / `verify-node-crud.mjs` 已改为此法）。

---

## 6. 下次再遇到"链不通"，按这个顺序查（省时间）

1. **容器内**查一次 RPC（`_rpc_probe.sh`）：`getBlockNumber` / `getConsensusStatus`。
   宿主连不上 ≠ 链有问题。
2. 看 `consensusedBlockNumber` 与 `txPoolSize`：
   **空载不出块是正常的**（`omitEmptyBlock: true`）。要判断共识活没活，
   **发一笔交易**，而不是盯着 `getBlockNumber`。
3. 跑 `tests/fisco_cert_audit.sh`：SDK 证书是否被**当前链**信任。
   换链之后必须重发 SDK 证书，否则前面两步全对也连不上。
4. 看 KMS 侧日志有没有 `ssl handshake failed`（SDK 初始化那几行），
   它比 `FISCO_NOT_READY` 有用得多。

## 7. 相关文件

| 文件 | 说明 |
|---|---|
| `kms-ops/scripts/rebuild-fisco-chain.ps1` | 重建链 + 换链 + 分发证书（幂等，可重跑） |
| `kms-ops/tests/fisco_cert_audit.sh` | 证书谱系体检（在 WSL 跑） |
| `kms-ops/tests/fisco_verify_newchain.sh` | 新链自检：nodeid/创世/签发关系 |
| `kms-ops/tests/SdkProbe.java` | 最小 SDK 探针：连得上吗、几号块 |
| `kms-ops/tests/DeployKeyEvidence.java` | 部署合约 + 三种写入，验证"有交易就出块" |
| `kms-ops/tests/fisco_rpc_probe.sh` | 容器内直连 RPC（无 curl 也能用）；换链时由重建脚本投放到链目录 |
| `kms-ops/mysql/init/27_node_management_page.sql` | 节点管理菜单改造 |
| `kms-ops/mysql/init/28_rename_nodeauth_menu.sql` | 「节点鉴权」→「节点分发授权」改名 |
| `kms-ops/mysql/init/29_distribution_native_pages.sql` | 分发模块功能原生化的菜单改动 |
| `kms-updatedel/front/src/api/pqkds/distribution.js` | 分发功能接口（密钥池/会话/日志/统计） |
| `kms-updatedel/front/src/views/distOverview/index.vue` | 分发总览（替换 iframe 分发控制台） |
| `kms-updatedel/front/src/views/keypool/index.vue` | 密钥池：生成并分发/补充/清理/删除 |
| `kms-updatedel/front/src/views/sessions/index.vue` | 会话密钥（只读） |
| `kms-updatedel/front/src/views/distlogs/index.vue` | 分发日志 |
| `kms-updatedel/front/src/views/chain/index.vue` | 区块链存证（FISCO 口径，替换 Ganache 口径的浏览器） |
| `kms-updatedel/front/src/api/pqkds/http.js` | 分发模块共用 HTTP 客户端（认 200 / 2000 两种信封） |
| `kms-updatedel/front/src/router/index.js` | 去掉重复的静态路由；仪表盘改名为 `Dashboard` 以免撞名 |
| `tools/verify-node-page.mjs` | 真浏览器验证节点管理页 |
| `tools/cdp-eval.mjs` | 在页面上下文里执行任意 JS（查"接口 200 但页面不对"） |
| `kms-ops/nodes/127.0.0.1.broken.<ts>/` | 被替换掉的旧链现场（可对比，可删） |
| `kms-ops/fisco/.rebuild/` | 本次 build_chain.sh 的原始产物 |

### 已知遗留

- **「分发控制台」「区块链浏览器」两个菜单的登录墙已消除**（第三轮，见 §5.6）：
  两者连同新增的三个分发功能页一起改成原生页面，不再 iframe 嵌 `/distribute/`。
  至此 `/distribute/` 只剩**验收测试台**那类不涉及登录的内嵌页（它是正常的）。
  分发模块自带的那个前端应用（`/distribute/`）现在**没有任何管理端入口**，
  若确认长期不用，可以考虑停止构建与投放它以省一次打包。

- **Falcon-1024 仍不可用**（镜像里没有对应 .dll），不影响 D16 默认 Kyber。
- **路由命名约定（踩过一次，记下来）**：后端按菜单 `path` 首字母大写生成路由名。
  因此**新增静态路由时，name 必须避开任何业务菜单的 path**（现在的静态路由名
  `Dashboard` / `Profile` 都不与业务 path 冲突；正是 `index` 那次撞名把仪表盘顶掉的）。
- 分发模块的节点接口**不校验身份**（见 §5.3），属于分发模块自身的问题，本次未动。
- 旧链时代的历史存证无法在新链上对账（见 §4 末尾）。
- `fisco/console/conf/config.toml` 的 peer 仍写 `127.0.0.1:20200`，
  依赖"console 与 node0 共享网络命名空间"这一 compose 约定；若将来改拓扑需同步改它。
- `nodes/127.0.0.1.broken.<时间戳>/`（被替换的 4 节点旧链，33 MB）与
  `nodes/127.0.0.1.bak.20260924094748/`（更早的单节点链备份，161 MB）
  都留在原地当现场；确认不再需要后可整体删除。
- 本次**没有提交 git**：工作区里还混着此前若干轮留下的改动，
  一并提交会把无关变更卷进来。要提交时建议按文件挑（本次涉及的文件见 §7）。