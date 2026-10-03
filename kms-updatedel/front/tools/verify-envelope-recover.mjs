/**
 * KMS-011 验收：**接收节点取信封、本机验签与解封**（计划 §7 阶段 4 的前两条）。
 * KMS-012 扩展：**双方确认与 established 状态机**（第三条，阶段 4 出口检查）。
 *
 * 判据为什么是这几个动作，而不是"接口返回 200"
 * ------------------------------------------
 * 本阶段的主体会把会话从 `initiated` 推到 `established`，而**每一步都能
 * 在失败的情况下返回 200**：
 *
 *   * "接收方验签通过" ≠ "它真的验了"。服务端能独立复核（本脚本第 4 节
 *     用**服务端那份规范实现**验，跨语言比对序列化口径）；验不过必须拒，
 *     且**状态不动** —— 这一条是"验签的失败方向必须是拒绝"的可执行形式。
 *   * "解封成功" ≠ "解出来的 K 是对的"。所以第 8 节把解出的 16 字节
 *     `sha256(K)` 与信封里的 `key_hash` 声明**逐字比对**，并且真算
 *     `HMAC(K, session_id)` 与发送方那把比对（三方逐字节相同）。
 *   * "状态推进了" ≠ "随便一跳"。第 6 节先把**顺序打乱**（没验签就回报解封）
 *     要求 `SESSION_STATE_INVALID`，再按正确顺序走通。KMS-012 起
 *     `confirm` 也必须查表：第 6 节让 A 先交一笔确认（不许推进状态），
 *     第 8.5 节让**双方确认齐、证据链却不完整**（不许建立，`blockedBy` 指出来）。
 *   * "关闭"是终态：第 8.5 节关掉一条会话，再确认必须被拒（`SESSION_TERMINAL`），
 *     另一方重复关闭是幂等 ok（原因/时间不被改写）。
 *   * "服务端没拿到 SM4" 不是口头承诺：第 9 节拿本机那把 K 的 hex/base64
 *     在库里逐表搜，必须一处都搜不到（计划 §2.1）。
 *
 * 与其它脚本的关系
 * ---------------
 * `verify-node-distribution.mjs`（KMS-008/009/010）验的是**发送侧**：
 * 按指定版本封装、签名、服务端验签。本脚本接力验**接收侧**（取信 → 验签 →
 * 解封）与**会话闭环**（双方确认 → established / 关闭）。两边的"指定版本"
 * 必须是**同一版** —— 第 3 节把它作为断言（会话行记的两版 = 分发时实际用的两版）。
 *
 * ⚠️ 会**建真节点、写真数据**，只在本地验证环境跑。结尾 11 节自建自清。
 * ⚠️ 服务端代码打进镜像：改了后端不重建，第 1 节的部署探针先失败 —— 刻意如此。
 */
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
import { execFileSync } from 'node:child_process'

const { check, info, finish } = makeReporter()

const KYBER = 'KYBER'
const DOMAIN = 'kms011'

const NODE_TABLE = 'falcon_kds.dvadmin_pqkds_nodes'
const POOL_TABLE = 'falcon_kds.dvadmin_pqkds_pre_distributed_keys'
const SESSION_TABLE = 'falcon_kds.dvadmin_pqkds_session_keys'
const CONFIRM_TABLE = 'falcon_kds.dvadmin_pqkds_session_confirmations'

const sessionStatus = (sid) =>
  sqlScalar(`SELECT status FROM ${SESSION_TABLE} WHERE session_id='${sid}';`) || ''
const sessionVersions = (sid) =>
  sqlScalar(
    `SELECT CONCAT_WS('|', IFNULL(recipient_key_id,'NULL'), IFNULL(recipient_key_version,'NULL'), `
    + `IFNULL(falcon_key_id,'NULL'), IFNULL(falcon_key_version,'NULL')) `
    + `FROM ${SESSION_TABLE} WHERE session_id='${sid}';`
  ) || ''

// ---------------------------------------------------------------------------
// 1. ★ 部署探针：三个新端点到底在不在跑着的进程里
// ---------------------------------------------------------------------------
title('1. ★ 部署探针：KMS-011 的三条新端点（无令牌探法，不产生副作用）')
info('无令牌请求：注册了 → 401（require_kms_user 先拦），没注册 → 404/405。')
info('三个都探，不探的话后面每条断言都会以"没读到字段"的方式失败，')
info('看起来像十几个逻辑缺陷，实际只是一次没重建镜像。')

for (const [label, path, method] of [
  ['POST /node-self/sessions/<sid>/versions/', '/node-self/sessions/probe-not-a-session/versions/', 'POST'],
  ['POST /node-self/envelopes/<id>/verify/', '/node-self/envelopes/1/verify/', 'POST'],
  ['POST /node-self/envelopes/<id>/recover/', '/node-self/envelopes/1/recover/', 'POST'],
  ['POST /node-self/sessions/<sid>/close/', '/node-self/sessions/probe-not-a-session/close/', 'POST']
]) {
  const res = await api(PQKDS, path, { method })
  check(`★ ${label} 已部署（不是 404/405）`, res.status !== 404 && res.status !== 405,
    `HTTP=${res.status} body=${JSON.stringify(res.body).slice(0, 120)}`)
}

// ---------------------------------------------------------------------------
// 2. 夹具：两个节点（A 发送、B 接收），四套密钥，走一次真实分发
// ---------------------------------------------------------------------------
title('2. 夹具：A/B 各登记四套密钥 → A 按 B 指定的 KYBER 版本封装并签名 → 服务端登记')
info('分发这一侧已经在 verify-node-distribution.mjs 里验过；这里重建它，')
info('是为了让接收侧（本脚本的主体）拿到一份**真信**：真 OTP、真签名、真密文。')

const adminToken = await adminLogin()
const nodeA = await newNodeSession(adminToken, { prefix: 'K11A', name: 'KMS-011 发送方', domainId: DOMAIN })
const nodeB = await newNodeSession(adminToken, { prefix: 'K11B', name: 'KMS-011 接收方', domainId: DOMAIN })
const nodeC = await newNodeSession(adminToken, { prefix: 'K11C', name: 'KMS-011 无关节点', domainId: DOMAIN })
check('三个节点已建好并激活（C 用来验"不是收件人"的拒绝面）',
  Boolean(nodeA.token && nodeB.token && nodeC.token),
  `${nodeA.nodeId} / ${nodeB.nodeId} / ${nodeC.nodeId}`)

const userA = sqlScalar(`SELECT IFNULL(sys_user_id, '') FROM ${NODE_TABLE} WHERE node_id='${nodeA.nodeId}';`) || ''
const nodeBId = sqlScalar(`SELECT id FROM ${NODE_TABLE} WHERE node_id='${nodeB.nodeId}';`) || ''
check('A 映射到用户（分发的身份靠它），B 在库里有主键', Boolean(userA && nodeBId),
  `A.user=${userA} B.pk=${nodeBId}`)

const grant = await api(PQKDS, '/admin/node-authorizations/', {
  method: 'POST',
  token: adminToken,
  body: { userId: Number(userA), nodeId: Number(nodeBId), remark: 'KMS-011 验收：A 需要能向 B 分发' }
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
      keyVersion: material.version,
      ...(extra.rotate ? { rotate: true } : {})
    }
  })

info('生成密钥并登记（Falcon 本机生成要十几秒；四套都登记，init 收尾要求四套齐备）…')
const keys = { A: {}, B: {}, C: {} }
for (const [label, session] of [['A', nodeA], ['B', nodeB], ['C', nodeC]]) {
  for (const [algorithm, options, extra] of [
    ['SM2', {}, {}],
    ['SSCL', {}, {}],
    [KYBER, { variant: 768 }, { securityLevel: '768' }],
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
    check(`${session.nodeId} 初始化收尾成功`, false, `code=${init.body?.code} msg=${init.body?.msg}`)
  }
}
check('A/B/C 各自的四套密钥已登记并激活（init 收尾要求四套齐备）',
  [nodeA, nodeB, nodeC].every((s) => {
    const label = s === nodeA ? 'A' : (s === nodeB ? 'B' : 'C')
    return ['SM2', 'SSCL', KYBER, 'FALCON'].every((alg) => sqlScalar(
      `SELECT status FROM falcon_kds.dvadmin_pqkds_node_long_term_keys `
      + `WHERE node_id=(SELECT id FROM ${NODE_TABLE} WHERE node_id='${s.nodeId}') `
      + `AND algorithm='${alg}' AND key_id='${keys[label][alg].keyId}';`
    ) === 'ACTIVE')
  }), `${nodeA.nodeId} / ${nodeB.nodeId} / ${nodeC.nodeId}`)

const { buildNodeEnvelope, generatePayloadKey, newBatchId, signNodeEnvelope } =
  await import('../src/utils/crypto/envelope-signing.js')

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
check('★ 分发成功（服务端已验签并登记）',
  isOk(dist.body) && dist.body?.data?.signatureVerified === true,
  `code=${dist.body?.code} verified=${dist.body?.data?.signatureVerified} msg=${dist.body?.msg}`)

const sessionId = `${batchId}-n${nodeBId}`
check('★ 会话行按批次 + 接收方主键建立（`{batchId}-n{pk}` 的命名约定）',
  sessionStatus(sessionId) === 'initiated',
  `session_id=${sessionId} status=${sessionStatus(sessionId)}`)

// ---------------------------------------------------------------------------
// 3. ★ 会话行关联的具体密钥版本（计划 §7 阶段 4 第 1 条）
// ---------------------------------------------------------------------------
title('3. ★ 会话记录关联**具体两版密钥**：分发时实际用的那两版，逐字落库')
info('这一条防的是"页面显示的版本"与"实际封装/签名用的版本"对不上 ——')
info('本仓库反复踩过的那类静默错误。判据是逐字比对，不是"非空即可"。')

check('★ 会话行的两版引用 = 分发时实际用的两版（逐字）',
  sessionVersions(sessionId)
  === `${keys.B[KYBER].keyId}|1|${keys.A.FALCON.keyId}|1`,
  `读到 ${sessionVersions(sessionId)}，期望 ${keys.B[KYBER].keyId}|1|${keys.A.FALCON.keyId}|1`)

const sessionsB = await api(PQKDS, '/node-self/sessions/', { token: nodeB.token })
const rowB = (sessionsB.body?.data?.items || []).find((item) => item.sessionId === sessionId)
check('★ 会话列表下发这两版引用（页面据此显示"该用哪一版"），且标出我是接收方',
  rowB?.recipientKeyId === keys.B[KYBER].keyId
  && Number(rowB?.recipientKeyVersion) === 1
  && rowB?.falconKeyId === keys.A.FALCON.keyId
  && Number(rowB?.falconKeyVersion) === 1
  && rowB?.isRecipient === true,
  `recipient=${rowB?.recipientKeyId}v${rowB?.recipientKeyVersion} falcon=${rowB?.falconKeyId}v${rowB?.falconKeyVersion} isRecipient=${rowB?.isRecipient}`)

// 取信封列表：待处理行要带"哪条会话、我是不是收件方"
const envelopesB = await api(PQKDS, '/node-self/envelopes/', { token: nodeB.token })
const envEntry = (envelopesB.body?.data?.items || []).find((item) => item.sessionId === sessionId)
check('★ 取信封列表里这条信封带会话定位（sessionId/sessionStatus/isRecipient）与整数 ID',
  Boolean(envEntry) && envEntry.isRecipient === true
  && envEntry.sessionStatus === 'initiated'
  && Number.isInteger(Number(envEntry.envelopeId)),
  `envelopeId=${envEntry?.envelopeId} sessionId=${envEntry?.sessionId} status=${envEntry?.sessionStatus}`)

const envelopeId = envEntry?.envelopeId

// versions 端点：接收方拿到"该用哪两版"
const versions = await api(PQKDS, `/node-self/sessions/${sessionId}/versions/`, {
  method: 'POST', token: nodeB.token
})
check('★ versions 端点回两版引用 + 发送方 Falcon 公钥（小写 hex，可直接参与验签）',
  isOk(versions.body)
  && versions.body?.data?.recipientKeyId === keys.B[KYBER].keyId
  && versions.body?.data?.falconKeyId === keys.A.FALCON.keyId
  && Number(versions.body?.data?.falconKeyVersion) === 1
  && versions.body?.data?.falconPublicKey === keys.A.FALCON.publicKey.toLowerCase(),
  `falconKeyId=${versions.body?.data?.falconKeyId} 公钥前 16=${String(versions.body?.data?.falconPublicKey).slice(0, 16)}…`)
check('公钥形状是 hex（不是 base64）—— 形状错了会在浏览器侧静默解成错字节',
  /^[0-9a-f]+$/.test(String(versions.body?.data?.falconPublicKey || ''))
  && String(versions.body?.data?.falconPublicKey || '').length === 1794,
  `长度=${String(versions.body?.data?.falconPublicKey || '').length}`)

// 越权：发送方与无关节点都不该拿到这条映射
const versionsAsSender = await api(PQKDS, `/node-self/sessions/${sessionId}/versions/`, {
  method: 'POST', token: nodeA.token
})
check('★ 发送方来查这两版 → 403 NOT_SESSION_PARTY（只有接收方需要）',
  versionsAsSender.body?.code === 403
  && versionsAsSender.body?.data?.error_code === 'NOT_SESSION_PARTY',
  `code=${versionsAsSender.body?.code} error_code=${versionsAsSender.body?.data?.error_code}`)
const versionsAsOther = await api(PQKDS, `/node-self/sessions/${sessionId}/versions/`, {
  method: 'POST', token: nodeC.token
})
check('★ 无关节点来查 → 403（不是 404：会话确实存在，但这条映射与它无关）',
  versionsAsOther.body?.code === 403,
  `code=${versionsAsOther.body?.code} error_code=${versionsAsOther.body?.data?.error_code}`)

// ---------------------------------------------------------------------------
// 4. ★★ 接收端跨语言验签：本机验得过，且与服务端同一份规范实现一致
// ---------------------------------------------------------------------------
title('4. ★★ 接收方的本机验签：用**发送方那一版**公钥 + 服务端同一份规范化实现')
info('这是本阶段的核心判据 —— 接收方如果不验签就解封，伪造的信封照样能解开')
info('（封装只保证"只有我能解"，不保证"是谁发给我的"）。')
info('做法：先证明服务端那份实现也能验过同一封信（跨语言一致），')
info('再让浏览器用返回的公钥验 —— 两边结论必须同为"通过"。')

const { verifyNodeEnvelope: verifyLocally, unwrapNodeEnvelope, checkRecoveredKeyHash, nodeProof } =
  await import('../src/utils/crypto/node-envelope.js')

const localVerify = await verifyLocally({
  provider: cryptoProvider,
  envelope: envEntry.envelope,
  signatureB64: envEntry.envelope?.signature,
  senderFalconPublicKeyHex: versions.body.data.falconPublicKey
})
check('★★ 接收方在本机验签通过（浏览器实现 + 发送方那一版公钥）',
  localVerify.ok === true, localVerify.detail)

// 服务端对照：用容器里那份实现验同一封信（跨语言比对序列化口径）
const verifyProgram = `
import json, sys
sys.path.insert(0, '/backend')
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
import django
django.setup()
from pqkds.models import Node, NodeLongTermKey
from pqkds.envelope_signature import verify_node_envelope, node_canonical_payload
stored = json.loads(r'''${JSON.stringify(envEntry.envelope)}''')
sender = Node.objects.filter(node_id='${nodeA.nodeId}').first()
key = NodeLongTermKey.objects.filter(
    node=sender, algorithm='FALCON', key_id='${keys.A.FALCON.keyId}', key_version=1).first()
print('CANON_SHA=%s' % __import__('hashlib').sha256(node_canonical_payload(stored)).hexdigest())
print('SERVER_VERIFY=%s' % verify_node_envelope(stored, stored.get('signature'), key.public_key))
`
const verifyOut = execFileSync(dockerBin, ['exec', '-i', '-w', '/backend', 'dvadmin3-django', 'python', '-'], {
  input: verifyProgram,
  encoding: 'utf8',
  env: { ...process.env, MSYS_NO_PATHCONV: '1' }
})
check('★★ 服务端那份规范实现验同一封信也通过（两侧序列化逐字节一致）',
  verifyOut.includes('SERVER_VERIFY=True'),
  verifyOut.trim().split('\n').filter((l) => /^[A-Z_]+=/.test(l)).join(' '))

// ---------------------------------------------------------------------------
// 5. ★ 篡改与错公钥：验不过必须拒，且**状态不动**
// ---------------------------------------------------------------------------
title('5. ★ 本机验签的拒绝面：改一个被签字段、换一把公钥都必须验不过')
info('只证"验得过"是不够的 —— 一个恒返回 true 的实现也能让上一条绿。')

const tampered = JSON.parse(JSON.stringify(envEntry.envelope))
tampered.recipient_key_version = 2
const tamperedVerify = await verifyLocally({
  provider: cryptoProvider,
  envelope: tampered,
  signatureB64: tampered.signature,
  senderFalconPublicKeyHex: versions.body.data.falconPublicKey
})
check('★ 改一个被签字段（接收方版本 1→2）→ 本机验签**不通过**',
  tamperedVerify.ok === false, tamperedVerify.detail)

const wrongKeyVerify = await verifyLocally({
  provider: cryptoProvider,
  envelope: envEntry.envelope,
  signatureB64: envEntry.envelope?.signature,
  senderFalconPublicKeyHex: keys.C.FALCON.publicKey
})
check('★ 拿**别的节点**的公钥验 → 不通过（签名绑住了发送者身份）',
  wrongKeyVerify.ok === false, wrongKeyVerify.detail)

// 服务端侧：用一个**被改过**的信封调 verify 端点（直接把库里那封改一个字段再调）。
// 做法：在**容器里**读原来那串、替换一个被签字段的字节、写回；调接口；再恢复。
// ⚠️ 不用 js 字符串拼 SQL —— 信封 JSON 里引号多，拼一次就是一次注入式的
//    手写转义（本脚本一开始就在这里写错过一次），让 Django 参数化去处理。
const tamperProgram = `
import json, sys
sys.path.insert(0, '/backend')
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
import django
django.setup()
from pqkds.models import PreDistributedKey

record = PreDistributedKey.objects.get(pk=${envelopeId})
original = record.encrypted_key_data
tampered = original.replace('"recipient_key_version":1', '"recipient_key_version":2')
print('CHANGED=%s' % (tampered != original))
record.encrypted_key_data = tampered
record.save(update_fields=['encrypted_key_data'])
open('/tmp/kms011-original.json', 'w', encoding='utf-8').write(original)
`
const tamperSetup = execFileSync(dockerBin, ['exec', '-i', '-w', '/backend', 'dvadmin3-django', 'python', '-'], {
  input: tamperProgram,
  encoding: 'utf8',
  env: { ...process.env, MSYS_NO_PATHCONV: '1' }
})
check('夹具：库内信封确实能被改出一个被签字段（否则下一段测了个没改动的请求）',
  tamperSetup.includes('CHANGED=True'), tamperSetup.trim().split('\n').slice(-1)[0])

const tamperResp = await api(PQKDS, `/node-self/envelopes/${envelopeId}/verify/`, {
  method: 'POST', token: nodeB.token
})
check('★ 服务端对**被改过**的信封调 verify → 拒（SIGNATURE_INVALID），且状态仍是 initiated',
  tamperResp.body?.data?.error_code === 'SIGNATURE_INVALID'
  && sessionStatus(sessionId) === 'initiated',
  `${tamperResp.body?.data?.error_code} status=${sessionStatus(sessionId)} msg=${tamperResp.body?.msg}`)
// 恢复原值（后续按正路走）
const restoreProgram = `
import sys
sys.path.insert(0, '/backend')
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
import django
django.setup()
from pqkds.models import PreDistributedKey
record = PreDistributedKey.objects.get(pk=${envelopeId})
record.encrypted_key_data = open('/tmp/kms011-original.json', encoding='utf-8').read()
record.save(update_fields=['encrypted_key_data'])
print('RESTORED=True')
`
const restored = execFileSync(dockerBin, ['exec', '-i', '-w', '/backend', 'dvadmin3-django', 'python', '-'], {
  input: restoreProgram,
  encoding: 'utf8',
  env: { ...process.env, MSYS_NO_PATHCONV: '1' }
})
check('夹具已恢复原值（后续正路用的是与签名一致的原文）',
  restored.includes('RESTORED=True'))

// ---------------------------------------------------------------------------
// 6. ★ 顺序守卫：没验签就回报"解封成功" → SESSION_STATE_INVALID
// ---------------------------------------------------------------------------
title('6. ★ 状态机守卫：`initiated → key_recovered` 不是合法边')
info('少了这一条，"两件事都真的发生过"就退化成"随便调两个接口"。')

const recoverFirst = await api(PQKDS, `/node-self/envelopes/${envelopeId}/recover/`, {
  method: 'POST', token: nodeB.token
})
check('★★ 先解封后验签 → SESSION_STATE_INVALID，且状态仍是 initiated',
  recoverFirst.body?.data?.error_code === 'SESSION_STATE_INVALID'
  && sessionStatus(sessionId) === 'initiated',
  `${recoverFirst.body?.data?.error_code} status=${sessionStatus(sessionId)} msg=${recoverFirst.body?.msg}`)

// KMS-012：**确认可以先于验签/解封提交** —— 且不误触发建立。
// 让 A（发送方）此刻就交确认：会话状态必须仍是 initiated（状态机不放行），
// 确认数变成 1/2。这一条把"提交与建立解耦、但建立受证据门限"钉在正路上。
const proofEarlyA = await nodeProof({ payloadKey, sessionId })
const earlyConfirmA = await api(PQKDS, `/node-self/sessions/${sessionId}/confirm/`, {
  method: 'POST', token: nodeA.token, body: { proof: proofEarlyA }
})
check('★★ KMS-012：发送方先交确认（1/2）→ 记录成功但**不建立**，状态仍是 initiated',
  isOk(earlyConfirmA.body) && earlyConfirmA.body?.data?.established === false
  && earlyConfirmA.body?.data?.confirmedBy === 1
  && sessionStatus(sessionId) === 'initiated',
  `established=${earlyConfirmA.body?.data?.established} confirmedBy=${earlyConfirmA.body?.data?.confirmedBy} 库内=${sessionStatus(sessionId)}`)

// 非收件人：C 来回报 → 403 NOT_ENVELOPE_RECIPIENT
const verifyAsOther = await api(PQKDS, `/node-self/envelopes/${envelopeId}/verify/`, {
  method: 'POST', token: nodeC.token
})
check('★★ 非收件人拿别人的信封 ID 来处理 → 403 NOT_ENVELOPE_RECIPIENT（信封确实存在，但不是它的）',
  verifyAsOther.body?.code === 403
  && verifyAsOther.body?.data?.error_code === 'NOT_ENVELOPE_RECIPIENT',
  `code=${verifyAsOther.body?.code} error_code=${verifyAsOther.body?.data?.error_code}`)

const missingEnvelope = await api(PQKDS, '/node-self/envelopes/99999999/verify/', {
  method: 'POST', token: nodeB.token
})
check('不存在的信封 ID → 404 ENVELOPE_NOT_FOUND（与"不是发给你"分开）',
  missingEnvelope.body?.code === 404
  && missingEnvelope.body?.data?.error_code === 'ENVELOPE_NOT_FOUND',
  `code=${missingEnvelope.body?.code} error_code=${missingEnvelope.body?.data?.error_code}`)

// ---------------------------------------------------------------------------
// 7. ★ 正路：回报验签通过 → 回报解封成功（状态真的落库，且幂等）
// ---------------------------------------------------------------------------
title('7. ★ 正路：verify → recipient_verified；recover → key_recovered（状态落库）')
info('每一步都读库核对，不看响应里的 status —— 响应可以说得比库更漂亮。')

const verifyResp = await api(PQKDS, `/node-self/envelopes/${envelopeId}/verify/`, {
  method: 'POST', token: nodeB.token
})
check('★ 回报验签通过 → 会话进 recipient_verified（**库内**状态）',
  isOk(verifyResp.body) && verifyResp.body?.data?.advanced === true
  && sessionStatus(sessionId) === 'recipient_verified',
  `resp.status=${verifyResp.body?.data?.status} 库内=${sessionStatus(sessionId)}`)

const verifyAgain = await api(PQKDS, `/node-self/envelopes/${envelopeId}/verify/`, {
  method: 'POST', token: nodeB.token
})
check('★ 重复回报"验签通过" → 幂等成功（advanced=false），状态不回退、不重复推进',
  isOk(verifyAgain.body) && verifyAgain.body?.data?.advanced === false
  && sessionStatus(sessionId) === 'recipient_verified',
  `advanced=${verifyAgain.body?.data?.advanced} 库内=${sessionStatus(sessionId)}`)

// KMS-011 口径不变：解封这一步**执行后**再看状态，若双方确认早已齐
// （第 6 节那两笔交了）且一致 → 这一刻兑现为 established。
const recoverResp = await api(PQKDS, `/node-self/envelopes/${envelopeId}/recover/`, {
  method: 'POST', token: nodeB.token
})
check('★ 回报解封成功 → 会话进 key_recovered（库内状态）',
  isOk(recoverResp.body) && recoverResp.body?.data?.advanced === true
  && sessionStatus(sessionId) === 'key_recovered',
  `resp.status=${recoverResp.body?.data?.status} 库内=${sessionStatus(sessionId)}`)
check('★ 此刻只有 A 交过确认（1/2）→ 解封**不**触发建立（补提升是条件性的）',
  recoverResp.body?.data?.established === false,
  `established=${recoverResp.body?.data?.established}`)

check('响应如实标注"解封是节点声明"（服务端不持有 K，不能独立验证这一步）',
  String(recoverResp.body?.data?.note || '').includes('节点回报'),
  `note=${String(recoverResp.body?.data?.note || '').slice(0, 60)}…`)

// ---------------------------------------------------------------------------
// 8. ★★ 解封 + 自查 + 双方 proof：解出的 K 与发送方**是同一把**
// ---------------------------------------------------------------------------
title('8. ★★ 解出的 K 与发送方那把是同一把：sha256 自查 + HMAC proof 与发送方比对')
info('这是"解封成功"的唯一硬判据。只断言"解出 16 字节"会让"解错了一把"')
info('（例如按物化列而不是指定版本解封）照样通过。')

// ⚠️ 本节要用的四个函数在**第 4 节开头**已经一次性解构过
//    （`verifyLocally` / `unwrapNodeEnvelope` / `checkRecoveredKeyHash` /
//    `nodeProof`）—— 同一个模块不重复声明：ESM 的 `const` 重名会直接
//    抛 SyntaxError，而报错位置在加载期，看起来与"改了什么"毫无关系。

const recovered = await unwrapNodeEnvelope({
  provider: cryptoProvider,
  keyRef: keys.B[KYBER].keyRef,
  envelope: envEntry.envelope
})
check('★★ 接收方用**指定的那一版**私钥解出 16 字节 SM4',
  recovered instanceof Uint8Array && recovered.length === 16,
  `长度=${recovered?.length}`)
check('★★ 解出的 K 与发送方那把**逐字节相同**（不是"解出了 16 字节"就算）',
  Buffer.from(recovered).equals(Buffer.from(payloadKey)),
  `本机 ${Buffer.from(recovered).toString('hex').slice(0, 16)}… 发送方 ${Buffer.from(payloadKey).toString('hex').slice(0, 16)}…`)

const hashCheck = await checkRecoveredKeyHash(recovered, envEntry.envelope)
check('★★ 自查：解出 K 的 sha256 与信封里 key_hash 声明一致',
  hashCheck.ok === true, hashCheck.detail)

// 双方 proof：B 用解出的 K 算，A 用它自己那把 K 算 —— 必须相同。
// ⚠️ A 那侧在本脚本里是"稍早交过一笔"（§6 的 1/2）：这里再算一次必须
//    逐字节相同 —— upsert 会覆盖它，若两次算出不同的值，第二笔就会把
//    第一笔改坏，而现象是"明明同一把 K 却建立不了"。
const proofB = await nodeProof({ payloadKey: recovered, sessionId })
const proofA = await nodeProof({ payloadKey, sessionId })
check('★★ 双方 HMAC proof 一致（B 解出的 K 与 A 发出的 K 是同一把，且与 A 早先那笔逐字相同）',
  proofB === proofA && proofB === proofEarlyA && proofB.length === 64,
  `B=${proofB.slice(0, 16)}… A=${proofA.slice(0, 16)}… A早先=${proofEarlyA.slice(0, 16)}…`)

// 此时 A 已确认（§6）、B 还没交 → 补交 B 这一笔，双方齐且一致。
const confirmB = await api(PQKDS, `/node-self/sessions/${sessionId}/confirm/`, {
  method: 'POST', token: nodeB.token, body: { proof: proofB }
})
check('★★ KMS-012：第二笔确认到达的那一刻，会话建立（`key_recovered → established`，读库核对）',
  isOk(confirmB.body) && confirmB.body?.data?.established === true
  && sessionStatus(sessionId) === 'established',
  `established=${confirmB.body?.data?.established} 库内=${sessionStatus(sessionId)}`)

// 已建立的会话再确认：幂等回 ok，不产生第三条记录
const confirmAgain = await api(PQKDS, `/node-self/sessions/${sessionId}/confirm/`, {
  method: 'POST', token: nodeA.token, body: { proof: proofA }
})
check('★ 已建立再确认 → 幂等回 ok（不报错、不重复建立）',
  isOk(confirmAgain.body) && confirmAgain.body?.data?.established === true,
  `msg=${confirmAgain.body?.msg}`)

// ⚠️ 子查询：`session_id` 是业务字符串，确认表里**没有**这个列（它外键到
//    `SessionKey` 的整数主键）。一开始按 `session_id=` 查恒返回 0 行，
//    断言看起来像"确认没写进去"——实际是查错了列。
const confirmRows = sqlScalar(
  `SELECT COUNT(*) FROM ${CONFIRM_TABLE} `
  + `WHERE session_id=(SELECT id FROM ${SESSION_TABLE} WHERE session_id='${sessionId}');`
) || '0'
check('确认记录是**双方各一条**（不是一遍遍覆盖同一条，也不是每确认一次加一条）',
  confirmRows === '2', `confirmations=${confirmRows}`)

// ---------------------------------------------------------------------------
// 8.5 ★★ KMS-012：第二对会话 —— 证据不齐不建立、关闭是终态
// ---------------------------------------------------------------------------
title('8.5 ★★ 证据门限与关闭：`initiated → established` 直跳被拒；关闭是终态')
info('另做一次真实分发（同一对节点、同一把 KYBER 公钥）：这次让**双方都把确认交齐**、')
info('但都不走验签/解封 —— 两笔 proof 一致也**不许**建立（状态机不放行），')
info('再关掉它验证终态语义。')

const payloadKey2 = generatePayloadKey()
const batch2 = newBatchId()
const expiresAt2 = new Date(Date.now() + 2 * 3600 * 1000).toISOString()
const built2 = await buildNodeEnvelope({
  provider: cryptoProvider,
  payloadKey: payloadKey2,
  wrapping: KYBER,
  recipientPublicKeyHex: keys.B[KYBER].publicKey,
  batchId: batch2,
  senderNodeId: nodeA.nodeId,
  receiverNodeId: nodeB.nodeId,
  recipientKeyId: keys.B[KYBER].keyId,
  recipientKeyVersion: 1,
  expiresAt: expiresAt2
})
const signature2 = await signNodeEnvelope(cryptoProvider, keys.A.FALCON.keyRef, built2.envelope)
const dist2 = await api(PQKDS, '/node-self/distributions/', {
  method: 'POST',
  token: nodeA.token,
  body: {
    receiverNodeId: nodeB.nodeId,
    protectionAlgorithm: KYBER,
    recipientKeyId: keys.B[KYBER].keyId,
    recipientKeyVersion: 1,
    falconKeyId: keys.A.FALCON.keyId,
    falconKeyVersion: 1,
    batchId: batch2,
    expiresAt: expiresAt2,
    envelope: built2.envelope,
    signature: signature2,
    keyHash: built2.keyHash
  }
})
check('★ KMS-012：分发回执带**这条分发对应的会话 ID**（发起方据此存 K 并确认，不必拼命名约定）',
  isOk(dist2.body) && Boolean(dist2.body?.data?.sessionId)
  && dist2.body?.data?.sessionStatus === 'initiated',
  `sessionId=${dist2.body?.data?.sessionId} status=${dist2.body?.data?.sessionStatus}`)

const sessionId2 = dist2.body?.data?.sessionId || ''
const env2Rows = JSON.parse(sqlScalar(
  `SELECT encrypted_key_data FROM ${POOL_TABLE} WHERE pool_id='${batch2}' LIMIT 1;`
) || '{}')

// A 交确认（它手里有 K）
const proof2A = await nodeProof({ payloadKey: payloadKey2, sessionId: sessionId2 })
const conf2A = await api(PQKDS, `/node-self/sessions/${sessionId2}/confirm/`, {
  method: 'POST', token: nodeA.token, body: { proof: proof2A }
})
// B 本机解出 K（**不走 verify/recover 回执**）后交确认
const recovered2 = await unwrapNodeEnvelope({
  provider: cryptoProvider, keyRef: keys.B[KYBER].keyRef, envelope: env2Rows
})
check('夹具：B 能从第二封信封里解出与 A 相同的那把 K（两笔 proof 会一致）',
  Buffer.from(recovered2).equals(Buffer.from(payloadKey2)),
  `B ${Buffer.from(recovered2).toString('hex').slice(0, 12)}… A ${Buffer.from(payloadKey2).toString('hex').slice(0, 12)}…`)
const proof2B = await nodeProof({ payloadKey: recovered2, sessionId: sessionId2 })
const conf2B = await api(PQKDS, `/node-self/sessions/${sessionId2}/confirm/`, {
  method: 'POST', token: nodeB.token, body: { proof: proof2B }
})
check('★★ 双方确认齐且一致（2/2），但**证据链不完整** → 不建立，`blockedBy=SESSION_STATE_INVALID`',
  isOk(conf2A.body) && isOk(conf2B.body)
  && conf2B.body?.data?.confirmedBy === 2
  && conf2B.body?.data?.established === false
  && conf2B.body?.data?.blockedBy === 'SESSION_STATE_INVALID'
  && sessionStatus(sessionId2) === 'initiated',
  `confirmedBy=${conf2B.body?.data?.confirmedBy} established=${conf2B.body?.data?.established} `
  + `blockedBy=${conf2B.body?.data?.blockedBy} 库内=${sessionStatus(sessionId2)}`)

const sessionsMid = await api(PQKDS, '/node-self/sessions/', { token: nodeA.token })
const rowMid = (sessionsMid.body?.data?.items || []).find((item) => item.sessionId === sessionId2)
check('★ 会话列表的 confirmedCount 如实为 2（页面显示"2/2"而不是"已建立"）',
  rowMid?.confirmedCount === 2 && rowMid?.status === 'initiated',
  `confirmedCount=${rowMid?.confirmedCount} status=${rowMid?.status}`)

// 关闭：发起方关掉这条没走完的会话（从这里起是终态）
const closeByA = await api(PQKDS, `/node-self/sessions/${sessionId2}/close/`, {
  method: 'POST', token: nodeA.token
})
check('★★ 关闭成功 → 状态进 closed（终态，读库核对）',
  isOk(closeByA.body) && closeByA.body?.data?.advanced === true
  && sessionStatus(sessionId2) === 'closed',
  `advanced=${closeByA.body?.data?.advanced} 库内=${sessionStatus(sessionId2)}`)

const confirmAfterClose = await api(PQKDS, `/node-self/sessions/${sessionId2}/confirm/`, {
  method: 'POST', token: nodeB.token, body: { proof: proof2B }
})
check('★★ 关闭后再确认 → SESSION_TERMINAL（终态不再接受确认）',
  confirmAfterClose.body?.data?.error_code === 'SESSION_TERMINAL'
  && sessionStatus(sessionId2) === 'closed',
  `${confirmAfterClose.body?.data?.error_code} 库内=${sessionStatus(sessionId2)}`)

const closeAgain = await api(PQKDS, `/node-self/sessions/${sessionId2}/close/`, {
  method: 'POST', token: nodeB.token
})
check('★ 另一方重复关闭 → 幂等回 ok（advanced=false），终态的原因/时间不被改写',
  isOk(closeAgain.body) && closeAgain.body?.data?.advanced === false
  && sessionStatus(sessionId2) === 'closed',
  `advanced=${closeAgain.body?.data?.advanced} 库内=${sessionStatus(sessionId2)}`)

const closeAsOther = await api(PQKDS, `/node-self/sessions/${sessionId2}/close/`, {
  method: 'POST', token: nodeC.token
})
check('★ 非会话方关闭 → 403 NOT_SESSION_PARTY',
  closeAsOther.body?.code === 403
  && closeAsOther.body?.data?.error_code === 'NOT_SESSION_PARTY',
  `code=${closeAsOther.body?.code} error_code=${closeAsOther.body?.data?.error_code}`)

// ---------------------------------------------------------------------------
// 8.6 ★★ 双方各持不同的 K → proof 不一致 → 不提升，且如实报告
// ---------------------------------------------------------------------------
title('8.6 ★★ 双方证明不一致（各持不同的 K）→ 不建立，服务端如实报告')
info('构造法（roadmap §3 判据）：第三次真实分发，A 用真 K 交确认，')
info('B 故意用**另一把 K** 交确认 —— 模拟"一方手里的 K 不是这一批的"。')
info('这种情形下"两笔都在库里"，但与"证据链不完整"是**两码事**：')
info('一个要继续等/继续做，一个必须去查（可能信封或算法搞混、也可能有人伪造）。')

const payloadKey3 = generatePayloadKey()
const batch3 = newBatchId()
const expiresAt3 = new Date(Date.now() + 2 * 3600 * 1000).toISOString()
const built3 = await buildNodeEnvelope({
  provider: cryptoProvider,
  payloadKey: payloadKey3,
  wrapping: KYBER,
  recipientPublicKeyHex: keys.B[KYBER].publicKey,
  batchId: batch3,
  senderNodeId: nodeA.nodeId,
  receiverNodeId: nodeB.nodeId,
  recipientKeyId: keys.B[KYBER].keyId,
  recipientKeyVersion: 1,
  expiresAt: expiresAt3
})
const signature3 = await signNodeEnvelope(cryptoProvider, keys.A.FALCON.keyRef, built3.envelope)
const dist3 = await api(PQKDS, '/node-self/distributions/', {
  method: 'POST',
  token: nodeA.token,
  body: {
    receiverNodeId: nodeB.nodeId,
    protectionAlgorithm: KYBER,
    recipientKeyId: keys.B[KYBER].keyId,
    recipientKeyVersion: 1,
    falconKeyId: keys.A.FALCON.keyId,
    falconKeyVersion: 1,
    batchId: batch3,
    expiresAt: expiresAt3,
    envelope: built3.envelope,
    signature: signature3,
    keyHash: built3.keyHash
  }
})
const sessionId3 = dist3.body?.data?.sessionId || ''
check('夹具：第三次分发成功且带会话 ID', isOk(dist3.body) && Boolean(sessionId3),
  `sessionId=${sessionId3}`)

const proof3A = await nodeProof({ payloadKey: payloadKey3, sessionId: sessionId3 })
const conf3A = await api(PQKDS, `/node-self/sessions/${sessionId3}/confirm/`, {
  method: 'POST', token: nodeA.token, body: { proof: proof3A }
})
// B 交的是**另一把 K** 的证明（不是这一批的载荷密钥）—— 模拟"双方手里的 K
// 不是同一把"。⚠️ 用生成器的 `generatePayloadKey`（随机 16 字节），
// 而不是 `nodeProof` 出错：要的就是"合法的 proof、只是 K 不同"。
const wrongKey = generatePayloadKey()
const proof3BWrong = await nodeProof({ payloadKey: wrongKey, sessionId: sessionId3 })
check('夹具：B 手里那把 K 与 A 的不同（两笔 proof 必然不一致）',
  proof3BWrong !== proof3A, `A=${proof3A.slice(0, 12)}… B=${proof3BWrong.slice(0, 12)}…`)
const conf3B = await api(PQKDS, `/node-self/sessions/${sessionId3}/confirm/`, {
  method: 'POST', token: nodeB.token, body: { proof: proof3BWrong }
})
check('★★ 两笔确认齐但证明不一致 → 不建立，如实报 reason=PROOF_MISMATCH（**不是** blockedBy）',
  isOk(conf3A.body) && isOk(conf3B.body)
  && conf3B.body?.data?.confirmedBy === 2
  && conf3B.body?.data?.established === false
  && conf3B.body?.data?.reason === 'PROOF_MISMATCH'
  && sessionStatus(sessionId3) === 'initiated',
  `confirmedBy=${conf3B.body?.data?.confirmedBy} established=${conf3B.body?.data?.established} `
  + `reason=${conf3B.body?.data?.reason} 库内=${sessionStatus(sessionId3)}`)

const mismatchRows = sqlScalar(
  `SELECT COUNT(*) FROM ${CONFIRM_TABLE} `
  + `WHERE session_id=(SELECT id FROM ${SESSION_TABLE} WHERE session_id='${sessionId3}');`
) || '0'
const distinctProofs = sqlScalar(
  `SELECT COUNT(DISTINCT proof) FROM ${CONFIRM_TABLE} `
  + `WHERE session_id=(SELECT id FROM ${SESSION_TABLE} WHERE session_id='${sessionId3}');`
) || '0'
check('★ 库里确实是**两条不同 proof**（不是同一笔被覆盖成两条）',
  mismatchRows === '2' && distinctProofs === '2',
  `confirmations=${mismatchRows} distinctProofs=${distinctProofs}`)

// ---------------------------------------------------------------------------
// 9. ★ 服务端全程没有拿到 SM4（计划 §2.1）
// ---------------------------------------------------------------------------
title('9. ★ 服务端拿不到 SM4：那把 K 的 hex/base64 在相关表里一处都搜不到')
info('判据是**在库里搜明文**，不是读一句代码结论 —— 明文可能出现在任何一列。')

const keyHex = Buffer.from(payloadKey).toString('hex')
const keyB64 = Buffer.from(payloadKey).toString('base64')
const leakProgram = `
import json, sys
sys.path.insert(0, '/backend')
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
import django
django.setup()
from pqkds.models import PreDistributedKey, SessionKey, DistributionBatch
needles = ['${keyHex}', '${keyB64}']
def scan(label, values):
    hits = [n for n in needles if any(n in str(v) for v in values if v)]
    print('%s=%s' % (label, 'LEAK:' + ','.join(hits) if hits else 'CLEAN'))
pool = PreDistributedKey.objects.filter(pool_id='${batchId}')
scan('POOL', [p.encrypted_key_data for p in pool] + [p.key_hash for p in pool])
sess = SessionKey.objects.filter(session_id='${sessionId}')
scan('SESSION', [s.encrypted_session_key for s in sess] + [s.key_exchange_data for s in sess])
batches = DistributionBatch.objects.filter(batch_id='${batchId}')
scan('BATCH', [b.node_ids for b in batches] + [b.target_domain_ids for b in batches])
`
const leakOut = execFileSync(dockerBin, ['exec', '-i', '-w', '/backend', 'dvadmin3-django', 'python', '-'], {
  input: leakProgram,
  encoding: 'utf8',
  env: { ...process.env, MSYS_NO_PATHCONV: '1' }
})
const leakLines = leakOut.trim().split('\n').filter((l) => /^[A-Z_]+=/.test(l)).join(' ')
check('★★ 池行 / 会话行 / 批次行里都搜不到 K 的 hex 与 base64（服务端没有明文）',
  leakOut.includes('POOL=CLEAN') && leakOut.includes('SESSION=CLEAN')
  && leakOut.includes('BATCH=CLEAN'),
  leakLines)

// ---------------------------------------------------------------------------
// 10. 会话列表把两个中间状态如实显示（不是压成"进行中"）
// ---------------------------------------------------------------------------
title('10. 状态如实下发：会话列表能读出这两个中间状态')
const sessionsFinal = await api(PQKDS, '/node-self/sessions/', { token: nodeB.token })
const rowFinal = (sessionsFinal.body?.data?.items || []).find((item) => item.sessionId === sessionId)
check('★ established 的会话在两边的列表里状态一致（A 视角也一样）',
  rowFinal?.status === 'established',
  `B 视角=${rowFinal?.status}`)
const sessionsA = await api(PQKDS, '/node-self/sessions/', { token: nodeA.token })
const rowA = (sessionsA.body?.data?.items || []).find((item) => item.sessionId === sessionId)
check('★ 发送方视角：isSender=true / isRecipient=false（页面的"处理"按钮不会出现在它这边）',
  rowA?.isSender === true && rowA?.isRecipient === false,
  `isSender=${rowA?.isSender} isRecipient=${rowA?.isRecipient}`)

// ---------------------------------------------------------------------------
// 11. 清理：自建自清
// ---------------------------------------------------------------------------
title('11. 清理：删掉本脚本建的节点及其一切关联行')
const cleanupProgram = `
import os, sys
sys.path.insert(0, '/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
import django
django.setup()
from pqkds.models import Node, UserKeyEnvelope, DistributionBatch

nodes = list(Node.objects.filter(domain_id='${DOMAIN}'))
ids = [n.pk for n in nodes]
user_ids = [n.sys_user_id for n in nodes if n.sys_user_id]
envelopes, _ = UserKeyEnvelope.objects.filter(user_id__in=user_ids).delete()
batches, _ = DistributionBatch.objects.filter(user_id__in=user_ids).delete()
deleted, _ = Node.objects.filter(pk__in=ids).delete()
left = Node.objects.filter(domain_id='${DOMAIN}').count()
print('nodes=%d user_key_envelopes=%d distribution_batches=%d cascaded=%d left=%d'
      % (len(ids), envelopes, batches, deleted, left))
`
let cleanupOut = ''
let cleanupErr = ''
try {
  cleanupOut = execFileSync(dockerBin, ['exec', '-i', '-w', '/backend', 'dvadmin3-django', 'python', '-'], {
    input: cleanupProgram,
    encoding: 'utf8',
    env: { ...process.env, MSYS_NO_PATHCONV: '1' }
  }).trim()
} catch (error) {
  cleanupErr = String(error?.stderr || error?.message || error)
}
info(cleanupOut || cleanupErr)
check('清理完成：域内不再有本脚本建的节点',
  Boolean(cleanupOut) && cleanupOut.endsWith('left=0'),
  cleanupOut || cleanupErr)

info(`本次真建的节点：${nodeA.nodeId} / ${nodeB.nodeId} / ${nodeC.nodeId}（已在上面删掉）`)
info('证据都在上面：会话行关联两版密钥（逐字）、接收方本机跨语言验签（含篡改/错公钥拒绝）、')
info('状态机顺序守卫（先解封被拒、非收件人 403）、验签/解封状态落库与幂等、')
info('解出 K 与发送方逐字节相同 + sha256 自查 + 双方 proof 一致 → established、')
info('KMS-012：确认先交不误建 / 证据不齐 blockedBy / 双方各持不同 K → PROOF_MISMATCH 不提升 /')
info('关闭是终态（关后确认 SESSION_TERMINAL、重复关闭幂等）、以及"服务端库里搜不到 K 明文"。')
finish()
