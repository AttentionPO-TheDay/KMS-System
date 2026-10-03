/**
 * KMS-008 验收：**新的分发请求契约**（节点到节点、按接收方指定版本封装）。
 *
 * 判据为什么是这几个动作，而不是"接口返回 200"
 * ------------------------------------------
 * 计划 §7 阶段 3 里本次负责的四条（本脚本验前三条与最后一条）：
 *   * 删除页面「我的解封密钥」与 `sourceKeyId` 的新流程依赖；
 *   * 分发改为"接收节点 + 保护算法 + 接收方 key_id/version + 有效期"；
 *   * 保护算法只允许 SM2 / SSCL / Kyber；
 *   * 旧用户腿接口保留迁移期，但标记 deprecated。
 *
 * 这四条都不能用"调用成功"证明，因为**失败形态恰恰是成功**：
 *
 *   * "请求里带了版本" ≠ "封装真的用了那一版"。旧实现读的是节点**物化列**
 *     （"当前生产公钥"），请求里就算有版本号也传不进封装调用 ——
 *     于是"选了 v1、实际用 v2 封的"，而每一处都成功。所以第 4/5 节的判据是
 *     **让接收方用那一版私钥去解**：解得开才算"真按这一版封的"，
 *     用另一版解**必须解不开**（半条不许少，否则"两把都能解"也会绿）。
 *   * "不再要求 source_key_id" ≠ "新接口在服务端真的没用它"。所以第 6 节
 *     连"传了也不作数"一起验：库里那一列必须是 NULL，且批次/池行都如此。
 *   * "标记 deprecated" 是一个**头部**事实，不是 body 里的字段。所以第 8 节
 *     断言响应头 `Deprecation: true`，并确认旧接口本身仍然可用（迁移期）。
 *
 * 那条最容易做假的判据：接收方真的能解开
 * -------------------------------------
 * 第 5 节用**真密钥**走完整往返：发送方指定 B 的 `keyId@v1` → 服务端按那一版封 →
 * 从库/接口取出信封 → 用 B 本地密钥库里 **v1 那一版私钥** `unwrapEnvelope` →
 * 必须解出 16 字节载荷；再用 **v2 那一版私钥**解同一封信封 → 必须失败。
 * 这两条合起来才排除了"物化列碰巧也是 v1"与"任何私钥都能解"两种假绿。
 *
 * ⚠️ 会**建真节点、写真数据**，只在本地验证环境跑。第 9 节自建自清。
 * ⚠️ 服务端代码是**打进镜像**的：改了后端不重建容器，本脚本的部署探针
 *    （第 1 节）会先失败——那是刻意的，免得一次部署问题伪装成十几个逻辑缺陷。
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

const KYBER = 'KYBER'
const SM2 = 'SM2'
const SSCL = 'SSCL'
const VARIANT = 768
/** 本脚本建的节点都打这个域标记，清理时按它捞。 */
const DOMAIN = 'kms008'

const NODE_TABLE = 'falcon_kds.dvadmin_pqkds_nodes'
const POOL_TABLE = 'falcon_kds.dvadmin_pqkds_pre_distributed_keys'
const BATCH_TABLE = 'falcon_kds.dvadmin_pqkds_distribution_batches'
const SESSION_TABLE = 'falcon_kds.dvadmin_pqkds_session_keys'

const ownerId = (nodeId) =>
  `(SELECT id FROM ${NODE_TABLE} WHERE node_id='${nodeId}')`

/**
 * 该批次的信封有效期（**分钟**）。
 *
 * ⚠️ 用分钟而不是小时：`TIMESTAMPDIFF(HOUR, …)` 是**向下取整**的，
 *    一个 2 小时差几十微秒的有效期会读成 `1` —— 断言会以"写死了 1 小时"
 *    的样子失败，而真相只是取整方向。分钟同样取整，但 119/120 的窗口
 *    足以把"2 小时"与"24 小时"分开。
 *
 * ⚠️ 断言时用 `nearMinutes` 而不是 `=== 120`：`expires_at` 在**建行之前**
 *    算好（`now + timedelta`），而 `create_datetime` 是建行那一刻的 `auto_now_add` ——
 *    两者差着一次 INSERT 的时间（微秒级）。取整之后就是 119 而不是 120，
 *    拿精确值去比会以"有效期没进库"的样子失败，而它其实进得好好的。
 */
const expiresMinutes = (batchId) => Number(sqlScalar(
  `SELECT TIMESTAMPDIFF(MINUTE, create_datetime, expires_at) FROM ${POOL_TABLE} `
  + `WHERE pool_id='${batchId}' LIMIT 1;`) || 0)

/** `expiresMinutes` 的容差判据：±2 分钟，够吞掉取整与建行耗时，远小于要区分的档位差。 */
const nearMinutes = (actual, expected) => Math.abs(actual - expected) <= 2

/** 一次分发的批次行：来源密钥 | 封装算法 | 成功数 | 状态 | 用户腿列。 */
const batchFact = (batchId) => sqlScalar(
  `SELECT CONCAT_WS('|', IFNULL(source_key_id, 'NULL'), wrapping_algorithm, `
  + `node_success_count, status, IF(user_envelope_ok, 'USER_YES', 'USER_NO')) `
  + `FROM ${BATCH_TABLE} WHERE batch_id='${batchId}';`
) || ''

/** 该批次下发给接收方的池项：长期密钥引用 | 状态 | 来源密钥列。 */
const poolFact = (batchId) => sqlScalar(
  `SELECT CONCAT_WS('|', IFNULL(long_term_key_id, 'NULL'), `
  + `IFNULL(long_term_key_version, 'NULL'), status, IFNULL(source_key_id, 'NULL')) `
  + `FROM ${POOL_TABLE} WHERE pool_id='${batchId}';`
) || ''

/** 信封本体（JSON 文本）—— 用它交给节点的解封实现。 */
const envelopeOf = (batchId) => sqlScalar(
  `SELECT encrypted_key_data FROM ${POOL_TABLE} WHERE pool_id='${batchId}' LIMIT 1;`
) || ''

const sessionFact = (batchId) => sqlScalar(
  `SELECT CONCAT_WS('|', session_type, status) FROM ${SESSION_TABLE} `
  + `WHERE session_id LIKE '${batchId}-%' ORDER BY id DESC LIMIT 1;`
) || ''

// ---------------------------------------------------------------------------
// 1. ★ 部署探针：先证明**跑着的服务端**有这两条新路由
// ---------------------------------------------------------------------------
title('1. ★ 部署探针：新分发的两条路由到底在不在跑着的进程里')

// 探法用**无令牌**请求：新端点没注册时拿到 404/405，注册了则是 401
// （`require_kms_user` 先于路由处理逻辑拦下）。401 ∉ {404, 405}。
const probePeers = await api(PQKDS, '/node-self/peers/probe-not-a-real-node/keys/')
const probeDist = await api(PQKDS, '/node-self/distributions/', {
  method: 'POST', body: {}
})
const peersOk = probePeers.status !== 404 && probePeers.status !== 405
const distOk = probeDist.status !== 404 && probeDist.status !== 405
check('★ GET /node-self/peers/<id>/keys/ 已部署（不是 404/405）', peersOk,
  `HTTP=${probePeers.status} body=${JSON.stringify(probePeers.body).slice(0, 120)}`)
check('★ POST /node-self/distributions/ 已部署（不是 404/405）', distOk,
  `HTTP=${probeDist.status} body=${JSON.stringify(probeDist.body).slice(0, 120)}`)
if (!peersOk || !distOk) {
  info('路由没注册：后面的用例一条都不跑 —— 否则每条断言都会以"没读到字段"')
  info('的方式失败，看起来像十几个逻辑缺陷，实际只是一次部署问题。')
  info('先重建后端镜像（代码是打进镜像的，docker cp 之后进程不重启就 import 不到），再重跑。')
  finish()
  process.exit(1)
}

// ---------------------------------------------------------------------------
// 2. 准备：两个真节点，四套密钥登记齐
// ---------------------------------------------------------------------------
title('2. 准备：发送方 A / 接收方 B（四套密钥登记齐）')
const adminToken = await adminLogin()
const nodeA = await newNodeSession(adminToken, { prefix: 'K8A', name: 'KMS-008 发送方', domainId: DOMAIN })
const nodeB = await newNodeSession(adminToken, { prefix: 'K8B', name: 'KMS-008 接收方', domainId: DOMAIN })
const nodeC = await newNodeSession(adminToken, { prefix: 'K8C', name: 'KMS-008 未授权节点', domainId: DOMAIN })
check('三个节点都已激活（各自持有登录令牌）',
  Boolean(nodeA.token && nodeB.token && nodeC.token),
  `A=${nodeA.nodeId} B=${nodeB.nodeId} C=${nodeC.nodeId}`)

const userA = sqlScalar(`SELECT IFNULL(sys_user_id, '') FROM ${NODE_TABLE} WHERE node_id='${nodeA.nodeId}';`) || ''
const nodeBId = sqlScalar(`SELECT id FROM ${NODE_TABLE} WHERE node_id='${nodeB.nodeId}';`) || ''
const nodeCId = sqlScalar(`SELECT id FROM ${NODE_TABLE} WHERE node_id='${nodeC.nodeId}';`) || ''
check('三个节点在库里有主键、且 A 映射到了用户（分发身份靠它）',
  Boolean(userA && nodeBId && nodeCId), `A.user=${userA} B.pk=${nodeBId} C.pk=${nodeCId}`)

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

info('生成四套密钥并登记（FALCON 本机生成要十几秒，三遍）…')
const keys = {}
for (const [label, session] of [['A', nodeA], ['B', nodeB], ['C', nodeC]]) {
  keys[label] = {}
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
check('三个节点各自四套密钥都已登记且为 ACTIVE',
  [nodeA, nodeB, nodeC].every((s) => {
    const label = s === nodeA ? 'A' : (s === nodeB ? 'B' : 'C')
    return [KYBER, SM2, SSCL, 'FALCON'].every((alg) =>
      sqlScalar(
        `SELECT CONCAT_WS('|', key_version, status) FROM falcon_kds.dvadmin_pqkds_node_long_term_keys `
        + `WHERE node_id=${ownerId(s.nodeId)} AND algorithm='${alg}' `
        + `AND key_id='${keys[label][alg].keyId}' AND key_version=1;`
      ) === '1|ACTIVE')
  }),
  `${nodeA.nodeId} / ${nodeB.nodeId} / ${nodeC.nodeId}`)

for (const session of [nodeA, nodeB, nodeC]) {
  const init = await api(PQKDS, '/node-self/init/', { method: 'POST', token: session.token })
  if (!isOk(init.body)) {
    check(`${session.nodeId} 初始化收尾成功`, false, `code=${init.body?.code} msg=${init.body?.msg}`)
  }
}

// 授权：A 的用户 → B 的节点。**故意不给 C**：第 3.2 节要用它验未授权拒绝。
const grant = await api(PQKDS, '/admin/node-authorizations/', {
  method: 'POST',
  token: adminToken,
  body: { userId: Number(userA), nodeId: Number(nodeBId), remark: 'KMS-008 验收：A 需要能向 B 分发' }
})
check('节点鉴权已授予（A 的用户 → B 的节点，**不含 C**）', isOk(grant.body),
  `code=${grant.body?.code} msg=${grant.body?.msg}`)

// ---------------------------------------------------------------------------
// 3. ★ §16.1：peers keys —— 能查对端、且只能查有授权的
// ---------------------------------------------------------------------------
title('3. ★ GET /node-self/peers/<id>/keys/：对端密钥列表')
const peerB = await api(PQKDS, `/node-self/peers/${nodeB.nodeId}/keys/?algorithm=SM2,SSCL,KYBER`, {
  token: nodeA.token
})
const peerBKeys = peerB.body?.data?.keys || []
check('★ A 能读到 B 的密钥列表（HTTP 200 + code 200）',
  peerB.status === 200 && isOk(peerB.body), `HTTP=${peerB.status} code=${peerB.body?.code}`)
check('响应带节点归属（主键 + 业务编号 + 名字）',
  peerB.body?.data?.nodeCode === nodeB.nodeId && Number(peerB.body?.data?.nodeId) === Number(nodeBId),
  `nodeId=${peerB.body?.data?.nodeId} nodeCode=${peerB.body?.data?.nodeCode}`)

const expectKey = keys.B[KYBER]
const foundKey = peerBKeys.find(
  (k) => k.algorithm === KYBER && k.keyId === expectKey.keyId && Number(k.keyVersion) === 1)
check('★ 列表里有 B 登记的那把 KYBER（算法/keyId/版本逐字段对得上）',
  Boolean(foundKey),
  foundKey ? JSON.stringify(foundKey).slice(0, 200) : `列表=${JSON.stringify(peerBKeys.map((k) => [k.algorithm, k.keyId, k.keyVersion]))}`)
check('那一行带"能不能用于新工作"的判据（allowsNewWork，前端据此置灰而不自己判）',
  foundKey?.allowsNewWork === true && foundKey?.status === 'ACTIVE',
  `status=${foundKey?.status} allowsNewWork=${foundKey?.allowsNewWork} statusLabel=${foundKey?.statusLabel}`)

check('只回了被请求的三种保护算法（FALCON 不在列表里）',
  peerBKeys.length > 0 && peerBKeys.every((k) => [SM2, SSCL, KYBER].includes(k.algorithm)),
  `算法集合=${JSON.stringify([...new Set(peerBKeys.map((k) => k.algorithm))])}`)

// ⚠️ 只回公开量：这一条不是"读不到私钥"（那本来就没写在响应里），
//    而是**任何一行的字段集合里都不该出现私钥字段**。
check('列表里没有任何私钥字段（publicKey 是公开量，可以回；privateKey 类字段一个都不许有）',
  peerBKeys.every((k) => !['privateKey', 'secretKey', 'private_key', 'secret_key']
    .some((f) => f in k)),
  `字段集合=${JSON.stringify([...new Set(peerBKeys.flatMap((k) => Object.keys(k)))])}`)

// 3.2 未授权：A 查 C（A 的用户对 C 没有授权行）
const peerC = await api(PQKDS, `/node-self/peers/${nodeC.nodeId}/keys/`, { token: nodeA.token })
check('★ 未授权的对端 → 403 + NOT_AUTHORIZED（否则任一节点可枚举全部节点的密钥版本）',
  peerC.status === 200 && peerC.body?.code === 403
  && peerC.body?.data?.error_code === 'NOT_AUTHORIZED',
  `HTTP=${peerC.status} code=${peerC.body?.code} error_code=${peerC.body?.data?.error_code} msg=${peerC.body?.msg}`)

// 3.3 不存在的节点：明确的 404，而不是"空列表"
const peerMissing = await api(PQKDS, '/node-self/peers/no-such-node-xyz/keys/', { token: nodeA.token })
check('不存在的对端 → 明确的 KEY_NOT_FOUND（不是"列表为空"那种要靠猜的回答）',
  peerMissing.body?.code === 404 && peerMissing.body?.data?.error_code === 'KEY_NOT_FOUND',
  `code=${peerMissing.body?.code} error_code=${peerMissing.body?.data?.error_code}`)

// ---------------------------------------------------------------------------
// 4. ★ §16.2：POST /node-self/distributions/ —— 按指定的那一版封装
// ---------------------------------------------------------------------------
title('4. ★ 新契约的核心：按接收方**指定的那一版**封装')

const distribute = (session, body) =>
  api(PQKDS, '/node-self/distributions/', { method: 'POST', token: session.token, body })

const distB = await distribute(nodeA, {
  receiverNodeId: nodeB.nodeId,
  protectionAlgorithm: KYBER,
  recipientKeyId: expectKey.keyId,
  recipientKeyVersion: 1,
  expiresInHours: 2
})
check('★ 分发成功（HTTP 200 + code 200 + status=success）',
  distB.status === 200 && isOk(distB.body) && distB.body?.data?.status === 'success',
  `HTTP=${distB.status} code=${distB.body?.code} msg=${distB.body?.msg}`)
const batchB = distB.body?.data?.batchId || ''
check('回显**实际用的**那一版（这是"请求里的版本真进了封装"的第一层证据）',
  distB.body?.data?.recipientKeyId === expectKey.keyId
  && Number(distB.body?.data?.recipientKeyVersion) === 1,
  `recipientKeyId=${distB.body?.data?.recipientKeyId} v=${distB.body?.data?.recipientKeyVersion}`)

check('★ 库内那一行记的长期密钥引用 = 请求指定的那一版（逐字）',
  poolFact(batchB) === `${expectKey.keyId}|1|distributed|NULL`,
  `读到 ${poolFact(batchB)}，期望 ${expectKey.keyId}|1|distributed|NULL`)

check('★ 批次行：来源密钥为 NULL（新契约没有用户腿）、成功数 1、用户腿列 False',
  batchFact(batchB) === `NULL|kyber_kem|1|success|USER_NO`,
  `读到 ${batchFact(batchB)}`)
check('有效期进了库（2 小时，不是写死的 24）',
  nearMinutes(expiresMinutes(batchB), 120),
  `库内有效期差=${expiresMinutes(batchB)} 分钟（期望 120）`)
check('★ 会话已建立，且**按实际保护算法**记（kyber_kem，不再一律 kyber_kem 的时代结束了）',
  sessionFact(batchB) === 'kyber_kem|initiated',
  `读到 ${sessionFact(batchB)}`)

// ---------------------------------------------------------------------------
// 5. ★★ 最要紧的一条：接收方用**那一版**私钥解得开、用别的版本解不开
// ---------------------------------------------------------------------------
title('5. ★★ 接收方真能解开：用指定的那一版解得开，用另一版解不开')

const envelopeB = JSON.parse(envelopeOf(batchB) || '{}')
check('信封本体在库里、且是 kyber_kem 形状（kem_ciphertext / encrypted_key / nonce / tag）',
  Boolean(envelopeB.kem_ciphertext && envelopeB.encrypted_key && envelopeB.nonce && envelopeB.tag)
  && envelopeB.wrapping_algorithm === 'kyber_kem',
  `字段=${JSON.stringify(Object.keys(envelopeB))}`)

const refBv1 = keys.B[KYBER].keyRef
let recovered = null
let recoverErr = ''
try {
  recovered = await cryptoProvider.unwrapEnvelope(KYBER, refBv1, envelopeB)
} catch (error) {
  recoverErr = String(error?.message || error)
}
check('★★ B 用**指定的那一版（v1）**私钥解得开信封，且解出 16 字节载荷（SM4）',
  recovered instanceof Uint8Array && recovered.length === 16,
  recovered ? `长度=${recovered.length} 字节` : `解封失败：${recoverErr}`)

// ⚠️ 半条不许少：还要证明**别的版本解不开**。只验"v1 能解"的话，
//    "服务端用了物化列（恰好也是 v1）"与"任何私钥都能解"两种假绿都拦不住。
//    做法：给 B 的同一 keyId 升一版（v2，私钥不同），用 v2 的 keyRef 解同一封信封。
const K2v2 = await cryptoProvider.generate(KYBER, {
  nodeId: nodeB.nodeId, keyId: keys.B[KYBER].keyId, version: 2, variant: VARIANT
})
const upV2 = await register(nodeB, KYBER, K2v2, { securityLevel: String(VARIANT), rotate: true })
check('B 把同一 keyId 更新到 v2 成功（这一版只是**另一把私钥**，用来做反证）',
  isOk(upV2.body) && String(upV2.body?.msg || '').includes('已更新'),
  `code=${upV2.body?.code} msg=${upV2.body?.msg}`)

let wrongOpened = false
let wrongErr = ''
try {
  const wrong = await cryptoProvider.unwrapEnvelope(KYBER, K2v2.keyRef, envelopeB)
  wrongOpened = Boolean(wrong)
} catch (error) {
  wrongErr = String(error?.message || error)
}
check('★★ 用 v2 的私钥解**同一封**信封必须失败（否则"按指定版本封装"这句话是空的）',
  wrongOpened === false,
  wrongOpened ? '竟然解开了 —— 两把私钥都能解，说明封装没用指定的那一版' : `如期望地失败：${wrongErr.slice(0, 80)}`)

// 4.2 换一版再分发：库内的引用要跟着变（证明"指定哪版就封哪版"不是碰巧）
const distBv2 = await distribute(nodeA, {
  receiverNodeId: nodeB.nodeId,
  protectionAlgorithm: KYBER,
  recipientKeyId: K2v2.keyId,
  recipientKeyVersion: 2
})
const batchBv2 = distBv2.body?.data?.batchId || ''
check('★ 指定 v2 再分发一次 → 库内引用变成 v2（引用随请求走，不是"永远记 v1"）',
  isOk(distBv2.body) && poolFact(batchBv2) === `${K2v2.keyId}|2|distributed|NULL`,
  `读到 ${poolFact(batchBv2)}，期望 ${K2v2.keyId}|2|distributed|NULL`)
const envBv2 = JSON.parse(envelopeOf(batchBv2) || '{}')
let v2Opened = null
try {
  v2Opened = await cryptoProvider.unwrapEnvelope(KYBER, K2v2.keyRef, envBv2)
} catch (error) { /* 下面按 null 断言 */ }
check('★★ 这一封用 v2 私钥解得开（同一个判据在两个版本上各成立一次）',
  v2Opened instanceof Uint8Array && v2Opened.length === 16,
  v2Opened ? `长度=${v2Opened.length} 字节` : '解封失败')

// 4.3 默认有效期：不传时是 24 小时
const distDef = await distribute(nodeA, {
  receiverNodeId: nodeB.nodeId,
  protectionAlgorithm: KYBER,
  recipientKeyId: K2v2.keyId,
  recipientKeyVersion: 2
})
const batchDef = distDef.body?.data?.batchId || ''
check('不传 expiresInHours 时用默认 24 小时',
  isOk(distDef.body) && nearMinutes(expiresMinutes(batchDef), 24 * 60),
  `库内有效期差=${expiresMinutes(batchDef)} 分钟（期望 ${24 * 60}）`)

// ---------------------------------------------------------------------------
// 6. ★ 三种保护算法都能产生信封（阶段 3 出口检查的前半句）+ 版本引用都进库
// ---------------------------------------------------------------------------
title('6. ★ 三种保护算法各产一封有效信封，且都按指定版本封装')
for (const algorithm of [SM2, SSCL]) {
  const material = keys.B[algorithm]
  const res = await distribute(nodeA, {
    receiverNodeId: nodeB.nodeId,
    protectionAlgorithm: algorithm,
    recipientKeyId: material.keyId,
    recipientKeyVersion: 1
  })
  const batchId = res.body?.data?.batchId || ''
  const expectedWrapping = algorithm === SM2 ? 'gm_sm2' : 'gm_sscl'
  check(`★ ${algorithm}：分发成功且库内引用 = 指定的那一版`,
    isOk(res.body) && poolFact(batchId) === `${material.keyId}|1|distributed|NULL`,
    `code=${res.body?.code} 读到 ${poolFact(batchId)}`)

  const env = JSON.parse(envelopeOf(batchId) || '{}')
  check(`${algorithm}：信封是国密形状（algorithm='sm2' + ciphertext + wrapping_algorithm=${expectedWrapping}）`,
    env.algorithm === 'sm2' && Boolean(env.ciphertext) && env.wrapping_algorithm === expectedWrapping,
    `字段=${JSON.stringify(Object.keys(env))} wrapping=${env.wrapping_algorithm}`)

  let opened = null
  let openedErr = ''
  try {
    opened = await cryptoProvider.unwrapEnvelope(algorithm, material.keyRef, env)
  } catch (error) {
    openedErr = String(error?.message || error)
  }
  check(`★ ${algorithm}：接收方用**指定的那一版私钥**解得开（真往返，不是看字段）`,
    opened instanceof Uint8Array && opened.length === 16,
    opened ? `长度=${opened.length} 字节` : `解封失败：${openedErr.slice(0, 100)}`)

  check(`${algorithm}：会话类型按实际算法记（${expectedWrapping}），不是一律 kyber_kem`,
    sessionFact(batchId) === `${expectedWrapping}|initiated`,
    `读到 ${sessionFact(batchId)}`)
}

// ---------------------------------------------------------------------------
// 7. ★ 拒绝面：每一条都要**指名**，不能写成 !isOk
// ---------------------------------------------------------------------------
title('7. ★ 拒绝面：算法、版本、授权、参数')

const errCodeOf = (body) => body?.data?.error_code || '(无 error_code)'

// 7.1 FALCON 当保护算法 —— 它是签名算法，不提供机密性（计划 §3）
const falconAsProtection = await distribute(nodeA, {
  receiverNodeId: nodeB.nodeId,
  protectionAlgorithm: 'FALCON',
  recipientKeyId: keys.B.FALCON.keyId,
  recipientKeyVersion: 1
})
check('★ FALCON 当保护算法 → ALGORITHM_NOT_ALLOWED（它只做签名，包不了 SM4）',
  falconAsProtection.body?.code === 400
  && falconAsProtection.body?.data?.error_code === 'ALGORITHM_NOT_ALLOWED',
  `code=${falconAsProtection.body?.code} ${errCodeOf(falconAsProtection.body)} msg=${falconAsProtection.body?.msg}`)

const legacyAsProtection = await distribute(nodeA, {
  receiverNodeId: nodeB.nodeId,
  protectionAlgorithm: 'falcon_lattice',
  recipientKeyId: keys.B.FALCON.keyId,
  recipientKeyVersion: 1
})
check('★ 历史拼写 falcon_lattice 同样被拒（新代码不认它作保护算法）',
  legacyAsProtection.body?.data?.error_code === 'ALGORITHM_NOT_ALLOWED',
  `${errCodeOf(legacyAsProtection.body)}`)

// 7.2 不存在的版本 / keyId
const missingVersion = await distribute(nodeA, {
  receiverNodeId: nodeB.nodeId,
  protectionAlgorithm: KYBER,
  recipientKeyId: K2v2.keyId,
  recipientKeyVersion: 99
})
check('★ 不存在的版本 → KEY_NOT_FOUND（**不回退**到"最新那一版"）',
  missingVersion.body?.data?.error_code === 'KEY_NOT_FOUND',
  `${errCodeOf(missingVersion.body)} msg=${missingVersion.body?.msg}`)

const badKeyId = await distribute(nodeA, {
  receiverNodeId: nodeB.nodeId,
  protectionAlgorithm: KYBER,
  recipientKeyId: 'no-such-key-id',
  recipientKeyVersion: 1
})
check('★ 不存在的 keyId → KEY_NOT_FOUND',
  badKeyId.body?.data?.error_code === 'KEY_NOT_FOUND',
  `${errCodeOf(badKeyId.body)}`)

// 7.3 被取代的旧版本：KEY_VERSION_MISMATCH（判据②）
//     B 的 KYBER 现在在产的是 v2；v1 已 RETIRED。
const retiredVersion = await distribute(nodeA, {
  receiverNodeId: nodeB.nodeId,
  protectionAlgorithm: KYBER,
  recipientKeyId: K2v2.keyId,
  recipientKeyVersion: 1
})
check('★ 已被取代的旧版本（RETIRED）→ KEY_VERSION_MISMATCH —— 判据②「旧版本不能被误当成当前生产版本」',
  retiredVersion.body?.data?.error_code === 'KEY_VERSION_MISMATCH',
  `${errCodeOf(retiredVersion.body)} msg=${retiredVersion.body?.msg}`)

// 7.4 已回收的版本：KEY_REVOKED
const revokeB = await api(PQKDS, '/node-self/keys/revoke/', {
  method: 'POST', token: nodeB.token,
  body: { algorithm: SM2, keyId: keys.B[SM2].keyId, keyVersion: 1, reason: 'KMS-008 验收：造一把已回收的' }
})
check('B 回收自己的 SM2 v1（造拒绝面用的已回收版本）', isOk(revokeB.body),
  `code=${revokeB.body?.code} msg=${revokeB.body?.msg}`)
const revokedVersion = await distribute(nodeA, {
  receiverNodeId: nodeB.nodeId,
  protectionAlgorithm: SM2,
  recipientKeyId: keys.B[SM2].keyId,
  recipientKeyVersion: 1
})
check('★ 已回收的版本 → KEY_REVOKED（与"不存在"分开，重试永远不会成功）',
  revokedVersion.body?.data?.error_code === 'KEY_REVOKED',
  `${errCodeOf(revokedVersion.body)} msg=${revokedVersion.body?.msg}`)

// 7.5 未授权的接收节点：C（A 的用户对 C 没有授权行）
const toC = await distribute(nodeA, {
  receiverNodeId: nodeC.nodeId,
  protectionAlgorithm: KYBER,
  recipientKeyId: keys.C[KYBER].keyId,
  recipientKeyVersion: 1
})
check('★ 未授权的接收节点 → 403 + NOT_AUTHORIZED',
  toC.body?.code === 403 && toC.body?.data?.error_code === 'NOT_AUTHORIZED',
  `code=${toC.body?.code} ${errCodeOf(toC.body)} msg=${toC.body?.msg}`)

// 7.6 有效期越界
for (const bad of [0, -1, 999, 'abc', true]) {
  const res = await distribute(nodeA, {
    receiverNodeId: nodeB.nodeId,
    protectionAlgorithm: KYBER,
    recipientKeyId: K2v2.keyId,
    recipientKeyVersion: 2,
    expiresInHours: bad
  })
  check(`expiresInHours=${JSON.stringify(bad)} 被拒（1..168，不做 int() 兜底）`,
    res.body?.data?.error_code === 'INVALID_PARAMETER',
    `${errCodeOf(res.body)} msg=${res.body?.msg}`)
}

// 7.7 缺参数
const noReceiver = await distribute(nodeA, {
  protectionAlgorithm: KYBER, recipientKeyId: K2v2.keyId, recipientKeyVersion: 2
})
check('缺 receiverNodeId → 明确报错（不是"随便挑一个节点"）',
  !isOk(noReceiver.body) && /receiverNodeId/.test(String(noReceiver.body?.msg || '')),
  `code=${noReceiver.body?.code} msg=${noReceiver.body?.msg}`)

// 7.8 以上全部被拒之后，池表里没有多出对应的行
const poolRowsForBV2 = Number(sqlScalar(
  `SELECT COUNT(*) FROM ${POOL_TABLE} WHERE node1_id=${ownerId(nodeB.nodeId)} `
  + `AND long_term_key_id='${K2v2.keyId}' AND long_term_key_version=2;`) || 0)
check('被拒的请求一条池行都没留下（只数成功的那些）',
  poolRowsForBV2 === 2,
  `B 上引用 v2 的池行=${poolRowsForBV2}（期望 2：第 4.2 与 4.3 节各成功一条）`)

// ---------------------------------------------------------------------------
// 8. ★ 旧接口：仍然可用（迁移期）但已标记 deprecated
// ---------------------------------------------------------------------------
title('8. ★ 旧用户腿接口：保留可用 + 弃用标记')
const UA = '04573e32965ced2ca54c9f9a26be3c5115f83f61bc0d7ed72b90ffb9cce6b741235c0e249f323ad7703340983665e5147c6893490242af26fa642372a899a74c30'
const UPDATEDEL_API = 'http://127.0.0.1/updatedel-api'
const km = await api(UPDATEDEL_API, '/lifecycle/keymanage', {
  method: 'POST', token: adminToken,
  body: {
    userId: Number(userA), userName: nodeA.nodeId, encrytType: '无证书非对称加密',
    encrytName: 'SM2', keyName: `KMS-008 验收 ${Date.now()}`, keyUse: 'session',
    keyDomain: 'A', status: '0', ua: UA
  }
})
const sourceKeyId = km.body?.data?.key_id ?? km.body?.data?.keyId
check('用户腿源密钥已建立（旧接口的入参，只为本节的弃用验证服务）', Boolean(sourceKeyId),
  `key_id=${sourceKeyId}`)

const legacy = await api(PQKDS, '/key-pool/distribute-to-user/', {
  method: 'POST', token: nodeA.token,
  body: {
    source_key_id: Number(sourceKeyId), node_ids: [Number(nodeBId)],
    count: 1, node_wrapping_algorithm: 'kyber_kem'
  }
})
check('★ 旧接口**仍然可用**（迁移期承诺：不静默停用）',
  isOk(legacy.body), `code=${legacy.body?.code} msg=${legacy.body?.msg}`)
check('★ 旧接口带 `Deprecation: true` 响应头（"还有谁在用它"必须可查）',
  String(legacy.headers?.deprecation || '') === 'true',
  `deprecation=${JSON.stringify(legacy.headers?.deprecation)} 头集合=${JSON.stringify(Object.keys(legacy.headers || {}))}`)
info('⚠️ 新接口**没有**这个头 —— 第 9 节的对照断言会确认这一点，')
info('   否则"所有接口都带 Deprecation"也会让上面那条绿。')

// ---------------------------------------------------------------------------
// 9. ★ 对照：新接口不带弃用头 + 传了 source_key_id 也不作数
// ---------------------------------------------------------------------------
title('9. ★ 对照与收尾')
const fresh = await distribute(nodeA, {
  receiverNodeId: nodeB.nodeId,
  protectionAlgorithm: KYBER,
  recipientKeyId: K2v2.keyId,
  recipientKeyVersion: 2
})
check('★ 新接口**没有** Deprecation 头（与第 8 节配成一对）',
  isOk(fresh.body) && String(fresh.headers?.deprecation || '') !== 'true',
  `deprecation=${JSON.stringify(fresh.headers?.deprecation)}`)
const freshBatch = fresh.body?.data?.batchId || ''

// 新契约里 source_key_id 即使被传了也不作数（库内必须是 NULL）。
const withSource = await distribute(nodeA, {
  receiverNodeId: nodeB.nodeId,
  protectionAlgorithm: KYBER,
  recipientKeyId: K2v2.keyId,
  recipientKeyVersion: 2,
  source_key_id: Number(sourceKeyId)
})
const withSourceBatch = withSource.body?.data?.batchId || ''
check('★ 传了 source_key_id 也不作数：批次行与池行的来源密钥列都是 NULL',
  isOk(withSource.body)
  && batchFact(withSourceBatch).startsWith('NULL|')
  && poolFact(withSourceBatch).endsWith('|NULL'),
  `批次=${batchFact(withSourceBatch)} 池=${poolFact(withSourceBatch)}`)

// ---------------------------------------------------------------------------
// 10. 清理：脚本自建自清
// ---------------------------------------------------------------------------
title('10. 清理：删掉本脚本建的节点及其一切关联行')
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
info('证据都在上面：对端密钥列表与归属校验（含未授权 403）、按指定版本封装并在库内逐字核对、')
info('接收方用那一版私钥真解封（含"另一版解不开"的反证）、三种保护算法各一次完整往返、')
info('五种拒绝各自的错误码、新契约对 source_key_id 不作数、新旧接口的弃用头对照。')
finish()