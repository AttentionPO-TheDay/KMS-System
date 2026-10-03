/**
 * KMS-014 验收：**权限、审计与链上事件**（计划 §7 阶段 6 的全部判据）。
 *
 * 判据为什么是这几个动作，而不是"接口返回 200"
 * ------------------------------------------
 * 这一阶段有三条独立的主张，每条都可能"看起来成立"：
 *
 *   * **"三个链上事件接通了"** ≠ "接口返回了 chainHash"。第 5/7 节直连
 *     FISCO JSON-RPC（KMS-007 建立的做法：getPastLogs 不可用，按块遍历）
 *     **逐字段核对**：事件类型、keyId（接收方长期密钥行的整数主键）、
 *     nodeId（接收节点）—— 同一锚定口径在三个事件之间必须一致，
 *     否则链上回读答不出"谁的哪把钥匙受了影响"。
 *   * **"五态能区分"** ≠ "状态列多画了几个标签"。第 4 节读会话行的
 *     `evidence_state`，并**先建立再关闭**：关闭后 status 只剩 `closed`，
 *     若五态是从 status 反推的，这一步之后"走到过哪一步"会静默丢失 ——
 *     断言 `evidence_state` 在关闭后**仍然**是五个 true。
 *   * **"越权被拒"** ≠ "回了个错"。第 8/9 节的每一条越权都断言**可编程的
 *     错误码**（`NOT_ENVELOPE_RECIPIENT` / `NOT_SESSION_PARTY` /
 *     `POOL_ITEM_*` 之外的授权拒绝），并单独断言"管理员走同一条路是通的"
 *     —— 没有正对照时，一个恒拒绝的闸门能让越权面全绿。
 *   * **"有审计记录"**：第 8 节在拒绝发生之后查 `dvadmin_system_operation_log`
 *     （`ApiLoggingMiddleware` 的落点），确认那次篡改判定的请求确实留了痕 ——
 *     链上事件是"发生过什么"，HTTP 审计是"谁在什么时候试了什么"，
 *     两者不是一回事。
 *
 * 与其它脚本的关系
 * ---------------
 * KMS-013 的 `verify-pool-consume` 验池子；本脚本验**会话类的链上证据**与
 * **命名空间权限收口**（`/key-pool/*` 从 KMS-013 起是真写端点，此前匿名可达）。
 *
 * ⚠️ 会**建真节点、写真数据、真上链**（开发链，不在意多几条存证）。
 *    结尾第 10 节自建自清。
 * ⚠️ 服务端代码打进镜像：改了后端不重建，第 1 节的探针先失败 —— 刻意如此。
 */
import { execFileSync } from 'node:child_process'
import {
  PQKDS,
  UPDATEDEL_API,
  api,
  isOk,
  title,
  makeReporter,
  adminLogin,
  newNodeSession,
  cryptoProvider
} from './lib/node-session.mjs'
import { sqlScalar, dockerBin } from '../../../tools/lib/mysql.mjs'

const { check, info, finish } = makeReporter()

const KYBER = 'KYBER'
const VARIANT = 768
const DOMAIN = 'kms014'

const NODE_TABLE = 'falcon_kds.dvadmin_pqkds_nodes'
const SESSION_TABLE = 'falcon_kds.dvadmin_pqkds_session_keys'
const POOL_TABLE = 'falcon_kds.dvadmin_pqkds_pre_distributed_keys'
const OP_LOG_TABLE = 'falcon_kds.dvadmin_system_operation_log'

// ---------------------------------------------------------------------------
// FISCO 直连回读（照抄 verify-keyrevoke-impact.mjs 的已验证实现，见那儿的说明：
// getPastLogs 不支持；groupId 是数字；keyId 在 topics 不在 data）
// ---------------------------------------------------------------------------
const FISCO_RPC = 'http://127.0.0.1:8545'
const FISCO_GROUP = 1
/** 合约地址写成**常量**（不从被测系统读 —— 那等于让它自证清白）。 */
const CONTRACT = '0xb7a03cd7da5553239faa9357a795f0c6015fcdda'
const EVENT_TOPIC = '0x22de73619d629ec7133d447cdf4518a474ff2e04167d013fe27d8ae0022716b0'

async function rpc(method, params) {
  const res = await fetch(FISCO_RPC, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ jsonrpc: '2.0', method, params, id: 1 })
  })
  const json = await res.json()
  if (json.error) throw new Error(`${method} 失败：${json.error.message || JSON.stringify(json.error)}`)
  return json.result
}
const word = (hex, i) => BigInt('0x' + hex.slice(i * 64, (i + 1) * 64))
function abiString(hex, i) {
  const off = Number(word(hex, i)) * 2
  const len = Number(BigInt('0x' + hex.slice(off, off + 64))) * 2
  return Buffer.from(hex.slice(off + 64, off + 64 + len), 'hex').toString('utf8')
}
function decodeLifecycleEvent(log) {
  const hex = log.data.slice(2)
  return {
    keyId: BigInt(log.topics[1]),
    eventType: abiString(hex, 0),
    version: Number(word(hex, 1)),
    nodeId: abiString(hex, 2),
    materialHash: abiString(hex, 3)
  }
}
async function scanLifecycleEvents() {
  const head = Number(await rpc('getBlockNumber', [FISCO_GROUP]))
  const events = []
  for (let n = 0; n <= head; n += 1) {
    const block = await rpc('getBlockByNumber', [FISCO_GROUP, '0x' + n.toString(16), true])
    for (const tx of (block.transactions || [])) {
      const receipt = await rpc('getTransactionReceipt', [FISCO_GROUP, tx.hash])
      if (!receipt) continue
      for (const log of (receipt.logs || [])) {
        if (log.topics?.[0] !== EVENT_TOPIC) continue
        if (String(log.address).toLowerCase() !== CONTRACT) continue
        events.push({ txHash: tx.hash, block: n, ...decodeLifecycleEvent(log) })
      }
    }
  }
  return events
}

const orm = (program) => execFileSync(
  dockerBin, ['exec', '-i', '-w', '/backend', 'dvadmin3-django', 'python', '-'],
  { input: program, encoding: 'utf8', env: { ...process.env, MSYS_NO_PATHCONV: '1' } }
)
const ormHeader = `
import os, sys
sys.path.insert(0, '/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
import django
django.setup()
`

const sessionStatus = (sid) =>
  sqlScalar(`SELECT status FROM ${SESSION_TABLE} WHERE session_id='${sid}';`) || ''

// ---------------------------------------------------------------------------
// 1. ★ 部署探针：新端点与新闸门都在跑着的进程里
// ---------------------------------------------------------------------------
title('1. ★ 部署探针：节点密钥泄漏分析端点已注册；/key-pool 与 /session-keys 不再匿名')
info('KMS-014 的三个可观察标记：① 新的 node-key-analysis 端点（404=没部署）；')
info('② /key-pool/* 匿名请求被拒（KMS-013 之前它匿名可达）；')
info('③ /session-keys/ 匿名请求被拒（KMS-014 从匿名名单移除）。')

const adminToken = await adminLogin()

const probeAnalysis = await api(UPDATEDEL_API, '/lifecycle/keymanage/node-key-analysis/probe-not-a-key', { token: adminToken })
check('★ ① 节点密钥泄漏分析端点已部署（不是 404）',
  probeAnalysis.status !== 404,
  `HTTP=${probeAnalysis.status} code=${probeAnalysis.body?.code} msg=${String(probeAnalysis.body?.msg || '').slice(0, 60)}`)
check('★ ① 未知 keyId → 空关联面（不是错误）：查询按标识逐字比对，查不到就是没有',
  isOk(probeAnalysis.body)
  && Array.isArray(probeAnalysis.body?.data?.distributeFootprints)
  && probeAnalysis.body?.data?.distributeFootprints.length === 0,
  `data=${JSON.stringify(probeAnalysis.body?.data).slice(0, 120)}`)

const probePool = await api(PQKDS, '/key-pool/?page=1&limit=1')
check('★ ② /key-pool/ 匿名被拒（KMS-013 起 consume 是真写端点，KMS-014 收口）',
  !isOk(probePool.body),
  `code=${probePool.body?.code} msg=${String(probePool.body?.msg || '').slice(0, 60)}`)

const probeSessions = await api(PQKDS, '/session-keys/?page=1&limit=1')
check('★ ③ /session-keys/ 匿名被拒（会话元数据不再对未登录可见）',
  !isOk(probeSessions.body),
  `code=${probeSessions.body?.code} msg=${String(probeSessions.body?.msg || '').slice(0, 60)}`)

const probeSessionsAuth = await api(PQKDS, '/session-keys/?page=1&limit=1', { token: adminToken })
check('★ ③ 正对照：管理员带令牌读同一接口是通的（闸门不是恒拒绝）',
  isOk(probeSessionsAuth.body),
  `code=${probeSessionsAuth.body?.code}`)

// ---------------------------------------------------------------------------
// 2. 夹具：A（发送）B（接收）C（无关节点）+ A 对 B 的授权
// ---------------------------------------------------------------------------
title('2. 夹具：A/B/C 三个节点（四套密钥），A 获得对 B 的分发授权')

const nodeA = await newNodeSession(adminToken, { prefix: 'K14A', name: 'KMS-014 发送方', domainId: DOMAIN })
const nodeB = await newNodeSession(adminToken, { prefix: 'K14B', name: 'KMS-014 接收方', domainId: DOMAIN })
const nodeC = await newNodeSession(adminToken, { prefix: 'K14C', name: 'KMS-014 无关节点', domainId: DOMAIN })
check('三个节点已建好并激活', Boolean(nodeA.token && nodeB.token && nodeC.token),
  `${nodeA.nodeId} / ${nodeB.nodeId} / ${nodeC.nodeId}`)

const userA = sqlScalar(`SELECT IFNULL(sys_user_id, '') FROM ${NODE_TABLE} WHERE node_id='${nodeA.nodeId}';`) || ''
const nodeBId = sqlScalar(`SELECT id FROM ${NODE_TABLE} WHERE node_id='${nodeB.nodeId}';`) || ''
check('A 映射到用户，B 在库里有主键', Boolean(userA && nodeBId), `A.user=${userA} B.pk=${nodeBId}`)

const grant = await api(PQKDS, '/admin/node-authorizations/', {
  method: 'POST',
  token: adminToken,
  body: { userId: Number(userA), nodeId: Number(nodeBId), remark: 'KMS-014 验收：A 需要能向 B 分发' }
})
check('节点鉴权已授予（A 的用户 → B 的节点）', isOk(grant.body),
  `code=${grant.body?.code} msg=${grant.body?.msg}`)

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
      keyVersion: material.version
    }
  })

info('生成密钥并登记（Falcon 本机生成要十几秒）…')
const keys = { A: {}, B: {}, C: {} }
for (const [label, session] of [['A', nodeA], ['B', nodeB], ['C', nodeC]]) {
  for (const [algorithm, options, extra] of [
    ['SM2', {}, {}],
    ['SSCL', {}, {}],
    [KYBER, { variant: VARIANT }, { securityLevel: String(VARIANT) }],
    ['FALCON', {}, {}]
  ]) {
    const material = await cryptoProvider.generate(algorithm, { nodeId: session.nodeId, ...options })
    const up = await register(session, algorithm, material, extra)
    if (!isOk(up.body)) {
      check(`${label} 的 ${algorithm} 登记成功`, false, `code=${up.body?.code} msg=${up.body?.msg}`)
    }
    keys[label][algorithm] = material
  }
}
for (const session of [nodeA, nodeB, nodeC]) {
  const init = await api(PQKDS, '/node-self/init/', { method: 'POST', token: session.token })
  if (!isOk(init.body)) {
    check(`${session.nodeId} 初始化收尾成功`, false, `msg=${init.body?.msg}`)
  }
}

/** 接收方那把 KYBER 在 NodeLongTermKey 里的**整数主键** —— 链上 keyId 的期望值。 */
const receiverKeyPk = sqlScalar(
  `SELECT id FROM falcon_kds.dvadmin_pqkds_node_long_term_keys `
  + `WHERE node_id=${nodeBId} AND algorithm='${KYBER}' AND key_id='${keys.B[KYBER].keyId}';`) || ''
check('接收方 KYBER 登记行的整数主键可查（链上事件按它锚定）',
  Boolean(receiverKeyPk), `pk=${receiverKeyPk}`)

// ---------------------------------------------------------------------------
// 3. 真实会话：分发 → 验签 → 解封 → 双方确认 → established（带 chainHash）
// ---------------------------------------------------------------------------
title('3. 真实会话（A→B）：三个会话类事件各自的落点都被走到')
info('分发（KEY_DISTRIBUTED 已在 KMS-008 接通）→ verify（ENVELOPE_VERIFIED）→')
info('recover（无链上事件，如实说明）→ 双方确认 → established（SESSION_ESTABLISHED）。')

const { buildNodeEnvelope, generatePayloadKey, newBatchId, signNodeEnvelope } =
  await import('../src/utils/crypto/envelope-signing.js')
const { unwrapNodeEnvelope, nodeProof } = await import('../src/utils/crypto/node-envelope.js')

const payloadKey = generatePayloadKey()
const batchId = newBatchId()
const expiresAt = new Date(Date.now() + 2 * 3600 * 1000).toISOString()
const built = await buildNodeEnvelope({
  provider: cryptoProvider,
  payloadKey,
  wrapping: KYBER,
  recipientPublicKeyHex: keys.B[KYBER].publicKey,
  batchId,
  senderNodeId: nodeA.nodeId,
  receiverNodeId: nodeB.nodeId,
  recipientKeyId: keys.B[KYBER].keyId,
  recipientKeyVersion: 1,
  expiresAt
})
const signature = await signNodeEnvelope(cryptoProvider, keys.A.FALCON.keyRef, built.envelope)
const dist = await api(PQKDS, '/node-self/distributions/', {
  method: 'POST',
  token: nodeA.token,
  body: {
    receiverNodeId: nodeB.nodeId,
    protectionAlgorithm: KYBER,
    recipientKeyId: keys.B[KYBER].keyId,
    recipientKeyVersion: 1,
    falconKeyId: keys.A.FALCON.keyId,
    falconKeyVersion: 1,
    batchId,
    expiresAt,
    envelope: built.envelope,
    signature,
    keyHash: built.keyHash
  }
})
check('分发成功（服务端已验签并登记）',
  isOk(dist.body) && dist.body?.data?.signatureVerified === true,
  `code=${dist.body?.code} verified=${dist.body?.data?.signatureVerified}`)

const sessionId = `${batchId}-n${nodeBId}`
check('会话行按批次 + 接收方主键建立', sessionStatus(sessionId) === 'initiated',
  `session_id=${sessionId} status=${sessionStatus(sessionId)}`)

const envelopesB = await api(PQKDS, '/node-self/envelopes/', { token: nodeB.token })
const envEntry = (envelopesB.body?.data?.items || []).find((item) => item.sessionId === sessionId)
const envelopeId = envEntry?.envelopeId
check('B 取到信封（带整数 ID 与会话定位）', Boolean(envelopeId), `envelopeId=${envelopeId}`)

const versionsB = await api(PQKDS, `/node-self/sessions/${sessionId}/versions/`, {
  method: 'POST', token: nodeB.token
})
const verifyB = await api(PQKDS, `/node-self/envelopes/${envelopeId}/verify/`, {
  method: 'POST', token: nodeB.token
})
check('★ verify 推进到 recipient_verified，且响应带 chainHash（ENVELOPE_VERIFIED 已上链）',
  isOk(verifyB.body) && verifyB.body?.data?.status === 'recipient_verified'
  && String(verifyB.body?.data?.chainHash || '').startsWith('0x'),
  `status=${verifyB.body?.data?.status} chainHash=${String(verifyB.body?.data?.chainHash || '').slice(0, 20)}…`)
const verifiedTx = String(verifyB.body?.data?.chainHash || '')

const recovered = await unwrapNodeEnvelope({
  provider: cryptoProvider,
  keyRef: keys.B[KYBER].keyRef,
  envelope: envEntry.envelope
})
check('B 本机解出 16 字节 SM4（解封这一步服务端无法复核，见 recover 的口径说明）',
  recovered instanceof Uint8Array && recovered.length === 16, `长度=${recovered?.length}`)

const recoverB = await api(PQKDS, `/node-self/envelopes/${envelopeId}/recover/`, {
  method: 'POST', token: nodeB.token
})
check('★ recover 推进到 key_recovered，响应如实带 note（这一步是节点声明）',
  isOk(recoverB.body) && recoverB.body?.data?.status === 'key_recovered'
  && String(recoverB.body?.data?.note || '').includes('节点回报'),
  `status=${recoverB.body?.data?.status}`)

const proofB = await nodeProof({ payloadKey: recovered, sessionId })
const proofA = await nodeProof({ payloadKey, sessionId })
const confirmA = await api(PQKDS, `/node-self/sessions/${sessionId}/confirm/`, {
  method: 'POST', token: nodeA.token, body: { proof: proofA }
})
check('★ 第一笔确认不建立（waiting）', isOk(confirmA.body) && confirmA.body?.data?.established === false,
  `established=${confirmA.body?.data?.established} msg=${String(confirmA.body?.msg || '').slice(0, 40)}`)

const confirmB2 = await api(PQKDS, `/node-self/sessions/${sessionId}/confirm/`, {
  method: 'POST', token: nodeB.token, body: { proof: proofB }
})
check('★★ 第二笔确认到达 → established，且响应带 chainHash（SESSION_ESTABLISHED 已上链）',
  isOk(confirmB2.body) && confirmB2.body?.data?.established === true
  && sessionStatus(sessionId) === 'established'
  && String(confirmB2.body?.data?.chainHash || '').startsWith('0x'),
  `established=${confirmB2.body?.data?.established} 库内=${sessionStatus(sessionId)} `
  + `chainHash=${String(confirmB2.body?.data?.chainHash || '').slice(0, 20)}…`)
const establishedTx = String(confirmB2.body?.data?.chainHash || '')

// ---------------------------------------------------------------------------
// 4. ★ 监管页五态：建立之后再关闭，轨迹**不因终态丢失**
// ---------------------------------------------------------------------------
title('4. ★ 五态（已登记/已验签/已解封/已建立/已上链）：先读一次，关闭后再读一次')
info('关闭后 status 只剩 closed —— 若五态是从 status 反推的，这一步之后')
info('"走到过哪一步"会静默丢失。判据是：关闭前后 evidence_state 都成立。')

// 取整页后在客户端挑出这一条：`?session_id=` 这类参数要依赖 DRF 的过滤后端
// 恰好接受它（`extra_filter_class` 为空、过滤后端来自全局配置），
// 参数被静默忽略时"找不到行"看起来像"没写进去"——按业务串自己挑最可靠。
const readEvidence = async () => {
  const res = await api(PQKDS, '/session-keys/?page=1&limit=500', { token: adminToken })
  const row = (res.body?.data || []).find((r) => r.session_id === sessionId)
  return row || {}
}

const rowBeforeClose = await readEvidence()
check('★ 建立后五态读数全为 true（registered/verified/recovered/established/onChain）',
  ['registered', 'verified', 'recovered', 'established', 'onChain']
    .every((k) => rowBeforeClose.evidence_state?.[k] === true),
  JSON.stringify(rowBeforeClose.evidence_state || '(读不到 evidence_state)'))
check('★ 轨迹里带各步时间与链上哈希（解封一步如实**没有** tx —— 它本就不上链）',
  (() => {
    let d = {}
    try { d = JSON.parse(rowBeforeClose.lifecycle_evidence || '{}') } catch { return false }
    return Boolean(d.verified?.at) && d.verified?.tx === verifiedTx
      && Boolean(d.recovered?.at) && !d.recovered?.tx
      && d.established?.tx === establishedTx
  })(),
  String(rowBeforeClose.lifecycle_evidence || '').slice(0, 220))

const closeA = await api(PQKDS, `/node-self/sessions/${sessionId}/close/`, {
  method: 'POST', token: nodeA.token
})
check('★ 关闭成功且响应带 chainHash（SESSION_CLOSED 已上链）',
  isOk(closeA.body) && closeA.body?.data?.advanced === true
  && String(closeA.body?.data?.chainHash || '').startsWith('0x'),
  `advanced=${closeA.body?.data?.advanced} chainHash=${String(closeA.body?.data?.chainHash || '').slice(0, 20)}…`)
const closedTx = String(closeA.body?.data?.chainHash || '')

const rowAfterClose = await readEvidence()
check('★★ 关闭后五态读数**仍然全为 true**（轨迹不因终态丢失 —— 这就是它落库而非反推的理由）',
  rowAfterClose.status === 'closed'
  && ['registered', 'verified', 'recovered', 'established', 'onChain']
    .every((k) => rowAfterClose.evidence_state?.[k] === true),
  `status=${rowAfterClose.status} evidence=${JSON.stringify(rowAfterClose.evidence_state)}`)
check('★ 关闭一步也进了轨迹（时间 + tx）',
  (() => {
    try { return JSON.parse(rowAfterClose.lifecycle_evidence || '{}').closed?.tx === closedTx } catch { return false }
  })(),
  String(rowAfterClose.lifecycle_evidence || '').slice(0, 260))

// ---------------------------------------------------------------------------
// 5. ★★ 链上回读：三个事件逐字段核对（直连 JSON-RPC）
// ---------------------------------------------------------------------------
title('5. ★★ 链上回读：ENVELOPE_VERIFIED / SESSION_ESTABLISHED / SESSION_CLOSED 逐字段核对')
info('⚠️ 回读的锚定口径必须与 KEY_DISTRIBUTED 一致：keyId = 接收方长期密钥行主键、')
info('nodeId = 接收节点。链上"谁的哪把钥匙"一旦分叉，回读就答不出谁受影响。')

const events = await scanLifecycleEvents()
info(`全链共 ${events.length} 条生命周期事件（本次现扫）`)
const mineFor = (t) => events.filter((e) =>
  e.eventType === t && e.keyId === BigInt(receiverKeyPk) && e.nodeId === nodeB.nodeId)

const evVerified = mineFor('ENVELOPE_VERIFIED')
const evEstablished = mineFor('SESSION_ESTABLISHED')
const evClosed = mineFor('SESSION_CLOSED')
check('★★ ENVELOPE_VERIFIED 在链上，且 tx 与响应里的 chainHash 一致',
  evVerified.length === 1 && evVerified[0].txHash === verifiedTx,
  `条数=${evVerified.length} tx=${evVerified[0]?.txHash?.slice(0, 22)}… 响应=${verifiedTx.slice(0, 22)}…`)
check('★★ SESSION_ESTABLISHED 在链上，且 tx 与响应里的 chainHash 一致',
  evEstablished.length === 1 && evEstablished[0].txHash === establishedTx,
  `条数=${evEstablished.length} tx=${evEstablished[0]?.txHash?.slice(0, 22)}…`)
check('★★ SESSION_CLOSED 在链上，且 tx 与响应里的 chainHash 一致',
  evClosed.length === 1 && evClosed[0].txHash === closedTx,
  `条数=${evClosed.length} tx=${evClosed[0]?.txHash?.slice(0, 22)}…`)
check('★ 三个事件与 KEY_DISTRIBUTED 同锚定：keyId=接收方密钥行、nodeId=接收节点（逐字）',
  [evVerified[0], evEstablished[0], evClosed[0]].every(
    (e) => e && e.keyId === BigInt(receiverKeyPk) && e.nodeId === nodeB.nodeId),
  `keyId 期望=${receiverKeyPk} nodeId 期望=${nodeB.nodeId}`)
check('★ 材料摘要 = 该登记行的 public_key_hash（链上核验"是不是同一份材料"）',
  [evVerified[0], evEstablished[0], evClosed[0]].every((e) => e && e.materialHash
    === (sqlScalar(`SELECT public_key_hash FROM falcon_kds.dvadmin_pqkds_node_long_term_keys `
      + `WHERE id=${receiverKeyPk};`) || '')),
  String(evVerified[0]?.materialHash || '').slice(0, 20) + '…')

// ---------------------------------------------------------------------------
// 6. 越权与篡改：每一条都断言**可编程错误码**，且带正对照
// ---------------------------------------------------------------------------
title('6. 越权与篡改：无关节点/篡改信封都被拒，错误码可编程区分')

const batchK = newBatchId()
const payloadKeyK = generatePayloadKey()
const builtK = await buildNodeEnvelope({
  provider: cryptoProvider,
  payloadKey: payloadKeyK,
  wrapping: KYBER,
  recipientPublicKeyHex: keys.B[KYBER].publicKey,
  batchId: batchK,
  senderNodeId: nodeA.nodeId,
  receiverNodeId: nodeB.nodeId,
  recipientKeyId: keys.B[KYBER].keyId,
  recipientKeyVersion: 1,
  expiresAt
})
const signatureK = await signNodeEnvelope(cryptoProvider, keys.A.FALCON.keyRef, builtK.envelope)
await api(PQKDS, '/node-self/distributions/', {
  method: 'POST',
  token: nodeA.token,
  body: {
    receiverNodeId: nodeB.nodeId,
    protectionAlgorithm: KYBER,
    recipientKeyId: keys.B[KYBER].keyId,
    recipientKeyVersion: 1,
    falconKeyId: keys.A.FALCON.keyId,
    falconKeyVersion: 1,
    batchId: batchK,
    expiresAt,
    envelope: builtK.envelope,
    signature: signatureK,
    keyHash: builtK.keyHash
  }
})
const sessionIdK = `${batchK}-n${nodeBId}`
const envK = await api(PQKDS, '/node-self/envelopes/', { token: nodeB.token })
const entryK = (envK.body?.data?.items || []).find((item) => item.sessionId === sessionIdK)
check('第二个夹具会话已建立（用于越权面）', sessionStatus(sessionIdK) === 'initiated',
  `session_id=${sessionIdK}`)

// 越权 1：无关节点 C 验别人的信封
const cVerify = await api(PQKDS, `/node-self/envelopes/${entryK.envelopeId}/verify/`, {
  method: 'POST', token: nodeC.token
})
check('★ 无关节点验他人信封 → 403 + NOT_ENVELOPE_RECIPIENT（码可编程区分）',
  cVerify.body?.code === 403
  && cVerify.body?.data?.error_code === 'NOT_ENVELOPE_RECIPIENT',
  `code=${cVerify.body?.code} error_code=${cVerify.body?.data?.error_code}`)
check('★ 被拒后会话状态**没动**（越权尝试不产生任何副作用）',
  sessionStatus(sessionIdK) === 'initiated', `status=${sessionStatus(sessionIdK)}`)

// 越权 2：无关节点 C 替别人确认
const cConfirm = await api(PQKDS, `/node-self/sessions/${sessionIdK}/confirm/`, {
  method: 'POST', token: nodeC.token, body: { proof: 'a'.repeat(64) }
})
check('★ 无关节点提交他人会话确认 → 403 + NOT_SESSION_PARTY',
  cConfirm.body?.code === 403
  && cConfirm.body?.data?.error_code === 'NOT_SESSION_PARTY',
  `code=${cConfirm.body?.code} error_code=${cConfirm.body?.data?.error_code}`)

// 篡改：ORM 改库内信封密文一个字符（⚠️ 不用 js 拼 SQL —— JSON 引号多，
// 转义错一次就测到"没改动的请求"；沿用 KMS-011 建立的 ORM 两段式夹具）
//
// ⚠️ 翻转是**不可逆**的（不知道原字符是什么）。所以恢复不靠"再翻一下"，
//    而是把**原值**记下来、写回去 —— 原值就在 `builtK.envelope` 里
//    （这封信是脚本自己造的，逐字段都还在手上）。
const cipherField = builtK.envelope.kem_ciphertext
  ? 'kem_ciphertext'
  : (builtK.envelope.ciphertext ? 'ciphertext' : 'encrypted_key')
const originalCipherField = builtK.envelope[cipherField]

const tamperOut = orm(ormHeader + `
from pqkds.models import PreDistributedKey
import json
row = PreDistributedKey.objects.get(pk=${entryK.envelopeId})
data = json.loads(row.encrypted_key_data)
key = '${cipherField}'
original = data[key]
flipped = ('B' if original[0] != 'B' else 'C') + original[1:]
data[key] = flipped
row.encrypted_key_data = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
row.save(update_fields=['encrypted_key_data'])
print('TAMPERED_FIELD=%s %s…→%s…' % (key, original[:8], flipped[:8]))
`)
check('夹具：库内信封的密文被改了一个字符（ORM 改，不用手拼 SQL）',
  tamperOut.includes('TAMPERED_FIELD='),
  tamperOut.trim().split('\n')[-1])

const tamperedVerify = await api(PQKDS, `/node-self/envelopes/${entryK.envelopeId}/verify/`, {
  method: 'POST', token: nodeB.token
})
check('★ 篡改信封 → 拒绝且码是 ENVELOPE_TAMPERED（先于验签：序列化漂移不伪装成伪造）',
  !isOk(tamperedVerify.body)
  && tamperedVerify.body?.data?.error_code === 'ENVELOPE_TAMPERED',
  `code=${tamperedVerify.body?.code} error_code=${tamperedVerify.body?.data?.error_code}`)
check('★ 篡改被拒后会话状态没动', sessionStatus(sessionIdK) === 'initiated',
  `status=${sessionStatus(sessionIdK)}`)

// 恢复：把**原值**写回（原值在手上，不从库内反推）
const restoreOut = orm(ormHeader + `
from pqkds.models import PreDistributedKey
import json
row = PreDistributedKey.objects.get(pk=${entryK.envelopeId})
data = json.loads(row.encrypted_key_data)
data['${cipherField}'] = ${JSON.stringify(originalCipherField)}
row.encrypted_key_data = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
row.save(update_fields=['encrypted_key_data'])
print('RESTORED=%s' % '${cipherField}')
`)
check('信封已恢复原文（恢复后照常走验签路径 —— 下方撤销用例依赖它）',
  restoreOut.includes('RESTORED='), restoreOut.trim().split('\n')[-1])
const verifyAfterRestore = await api(PQKDS, `/node-self/envelopes/${entryK.envelopeId}/verify/`, {
  method: 'POST', token: nodeB.token
})
check('正对照：恢复后的信封验签通过（前面的拒绝不是"恒拒绝"）',
  isOk(verifyAfterRestore.body) && verifyAfterRestore.body?.data?.status === 'recipient_verified',
  `status=${verifyAfterRestore.body?.data?.status}`)

// 越权 3：/key-pool 的"节点对一方"检查（KMS-014 新收口）
const poolGenByC = await api(PQKDS, '/key-pool/generate/', {
  method: 'POST',
  token: nodeC.token,
  body: { node1_id: nodeA.nodeId, node2_id: nodeB.nodeId, algorithm: 'kyber_kem', count: 1 }
})
check('★ 节点用户 C 替 A↔B 预分配 → 被拒（不是该节点对的一方）',
  !isOk(poolGenByC.body)
  && String(poolGenByC.body?.msg || '').includes('不是该节点对'),
  `code=${poolGenByC.body?.code} msg=${String(poolGenByC.body?.msg || '').slice(0, 80)}`)
const poolGenByA = await api(PQKDS, '/key-pool/generate/', {
  method: 'POST',
  token: nodeA.token,
  body: { node1_id: nodeA.nodeId, node2_id: nodeB.nodeId, algorithm: 'kyber_kem', count: 1 }
})
check('★ 正对照：A 自己（该节点对的一方，L2 有 CAP_DISTRIBUTE）预分配是通的',
  isOk(poolGenByA.body), `code=${poolGenByA.body?.code} msg=${String(poolGenByA.body?.msg || '').slice(0, 60)}`)

// ---------------------------------------------------------------------------
// 7. 审计记录：拒绝必须留痕（ApiLoggingMiddleware → operation_log）
// ---------------------------------------------------------------------------
title('7. 审计：上面的越权/篡改请求在 operation_log 里留了记录')
info('链上事件回答"发生过什么"，HTTP 审计回答"谁在什么时候试了什么"——')
info('两者不是一回事：越权尝试不会产生链上事件，但必须在审计里可见。')
info('⚠️ 审计行里 `json_result` 存的是 **code + msg 文案**（不是 data.error_code）——')
info('按错误码 LIKE 会恒 0 行，看起来像"没留痕"。这里按文案里那句可辨识的话匹配。')
info('⚠️ KMS-014 施工时实测到一处真缺陷：中间件把行 id 存在**中间件实例**上，')
info('函数视图的响应会 update_or_create 到**上一个请求留下的行**上 —— 越权/篡改')
info('的审计被后续请求覆盖。已修（id 挂到 request），这里的断言就是它的回归判据。')

const auditTamper = sqlScalar(
  `SELECT COUNT(*) FROM ${OP_LOG_TABLE} `
  + `WHERE request_path LIKE '%/envelopes/${entryK.envelopeId}/verify/%' `
  + `AND json_result LIKE '%摘要与服务端重算的不一致%';`) || '0'
check('★ 篡改判定的那次请求在 operation_log 里有记录（判据④"有拒绝和审计记录"的审计半边）',
  Number(auditTamper) >= 1, `命中 ${auditTamper} 条`)

const auditOverreach = sqlScalar(
  `SELECT COUNT(*) FROM ${OP_LOG_TABLE} `
  + `WHERE request_path LIKE '%/sessions/${sessionIdK}/confirm/%' `
  + `AND json_result LIKE '%你不是这条会话的一方%';`) || '0'
check('★ 越权确认的拒绝也在审计里（不是只在链上或只在日志文件里）',
  Number(auditOverreach) >= 1, `命中 ${auditOverreach} 条`)

// ---------------------------------------------------------------------------
// 8. 过期与撤销：终态拒绝继续推进
// ---------------------------------------------------------------------------
title('8. 过期与撤销：会话进终态后不再接受确认（SESSION_TERMINAL）')

orm(ormHeader + `
from pqkds.models import SessionKey
s = SessionKey.objects.get(session_id='${sessionIdK}')
s.status = 'expired'
s.save(update_fields=['status'])
print('FORCED_EXPIRED')
`)
const confirmExpired = await api(PQKDS, `/node-self/sessions/${sessionIdK}/confirm/`, {
  method: 'POST', token: nodeA.token, body: { proof: 'b'.repeat(64) }
})
check('★ 过期会话收到的确认被拒：SESSION_TERMINAL（终态不接受任何确认）',
  !isOk(confirmExpired.body)
  && confirmExpired.body?.data?.error_code === 'SESSION_TERMINAL',
  `code=${confirmExpired.body?.code} error_code=${confirmExpired.body?.data?.error_code}`)

orm(ormHeader + `
from pqkds.models import SessionKey
s = SessionKey.objects.get(session_id='${sessionIdK}')
s.status = 'revoked'
s.save(update_fields=['status'])
print('FORCED_REVOKED')
`)
const verifyRevoked = await api(PQKDS, `/node-self/envelopes/${entryK.envelopeId}/verify/`, {
  method: 'POST', token: nodeB.token
})
check('★ 已撤销会话上的验签回报被拒（不能把终止的会话往回推）',
  !isOk(verifyRevoked.body) && Boolean(verifyRevoked.body?.data?.error_code),
  `code=${verifyRevoked.body?.code} error_code=${verifyRevoked.body?.data?.error_code} `
  + `msg=${String(verifyRevoked.body?.msg || '').slice(0, 60)}`)

// ---------------------------------------------------------------------------
// 9. 节点密钥泄漏分析：按版本追踪受影响信封/池项/会话（KMS-008 的过渡缺口）
// ---------------------------------------------------------------------------
title('9. ★ 节点密钥泄漏分析：按长期密钥版本追踪信封/池项/会话/节点')
info('KMS-008 如实记录"新批次不进泄漏分析（source_key_id 为 NULL）" ——')
info('新链路的关联键是**接收方那一版长期密钥**。这条入口回答的就是它。')

// 该接收方密钥此刻已引用过：会话 1（已关闭）与夹具会话 K（expired/revoked）。
const leak = await api(
  UPDATEDEL_API,
  `/lifecycle/keymanage/node-key-analysis/${encodeURIComponent(keys.B[KYBER].keyId)}?version=1`,
  { token: adminToken }
)
check('★ 分析可查（管理员）', isOk(leak.body), `code=${leak.body?.code} msg=${String(leak.body?.msg || '').slice(0, 60)}`)
const leakSessions = leak.body?.data?.operationTrails || []
const leakEnvelopes = leak.body?.data?.distributeFootprints || []
const leakNodes = leak.body?.data?.affectedNodes || []
check('★ 会话被追踪到（recipient_key_id/version 命中，两条：已关闭的那条与夹具）',
  leakSessions.some((s2) => s2.session_id === sessionId)
  && leakSessions.some((s2) => s2.session_id === sessionIdK),
  `命中会话=${leakSessions.map((s2) => s2.session_id).join(', ').slice(0, 90)}`)
check('★ 信封/池行被追踪到（long_term_key_id/version 命中）',
  leakEnvelopes.some((e) => e.pool_id === batchId)
  && leakEnvelopes.some((e) => e.pool_id === batchK),
  `命中批次=${leakEnvelopes.map((e) => e.pool_id).join(', ').slice(0, 90)}`)
check('★ 受影响节点含接收方 B（回读给的 node_id 是业务编号）',
  leakNodes.some((n) => n.node_id === nodeB.nodeId),
  `节点=${leakNodes.map((n) => n.node_id).join(', ').slice(0, 60)}`)

// 正对照：不存在的 keyId → 空关联面（查询按标识逐字比对，不是"什么都命中"）
const leakEmpty = await api(
  UPDATEDEL_API,
  '/lifecycle/keymanage/node-key-analysis/KMS014-NO-SUCH-KEY?version=1',
  { token: adminToken }
)
check('★ 正对照：不存在的 keyId → 关联面为空（查询不是"什么都命中"）',
  isOk(leakEmpty.body)
  && (leakEmpty.body?.data?.operationTrails || []).length === 0
  && (leakEmpty.body?.data?.distributeFootprints || []).length === 0,
  JSON.stringify(leakEmpty.body?.data).slice(0, 100))

// 非管理员访问 → 拒绝（跨用户的全量关联面仅平台管理员）
const leakAsNode = await api(
  UPDATEDEL_API,
  `/lifecycle/keymanage/node-key-analysis/${encodeURIComponent(keys.B[KYBER].keyId)}?version=1`,
  { token: nodeB.token }
)
check('★ 节点令牌访问节点密钥分析 → 被拒（仅平台管理员：它跨用户给全量关联面）',
  !isOk(leakAsNode.body) && String(leakAsNode.body?.msg || '').includes('管理员'),
  `code=${leakAsNode.body?.code} msg=${String(leakAsNode.body?.msg || '').slice(0, 60)}`)

// ---------------------------------------------------------------------------
// 10. 清理：自建自清
// ---------------------------------------------------------------------------
title('10. 清理：删掉本脚本建的三个节点及其一切关联行')
const cleanupProgram = ormHeader + `
from pqkds.models import Node, UserKeyEnvelope, DistributionBatch
nodes = list(Node.objects.filter(domain_id='${DOMAIN}'))
ids = [n.pk for n in nodes]
user_ids = [n.sys_user_id for n in nodes if n.sys_user_id]
envelopes, _ = UserKeyEnvelope.objects.filter(user_id__in=user_ids).delete()
batches, _ = DistributionBatch.objects.filter(user_id__in=user_ids).delete()
deleted, _ = Node.objects.filter(pk__in=ids).delete()
left = Node.objects.filter(domain_id='${DOMAIN}').count()
print('nodes=%d envelopes=%d batches=%d cascaded=%d left=%d'
      % (len(ids), envelopes, batches, deleted, left))
`
let cleanupOut = ''
let cleanupErr = ''
try {
  cleanupOut = orm(cleanupProgram).trim()
} catch (error) {
  cleanupErr = String(error?.stderr || error?.message || error)
}
info(cleanupOut || cleanupErr)
check('清理完成：域内不再有本脚本建的节点',
  Boolean(cleanupOut) && cleanupOut.endsWith('left=0'), cleanupOut || cleanupErr)

info(`本次真建的节点：${nodeA.nodeId} / ${nodeB.nodeId} / ${nodeC.nodeId}（已在上面删掉）`)
info('证据都在上面：部署探针（新端点 + 两处收口）、三个会话事件**链上逐字段回读**、')
info('五态在关闭后仍完整、越权（NOT_ENVELOPE_RECIPIENT / NOT_SESSION_PARTY / 节点对一方）')
info('与篡改（ENVELOPE_TAMPERED）各有可编程错误码与正对照、拒绝在 operation_log 留痕、')
info('终态拒绝推进（SESSION_TERMINAL）、节点密钥泄漏分析按版本命中四类关联面。')
finish()
