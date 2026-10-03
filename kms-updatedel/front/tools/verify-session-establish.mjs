/**
 * §6.5 端到端验证：会话提升为 established。
 *
 * 这一条此前**无法达成** —— 缺的不是"确认接口"，而是「接收节点恢复 SM4」
 * 这件事从没在节点侧发生过（服务端只封装入库，那几处 decaps 都在
 * 前端不调用的旧端点里）。所以本用例的判据分两层：
 *
 *   第一层：节点能取到自己的信封并**在本地解出 K**（这是新增能力）
 *   第二层：双方各交 HMAC(K, session_id)，服务端比较后提升为 established
 *
 * ⚠️ 关键断言是「服务端自始至终没看到 K」：
 *    它只比较两条 PRF 输出。若为了确认而让节点上传 K，
 *    数据库泄露就从"元数据泄露"变成"全部会话密钥泄露"。
 */
import 'fake-indexeddb/auto'
import { execFileSync } from 'node:child_process'
import { writeFileSync, unlinkSync } from 'node:fs'
import { createHmac, createHash } from 'node:crypto'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const results = []
const check = (n, p, d = '') => { results.push({ n, p, d }); console.log(`  ${p ? '[PASS]' : '[FAIL]'} ${n}${d ? '  → ' + d : ''}`) }
const ORIGIN = 'http://127.0.0.1'
const PQKDS = `${ORIGIN}/pqkds-api/pqkds`
const hex = (u8) => [...u8].map((b) => b.toString(16).padStart(2, '0')).join('')

// 本文件在 `kms-updatedel/front/tools/` 下：
//   `../src/...`                  → kms-updatedel/front/src/...   （退一级）
//   `../../../tools/lib/...`      → kms-code/tools/lib/...        （退三级，到仓库根）
// ⚠️ 这两个 `../` 的数量不一样是**正确**的：src 在前端目录下，
//    而 captcha.mjs 在**仓库根**的 tools/ 下。写错一个的报错是
//    ERR_MODULE_NOT_FOUND 指向某个 .mjs，看不出是层级数错了。
const { cryptoProvider } = await import('../src/utils/crypto/browser-provider.js')
const { login } = await import('../../../tools/lib/captcha.mjs')

// 临时文件放在**本文件同目录**（与 verify-node-crypto.mjs 同一写法）：
// 写死绝对路径在换机器/换目录时必然失效，而那种失效表现为
// "docker cp 找不到文件"，看不出是路径写死了。
const HERE = dirname(fileURLToPath(import.meta.url))

function sql(q) {
  const local = join(HERE, '._q_session.sql')
  writeFileSync(local, q, 'utf8')
  try {
    execFileSync('docker', ['cp', local, 'kms_mysql:/tmp/_q3.sql'], { encoding: 'utf8' })
    const pw = execFileSync('bash', ['-lc', "grep -E '^MYSQL_ROOT_PASSWORD=' C:/Users/AllenR/Desktop/kms-code/kms-ops/.env | head -1 | sed 's/^MYSQL_ROOT_PASSWORD=//' | tr -d '\\r\"'"], { encoding: 'utf8' }).trim()
    return execFileSync('docker', ['exec', 'kms_mysql', 'sh', '-c', `mysql -uroot -p'${pw}' falcon_kds -N -B < /tmp/_q3.sql`], { encoding: 'utf8' })
  } finally { try { unlinkSync(local) } catch { /* 忽略 */ } }
}

function runPy(code, tag) {
  const local = join(HERE, `._v_${tag}.py`)
  writeFileSync(local, code, 'utf8')
  try {
    execFileSync('docker', ['cp', local, `dvadmin3-django:/backend/_v_${tag}.py`], { encoding: 'utf8' })
    return execFileSync('docker', ['exec', 'dvadmin3-django', 'python', `/backend/_v_${tag}.py`],
      { encoding: 'utf8', env: { ...process.env, MSYS_NO_PATHCONV: '1' } })
  } finally { try { unlinkSync(local) } catch { /* 忽略 */ } }
}

const admin = await login(ORIGIN, '/updatedel-api', 'admin', 'admin123')
const api = async (base, p, { method = 'GET', token, body } = {}) => {
  const r = await fetch(`${base}${p}`, { method, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}) }, ...(body ? { body: JSON.stringify(body) } : {}) })
  return { status: r.status, body: await r.json().catch(() => null) }
}
const isOk = (b) => b?.code === 200 || b?.code === 2000

const SEED = Date.now()
const STAMP = SEED.toString(36).toUpperCase().slice(-6)
const NODE_A = `NSA-${STAMP}`   // 发送方（也是分发发起人）
const NODE_B = `NSB-${STAMP}`   // 接收方

// ---------------------------------------------------------------- 准备
console.log('\n=== 1. 建两个节点，各自生成并上报四套公钥 ===')
const nodes = {}
let seq = 1
for (const nid of [NODE_A, NODE_B]) {
  // ⚠️ register 有**两条**重复检查：按 node_id，以及按 ip:port。
  //    编号唯一不够 —— 两个节点若落在同一 ip:port 上，第二个会被判成
  //    "IP 已被使用"并返回**第一个节点**，而现象只是"第二个节点建不出来"。
  const r = await api(PQKDS, '/nodes/register/', { method: 'POST', token: admin, body: {
    node_id: nid, name: nid,
    ip_address: `10.66.${((SEED + seq) % 200) + 1}.${seq}`,
    port: 52000 + (SEED % 5000) + seq,
    node_type: 'full', permission_level: 'L2', domain_id: 'd65' } })
  seq += 1
  if (!isOk(r.body)) { console.log(`建节点 ${nid} 失败:`, JSON.stringify(r.body).slice(0, 200)); process.exit(1) }
  const token = await login(ORIGIN, '/updatedel-api', nid, 'admin123')
  // keyRef 一律取 generate 的返回值，按节点登记在**唯一这一处**（解封/签名都从
  // 这里取）—— 手写串与 store 里的格式对不上时，报错只是"本机没有这把密钥"，
  // 看起来像密钥丢了，其实是引用拼错。
  nodes[nid] = { token, refs: {} }
  for (const [algo, opts] of [['SM2', {}], ['SSCL', {}], ['KYBER', { variant: 768 }], ['FALCON', {}]]) {
    const kp = await cryptoProvider.generate(algo, { nodeId: nid, ...opts })
    nodes[nid].refs[algo] = kp.keyRef
    const up = await api(PQKDS, '/node-self/keys/', { method: 'POST', token, body: {
      algorithm: algo, publicKey: kp.publicKey, securityLevel: opts.variant ? String(opts.variant) : undefined } })
    if (!isOk(up.body)) { console.log(`${nid}/${algo} 上报失败: ${up.body?.msg}`); process.exit(1) }
  }
  await api(PQKDS, '/node-self/init/', { method: 'POST', token })
  const id = sql(`SELECT id FROM dvadmin_pqkds_nodes WHERE node_id='${nid}';`).trim()
  nodes[nid].id = Number(id)
}
check('两个节点均初始化完成', true, `A=${nodes[NODE_A].id} B=${nodes[NODE_B].id}`)

// ---------------------------------------------------------------- 取节点用户 id 与授权
const userA = sql(`SELECT sys_user_id FROM dvadmin_pqkds_nodes WHERE node_id='${NODE_A}';`).trim()
const grant = await api(PQKDS, '/admin/node-authorizations/', { method: 'POST', token: admin, body: {
  userId: Number(userA), nodeId: nodes[NODE_B].id, remark: '§6.5 验证' } })
check('授权 A 与 B 通信', isOk(grant.body), `${grant.body?.msg || ''}`)

// ---------------------------------------------------------------- 分发（产生节点腿信封 + 会话）
console.log('\n=== 2. A 向 B 分发，产生节点腿信封与 initiated 会话 ===')
// ⚠️ uA 必须是**真实在 sm2p256v1 上的点** —— KGC 会校验曲线方程，
//    随手填 '04'+'ab'*64 会被拒，而报错发生在建密钥那一步，
//    表现为"源密钥已建"失败，看不出是 uA 的问题。
const UA = '04573e32965ced2ca54c9f9a26be3c5115f83f61bc0d7ed72b90ffb9cce6b741235c0e249f323ad7703340983665e5147c6893490242af26fa642372a899a74c30'
const keyRes = await api(`${ORIGIN}/updatedel-api`, '/lifecycle/keymanage', { method: 'POST', token: admin, body: {
  userId: Number(userA), userName: NODE_A, encrytType: '无证书非对称加密', encrytName: 'SM2',
  keyName: `p65-${STAMP}`, keyUse: 'session', keyDomain: 'A', status: '0', ua: UA } })
const sourceKeyId = keyRes.body?.data?.key_id ?? keyRes.body?.data?.keyId
check('源密钥已建', !!sourceKeyId, `keyId=${sourceKeyId} ${keyRes.body?.msg || ''}`)
if (!sourceKeyId) { console.log('无法继续'); process.exit(1) }

const dist = await api(PQKDS, '/key-pool/distribute-to-user/', { method: 'POST', token: nodes[NODE_A].token, body: {
  source_key_id: Number(sourceKeyId), node_ids: [nodes[NODE_B].id], count: 1, node_wrapping_algorithm: 'kyber_kem' } })
check('分发成功', isOk(dist.body), `${dist.body?.msg || ''}`)
const batchId = dist.body?.data?.batchId
if (!batchId) { console.log('无法继续'); process.exit(1) }

// ⚠️ 必须按**本次批次**取会话，不能取"最新一条" ——
//    库里还留着历次测试的会话，`ORDER BY id DESC LIMIT 1` 会抓到上一次的残留，
//    于是后面的确认与提升都作用在**别的会话**上，而用例照样全绿。
const sessionId = sql(`SELECT session_id FROM dvadmin_pqkds_session_keys WHERE session_id LIKE '${batchId}-%' ORDER BY id DESC LIMIT 1;`).trim()
check('本次批次已登记 initiated 会话', sessionId.startsWith(batchId), `sessionId=${sessionId}`)
const st0 = sql(`SELECT status FROM dvadmin_pqkds_session_keys WHERE session_id='${sessionId}';`).trim()
check('会话初始状态为 initiated（未越级建 established）', st0 === 'initiated', `status=${st0}`)

// ---------------------------------------------------------------- B 取信封并在本地解出 K
console.log('\n=== 3. ★ B 取自己的信封并在**本地**解出 K ===')
const envs = await api(PQKDS, '/node-self/envelopes/', { token: nodes[NODE_B].token })
const items = (envs.body?.data?.items || []).filter((it) => it.poolId === batchId)
check('取到本次批次的节点腿信封', items.length > 0, `本批条数=${items.length}（接口共返回 ${envs.body?.data?.items?.length || 0}）`)
const envItem = items[0]
if (!envItem) { console.log('无法继续：本批次没有可解的信封'); process.exit(1) }
check('信封不含任何私钥字段',
  !JSON.stringify(envItem).toLowerCase().includes('private'),
  `字段=${Object.keys(envItem).join(',')}`)

let recoveredKey = null
try {
  // ref 用生成 KYBER 时返回的那一把（nodes[NODE_B].refs.KYBER），不手写
  recoveredKey = await cryptoProvider.unwrapEnvelope(
    envItem.wrappingAlgorithm, nodes[NODE_B].refs.KYBER, envItem.envelope)
} catch (e) { check('★ B 在本地解封', false, e.message) }
if (recoveredKey) {
  check('★ B 在本地解封成功', true, `解出 ${recoveredKey.length} 字节`)
  // 与服务端记录的 key_hash 比对 —— 这是我们能自查"解对了"的唯一凭据
  const h = createHash('sha256').update(recoveredKey).digest('hex')
  check('★★ 解出的 K 与服务端记录的 key_hash 一致', h === envItem.keyHash,
    h === envItem.keyHash ? '' : `${h.slice(0, 16)} vs ${String(envItem.keyHash).slice(0, 16)}`)
}

// ---------------------------------------------------------------- 证明与提升
console.log('\n=== 4. ★ 双方提交证明 → 会话提升 ===')
const proofOf = (k) => createHmac('sha256', k).update(sessionId).digest('hex')

// 4a. 只有 B 提交 → 不提升
const cb = await api(PQKDS, `/node-self/sessions/${sessionId}/confirm/`, { method: 'POST', token: nodes[NODE_B].token, body: { proof: proofOf(recoveredKey) } })
check('单方提交后仍为 initiated（不越级提升）', cb.body?.data?.established === false,
  `established=${cb.body?.data?.established} msg=${cb.body?.msg || ''}`)

// 4b. 非会话方不得确认。
//
// ⚠️ 这里必须用**第三个映射到节点、但不属于这条会话**的节点来测。
//    用 admin 测是错的：admin 没映射到任何节点，会走
//    "当前账号未关联任何节点"那条分支 —— 用例照样 PASS，
//    但**根本没碰到会话方校验那一行**。
//    这类"通过的理由不对"的假通过，比失败更难发现。
const NODE_C = `NSC-${STAMP}`
const cRes = await api(PQKDS, '/nodes/register/', { method: 'POST', token: admin, body: {
  node_id: NODE_C, name: NODE_C, ip_address: `10.66.${((SEED + 99) % 200) + 1}.9`,
  port: 57000 + (SEED % 5000), node_type: 'full', permission_level: 'L2', domain_id: 'd65' } })
check('第三个节点（非会话方）已建', isOk(cRes.body), `code=${cRes.body?.code}`)
const tokenC = await login(ORIGIN, '/updatedel-api', NODE_C, 'admin123')
const outsider = await api(PQKDS, `/node-self/sessions/${sessionId}/confirm/`, { method: 'POST', token: tokenC, body: { proof: 'ab'.repeat(32) } })
check('★ 非会话方无权确认',
  !isOk(outsider.body) && /无权确认|不是这条会话/.test(String(outsider.body?.msg || '')),
  `code=${outsider.body?.code} msg=${String(outsider.body?.msg || '').slice(0, 50)}`)

// 4c. A 也提交**正确的**证明（A 持有同一把 K，因为它封装的）
const ca = await api(PQKDS, `/node-self/sessions/${sessionId}/confirm/`, { method: 'POST', token: nodes[NODE_A].token, body: { proof: proofOf(recoveredKey) } })
check('★★ 双方证明一致 → 提升为 established', ca.body?.data?.established === true,
  `established=${ca.body?.data?.established} msg=${ca.body?.msg || ''}`)
const st1 = sql(`SELECT status FROM dvadmin_pqkds_session_keys WHERE session_id='${sessionId}';`).trim()
check('★★ 库里会话状态确为 established', st1 === 'established', `status=${st1}`)

// ---------------------------------------------------------------- 服务端从未看到 K
console.log('\n=== 5. ★ 服务端自始至终没有 K ===')
const proofs = sql(`SELECT proof FROM dvadmin_pqkds_session_confirmations c JOIN dvadmin_pqkds_session_keys s ON s.id=c.session_id WHERE s.session_id='${sessionId}';`).trim()
const keyHex = hex(recoveredKey)
check('★ 库里存的确认是 HMAC 输出、不是 K 本身', !proofs.includes(keyHex) && proofs.length > 0,
  `proof 前缀=${proofs.slice(0, 20)}…`)
const leaked = sql(`SELECT COUNT(*) FROM dvadmin_pqkds_session_confirmations WHERE proof LIKE '%${keyHex}%';`).trim()
check('★ 全表检索不到明文 K', leaked === '0', `匹配=${leaked}`)

// ---------------------------------------------------------------- 证明不一致不提升
console.log('\n=== 6. 证明不一致时不提升（那是真问题，不能当成功）===')
const s2 = `${sessionId}-mismatch`
sql(`INSERT INTO dvadmin_pqkds_session_keys (session_id, node1_id, node2_id, encrypted_session_key, key_exchange_data, session_type, status, expires_at, create_datetime, update_datetime)
     SELECT '${s2}', node1_id, node2_id, encrypted_session_key, key_exchange_data, session_type, 'initiated', expires_at, NOW(), NOW()
     FROM dvadmin_pqkds_session_keys WHERE session_id='${sessionId}';`)
await api(PQKDS, `/node-self/sessions/${s2}/confirm/`, { method: 'POST', token: nodes[NODE_B].token, body: { proof: proofOf(recoveredKey) } })
const cm = await api(PQKDS, `/node-self/sessions/${s2}/confirm/`, { method: 'POST', token: nodes[NODE_A].token, body: { proof: 'cd'.repeat(32) } })
check('★ 双方证明不一致 → 不提升', cm.body?.data?.established === false,
  `established=${cm.body?.data?.established} msg=${String(cm.body?.msg || '').slice(0, 60)}`)
const st2 = sql(`SELECT status FROM dvadmin_pqkds_session_keys WHERE session_id='${s2}';`).trim()
check('★ 库里状态仍是 initiated', st2 === 'initiated', `status=${st2}`)

const pass = results.filter((r) => r.p).length
console.log(`\n=== 结果：${pass}/${results.length} 项通过 ===`)
if (pass !== results.length) { results.filter((r) => !r.p).forEach((r) => console.log(`  - ${r.n}  ${r.d}`)); process.exitCode = 1 }