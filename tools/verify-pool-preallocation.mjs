// =============================================================================
// verify-pool-preallocation.mjs —— 任务书「预分配」端到端验收
// -----------------------------------------------------------------------------
// 规范（用户定义，逐字）：
//   "密钥预分配是指发送节点在实际通信之前，提前生成一定数量的随机 SM4 会话密钥，
//    利用接收节点的 Kyber 公钥形成加密保护包，并将保护包上传至 KMS 预分配密钥池。
//    服务端仅负责保存、调度和管理保护包。实际建立会话时，发送节点取用一条预分配
//    资源，使用 Falcon 私钥签名并发送，接收节点验签和解封装成功后，双方建立
//    SM4 安全会话"
//
// 本脚本把这句话拆成**可执行的判据**，逐条对上：
//
//   1. 节点侧生成 + 封装 + 上传 —— 且**实测吞吐**（任务书 §20 的量化指标
//      「Kyber 预分配 ≥ 50 条/秒」）。做不到就如实报实测值，不四舍五入凑数。
//   2. 服务端**拿不到 K**：库里只有密文与摘要；K 的哈希由发送方声称、
//      服务端无法自算（本脚本用"服务端从未见过 K"来钉：它只回 key_hash）。
//   3. 池项在**取用之前**不出现在任何一方的信封列表里
//      （`recipient_type='pool'` vs 'node'）—— 负对照。
//   4. 取用是**一次性**的：并发取两条 → 恰好两条不同的池项被消费。
//   5. **真往返**（核心）：接收方拿到信封 → 本地用发送方 Falcon 公钥验签 →
//      用本机 Kyber 私钥解封 → 解出的 K 的 sha256 **逐字节等于**库内 key_hash
//      → 服务端独立验签也通过。
//   6. 长期密钥回收 → 该批剩余池项转 REVOKED、再取用被拒（与 KMS-007/013 同判据）。
//   7. 授权仍是唯一判据：未授权节点取用被拒。
//
// ⚠️ 会真建 2 个节点、真走完整条链、结尾自建自清。
// 用法：node tools/verify-pool-preallocation.mjs
// =============================================================================
import { execFileSync, spawn } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { login } from './lib/captcha.mjs'
import { sql, sqlScalar } from './lib/mysql.mjs'

const ORIGIN = 'http://127.0.0.1'
const DOMAIN = 'pool-verify'
const PORT = 9407
const CHROME = ['C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find((p) => existsSync(p))

const POOL_ITEMS = 'falcon_kds.dvadmin_pqkds_pre_distributed_keys'
const NODES = 'falcon_kds.dvadmin_pqkds_nodes'
const SESSIONS = 'falcon_kds.dvadmin_pqkds_session_keys'
const LOGS = 'falcon_kds.dvadmin_pqkds_key_distribution_log'

const results = []
const check = (n, p, d = '') => {
  results.push({ n, p, d })
  console.log(`  ${p ? '[PASS]' : '[FAIL]'} ${n}${d ? '  → ' + String(d).slice(0, 220) : ''}`)
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const nodePk = (nodeId) => sqlScalar(`SELECT id FROM ${NODES} WHERE node_id='${nodeId}';`)

const api = async (path, { method = 'GET', token, body } = {}) => {
  const res = await fetch(`${ORIGIN}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    ...(body ? { body: JSON.stringify(body) } : {})
  })
  let parsed = null
  try { parsed = await res.json() } catch { parsed = null }
  return { status: res.status, body: parsed }
}

let chrome = null
let ws = null

try {
  // ===== 1. 夹具：两个节点，各自四套长期密钥 =====
  console.log('\n== 1. 建节点 A(发送方) / B(接收方) 并初始化 ==')
  const admin = await login(ORIGIN, '/updatedel-api', 'admin', 'admin123')
  const lib = await import('../kms-updatedel/front/tools/lib/node-session.mjs')
  const { cryptoProvider } = lib
  const sign = await import('../kms-updatedel/front/src/utils/crypto/envelope-signing.js')
  const { buildKeyRef } = await import('../kms-updatedel/front/src/utils/crypto/key-ref.js')

  const sessions = []
  for (const tag of ['PA', 'PB']) {
    const created = await lib.createNode(admin, { prefix: tag, domainId: DOMAIN })
    const act = await lib.activateNode(created.nodeId, created.activationCode)
    // 四套长期密钥：Kyber（封装用）与 Falcon（签名用）是必须的，另外两套是为了
    // 让节点状态与真实节点一致（初始化要求四套齐全）。
    for (const [algo, opts] of [['SM2', {}], ['SSCL', {}], ['KYBER', { variant: 768 }], ['FALCON', {}]]) {
      const kp = await cryptoProvider.generate(algo, { nodeId: created.nodeId, ...opts })
      await fetch(`${ORIGIN}/pqkds-api/pqkds/node-self/keys/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${act.token}` },
        body: JSON.stringify({
          algorithm: algo, publicKey: kp.publicKey, deviceId: act.fingerprint,
          keyId: kp.keyId, keyVersion: kp.version
        })
      })
    }
    await fetch(`${ORIGIN}/pqkds-api/pqkds/node-self/init/`, {
      method: 'POST', headers: { Authorization: `Bearer ${act.token}` }
    })
    sessions.push({ tag, nodeId: created.nodeId, token: act.token })
  }
  const [A, B] = sessions
  check('两个节点已建好并各自完成初始化（四套长期密钥）',
    Boolean(A?.token) && Boolean(B?.token), `${A?.nodeId} / ${B?.nodeId}`)

  // 授权（预分配与取用都走同一条判据）。
  const sub = await api('/pqkds-api/pqkds/node-self/authorization-requests/', {
    method: 'POST', token: A.token, body: { targetNodeId: B.nodeId, reason: '预分配验收' }
  })
  const reqId = sub.body?.data?.request?.id
  await api(`/pqkds-api/pqkds/admin/node-authorization-requests/${reqId}/decide/`, {
    method: 'POST', token: admin, body: { decision: 'approve', remark: '验收' }
  })
  const authOk = await api(`/pqkds-api/pqkds/node-self/peers/${B.nodeId}/keys/?algorithm=KYBER`,
    { token: A.token })
  check('授权已生效（A 能取 B 的 Kyber 公钥版本）',
    authOk.body?.code === 200, `code=${authOk.body?.code}`)

  // ===== 2. 节点侧生成 + 封装 + 签名 + 上传（实测吞吐）=====
  console.log('\n== 2. 节点侧批量预封装并上传（任务书 §20 指标）==')
  const peerKeys = await api(`/pqkds-api/pqkds/node-self/peers/${B.nodeId}/keys/?algorithm=KYBER`,
    { token: A.token })
  const kyberKey = (peerKeys.body?.data?.keys || []).find((k) => k.allowsNewWork === true)
  const myKeys = await api('/pqkds-api/pqkds/node-self/keys/', { token: A.token })
  const falconMeta = (myKeys.body?.data?.keys || [])
    .find((k) => k.algorithm === 'FALCON' && k.allowsNewWork === true)
  const falconRef = buildKeyRef({
    nodeId: A.nodeId, algorithm: 'FALCON',
    keyId: falconMeta.keyId, version: falconMeta.keyVersion
  })

  const N = 20
  const poolId = `pool_${sign.nodeCanonicalPayload ? '' : ''}${Buffer.from(
    crypto.getRandomValues(new Uint8Array(16))).toString('hex')}`
  const expiresAt = new Date(Date.now() + 24 * 3600 * 1000).toISOString()
  const localKeys = []
  const items = []
  const t0 = performance.now()
  for (let i = 0; i < N; i++) {
    const K = sign.generatePayloadKey()
    localKeys.push(K)
    const built = await sign.buildNodeEnvelope({
      provider: cryptoProvider, payloadKey: K, wrapping: 'KYBER',
      recipientPublicKeyHex: kyberKey.publicKey, batchId: poolId,
      senderNodeId: A.nodeId, receiverNodeId: B.nodeId,
      recipientKeyId: kyberKey.keyId, recipientKeyVersion: kyberKey.keyVersion, expiresAt
    })
    const signature = await sign.signNodeEnvelope(cryptoProvider, falconRef, built.envelope)
    items.push({ envelope: built.envelope, signature, keyHash: built.keyHash })
  }
  const localMs = performance.now() - t0
  const localRate = Math.round((N / localMs) * 1000)
  // ⚠️ 这是**任务书 §20 的量化指标**。达不到就报实测值（判据会红），
  //    绝不四舍五入或换个口径把它凑过 —— 那等于把指标做成了装饰。
  check(`★★ 本机（节点侧）生成 + 封装 + 签名吞吐 ≥ 50 条/秒（实测 ${localRate} 条/秒）`,
    localRate >= 50, `${N} 条 / ${localMs.toFixed(0)}ms = ${localRate} 条/秒`)

  const up = await api('/pqkds-api/pqkds/node-self/pool/preallocate/', {
    method: 'POST', token: A.token,
    body: {
      targetNodeCode: B.nodeId, poolId, expiresAt, items,
      falconKeyId: falconMeta.keyId, falconKeyVersion: falconMeta.keyVersion
    }
  })
  check('★★ 上传保护包：服务端逐条验签后入池（generated = 请求数）',
    up.body?.code === 200 && up.body?.data?.generated === N,
    `generated=${up.body?.data?.generated}/${up.body?.data?.requested} failed=${JSON.stringify(up.body?.data?.failed || []).slice(0, 200)}`)

  // 落库形状：READY + pool + node1=B(收件方) + long_term_key 引用 = B 那一版
  const row = sql(`SELECT status, recipient_type, node1_id, node2_id, long_term_key_id, long_term_key_version, key_hash FROM ${POOL_ITEMS} WHERE pool_id='${poolId}' ORDER BY key_index LIMIT 1;`)
  const bPk = nodePk(B.nodeId)
  const aPk = nodePk(A.nodeId)
  check('★★ 落库：READY / recipient_type=pool / node1=接收方 / 长期密钥引用=B 那一版',
    /READY/.test(row) && /\bpool\b/.test(row) && row.includes(String(bPk))
    && row.includes(String(kyberKey.keyId)),
    row.replace(/\t/g, ' | '))

  // 服务端**拿不到 K**：库里那份密文解不出 K（它没私钥），只有摘要。
  const cipherText = sqlScalar(`SELECT encrypted_key_data FROM ${POOL_ITEMS} WHERE pool_id='${poolId}' LIMIT 1;`)
  const hashInDb = sqlScalar(`SELECT key_hash FROM ${POOL_ITEMS} WHERE pool_id='${poolId}' ORDER BY key_index LIMIT 1;`)
  const k0Hash = await sign.keyHashOf(localKeys[0])
  check('★★ 服务端存的只是密文（解不出 K）：库内 key_hash = 本机 K0 的 sha256',
    cipherText.includes('kem_ciphertext') && !cipherText.includes(Buffer.from(localKeys[0]).toString('hex'))
    && hashInDb === k0Hash,
    `hash一致=${hashInDb === k0Hash} 密文含明文K=${cipherText.includes(Buffer.from(localKeys[0]).toString('hex'))}`)

  // ===== 3. 负对照：未取用前，双方信封列表都看不到 =====
  console.log('\n== 3. 负对照：未取用的池项对双方都不可见 ==')
  const bEnvBefore = await api('/pqkds-api/pqkds/node-self/envelopes/', { token: B.token })
  const aEnvBefore = await api('/pqkds-api/pqkds/node-self/envelopes/', { token: A.token })
  const seenByPool = (r) => (r.body?.data?.items || []).filter((i) => i.poolId === poolId).length
  check('★★ 接收方的信封列表里**还没有**它（还没发）',
    seenByPool(bEnvBefore) === 0, `可见 ${seenByPool(bEnvBefore)} 条`)
  check('★ 发送方也看不到（池项不是给他的信封）',
    seenByPool(aEnvBefore) === 0, `可见 ${seenByPool(aEnvBefore)} 条`)

  // 余量
  const summary = await api('/pqkds-api/pqkds/node-self/pool/summary/', { token: A.token })
  const mine = (summary.body?.data?.items || []).find((i) => i.nodeCode === B.nodeId)
  check('★ 余量接口如实报可用条数', mine?.available === N, JSON.stringify(mine))

  // ===== 4. 取用（一次性）+ 并发不重复 =====
  console.log('\n== 4. 取用：一次性、并发不重复 ==')
  const batchId = sign.newBatchId()
  const consume1 = await api('/pqkds-api/pqkds/node-self/pool/consume/', {
    method: 'POST', token: A.token,
    body: {
      peerNodeCode: B.nodeId, batchId, protectionAlgorithm: 'KYBER',
      falconKeyId: falconMeta.keyId, falconKeyVersion: falconMeta.keyVersion
    }
  })
  check('★★ 取用成功：建 initiated 会话 + 余量减一',
    consume1.body?.code === 200 && Boolean(consume1.body?.data?.sessionId)
    && consume1.body?.data?.remaining === N - 1,
    `session=${consume1.body?.data?.sessionId} 剩余=${consume1.body?.data?.remaining}`)

  // 并发取两条：必须命中**两条不同的**池项。
  const fire = () => api('/pqkds-api/pqkds/node-self/pool/consume/', {
    method: 'POST', token: A.token,
    body: {
      peerNodeCode: B.nodeId, batchId: sign.newBatchId(), protectionAlgorithm: 'KYBER',
      falconKeyId: falconMeta.keyId, falconKeyVersion: falconMeta.keyVersion
    }
  })
  const [r1, r2] = await Promise.all([fire(), fire()])
  const idx1 = r1.body?.data?.keyIndex
  const idx2 = r2.body?.data?.keyIndex
  const consumedAfter = Number(sqlScalar(
    `SELECT COUNT(*) FROM ${POOL_ITEMS} WHERE pool_id='${poolId}' AND status='CONSUMED';`))
  check('★★ 并发取用两条 → 恰好两条**不同**的池项（不重复消费）',
    r1.body?.code === 200 && r2.body?.code === 200 && idx1 !== idx2 && consumedAfter === 3,
    `index=${idx1}/${idx2} code=${r1.body?.code}/${r2.body?.code} 已消费=${consumedAfter} msg=${r1.body?.code === 200 ? (r2.body?.msg || '') : (r1.body?.msg || '')}`)

  // ===== 5. 补签名 + 真往返 =====
  console.log('\n== 5. 补签名 + 接收方验签解封（真往返）==')
  const envPk = consume1.body?.data?.envelopeId
  const envelope = consume1.body?.data?.envelope
  const sig = await sign.signNodeEnvelope(cryptoProvider, falconRef, envelope)
  const signed = await api(`/pqkds-api/pqkds/node-self/envelopes/${envPk}/sign/`, {
    method: 'POST', token: A.token,
    body: { signature: sig, falconKeyId: falconMeta.keyId, falconKeyVersion: falconMeta.keyVersion }
  })
  check('★ 发送方补交签名（服务端先独立验一遍再落库）',
    signed.body?.code === 200 && signed.body?.data?.signatureAttached === true,
    signed.body?.msg)
  const signedAgain = await api(`/pqkds-api/pqkds/node-self/envelopes/${envPk}/sign/`, {
    method: 'POST', token: A.token,
    body: { signature: sig, falconKeyId: falconMeta.keyId, falconKeyVersion: falconMeta.keyVersion }
  })
  check('★ 同一份签名重复补交 → 幂等（alreadySigned，不重复写）',
    signedAgain.body?.data?.alreadySigned === true, signedAgain.body?.msg)
  const signForbidden = await api(`/pqkds-api/pqkds/node-self/envelopes/${envPk}/sign/`, {
    method: 'POST', token: B.token, body: { signature: sig }
  })
  check('★ 接收方（非签名者）补签 → 拒',
    signForbidden.body?.code === 403, `code=${signForbidden.body?.code} msg=${signForbidden.body?.msg}`)

  // 接收方列表里出现它
  const bEnv = await api('/pqkds-api/pqkds/node-self/envelopes/', { token: B.token })
  const mineEnv = (bEnv.body?.data?.items || []).find((i) => i.envelopeId === envPk)
  check('★★ 取用后接收方的信封列表里出现它，且带签名',
    Boolean(mineEnv) && Boolean(mineEnv?.envelope?.signature),
    `session=${mineEnv?.sessionId} hasSignature=${Boolean(mineEnv?.envelope?.signature)}`)

  // 真往返：本机解封 → sha256 与库内 key_hash 逐字节一致
  const kyberRef = buildKeyRef({
    nodeId: B.nodeId, algorithm: 'KYBER',
    keyId: kyberKey.keyId, version: kyberKey.keyVersion
  })
  let recovered = null
  let unwrapErr = ''
  try {
    recovered = await cryptoProvider.unwrapEnvelope('KYBER', kyberRef, mineEnv.envelope)
  } catch (error) {
    unwrapErr = String(error?.message || error)
  }
  const recoveredHash = recovered ? await sign.keyHashOf(recovered) : ''
  check('★★★ 接收方本机解封得到 K，其 sha256 **逐字节等于**库内 key_hash',
    Boolean(recovered) && recoveredHash === hashInDb,
    unwrapErr || `recovered=${recoveredHash.slice(0, 16)}… db=${hashInDb.slice(0, 16)}…`)

  // ⚠️ 这条同时钉住"发送方当时封的确实是库内那一份"：解出来的 K 必须**就是**
  //    发送方本机那把（否则"解开了"可能只是解出了别的东西）。
  const k0 = localKeys[consume1.body?.data?.keyIndex]
  check('★★★ 解出的 K 与**发送方本机那把**逐字节相同（按 keyIndex 对位）',
    Boolean(recovered) && Buffer.from(recovered).toString('hex') === Buffer.from(k0).toString('hex'),
    `idx=${consume1.body?.data?.keyIndex}`)

  // 服务端独立验签
  const srvVerify = await api(`/pqkds-api/pqkds/node-self/envelopes/${envPk}/verify/`, {
    method: 'POST', token: B.token, body: {}
  })
  check('★★ 服务端独立验签通过（用它自己记得的那一版发送方 Falcon 公钥）',
    srvVerify.body?.code === 200, `code=${srvVerify.body?.code} msg=${srvVerify.body?.msg}`)

  // 审计流水
  const logHit = Number(sqlScalar(
    `SELECT COUNT(*) FROM ${LOGS} WHERE action IN ('pool_consume','pool_prealloc') AND node_id=${aPk};`))
  check('★ 预分配与取用都写了审计流水（「分发记录」页的数据源）',
    logHit >= 4, `${logHit} 条`)
  // ⚠️ 流水里**绝不能有 K**：这一列会显示在页面上。
  const leak = sqlScalar(
    `SELECT COUNT(*) FROM ${LOGS} WHERE details LIKE '%${Buffer.from(k0).toString('hex')}%';`)
  check('★★ 审计流水里不含明文 K（那是会显示在页面上的列）',
    Number(leak) === 0, `命中 ${leak} 条`)

  // ===== 6. 长期密钥回收 → 该批剩余池项失效 =====
  console.log('\n== 6. 回收接收方那一版 Kyber → 剩余池项失效、再取用被拒 ==')
  const revoke = await api('/pqkds-api/pqkds/node-self/keys/revoke/', {
    method: 'POST', token: B.token,
    body: {
      algorithm: 'KYBER', keyId: kyberKey.keyId, keyVersion: kyberKey.keyVersion,
      reason: '验收：回收该版'
    }
  })
  check('接收方回收 Kyber 那一版成功', revoke.body?.code === 200, `code=${revoke.body?.code} msg=${revoke.body?.msg}`)
  const revokedLeft = Number(sqlScalar(
    `SELECT COUNT(*) FROM ${POOL_ITEMS} WHERE pool_id='${poolId}' AND status='READY';`))
  check('★★ 该批**剩余** READY 池项被连带置为 REVOKED（与 KMS-007 同判据）',
    revokedLeft === 0, `剩余 READY=${revokedLeft}`)
  const consumeAfter = await api('/pqkds-api/pqkds/node-self/pool/consume/', {
    method: 'POST', token: A.token,
    body: {
      peerNodeCode: B.nodeId, batchId: sign.newBatchId(), protectionAlgorithm: 'KYBER',
      falconKeyId: falconMeta.keyId, falconKeyVersion: falconMeta.keyVersion
    }
  })
  check('★★ 回收后再取用被拒（KEY_REVOKED / KEY_EXPIRED 系）',
    consumeAfter.body?.code !== 200, `code=${consumeAfter.body?.code} msg=${consumeAfter.body?.msg}`)

  // ===== 7. 未授权节点取用被拒（授权仍是唯一判据）=====
  console.log('\n== 7. 授权仍是唯一判据 ==')
  const created3 = await lib.createNode(admin, { prefix: 'PC', domainId: DOMAIN })
  const act3 = await lib.activateNode(created3.nodeId, created3.activationCode)
  const strangers = await api('/pqkds-api/pqkds/node-self/pool/consume/', {
    method: 'POST', token: act3.token,
    body: {
      peerNodeCode: A.nodeId, batchId: sign.newBatchId(), protectionAlgorithm: 'KYBER',
      falconKeyId: falconMeta.keyId, falconKeyVersion: falconMeta.keyVersion
    }
  })
  check('★★ 未授权的节点取用 → 拒（与分发同一条闸门，没有第二套判据）',
    strangers.body?.code === 403 || strangers.body?.data?.error_code === 'NOT_AUTHORIZED',
    `code=${strangers.body?.code} err=${strangers.body?.data?.error_code}`)
  // 会话确实建了（第 4 步那条 initiated）
  const sessRow = sql(`SELECT session_id, status FROM ${SESSIONS} WHERE node1_id=${aPk} AND node2_id=${bPk} ORDER BY id LIMIT 1;`)
  check('★★ 取用建的会话落在池号+序号下（接收方按 `{池号}-n{自己}` 找得到它）',
    new RegExp(`^${poolId}-k\\d+-n${bPk}$`).test((sessRow.split(/\s+/)[0] || '').trim()),
    sessRow.replace(/	/g, ' | '))
} catch (e) {
  console.error('\n[ERROR]', e.stack || e.message)
  results.push({ n: '脚本异常', p: false, d: String(e.message).slice(0, 200) })
} finally {
  try { ws?.close() } catch { /* noop */ }
  try { chrome.kill() } catch { /* noop */ }
  try {
    const out = execFileSync('docker', ['exec', '-i', 'dvadmin3-django', 'python', '-'], {
      input: `
import os, sys
sys.path.insert(0, '/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
import django
django.setup()
from pqkds.models import Node
rows = list(Node.objects.filter(domain_id='${DOMAIN}'))
ids = [n.pk for n in rows]
deleted, _ = Node.objects.filter(pk__in=ids).delete()
print('nodes=%d cascaded=%d left=%d' % (len(ids), deleted, Node.objects.filter(domain_id='${DOMAIN}').count()))
`,
      encoding: 'utf8', env: { ...process.env, MSYS_NO_PATHCONV: '1' }
    }).trim()
    console.log(`  [info] 清理：${out}`)
    check('清理完成：域内不再有本脚本建的节点及其池项/会话', out.endsWith('left=0'), out)
  } catch (error) {
    console.log(`  [info] 清理失败：${String(error?.message || error).slice(0, 150)}`)
    check('清理失败（需人工处理）', false)
  }
  const failed = results.filter((r) => !r.p)
  console.log(`\n===== 汇总 =====\n总计 ${results.length}，通过 ${results.length - failed.length}，失败 ${failed.length}`)
  failed.forEach((f) => console.log(`  - ${f.n}  ${f.d}`))
  process.exitCode = failed.length ? 1 : 0
}
