# PROJECT_PROGRESS.md — KMS 系统完善与重构（当前进度与交接）

> 快照时间：2026-10-04　分支：`v1`　HEAD：`e0ef4a1f`　仓库根：`C:/Users/AllenR/Desktop/kms-code`
> 工作区：干净 —— KMS-016 的代码与脚本已在 `e0ef4a1f` 提交；
> untracked 只剩本文（刻意不进 git）。
> **十六个任务（KMS-001 ~ KMS-016）全部关闭，八个阶段的出口检查全部闭合。
> 发布报告在 `doc/kms-release-report.md` —— 那是本轮的最终交付物，
> 后续工作的入口是它的 §5「已知限制与遗留」。**

> **交接点：全部完成。** 下面 §2~§6 是 KMS-006 的历史记录
> （仍有效，尤其 §7 的环境陷阱）。KMS-007 见 §2.6、KMS-008 见 §2.7、
> KMS-009 见 §2.8、KMS-010 见 §2.9、KMS-011 见 §2.10、KMS-012 见 §2.11、
> KMS-013 见 §2.12、KMS-014 见 §2.13、KMS-015 见 §2.14、**KMS-016 见 §2.15**。

这份文档写给**下一个 Claude Code 会话**：只读它就能接着干。它记录刚关闭的 KMS-006
是怎么收口的（改了什么、为什么这么设计、踩过哪些坑）、下一个任务从哪里起手，
以及本仓库那些会静默骗人的硬约束。
总纲仍是 `doc/kms-system-completion-and-refactor-plan.md`（现在 695 行），本文不重复计划全文。

⚠️ `doc/` 整个目录被 gitignore（`.gitignore:120`）——计划文档、总览文档**只存在于磁盘**，
`git status` 看不到它们。不要把"文档更新"算进提交完整性，也不要因为 git 里没有就以为文件不存在。

---

## 1. 总目标与当前任务

### 1.1 总目标

用户原话：「kms-system-completion-and-refactor-plan.md 按照整个计划来完善整个系统」——
让 `kms-updatedel`、`kms-distribute/dvadmin`、`kms-generate`、`kms-ops` 达到计划 §12 的九条完成判定。

计划 §13 硬性规则（第 526 行，逐字）：

> 每项任务的完成条件是：代码、测试、迁移和文档在同一变更中完成；只修改页面而没有后端约束，
> 或只增加接口而没有节点端真实调用，均不得关闭任务。

计划第 650 行（逐字）：

> 阶段出口检查失败时，不能通过修改统计口径、放宽断言或把错误状态改名来关闭阶段；
> 必须修复实现或明确记录阻塞原因。

### 1.2 当前任务：无 —— 全部完成（KMS-001 ~ KMS-016）

> 本节随任务推进更新：KMS-006 已关闭（§2~§6 历史）、KMS-007 见 §2.6、
> KMS-008 见 §2.7、KMS-009 见 §2.8、KMS-010 见 §2.9、KMS-011 见 §2.10、
> KMS-012 见 §2.11、KMS-013 见 §2.12、KMS-014 见 §2.13、KMS-015 见 §2.14、
> **KMS-016 见 §2.15**。

**八个阶段的出口检查全部闭合**（KMS-016 完成 §2.15）。最终交付物是
**`doc/kms-release-report.md`（发布报告）**：提交清单、干净环境构建记录、
验证证据汇总（十四个脚本 + 后端 17 组）、验收中修复的缺陷表、已知限制、
复现方式。后续工作的三个入口（发布报告 §5）：
1. 旧接口/旧函数体的删除（完整发布周期 + 回滚演练后，计划 §15 第 8 步）；
2. KGC 主秘密双拷贝（总览 §5.3）；
3. `admin-node-login-design.md` 实施状态章节（总览 §5.4）。

### 1.3 阶段 2 的完成判据（计划第 231-234 行，逐字）

- 更新前后 `key_id` 不变、版本递增。
- 旧版本不能被误当成当前生产版本。
- 回收后的接口返回明确错误码，如 `KEY_REVOKED`。
- 更新、回收事件能够正确进入审计和链上记录。

阶段 2 任务（计划第 220-227 行）：明确 SM2/SSCL 的部分刷新与完整轮换协议；更新时先在本地生成
并保存新版本，再登记公钥，最后切换生产版本；任一步失败不得把服务端状态标成 ACTIVE；回收时
同步禁止新分发/新签名/新预分配/新会话；为正在使用旧版本的信封和会话定义策略；补充旧版本可
恢复性检查。

阶段 2 出口检查（计划第 642 行，逐字）：**「更新、回收后的版本和状态能被所有业务入口正确识别」**。

### 1.4 KMS-006 的完成定义（按 §13 硬规则）

代码 + 测试 + 文档在**同一变更**里完成。只改页面没有后端约束、只加接口没有节点端真实调用，
都不算关闭。所以剩余工作必须包含：前端页面真实调用新契约、验收脚本以真实浏览器 + 数据库证据
跑通、两份磁盘文档（计划 §13.1 与 `doc/系统完成情况总览.md`）更新、最后提交。

---

## 2. 已完成的工作（后端 a/b/c，已验证并已提交）

✅ **下面三项都已随 `298c6c5a` 提交**，改动细节见 §4 的文件表。

### a. 修复两处损坏的 `rotate_public_key` 调用点 ✅

`tests/test_node_key_registry.py` 里有两处按老签名（"取最新一行 +1"）写的调用，改成显式
`key_id=` + `key_version=`：

- 分组三（约 276-281 行，`test_rotation_demotes_previous` 末段）
- 分组六（约 401-403 行，`test_require_usable_key_error_codes`）

两处都带注释：「更新（KMS-006）：版本由调用方显式给出，服务端不再"取最新一行 +1"」。

### b. 补 KMS-006 不变量 7-8 ✅

- `tests/test_node_key_registry.py` docstring 第 36-49 行新增「KMS-006 追加两组」小节，
  写明三条拒绝各自对应旧实现的哪一种静默坏结果；
- `rotate_public_key` 自己的 docstring（`node_key_registry.py:332-366`）同样写明
  「`key_id` 与 `key_version` 都必填」的理由与三类拒绝。

### c. 两个新测试组，并**注册进 `_main()`** ✅

- `test_rotate_requires_explicit_identity`（第 772 行起）—— 分组十一：显式身份、三类拒绝、
  被拒之后库里没有任何变化；
- `test_store_node_public_key_rotate`（第 879 行起）—— 分组十二：接口层 `rotate=True`、
  回收终态、生产槽位归属。

⚠️ **这里有一个已经踩过的坑，务必记住**：新写的测试函数若不登记进 `_main()` 的 `tests` 列表，
脚本照样打印「13 组通过」——**一次什么都不证明的通过**。它们已经登记好了（第 1088-1102 行，
共 13 项）。**任何新增测试组都必须同步注册进 `_main()`**。

### 2.4 验证证据（实测输出，不是推断）

运行方式见 §7.1。结果是：

```
== 结果：13 组通过 / 0 组失败 ==
长期密钥的登记、版本、状态与物化视图同步均符合计划 §6.1。
== 清理：已删除 13 个临时节点及其关联行（共 56 行）==
```

分组十一/十二/十三的选定输出（真实打印）：

```
更新保留 key_id、版本递增（判据①）  TESTKMS004-11-ac6908-SM2-806f3481 v1→v2
全部被拒之后：仍只有两行、生产版本还是 v2、物化视图未动  count=2 active=v2
回传 rotated=True 且 key_pk / public_key_hash 指向刚落的这一行（接口层据此补 KEY_UPDATED 存证）  pk=393
已回收的 keyId 不能更新 → KEY_REVOKED（终态）
更新一把非生产的 keyId → KEY_VERSION_MISMATCH（否则在产那把会被换掉）
被拒之后：生产版本仍是原来那把、物化视图未动、没有多出半行
登记口给已有 keyId 加版本 → 拒绝，且消息指路 rotate
已回收的 keyId 不能靠登记口复活（否则"回收是终态"只在一条路径上成立）
全部被拒之后：SM2 仍只有被回收的那一行  count=1
```

### 2.5 后端已就绪的完整契约（新会话直接照用，不必再推导）

**`rotate_public_key`（`node_key_registry.py:358-483`，`@transaction.atomic`）**

签名：`rotate_public_key(node, *, algorithm, public_key, key_id, key_version, security_level='', device_id='', effective_at=None, expires_at=None)`

校验顺序（**顺序对测试至关重要，别调换**）：

1. `_assert_registrable` → 白名单 SM2/SSCL/KYBER/FALCON；
2. 空 `public_key` → `ERR_INVALID_PARAMETER`（'公钥为空'）；
3. `_validate_key_id(key_id)` → 空白/越界字符/超长 → `ERR_INVALID_PARAMETER`；
4. 空 kid → `ERR_INVALID_PARAMETER`，文案含「不再替你推断」；
5. `_as_version(key_version)` → 非 ≥1 整数 → `ERR_INVALID_PARAMETER`，文案含「keyVersion」；
6. 该 (node, algorithm, key_id) 无任何行 → `ERR_KEY_NOT_FOUND`，文案含「无法更新」；
7. `latest.status == REVOKED` → `ERR_KEY_REVOKED`，文案含「已回收」；
8. 生产槽位归属：`active is not None and active.key_id != kid` → `ERR_KEY_VERSION_MISMATCH`，
   文案含「不是请求要更新的」；
9. 版本规则：`== latest` 通过（重试）；`== latest+1` 通过；`< latest` → `ERR_KEY_VERSION_MISMATCH`
   文案含「更旧」；`> latest+1` → `ERR_KEY_VERSION_MISMATCH` 文案含「逐版递增」。

通过后委托 `register_public_key(..., activate=True, _via_rotate=True)`：同事务里旧 ACTIVE 降级 RETIRED、
新版本置 ACTIVE、同步 `Node.<算法>_public_key`（FALCON 还写镜像列 `falcon_public_key`）。

⚠️ **`_via_rotate=True` 是那个内部标志唯一的传值点**（第 470-482 行）。不传的话登记函数会把
每一次合法更新都判成"登记口试图给已有 keyId 加版本"而拒绝 —— 它拿到的参数与那种绕过**长得
一模一样**。删它之前先读 `node_key_registry.py:263-299` 的说明和第 13 组自测。

**`register_public_key` 的登记口守卫**（`node_key_registry.py:291-299`，`ERR_KEY_VERSION_MISMATCH`）：
`kid` 非空、`_via_rotate` 为假、且该 `(node, algorithm, key_id)` 已有任何行时拒绝，
文案含「请走 rotate」。这一条拦的是"不带 rotate 却带着 keyId + 更大版本"的请求 ——
放行的话已回收的 keyId 会被复活、在产那把会被换掉，而请求返回"已登记"。

**`register_public_key` 的冲突文案**（`node_key_registry.py:231-235`，`ERR_KEY_VERSION_MISMATCH`）：

```
{name} 密钥 {kid} v{version} 已登记且公钥不同；换公钥应当走 rotate_public_key（新版本），不要同名覆盖
```

（这行就是用户点名要修的那条测试输出。`rotate_public_key` 的重试路径正是靠它区分"无操作"与"真冲突"。）

**`_as_version(raw)`（`node_key_registry.py:330-355`）**：只接受 `int` 或纯数字 `str`；
`isinstance(raw, bool) or raw is None` 直接拒；值 < 1 拒。绝不 `int()` 兜底（`int(1.9)→1`、
`int(True)→1` 都是"以为存的是 X、实际是 Y"）。

**`store_node_public_key`（`node_service.py:392-397`）**

```python
def store_node_public_key(self, algorithm, public_key, security_level=None,
                          device_id=None, key_id=None, key_version=None,
                          rotate: bool = False) -> Dict[str, Any]:
```

- `rotate and (not key_id or version is None)` → `{'success': False, 'code': ERR_INVALID_PARAMETER,
  'message': '更新（rotate）必须同时提供 keyId 与 keyVersion；节点本地已按该版本封存了新私钥，
  服务端不能另算版本号'}`（第 528-537 行）；
- `except C.ContractError` 统一收敛为 `{'success': False, 'message': exc.message, 'code': exc.code}`
  （第 574-577 行）；`except IntegrityError` 收敛为 `ERR_KEY_VERSION_MISMATCH` +「这一版刚被另一次
  请求登记了（并发更新同一版本）」（第 578-593 行）—— 不收敛的话会逃到接口层兜底 except，
  把 MySQL 的表名索引名一起回给调用方；
- `retry_same_version` 预检查（第 549-556 行）：`rotate` 且该 (node, algorithm, key_id, key_version)
  **已存在** → 这是"响应丢了之后的重试"，走幂等分支，回传的 `rotated` 必须是 False；
- 成功回传**多出三个只给接口层用**的字段（不会进 HTTP 响应）：`key_pk`（`NodeLongTermKey` 整数主键）、
  `public_key_hash`、`rotated`（第 626-642 行），其中 `rotated` 是
  `bool(rotate) and not retry_same_version`（第 642 行）。消息三选一（第 610-618 行）：
  重试 → `... 公钥已是 vN，本次未做改动（上一次更新已经生效）`；rotate →
  `... 公钥已更新为 vN`；否则 → `... 公钥已登记`。

**`_as_bool(value, field='rotate')`（`node_self_views.py:114-140`）**：严格解析，不做真值猜测。
认 `True/False`、`0/1`（int/float）、`'true'/'false'/'1'/'0'`（去空白、忽略大小写）；`None`/`''` → False；
**出现过但认不出的值 → `ERR_INVALID_PARAMETER`**，文案 `f'{field} 应为布尔值（true/false），收到 {value!r}'`。

**HTTP 入口（`node_self_views.py:311-335`, `node_self_keys`）**：body 字段为驼峰 `algorithm` /
`publicKey` / `securityLevel` / `deviceId` / `keyId` / `keyVersion` / `rotate`（各带 snake_case 兜底）。
⚠️ `key_version=payload.get('keyVersion', payload.get('key_version'))` 刻意用 `.get(..., default)`
而不是 `or` —— 用 `or` 会把 `keyVersion: 0` 吞成"没提供"，服务端静默按 v1 登记。

**链上事件（判据④，`node_self_views.py:354-376`）**：`record_chain_event(event_type, key_id:int,
version=0, node_id='', public_material_hash='', timeout=12)` POST 到
`{KMS_LIFECYCLE_BASE}/internal/lifecycle/chain/event`，返回 tx 哈希；**任何失败都返回 None，从不抛出**。
触发点在原子块**提交之后**，仅当 `if result.get('rotated')`；响应字段名 `chainHash`（第 390 行），
拿不到时是 `''`（页面据此如实说"已更新，但存证未成功"，审计缺口必须可见）。
Java 端只接受 KEY_CREATED/KEY_UPDATED/KEY_REVOKED/KEY_DISTRIBUTED 且 `keyId` 必须是**整数** ——
所以传的是 `int(result.get('key_pk') or 0)`，不是字符串 `key_id`。KEY_CREATED/KEY_REVOKED 有意推迟到
KMS-014/KMS-007，KMS-006 只补 KEY_UPDATED。

**响应约定**：`_ok(data, msg)` → `{'code': 200, 'msg': ..., 'data': ...}`；
`_error(msg, code=400, error_code=None)` → `{'code','msg','data':{'error_code'}}`，**HTTP 恒 200**。
调用方必须看 `code`，不能看 HTTP 状态。

**错误码（`api_contract.py`，逐字，无需再查）**：`ERR_KEY_NOT_FOUND='KEY_NOT_FOUND'`(286)、
`ERR_KEY_REVOKED='KEY_REVOKED'`(287)、`ERR_KEY_EXPIRED='KEY_EXPIRED'`(288)、
`ERR_KEY_VERSION_MISMATCH='KEY_VERSION_MISMATCH'`(289)、`ERR_KEY_LOCAL_MISSING='KEY_LOCAL_MISSING'`(290)、
`ERR_ALGORITHM_NOT_ALLOWED`(291)、`ERR_SIGNATURE_INVALID`(292)、`ERR_SIGNATURE_REQUIRED`(293)、
`ERR_ENVELOPE_TAMPERED`(294)、`ERR_ENVELOPE_EXPIRED`(295)、`ERR_ENVELOPE_NOT_FOUND`(296)、
`ERR_NOT_ENVELOPE_RECIPIENT`(297)、`ERR_SESSION_NOT_FOUND`(298)、`ERR_SESSION_STATE_INVALID`(299)、
`ERR_SESSION_TERMINAL`(300)、`ERR_PROOF_MISMATCH`(301)、`ERR_NOT_SESSION_PARTY`(302)、
`ERR_NOT_AUTHORIZED`(303)、`ERR_DEVICE_MISMATCH`(304)、`ERR_POOL_ITEM_CONSUMED`(305)、
`ERR_POOL_ITEM_RESERVED`(306)、`ERR_POOL_ITEM_UNAVAILABLE`(307)、`ERR_INVALID_PARAMETER='INVALID_PARAMETER'`(308)。

### 2.6 KMS-007「完成回收影响处理」——已关闭（`fab29538`）

**任务**：计划 §13 第 515 行，前置 KMS-006，产出「回收闭环」。对应 §7 阶段 2 的
判据③（回收后接口返回明确错误码）与④（回收事件进审计与链上）。

**回收真正的入口原本不在 A 链上**：节点侧「密钥回收」菜单（`keydelete`）删的是
updatedel 旧 `keymanage` 行，`NodeLongTermKey` 原样不动 —— 与 KMS-006 之前的更新页
问题同源。本次把三个页面（`keydelete`/`userKeys`/`keyVersionHistory`）改到
`/node-self/keys/`，B 链端点保留但不再是落点。

**新增/改动**（18 个文件，`git show --stat fab29538`）：

| 文件 | 改了什么 |
|---|---|
| `pqkds/key_revocation_service.py`（新建） | 编排：撤长期密钥 → 失效池项 → 失效会话 → 汇总影响面。**不包外层事务**，每步可重入；刻意不在「已是 REVOKED」时提前 return（否则半成品永久固化） |
| `pqkds/node_key_registry.py` | `revoke_public_key` 返回值补影响面信息 |
| `pqkds/node_self_views.py` | 新端点 `POST /node-self/keys/revoke/`（显式 keyId+keyVersion）；`KEY_REVOKED` 链上事件在事务**提交后**补发，仅当 `not alreadyRevoked` |
| `pqkds/key_pool_service.py` | `revoke_pool_items_for_key` 精确化（改前**只按 node 匹配**，key_id/version 只出现在日志里）；预分配创建时回填两列；三处 `require_usable_key` 闸门 |
| `pqkds/node_session_views.py` | 取信封前按**这批信封实际用到的算法**逐个判（不判"节点名下所有算法"） |
| `pqkds/user_distribution_views.py` | 节点腿封装前 + FALCON 签名前各一道闸门 |
| `pqkds/models.py` + `migrations/0017` | `PreDistributedKey` 补 `long_term_key_id` + `long_term_key_version`；历史 NULL 行**刻意不回填**（猜一个 key_id 比留空更糟） |
| `kms-updatedel/front/tools/verify-keyrevoke-impact.mjs`（新建） | 验收脚本，**82/82** |
| `tests/test_node_key_registry.py` | 第 14 组「回收影响面」，已注册进 `_main()`（14 组通过） |

**`require_usable_key` 改前生产调用点为 0** —— 函数写好了、单测钉住了，但没有任何
业务入口调用它，四入口一律直接读物化列。本次五个门接上：

| 入口 | 调用点 |
|---|---|
| ① `GET /node-self/envelopes/` | `node_session_views.py:154-166`（判这批信封用到的算法，`error_code` 在 `data`） |
| ② distribute-to-user（节点腿） | `user_distribution_views.py:786-794`（失败进 `failed[]`，批次记 partial） |
| ③ `POST /key-pool/generate/` | `key_pool_service.py:219`（判 node2，码写进 **message 文本**） |
| ④ `POST /key-pool/distribute/` | `key_pool_service.py:734`（判 **sender**） |
| ⑤ FALCON 签名闸门 | `user_distribution_views.py:670-676`（真 HTTP 409；**只在 `falcon_sign_private_key` 非空时才判**） |

**三个响应约定并存**（写断言时别搞混）：`/node-self/*` 恒 HTTP 200、码在
`body.data.error_code`；`/key-pool/*` 恒 HTTP 200、**没有错误码字段**、只在 `msg`
文本里；`distribute-to-user` 用真 HTTP 状态码（KEY_REVOKED → 409，码在 `message`）。

**⚠️ 补证据时新发现一处既有断口（不属本次改动面，已如实记录未越界修）**：
`user_distribution_views` 的签名路径把签名写进信封，但
`envelope_signature.SIGNED_FIELDS` 里另外五个字段（`batch_id`/`source_key_id`/
`recipient_user_id`/`wrapping_algorithm`/`expires_at`）**从没随信封落库** →
验签侧从库里重建被签字节串时它们全是 `None` → **自己签的信自己验不过**。
影响面：`GET /user-symmetric-keys/<id>/` 先验签再交密文，于是 403「拒绝交出密文」。
引入点是阶段 5 的 `94754d07`。脚本里用两条断言钉住（断口仍在时绿、被修好后立即红），
**修复归 KMS-010/011**（要决定"信封该冗余存哪些字段"这类契约问题）。

**链上回读怎么做**（KMS-008 之后若要读链，直接照用）：直连
`http://127.0.0.1:8545`（compose 只绑回环）的 FISCO JSON-RPC。`getPastLogs`
**不支持**（实测 `METHOD_NOT_FOUND`），所以按块遍历 `getBlockByNumber(groupId, '0xN', true)`
→ `getTransactionReceipt(groupId, hash)`。事件 `KeyLifecycleEvent` 的
`topics[0] = 0x22de7361…`（签名哈希，与地址无关），`keyId` 在 `topics[1]`（**不进 data**），
data 里依次是 eventType / version / nodeId / materialHash / timestamp 的 ABI 编码。
合约地址 = `kms-ops/.env` 的 `FISCO_CONTRACT_ADDRESS`（脚本里写成**常量**，不从被测
系统读——那等于让它自证清白）。

**验收实测**：`verify-keyrevoke-impact` **82/82**；`verify-keyupdate-rotate` **48/48**
（无回归，其第 7 节已从"回收全仓没有 HTTP 入口"改写为走真实回收入口）；
后端 `tests/test_node_key_registry.py` **14 组通过 / 0 组失败**；清理 `left=0`。

**KMS-008 起手线索**：计划 §13 第 516 行「重构分发请求模型」…… 已由 §2.7 完成。

### 2.7 KMS-008「重构分发请求模型」——已关闭（`615907b4`）

**交付的是新契约**（计划 §13 第 516 行，产出「新请求契约」）：分发从**用户腿**
（发起人选一把"我的解封密钥"，服务端给用户本人也封一份）改为**节点到节点**
（发送节点取**接收方指定版本**的公钥封 SM4，没有用户那一份）。

**两条新端点**（§16 契约，都在 `/node-self/*`，即 HTTP 恒 200 + `data.error_code`）：

| 端点 | 要点 |
|---|---|
| `GET /node-self/peers/<业务编号>/keys/?algorithm=SM2,SSCL,KYBER` | 复用 `node_self_views._long_term_key_payload` 的形状；**必须对 peer 有授权**否则 403 + `NOT_AUTHORIZED`；**不过滤状态**（页面要能显示"已被取代/已回收"），能不能用由 `allowsNewWork` 回答 |
| `POST /node-self/distributions/` | 请求体 `{receiverNodeId(业务编号), protectionAlgorithm(SM2/SSCL/KYBER 规范名), recipientKeyId, recipientKeyVersion, expiresInHours?}`；**不收 `source_key_id`**（传了也忽略，库里是 NULL）；需要 映射到节点 + `CAP_DISTRIBUTE` + 对接收方有授权 |

**⚠️ 两条端点收的是节点业务编号（`Node.node_id`），不是主键** ——
与 `/user-nodes/` 回的 `nodeId`（主键）不同。混了的表现是"节点明明在，接口说它不存在"。

**本次实质性的修复**：`require_key_version(node, algorithm, key_id, key_version)`
（`node_key_registry.py`）把"指定的那一版"变成**先于封装发生**的一次查询。
改前 `wrap_for_node` 读节点**物化列**（"当前生产公钥"），请求里带了版本也传不进
封装调用 —— "用户选了 v1、实际用 v2 封的"，而每一处都成功。四种拒绝：
`KEY_NOT_FOUND` / `KEY_REVOKED` / `KEY_EXPIRED` / `KEY_VERSION_MISMATCH`（RETIRED，
即判据②「旧版本不能被误当成当前生产版本」）。`for_new_work=False` 时 RETIRED 仍放行
（解旧信封那条路不能被砍）。

**结构**：新增 `pqkds/distribution_service.py`（编排层，不出 HTTP 就能被测）；
`create_initiated_sessions` / `record_distribution_chain_event` /
`classify_distribution` / `authorized_node_ids` 四条共用助手从视图层**搬进**
服务层（不搬就是"服务反向 import 视图、视图又要 import 服务"的循环前身）。
`wrappers.wrap_for_node` 拆成"读物化列 → 调 `wrap_with_public_key`"，后者是
节点腿封装的**唯一实现**；顺手删掉 `falcon_lattice` 死分支（已被白名单排除）。

**迁移 0018**（纯结构）：`DistributionBatch.source_key_id` 改可空；
`SessionKey.session_type` 的 choices 补 `gm_sm2`/`gm_sscl`（该字段以
`protectionAlgorithm` 的名义下发，旧流程一律写 kyber_kem 是既有失真）。

**如实记录的两条过渡缺口**（都不是本次能决定的）：

1. **新批次不进泄漏分析**：`source_key_id` 为 NULL，而主 KMS 的
   `LifecycleService` 按该列反查分发足迹。新流程的关联键是接收方那一版长期密钥
   （`PreDistributedKey.long_term_key_id/version`）—— 那条查询要一起改，归 **KMS-014**。
2. **信封暂时没有签名**：私钥只在节点本地（KMS-005 起服务端不再持有），
   信封里没有签名字段。**不装作已签**。归 **KMS-009/010**。

**验收**：`verify-node-distribution.mjs` **56/56**（核心判据是真往返：用**指定的
那一版**私钥解得开、用**另一版**解不开）；`verify-keyrevoke-impact` 82/82、
`verify-keyupdate-rotate` 48/48 无回归；后端 **15 组**通过；前端产物三重 md5 一致。

**本次**没做**的（KMS-009 的边界）**：服务端仍生成 SM4 并封装（**过渡实现**，
但按显式版本）—— 把它搬到节点侧、加 Falcon 签名，就是 KMS-009（见 §2.8）。

### 2.8 KMS-009「实现节点本地封装和 Falcon 签名」——已关闭（`82950ce8`）

**交付**：阶段 3 的后三条落地。KMS-008 时 SM4 生成与封装还在服务端（过渡实现），
本次全部搬到**发送节点的浏览器**里：

| | 谁做 | 落在哪 |
|---|---|---|
| 生成 16 字节 SM4 | 发送节点 | `envelope-signing.js` 的 `generatePayloadKey` |
| 用接收方**指定版本**公钥封装 | 发送节点 | `provider.wrapForPeer`（KYBER/SM2/SSCL 三条腿） |
| 用本地 Falcon 私钥签名 | 发送节点 | `signEnvelopePayload`（走 `provider.sign`） |
| 核形状、算摘要、落库 | 服务端 | `distribution_service.create_node_distribution` |
| **验签** | —— | **KMS-010**（`verify_node_envelope` 已写好但无生产调用点） |

于是服务端**从头到尾拿不到 SM4 明文**（计划 §2.1）。

**签名覆盖 `NODE_ENVELOPE_SIGNED_FIELDS`**（收发节点、保护算法、接收方 keyId
与版本、密文摘要、载荷密钥哈希、**批次号**、**有效期**）—— 两份实现必须逐字
相同：服务端 `envelope_signature.node_canonical_payload`、浏览器
`utils/crypto/envelope-signing.js`。序列化口径 = **键排序 + 无空白**紧凑 JSON。

⚠️ **因为签了 batchId 与 expiresAt，两者必须由页面给出**（KMS-008 时是服务端
赋值）。服务端仍强制**形状与上界**：批次号正则 `dist-\d{14}-[0-9a-f]{8}`、
有效期不得已过期且 ≤168 小时。批次号撞唯一约束时转成 `INVALID_PARAMETER`
（可重试的业务冲突，不是 500）。

**三个实测踩中的坑**（都会被报成与实现无关的错误，务必记住）：

1. **登记表里的 Falcon 公钥是 hex，不是 base64**：`NodeLongTermKey.public_key`
   是 1794 字符的 hex（897 字节），而用户腿的 `falcon_sign_public_key` 是 base64。
   照抄 `_decode_b64` 会**永远验不过**且不报编码错（4 的倍数时解出等长错字节 →
   "签名无效"；否则抛异常被吞 → 还是 False）。修法：
   `_decode_registry_key_material` 按**形状**认编码。
2. **`USE_TZ = False`**（`application/settings.py`）：`timezone.now()` 是**朴素**
   时间。`make_aware` 之后比较抛 `can't compare offset-naive and offset-aware
   datetimes` → 500（像服务端坏了）。要 `make_naive`。
3. **gm-crypto 的 `encrypt` 只收 ArrayBuffer，不收 Uint8Array**（它判
   `instanceof ArrayBuffer`，而 Uint8Array 是视图）。要 `Uint8Array.from(key).buffer`。

**验收**：`verify-node-distribution.mjs` **72/72**（KMS-008 的 56 条 + 本次新增）。
新增判据都能证伪：库内密文与节点产出**逐字相同**（服务端若还自己封必然不同）、
**跨语言验签通过**（服务端那份规范实现重建字节串）、把被签字段改一个就**验不过**、
不带签名 → `SIGNATURE_REQUIRED`、摘要被改 → `ENVELOPE_TAMPERED`。
82/82、48/48、后端 15 组均无回归；前端产物三重 md5 一致。

⚠️ **阶段 3 出口检查的后半句仍判不了**：「Falcon 缺失时不能发送」现在的实现是
"没有签名就拒收"，但**验签还没做** —— 所以"这把 Falcon 不可用"目前只能靠
"没有签名"表达。补完它是 KMS-010。

### 2.9 KMS-010「实现服务端验签与信封登记」——已收口（阶段 3 就此闭合）

**交付**：`verify_node_envelope` 接进生产路径 + 请求契约补签名者版本 +
修掉用户腿断口。阶段 3 出口检查的两句从此刻都成立。

| 改动 | 落点 |
|---|---|
| 验签接入（摘要检查**之后**、落库之前） | `distribution_service.create_node_distribution` |
| 签名者那一版（`falconKeyId` / `falconKeyVersion`）显式进请求 | 同一处 + `node_self_views` + 分发页 + 验收脚本 |
| 响应回 `signatureVerified` + 验签实际用的版本 | `node_self_views.node_self_distributions` |
| 被签字段随用户腿信封落库（修 KMS-007 记录的断口） | `user_distribution_views` 的签名段（`sign_fields` → `user_envelope.update`） |
| 公钥解码按**形状**认（hex/base64，第二层原因） | `envelope_signature._decode_falcon_public_key` |

**请求契约**（§16.2 更新）：`POST /node-self/distributions/` 新增
`falconKeyId` / `falconKeyVersion`。服务端用
`require_key_version(sender, 'FALCON', …)` 查**那一版**公钥 —— 不按"当前生产
版本"猜（并发轮换时会验到另一把上，报成 `SIGNATURE_INVALID` 而像伪造）。
四种版本类拒绝原样透出：`KEY_NOT_FOUND` / `KEY_REVOKED` / `KEY_EXPIRED` /
`KEY_VERSION_MISMATCH`（已回收的签名密钥不能发新信）。

**两种检查的顺序是契约**（改之前先读注释）：摘要自洽（`ENVELOPE_TAMPERED`）
在验签（`SIGNATURE_INVALID`）**之前**。「序列化口径漂移」与「伪造」处置不同，
顺序反了会让前者全部伪装成安全事件。

**实测**：`verify-node-distribution` **80/80**（新增 §4.1 四条 + §9.5 两条）、
`verify-keyrevoke-impact` **84/84**（断口修复 + 取件口交密文）、
`verify-keyupdate-rotate` **48/48** 无回归、后端 **16 组通过 / 0 组失败**
（第 16 组用真 Falcon/Kyber 走完整签发验，含"库内信封能被接收方私钥解开"）。

**两个新踩实的坑**（roadmap §8 已收录）：
1. **用户腿断口有第二层原因**：把五个被签字段落库之后取件口**仍然 403** ——
   `Node.falcon_sign_public_key` 在真节点上是 **hex**，而
   `_decode_falcon_public_key` 只按 base64 解（1794 % 4 == 2，异常被吞 →
   验签恒 False）。已改成按形状认编码（与 KMS-009 在节点腿的修法同一套）；
2. 后端自测第 16 组要落 `DistributionBatch`（`user_id` 非空 = `Node.sys_user_id`），
   夹具节点必须带 `sys_user_id`；`_make_node` 加了 `with_user` 形参，且随机值
   取——那一列有唯一约束，固定值会在同一次运行里撞键。

⚠️ **`open_node_envelope` 的变体判定是坏的**（既有，未修也不属本条线）：
它按 `len(node_sk)` 查 `{32: 512, 64: 768, 128: 1024}` —— 那三组键是**共享秘密**
长度，私钥长度（1632/2400/3168）一个都不在里面，于是恒取 512，再用 768 的私钥
去 `decrypt` 直接抛"Invalid secret key length"。要解节点腿信封就照
`test_node_key_registry` 第 16 组那样自己按 `pk_len_map` 定变体（或等 KMS-011
把节点侧解封做正）。

### 2.11 KMS-012「实现双方确认和 established 状态机」——已收口（阶段 4 闭合）

**交付**：`confirm` 接入状态机、`close` 端点、本地会话密钥库、双方确认数。
阶段 4 出口检查「两个真实节点能将 initiated 提升为 established」闭合。

| 改动 | 落点 |
|---|---|
| `confirm` 走 `SESSION_TRANSITIONS`（经 `_maybe_establish`） | `node_session_views.py`（唯一合法边 `key_recovered → established`；四态回报 waiting/mismatch/state/established） |
| `recover` 后补一次"尽力而为"的提升 | 同文件（确认可先交，证据齐的一刻自动兑现；失败只记日志） |
| `POST /node-self/sessions/<sid>/close/` | 同文件 + `urls.py`（终态、重复幂等、非会话方 403） |
| **契约变更**：`closed` 从每个非终态可达 | `api_contract.SESSION_TRANSITIONS`（理由写在表上方；连带 `node_session_close` 的 allow_from） |
| 会话列表 `confirmedCount` | `node_sessions`（一条聚合查询，不 N+1） |
| 分发响应 `sessionId` / `sessionStatus` | `distribution_service` + `node_self_views`（发起方据此存 K 并确认） |
| 本地会话密钥库（IndexedDB v4 `sessionKeys`） | `node-key-store.js`（同一把不可导出保护密钥；`sealSessionSecret` 等五个函数） |
| 会话页「确认」「关闭」+ `x/2` 列；分发页存 K | `selfSessions/index.vue`、`distribute/index.vue`、`node-self.js`（`closeSelfSession`） |

**三条设计口径**（改之前先读注释）：
1. **提交与建立解耦、建立受证据门限**：proof 随时可交（顺序独立），
   但提升只在 `key_recovered → established` 这条边上发生；
2. **改 `SESSION_TRANSITIONS` 前先问"这条边会不会让人相信没验证过的属性"** ——
   `closed` 可以放开（不产生信任主张），`established` 不能；
3. 关闭的本地清理顺序：**先服务端关闭、后删本机副本**（反过来一旦失败，
   本机算不出 proof 而会话还活着）。

**实测**：`verify-envelope-recover` **56/56**（41 → 56：新增"先交确认不误建"、
"证据不齐 blockedBy"、"双方各持不同 K → PROOF_MISMATCH"、"关后确认
SESSION_TERMINAL"、"重复关闭幂等"、"非会话方关闭 403"、分发回执带会话 ID）、
`verify-node-distribution` 80/80、`verify-keyrevoke-impact` 84/84、
`verify-keyupdate-rotate` 48/48、后端 16 组通过 / 0 组失败；
前端产物三重核对（489 个 asset，磁盘 = 容器内 = HTTP md5 一致）。

**施工中实测到、归 KMS-013 的断口**（roadmap §4 有复现命令）：
`KeyPoolService.consume_key` 里 `POOL_STATUS_READY_VALUES` 是**裸名**
（它是类属性）→ `NameError`；修掉后还会撞 `select_for_update` 无外层事务的
`TransactionManagementError`。即 `/key-pool/consume/` **从未成功跑通过**。
**→ KMS-013 已修（`4cb1388f`）：除这两条外，还发现原 `atomic()` 的边界只包
"标记"几行、选中与标记之间锁已释放 —— 并发会拿到同一条 READY 行并各自
返回成功。见 §2.12。**

### 2.12 KMS-013「重构预分配和池项消费」——已收口（阶段 5 闭合）

**交付**：`consume_key` 两层断口修复 + `RESERVED` 定夺 + 消费前置复核
（识破即纠正、跳过继续取）+ 口径收口到 `api_contract` + 池页面如实化。
阶段 5 出口检查「池项不能重复消费；密钥版本失效会阻止消费」闭合。

| 改动 | 落点 |
|---|---|
| 常量派生 + 状态机/别名表（单一出处） | `api_contract.py`（`POOL_TRANSITIONS` / `POOL_LEGACY_STATUS_ALIASES` / `normalize_pool_status` / `pool_transition_allowed`；`KeyPoolService` 常量改为从它派生） |
| `consume_key` 重写：单事务包整个临界区、`skip_locked` 显式形参、识破即纠正 + 跳过、拒绝时带错误码 | `key_pool_service.py`（docstring 记两层断口、事务边界为什么必须宽、`MAX_PROBE=64`） |
| 统计/补货/列表清理/`cleanup_expired` 换同一套符号名 | 同文件 + `views.py`（`KeyPoolViewSet.get_queryset` / `consume` 动作把 code 写进 msg） |
| 列表新数据：`effective_status` / 长期密钥引用 / 消费情况与消费会话 | `serializers.py`（`effective_status` 是 SerializerMethodField；`used_by_session_id` 必须显式声明，它是 attname 不是 DRF 字段名）+ `views.py` 的 `.only()` 补列 |
| `RESERVED` 文案如实化、`distributed` 标注历史别名身份 | `models.py` + 迁移 `0020_pool_status_reserved_label`（纯 choices，无 DDL、不写数据） |
| 池页面两列 + 五读数 + 部分完成提示 | `views/keypool/index.vue`（路由 `/distzone/selfpool`，由 sys_menu 下发给**普通角色**；admin 看的是另一个页 `poolgov`） |

**三条设计口径**（改之前先读注释）：
1. **事务边界必须包住"选中 + 标记"整个临界区**：只包标记那几行等于没锁 ——
   并发下两个请求拿到同一条 READY 行、各自标记、各自返回成功；
2. **复核不过时的动作是"识破即纠正 + 跳过继续取"**，不是"拒绝"：只拒绝时
   一条死件（标记漏网、key_index 最小）会**毒化整个节点对**；就地标 REVOKED
   用的是与回收路径**同一判据**（登记行已 REVOKED）的迟到应用，不是另写策略；
   全部不可用才按 `KEY_REVOKED` 拒（处置是重新预分配）；
3. **不猜"哪个节点是收件方"**：单向池（`pool_dist_*`）封给发送方自己、
   节点间池封给 node2，同是 `kyber_kem` 在行上分不出来 —— 只看池项自带的
   `long_term_key_id/version` 引用。

**实测**：后端 `tests/test_node_key_registry.py` **17 组通过 / 0 组失败**
（第 17 组：断口复现、状态机表、旧拼写、过期两处同判、识破即纠正+跳过+
正对照、等锁路径真等待）；`verify-pool-consume` **45/45**（新增：部署探针、
**真并发 8 子进程 8 取 3 → 恰好 3、8 取 1 → 恰好 1**、脱敏的撤密钥链、
清理口径、吞吐 100→969 / 1000→2933 条/s）；`smoke-pool-page` **7/7**
（新增，真浏览器 + 节点令牌）；48/48、80/80、56/56、84/84 无回归；
前端产物三重核对（489 asset）。

**三个新踩实的坑**（roadmap §4 末尾已收录）：
1. **列表端点加载时会自动清理过期未用行** —— 验收脚本"先读列表、后消费"
   的顺序会把夹具行删掉，两组断言一起读到 null（判据的顺序是判据的一部分）；
2. **刷新夹具行走容器内 ORM**（与 KMS-011 的做法一致），不要用列表接口的
   副作用来做；
3. `/key-pool/*` 的 `get_permissions` 返回空列表是既有事实；consume 现在
   真的能消费密钥了，该端点的鉴权归 **KMS-014**（已如实记录未越界改）。
   KMS-008 记录的"新批次不进泄漏分析"（按 `long_term_key_id/version` 反查）
   也一并归 KMS-014。

---

### 2.10 KMS-011「实现接收节点取信封和本地解封」——已收口

**交付**：三条新端点 + 会话行四列版本引用 + 接收端前端全流程。
`recipient_verified` / `key_recovered` 两个状态**首次有了写入点**。

| 改动 | 落点 |
|---|---|
| 会话行四列（接收密钥 + 发送方 Falcon 的 keyId/version） | `models.py` + 迁移 `0019`；写入点在 `distribution_service.create_initiated_sessions`（新旧两条路径都写） |
| `POST /node-self/sessions/<sid>/versions/` | `node_session_views.node_session_versions`（只回接收方；越权 403 `NOT_SESSION_PARTY`） |
| `POST /node-self/envelopes/<id>/verify/` | 同文件：回执 + **服务端独立复核**（摘要自洽在前）→ `recipient_verified` |
| `POST /node-self/envelopes/<id>/recover/` | 同文件：回执 → `key_recovered`，响应注明"这是节点声明" |
| 接收端密码学（验签/解封/自查/HMAC） | 新模块 `utils/crypto/node-envelope.js` |
| 会话页「处理」全流程 | `views/selfSessions/index.vue`（逐步记录，失败停在那一步） |
| API 层五个封装 | `api/pqkds/node-self.js`（`listSelfEnvelopes` / `getSessionVersions` / `verifyEnvelope` / `recoverEnvelope` / `confirmSelfSession`） |

**三条设计口径**（改之前先读注释）：
1. **顺序由 `SESSION_TRANSITIONS` 强制** —— `_advance_session` 查表，
   `initiated → key_recovered` 直跳给 `SESSION_STATE_INVALID`；幂等由
   **端点自己**判（"已在目标状态"与"已越过目标"都回 ok + `advanced=false`，
   状态只增不减），**不要**给状态机表加"回退"边；
2. **verify 端点做服务端独立复核**：不信节点的"我验过了"，服务端用会话记录
   的发送方版本自己再验一次；**recover 无法复核**（服务端没有 K），
   响应里如实标注，真正的锚是双方 proof；
3. **两版密钥的 keyRef 由服务端下发的版本引用来拼**，页面不猜 ——
   `node_session_versions` 还归一化了 Falcon 公钥（小写 hex）。

**实测**：`verify-envelope-recover` **41/41**（新增）、`verify-node-distribution`
80/80、`verify-keyrevoke-impact` 84/84、`verify-keyupdate-rotate` 48/48、
后端 16 组通过 / 0 组失败；前端产物三重核对（489 个 asset，HTTP md5 一致）。

**三个新踩实的坑**（roadmap §2 末已收录）：
1. 不要用 js 拼 SQL 改库内信封做篡改夹具（JSON 引号多，转义错一次 = 测了个
   没改动的请求）；在容器里用 ORM 改 + 恢复；
2. 确认表的 `session_id` 是**外键**（指向 `SessionKey` 主键），按业务字符串查
   恒 0 行——看起来像"确认没写进去"；
3. 夹具节点要登记**四套**密钥才能过 `/node-self/init/`（它校验四套齐备）。

### 2.10 KMS-011「实现接收节点取信封和本地解封」——已收口

**交付**：三条新端点 + 会话行四列版本引用 + 接收端前端全流程。
`recipient_verified` / `key_recovered` 两个状态**首次有了写入点**。

| 改动 | 落点 |
|---|---|
| 会话行四列（接收密钥 + 发送方 Falcon 的 keyId/version） | `models.py` + 迁移 `0019`；写入点在 `distribution_service.create_initiated_sessions`（新旧两条路径都写） |
| `POST /node-self/sessions/<sid>/versions/` | `node_session_views.node_session_versions`（只回接收方；越权 403 `NOT_SESSION_PARTY`） |
| `POST /node-self/envelopes/<id>/verify/` | 同文件：回执 + **服务端独立复核**（摘要自洽在前）→ `recipient_verified` |
| `POST /node-self/envelopes/<id>/recover/` | 同文件：回执 → `key_recovered`，响应注明"这是节点声明" |
| 接收端密码学（验签/解封/自查/HMAC） | 新模块 `utils/crypto/node-envelope.js` |
| 会话页「处理」全流程 | `views/selfSessions/index.vue`（逐步记录，失败停在那一步） |
| API 层五个封装 | `api/pqkds/node-self.js`（`listSelfEnvelopes` / `getSessionVersions` / `verifyEnvelope` / `recoverEnvelope` / `confirmSelfSession`） |

**三条设计口径**（改之前先读注释）：
1. **顺序由 `SESSION_TRANSITIONS` 强制** —— `_advance_session` 查表，
   `initiated → key_recovered` 直跳给 `SESSION_STATE_INVALID`；幂等由
   **端点自己**判（"已在目标状态"与"已越过目标"都回 ok + `advanced=false`，
   状态只增不减），**不要**给状态机表加"回退"边；
2. **verify 端点做服务端独立复核**：不信节点的"我验过了"，服务端用会话记录
   的发送方版本自己再验一次；**recover 无法复核**（服务端没有 K），
   响应里如实标注，真正的锚是双方 proof；
3. **两版密钥的 keyRef 由服务端下发的版本引用来拼**，页面不猜 ——
   `node_session_versions` 还归一化了 Falcon 公钥（小写 hex）。

**实测**：`verify-envelope-recover` **41/41**（新增）、`verify-node-distribution`
80/80、`verify-keyrevoke-impact` 84/84、`verify-keyupdate-rotate` 48/48、
后端 16 组通过 / 0 组失败；前端产物三重核对（489 个 asset，HTTP md5 一致）。
（KMS-012 已把该脚本扩到 56/56，见 §2.11。）

**三个新踩实的坑**（roadmap §2 末已收录）：
1. 不要用 js 拼 SQL 改库内信封做篡改夹具（JSON 引号多，转义错一次 = 测了个
   没改动的请求）；在容器里用 ORM 改 + 恢复；
2. 确认表的 `session_id` 是**外键**（指向 `SessionKey` 主键），按业务字符串查
   恒 0 行——看起来像"确认没写进去"；
3. 夹具节点要登记**四套**密钥才能过 `/node-self/init/`（它校验四套齐备）。

### 2.13 KMS-014「补齐权限、审计和链上事件」——已收口（阶段 6 闭合）

**交付**：三个会话事件上链 + 五态轨迹落库 + 两个命名空间收口 + 泄漏分析
按版本追踪 + 修掉审计中间件的覆盖缺陷。阶段 6 出口检查闭合。

| 改动 | 落点 |
|---|---|
| Java：三个事件常量、白名单扩到七个、消费者显式只留痕 | `ChainSyncEvent.java`、`InternalLifecycleController.java`、`UpdatedelChainConsumer.java` |
| PQKDS 三处发出（verify / `_maybe_establish` / close），只在其真推进时发 | `node_session_views.py`（`record_session_chain_event`；口径同 KEY_DISTRIBUTED） |
| 五态轨迹列（每步 `{at,tx}`；recovered 无链上事件） | `models.py`（`lifecycle_evidence` + `record_evidence`/`evidence_state`）+ 迁移 `0021` |
| 五态下发与显示 | `serializers.py`（`SessionKeySerializer.evidence_state`）+ `views/sessions/index.vue` |
| `/key-pool/*` 三档闸门（`_pool_actor`，`initial()` 统一执行、兜底最严档） | `views.py`；池页按主体隐藏维护按钮（`keypool/index.vue`） |
| `/session-keys/` list/retrieve 移出匿名名单（introspect 链，非 DRF IsAuthenticated） | `views.py` |
| 泄漏分析按节点长期密钥版本追踪（新入口，仅管理员）+ 页面标识空间切换 | `LifecycleService`、`LifecycleKeyController`、`lifecycle.js`、`keyLeakAnalysis/index.vue` |
| **审计中间件覆盖缺陷修复**（id 从中间件实例挂到 request） | `dvadmin/utils/middleware.py` |

**四条设计口径**（改之前先读注释）：
1. **只在其真的推进那一步时上链**（advanced=True）——重复回执/关闭不重复写，
   与 KMS-007 对回收的口径一致；
2. **五态刻意不从 status 反推**：关闭后 status 只剩 `closed`，反推会静默丢轨迹
   —— 判据就是"关闭后五态仍全为 true"（`verify-governance` §4）；
3. **RuoYi 令牌不是 DRF 的 JWT**：给 ViewSet 收紧权限用 `introspect` 链，
   别用 `IsAuthenticated`（实测会把管理员一起挡住）；
4. **审计行 id 挂 request 不挂中间件实例**：函数视图的响应否则会
   `update_or_create` 到上一个请求的行上**覆盖别人的审计记录**。

**实测**：`verify-governance` **49/49**（新增：三个事件直连 JSON-RPC 逐字段
回读且 tx=响应 chainHash、五态关闭后仍完整、越权三条可编程码 + 正对照、
篡改 `ENVELOPE_TAMPERED`、拒绝在 `operation_log` 留痕、终态拒绝、泄漏分析
四类关联面 + 空 keyId 正对照 + 非管理员被拒）；45/45、84/84、56/56、80/80、
48/48 无回归；后端 17 组通过；smoke 7/7；前端产物三重核对（489 asset）。

**四个新踩实的坑**（roadmap §5 末尾已收录）：
1. 先改 Java 白名单再加发布侧（反了 = "存证没成功"且只看得到 Java 日志）；
2. `json_result` 存的是 code+msg **文案**，不是 `data.error_code` ——
   审计断言按错误码 LIKE 恒 0 行；
3. 翻转密文做篡改夹具**不可逆**：恢复要用原值（脚本自己造的信，原值在手上）；
4. 链上 `version` 对会话事件记的是**接收方长期密钥的版本**（与 keyId 同源），
   不是"第几次会话"。

**归 KMS-015 的两件事**（已写进 roadmap §9）：`/session-keys/` 上旧会话模型的
动作端点仍匿名，与 `verify-session-establish.mjs` 一起决定封存/删除；
`lifecycle_evidence` 与链上事件锚定的那几版长期密钥，标记 legacy 时别一起处理。

### 2.14 KMS-015「迁移历史数据并封存旧路径」——已收口（阶段 7 闭合）

**交付**：错误算法三入口全拒、镜像列停写、服务端不再产生私钥、
私钥清理三步可审计（已实测执行）、旧脚本删除/反转、旧会话动作封存 410。
阶段 7 出口检查闭合。

| 改动 | 落点 |
|---|---|
| falcon_lattice 三入口全拒（generate / replenish / consume），`generate_falcon_pool` 整体删除 | `key_pool_service.py`、`views.py`（码写进文案，与 consume 同一条约定） |
| 镜像列停写：写只写规范列、回收仍两列都清 | `node_key_registry._write_node_column` |
| 读路径切规范列优先 + 旧列兜底 | `node_self_views`（就绪判定）、`database_blockchain_sync_service`（两处） |
| auto_fix 只报告不生成（原会重新生成并写回私钥） | `apps.py` |
| 私钥清理三步（dry-run → 0600 备份 → 核验后清空；无备份拒） | 新管理命令 `clear_node_private_keys` |
| 旧会话五个动作封存 410 + 指路新链路（旧实现保留供回滚期对照） | `views.py`（`_SEALED_SESSION_ACTIONS`） |
| `Deprecation` 头统一加在每个响应上（含 4xx） | `user_distribution_views.py`（拆出包装函数） |
| 夹具地址按 nodeId 哈希派生（原先时钟取模会撞服务端去重） | `tools/lib/node-session.mjs` |
| 旧脚本删除八份 + 断言反转进新脚本 | `kms-ops/tests/` ×3、`tools/` ×3、`front/tools/verify-session-establish.mjs`、`certificateless_key_update_service.py` |

**四条设计口径**（改之前先读注释）：
1. **"停写"与"不清理"是两回事**：镜像列停写后回收仍要清它（存量旧值）；
2. **封存 ≠ 删除**：旧动作返回 410 并指路，实现保留供回滚期内对照
   （计划 §15 第 8 步：删除旧接口要在完整发布周期之后）；
3. **清理命令默认"看"**：`--clear` 必须带 `--backup`，且先逐行核验
   备份哈希与库内一致（"以为备份了、实际没备"比不清更糟）；
4. **历史行可读是断言的一半**：只钉"拒绝"会让"把历史行删掉"同样全绿。

**实测**：`verify-legacy-sealed` **31/31**（新增）；无回归 45/45、84/84、
80/80、56/56、49/49、48/48；后端 **17 组通过 / 0 组失败**（第 1/5 组按
新契约更新）。**私钥清理已真实执行**：1 个存量值 → 备份（0600，在
gitignored 的 kms-ops/dvadmin-logs/）→ 清空 → 六列归零。

**四个新踩实的坑**（roadmap §6 末尾已收录）：
1. 夹具地址不能用时钟取模（中断运行的残留 + 服务端去重 = "建节点成功但
   没拿到激活凭证"，报错里是另一个节点）；
2. 验证脚本日志捕获要挂 handler（`logging.basicConfig` 在本项目是 no-op）；
3. `Deprecation` 头只挂成功路径时，弃用接口的 4xx 与活接口无法区分；
4. 断言比"坏材料没被动过"要按**写入时的形状**比（夹具用 base64 写就比 base64）。

### 2.15 KMS-016「执行全量验收并更新文档」——已收口（阶段 8 闭合，项目完成）

**交付**：三算法端到端验收 + 会话失效粒度缺陷修复 + 干净环境构建实测 +
发布报告与文档收口。

| 改动 | 落点 |
|---|---|
| 新脚本 `verify-stage8-e2e`（§9.3 八步，三算法完整会话链） | `kms-updatedel/front/tools/verify-stage8-e2e.mjs`（34/34） |
| **会话失效按版本引用精确匹配**（原按节点全撤） | `session_invalidation_service.py`（精确面 + 家族退化面 + 粗粒度 warning + `skipped_unmatched`） |
| 回收路径传入版本三元组 | `key_revocation_service.py` |
| 后端第 14 组补两条"不误伤"断言 + 夹具带版本引用、方向与生产一致 | `tests/test_node_key_registry.py` |
| 发布报告（阶段 8 产出物） | `doc/kms-release-report.md` |
| 三份文档收口（总览、overall-flow 模型说明、v2 实施结果三类分离） | `doc/系统完成情况总览.md`、`doc/kms-system-overall-flow-and-pages.md`、`doc/three-subsystem-refactor-plan-v2.md` |

**干净环境构建证据**（阶段 8 出口检查逐字：干净环境构建、启动、迁移和
端到端测试全部通过）：干净 worktree（2074 文件）→ 后端 213 `.py` 解析 /
Java `mvn package` / 前端 489 asset 全过 → `docker compose config` exit 0
（干净树上正确要求 `.env`）→ **空库 39 个迁移全 OK + `makemigrations --check`
零漂移** → `verify-stage8-e2e` 34/34。

**验收中揪出的真缺陷**：`verify-stage8-e2e` §7"关闭 established 会话"发现
该会话提前变 `revoked` —— 会话失效按**节点全撤**，撤一把 KYBER 杀掉
SM2/SSCL 保护的会话（与 KMS-007 修池项缺陷同源）。已修（见上表），
后端第 14 组两条新断言是它的回归判据。

**三个新踩实的坑**（roadmap §7 末尾已收录）：
1. "验收脚本全绿"不等于"验收通过"——全量验收的价值在把各阶段脚本**没交叉
   到的组合**走一遍（三算法同时在谈 + 中途撤一把密钥）；
2. 干净树的 compose 校验失败（缺 .env）是**守卫**不是缺陷；
3. 夹具方向要与生产一致（被撤节点 = 会话的接收方 node2，保护密钥引用在接收侧）。

---

## 3. 关键设计决策（含理由，别推翻）

### 3.1 单阶段原子轮换，**不是**两阶段 PENDING → 激活

曾考虑"先在服务端记一行 PENDING，本地密封好再上报激活"。否决，理由：

- 两阶段会让**重试**命中 `register_public_key` 的幂等分支，返回 PENDING 行而不激活 ——
  接口返回 success，生产版本却从没切过去。这是最坏的一种失败：静默。
- 单阶段在失败后不留下任何东西，严格更强。

跨会话边界（先本地封存 → 再上报）靠**调用方提供 keyVersion** 解决，而不是靠服务端状态机。
这正是计划 §6.1 那句「所有请求显式携带版本；不允许依赖'当前最新版本'的隐式行为」。

### 3.2 版本由调用方给出，服务端不推断

老的 `rotate_public_key` 是"取该算法最新一行、版本 +1"，有三个**一个都不报错**的坏结果：

1. 最新一行已 REVOKED 时，在回收记录之上再叠一个 ACTIVE 版本，把终态盖掉；
2. 调用方手里的 keyId 与服务端在产那把不同时（换过设备 / 两次更新并发），会把**另一把**降级、
   把手里这把扶正 —— 生产版本被换掉，而请求返回成功（判据②要防的就是这个）；
3. 节点已在本地按某个版本号封存了新私钥，服务端另算一个版本号 → 两边对同一个 keyRef 的记账分叉，
   表现是"密钥在、查不到"。

三类仍在的拒绝（`KEY_NOT_FOUND` / `KEY_REVOKED` / `KEY_VERSION_MISMATCH`）各自对应其中一种。

### 3.3 重试语义不需要额外机制

`version == latest` 时不特殊处理，直接交给 `register_public_key`：同摘要 → 返回已有行（无操作）；
异摘要 → 同 (keyId, 版本) 两把公钥，是真冲突 → `ERR_KEY_VERSION_MISMATCH`。分组十一 B 段两个分支
都通过，验证了这条。

### 3.4 接口层 `rotate=True` 的"缺一不可"

只给 keyId 时服务端**能**算出"下一版"，但算出的那一版与节点本地已按 keyRef 封存的可能不是同一个 ——
于是本机多出一把永远用不上的私钥，而生产版本指向的 keyRef 在本机查不到。两个失败都不报错。
所以缺 keyVersion 直接拒，而不是替调用方补。

### 3.5 `_as_bool` 拒绝而不猜

这个标志决定"生成新密钥"还是"更新同一把"，两条路的落库完全不同。猜成 False，最坏是多出一个 keyId；
猜成 True，最坏是**生产版本被换掉而请求返回成功**。两个方向都不该由服务端猜。

### 3.6 链上事件在事务之外、失败不抛出

密钥已经换好、旧版本已经降级，那些事实不因为链上少一条记录而改变。`record_chain_event` 失败只
返回 None 并记日志（旁路增强），页面拿到空 `chainHash` 时如实显示"存证未成功"。

### 3.7 前端 `NODE_SELF_ERR` 只映射**有分支处理**的几个

`node-self.js:13-32` 的注释写明了理由：全量抄一份就会与后端漂移，而漂移的表现是某个分支
**永远不成立**（名字对不上），且不报错。**要新增分支时，去 `api_contract.py` 取准确名字再往这里加。**
判断必须用 `error.errorCode`（由 `@/api/pqkds/http` 拦截器附上），不要匹配 `error.message` —— 文案随时会改。

---

## 4. 本次修改的文件（已提交，7 个 + 1 个 docstring 跟进）

`git show --stat 298c6c5a` 实测：7 files changed, 1908 insertions(+), 649 deletions(-)。

| 文件 | 改了什么 |
|---|---|
| `kms-distribute/dvadmin/backend/pqkds/node_key_registry.py` | `rotate_public_key` 重写为显式身份 + 三类拒绝（358-483 行，含 docstring 371-405）；`_as_version` 新增（330-355）；登记口守卫与 `_via_rotate`（263-299，守卫本体 291-299） |
| `kms-distribute/dvadmin/backend/pqkds/node_service.py` | `store_node_public_key` 加 `rotate` 形参与"缺一不可"守卫（528-537）、`retry_same_version` 预检查（549-556）、`IntegrityError` 收敛（578-593）、回传 `key_pk`/`public_key_hash`/`rotated`（626-642） |
| `kms-distribute/dvadmin/backend/pqkds/node_self_views.py` | `_as_bool`（114-140）、`rotate` 字段读取（316-321）、KEY_UPDATED 链上事件（354-376）、`chainHash` 回传（390） |
| `kms-distribute/dvadmin/backend/tests/test_node_key_registry.py` | docstring 不变量 7-9；两处调用点改显式身份；三个新测试组（第 11、12、13 组）并注册进 `_main()`（1088-1102 行） |
| `kms-updatedel/front/src/api/pqkds/node-self.js` | `NODE_SELF_ERR` 补到 6 个码；`registerSelfNodePublicKey` 加第 7 个形参 `rotate`（只在 `=== true` 时才进 body） |
| `kms-updatedel/front/src/views/keyupdate/index.vue` | 整页重写：本地封存新版本 → 自检 → `rotate:true` 上报 |
| `kms-updatedel/front/tools/verify-keyupdate-rotate.mjs` | 整脚本重写：四条判据 + 部署探针 + "更新 vs 登记" 判别（45/45） |

**HEAD = `ee89813b`**（分支 `v1`）。KMS-006 主体是 `298c6c5a`；紧随的 `ee89813b`
只补自测文件的文件级 docstring（测试列表与断点一字未动，改后复跑仍 13/13）。
再往前：`b15a07b1` → `5c2e1b15` → `2fe07dd7`。

⚠️ 本文件（`PROJECT_PROGRESS.md`）与整个 `doc/` 一样**不进 git**（`.gitignore:120`
忽略 `doc/`；本文件在仓库根、仍是 untracked）。这是刻意的：进度与计划文档只存在于
磁盘，`git status` 看不到它们 —— 别把"文档更新"算进提交完整性。

⚠️ 前端三处在 `kms-updatedel/` 子树，与后端四个文件不在同一目录，但按 §13 硬规则
必须**同一个提交**收口 —— 它们共同构成 KMS-006 这一次交付。

⚠️ 前端产物（`kms-ops/front/updatedel/`）**不在** git 里（`.gitignore:146`），
所以"重建镜像"这件事不会体现在 diff 上。别人拉下这次提交后，**必须自己重建
nginx 镜像**才能看到新的更新页 —— 只 pull 不 rebuild，页面还是旧的。
这一点已写进 `doc/系统完成情况总览.md` §5.6。

---

## 5. KMS-006 的 (d)-(h)：全部已完成

### (d) `node-self.js` 加 `rotate` 参数 + 补两个错误码 ✅

`registerSelfNodePublicKey` 新增第七个形参 `rotate`，**只在显式传 `true` 时**才往
body 里加字段（`undefined`/`false` 都不加）。两个既有调用点
（`views/nodeInit/index.vue`、`views/generate/create.vue`）的请求体因此**一字未变**
—— KMS-005 的验收脚本按逐字节比对走生成页那条路径，改坏了会静默变成另一条路。

`NODE_SELF_ERR` 由 4 个码补到 6 个（新增 `KEY_REVOKED`、`KEY_NOT_FOUND`），
并在 `KEY_VERSION_MISMATCH` 的注释里写清它**一个码对应三种触发**
（同 keyId 两把公钥 / 版本回退或跨越 / 更新的不是生产那把）。

### (e) 重写 `keyupdate/index.vue` ✅

整页从旧的 keymanage 模型（`composeUpdatedPrivateKey` + 下载密钥文件）重写为
节点本地流程，逐字复刻计划 §7 阶段 2 的顺序：**先本地封存新版本 → 当场自检 →
通过之后才带 `rotate: true` 上报**。自检失败时本地那一版**留着**（下次更新复用，
避免"同 keyId 同版本两把公钥"被判成真冲突）但**不上报**，生产版本原封不动。

失败分支按 `error.errorCode` 走，不匹配文案。对账不是「一致」时更新按钮**禁用**
并给出各自的下一步 —— 这是本页唯一真正的门禁。

### (f) 重写 `verify-keyupdate-rotate.mjs` ✅ → 45/45

按阶段 2 四条判据重写，全部走真实 HTTP + 读库。**重写之后又补了两条断言**，
因为前一版（43 项、也全绿）其实**判不出它想判的东西**：

- **部署探针**：先用一个 `_as_bool` 认不出的 `rotate` 值探"跑着的服务端有没有这段
  代码"。这条探针不碰库（rotate 的解析排在校验与落库之前），所以能安全地跑在
  所有用例之前。
- **「更新 vs 登记」**：`rotate` 被服务端忽略时，两条路径**落库完全一致**，所以
  读库断言全部单独都不足以证明走的是更新。能分辨的只有响应文案与第 8 节的
  `chainHash`。

### (g) 重建前端产物与 nginx 镜像 ✅

产物已与构建输出**逐字节相同**（清掉旧的 161 个 stale chunk 后 484 个文件），
容器内核对一致、网关端到端可取。

### (h) 更新两份磁盘文档并提交 ✅

- 提交 `298c6c5a`：后端四个文件 + 前端三处改动收在**同一个提交**里
  （7 files changed, 1908 insertions(+), 649 deletions(-)），提交信息写了四条判据
  的落地方式、复核查出的四条静默缺陷、`_via_rotate` 的来由，以及两条刻意不改的
  已知限制；
- 跟进提交 `ee89813b`：只补自测文件的文件级 docstring（少了第 9 条不变量），
  测试列表与断言一字未动；
- `doc/kms-system-completion-and-refactor-plan.md` §13.1 关闭记录表加 KMS-006 行，
  并把 KMS-004 行过时的「10 组」改为实测的 **13 组**；表下补一段说明 `_via_rotate`
  为何存在、删掉它会怎样；
- `doc/系统完成情况总览.md` §4.2（13 组、四条缺陷与两条刻意不改的说明）、
  §5.1（已提交表加 KMS-006 行与跟进提交）、§6（KMS-002~006）。

### 已知但**超出** KMS-006 范围（不要顺手做）

- 节点侧页面 `userKeys` / `keyVersionHistory` / `keydelete` 仍在旧 keymanage 模型上 → KMS-007；
- `KEY_CREATED` / `KEY_REVOKED` 链上事件 → KMS-014 / KMS-007；
- `Node.falcon_public_key` 镜像列的停写 → KMS-015。

---

## 6. 施工单与执行记录（全部已执行）

(d)(e)(f)(g)(h) 已按原施工单执行完毕，成品与实测结果见 §5；下面保留每一步的执行记录，
其中夹杂的坑对 KMS-007 同样适用。

### 第 1 步：(d)(e)(f) —— 已执行

三处改动都已落盘并实测：`node-self.js` 的 `rotate` 只在 `=== true` 时进 body
（两个既有调用点请求体一字未变）；`keyupdate/index.vue` 按"先本地封存 → 自检 →
再上报"重写；`verify-keyupdate-rotate.mjs` 整脚本重写为 45/45。

⚠️ 执行中确认了一条**原施工单没写、但会决定成败**的事实：`rotate` 被服务端忽略时，
"更新"与"带显式版本的登记"**落库完全一致**。所以验收脚本必须能分辨这两条路径 ——
现在靠**部署探针**（第 1 节，用一个 `_as_bool` 认不出的值探在跑的代码）
与**响应文案**（第 3 节，`-- 公钥已更新为 vN` vs `-- 公钥已登记`）。
以后任何一次"改后端 → 跑验收"，先看探针那一行过不过。

### 第 2 步：(g) 已执行 —— 构建与部署的**正确**顺序

实际执行并核对的顺序（与 `doc/系统完成情况总览.md` §5.6 一致）：

```bash
# 1) 前端构建（kms-updatedel/front 下）
export PATH="/d/Users/AllenR/AppData/Local/Author Software/nvm/installs/v25.6.1:$PATH"   # 新 shell 里 node 不在 PATH
npm run build:prod

# 2) 同步产物 —— ⚠️ 必须先清 assets/ 再拷
#    cp -r 只覆盖不删旧，旧 hash chunk 会一并进镜像。实测踩中过：
#    同步后 assets/ 里有 645 个文件，其中 161 个是上一轮的陈旧 chunk。
rm -rf ../../kms-ops/front/updatedel/assets
cp -r dist/. ../../kms-ops/front/updatedel/
#    核对：本机 dist 与目标目录 diff -rq 必须无差异（实测 IDENTICAL，484 == 484）

# 3) 重建 nginx 镜像（产物打进镜像，不重建不生效）
cd kms-ops && docker compose up -d --build nginx

# 4) 跑验收
cd kms-updatedel/front && node tools/verify-keyupdate-rotate.mjs
```

⚠️ **判断前端是否真的生效，看容器内产物里的 hash，不要看本机 dist** ——
本机 `dist/` 更新了不等于容器里的换了。本次核对方式：

```bash
docker exec kms_gateway sh -c 'ls /usr/share/nginx/html/updatedel/assets | wc -l'   # 484
docker exec kms_gateway grep -rl "<新页面文案>" /usr/share/nginx/html/updatedel/assets/
docker exec kms_gateway grep -rl "composeUpdatedPrivateKey" /usr/share/nginx/html/updatedel/  # 必须无输出
```

### 第 3 步：(h) —— 文档与提交 ✅ 已执行

1. 计划 §13.1 加 KMS-006 行（`298c6c5a`，关闭依据写四条判据的实测证据），
   并修正 KMS-004 行的 10 → **13**；
2. `doc/系统完成情况总览.md` §4.2（判据证据 + 复核四条缺陷）与 §5.1（已提交表）同步；
3. 提交：后端四个文件 + 前端三处改动
   （`node-self.js`、`keyupdate/index.vue`、`verify-keyupdate-rotate.mjs`）
   在**同一个提交**里 —— 实际用的主题是
   `更新页与更新服务收口为本地流程：同 keyId 显式递增版本，登记口不再能加版本`，
   六节散文体（判据落地 / 四条静默缺陷 / `_via_rotate` 来由 / 前端 / 验证 / 两条已知限制）。

---

## 7. 环境与操作细节（踩过的坑）

### 7.1 后端改动：**必须重建镜像**（本会话实测踩中）

所有服务代码**打进镜像**，没有 bind mount（`dvadmin3-django` 只挂了 `/var/log`）。
`docker cp` 进容器的文件只活在**可写层**，而且**跑着的进程不会重新 import** ——
磁盘上的文件与容器内 md5 逐字节相同，进程持有的仍是启动时导入的旧字节码。

⚠️ 本会话实测踩中：容器 09:30 启动、三个 `.py` 10:05 才 `docker cp` 进去，于是
`rotate` 在服务端**恒为 False**，更新静默退化成"带显式版本的登记" —— 两者成功场景下
**落库完全一致**，接口 200、库里也确实变了，验收脚本一度 33/43 而看不出原因。

**正确做法**：

```bash
cd kms-ops && docker compose up -d --build dvadmin3-django
```

**跑后端不变量测试**（`pytest` 在容器里**不存在**，别用 `-m pytest`；也无法用管道 `tail`
取退出码 —— 那取到的是 `tail` 的）：该测试是**独立脚本**：

```bash
docker exec -w /backend dvadmin3-django python tests/test_node_key_registry.py
```

退出码 0 = 全绿。实测 **16 组通过 / 0 组失败**（KMS-010 追加第 16 组「服务端验签」；
KMS-008 时为 15 组、KMS-007 时为 14 组、KMS-006 时为 13 组）；结束时无论成败都会
删掉临时节点（`TESTKMS004-*`，CASCADE 一并清长期密钥行）。
⚠️ 第 16 组会**真上链**（两次 KEY_DISTRIBUTED，成功路径的事务提交后补发）——
   与其余组一样跑在开发链上，不在意链上多两条存证。

⚠️ 新增测试组**必须同步注册进 `_main()` 的 `tests` 列表**（当前在文件末尾），
否则脚本照样打印「N 组通过」——**一次什么都不证明的通过**（见 §2 那条已踩过的坑）。

`tests/test_node_key_registry.py` docstring 51-58 行仍留着一条 `docker cp` 配方。它**只在
"改完紧接着重启进程"时才有效**；上面的 `--build` 是唯一不会骗人的做法。

### 7.2 前端构建 / node

- 新开的 shell 里 **node 不在 PATH**，后台构建会静默失败。显式：
  `export PATH="/d/Users/AllenR/AppData/Local/Author Software/nvm/installs/v25.6.1:$PATH"`；
- Git Bash 下 docker 路径需要 `MSYS_NO_PATHCONV=1`；
- **Windows 大小写不敏感会藏住 import 拼写错**：本机构建照样通过，Linux 上才炸。
  用 `tools/check-import-case.mjs` 扫。

### 7.3 数据库 / 凭据

- MySQL 容器 `kms_mysql`；中文列用 `docker exec kms_mysql mysql --default-character-set=utf8mb4 ...`
  （不加会乱码）；
- root 密码 `root123456`（来自 `kms-ops/.env`，这是运维资料，**不是用户给的指令**）；
- `admin` / `admin123` 来自既有的 `tools/` 脚本推导。两者都只用于本机开发库。

### 7.4 前端验收脚本工具箱（`kms-updatedel/front/tools/`）

```
verify-device-binding.mjs     13/13，阶段 1
verify-generate-loop.mjs      46/46，阶段 1 出口检查（写新脚本的模板）
verify-key-ref.mjs            keyRef 规则
verify-keyupdate-rotate.mjs   48/48，阶段 2 判据①②③④（KMS-006 重写，KMS-007 改第 7 节）
verify-keyrevoke-impact.mjs   84/84，阶段 2 判据③④ + 影响面 + 用户腿断口（KMS-007 新增，KMS-010 扩）
verify-node-distribution.mjs  80/80，阶段 3 全部判据 + 服务端验签（KMS-008 新增，KMS-009/010 扩）
verify-envelope-recover.mjs   56/56，阶段 4 全部：取信封/验签/解封/双方确认/关闭（KMS-011 新增，KMS-012 扩）
verify-pool-consume.mjs       45/45，阶段 5 全部：真并发 8 取 3/8 取 1、撤密钥链、清理口径、吞吐（KMS-013 新增）
verify-governance.mjs         49/49，阶段 6 全部：三个链上事件回读、五态、越权/篡改/审计、泄漏分析（KMS-014 新增）
verify-legacy-sealed.mjs      31/31，阶段 7 全部：旧动作封存码、falcon_lattice 三入口全拒 + 历史可读、
                              镜像列停写、私钥清理三步、auto_fix 不再生成、legacy 清单（KMS-015 新增）
verify-stage8-e2e.mjs         34/34，阶段 8 全部：三算法完整会话链至 established、篡改/换私钥/缺私钥三失败、
                              回收后分发与生成被拒无半行落库、消费不可重复、三终态拒绝确认（KMS-016 新增）
smoke-pool-page.mjs           7/7，密钥池页真浏览器冒烟（KMS-013 新增；节点令牌 + /distzone/selfpool）
verify-node-crypto.mjs        浏览器侧密码学
verify-node-init-ui.mjs       28/28，激活流程
lib/node-session.mjs          ← 共享库（登录/建节点/浏览器 provider）
```

⚠️ KMS-015 **删除**的旧流程脚本（不保留"继续绿"的）：`kms-ops/tests/` 的
`verify_user_leg_e2e.py` / `verify_node_leg_e2e.py` / `make_browser_decrypt_sample.py`、
`tools/` 的 `verify-falcon-pool.mjs` / `verify-manual-rotation.mjs`（同时是 `tools/lib/mysql.mjs`
点名"SQL 在 Windows 恒空、断言不可信"的两个）、`kms-updatedel/front/tools/verify-session-establish.mjs`
（旧会话模型，新链路已由 `verify-envelope-recover` 覆盖）。它们验证的链路
已封存（旧会话动作返回 410、falcon_lattice 拒绝面见 `verify-legacy-sealed`），
留着只会给旧路径续命。删除时均为 git 跟踪文件（可回滚）。

⚠️ 新脚本的**夹具节点要登记四套密钥**才能过 `/node-self/init/`
（它校验 SM2/SSCL/KYBER/FALCON 齐备）——只登记 KYBER+FALCON 会得到
"以下基础公钥尚未登记"（KMS-011 实测踩中）。

`lib/node-session.mjs` 的 `api()` **返回 `{status, body, headers}`**（KMS-008 起加了
`headers`）—— 有的判据本来就在头部而不在 body 里，例如弃用标记 `Deprecation: true`。
`user-distribution-api.js` 里**两个 HTTP 客户端并存**（`requestJson` 给旧接口、
`@/api/pqkds/http` 给新接口），后者才带 `error.errorCode`，新的按错误码分支的写法
一律用后者。

`verify-keyrevoke-impact.mjs` 里有两样 KMS-008 之后可能直接复用的东西：
**FISCO JSON-RPC 回读**（`rpc()`/`scanLifecycleEvents()`/`decodeLifecycleEvent()`，
见 §2.6 的说明）与**容器内现生成真 Falcon 密钥对**（`generateFalconKeypair()`）。

新脚本一律走 `lib/node-session.mjs`，别再自己拼 admin 登录：旧脚本里的
`login(ORIGIN, '/updatedel-api', 'admin', 'admin123')` + `/lifecycle/keymanage`
那条路径已是被废弃的模型（KMS-006 重写的就是这个）。

`node-key-compare.js` 导出的对账工具：`RECONCILE`、`RECONCILE_TEXT`、`reconcileOk`、`samePublicKey`、
`compareKey`、`findLocalKey`、`reconcileRow`、`compareNodeKeys`、`activeServerKey`。

⚠️ 查库统一走仓库根的 `tools/lib/mysql.mjs`（`sqlScalar`、`dockerBin`）。手写 `docker exec mysql`
时注意三个坑（都踩过）：`CONCAT_WS` 会**跳过 NULL**（要写 `IFNULL(active_slot,'NULL')` 占位）；
MySQL 默认排序规则**不区分大小写**（比较两侧都加 `BINARY`）；Git Bash 下路径要
`MSYS_NO_PATHCONV=1`，否则 `/backend/...` 会被改写成 `D:/Program Files/Git/backend/...`。

### 7.5 仓库写作风格（新代码必须匹配）

中文注释解释**为什么**，尤其是"这类失败是静默的 / 这类假警报比不报警更糟"的推理链；
`⚠️` 标记关键坑；docstring 里用 `----` 下划线小标题；中文破折号用 `——`。
不要写"改进了 XX"式的空话，要写清"不做这一步会怎样、为什么看不出错"。

---

## 8. 一句话状态

**项目完成：KMS-001 ~ KMS-016 全部关闭，八个阶段的出口检查全部闭合。**
最终提交 `e0ef4a1f`（会话失效粒度缺陷修复 + 阶段 8 端到端脚本）与
KMS-015 的 `43ebb8b5` 等各阶段提交共同构成交付。
**最终交付物是 `doc/kms-release-report.md`（发布报告）**：
提交清单、**干净环境构建**（干净 worktree → 三条构建链全过 →
`compose config` 通过 → **空库 39 个迁移全 OK + 零漂移** →
端到端 34/34）、验证证据汇总（十四个前端脚本 + 后端 **17 组**）、
验收中修复的七个缺陷（含 KMS-016 实测揪出的"会话失效按节点全撤"——
撤一把 KYBER 会杀掉 SM2/SSCL 保护的活跃会话，已改为按 KMS-011 四列
版本引用精确匹配）、已知限制与复现方式。
**阶段 8 出口检查「干净环境构建、启动、迁移和端到端测试全部通过」闭合。**
后续工作的入口是发布报告 §5：旧接口函数体的删除（完整发布周期后）、
KGC 主秘密双拷贝、`admin-node-login-design.md` 实施状态章节。

---

## 9. 发布后增补（2026-10-08，非 KMS 编号）

### 9.1 节点登录体验三项（提交 `45151931`）

激活凭证改为密码式展示（管理端弹窗打码 + 登录框 `type=password`）、
登录即在本机写**绑定文件**（`node-binding.js`，meta store 的
`node-{id}-binding`：节点名/设备指纹/首登与最近登录/次数）、
换节点登录时先确认再清除旧绑定与旧设备凭据。
验收 `tools/verify-node-binding.mjs` **32/32**（真浏览器 + 真 IndexedDB）。

### 9.2 节点管理页四个动作的**断路**修复（提交 `18a02080`）

用户在界面上报「无法删除节点、无法重发凭证，报错：身份认证信息未提供」。
根因不是新引入的：`NodeViewSet` 的 destroy/batch_delete/reissue 在 §4.4 阶段一
被移出 AllowAny 名单后交给 `super().get_permissions()`，而本仓
`SIMPLE_JWT["AUTH_HEADER_TYPES"]=("JWT",)` 与全系统的 `Authorization: Bearer`
不匹配 → `JWTAuthentication` 返回 None → `request.user` 是 AnonymousUser →
`CustomPermission` 直接拒。**管理员自己也进不去**；同一原因还压掉了
`keys` / `key_details` / `update_keys` / `update`（编辑）。
修法：这些动作改走 `initial()` 里的 introspect 闸门（与 `/key-pool/*` 同套路）。
验收 `tools/verify-node-admin-gate.mjs` **28/28**（含"拒绝理由里不得出现那句
配置缺陷文案"的反向护栏）。

### 9.3 任务书「节点多级授权」（本次）

任务书《1-课题2-任务书》把**节点多级授权**列为「密钥动态更新与回收系统」的
4 项功能指标之一（p17 / p35，由具有资质第三方检测机构测试）。改造前的
「节点授权」完全是管理端单方面动作，节点侧连"有哪些节点"都看不到
（`/user-nodes/` 只回已授权节点），界面上体现不出这个过程。

**新流程**：节点看到**全网名录** → 选对端**发起申请** → 管理员**审批** →
**双向放行**（两个方向都写授权行）。

* 新表 `NodeAuthorizationRequest`（迁移 `0022`/`0023`），状态机
  pending → approved / rejected / cancelled；`pending_key` 唯一列保证
  "同一对节点同时只有一条未决申请"（`select_for_update` 锁不到还不存在的行，
  并发下两个标签页会双双插入 —— 这是设计评审阶段揪出来的）。
* 节点侧端点：`GET /node-self/directory/`（**只回身份性字段**，不含
  ip/端口/sys_user_id/公钥）、`POST|GET /node-self/authorization-requests/`、
  `POST .../<id>/cancel/`。
* 管理端端点：`GET /admin/node-authorization-requests/`、
  `POST .../<id>/decide/`（approve 写**两行**授权，响应如实区分
  created/reactivated；reject 必填理由、零权限副作用）。
* 抽取 `authorization_service` 作为授权行的**唯一写点**（手工授权与审批共用，
  避免"同一个动作在不同入口下留下不同痕迹"）。
* 上链：新增 `AUTH_GRANTED` / `AUTH_REJECTED` 两个事件类型
  （**Java 白名单 + 消费端只留痕分支**，需重建 `kms_updatedel_java`）。
  链上 `keyId` 位装**申请单主键**（授权没有对应密钥），这条拉伸的边界写在
  `ChainSyncEvent` 的注释里。**部署顺序硬约束：Java 先认、PQKDS 再发。**
* 前端：节点侧新页「节点授权」（菜单 9476，`selfauth`）+ 管理端「节点分发授权」
  页加待审批区；三处过期文案/注释收口（含 `nodeauth/index.vue` 那句
  "不存在申请-审批这条路径"）。

**红线（本次最重要的设计约束）**：批准必须**真的写授权行**；
放行判据自始至终只有 `authorized_node_ids`（读 `UserNodeAuthorization`）一处。
仓库里原有一套 `permission_request` 审批流，正因它的 `approve()` 刻意不授予
任何权限、形成了**第二套权限语义**而被整体下线
（`kms-ops/mysql/init/35_remove_permission_request_menu.sql`）——本次不重蹈。

**验收**：`tools/verify-node-authorization.mjs` **47/47**，其中五条是核心：
① 批准前 `node_peer_keys` 403、批准后 200；② **双向**（A→B 与 B→A 都通）；
③ **判据只有一张表** —— 手工把授权行置 `revoked`，A 立刻回到 403
（此时申请单仍是 `approved`）；④ 驳回/撤回**零权限副作用**；
⑤ **并发**：同一对节点的两个同时申请都成功、指向同一条、库里只有 1 条 pending
（`pending_key` 唯一索引是真保证 —— `select_for_update` 锁不到还不存在的行）。
界面级：节点侧侧边栏出现「节点授权」、页面渲染出名录、
管理端待审批区可批准；链上拿得到交易哈希。

**验收途中查出并修掉的两个缺陷**（都不是新写的功能，而是本次改动引入的）：

1. `admin_node_authorization_views` 里手工授权调用 `_auth_chain_args(row, 'AUTH_GRANTED', identity)`
   —— 该函数只收两个位置参数，多传一个直接 `TypeError` → **整个接口 500**
   （响应里 `code` 变 undefined）。被 `verify-governance` 的"节点鉴权已授予"
   那条当场抓到（48/49）。修好后 49/49。
2. `node_authorization_service.create_request` 的并发兜底原本写成
   "在同一个 `atomic` 里 `except IntegrityError` 再查一遍" —— 那是**必然失败**的：
   Django 一旦在 atomic 块里见到 IntegrityError 就把连接标记为需要回滚，
   后续查询抛 `TransactionManagementError`。改成"内层 atomic 形成 savepoint 吃掉冲突
   + 回读放在**外层事务之外**（MySQL REPEATABLE READ 下同一事务的快照看不到
   并发提交的那一行）"。本仓 `consume_key` 有过同类两层断口，属同一类错误。

**数据库重新初始化（用户要求）**：新增 `kms-ops/reinit-db.sh`
（与 `rebuild-env.sh` 的区别：**只动数据库**，Redis/Kafka/FISCO 链与产物构建都不碰）。
实测：DROP+CREATE 两个库 → 重放 `mysql/init/*.sql` 42 个脚本（含 44_，三次自检全 1）
→ 重启 Django 由 `start.sh` 在**空库**上跑迁移。
结果：`kms` 34 表、`falcon_kds` 54 表、**0 节点**、23 个 pqkds 迁移全应用
（最新 `0023_node_authorization_request_pending_key`）。
这顺带把两条主张变成了实测：**迁移从空库可建**、`44_*.sql` 重放幂等。
重置后重跑：验收 47/47、治理 49/49、admin-gate 28/28、binding 32/32、
full-loop 22/22、login-ui 13/13、后端不变量 17 组 —— 全部在**重建镜像后**复验，
不是只在运行中的容器上（本仓代码是打进镜像的，`docker cp` + 重启不算交付）。

**与既有「节点多级授权」表述的关系**（防止第三方检测时混淆）：
`permission_level`（L1/L2/L3）是**能力等级**（这个节点能做什么），
本次的授权申请/审批是**逐对端的通信授权**（它能跟谁通信）。两者正交：
L2 是"能发起分发"的必要条件，对端授权是"能向谁分发"。对外表述为
**「节点多级授权 = 权限等级 × 对端授权（申请-审批-双向放行）」**。

### 9.4 登录页：一台设备一个节点，且以服务端为准

数据库重置之后，浏览器里还留着那些节点的登录信息 —— 用户看不到它们已经作废，
点下去只会得到一句"节点不存在"。本次把"本机记录 vs 服务端事实"这条分叉收口：

* **新增只读校对端点** `GET /node-self/still-exists/?nodeIds=A,B,C`（免鉴权，
  上限 50）：登录页在**拿到令牌之前**没有任何带鉴权的接口可用，所以这条必须免鉴权。
  它只回答存在性，不回名字/状态/公钥/IP —— docstring 里如实记录了
  "这是一个存在性 oracle，与 `node_challenge` 已有的报错同量级"以及不可扩围。
* **登录页在加载时校对**：服务端已经没有的节点，连同它的**设备凭据与绑定文件**
  一起清掉（不是只在界面上藏起来）。
* **探测失败时绝不清理**：`probeNodesExist` 任何异常/异常形状都返回 null，
  调用方据此**不做任何清理** —— 网络抖动、后端版本旧都可能让"存在性"无从判断，
  而误删等于毁掉本机唯一能登录的身份（私钥不可导出，删了只剩重新激活）。
  这条是本功能最重要的安全属性，验收脚本用 `Network.setBlockedURLs` 屏蔽探测接口
  单独钉住（并配一条对照：探测恢复后同一记录被清掉，证明保留是因为探测失败而非逻辑没跑）。
* **免密优先**：本机已有可免密登录的节点时，登录页**默认只显示节点、收起激活表单**
  —— 表单那两个框（节点名 + 一次性凭证）看着像"每次都得填"，会让人以为免密失效。
  另给一个「**登录其它节点**」按钮展开表单（按钮只在表单收起时出现，不留"点了没反应"的装饰），
  展开后说清"会替换本机登录信息、本机只保留新节点"。

**验收**：`tools/verify-login-remembered-node.mjs` **14/14**
（无记录时必须显示表单／有记录时只显示免密登录＋按钮／展开后说明会替换／
换节点后本机只剩新的／陈旧记录被清／**探测失败时原样保留**＋对照）。
`verify-node-binding` **33/33**（新增一条"表单默认收起、点按钮展开"，
其余脚本中"直接往表单填值"的步骤同步改为先展开）。

### 9.6 分发页多选批量授权（用户："选择对应的节点列表提交这个分发的权限确认请求"）

**需求**：分发页要能拿到**全部可用节点** → 多选 → **一次**提交权限确认请求 →
管理员批准后这些节点即可分发。

**改了什么**

| 层 | 落点 |
|---|---|
| 模型 | 迁移 `0024`：`NodeAuthorizationRequest` 加 `batch_id` / `batch_seq`（**只加列、不加新表**） |
| 服务 | `node_authorization_service.create_requests()` —— 逐目标复用既有 `create_request`（全部校验与并发兜底同一份实现），分一个组号、汇总逐条结果 |
| 节点侧 | `POST /node-self/authorization-requests/` 接受 `targetNodeIds: [...]`（与单目标 `targetNodeId` **并存**，单个走原路径） |
| 管理端 | `POST /admin/node-authorization-requests/decide-batch/` —— 勾选多条一次处置，**逐条回报**（各自的 granted / chainHash / 失败原因） |
| 界面 | 分发页接收节点下拉改**名录**为数据源（未授权项可勾选 → 按钮变「提交授权申请」）；节点授权页多选提交；管理端待审批卡片勾选多条批量批准 |

**红线**：组号**只用于展示与勾选**，不参与任何放行判断 —— 每条申请仍是独立一行、
独立状态，管理员可以只批其中几条。放行判据自始至终只有 `UserNodeAuthorization`
（见 `models.NodeAuthorizationRequest` 的 docstring：仓库为此整体下线过一整套审批）。

**验收**：`tools/verify-node-authorization.mjs` **47 → 53/53**。新增 6 条钉住：
一次提交多条共用一个组号、已授权目标进 `skipped`、重复提交不建第二条、
批量批准逐条回报、批准后确实放行、**批量不是全或无**（只批一条时另一条仍 pending）、
节点令牌调批量批准 403。

### 9.7 预分配密钥池支线收口（用户："预分配的指标也需要达成"）

**规范（用户定义，逐字）**："发送节点在实际通信之前，提前生成一定数量的随机 SM4
会话密钥，利用接收节点的 Kyber 公钥形成加密保护包，并将保护包上传至 KMS 预分配
密钥池。服务端仅负责保存、调度和管理保护包。实际建立会话时，发送节点取用一条
预分配资源，使用 Falcon 私钥签名并发送，接收节点验签和解封装成功后，双方建立
SM4 安全会话"。

**核查结论：旧实现不符合规范，而且**根本不可用**（交付前是死的）：

* 预分配页**从未成功过** —— 页面发 `nodeIds: [...]`，而 `/key-pool/generate/` 只读
  `node1_id`/`node2_id` → 永久 400「缺少 node1_id 或 node2_id」；
* K 由**服务端**生成 —— 与"服务端仅负责保存、调度和管理"相抵（它生成时必然知道 K）；
* 池项的消费通路是死的（唯一调用方 `SessionKeyViewSet.initiate` 已封死为 410），
  取用后**不建会话**（`used_by_session` 恒 NULL）；
* 池项**漏进接收方的信封列表**（`recipient_type` 缺省 `'node'`，"还没发就已经收到"）；
* 存量的保护包形状与节点信封不同（`encrypted_aes_key` + 无 `wrapping_algorithm`），
  前端解封按 `wrapping_algorithm` 分派、按 `encrypted_key` 取密文 —— 不归一化则**静默解不开**。

**改了什么**

| 改动 | 落点 |
|---|---|
| 池项标 `recipient_type='pool'`（取用时翻 `'node'`） | `key_pool_service.generate_kyber_pool` / `consume_key` |
| 一个池子 N 条 = N 个会话（会话号 `{池号}-k{序号}-n{接收方}`） | `distribution_service.create_initiated_sessions(session_id_suffix=…)` + `node_session_views._session_of_batch` 认两种形状 |
| 三条新端点：上传保护包 / 余量 / 取用 | `node_self_views`（`pool/preallocate`、`pool/summary`、`pool/consume`）+ `pool_consume_service.py` |
| 补签名端点（先独立验一遍再落库） | `node_session_views.node_envelope_sign`（与 verify/recover 同段路由） |
| 归一化保护包 + 重算密文摘要 | `pool_consume_service._normalize_protection_package` / `_build_delivery_envelope` |
| 审计流水（`pool_consume` / `pool_prealloc` + 链上哈希） | 迁移 `0025`（纯 choices）+ `_write_pool_log`（**只记摘要，绝不记 K**） |
| 界面 | 预分配页重写（参数名修对 + 任务书 §20 六项读数 + Kyber 单算法）、分发页新增「用预分配密钥发送」路径、密钥池/总览页收口 |

**指标实测**：本机（浏览器同款 `@noble/post-quantum` + SM4-GCM + Falcon 签名）
**约 130 ~ 143 条/秒** —— 任务书 §20 的「Kyber 预分配 ≥ 50 条/秒」达标。
验收脚本每次都会**实测并打印**，达不到就判红（不四舍五入凑数）。

**施工中实测揪出并修掉的两个真缺陷**（都不是读代码看出来的）：

1. **并发取用一条 200、另一条报"没有可用"**（池子里明明还有 18 条）。
   根因有两层：`SELECT … ORDER BY … FOR UPDATE SKIP LOCKED LIMIT n` 会把**它扫过的
   每一行**都锁上（不是 n 行）；而修成"逐行锁"之后我第一版**把锁到的行全收着**
   （够用不停），于是第一个请求仍然把整个池子点着。定位靠的是往 `consume_key`
   里加一行 DIAG 日志（`candidate_pks=18 contested=18`）+ 采样
   `performance_schema.data_locks`，不是靠读 SQL 猜。最终形态：
   **无锁选出候选 pk → 锁一条、判一条、够用即停**。三次连跑 26/26。
2. **「分发记录」页恒空**（与本次无关，是既有缺陷）：`KeyDistributionLogViewSet`
   被 `DataLevelPermissionsFilter` 按主 KMS 的**部门数据权限**逐行过滤，
   而它读的 `request.user` 因 `SIMPLE_JWT["AUTH_HEADER_TYPES"]=("JWT",)` 与全系统的
   `Bearer` 不匹配而恒为匿名 → `queryset.none()`。**库里有 5 行、接口恒回
   `{total: 0, msg: "暂无数据"}`** —— 根因不在页面、也不在"没人写流水"。
   该表是审计流水、按 `node` 归属，没有部门概念，故在这个视图集上清空
   `extra_filter_class`（其余筛选后端全保留）。

**验收**：新脚本 `tools/verify-pool-preallocation.mjs` **26/26**。核心是**真往返**：
上传（本机生成 20 条并逐条签名）→ 负对照（未取用前**双方**都看不到）→ 取用 →
补签名（含幂等与非签名者 403）→ 接收方本机**解封得到 K，其 sha256 逐字节等于
库内 `key_hash`，且与发送方本机那把逐字节相同** → 服务端独立验签通过 →
审计流水里搜不到明文 K → 回收接收方那一版 → 剩余池项转 REVOKED、再取用被拒 →
未授权节点取用被拒。

**回归**：`verify-pool-consume` 45/45、`verify-node-distribution` 80/80、
`verify-envelope-recover` 56/56、`verify-governance` 49/49、
`verify-keyrevoke-impact` 84/84、`verify-node-authorization` 53/53、
`verify-detail-layout` 10/10、`verify-node-full-loop` 22/22、
`verify-workbench-basekeys` 11/11、`smoke-pool-page` 7/7、`verify-workbench-shape` 全 OK。

⚠️ **如实记录一条本来就坏的脚本**：`tools/verify-distribute-ui.mjs` 跑不通，
但它测的是 **KMS-008 之前就已被删掉的"用户腿"页面模型**（它找「节点封装算法」
「源密钥」，而这两样在改动前的 HEAD 上就 grep 不到）；脚本里还有 cmd 语法的
`2>nul`，在 Git Bash 下必然失败。**不是本次回归**，未修（修它等于重写一个测已删功能的脚本）。

⚠️ 本次**不做**算法三选一（用户明确：量化指标基于格密码）；`/key-pool/generate/`、
`/key-pool/distribute/` 与本地明文池保留但新支线**绕开**它们（注释里写明原因）。

### 9.5 工作台补上「基础密钥」（用户问："初始化生成的密钥为什么不在工作台"）

**根因不是数据丢了，是工作台问错了地方**：它的密钥类卡片与图表全部来自
**generate / lifecycle 两个子系统**的记录（`kms` 库），而四套基础密钥登记在
**分发模块**的 `NodeLongTermKey`（`GET /node-self/keys/`）——两套不同的事实来源，
工作台从来没问过后者的存在。节点侧登录后走的「密钥生成/更新回收」又是另一条链路，
所以初始化那四把钥匙在工作台上永远是 0。

改了四处，并且**守住工作台的硬约束（KPI 4 张 / 图表 5 张）**：

1. **KPI「待审批申请」→「基础密钥」**。原卡片是**死的**：审批流阶段 8 已下线，
   `loadPermission()` 把 `permissionRows` 硬编码成空数组，它永远显示 0。
   新卡片显示四套里当前可用的套数，提示列出算法名（缺哪套就报哪套）。
2. **「权限申请」区块 → 「基础密钥」明细**。原区块同样是死壳（永远"暂无权限申请记录"，
   比空着更糟 —— 用户会以为"我还没有申请资格"）。现在逐行列出
   算法 / 状态标签 / keyId / 版本 / 指纹，并保留右侧「当前可用能力」。
3. **数据源**：`loadNodeKeys()` 走 `getSelfNode()` + `listSelfNodeKeys()`；
   管理员账号不映射节点 → 记 `STAT_NA`（不是 ERROR，否则管理员打开工作台会看到红字）。
   "当前哪一把"用服务端下发的 `allowsNewWork`，**不在前端按 status 字符串自己判**。
4. **没有新增第 6 张图表**：基础密钥的状态已由明细区块逐行说全，再补一张饼图是重复表达，
   而代价是破坏"图表 5 张"这条硬约束（`verify-workbench-shape.mjs` 钉着）。

**顺带修了一条一直坏着的检查**：`tools/verify-workbench-shape.mjs` 原先作用于
`/user/workbench` —— 那是阶段 1 就已合并下线的前台（nginx 对 `/user/` 显式 404）。
也就是说它**从来没真正校验过**：打开一个 404 页，DOM 里当然什么都没有，
报"KPI 为 0 张"。现在改为"节点令牌 → 真工作台（`/updatedel/workbench`）"并自带浏览器，
**首次真正通过**（4 张 KPI / 5 张图 / 5 个 canvas）。

**验收**：`tools/verify-workbench-basekeys.mjs` **11/11**（界面激活 → 界面初始化四套 →
工作台 KPI = 4、提示列出四算法、区块逐行列全、KPI 仍 4 张、图表仍 5 张、
死卡片已被替换；对照组：未初始化的节点被守卫送回 `/node-init`）。
`verify-workbench-shape` 全 OK；`verify-node-full-loop` 22/22。

**KMS-011 已收口**（`9e2f9d83`，12 files changed，1727 insertions(+), 19 deletions(-)）。
代码（三条新端点 + 会话四列 + 迁移 0019 + `node-envelope.js` + 会话页「处理」全流程）、
测试（`verify-envelope-recover` **41/41** 新增、`verify-node-distribution` 80/80、
`verify-keyrevoke-impact` 84/84、`verify-keyupdate-rotate` 48/48、后端 **16 组
通过 / 0 组失败**）、文档（计划 §13.1、总览 §4.2/§5.1/§6、本文 §2.10）在同一轮收口；
前端产物已重建进 nginx 镜像并三重核对（489 个 asset，磁盘 = 容器内 = HTTP md5 一致）。
`recipient_verified` / `key_recovered` 两个状态**首次真的落库**，
**阶段 4 出口检查的"双方 proof 一致 → established"已在验收里走通** ——
阶段 4 的完整闭合由 KMS-012 完成（见上一段），本文 §2.11。

**KMS-010 已收口**（`5de0442b`，9 files changed，645 insertions(+), 80 deletions(-)）。
代码（验签接入 `create_node_distribution` + 请求新增 `falconKeyId`/`falconKeyVersion`
+ 响应回 `signatureVerified` + 用户腿被签字段落库 + 公钥解码按形状认编码）、
测试（后端 **16 组通过 / 0 组失败**、`verify-node-distribution` **80/80**、
`verify-keyrevoke-impact` **84/84**、`verify-keyupdate-rotate` **48/48** 无回归）、
文档（计划 §13.1、总览 §4.2/§5.1/§6、本文 §2.9）在同一轮收口；前端产物已重建进
nginx 镜像并三重核对（磁盘 487 个 asset = 容器内 = HTTP md5 一致）。
**阶段 3 出口检查「三种保护算法均能产生信封；Falcon 缺失时不能发送」两句全部成立**，
用户腿取件口从"恒 403"恢复为正常交密文（`signatureState='valid'`）。

**KMS-009 已关闭**（`82950ce8`，9 files changed, 1118 insertions(+), 155 deletions(-)）。
代码（`provider.wrapForPeer` 三条腿 + 新模块 `envelope-signing.js` + 服务端改为
"核形状、算摘要、落库" + 页面本机封装与签名 + 分发页显示本机签名密钥）、
测试（后端 **15 组通过 / 0 组失败**、新脚本 **72/72**、KMS-006/007 脚本
**48/48 与 82/82 无回归**）、文档（计划 §13.1、总览 §4.2/§5.1/§6、本文 §2.8）
在同一轮收口；前端产物已重建进 nginx 镜像并三重核对（磁盘 = 容器内 = HTTP）。
服务端从此**拿不到 SM4 明文**。**验签仍归 KMS-010**（`verify_node_envelope`
无生产调用点），所以阶段 3 出口检查的后半句**还判不了**——如实记在 §2.8 与总览。

**KMS-008 已关闭**（`615907b4`，13 files changed, 2032 insertions(+), 368 deletions(-)）。
代码（两条新端点 + `distribution_service` 编排层 + `require_key_version` + 迁移 0018
+ 页面重写）、测试（后端 **15 组通过 / 0 组失败**、新脚本 **56/56**、
KMS-006/007 脚本 **48/48 与 82/82 无回归**）、文档（计划 §13.1、总览
§4.2/§5.1/§6、本文 §2.7）在同一轮收口；前端产物已重建进 nginx 镜像并三重核对。
两条过渡缺口**如实记录**（新批次不进泄漏分析 → KMS-014；信封暂时没有签名 → KMS-009/010）。

**KMS-007 已关闭**（`fab29538`，18 files changed, 3336 insertions(+), 627 deletions(-)）。
代码（新增回收编排服务 + 迁移 0017 + 五道闸门 + 三个页面收口）、测试
（后端 **14 组通过 / 0 组失败**、前端 **82/82** 且 KMS-006 脚本 **48/48** 无回归）、
文档（计划 §13.1、总览 §4.2/§5.1/§6、本文 §2.6）在同一轮里收口；前端产物已重建进
nginx 镜像。独立复核点名的四处空心断言全部补齐（链上回读、三条正对照、会话反例、
池项全局计数差），补证据时**另发现一处既有断口**（签名被签字段未随信封落库 →
取件口 403），按计划第 657 行如实记录并以两条断言钉住，**KMS-010 已修复**
（且查出第二层原因：公钥列是 hex 而解码只认 base64，见 §2.9）。

**KMS-006 已关闭**（`298c6c5a` + `ee89813b`）：后端 13 组、前端 45/45，
独立复核查出四条静默缺陷全部修掉，其中「登记口能给已有 keyId 加版本」改动了
存储层接口（`_via_rotate`）；两条低危项**刻意不改**，理由写在提交信息与总览 §4.2 里。

下一步是 **KMS-013（重构预分配和池项消费）**，执行要点在
**`doc/kms-010-016-roadmap.md` §4**（缺口清单、判据、两条**实测复现的断口**
都在那）。三件起手事：

1. **先复现两条断口**（各一行直调，roadmap 里有命令）：
   `consume_key` 的 `POOL_STATUS_READY_VALUES` 裸名 → `NameError`；
   修掉后还有 `select_for_update` 无外层事务的 `TransactionManagementError`
   —— 即 `/key-pool/consume/` **从未成功跑通过**；
2. **真并发钉住**：N 个并发消费同一池项 → 恰好 1 个成功（不是"N-1 个没报错"）；
3. 撤一把密钥 → 该池项的消费必须失败（补"消费口"那一半；失效本身
   KMS-007 后端第 14 组已覆盖）；过期的池项取不出来。

⚠️ 别把"能跑"当成"并发安全"：`skip_locked` 在没事务时连"能跑"都不成立。

⚠️ 起手前先记住两条本仓库的硬约束：后端改动**必须** `docker compose up -d --build
dvadmin3-django`（没有 bind mount，`docker cp` 进去的文件进程永远 import 不到，
表现是接口照常 200 而新代码从未执行）；前端产物打进 nginx 镜像，改完必须重建。

---

## 10. 双入口与受控免登录演示（2026-10-09，非 KMS 编号增量）

> 本节是当前增量改造的交接入口；前文 KMS-001～016 及发布后记录保留为历史。
> 分支仍为 `v1`；本轮代码未自动提交，原需求文档保留原样。
> **双入口改造与本机真实闭环已完成并部署**；下表列实际执行的验证，不代表全项目历史脚本重跑。

### 10.1 目标及实际入口

按根目录《KMS-双路由登录与演示模式改造方案》实现完整闭环，不只是修改登录页：

- **Standalone**：`http://127.0.0.1/standalone`，导航至管理员或节点原登录组件。
  `/updatedel/login`、节点激活/设备快捷登录及原业务地址继续有效。
  Demo 页的「返回独立运行入口」及旧登录别名会由网关整页跳回同主机原 80 端口，
  不在 8088 加载旧 API 或空的旧 IndexedDB origin；Cookie 跨端口不等于密钥库也跨端口。
- **本机 Demo**：`http://127.0.0.1:8088/demo?nodeId=<已登记业务编号>`；
  没有登录/激活表单，未初始化节点进入四算法初始化，ACTIVE 节点先核对本地材料。
- **Demo 管理入口**：`http://127.0.0.1:8088/updatedel/demo/admin`。
  管理员不映射业务节点，当前节点保存在服务端会话供返回；审批不会因切换按钮自动完成。
- Demo 只由显式 `docker-compose.demo.yml` 开启并发布到 **127.0.0.1:8088**；
  基础配置和 `.env.example` 默认关闭，原 80 端口对 `/demo`、`/demo-api` 和
  `/updatedel/demo` 一律 404。未更改用户 `.env`，未重置数据库，未改 Fabric/DID SDK。

### 10.2 实现边界与共享来源

1. **会话权威只有 Java 一处**：新增 opaque HttpOnly/SameSite Demo Cookie、独立 Redis
   空间，角色/返回节点/CSRF/revision 由服务端保存。不是普通管理员 JWT，不冒用账号 1。
   Generate Java、Django 经内部通道使用同一自省，原 TokenService 会话原样保留。
2. **受控边界**：独立网关注入可信模式与内部凭据，原网关清掉客户端伪造的 Demo 头。
   后端也判开关/来源；变更校验 Origin/CSRF/revision，角色切换与尚未提交的变更受会话
   租约及 in-flight fence 约束。内部令牌只在获用户批准的容器内 0600 配置中使用。
3. **私钥仍在本地**：Standalone DB 名称不改，Demo 用独立 `kms-demo-node-keystore`。
   保护密钥、设备记录、meta、长期材料和会话密钥一起隔离；不同节点仍按完整 keyRef 区分。
   模式/视角切换采用整页边界，不能让未完成的 IndexedDB 操作中途换库。
4. **可恢复初始化**：复用同一生成模块和公钥登记服务，精确对账算法/keyId/version/公钥，
   对应私密材料必须可读；已登记的跳过、未登记本地材料重报、缺的才生成。
   浏览器锁及每节点服务端租约防竞争；Demo 不激活设备、不消耗凭证、不改原设备绑定。
   ACTIVE 缺材料只能提示恢复/显式新版本处置，绝不自动覆盖原版本。
5. **同一业务事实**：创建复用 `provision_node`；Demo 创建不签凭证，Standalone 照旧。
   审批/撤销仍调用原授权服务，只写 `UserNodeAuthorization`，审计标记 `DEMO_ADMIN`。
   L1/L2/L3 能力等级仍生效，管理员不是节点，也不使用其私钥。
6. **业务页不复制**：Demo 菜单从原 `sys_menu` 映射同一组件，路由/名称加命名空间。
   密钥池只读查询按可信节点归属过滤，Demo GET 不顺带全局删除过期资源；节点池操作
   指向原有本机保护包预分配页，旧服务端生成路径不作为 Demo 节点入口。

### 10.3 验收证据（实际执行，不以编译成功代替闭环）

| 项目 | 结果 |
|---|---|
| 生命周期 Java clean package / 测试 | BUILD SUCCESS，13 项，0 失败/错误/跳过 |
| Generate Java clean package / 测试 | BUILD SUCCESS，3 项，0 失败/错误/跳过 |
| Demo Python 边界测试 | 16 项通过 |
| 初始化模块 | 19 项通过，含真实四算法 + 加密 fake IndexedDB 中断/恢复 |
| 真实 Demo API (`tools/verify-demo-api.mjs`) | **37/37**：免凭证、四算法、重入不换钥、真实审批/撤销、L1 反证、池归属、Falcon 验签、Kyber 解封 SM4 逐字节相同、双方 HMAC → 原表 established |
| 真实 Demo 浏览器 (`tools/verify-demo-entry-ui.mjs`) | 最终 **26 项/115 次实际请求全部通过**：初始化中断/竞争/恢复、刷新、角色往返、双节点、本地缺材料、共享密钥池及原本机保护包预分配页 |
| 关闭 Demo 反证 | **4/4**：四服务关闭时页面/API 404；验证后恢复本机回环演示 |
| 实际返回独立入口链接 (`tools/demo/verify-live-entry-readonly.mjs`) | **7/7**：真实点击 Demo 页锚点切回原 80 origin，2 次 Demo GET、0 写请求、0 未捕获异常 |
| 新部署后的旧节点登录 UI | **13/13** |
| 新部署后的旧创建→激活→初始化→免密登录 UI | **22/22** |
| 改动前管理员节点闸门基线 | **28/28** |
| 导入大小写 / 前端生产构建 | 最终构建及导入检查通过，新产物已进 nginx 镜像；磁盘/容器/HTTP 哈希核对 |
| Python 模型迁移漂移 | No changes detected，无新核心表/迁移 |

API 和 Demo UI 夹具只使用唯一 `Demo-API-*` / `Demo-UI-*` 前缀，新建节点通过受保护
删除 API 自清；不在容器内执行 ORM/SQL 写入清理。测试审计和本地链上存证可能保留。

### 10.4 部署与回滚

两套 Java **必须 clean package**：本轮遇到增量 package 显示成功但 fat JAR 仍包含旧
`ruoyi-framework` 的情况；已检查最终嵌套依赖和容器 SHA256，不以 Maven 提示自证。

- 生命周期最终 JAR SHA256：`35c95dab7de15ba57c5d70b7f2dd77cdf501dbf70889c88205890e0bd5b5064a`
- Generate 最终 JAR SHA256：`f0f1b59a1e7017227853022f0046523b9e331757dc8d09ac6626a050ca721a8a`
- 原 JAR 回滚副本：`kms-ops/runtime/{updatedel-java,generate-java}/*.pre-demo-20261009.jar`
- 原前端回滚目录：`kms-ops/front/updatedel.pre-demo-20261009/`；后续迭代副本带额外后缀。
- 回滚副本/`.env` 通过本机新增 `.dockerignore` 排除，不进入构建上下文。
  仓库已有 `**/.dockerignore` 忽略规则，此本机文件不在 Git 变更清单；其它部署需保留同样的排除项。

本机显式启用（仓库根）：

```powershell
docker compose -f kms-ops/docker-compose.yml -f kms-ops/docker-compose.demo.yml up -d --build
node tools/verify-demo-api.mjs
node tools/verify-demo-entry-ui.mjs
```

关闭反证时额外叠加 `kms-ops/docker-compose.demo-disabled.yml`；去掉它恢复本机 Demo。
普通部署只使用基础 `docker-compose.yml`，默认不启用、不发布演示端口。

### 10.5 如实记录的限制与残留

- Demo 不具备正式操作者身份认证保证，只用于隔离、本机课题展示；禁止生产数据库/公网启用。
- 已在 Standalone 初始化的节点，其原私钥不会自动复制到 Demo；Demo 无对应材料时正确阻止。
- `verify-login-identity.mjs` 在改动前即为 **5/9**：仍按已经取消的节点密码登录及旧文案填写。
  本轮未为凑绿恢复旧密码机制，也未修改它的断言；当前有效旧 UI 测试 13/13、22/22 已通过。
- 旧 UI 回归脚本按原行为留下本轮节点 `Node-UI-UBCL6`、`Node-UI-6OVAS`、
  `Node-E2E-06PSW9`。自动删除请求被权限检查拒绝，未绕过；可在管理员节点页核对后手动删除。
- 此轮未声称重跑 KMS-001～016 的全部历史脚本；上述表格只列真正执行的检查。

---

## 11. Fabric 国密 DID 离线适配（2026-10-09，未切换真实链）

用户确认没有实际 connection/MSP/TLS/通道链码参数及测试 DID，选择先做代码适配。
**本轮不是在线 Fabric 替换成功证明**；未连接/写入真实 Fabric，未应用现有数据库迁移，
未改变运行默认后端、未重置数据库、未修改供应方 JAR、未自动提交。

### 11.1 已实现

- 新 `kms-fabric-did/` 独立 Java 8 Bridge，供应方 SDK/定制 Gateway/国密 provider
  用原 Maven 包；thin JAR + 全部原签名 lib，避免与现有 FISCO JVM 混装。
- 内部认证、懒加载、关闭/缺配置诊断、原样 DID 读取、严格 metadata、
  prepare → durable nonce/txId → submit → 交易验证/metadata 回读接口。
- 新 `ChainKeyBinding` / `0026_chain_key_binding` / durable outbox，公钥和版本取真实
  NodeLongTermKey。覆盖首次登记、轮换（含旧版退役）、回收，唯一约束/节点锁、
  租约、同作用域顺序，链失败不回滚本地已核验私钥/ACTIVE 状态，也不假称上链。
- `KMS_CHAIN_BACKEND=legacy|fabric-did` 默认 legacy。Java generate/updatedel FISCO、
  Python Web3/BlockchainKDS 的构造/写入、旧初始化脚本/管理 GET 自动同步均有闸门；
  不用修改 BlockchainConfig 合约地址（旧 save 会清全部交易/重置节点）。
- API `chainBackend`/每版本 `chainBinding`，公钥页面独立显示 DID 绑定状态。
  `CONFIRMED` 要求原 txId 有效、DID/chainId/digest/metadata 精确匹配，不把 SDK String 返回值当 txId。
- 外置只读安全材料目录、默认关闭的可选 Compose profile、Bridge 构建镜像定义；
  已准备新 `kms-ops/runtime/fabric-did/app.jar + lib`，没有覆盖原服务运行产物。

### 11.2 实测与边界

| 检查 | 当前结果 |
|---|---|
| Bridge Maven/单测 | clean package，17 项离线 tests 全通过；fake SDK 只在测试源码 |
| 主会话实际 JVM/HTTP | `tools/verify-fabric-bridge-offline.mjs` **8/8**，关闭/未配置/认证失败/不调用实链 |
| Java 现有服务 | 生命周期 18 项、生成 6 项全部通过，含新增 8 项旧链保护；两套 clean package 成功 |
| Python 旧链副作用入口 | **9/9**，源码入口 + mock；无 django.setup、真实数据库或网络 |
| Python Outbox/登记/回读 | 隔离 :memory: SQLite 最终 **45/45** 通过，含事务回滚、幂等、HTTP 模拟、原 txId、namespace、准备阶段崩溃恢复、删除源记录保留证据/阻止新提交及历史 keyRef 不可冒用 |
| 前端/Compose | 最终前端生产构建和大小写检查通过；可选 profile config --quiet 通过 |
| Docker/MySQL/实链 | 用户启动 Docker 后已补建 Bridge 镜像，临时容器 **5/5**、无网络容器 Python **45/45 + 9/9** 通过；未迁移现有库、未切换真实链，完整新 UI 及真实 Fabric TLS/metadata/交易仍未声称验证 |

主机无 Django 时已获用户许可建立 `.omc/fabric-test-venv`，只安装仓库版本的测试依赖；
默认镜像源 TLS EOF 改用官方 HTTPS 成功，**没有关闭 TLS 校验或改全局 Python**。
SQLite 证明应用事务/约束行为，不证明 MySQL 的并发锁语义。

### 11.3 后续入口与限制

详细交接：根目录 `FABRIC_DID_INTEGRATION.md`、`kms-fabric-did/README.md`；
安全目录说明：`kms-ops/fabric-did-secrets/README.md`。

当前支持受限 create-only 版本/事件 DID 绑定，稳定节点最新投影、DID 更新/停用、
完整旧生命周期事件等价尚为 UNSUPPORTED；不得把普通接口“成功返回”改口成这些能力已实现。
DID 管理 SM2 公钥与业务四算法公钥分离；不生成临时新管理者替代既有 DID 所有者。

链方仍需实际 connection.json、应用 MSP enrollment 证书/匹配私钥、TLS CA/GM 配置、
channelName/mspId/chaincodeId/methodId、原样只读测试 DID，以及 metadata JSON/长度/
还原/命名空间/签名/交易归属/单写者与 CAS 策略。先只读验证，再单独批准本应用测试
命名空间写入，最后确定迁移与切换；不覆盖链方给的既有 DID，不开发新业务链码。

---

## 12. 全部真实链写入已暂停（2026-10-09，运行配置已生效）

用户要求公网链地址未提供前，所有真实上链暂不执行。新增独立于后端选择的
`KMS_CHAIN_WRITES_ENABLED=false`（代码默认 false），同时链 Kafka 消费要求
`KMS_CHAIN_CONSUMER_ENABLED=true` 才可恢复；仅打开写开关不会自动重放历史队列。

- 三个写链后端经用户明确维护许可先停止，现已用新镜像全部恢复。
- 两 Java 运行容器 writes/consumer 均为 false，Updatedel chain-sync/旧 chain-consumer 也 false。
- Python 运行进程确认 `legacy PAUSED`；暂停时不构造 Web3/FISCO/DID 客户端，不部署合约。
- 旧事件端点实测返回业务码409、`PAUSED/CHAIN_WRITES_PAUSED`、无chainHash；不伪造成功。
- Fabric prepare/submit/worker 全局暂停优先；outbox 保留公开量，不 claim/发 HTTP，不改已有确认。
- 本地密钥、版本、回收/分发和操作审计保留，公钥页独立提示“真实上链已暂停”。

本机 `.env` 的直接读取被明确权限规则拒绝，未绕过、未修改该文件；使用最后叠加的
`kms-ops/docker-compose.chain-paused.yml` 强制暂停，无论 `.env` 原值为何。当前部署命令：

```powershell
docker compose -f kms-ops/docker-compose.yml -f kms-ops/docker-compose.demo.yml -f kms-ops/docker-compose.chain-paused.yml up -d --build
```

暂停覆盖对 Django 显式 gunicorn入口+空command，不顺带执行 start.sh 的0026迁移。
数据库/Redis/Kafka/链节点未停止未清理；保留旧业务队列/历史证据，不自动补发。
原JAR/前端有 `pre-chain-paused-20261009` 回滚副本（仅本地，不进 Git）。

验收：Python事务47/47与入口10/10，Java新增暂停边界9+7项及既有Demo测试通过，
独立Bridge22项通过，暂停容器8/8；恢复后的旧节点登录13/13、四算法完整流程22/22。
专用回归节点 `Node-E2E-0KHO6D` 实测 ACTIVE，0非空链哈希、0链交易（只读核对）。
运行 JAR SHA256：Generate `faa3588e181582767166e8153ca104b0661953490a90ad8a056c83bba4a8d851`，
Updatedel `67faa271317f96b9859ef051c9ea6c3483168eec89c946f9974335958a097a58`；与容器内一致。

恢复真实链、启用链监听、处置历史任务需用户再次明确确认。此轮新改动未自动提交，
上一次已提交快照仍为 `281d28b8`，不覆盖该提交。

### 后续提交与默认启动固化（用户明确要求推送）

已提交并正常快进推送 `origin/v1`：`a693c3be25467b2afc863b0c2194d9efee72b830`
（`fix(ops): 全系统默认不上链启动并暂停所有链写入口`）。远端 refs/heads/v1 实际哈希与本地相同，没有强推/关证书校验；Windows schannel 握手失败后仅本次命令换 OpenSSL TLS 后端成功。

基础Compose及可选Fabricprofile现在是固定false，不依赖最后叠加暂停文件，也不被.env或宿主true覆盖。
`start.sh` 不自动部署合约/同步模板账户，`rebuild-env.sh` 保留旧链live历史。默认普通启动：
`docker compose -f kms-ops/docker-compose.yml up -d --build`；需要Demo时加demo.yml，仍不上链。
维护专用chain-paused.yml只用于额外跳过尚未审批的数据库迁移，不再是关链的必要条件。

配置反证 `tools/verify-no-chain-config.mjs` **25/25**，Python47+10复验、Bash两个脚本语法与gitdiffcheck均通过。
当前Java运行开关全false，PythonPAUSED。已跟踪文件无剩余diff；四份原本本地进度/参考文档留untracked，不纳入远端。

### 12.1 0027 迁移、镜像重构与业务数据清理（2026-10-09）

- 已在启动新后端前完成两库私有备份并恢复到临时库验证；清理前再次备份并校验 SHA-256。
- `pqkds.0027_split_keygen_public_provenance` 已在真实 `falcon_kds` 应用，`showmigrations` 与 `makemigrations --check` 均通过。
- Java 使用项目 Docker Maven/JDK 完成构建；Go、前端、Django、Nginx 镜像均已重建并切换运行。
- 按限定范围清理 KMS 业务数据，保留 `kms.sys_user/sys_role/sys_menu/sys_config` 及 PQKDS 基础配置；清理后节点、长期密钥、会话、池项、分发、授权、链审计和旧 `kms.keymanage` 均为 0。
- Demo 通过 `docker-compose.demo.yml` 开启，仅发布 `127.0.0.1:8088`；基础 80 入口仍可用。
- Java/Python/Nginx 的链写入与消费者开关仍固定为 `false`；`verify-no-chain-config.mjs` 25/25 通过。
- 当前镜像摘要：Django `sha256:200474257eb3`、Nginx `sha256:2e8bf87a224d`、Generate Java `sha256:85d4828f9963`、Updatedel Java `sha256:616699e02c92`；切换前旧 Django 镜像摘要为 `sha256:cbed4b0987ec`，旧 Nginx 为 `sha256:02b3ca9afc6f`。

### 12.2 UI 补充计划（车道 A）开工：KMS-017 关闭（2026-10-10）

- 新批次依据 `doc/kms-017-023-ui-supplement-plan.md`（车道 A：017 → 018 → 021 → 020-Python 半；
  并行度与热点文件见该文 §7.1）。三份只读侦察报告固化在 `doc/ui-supplement-recon/`。
- **KMS-017 已关闭**，提交 `cfbb29f9`（v1 分支，未推送）：修
  `user_distribution_views._safe` 未定义（**≥1 条批次即 NameError→500**；
  库中 0 条批次正是它长期不可见的全部原因）+ crossDomain 页读不出
  `{items,total}` 的静默空表（service 层 unwrap 后不是数组也不是 `results`）。
- 新脚本 `tools/verify-batches-read.mjs` **20/20**：空账号 200 空数组、
  有批次 200、items/total 与库计数一致、sessionCount 的 0 与 2 两态分别对齐
  `LIKE '<batchId>-%'` 库计数、真浏览器 `/updatedel/distgov/crossdom` 表格行数
  与统计卡由接口数据渲染、种数据自建自清（left=0）。
- 部署实证：dvadmin3-django 与 nginx 镜像重建；产物 md5 磁盘=容器=HTTP 一致；
  容器内 `grep 批次统计项` 证明跑的是新代码。
- 施工环境事实：本机栈以 `docker-compose.yml + docker-compose.chain-local.yml`
  启动（链写入当前 **启用**，legacy 后端）；npm 经 cmd.exe 找不到 node 时，
  显式 `export PATH="/d/Users/AllenR/AppData/Local/Author Software/nvm/installs/v25.6.1:$PATH"` 后构建。
