/**
 * KMS-006 验收：**更新页那条"本地先生成、再登记、最后才切换生产版本"的轮换路径**。
 *
 * 判据为什么是这几个动作，而不是"接口返回 200"
 * ------------------------------------------
 * 计划 §12 阶段 2 的四条完成标准（文档 229-234 行）逐字是：
 *   ① 更新前后 key_id 不变、版本递增；
 *   ② 旧版本不能被误当成当前生产版本；
 *   ③ 回收后的接口返回明确错误码，如 KEY_REVOKED；
 *   ④ 更新、回收事件能够正确进入审计和链上记录。
 * 四条没有一条能用返回值单独证明：
 *   * ① 得**读库** —— 响应里的 keyVersion 只是服务端"它以为落下去的那一个"，
 *     与库里真实的行可以不一致，而两处各自都看着对；
 *   * ② 得**读库**看旧行的 status/active_slot 与 `Node.<算法>_public_key`
 *     物化列 —— "旧版本还被当成生产版本"的表现是分发继续用旧公钥，接口全绿；
 *   * ③ 得**真的**把一把密钥回收掉再拿它更新。⚠️ KMS-006 写作时这一步走的是
 *     临时 .py + docker exec 直调 `revoke_public_key`（当时它全仓没有 HTTP
 *     入口）；**KMS-007 加了 `POST /node-self/keys/revoke/` 之后改走真实入口**。
 *     这不只是"换条路调"：直调注册表绕过了接口层，也就绕过了挂在接口层上的
 *     `record_chain_event` —— 于是判据④的回收那一半当时根本无从验证；
 *   * ④ 得看响应里的 `chainHash`，**并且**承认链上事件按设计不落库表 ——
 *     `record_chain_event` 失败只返回空串、且它在事务之外被调用，所以
 *     "已更新"与"已上链"是两条独立证据，合成一句"成功"会把审计缺口盖掉。
 *
 * 调用顺序与模块都取自更新页
 * -------------------------
 * `views/keyupdate/index.vue` 的 `handleRotate` 是**先本地封存 → 再自检 →
 * 最后才上报**，本文件逐字照做：`cryptoProvider.generate` → `selfTest` →
 * `POST /node-self/keys/` 带 `rotate: true`。
 *
 * 刻意**不**复用 `lib/node-session.mjs` 的 `generateAndRegister`：那个 helper
 * 不带 `rotate` 字段，走的是"这是我当前的公钥"的登记语义 —— 用它测更新，
 * 测的会是另一条路（而且照样全绿）。
 *
 * ⚠️ 会**建真节点、写真数据**（`falcon_kds` 与浏览器存储都会变），
 *    只在本地验证环境跑。
 */
import { fileURLToPath } from 'node:url'
import { dirname } from 'node:path'

import {
  PQKDS,
  api,
  isOk,
  title,
  makeReporter,
  adminLogin,
  newNodeSession,
  cryptoProvider
} from './lib/node-session.mjs'
import { sqlScalar } from '../../../tools/lib/mysql.mjs'
// 静态 import src 模块在这里是安全的：ESM 按**声明顺序**深度优先求值，
// `./lib/node-session.mjs` 排在最前，它的 `import 'fake-indexeddb/auto'`
// 因此先于下面这些模块生效。反过来写（src 在前）会得到
// "indexedDB is not defined"，而那看起来像 crypto 模块坏了。
import { KYBER_PK_LENGTHS } from '../src/utils/crypto/browser-provider.js'
import { RECONCILE, findLocalKey, reconcileRow } from '../src/utils/crypto/node-key-compare.js'

const { check, info, finish } = makeReporter()

const KYBER = 'KYBER'
const VARIANT = 768
const HERE = dirname(fileURLToPath(import.meta.url))

// ---------------------------------------------------------------------------
// 查库
// ---------------------------------------------------------------------------
//: 规范算法名 → `Node` 上的公钥列。**这是 `api_contract.NODE_PUBLIC_KEY_COLUMN`
//: 的副本**，不是新定义。抄错/漂移的后果是可控的：列名不存在时 MySQL 直接报
//: 1054，`sql()` 抛出带真实 stderr 的错误（不静默），不会变成"读回空值"。
const PK_COLUMN = Object.freeze({
  KYBER: 'kyber_public_key',
  SM2: 'gm_public_key',
  SSCL: 'sscl_public_key',
  FALCON: 'falcon_sign_public_key'
})

/**
 * `NodeLongTermKey.node` 的**外键列名是 `node_id`，存的是 `Node` 的整数主键**
 * —— 不是业务编号 `Node.node_id`（模型里是 `ForeignKey(Node)`，无 `to_field`、
 * 无 `db_column`）。
 *
 * ⚠️ 所以按业务编号查长期密钥**必须**走这个子查询。直接写
 *    `WHERE node_id='NKR-XXXX'` 会**恒不命中却不报错**（整数列与字符串比较，
 *    转换后不相等），读回空值，随后的断言就走错分支 —— 而"空"看起来只是
 *    "这个节点还没登记过"。
 */
const ownerId = (nodeId) =>
  `(SELECT id FROM falcon_kds.dvadmin_pqkds_nodes WHERE node_id='${nodeId}')`

const LTK_TABLE = 'falcon_kds.dvadmin_pqkds_node_long_term_keys'

/** 一行长期密钥的三段事实：版本 | 状态 | 生产槽位。取不到返回 null。 */
function ltKeyFact(nodeId, algorithm, keyId, version) {
  // ⚠️ `CONCAT_WS` 会**跳过 NULL**，直接用 `active_slot` 会让"槽位为空"的结果
  //    少一段（`2|RETIRED`），与拼出来的期望串对不上；用 IFNULL 占位。
  return sqlScalar(
    `SELECT CONCAT_WS('|', key_version, status, IFNULL(active_slot, 'NULL')) FROM ${LTK_TABLE} `
    + `WHERE node_id=${ownerId(nodeId)} AND algorithm='${algorithm}' `
    + `AND key_id='${keyId}' AND key_version=${Number(version)};`
  )
}

/** 该算法当前占着生产槽位的 key_id。没有则为 null。 */
function activeKeyIdOf(nodeId, algorithm) {
  return sqlScalar(
    `SELECT key_id FROM ${LTK_TABLE} WHERE node_id=${ownerId(nodeId)} `
    + `AND algorithm='${algorithm}' AND status='ACTIVE';`
  )
}

/**
 * `Node.<算法>_public_key` 物化列是否**逐字节**等于给定值。
 *
 * ⚠️ 比较两侧都加 `BINARY`：MySQL 默认排序规则（`*_general_ci`）**不区分
 *    大小写**，不加的话 `'AB' = 'ab'` 为真 —— 而这条断言的全部意义就是
 *    "逐字节相同"，大小写不同正是它该抓到的那类不一致。
 */
function nodeColumnIs(nodeId, algorithm, expected) {
  const column = PK_COLUMN[algorithm]
  return sqlScalar(
    `SELECT (BINARY IFNULL(${column}, '') = BINARY '${expected}') `
    + `FROM falcon_kds.dvadmin_pqkds_nodes WHERE node_id='${nodeId}';`
  ) === '1'
}

/**
 * 公钥的**存储形式**：Kyber 存 base64、其余存小写 hex
 * （见 `node_service.store_node_public_key`）。
 *
 * ⚠️ 拿 hex 去比 Kyber 的列永远不相等 —— 而"物化列与长期密钥表不一致"是个
 *    很吓人的结论，实际只是编码不同。这里做转换，不靠人去记。
 */
const storedForm = (algorithm, hexPublicKey) => {
  const hex = String(hexPublicKey || '').toLowerCase()
  return algorithm === 'KYBER' ? Buffer.from(hex, 'hex').toString('base64') : hex
}

// ---------------------------------------------------------------------------
// 工具
// ---------------------------------------------------------------------------
const register = (session, algorithm, material, extra = {}) =>
  api(PQKDS, '/node-self/keys/', {
    method: 'POST',
    token: session.token,
    body: {
      algorithm,
      publicKey: material.publicKey,
      securityLevel: extra.securityLevel,
      deviceId: session.fingerprint,
      keyId: material.keyId,
      keyVersion: material.version,
      ...(extra.rotate ? { rotate: true } : {})
    }
  })

const errCodeOf = (body) => body?.data?.error_code || '(无 error_code)'
const serverKeys = async (session) =>
  (await api(PQKDS, '/node-self/keys/', { token: session.token })).body?.data?.keys || []

// ---------------------------------------------------------------------------
// 0. 准备
// ---------------------------------------------------------------------------
title('0. 准备：管理员登录 + 两个真节点')
const admin = await adminLogin()
const nodeA = await newNodeSession(admin, { prefix: 'NKR', name: 'KMS-006 轮换', domainId: 'kms006' })
const nodeB = await newNodeSession(admin, { prefix: 'NKB', name: 'KMS-006 槽位', domainId: 'kms006' })
check('两个节点都已激活（各自持有登录令牌）',
  Boolean(nodeA.token && nodeB.token && nodeA.nodeId !== nodeB.nodeId),
  `A=${nodeA.nodeId} B=${nodeB.nodeId}`)
info(`A（走完整轮换）：${nodeA.nodeId}   设备指纹 ${String(nodeA.fingerprint).slice(0, 16)}…`)
info(`B（生产槽位归属 / 回收）：${nodeB.nodeId}`)

// ---------------------------------------------------------------------------
// 1. 部署探针：先证明**跑着的服务端**有 rotate 这段代码，再谈它做得对不对
// ---------------------------------------------------------------------------
// 探针探的不是功能，是**部署**。
//
// 本仓库的后端代码是**打进镜像**的（没有 bind mount），而 `docker cp` 进去的
// 文件只活在容器的可写层 —— 进程不重启就永远 import 不到，磁盘上的文件却是新的
// （md5 都对得上）。这种状态下的表现极具欺骗性：接口照常 200、库里也真的发生了
// 变化，只是 `rotate` 从未被读取（默认 False），于是"更新"静默退化成
// **"带显式版本的登记"** —— 而这两条路径在成功场景下落库**完全一致**
// （旧版降级 RETIRED + 新版 ACTIVE + 物化列指向新版）。
//
// 所以下面第 4 节那些读库断言**不足以**证明走的是更新：服务端根本没有 rotate
// 时它们照样全绿。必须在这里先炸出来，而不是等第 5 节（拿非生产 keyId 去更新）
// 由一条间接的失败去反推 —— 那条链路要绕三节才看得出根因。
//
// 探法用的是 `_as_bool` 的严格性：**认不出的值必须被拒**。旧代码没有这段解析，
// 会把这个值静默忽略掉，于是"被接受"就等价于"服务端没有这段代码"。
//
// `publicKey: '00'` 是占位：`node_self_views` 里 rotate 的解析排在校验与落库
// **之前**（`_as_bool` 在构造 NodeService 之前就抛了），所以这条探针不碰库、
// 不留痕 —— 正是这一点让它能安全地跑在任何用例之前。
const probe = await api(PQKDS, '/node-self/keys/', {
  method: 'POST',
  token: nodeA.token,
  body: { algorithm: KYBER, publicKey: '00', deviceId: nodeA.fingerprint, rotate: 'maybe' }
})
check('★ 部署探针：服务端读不懂 rotate 的值时必须拒绝（证明新代码真的在跑）',
  probe.body?.data?.error_code === 'INVALID_PARAMETER',
  `code=${probe.body?.code} msg=${probe.body?.msg} —— 若这里被"接受"了，说明容器跑的是`
  + '旧代码，下面所有更新用例的结论都不可信（先重建镜像再重跑）')

// ---------------------------------------------------------------------------
// 2. 基线：本机生成 v1 并登记（不带 rotate —— 这是"登记"，不是"更新"）
// ---------------------------------------------------------------------------
title('2. 基线：本机生成 v1 并登记')
const v1 = await cryptoProvider.generate(KYBER, { nodeId: nodeA.nodeId, variant: VARIANT })
const v1Bytes = v1.publicKey.length / 2
check('v1 生成于本机，公钥长度可推断变体',
  KYBER_PK_LENGTHS[v1Bytes] === VARIANT && Number(v1.version) === 1,
  `${v1Bytes} 字节 → Kyber-${KYBER_PK_LENGTHS[v1Bytes]}；keyRef=${v1.keyRef}`)

const v1Test = await cryptoProvider.selfTest(KYBER, v1.keyRef)
check('v1 本机自检通过（自己封、自己解）', v1Test.ok, v1Test.detail)

const v1Up = await register(nodeA, KYBER, v1, { securityLevel: String(VARIANT) })
check('v1 登记成功', isOk(v1Up.body), `code=${v1Up.body?.code} msg=${v1Up.body?.msg}`)
check('库里 v1 是 ACTIVE 且占着生产槽位',
  ltKeyFact(nodeA.nodeId, KYBER, v1.keyId, 1) === `1|ACTIVE|${KYBER}`,
  `读到 ${ltKeyFact(nodeA.nodeId, KYBER, v1.keyId, 1)}`)
check('物化列等于 v1 公钥的存储形式（Kyber 是 base64，逐字节）',
  nodeColumnIs(nodeA.nodeId, KYBER, storedForm(KYBER, v1.publicKey)),
  'Node.<算法>_public_key 与长期密钥表必须同写 —— 两处不一致时哪一处为准取决于谁先读')

// ---------------------------------------------------------------------------
// 3. ★ 判据①：同一 keyId 从 v1 更新到 v2
// ---------------------------------------------------------------------------
title('3. ★ 判据①：更新前后 keyId 不变、版本递增')
const v2 = await cryptoProvider.generate(KYBER, {
  nodeId: nodeA.nodeId,
  keyId: v1.keyId,
  version: Number(v1.version) + 1,
  variant: VARIANT
})
check('v2 在本机封存时沿用同一 keyId、版本 +1',
  v2.keyId === v1.keyId && Number(v2.version) === 2,
  v2.keyRef)

const v2Test = await cryptoProvider.selfTest(KYBER, v2.keyRef)
check('v2 本机自检通过', v2Test.ok, v2Test.detail)

// 自检不过就不上行 —— 这是更新页那条分支的逐字复刻（顺序不可调换）。
let rotateRes = null
if (!v2Test.ok) {
  check('自检未过 → 不上报', false, '本机这一版已封存但没上行；生产版本应当原封不动')
} else {
  rotateRes = await register(nodeA, KYBER, v2, { securityLevel: String(VARIANT), rotate: true })
}
const upd = rotateRes?.body
check('更新请求被接受', isOk(upd), `code=${upd?.code} msg=${upd?.msg}`)
check('★ 响应里的 keyId 与更新前是同一个', upd?.data?.keyId === v1.keyId,
  `响应 keyId=${upd?.data?.keyId}，更新前 ${v1.keyId}`)
check('★ 响应里的版本是 v2', Number(upd?.data?.keyVersion) === 2, `v${upd?.data?.keyVersion}`)
check('响应里的状态是 ACTIVE', upd?.data?.keyStatus === 'ACTIVE', `${upd?.data?.keyStatus}`)
// 上面四条读库/读响应的断言**单独都不足以**证明走的是"更新"：`rotate` 被服务端
// 忽略时，落库结果与更新**完全一致**（旧版降级 + 新版 ACTIVE + 物化列指向新版），
// 而"带显式版本的登记"正是这么落库的。真正的判据只有两处：
//   * 这里这句文案（`node_service` 只在 rotate 分支吐"已更新为 vN"），
//   * 以及第 8 节的 chainHash（挂在 `result['rotated']` 上，登记路径不产生）。
// 断言文案**不是**把文案当契约（前端从不匹配 msg，只认 errorCode）—— 它是响应里
// 唯一能区分"服务端走了哪条分支"的投影。少了这一条，服务端把更新退化成登记时
// 本用例会**全绿**，而那正是"假通过"。
check('★ 走的确实是"更新"而不是"带显式版本的登记"',
  String(upd?.msg || '').includes('已更新'),
  `msg=${upd?.msg} —— 期望"已更新为 v2"；若这里是"已登记"，说明服务端没走 rotate 分支`)

// ---------------------------------------------------------------------------
// 4. ★ 判据②：库里旧版降级、生产槽位与物化列都指向新版
// ---------------------------------------------------------------------------
title('4. ★ 判据②：旧版本不能被误当成当前生产版本')
const v1After = ltKeyFact(nodeA.nodeId, KYBER, v1.keyId, 1)
check('★ v1 已降级为 RETIRED，且 active_slot 被清空',
  v1After === '1|RETIRED|NULL',
  `读到 ${v1After}（active_slot 漏清不报错，只会让唯一约束失效）`)
const v2After = ltKeyFact(nodeA.nodeId, KYBER, v1.keyId, 2)
check('★ v2 是 ACTIVE 且接过生产槽位', v2After === `2|ACTIVE|${KYBER}`, `读到 ${v2After}`)
check('同一算法在库里只有一个 ACTIVE 行',
  Number(sqlScalar(`SELECT COUNT(*) FROM ${LTK_TABLE} WHERE node_id=${ownerId(nodeA.nodeId)} `
    + `AND algorithm='${KYBER}' AND status='ACTIVE';`)) === 1,
  '两个 ACTIVE 是唯一约束 pqkds_ltk_uniq_active_per_node_alg 该拦住的状态')
check('★ 物化列已指向 v2 公钥（分发读的就是这一列）',
  nodeColumnIs(nodeA.nodeId, KYBER, storedForm(KYBER, v2.publicKey)))
check('★ 物化列**不再**等于 v1 公钥', !nodeColumnIs(nodeA.nodeId, KYBER, storedForm(KYBER, v1.publicKey)))

const rowsAfter = await serverKeys(nodeA)
const rowV1 = rowsAfter.find((k) => k.algorithm === KYBER && k.keyId === v1.keyId && Number(k.keyVersion) === 1)
const rowV2 = rowsAfter.find((k) => k.algorithm === KYBER && k.keyId === v1.keyId && Number(k.keyVersion) === 2)
check('接口下发的 v1：不可用于新会话，但仍可解旧信封',
  rowV1?.allowsNewWork === false && rowV1?.allowsUnwrap === true,
  `allowsNewWork=${rowV1?.allowsNewWork} allowsUnwrap=${rowV1?.allowsUnwrap} statusLabel=${rowV1?.statusLabel}`)
check('接口下发的 v2：可用于新会话', rowV2?.allowsNewWork === true, `allowsNewWork=${rowV2?.allowsNewWork}`)
check('接口下发的 v2 公钥与本机这把逐字节相同（比对形式：小写 hex）',
  String(rowV2?.publicKey || '').toLowerCase() === v2.publicKey.toLowerCase(),
  `服务端 ${String(rowV2?.publicKey).slice(0, 24)}… 本机 ${v2.publicKey.slice(0, 24)}…`)

const localA = await cryptoProvider.inspectNodeKeys(nodeA.nodeId)
const mineV2 = findLocalKey(localA.keys, { algorithm: KYBER, keyId: v2.keyId, version: 2 })
const rec = reconcileRow(rowV2, mineV2)
check('★ 本机 ↔ 平台对账：更新后仍判为「一致」', rec.state === RECONCILE.MATCH, rec.text)

// ---------------------------------------------------------------------------
// 5. ★ 判据②（续）：更新一把**不是当前生产版本**的密钥 → 拒绝
// ---------------------------------------------------------------------------
title('5. ★ 判据②：更新非生产 keyId → 拒绝，且生产版本原封不动')
info('节点 B 上先登记两把不同的逻辑密钥（两个 keyId），让第二把接管生产槽位，')
info('再拿第一把去"更新" —— 放行的话生产版本会被换成调用方手里那把。')

const kB1 = await cryptoProvider.generate(KYBER, { nodeId: nodeB.nodeId, variant: VARIANT })
const kB1Up = await register(nodeB, KYBER, kB1, { securityLevel: String(VARIANT) })
check('B 的第一把登记成功', isOk(kB1Up.body), `keyId=${kB1.keyId}`)

const kB2 = await cryptoProvider.generate(KYBER, { nodeId: nodeB.nodeId, variant: VARIANT })
const kB2Up = await register(nodeB, KYBER, kB2, { securityLevel: String(VARIANT) })
check('B 的第二把登记成功，并接管生产槽位',
  isOk(kB2Up.body) && activeKeyIdOf(nodeB.nodeId, KYBER) === kB2.keyId,
  `生产 keyId=${activeKeyIdOf(nodeB.nodeId, KYBER)}`)
check('两条 keyId 确实不同（否则这条用例测的是同一把）', kB1.keyId !== kB2.keyId)

// 拿**已经退居二线**的 kB1 去更新
const stale = await cryptoProvider.generate(KYBER, {
  nodeId: nodeB.nodeId, keyId: kB1.keyId, version: 2, variant: VARIANT
})
const staleUp = await register(nodeB, KYBER, stale, { securityLevel: String(VARIANT), rotate: true })
check('★ 更新被拒（isOk 为假）', !isOk(staleUp.body), `code=${staleUp.body?.code} msg=${staleUp.body?.msg}`)
check('★ 错误码是 KEY_VERSION_MISMATCH', staleUp.body?.data?.error_code === 'KEY_VERSION_MISMATCH',
  errCodeOf(staleUp.body))
check('★ 生产槽位没被换掉 —— 仍是第二把的 keyId',
  activeKeyIdOf(nodeB.nodeId, KYBER) === kB2.keyId,
  `生产 keyId=${activeKeyIdOf(nodeB.nodeId, KYBER)}`)
check('物化列也仍是第二把的公钥',
  nodeColumnIs(nodeB.nodeId, KYBER, storedForm(KYBER, kB2.publicKey)))
check('被拒的请求**没有留痕**：库里没有 kB1 的 v2 行',
  ltKeyFact(nodeB.nodeId, KYBER, kB1.keyId, 2) === null,
  String(ltKeyFact(nodeB.nodeId, KYBER, kB1.keyId, 2)))

// ---------------------------------------------------------------------------
// 6. ★ 本机自检不过就不上行
// ---------------------------------------------------------------------------
title('6. ★ 本机自检不过 → 不上报，服务端 v2 原封不动')
info('做法：本机生成 v3 之后**把它的私钥删掉**，再自检 —— 这正是"本机这一步失败"')
info('在代码里的样子（`selfTest` 把失败当结论返回，不抛错）。')

const v3 = await cryptoProvider.generate(KYBER, {
  nodeId: nodeA.nodeId, keyId: v1.keyId, version: 3, variant: VARIANT
})
await cryptoProvider.destroy(v3.keyRef)
const v3Test = await cryptoProvider.selfTest(KYBER, v3.keyRef)
check('私钥被移除后自检返回 ok=false，且**不抛错**',
  v3Test.ok === false && typeof v3Test.detail === 'string',
  v3Test.detail)
check('本机也没有 v3 的公钥记录可用了（destroy 删的是整条记录）',
  findLocalKey((await cryptoProvider.inspectNodeKeys(nodeA.nodeId)).keys,
    { algorithm: KYBER, keyId: v1.keyId, version: 3 }) === null)

const rowsA2 = await serverKeys(nodeA)
check('未上行：服务端没有 v3 行',
  !rowsA2.some((k) => k.algorithm === KYBER && k.keyId === v1.keyId && Number(k.keyVersion) === 3))
check('未上行：库里没有 v3 行', ltKeyFact(nodeA.nodeId, KYBER, v1.keyId, 3) === null)
check('★ 生产版本仍是 v2（物化列没动）',
  nodeColumnIs(nodeA.nodeId, KYBER, storedForm(KYBER, v2.publicKey)))
check('★ v2 仍占着生产槽位', ltKeyFact(nodeA.nodeId, KYBER, v1.keyId, 2) === `2|ACTIVE|${KYBER}`)

// ---------------------------------------------------------------------------
// 7. ★ 判据③：回收后的接口返回明确错误码 KEY_REVOKED
// ---------------------------------------------------------------------------
title('7. ★ 判据③：回收之后，更新该密钥要报 KEY_REVOKED')
info('回收走**真实回收入口** POST /node-self/keys/revoke/（KMS-007 新增）。')
info('KMS-006 写作时它还不存在：那时 `revoke_public_key` 全仓没有 HTTP 入口，本节只能靠')
info('临时 .py + docker exec 直调注册表 —— 那条路绕过接口层，也就绕过了挂在接口层上的')
info('`record_chain_event`，于是"回收侧的链上事件"根本无从验证（第 8 节那两句话因此改掉了）。')

// ⚠️ 用 nodeB **自己的令牌**调：回收是自助接口，节点身份取自令牌自省，
//    所以撤掉的必然是登录账号对应的那个节点 —— 传 nodeId 的入口根本不存在。
const revokeResp = await api(PQKDS, '/node-self/keys/revoke/', {
  method: 'POST',
  token: nodeB.token,
  body: {
    // ⚠️ `algorithm` 必传：服务端按 (节点, 算法, keyId, 版本) 定位那一行，
    //    且刻意不替调用方推断算法（keyId 跨算法不保证唯一）。缺了它拿到的是
    //    `缺少 algorithm / keyId / keyVersion` —— 而下面的部署探针会把这种
    //    "参数不全"读成"端点没部署"，把排查引向完全错误的方向。
    algorithm: KYBER,
    keyId: kB2.keyId,
    keyVersion: kB2.version,
    reason: 'KMS-006 验收：回收后不可再更新'
  }
})
// 这条同时是**部署探针**：新端点没注册时这里拿到的是 HTTP 404/405，
// 而后面每一条断言都会以"没读到字段"的方式失败 —— 那看起来像逻辑错，
// 实际是跑着的进程里没有这段代码（KMS-006 踩过：容器先启动、文件后 cp 进去）。
check('★ 回收入口存在且执行成功（HTTP 200 + code 200）',
  revokeResp.status === 200 && isOk(revokeResp.body),
  `HTTP=${revokeResp.status} code=${revokeResp.body?.code} msg=${revokeResp.body?.msg}`)
check('库里该行已是 REVOKED 终态',
  String(ltKeyFact(nodeB.nodeId, KYBER, kB2.keyId, kB2.version)).includes('|REVOKED|'),
  String(ltKeyFact(nodeB.nodeId, KYBER, kB2.keyId, kB2.version)))
check('★ 撤的正是生产版本：wasActive=true 且 alreadyRevoked=false',
  revokeResp.body?.data?.revoked?.wasActive === true
  && revokeResp.body?.data?.revoked?.alreadyRevoked === false,
  JSON.stringify(revokeResp.body?.data?.revoked))
check('★ 回收同时清空了物化列（不清的话既有读路径会继续把已回收的公钥当可用，且失败是静默的）',
  nodeColumnIs(nodeB.nodeId, KYBER, ''), '期望 Node.kyber_public_key 为空')

const afterRevoke = await cryptoProvider.generate(KYBER, {
  nodeId: nodeB.nodeId, keyId: kB2.keyId, version: 2, variant: VARIANT
})
const revokedUp = await register(nodeB, KYBER, afterRevoke, { securityLevel: String(VARIANT), rotate: true })
check('★ 更新已回收的密钥被拒（isOk 为假）', !isOk(revokedUp.body),
  `code=${revokedUp.body?.code} msg=${revokedUp.body?.msg}`)
check('★ 错误码是 KEY_REVOKED', revokedUp.body?.data?.error_code === 'KEY_REVOKED',
  errCodeOf(revokedUp.body))
check('回收是终态：没有因此在回收记录之上叠出一个 v2 行',
  ltKeyFact(nodeB.nodeId, KYBER, kB2.keyId, 2) === null)

// ---------------------------------------------------------------------------
// 8. ★ 判据④：审计与链上 —— 更新与回收各一条
// ---------------------------------------------------------------------------
title('8. ★ 判据④：更新与回收各自进了审计与链上')
const chainHash = String(upd?.data?.chainHash || '')
check('★ 更新那一半的链上：响应带回链上交易哈希（非空）', Boolean(chainHash), chainHash || '（空）')
check('★ 库内那一半：该行确已 v2 且 ACTIVE（与链上成不成无关，都必须成立）',
  ltKeyFact(nodeA.nodeId, KYBER, v1.keyId, 2) === `2|ACTIVE|${KYBER}`,
  `读到 ${ltKeyFact(nodeA.nodeId, KYBER, v1.keyId, 2)}`)

const revokeChainHash = String(revokeResp.body?.data?.chainHash || '')
check('★ 回收那一半的链上：响应同样带回链上交易哈希（非空）',
  Boolean(revokeChainHash), revokeChainHash || '（空）')
check('★ 回收那一半的库内：该行已 REVOKED 且记下了回收原因',
  String(ltKeyFact(nodeB.nodeId, KYBER, kB2.keyId, kB2.version)).includes('|REVOKED|')
  && revokeResp.body?.data?.revoked?.revokedReason === 'KMS-006 验收：回收后不可再更新',
  `reason=${JSON.stringify(revokeResp.body?.data?.revoked?.revokedReason)}`)

info('两件事必须分开读：')
info('  · 链上 —— 上面两个 chainHash，只在链上交易成功、且回执里取到生命周期事件时才产生；')
info('  · 库内 —— 上面那两条行状态，`record_chain_event` 在事务**之外**调用，')
info('    失败只返回空串、不回滚已经成立的那次状态变更。所以"已更新/已回收"与"已上链"是两个事实。')
info('链上事件按设计**不落库表**：它不写 `key_operation_record`、也不动 `keymanage.chain_status`，')
info('在 MySQL 里没有可回读的行 —— 能回读的只有上面这些独立证据。')
info('⚠️ 重试路径上 chainHash 空串**不是**审计缺口：`alreadyRevoked=true` 说明上一次回收')
info('   已经上过链，服务端刻意不重复发（同一次回收在链上留多条，"回收了几次"就没答案了）。')
info('   判别要看 `revoked.alreadyRevoked`，不能只看 chainHash 是否为空 —— 回收页的存证标签')
info('   就是按这个分的三态。重试语义由 tools/verify-keyrevoke-impact.mjs 专门验。')

info(`本次真建的节点：${nodeA.nodeId} / ${nodeB.nodeId}`)
info('证据都已落在上面：长期密钥表两行的状态、物化列、两个错误码、以及链上哈希。')
finish()
