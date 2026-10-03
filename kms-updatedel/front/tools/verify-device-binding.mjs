/**
 * §4.4 设备绑定验证。
 *
 * 要证明的是：**换了一台设备登录时，系统能发现**，并且这个发现是
 * 有依据的（服务端记着密钥绑在哪台设备，本机知道自己是哪台）。
 *
 * 为什么这件事非做不可：私钥只在节点侧，服务端**从密钥本身看不出**
 * 它属于哪台设备。没有绑定记录，"新设备登录"与"同一台设备"在服务端
 * 看来完全一样 —— 而两者的正确处置是相反的。
 * 后果是静默的：界面一切正常，直到某天某个信封解不开。
 */
import 'fake-indexeddb/auto'
import { execFileSync } from 'node:child_process'
import { writeFileSync, unlinkSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const HERE = dirname(fileURLToPath(import.meta.url))
const results = []
const check = (n, p, d = '') => { results.push({ n, p, d }); console.log(`  ${p ? '[PASS]' : '[FAIL]'} ${n}${d ? '  → ' + d : ''}`) }
const ORIGIN = 'http://127.0.0.1'
const PQKDS = `${ORIGIN}/pqkds-api/pqkds`

const { cryptoProvider } = await import('../src/utils/crypto/browser-provider.js')
const { login } = await import('../../../tools/lib/captcha.mjs')
const store = await import('../src/utils/crypto/node-key-store.js')

function sql(q) {
  const local = join(HERE, '._q_dev.sql')
  writeFileSync(local, q, 'utf8')
  try {
    execFileSync('docker', ['cp', local, 'kms_mysql:/tmp/_q_dev.sql'], { encoding: 'utf8' })
    const pw = execFileSync('bash', ['-lc', "grep -E '^MYSQL_ROOT_PASSWORD=' C:/Users/AllenR/Desktop/kms-code/kms-ops/.env | head -1 | sed 's/^MYSQL_ROOT_PASSWORD=//' | tr -d '\r\"'"], { encoding: 'utf8' }).trim()
    return execFileSync('docker', ['exec', 'kms_mysql', 'sh', '-c', `mysql -uroot -p'${pw}' falcon_kds -N -B < /tmp/_q_dev.sql`], { encoding: 'utf8' })
  } finally { try { unlinkSync(local) } catch { /* 忽略 */ } }
}

const api = async (p, { method = 'GET', token, body } = {}) => {
  const r = await fetch(`${PQKDS}${p}`, { method, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}) }, ...(body ? { body: JSON.stringify(body) } : {}) })
  return { status: r.status, body: await r.json().catch(() => null) }
}
const isOk = (b) => b?.code === 200 || b?.code === 2000

const SEED = Date.now()
const NODE_ID = `NDV-${SEED.toString(36).toUpperCase().slice(-6)}`
const admin = await login(ORIGIN, '/updatedel-api', 'admin', 'admin123')

console.log('\n=== 1. 建节点并完成初始化（设备 A）===')
const created = await api('/nodes/register/', { method: 'POST', token: admin, body: {
  node_id: NODE_ID, name: NODE_ID, ip_address: `10.88.${(SEED % 200) + 1}.1`,
  port: 62000 + (SEED % 10000), node_type: 'full', permission_level: 'L2', domain_id: 'ddv' } })
if (!isOk(created.body)) { console.log('建节点失败', JSON.stringify(created.body).slice(0, 150)); process.exit(1) }
const token = await login(ORIGIN, '/updatedel-api', NODE_ID, 'admin123')

const deviceA = await store.getDeviceId()
check('本机（设备 A）有 deviceId', Boolean(deviceA), `deviceA=${deviceA.slice(0, 12)}…`)

for (const [algo, opts] of [['SM2', {}], ['SSCL', {}], ['KYBER', { variant: 768 }], ['FALCON', {}]]) {
  const kp = await cryptoProvider.generate(algo, { nodeId: NODE_ID, ...opts })
  const up = await api('/node-self/keys/', { method: 'POST', token, body: {
    algorithm: algo, publicKey: kp.publicKey, deviceId: deviceA,
    securityLevel: opts.variant ? String(opts.variant) : undefined } })
  if (!isOk(up.body)) { console.log(`${algo} 上报失败: ${up.body?.msg}`); process.exit(1) }
}

// ★ 这条是 doc/kms-callsite-inventory.md §八已知风险「inspectNodeKeys() 恒返回
//   '无本地密钥'」的直接反转，KMS-003 的验收点之一：四把钥匙刚生成完，
//   本机就应当认得出来。若这里 present=false，说明 store 里记下的 ref 与
//   生成时返回的 ref 对不上 —— "这台设备有材料"与"新设备"就再也分不开。
const aKeys = await cryptoProvider.inspectNodeKeys(NODE_ID)
const aList = (aKeys.algorithms || []).map((a) => String(a).toUpperCase())
check('★ 本机认得刚生成的四套密钥（inspectNodeKeys 不再恒为空）',
  aKeys.present === true && ['SM2', 'SSCL', 'KYBER', 'FALCON'].every((a) => aList.includes(a)),
  `present=${aKeys.present} algorithms=${JSON.stringify(aKeys.algorithms)}`)

const fin = await api('/node-self/init/', { method: 'POST', token })
check('初始化完成', isOk(fin.body) && fin.body?.data?.node?.status === 'ACTIVE',
  `status=${fin.body?.data?.node?.status}`)

console.log('\n=== 2. 服务端记下了绑定设备 ===')
const bound = sql(`SELECT key_device_id FROM dvadmin_pqkds_nodes WHERE node_id='${NODE_ID}';`).trim()
check('★ 库里记录了绑定设备', bound === deviceA, `bound=${bound.slice(0, 12)}…`)

const self = await api('/node-self/', { token })
check('★ /node-self/ 下发 keyDeviceId（前端靠它判断）',
  self.body?.data?.node?.keyDeviceId === deviceA,
  `keyDeviceId=${String(self.body?.data?.node?.keyDeviceId).slice(0, 12)}…`)

console.log('\n=== 3. ★ 换设备上报必须被拒（这是本项的核心）===')
console.log('  [info] 清空本地密钥库，模拟"另一台设备"——它的 deviceId 与密钥库都是新的')
await store.clearAll()
const deviceB = await store.getDeviceId()
check('新设备拿到**不同**的 deviceId', deviceB && deviceB !== deviceA,
  `deviceB=${deviceB.slice(0, 12)}…`)

const bKeys = await cryptoProvider.inspectNodeKeys(NODE_ID)
check('★ 新设备本机没有任何该节点的密钥材料', bKeys.present === false, `algorithms=${JSON.stringify(bKeys.algorithms)}`)

const kpB = await cryptoProvider.generate('KYBER', { nodeId: NODE_ID, variant: 768 })
const rejected = await api('/node-self/keys/', { method: 'POST', token, body: {
  algorithm: 'KYBER', publicKey: kpB.publicKey, deviceId: deviceB } })
check('★★ 新设备上报公钥被拒', !isOk(rejected.body),
  `code=${rejected.body?.code} msg=${String(rejected.body?.msg || '').slice(0, 70)}`)
check('★ 拒绝理由是"设备不一致"（可处置），不是笼统的参数错',
  rejected.body?.code === 409 && /设备/.test(String(rejected.body?.msg || '')),
  `code=${rejected.body?.code}`)

console.log('\n=== 4. 同设备重试仍可通行（没有把正常路径一起挡掉）===')
const okSame = await api('/node-self/keys/', { method: 'POST', token, body: {
  algorithm: 'KYBER', publicKey: kpB.publicKey, deviceId: deviceA } })
check('★ 设备一致时正常登记（幂等重试不被误拦）', isOk(okSame.body), `${okSame.body?.msg || ''}`)

console.log('\n=== 5. 未上报 deviceId 时不做拦截（兼容旧调用方）===')
const noDev = await api('/node-self/keys/', { method: 'POST', token, body: {
  algorithm: 'SM2', publicKey: await (await cryptoProvider.generate('SM2', { nodeId: NODE_ID })).publicKey } })
check('不带 deviceId 时不因设备检查失败', isOk(noDev.body),
  `code=${noDev.body?.code} msg=${String(noDev.body?.msg || '').slice(0, 50)}`)

const pass = results.filter((r) => r.p).length
console.log(`\n=== 结果：${pass}/${results.length} 项通过 ===`)
if (pass !== results.length) { results.filter((r) => !r.p).forEach((r) => console.log(`  - ${r.n}  ${r.d}`)); process.exitCode = 1 }
