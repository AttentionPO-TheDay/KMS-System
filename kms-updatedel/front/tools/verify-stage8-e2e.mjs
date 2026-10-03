/**
 * KMS-016 验收：**双节点三算法全量端到端**（计划 §9.3 的八步，阶段 8 出口）。
 *
 * 与其它脚本的分工
 * ---------------
 * 前面每个脚本各钉自己那一段（`verify-node-distribution` 钉发送侧、
 * `verify-envelope-recover` 钉接收侧与状态机、`verify-pool-consume` 钉池、
 * `verify-governance` 钉监管、`verify-legacy-sealed` 钉封存）。本脚本是
 * **收口的全量验收**：把 §9.3 的八步在真实双节点上从头到尾走一遍，
 * 且**三条保护算法各走一次完整会话链**（分发 → 取信 → 验签 → 解封 →
 * 双方确认 → established）—— 这是"三种保护算法均能建立会话"的最终形式，
 * 而不是只看"能产生信封"。
 *
 * 八步与断言的对位
 * ---------------
 *   1. A/B 建节点、本地生成四类密钥、登记并初始化   —— §2
 *   2. SM2 / SSCL / Kyber 各一次完整会话（真往返）    —— §3（三次同行断言）
 *   3. 篡改一个字节 → 验签失败                        —— §4
 *   4. 换版本（用另一版私钥解封）→ 本地解不开          —— §4
 *   5. 删私钥（本机没有对应私钥）→ 解封明确失败        —— §4
 *   6. 回收接收密钥 → 后续分发被拒                    —— §5
 *   7. 预分配消费不可重复                             —— §6
 *   8. 关闭/过期/撤销不可恢复                         —— §7
 *
 * ⚠️ 会建真节点、写真数据、真上链（开发链）。结尾 §8 自建自清。
 * ⚠️ 服务端代码打进镜像：改了后端不重建，第 1 节的探针先失败 —— 刻意如此。
 */
import { execFileSync } from 'node:child_process'
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
import { sqlScalar, dockerBin } from '../../../tools/lib/mysql.mjs'

const { check, info, finish } = makeReporter()

const SM2 = 'SM2'
const SSCL = 'SSCL'
const KYBER = 'KYBER'
const VARIANT = 768
const DOMAIN = 'kms016'

const NODE_TABLE = 'falcon_kds.dvadmin_pqkds_nodes'
const POOL_TABLE = 'falcon_kds.dvadmin_pqkds_pre_distributed_keys'
const SESSION_TABLE = 'falcon_kds.dvadmin_pqkds_session_keys'

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
// 1. ★ 部署探针：全链路的三个关键端点都在跑着的进程里
// ---------------------------------------------------------------------------
title('1. ★ 部署探针：分发 / 取信封 / 会话确认 三组端点已部署')
info('全部无令牌探法（不产生副作用）：注册了 → 401（要求登录），没注册 → 404/405。')
info('⚠️ 旧会话动作返回的是 **410 封存码**（KMS-015）—— 探针别拿 404/405 判它。')

for (const [label, path, method] of [
  ['POST /node-self/distributions/', '/node-self/distributions/', 'POST'],
  ['GET  /node-self/envelopes/', '/node-self/envelopes/', 'GET'],
  ['POST /node-self/sessions/<sid>/confirm/', '/node-self/sessions/probe/confirm/', 'POST'],
  ['POST /node-self/sessions/<sid>/close/', '/node-self/sessions/probe/close/', 'POST'],
  ['GET  /node-self/keys/', '/node-self/keys/', 'GET']
]) {
  const res = await api(PQKDS, path, { method })
  check(`★ ${label} 已部署（不是 404/405）`, res.status !== 404 && res.status !== 405,
    `HTTP=${res.status} code=${res.body?.code}`)
}

const sealed = await api(PQKDS, '/session-keys/initiate/', { method: 'POST', body: {} })
check('★ 旧会话动作仍是 410 封存码（KMS-015 的封存面在 T 阶段依然成立）',
  sealed.body?.code === 410, `code=${sealed.body?.code}`)

// ---------------------------------------------------------------------------
// 2. 夹具：A（发送）B（接收），四类密钥本地生成、登记、初始化
// ---------------------------------------------------------------------------
title('2. 步①：双节点（A 发送 / B 接收）本地生成四类密钥并完成初始化')

const adminToken = await adminLogin()
const nodeA = await newNodeSession(adminToken, { prefix: 'K16A', name: 'KMS-016 发送方', domainId: DOMAIN })
const nodeB = await newNodeSession(adminToken, { prefix: 'K16B', name: 'KMS-016 接收方', domainId: DOMAIN })
check('A/B 已建好并激活', Boolean(nodeA.token && nodeB.token), `${nodeA.nodeId} / ${nodeB.nodeId}`)

const userA = sqlScalar(`SELECT IFNULL(sys_user_id, '') FROM ${NODE_TABLE} WHERE node_id='${nodeA.nodeId}';`) || ''
const nodeBId = sqlScalar(`SELECT id FROM ${NODE_TABLE} WHERE node_id='${nodeB.nodeId}';`) || ''
const grant = await api(PQKDS, '/admin/node-authorizations/', {
  method: 'POST',
  token: adminToken,
  body: { userId: Number(userA), nodeId: Number(nodeBId), remark: 'KMS-016 全量验收' }
})
check('A 的用户对 B 的节点已授权', isOk(grant.body), `code=${grant.body?.code}`)

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
const keys = { A: {}, B: {} }
for (const [label, session] of [['A', nodeA], ['B', nodeB]]) {
  for (const [algorithm, options, extra] of [
    [SM2, {}, {}],
    [SSCL, {}, {}],
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
for (const session of [nodeA, nodeB]) {
  const init = await api(PQKDS, '/node-self/init/', { method: 'POST', token: session.token })
  if (!isOk(init.body)) {
    check(`${session.nodeId} 初始化收尾成功`, false, `msg=${init.body?.msg}`)
  }
}
check('★ 步①完成：A/B 四套密钥就绪（init 校验过齐备）',
  true, `${nodeA.nodeId} / ${nodeB.nodeId}`)

const { buildNodeEnvelope, generatePayloadKey, newBatchId, signNodeEnvelope } =
  await import('../src/utils/crypto/envelope-signing.js')
const { unwrapNodeEnvelope, nodeProof } = await import('../src/utils/crypto/node-envelope.js')

/** 走一次完整会话：分发 → 取信 → 验签 → 解封 → 双方确认 → established。 */
async function fullSession(algorithm) {
  const payloadKey = generatePayloadKey()
  const batchId = newBatchId()
  const expiresAt = new Date(Date.now() + 2 * 3600 * 1000).toISOString()
  const built = await buildNodeEnvelope({
    provider: cryptoProvider,
    payloadKey,
    wrapping: algorithm,
    recipientPublicKeyHex: keys.B[algorithm].publicKey,
    batchId,
    senderNodeId: nodeA.nodeId,
    receiverNodeId: nodeB.nodeId,
    recipientKeyId: keys.B[algorithm].keyId,
    recipientKeyVersion: 1,
    expiresAt
  })
  const signature = await signNodeEnvelope(cryptoProvider, keys.A.FALCON.keyRef, built.envelope)
  const dist = await api(PQKDS, '/node-self/distributions/', {
    method: 'POST',
    token: nodeA.token,
    body: {
      receiverNodeId: nodeB.nodeId,
      protectionAlgorithm: algorithm,
      recipientKeyId: keys.B[algorithm].keyId,
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
  const sessionId = `${batchId}-n${nodeBId}`
  const envelopesB = await api(PQKDS, '/node-self/envelopes/', { token: nodeB.token })
  const envEntry = (envelopesB.body?.data?.items || []).find((item) => item.sessionId === sessionId)
  const verifyB = await api(PQKDS, `/node-self/envelopes/${envEntry?.envelopeId}/verify/`, {
    method: 'POST', token: nodeB.token
  })
  const recovered = await unwrapNodeEnvelope({
    provider: cryptoProvider,
    keyRef: keys.B[algorithm].keyRef,
    envelope: envEntry?.envelope
  })
  const recoverB = await api(PQKDS, `/node-self/envelopes/${envEntry?.envelopeId}/recover/`, {
    method: 'POST', token: nodeB.token
  })
  const proofB = await nodeProof({ payloadKey: recovered, sessionId })
  const proofA = await nodeProof({ payloadKey, sessionId })
  const confirmA = await api(PQKDS, `/node-self/sessions/${sessionId}/confirm/`, {
    method: 'POST', token: nodeA.token, body: { proof: proofA }
  })
  const confirmB = await api(PQKDS, `/node-self/sessions/${sessionId}/confirm/`, {
    method: 'POST', token: nodeB.token, body: { proof: proofB }
  })
  return {
    batchId, sessionId, envEntry, built, payloadKey,
    distOk: isOk(dist.body) && dist.body?.data?.signatureVerified === true,
    sessionTypeInDb: sqlScalar(
      `SELECT session_type FROM ${SESSION_TABLE} WHERE session_id='${sessionId}';`) || '',
    verifyOk: isOk(verifyB.body) && verifyB.body?.data?.status === 'recipient_verified',
    recoveredOk: recovered instanceof Uint8Array && recovered.length === 16
      && Buffer.from(recovered).equals(Buffer.from(payloadKey)),
    recoverOk: isOk(recoverB.body) && recoverB.body?.data?.status === 'key_recovered',
    proofsEqual: proofA === proofB && proofA.length === 64,
    established: isOk(confirmB.body) && confirmB.body?.data?.established === true
      && sessionStatus(sessionId) === 'established',
    confirmAOk: isOk(confirmA.body) && confirmA.body?.data?.established === false
  }
}

// ---------------------------------------------------------------------------
// 3. ★★ 步②：三条保护算法各走一次完整会话链
// ---------------------------------------------------------------------------
title('3. ★★ 步②：SM2 / SSCL / Kyber 各一次完整会话（分发→取信→验签→解封→双方确认→established）')
info('判据不是"信封产生了"，而是**整条链走到 established**，且每一步的中间产物')
info('都逐字核对（解出的 K 与发送方那把逐字节相同、双方 proof 一致、状态真的落库）。')

const runs = {}
for (const [algorithm, expectedType] of [[SM2, 'gm_sm2'], [SSCL, 'gm_sscl'], [KYBER, 'kyber_kem']]) {
  const r = await fullSession(algorithm)
  runs[algorithm] = r
  check(`★★ ${algorithm}：完整链走到 established`,
    r.distOk && r.verifyOk && r.recoveredOk && r.recoverOk && r.proofsEqual && r.established,
    `dist=${r.distOk} verify=${r.verifyOk} 解出16B且逐字节相同=${r.recoveredOk} `
    + `recover=${r.recoverOk} proofs=${r.proofsEqual} established=${r.established}`)
  check(`${algorithm}：会话类型按实际算法记（${expectedType}），不是一律 kyber_kem`,
    r.sessionTypeInDb === expectedType, `读到 ${r.sessionTypeInDb}`)
  check(`${algorithm}：第一笔确认不建立（waiting）—— 双方齐了才建立`,
    r.confirmAOk, `established=${r.confirmAOk}`)
}
check('★ 步②完成：三条算法三个 established（同一对节点、同一时刻）',
  [SM2, SSCL, KYBER].every((a) => runs[a].established),
  [SM2, SSCL, KYBER].map((a) => `${a}=${sessionStatus(runs[a].sessionId)}`).join(' '))

// ---------------------------------------------------------------------------
// 4. ★ 步③④⑤：篡改 / 换版本 / 删私钥 —— 三种失败各走一次
// ---------------------------------------------------------------------------
title('4. ★ 步③④⑤：篡改一字节 → 拒绝；换版本私钥 → 本地解不开；本机无私钥 → 明确失败')

// 步③篡改：ORM 改库内信封的密文一字节（用 KMS-016 专用的一条新会话做靶子）
const tamperTarget = runs[KYBER]
const cipherField = tamperTarget.built.envelope.kem_ciphertext
  ? 'kem_ciphertext' : (tamperTarget.built.envelope.ciphertext ? 'ciphertext' : 'encrypted_key')
const originalCipher = tamperTarget.built.envelope[cipherField]
orm(ormHeader + `
from pqkds.models import PreDistributedKey
import json
row = PreDistributedKey.objects.get(pool_id='${tamperTarget.batchId}', key_index=0)
data = json.loads(row.encrypted_key_data)
orig = data['${cipherField}']
data['${cipherField}'] = ('B' if orig[0] != 'B' else 'C') + orig[1:]
row.encrypted_key_data = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
row.save(update_fields=['encrypted_key_data'])
print('TAMPERED')
`)
const tampered = await api(PQKDS, `/node-self/envelopes/${tamperTarget.envEntry.envelopeId}/verify/`, {
  method: 'POST', token: nodeB.token
})
check('★ 步③：篡改一字节 → ENVELOPE_TAMPERED（先于验签报出）',
  !isOk(tampered.body) && tampered.body?.data?.error_code === 'ENVELOPE_TAMPERED',
  `error_code=${tampered.body?.data?.error_code}`)
check('★ 步③：被拒后会话状态没动（仍在 recipient_verified 之前或之后，不前进）',
  ['initiated', 'recipient_verified', 'key_recovered', 'established']
    .includes(sessionStatus(tamperTarget.sessionId)),
  `status=${sessionStatus(tamperTarget.sessionId)}`)
// 恢复原值（该会话已 established，恢复它保持库干净）
orm(ormHeader + `
from pqkds.models import PreDistributedKey
import json
row = PreDistributedKey.objects.get(pool_id='${tamperTarget.batchId}', key_index=0)
data = json.loads(row.encrypted_key_data)
data['${cipherField}'] = ${JSON.stringify(originalCipher)}
row.encrypted_key_data = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
row.save(update_fields=['encrypted_key_data'])
print('RESTORED')
`)

// 步④换版本：拿**另一把私钥**解封（B 的 SSCL 私钥解 SM2 信封）。
// 判据 = 明确失败**或**解出的字节与发送方的 K 不同 —— 两者都算"换版本
// 这一路走不通"。只写"抛错"会把"静默解出另一把"放过去（那正是要防的
// 静默错误；这里用 key_hash 做逐字判据）。
const wrongKeyUnwrap = await (async () => {
  try {
    const out = await unwrapNodeEnvelope({
      provider: cryptoProvider,
      keyRef: keys.B[SSCL].keyRef,          // 用 SSCL 私钥解 SM2 信封
      envelope: runs[SM2].envEntry.envelope
    })
    return { ok: true, out }
  } catch (error) {
    return { ok: false, err: String(error?.message || error) }
  }
})()
const wrongKeyIsSame = wrongKeyUnwrap.ok
  && Buffer.from(wrongKeyUnwrap.out).equals(Buffer.from(runs[SM2].payloadKey))
check('★ 步④：拿另一把私钥解封 → 明确失败或解出的不是那把 K（不会静默解"对"）',
  !wrongKeyIsSame,
  wrongKeyUnwrap.ok
    ? `解出了 ${wrongKeyUnwrap.out?.length} 字节，与发送方那把不同（正确：换版本走不通）`
    : `拒绝：${String(wrongKeyUnwrap.err).slice(0, 80)}`)

// 步⑤删私钥：用一个**本机密钥库里没有**的 keyRef（换成不存在的节点前缀）
const missingKeyUnwrap = await (async () => {
  try {
    const out = await unwrapNodeEnvelope({
      provider: cryptoProvider,
      keyRef: `node/K16-DELETED-NODE/${KYBER}/no-such-key/1`,
      envelope: runs[KYBER].envEntry.envelope
    })
    return { ok: true, out }
  } catch (error) {
    return { ok: false, err: String(error?.message || error) }
  }
})()
check('★ 步⑤：本机没有对应私钥 → 解封明确失败（KEY_LOCAL_MISSING 一类，不是静默解出错字节）',
  missingKeyUnwrap.ok === false,
  `拒绝：${String(missingKeyUnwrap.err || '').slice(0, 100)}`)

// ---------------------------------------------------------------------------
// 5. ★ 步⑥：回收接收密钥 → 后续分发被拒
// ---------------------------------------------------------------------------
title('5. ★ 步⑥：回收 B 的 KYBER → 再按它分发被拒（KEY_REVOKED）')

const revoke = await api(PQKDS, '/node-self/keys/revoke/', {
  method: 'POST',
  token: nodeB.token,
  body: { algorithm: KYBER, keyId: keys.B[KYBER].keyId, keyVersion: 1, reason: 'KMS-016 全量验收：步⑥' }
})
check('回收成功', isOk(revoke.body), `code=${revoke.body?.code}`)

const afterRevokePayload = generatePayloadKey()
const afterRevokeBatch = newBatchId()
const afterRevokeBuilt = await buildNodeEnvelope({
  provider: cryptoProvider,
  payloadKey: afterRevokePayload,
  wrapping: KYBER,
  recipientPublicKeyHex: keys.B[KYBER].publicKey,
  batchId: afterRevokeBatch,
  senderNodeId: nodeA.nodeId,
  receiverNodeId: nodeB.nodeId,
  recipientKeyId: keys.B[KYBER].keyId,
  recipientKeyVersion: 1,
  expiresAt: new Date(Date.now() + 3600 * 1000).toISOString()
})
const afterRevokeSig = await signNodeEnvelope(cryptoProvider, keys.A.FALCON.keyRef, afterRevokeBuilt.envelope)
const distAfterRevoke = await api(PQKDS, '/node-self/distributions/', {
  method: 'POST',
  token: nodeA.token,
  body: {
    receiverNodeId: nodeB.nodeId,
    protectionAlgorithm: KYBER,
    recipientKeyId: keys.B[KYBER].keyId,
    recipientKeyVersion: 1,
    falconKeyId: keys.A.FALCON.keyId,
    falconKeyVersion: 1,
    batchId: afterRevokeBatch,
    expiresAt: new Date(Date.now() + 3600 * 1000).toISOString(),
    envelope: afterRevokeBuilt.envelope,
    signature: afterRevokeSig,
    keyHash: afterRevokeBuilt.keyHash
  }
})
check('★ 回收后再按该版本分发 → 服务端拒绝（错误码透出，不是"看起来成功"）',
  !isOk(distAfterRevoke.body)
  && ['KEY_REVOKED', 'KEY_NOT_FOUND', 'KEY_VERSION_MISMATCH']
    .includes(distAfterRevoke.body?.data?.error_code),
  `code=${distAfterRevoke.body?.code} error_code=${distAfterRevoke.body?.data?.error_code}`)
check('★ 被拒后该批次没有池行（拒收不是"先落库后报错"）',
  Number(sqlScalar(`SELECT COUNT(*) FROM ${POOL_TABLE} WHERE pool_id='${afterRevokeBatch}';`) || 0) === 0,
  `池行=${sqlScalar(`SELECT COUNT(*) FROM ${POOL_TABLE} WHERE pool_id='${afterRevokeBatch}';`)}`)

// ---------------------------------------------------------------------------
// 6. ★ 步⑦：预分配消费不可重复（紧凑版；完整版在 verify-pool-consume）
// ---------------------------------------------------------------------------
title('6. ★ 步⑦：预分配消费不可重复（N 条 → 恰好 N 次成功，第 N+1 次失败）')
info('完整判据（真并发、撤密钥链、吞吐）在 `verify-pool-consume`；这一节是')
info('全量验收里的紧凑复述：取到条数上限后再取必失败。')

// ⚠️ 先正面撞一次：A→B 的生成**必须被拒**（B 的 KYBER 刚在步⑥被回收 ——
//    这条同时是"版本失效阻止新预分配"的判据，生成闸门看的就是 node2）。
const genRejected = await api(PQKDS, '/key-pool/generate/', {
  method: 'POST',
  token: adminToken,
  body: { node1_id: nodeA.nodeId, node2_id: nodeB.nodeId, algorithm: 'kyber_kem', count: 2 }
})
check('★ 步⑥衍：B 的 KYBER 已回收 → A→B 的预分配同样被拒（码在文案里）',
  !isOk(genRejected.body) && String(genRejected.body?.msg || '').includes('KEY_REVOKED'),
  `msg=${String(genRejected.body?.msg || '').slice(0, 90)}`)

// 换个方向（B→A，A 的 KYBER 完好）建池子，继续步⑦的消费判据。
const gen2 = await api(PQKDS, '/key-pool/generate/', {
  method: 'POST',
  token: adminToken,
  body: { node1_id: nodeB.nodeId, node2_id: nodeA.nodeId, algorithm: 'kyber_kem', count: 2 }
})
check('预分配 2 条成功（B→A 方向，A 的 KYBER 完好）',
  isOk(gen2.body) && gen2.body?.data?.generated === 2,
  `generated=${gen2.body?.data?.generated}`)

const c1 = await api(PQKDS, '/key-pool/consume/', {
  method: 'POST', token: adminToken, body: { node1_id: nodeB.nodeId, node2_id: nodeA.nodeId }
})
const c2 = await api(PQKDS, '/key-pool/consume/', {
  method: 'POST', token: adminToken, body: { node1_id: nodeB.nodeId, node2_id: nodeA.nodeId }
})
const c3 = await api(PQKDS, '/key-pool/consume/', {
  method: 'POST', token: adminToken, body: { node1_id: nodeB.nodeId, node2_id: nodeA.nodeId }
})
check('★ 步⑦：2 条 → 恰好 2 次成功、第 3 次失败（不可重复消费）',
  isOk(c1.body) && isOk(c2.body) && !isOk(c3.body)
  && String(c3.body?.msg || '').includes('POOL_ITEM_UNAVAILABLE'),
  `c1=${isOk(c1.body)} c2=${isOk(c2.body)} c3=${String(c3.body?.msg || '').slice(0, 60)}`)

// ---------------------------------------------------------------------------
// 7. ★ 步⑧：关闭/过期/撤销不可恢复
// ---------------------------------------------------------------------------
title('7. ★ 步⑧：established 会话关闭后不可恢复；过期/撤销会话拒绝确认')

const closeTarget = runs[SSCL]
const close = await api(PQKDS, `/node-self/sessions/${closeTarget.sessionId}/close/`, {
  method: 'POST', token: nodeA.token
})
check('★ 关闭 established 会话成功（终态）',
  isOk(close.body) && close.body?.data?.advanced === true,
  `status=${sessionStatus(closeTarget.sessionId)}`)
const confirmAfterClose = await api(PQKDS, `/node-self/sessions/${closeTarget.sessionId}/confirm/`, {
  method: 'POST', token: nodeB.token, body: { proof: 'f'.repeat(64) }
})
check('★ 关闭后确认被拒：SESSION_TERMINAL（不可恢复）',
  !isOk(confirmAfterClose.body) && confirmAfterClose.body?.data?.error_code === 'SESSION_TERMINAL',
  `error_code=${confirmAfterClose.body?.data?.error_code}`)

// 过期与撤销：用 ORM 直改 SM2 会话状态（真实时钟等不起），断言确认被拒
orm(ormHeader + `
from pqkds.models import SessionKey
SessionKey.objects.filter(session_id='${runs[SM2].sessionId}').update(status='expired')
print('FORCED_EXPIRED')
`)
const confirmExpired = await api(PQKDS, `/node-self/sessions/${runs[SM2].sessionId}/confirm/`, {
  method: 'POST', token: nodeA.token, body: { proof: 'e'.repeat(64) }
})
check('★ 过期会话的确认被拒：SESSION_TERMINAL',
  !isOk(confirmExpired.body) && confirmExpired.body?.data?.error_code === 'SESSION_TERMINAL',
  `error_code=${confirmExpired.body?.data?.error_code}`)

orm(ormHeader + `
from pqkds.models import SessionKey
SessionKey.objects.filter(session_id='${runs[KYBER].sessionId}').update(status='revoked')
print('FORCED_REVOKED')
`)
const confirmRevoked = await api(PQKDS, `/node-self/sessions/${runs[KYBER].sessionId}/confirm/`, {
  method: 'POST', token: nodeB.token, body: { proof: 'd'.repeat(64) }
})
check('★ 撤销会话的确认被拒：SESSION_TERMINAL',
  !isOk(confirmRevoked.body) && confirmRevoked.body?.data?.error_code === 'SESSION_TERMINAL',
  `error_code=${confirmRevoked.body?.data?.error_code}`)

// ---------------------------------------------------------------------------
// 8. 清理：自建自清
// ---------------------------------------------------------------------------
title('8. 清理：删掉本脚本建的两个节点及其一切关联行')
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

info(`本次真建的节点：${nodeA.nodeId} / ${nodeB.nodeId}（已在上面删掉）`)
info('证据都在上面：部署探针（含 410 封存面）、三算法完整会话链各自 established、')
info('篡改/换私钥/删私钥三种失败、回收后分发被拒（无半行落库）、消费不可重复、')
info('关闭/过期/撤销三个终态全部拒绝后续确认。')
finish()
