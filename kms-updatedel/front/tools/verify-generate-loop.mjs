/**
 * 生成回路的验收：计划 §7 阶段 1 的四条完成标准（KMS-005）。
 *
 * 判据为什么必须是这四个动作，而不是"接口返回 200"
 * ------------------------------------------------
 * 计划 §13 写着「只修改页面而没有后端约束，或只增加接口而没有节点端真实调用，
 * 均不得关闭任务」。阶段 1 的四条标准没有一条能用返回值证明：
 *
 *   ① 新建节点服务端四个私钥列为空       —— 得**读库看列长**；
 *   ② 本地私钥不可导出、刷新后仍可使用   —— 得**真的导出一次**、再**真的解一个信封**；
 *   ③ 两个节点同名、同一浏览器不串用     —— 得**造出同名两节点**，两边各自对账；
 *   ④ 新的逻辑密钥不复用旧 SM2/SSCL 的 u —— 得比**标量本身**（u 相同则 u·G 必然相同）。
 *
 * 调用顺序与模块都取自生成页（views/generate/create.vue），不另发明一条路径：
 *     cryptoProvider.generate（私钥只在这里产生、只在这里封存）
 *   → POST /node-self/keys/（过网的只有公钥 + 设备指纹 + keyId/版本）
 *   → 重新拉取平台登记 → compareNodeKeys 对账（与生成页、密钥历史页同一份判据）
 *
 * 本脚本不驱动 DOM（仓库暂无浏览器驱动依赖）：它证明的是"这条链路成立"，
 * 与 verify-node-init-ui.mjs 是同一条分工。
 *
 * ⚠️ 会**建真节点、写真数据**（falcon_kds 与浏览器存储都会变），只在本地验证环境跑。
 */
import { PQKDS, api, isOk, title, makeReporter, adminLogin, newNodeSession, cryptoProvider } from './lib/node-session.mjs'
import { sqlScalar } from '../../../tools/lib/mysql.mjs'
import * as nodeStore from '../src/utils/crypto/node-key-store.js'
import { deviceKeyRef } from '../src/utils/crypto/device-credential.js'
import { toHex } from '../src/utils/crypto/browser-provider.js'
import { compareNodeKeys } from '../src/utils/crypto/node-key-compare.js'

const { check, info, finish } = makeReporter()

// =============================================================================
// 工具
// =============================================================================

/** 服务端四个私钥列。判据①的对象就是这四个。 */
const PRIVATE_COLS = ['kyber_private_key', 'falcon_private_key', 'gm_private_key', 'sscl_private_key']
/** 四个公钥列。用作**对照**：证明"私钥列为空"不是"什么都没发生"。 */
const PUBLIC_COLS = ['kyber_public_key', 'falcon_public_key', 'gm_public_key', 'sscl_public_key']

/**
 * 读库里某节点若干列的**长度**。
 *
 * 为什么用 `CHAR_LENGTH` 而不是"是否为空"：长度是**可比较的数字**，
 * 能直接回答"是 0 还是非 0"；而"空"在 NULL 与 '' 之间摇摆，一旦某列
 * 从 blank=True 变成 null=True，`IS NULL` 这类断言就会静默失效。
 * 这里返回如 `kyber_private_key=0|falcon_private_key=0|...` 的串，
 * 原样打进证据里，看报告的人不需要再查一遍库。
 */
function columnSummary(nodeId, columns) {
  const parts = columns.map((c) => `CONCAT('${c}=', CHAR_LENGTH(IFNULL(${c}, '')))`).join(', ')
  return sqlScalar(`SELECT CONCAT_WS('|', ${parts}) FROM falcon_kds.dvadmin_pqkds_nodes WHERE node_id='${nodeId}';`) || ''
}

/** 摘要里每一列的长度都是 0。节点行不存在时摘要为空串，这里恒为 false —— 不会是"假通过"。 */
const allZero = (summary) => summary.includes('=') && summary.split('|').every((p) => p.endsWith('=0'))

/** ArrayBuffer / 类型化数组 → 小写 hex；其它类型返回空串。 */
function bytesOf(value) {
  if (value instanceof ArrayBuffer) return toHex(new Uint8Array(value))
  if (ArrayBuffer.isView(value)) return toHex(new Uint8Array(value.buffer, value.byteOffset, value.byteLength))
  return ''
}

/** 把一条密封记录的所有字段摊成"可搜索的文本"，用于找明文是否泄漏进了记录。 */
function recordHaystack(record) {
  return Object.entries(record || {})
    .map(([, v]) => (typeof v === 'string' ? v : bytesOf(v) || String(v ?? '')))
    .join('|')
    .toLowerCase()
}

/**
 * **绕过 store 的 API**，直接读 IndexedDB 里那条记录。
 *
 * 为什么非要直读：`unsealSecret` 是"能解开"的证明，但证明不了"库里存的
 * 到底是密文还是明文"—— 两种实现下 `unsealSecret` 都会成功。判据②说的是
 * "本地私钥**不可导出**"，那就得看**原样的存储形态**。
 *
 * 打开时不传版本号：用的是库里现有的版本，**绝不触发 upgrade**。
 * （传错版本的 open 会走进升级路径，能把"读失败"变成"数据没了"。）
 */
async function readRawRecord(keyRef) {
  const storeName = 'keys' // STORE_KEYS 未导出（见 node-key-store.js 尾部的导出清单）
  const db = await new Promise((resolve, reject) => {
    const rq = indexedDB.open(nodeStore.DB_NAME)
    rq.onerror = () => reject(new Error(rq.error?.message || '打开本地密钥库失败'))
    rq.onsuccess = () => resolve(rq.result)
  })
  try {
    if (!db.objectStoreNames.contains(storeName)) throw new Error(`密钥库里没有 ${storeName} 这个 store`)
    const record = await new Promise((resolve, reject) => {
      const rq = db.transaction(storeName, 'readonly').objectStore(storeName).get(keyRef)
      rq.onsuccess = () => resolve(rq.result)
      rq.onerror = () => reject(new Error(String(rq.error?.message || '读记录失败')))
    })
    return record ?? null
  } finally {
    db.close()
  }
}

async function secretHex(keyRef, module = nodeStore) {
  return new TextDecoder().decode(await module.unsealSecret(keyRef))
}

/** 生成页的两次动作：本机生成 → 只上报公钥。返回 `{generated, res}`。 */
async function generateAndRegister(session, algorithm, options = {}) {
  const generated = await cryptoProvider.generate(algorithm, { nodeId: session.nodeId, ...options })
  const res = await api(PQKDS, '/node-self/keys/', {
    method: 'POST',
    token: session.token,
    body: {
      algorithm,
      publicKey: generated.publicKey,
      // 设备公钥指纹（不是浏览器随机 id）；服务端拿它与 Node.key_device_id 比对
      deviceId: session.fingerprint,
      keyId: generated.keyId,
      keyVersion: generated.version,
      securityLevel: options.variant ? String(options.variant) : undefined
    }
  })
  return { generated, res }
}

const serverKeys = async (session) => (await api(PQKDS, '/node-self/keys/', { token: session.token })).body?.data?.keys || []

// =============================================================================
// 判据①（前半）：建出来的节点，服务端一个私钥都没有
// =============================================================================
title('1. ★ 判据①：新建节点的服务端四个私钥列为空')
const admin = await adminLogin()
// 名字在 ③ 里还要用：两个节点**取同一个名字**，那是判据③的前提条件
const SHARED_NAME = `同名节点-${Date.now().toString(36)}`
const a = await newNodeSession(admin, { prefix: 'NGL', name: SHARED_NAME, domainId: 'dgl', permissionLevel: 'L2' })
const NODE_A = a.nodeId

const privateAtCreate = columnSummary(NODE_A, PRIVATE_COLS)
check('库里查得到这个新节点', privateAtCreate.includes('='), `node_id=${NODE_A}`)
check('★ 建节点时四个私钥列长度全为 0（私钥从不上服务端）', allZero(privateAtCreate), privateAtCreate)
const publicAtCreate = columnSummary(NODE_A, PUBLIC_COLS)
check('此时四个公钥列也还是空的（后面拿它当对照）', allZero(publicAtCreate), publicAtCreate)

// =============================================================================
// 判据①（后半的真实风险）：走完一整轮生成登记，私钥列仍为空
// =============================================================================
title('2. 按生成页的顺序走：本机生成 → 只把公钥送上平台')
const FIRST = [['SM2', {}], ['SSCL', {}], ['KYBER', { variant: 768 }], ['FALCON', {}]]
const firstKeys = {}
for (const [algo, opts] of FIRST) {
  const { generated, res } = await generateAndRegister(a, algo, opts)
  firstKeys[algo] = generated
  check(`${algo} 本机生成并登记`, isOk(res.body) && res.body?.data?.keyId === generated.keyId,
    `keyRef=${generated.keyRef} 服务端回传 keyId=${res.body?.data?.keyId}`)
}
const fin = await api(PQKDS, '/node-self/init/', { method: 'POST', token: a.token })
check('四套齐备 → 节点初始化完成（ACTIVE）', isOk(fin.body) && fin.body?.data?.node?.status === 'ACTIVE',
  `status=${fin.body?.data?.node?.status}`)

title('3. ★ 判据①（真正的风险在生成之后）：私钥列仍为 0，而公钥列已写入')
const privateAfter = columnSummary(NODE_A, PRIVATE_COLS)
check('★ 一整轮生成登记走完，四个私钥列长度仍全为 0', allZero(privateAfter), privateAfter)
const publicAfter = columnSummary(NODE_A, PUBLIC_COLS)
check('四个公钥列都已写入（对照：私钥列为空不是因为什么都没发生）', !allZero(publicAfter), publicAfter)

// =============================================================================
// 判据②（之一）：不可导出
// =============================================================================
title('4. ★ 判据②之一：私钥不可导出')
check('保护密钥本身不可导出（不可导出的 AES-GCM CryptoKey，密文只在本机解开）',
  await nodeStore.assertProtectorNotExportable(),
  'crypto.subtle.exportKey(raw, protector) 被拒')

const sm2Ref = firstKeys.SM2.keyRef
const record = await readRawRecord(sm2Ref)
check('直读本地密钥库这条记录，只有密文与 IV',
  Boolean(record) && Boolean(record.sealed) && Boolean(record.iv) && Boolean(record.publicKey),
  record ? `字段：${Object.keys(record).join(',')}` : '（没读到记录）')
const haystack = recordHaystack(record)
const sm2Hex = await secretHex(sm2Ref)
check('★ 记录的任何字段里都搜不到明文私钥（存储形态就是密文）',
  sm2Hex.length > 0 && haystack.length > 0 && !haystack.includes(sm2Hex.toLowerCase()),
  `明文 ${sm2Hex.length} 字符；扫描的库内文本 ${haystack.length} 字符；sealed=${bytesOf(record?.sealed).length / 2} 字节`)

const devicePrivate = await nodeStore.getDevicePrivateKey(deviceKeyRef(NODE_A))
let deviceExportable = true
try {
  await crypto.subtle.exportKey('pkcs8', devicePrivate)
} catch {
  deviceExportable = false
}
check('★ 设备私钥（登录凭据）同样不可导出', Boolean(devicePrivate) && deviceExportable === false,
  'crypto.subtle.exportKey(pkcs8, devicePrivateKey) 被拒')

// =============================================================================
// 判据②（之二）：刷新页面后仍可使用
// =============================================================================
title('5. ★ 判据②之二：刷新页面后仍可使用')
// 为什么这样就是"刷新页面"：`getOrCreateProtector()` 没有模块级缓存，每次都从
// IndexedDB 取那把不可导出的保护密钥，provider 也不在内存里存任何私钥。
// 所以刷新后能不能用，只取决于「库里的密文 + 库里的保护密钥」——
// 而下面这个全新模块实例（内存与旧实例零共享）恰好就是那个状态。
const fresh = await import(`../src/utils/crypto/node-key-store.js?fresh=${Date.now()}`)
const refs = FIRST.map(([algo]) => firstKeys[algo].keyRef)
const found = await Promise.all(refs.map((r) => fresh.hasSecret(r)))
check('刷新后四把私钥都还在（按 keyRef 精确命中）', found.every(Boolean), `${found.filter(Boolean).length}/4`)

// "读出来了"与"能用"是两件事 —— 判据说的是"仍可使用"。
// 拿刷新后读出的标量，真解一个按**登记公钥**加密的信封，这才算数。
const { SM2 } = await import('gm-crypto')
const { decryptEnvelope } = await import('../src/utils/sm2-envelope.js')
const probe = `kms-refresh-${Date.now()}`
const freshSm2Hex = await secretHex(sm2Ref, fresh)
// ⚠️ gm-crypto 的 encrypt 返回 ArrayBuffer，C1 **不带 04 前缀**，要补回来
//    （否则 decryptEnvelope 会报"C1 不是未压缩点"，听起来像"密钥不对"）
const ciphertext = '04' + toHex(new Uint8Array(SM2.encrypt(probe, firstKeys.SM2.publicKey)))
const recovered = new TextDecoder().decode(decryptEnvelope({ algorithm: 'sm2', ciphertext }, freshSm2Hex))
check('★ 用刷新后读出的 SM2 私钥解开按登记公钥封的信封', recovered === probe,
  recovered === probe ? '明文逐字节相同' : `解出：${recovered.slice(0, 40)}`)

for (const [algo] of FIRST) {
  const result = await cryptoProvider.selfTest(algo, firstKeys[algo].keyRef)
  check(`${algo} 自检（真实往返，不是查字段）`, result.ok, result.detail)
}

// =============================================================================
// 判据③：两个同名节点、同一浏览器，密钥不串用
// =============================================================================
title('6. ★ 判据③：两个同名节点、同一浏览器，密钥不串用')
const b = await newNodeSession(admin, { prefix: 'NGL', name: SHARED_NAME, domainId: 'dgl', permissionLevel: 'L2' })
const NODE_B = b.nodeId
check('造出两个同名节点（判据③的前提；node_id 才是唯一键）',
  a.name === b.name && NODE_A !== NODE_B, `name=${SHARED_NAME}；${NODE_A} vs ${NODE_B}`)
check('同浏览器里两个节点的设备指纹不同（各有各的设备凭据）', a.fingerprint !== b.fingerprint,
  `${a.fingerprint.slice(0, 12)}… vs ${b.fingerprint.slice(0, 12)}…`)

const selfA = await api(PQKDS, '/node-self/', { token: a.token })
const selfB = await api(PQKDS, '/node-self/', { token: b.token })
check('同名不影响身份：两个令牌各自读回自己的 nodeId',
  selfA.body?.data?.node?.nodeId === NODE_A && selfB.body?.data?.node?.nodeId === NODE_B,
  `A=${selfA.body?.data?.node?.nodeId} B=${selfB.body?.data?.node?.nodeId}`)
check('B 绑定的设备是 B 自己那把（没有沿用 A）',
  selfB.body?.data?.node?.keyDeviceId === b.fingerprint,
  `B 的 keyDeviceId=${String(selfB.body?.data?.node?.keyDeviceId).slice(0, 12)}…`)

// ★ 这条是本判据的核心：B 还什么都没生成时，本机必须答得出来"B 没有材料"。
//   若这里 present=true（比如按名字或前缀匹配到了 A 的材料），
//   后面所有"对账一致"的结论都是拿 A 的私钥得出的。
const beforeB = await cryptoProvider.inspectNodeKeys(NODE_B)
check('★ B 尚未生成时，本机认得出"B 没有材料"（没有串到同名的那台）',
  beforeB.present === false, `algorithms=${JSON.stringify(beforeB.algorithms)}`)
const aStillFour = await cryptoProvider.inspectNodeKeys(NODE_A)
check('激活 B 没有动到 A 的本机材料', aStillFour.present === true && aStillFour.algorithms.length === 4,
  `A 的 algorithms=${JSON.stringify(aStillFour.algorithms)}`)

const bSm2 = await generateAndRegister(b, 'SM2')
check('B 生成并登记一把 SM2', isOk(bSm2.res.body) && bSm2.res.body?.data?.keyId === bSm2.generated.keyId,
  `B 的 keyId=${bSm2.generated.keyId}`)

const aLocal = await cryptoProvider.inspectNodeKeys(NODE_A)
const bLocal = await cryptoProvider.inspectNodeKeys(NODE_B)
check('本机材料按 nodeId 精确分区（各自只列自己的）',
  aLocal.keys.every((k) => k.nodeId === NODE_A) && bLocal.keys.every((k) => k.nodeId === NODE_B),
  `A ${aLocal.keys.length} 条 / B ${bLocal.keys.length} 条`)
const aKeyIds = new Set(aLocal.keys.map((k) => k.keyId))
check('两节点的 keyId 集合不相交', !bLocal.keys.some((k) => aKeyIds.has(k.keyId)),
  `B 的 keyId ${bLocal.keys.map((k) => k.keyId).join(',')} 不在 A 的 ${aKeyIds.size} 条里`)

const srvA = await serverKeys(a)
const srvB = await serverKeys(b)
const srvAIds = new Set(srvA.map((k) => k.keyId))
const srvBIds = new Set(srvB.map((k) => k.keyId))
check('★ 服务端按令牌分区：A 的列表里没有 B 的 keyId', !srvAIds.has(bSm2.generated.keyId),
  `A 有 ${srvAIds.size} 行，B 那把不在其中`)
check('★ 服务端按令牌分区：B 的列表里只有自己的那一把', srvBIds.size === 1 && srvBIds.has(bSm2.generated.keyId),
  `B 有 ${srvBIds.size} 行`)
check('B 的登记没有改到 A 在产的那把（A 四个算法各有 ACTIVE）',
  FIRST.every(([algo]) => srvA.filter((k) => k.algorithm === algo && k.allowsNewWork).length === 1),
  ['SM2', 'SSCL', 'KYBER', 'FALCON'].map((al) => `${al}:${srvA.filter((k) => k.algorithm === al && k.allowsNewWork).length}`).join(' '))

// 两个节点各自的平台行与本机材料对得上（页面表格用的就是这份判据）
const rowsA = compareNodeKeys({ serverKeys: srvA, localKeys: aLocal.keys })
const rowsB = compareNodeKeys({ serverKeys: srvB, localKeys: bLocal.keys })
check('★ A 的每一行都"平台登记 = 本机持有"（compareNodeKeys 全 MATCH）',
  rowsA.length > 0 && rowsA.every((r) => r.reconcile.ok), `${rowsA.length} 行：${rowsA.map((r) => r.reconcile.state).join(',')}`)
check('★ B 的每一行也都 MATCH，且两表的公钥各是各的',
  rowsB.length === 1 && rowsB.every((r) => r.reconcile.ok) && srvB[0].publicKey !== firstKeys.SM2.publicKey,
  `B 行=${rowsB[0]?.reconcile.state}`)

// =============================================================================
// 判据④：不复用旧 SM2/SSCL 的 u
// =============================================================================
title('7. ★ 判据④：生成新逻辑密钥不复用旧 SM2/SSCL 的 u')
for (const algo of ['SM2', 'SSCL']) {
  const old = firstKeys[algo]
  const { generated: next, res } = await generateAndRegister(a, algo)
  check(`${algo} 新密钥铸了新的 keyId`, next.keyId !== old.keyId, `${old.keyId} → ${next.keyId}`)

  const oldU = await secretHex(old.keyRef)
  const newU = await secretHex(next.keyRef)
  check(`★ ${algo} 新密钥的 u 与旧的不同（不是复用）`, oldU !== newU && newU.length > 0,
    `旧 ${oldU.slice(0, 12)}… 新 ${newU.slice(0, 12)}…`)
  // u 相同 ⇒ u·G 必然相同，所以公钥也必然相同；公钥不同是"没有复用"的第二重证据
  check(`★ ${algo} 新公钥也随之改变（u 相同则 u·G 必相同）`, next.publicKey !== old.publicKey,
    `旧 ${old.publicKey.slice(0, 16)}… 新 ${next.publicKey.slice(0, 16)}…`)

  const rows = await serverKeys(a)
  const rowNew = rows.filter((k) => k.algorithm === algo && k.keyId === next.keyId)
  const rowOld = rows.filter((k) => k.algorithm === algo && k.keyId === old.keyId)
  check(`★ ${algo} 服务端只有一把在产（新的），旧的降为 RETIRED 但仍可解旧信封`,
    rowNew.length === 1 && rowNew[0].allowsNewWork === true && rowNew[0].allowsUnwrap === true &&
      rowOld.length === 1 && rowOld[0].status === 'RETIRED' && rowOld[0].allowsNewWork === false && rowOld[0].allowsUnwrap === true,
    `新=${rowNew[0]?.status} 旧=${rowOld[0]?.status}`)
  check(`${algo} 旧私钥仍留在本机（按它分发的旧信封还要靠它解）`,
    await cryptoProvider.hasKey(old.keyRef), old.keyRef)
}

// 全流程结束时再看一眼判据①：加过密钥、轮换过版本之后，私钥列依然不能有东西
const privateAtEnd = columnSummary(NODE_A, PRIVATE_COLS)
check('★ 全流程结束时再看一眼：四个私钥列依然全为 0', allZero(privateAtEnd), privateAtEnd)
const finalRows = compareNodeKeys({ serverKeys: await serverKeys(a), localKeys: (await cryptoProvider.inspectNodeKeys(NODE_A)).keys })
check('轮换后本机与平台仍逐行对得上（旧版本也各自配对）',
  finalRows.every((r) => r.reconcile.ok), `${finalRows.length} 行全部 MATCH`)

info('四条判据的证据都已落在上面：读库列长、真实导出尝试、刷新后解封、同名双节点对账、标量比对')

finish()
