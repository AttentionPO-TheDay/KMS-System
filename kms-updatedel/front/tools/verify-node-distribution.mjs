/**
 * KMS-008/009 验收：**新的分发请求契约**（节点到节点，由节点本机封装并签名）。
 *
 * 判据为什么是这几个动作，而不是"接口返回 200"
 * ------------------------------------------
 * 计划 §7 阶段 3 里本次负责的四条（本脚本验前三条与最后一条）：
 *   * 删除页面「我的解封密钥」与 `sourceKeyId` 的新流程依赖；
 *   * 分发改为"接收节点 + 保护算法 + 接收方 key_id/version + 有效期"；
 *   * 保护算法只允许 SM2 / SSCL / Kyber；
 *   * 旧用户腿接口保留迁移期，但标记 deprecated。
 * KMS-009 再加一条：**SM4 与封装在节点本机完成，服务端只登记**（计划 §2.1）。
 *
 * 这四条都不能用"调用成功"证明，因为**失败形态恰恰是成功**：
 *
 *   * "请求里带了版本" ≠ "封装真的用了那一版"。旧实现读的是节点**物化列**
 *     （"当前生产公钥"），请求里就算有版本号也传不进封装调用 ——
 *     于是"选了 v1、实际用 v2 封的"，而每一处都成功。所以第 4/5 节的判据是
 *     **让接收方用那一版私钥去解**：解得开才算"真按这一版封的"，
 *     用另一版解**必须解不开**（半条不许少，否则"两把都能解"也会绿）。
 *   * "信封由节点产出" ≠ "服务端没有另生成一份"。所以第 4.5 节比对
 *     **库内那串密文与节点本机产出的那一串逐字相同** —— 服务端若还自己封，
 *     这两串必然不同。同一个判据对 KYBER 与国密两条腿各验一次。
 *   * "信封带着签名" ≠ "签名是真的、且绑住了这些字段"。所以第 4.5 节
 *     用**服务端那份规范实现**验签（跨语言比对序列化口径），再把一个被签字段
 *     改掉、要求**验不过** —— 否则"验签函数恒返回 True"也会让前者绿。
 *   * "不再要求 source_key_id" ≠ "新接口在服务端真的没用它"。所以第 9 节
 *     连"传了也不作数"一起验：库里那一列必须是 NULL，且批次/池行都如此。
 *   * "标记 deprecated" 是一个**头部**事实，不是 body 里的字段。所以第 8 节
 *     断言响应头 `Deprecation: true`，并确认旧接口本身仍然可用（迁移期）。
 *
 * 那条最容易做假的判据：接收方真的能解开
 * -------------------------------------
 * 第 5 节用**真密钥**走完整往返：发送方指定 B 的 `keyId@v1` → **在本机**用
 * 那一版公钥封装并签名 → 交给服务端登记 → 从库/接口取出信封 →
 * 用 B 本地密钥库里 **v1 那一版私钥** `unwrapEnvelope` → 必须解出 16 字节载荷；
 * 再用 **v2 那一版私钥**解同一封信封 → 必须失败。
 * 这两条合起来才排除了"物化列碰巧也是 v1"与"任何私钥都能解"两种假绿。
 *
 * ⚠️ 会**建真节点、写真数据**，只在本地验证环境跑。结尾自建自清。
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
title('4. ★ 新契约的核心：按接收方**指定的那一版**封装（KMS-009：本机封装 + 本机签名）')

const distribute = (session, body) =>
  api(PQKDS, '/node-self/distributions/', { method: 'POST', token: session.token, body })

/**
 * 造一份**节点产出的**分发请求体（KMS-009 之后，这一整套都在本机完成）：
 * 生成 SM4 → 用接收方那一版公钥封装 → 用本机 Falcon 私钥签名。
 *
 * ⚠️ 动态 import：`lib/node-session.mjs` 明确要求对 `src/` 模块一律动态引入 ——
 *    静态 import 会被提升到 `fake-indexeddb/auto` **之前**，
 *    而 provider 的密钥库依赖那个 polyfill（见该文件头部说明）。
 */
async function buildSignedBody({
  receiverNodeId, protectionAlgorithm, recipientKeyId, recipientKeyVersion,
  recipientPublicKeyHex, expiresInHours = 2
}) {
  const {
    buildNodeEnvelope, generatePayloadKey, newBatchId, signNodeEnvelope
  } = await import('../src/utils/crypto/envelope-signing.js')

  const payloadKey = generatePayloadKey()
  const batchId = newBatchId()
  const expiresAt = new Date(Date.now() + expiresInHours * 3600 * 1000).toISOString()
  const built = await buildNodeEnvelope({
    provider: cryptoProvider,
    payloadKey,
    wrapping: protectionAlgorithm,
    recipientPublicKeyHex,
    batchId,
    senderNodeId: nodeA.nodeId,
    receiverNodeId,
    recipientKeyId,
    recipientKeyVersion,
    expiresAt
  })
  const signature = await signNodeEnvelope(cryptoProvider, keys.A.FALCON.keyRef, built.envelope)
  return {
    batchId,
    built,
    payloadKey,
    body: {
      receiverNodeId,
      protectionAlgorithm,
      recipientKeyId,
      recipientKeyVersion,
      batchId,
      expiresAt,
      envelope: built.envelope,
      signature,
      keyHash: built.keyHash
    }
  }
}

const reqB = await buildSignedBody({
  receiverNodeId: nodeB.nodeId,
  protectionAlgorithm: KYBER,
  recipientKeyId: expectKey.keyId,
  recipientKeyVersion: 1,
  recipientPublicKeyHex: expectKey.publicKey,
  expiresInHours: 2
})
const distB = await distribute(nodeA, reqB.body)
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
// 4.5 ★★ KMS-009：库里的信封**就是节点本机产出的那一份**，且签名是真的
// ---------------------------------------------------------------------------
title('4.5 ★★ KMS-009：信封由本机产出并签名（服务端只登记，不再生成 SM4）')

// 判据一：**逐字节**相同。服务端若还在自己生成 SM4/封装（KMS-008 的过渡实现），
// 库里那串必然与节点交上来的不同 —— 这一条就是"服务端不再代封"的证伪点。
const storedJson = envelopeOf(batchB)
const storedObj = JSON.parse(storedJson || '{}')
check('★★ 库内信封与节点交上来的**逐字节等价**（服务端没有另生成一份）',
  storedObj.kem_ciphertext === reqB.built.envelope.kem_ciphertext
  && storedObj.encrypted_key === reqB.built.envelope.encrypted_key
  && storedObj.nonce === reqB.built.envelope.nonce
  && storedObj.tag === reqB.built.envelope.tag,
  `库内 kem=${String(storedObj.kem_ciphertext).slice(0, 24)}… 本机 kem=${String(reqB.built.envelope.kem_ciphertext).slice(0, 24)}…`)
check('★ 库内信封带着发送节点写进去的待签字段（批次号/收发节点/接收方 keyId 与版本/密钥哈希/摘要/有效期）',
  storedObj.batch_id === reqB.body.batchId
  && storedObj.sender_node_id === nodeA.nodeId
  && storedObj.receiver_node_id === nodeB.nodeId
  && storedObj.recipient_key_id === expectKey.keyId
  && Number(storedObj.recipient_key_version) === 1
  && storedObj.key_hash === reqB.built.keyHash
  && storedObj.ciphertext_digest === reqB.built.digest
  && storedObj.expires_at === reqB.body.expiresAt,
  `batch_id=${storedObj.batch_id} sender=${storedObj.sender_node_id} key_hash=${String(storedObj.key_hash).slice(0, 16)}…`)
check('★ 库内信封带着签名（签名字段随信封一起落库，KMS-010 才有东西可验）',
  typeof storedObj.signature === 'string' && storedObj.signature.length > 100,
  `signature 长度=${String(storedObj.signature || '').length}`)

// 判据二：签名**验得过**，且用的是**服务端那一份规范实现**重建的字节串。
// ⚠️ 这是本脚本唯一的**跨语言**断言：浏览器的规范化序列化（键排序 + 无空白）
//    必须与服务端 `node_canonical_payload` 逐字节一致。不一致的表现是
//    "节点签的信服务端验不过" —— 那看起来完全像伪造，必须在这里钉死。
const verifyProgram = `
import json, sys
sys.path.insert(0, '/backend')
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
import django
django.setup()
from pqkds.models import Node, NodeLongTermKey
from pqkds.envelope_signature import verify_node_envelope, node_canonical_payload

stored = json.loads(r'''${storedJson}''')
sender = Node.objects.filter(node_id='${nodeA.nodeId}').first()
key = NodeLongTermKey.objects.filter(
    node=sender, algorithm='FALCON', key_id='${keys.A.FALCON.keyId}', key_version=1).first()
print('SENDER_PK_LEN=%d' % len(key.public_key or ''))
# 服务端重建的规范字节串（与浏览器那份比对）
print('CANON_SHA=%s' % __import__('hashlib').sha256(node_canonical_payload(stored)).hexdigest())
print('VERIFY=%s' % verify_node_envelope(stored, stored.get('signature'), key.public_key))
`
const verifyOut = execFileSync(dockerBin, ['exec', '-i', '-w', '/backend', 'dvadmin3-django', 'python', '-'], {
  input: verifyProgram,
  encoding: 'utf8',
  env: { ...process.env, MSYS_NO_PATHCONV: '1' }
})
const canonLines = verifyOut.trim().split('\n').filter((l) => /^[A-Z_]+=/.test(l)).join(' ')
check('★★ 服务端用**它自己那份规范实现**验签：通过（证明两侧的序列化逐字节一致）',
  verifyOut.includes('VERIFY=True'), canonLines)

// 判据三：**改一个字节就验不过**。没有这一条，"验签通过"可能只是
// "验签函数恒返回 True"——那是这套证据里最容易假绿的一种。
const tamperedProgram = verifyProgram.replace(
  "print('VERIFY=%s' % verify_node_envelope(stored, stored.get('signature'), key.public_key))",
  "stored['recipient_key_version'] = 2\n"
  + "print('TAMPERED=%s' % verify_node_envelope(stored, stored.get('signature'), key.public_key))"
)
const tamperedOut = execFileSync(dockerBin, ['exec', '-i', '-w', '/backend', 'dvadmin3-django', 'python', '-'], {
  input: tamperedProgram,
  encoding: 'utf8',
  env: { ...process.env, MSYS_NO_PATHCONV: '1' }
})
check('★★ 把接收方版本从 v1 改成 v2（一个字段）→ **验不过**（签名真的绑住了这些字段）',
  tamperedOut.includes('TAMPERED=False'),
  tamperedOut.trim().split('\n').filter((l) => l.startsWith('TAMPERED')).join(' '))

// 判据四：**不带签名**直接拒（"移除服务端代签名"的落点：服务端自己不签，
// 也不接受没签的 —— 留一条无签名入口等于把签名变成可选）。
const noSigBody = { ...reqB.body }
delete noSigBody.signature
const noSig = await distribute(nodeA, noSigBody)
check('★ 不带签名 → SIGNATURE_REQUIRED（服务端不代签，也不接受未签名）',
  noSig.body?.code === 409 && noSig.body?.data?.error_code === 'SIGNATURE_REQUIRED',
  `code=${noSig.body?.code} ${noSig.body?.data?.error_code} msg=${noSig.body?.msg}`)

// 判据五：摘要对不上就拒 —— 它抓的是"两侧规范化口径漂移"这类实现问题，
// 在**登记**这一步就报出来，而不是等 KMS-010 验签时报成"签名无效"（像伪造）。
const badDigestBody = JSON.parse(JSON.stringify(reqB.body))
badDigestBody.envelope.ciphertext_digest = 'f'.repeat(64)
const badDigest = await distribute(nodeA, badDigestBody)
check('★ 信封摘要与服务端重算的不一致 → ENVELOPE_TAMPERED（把序列化漂移与伪造分开）',
  badDigest.body?.data?.error_code === 'ENVELOPE_TAMPERED',
  `${badDigest.body?.data?.error_code} msg=${badDigest.body?.msg}`)

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
const reqBv2 = await buildSignedBody({
  receiverNodeId: nodeB.nodeId,
  protectionAlgorithm: KYBER,
  recipientKeyId: K2v2.keyId,
  recipientKeyVersion: 2,
  recipientPublicKeyHex: K2v2.publicKey
})
const distBv2 = await distribute(nodeA, reqBv2.body)
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
check('★★ 这一次的库内信封同样与节点产出逐字节一致（换一版重复一次同样的判据）',
  JSON.parse(envelopeOf(batchBv2) || '{}').kem_ciphertext === reqBv2.built.envelope.kem_ciphertext,
  '两串若不同，说明服务端又自己封了一份')

// 4.3 有效期：由**调用方**给出（签名要覆盖它），服务端只校验上界
const reqDef = await buildSignedBody({
  receiverNodeId: nodeB.nodeId,
  protectionAlgorithm: KYBER,
  recipientKeyId: K2v2.keyId,
  recipientKeyVersion: 2,
  recipientPublicKeyHex: K2v2.publicKey,
  expiresInHours: 24
})
const distDef = await distribute(nodeA, reqDef.body)
const batchDef = distDef.body?.data?.batchId || ''
check('★ 调用方给 24 小时 → 库里就是 24 小时（服务端按它落库，不再自己算）',
  isOk(distDef.body) && nearMinutes(expiresMinutes(batchDef), 24 * 60),
  `库内有效期差=${expiresMinutes(batchDef)} 分钟（期望 ${24 * 60}）`)

// 4.4 有效期上界由**服务端**强制（"客户端给值"不等于"客户端说了算"）
const overBody = JSON.parse(JSON.stringify(reqDef.body))
overBody.batchId = (await import('../src/utils/crypto/envelope-signing.js')).newBatchId()
overBody.expiresAt = new Date(Date.now() + 999 * 3600 * 1000).toISOString()
const over = await distribute(nodeA, overBody)
check('★ expiresAt 超过 168 小时 → 被拒（上界仍在服务端，不由调用方定）',
  over.body?.data?.error_code === 'INVALID_PARAMETER',
  `${over.body?.data?.error_code} msg=${over.body?.msg}`)
const badBatch = await distribute(nodeA, { ...reqDef.body, batchId: 'not-a-batch-id' })
check('★ batchId 形状非法 → 被拒（客户端生成，但形状由服务端定义）',
  badBatch.body?.data?.error_code === 'INVALID_PARAMETER',
  `${badBatch.body?.data?.error_code} msg=${badBatch.body?.msg}`)

// ---------------------------------------------------------------------------
// 6. ★ 三种保护算法都能产生信封（阶段 3 出口检查的前半句）+ 版本引用都进库
// ---------------------------------------------------------------------------
title('6. ★ 三种保护算法各产一封有效信封，且都按指定版本封装')
for (const algorithm of [SM2, SSCL]) {
  const material = keys.B[algorithm]
  const req = await buildSignedBody({
    receiverNodeId: nodeB.nodeId,
    protectionAlgorithm: algorithm,
    recipientKeyId: material.keyId,
    recipientKeyVersion: 1,
    recipientPublicKeyHex: material.publicKey
  })
  const res = await distribute(nodeA, req.body)
  const batchId = res.body?.data?.batchId || ''
  const expectedWrapping = algorithm === SM2 ? 'gm_sm2' : 'gm_sscl'
  check(`★ ${algorithm}：分发成功且库内引用 = 指定的那一版`,
    isOk(res.body) && poolFact(batchId) === `${material.keyId}|1|distributed|NULL`,
    `code=${res.body?.code} 读到 ${poolFact(batchId)}`)

  const env = JSON.parse(envelopeOf(batchId) || '{}')
  check(`${algorithm}：信封是国密形状（algorithm='sm2' + ciphertext + wrapping_algorithm=${expectedWrapping}）`,
    env.algorithm === 'sm2' && Boolean(env.ciphertext) && env.wrapping_algorithm === expectedWrapping,
    `字段=${JSON.stringify(Object.keys(env))} wrapping=${env.wrapping_algorithm}`)
  check(`${algorithm}：库内密文与节点本机产出的逐字一致（服务端没有代封）`,
    env.ciphertext === req.built.envelope.ciphertext,
    `库内=${String(env.ciphertext).slice(0, 24)}… 本机=${String(req.built.envelope.ciphertext).slice(0, 24)}…`)

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

// 7.6 有效期与批次号：**形状由调用方给，约束由服务端定**
//     （KMS-009 起两者都是调用方提供的，所以这几条比 KMS-008 时更要紧 ——
//      "客户端给值"不等于"客户端说了算"。上界那两条在 4.4 节已验，这里查形状。）
for (const bad of [null, '', 'not-a-time', 12345, '2020-01-01T00:00:00Z']) {
  const body = { ...reqBv2.body, expiresAt: bad }
  const res = await distribute(nodeA, body)
  check(`expiresAt=${JSON.stringify(bad)} 被拒（ISO8601、不能已过期；不做时间猜测）`,
    res.body?.data?.error_code === 'INVALID_PARAMETER',
    `${errCodeOf(res.body)} msg=${String(res.body?.msg).slice(0, 80)}`)
}
for (const bad of [null, '', 'dist-xx', 'x'.repeat(70)]) {
  const body = { ...reqBv2.body, batchId: bad }
  const res = await distribute(nodeA, body)
  check(`batchId=${JSON.stringify(bad)} 被拒（形状由服务端定义）`,
    res.body?.data?.error_code === 'INVALID_PARAMETER',
    `${errCodeOf(res.body)}`)
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
  `B 上引用 v2 的池行=${poolRowsForBV2}（期望 2：4.2 与 4.3 两节各成功一条）`)

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
const reqFresh = await buildSignedBody({
  receiverNodeId: nodeB.nodeId,
  protectionAlgorithm: KYBER,
  recipientKeyId: K2v2.keyId,
  recipientKeyVersion: 2,
  recipientPublicKeyHex: K2v2.publicKey
})
const fresh = await distribute(nodeA, reqFresh.body)
check('★ 新接口**没有** Deprecation 头（与第 8 节配成一对）',
  isOk(fresh.body) && String(fresh.headers?.deprecation || '') !== 'true',
  `deprecation=${JSON.stringify(fresh.headers?.deprecation)}`)

// 新契约里 source_key_id 即使被传了也不作数（库内必须是 NULL）。
// ⚠️ 另造一份**新签的**请求体再塞 `source_key_id`，而不是改上面那份的 batchId ——
//    `batch_id` 是被签字段，改它等于提交一份"签名对不上的请求"。
//    那种请求现在（还没验签）能过，但它是**语义非法**的，会把这条断言
//    建立在"服务端还没验签"之上；KMS-010 落地后它会突然变红，
//    而红的原因与本条要证明的事（source_key_id 不作数）毫无关系。
const reqWithSource = await buildSignedBody({
  receiverNodeId: nodeB.nodeId,
  protectionAlgorithm: KYBER,
  recipientKeyId: K2v2.keyId,
  recipientKeyVersion: 2,
  recipientPublicKeyHex: K2v2.publicKey
})
const withSource = await distribute(nodeA, {
  ...reqWithSource.body,
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