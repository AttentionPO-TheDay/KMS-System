/**
 * 验证「节点初始化页」这条**界面路径**真的能走通。
 *
 * 为什么单独做这一条
 * ------------------
 * §4.4 的密钥生成能力是脚本验证过的，但当时 **UI 一行没改** ——
 * 页面上点"开始初始化"会直接失败（服务端只说"公钥尚未登记"），
 * 而页面不会告诉你为什么。脚本验证通过 ≠ 用户点得到。
 *
 * 所以这里不测底层能力，只测「页面里那几个函数的调用顺序能不能跑通」：
 *     cryptoProvider.generate（本机生成）
 *   → registerSelfNodePublicKey（只上传公钥）
 *   → initSelfNodeKeys（收尾）
 */
import 'fake-indexeddb/auto'

const ORIGIN = 'http://127.0.0.1'
const PQKDS = `${ORIGIN}/pqkds-api/pqkds`
const results = []
const check = (n, p, d = '') => { results.push({ n, p, d }); console.log(`  ${p ? '[PASS]' : '[FAIL]'} ${n}${d ? '  → ' + d : ''}`) }

const { cryptoProvider } = await import('../src/utils/crypto/browser-provider.js')
const { login } = await import('../../../tools/lib/captcha.mjs')

const api = async (base, p, { method = 'GET', token, body } = {}) => {
  const r = await fetch(`${base}${p}`, { method, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}) }, ...(body ? { body: JSON.stringify(body) } : {}) })
  return { status: r.status, body: await r.json().catch(() => null) }
}
const isOk = (b) => b?.code === 200 || b?.code === 2000

const SEED = Date.now()
const NODE_ID = `NUI-${SEED.toString(36).toUpperCase().slice(-6)}`

console.log('\n=== 1. 建节点（管理员侧不变）===')
const admin = await login(ORIGIN, '/updatedel-api', 'admin', 'admin123')
const created = await api(PQKDS, '/nodes/register/', { method: 'POST', token: admin, body: {
  node_id: NODE_ID, name: NODE_ID, ip_address: `10.77.${(SEED % 200) + 1}.1`, port: 61000 + (SEED % 10000),
  node_type: 'full', permission_level: 'L2', domain_id: 'dui' } })
check('建节点成功', isOk(created.body), `code=${created.body?.code}`)
if (!isOk(created.body)) process.exit(1)

const nodeToken = await login(ORIGIN, '/updatedel-api', NODE_ID, 'admin123')

console.log('\n=== 2. ★ 按 nodeInit 页的顺序走：本机生成 → 上报公钥 → 收尾 ===')
// 与页面里的 KEY_META 顺序一致（Falcon 放最后，它最慢）
const ALGOS = [['SM2', {}], ['SSCL', {}], ['KYBER', { variant: 768 }], ['FALCON', {}]]
const t0 = Date.now()
for (const [algo, opts] of ALGOS) {
  const tGen = Date.now()
  const keyRef = `node-${NODE_ID}-${algo}`
  const generated = await cryptoProvider.generate(algo, { keyRef, ...opts })
  const genMs = Date.now() - tGen
  check(`${algo} 本机生成`, Boolean(generated?.publicKey), `${generated.publicKey.length} hex 字符，耗时 ${genMs}ms`)

  const up = await api(PQKDS, '/node-self/keys/', { method: 'POST', token: nodeToken, body: {
    algorithm: algo, publicKey: generated.publicKey,
    securityLevel: algo === 'KYBER' ? '768' : undefined } })
  check(`${algo} 公钥上报`, isOk(up.body), `${up.body?.msg || ''}`)
}
const totalMs = Date.now() - t0
console.log(`  [info] 四套生成+上报总耗时 ${totalMs}ms（页面文案写的是"约 2~5 秒"，需与实测相符）`)

const fin = await api(PQKDS, '/node-self/init/', { method: 'POST', token: nodeToken })
check('收尾成功', isOk(fin.body), `${fin.body?.msg || ''}`)
check('节点进入 ACTIVE', fin.body?.data?.node?.status === 'ACTIVE', `status=${fin.body?.data?.node?.status}`)

console.log('\n=== 3. 页面依赖的字段都在 ===')
const self = await api(PQKDS, '/node-self/', { token: nodeToken })
const n = self.body?.data?.node
check('/node-self/ 返回 node.keys（页面用它显示四套就绪状态）',
  n?.keys && ['kyber', 'falcon', 'sm2', 'sscl'].every((k) => n.keys[k] === true),
  JSON.stringify(n?.keys))
check('返回 status 供页面判断 isActive', n?.status === 'ACTIVE', `status=${n?.status}`)

console.log('\n=== 4. 幂等：重复点初始化不该出错 ===')
const again = await api(PQKDS, '/node-self/init/', { method: 'POST', token: nodeToken })
check('重复初始化被幂等处理', isOk(again.body) && again.body?.data?.alreadyInitialized === true,
  `alreadyInitialized=${again.body?.data?.alreadyInitialized}`)

const pass = results.filter((r) => r.p).length
console.log(`\n=== 结果：${pass}/${results.length} 项通过 ===`)
if (pass !== results.length) { results.filter((r) => !r.p).forEach((r) => console.log(`  - ${r.n}  ${r.d}`)); process.exitCode = 1 }
