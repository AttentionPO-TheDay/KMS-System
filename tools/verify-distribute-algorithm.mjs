// =============================================================================
// verify-distribute-algorithm.mjs —— 验证「用户侧分发可选节点腿封装算法」
// -----------------------------------------------------------------------------
// 需求（2026-09-26）：抗量子应是**可选服务**，由用户决定这次分发给节点的封装算法，
// 而不是后端永远固定 Kyber。
//
// 本次改动：
//   * `wrap_for_node(payload_key, node, algorithm)` 补上 Falcon 分支 ——
//     **复用**既有 Falcon 池路径的配方（FalconAESSessionKeyEncryption），
//     节点侧解封路径不用改；
//   * `/key-pool/distribute-to-user/` 接受 `node_wrapping_algorithm`
//     （`kyber_kem` / `falcon_lattice`），非法值直接 400。
//
// 本脚本用接口层验证（避开界面细节）：
//   1) 用 Kyber 分发一次 → 节点信封 algorithm = kyber_kem
//   2) 用 Falcon 分发一次 → 节点信封 algorithm = falcon_lattice，且信封是 Falcon 形状
//   3) 传一个非法算法 → 被拒（400）
//   4) 让接收方节点没有 Falcon 公钥 → 该节点被如实标记为未送达，而不是整批假成功
//
// 用法：node tools/verify-distribute-algorithm.mjs [userId] [userName] [password] [keyId]
// =============================================================================
import { execSync } from 'node:child_process'
import { login } from './lib/captcha.mjs'

const USER_ID = Number(process.argv[2] || 2)
const USERNAME = process.argv[3] || 'yx'
const PASSWORD = process.argv[4] || 'admin123'
const KEY_ID = Number(process.argv[5] || 72)
const ORIGIN = 'http://127.0.0.1'

const results = []
function check(name, pass, detail = '') {
  results.push({ name, pass, detail })
  console.log(`${pass ? '  [PASS]' : '  [FAIL]'} ${name}${detail ? '  → ' + detail : ''}`)
}
const sql = (q) => execSync(`docker exec kms_mysql mysql -uroot -proot123456 -N -e "${q}" 2>nul`, { encoding: 'utf8' }).trim()

const token = await login(ORIGIN, '/lifecycle-api', USERNAME, PASSWORD)
const H = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }

async function distribute(body) {
  const r = await fetch(`${ORIGIN}/pqkds-api/key-pool/distribute-to-user/`, {
    method: 'POST', headers: H, body: JSON.stringify(body)
  })
  const json = await r.json().catch(() => null)
  return { status: r.status, json }
}

console.log('\n=== 0. 前置：节点授权与源密钥 ===')
const nodeRows = sql(`select n.id, n.node_id, char_length(ifnull(n.falcon_public_key,'')) from falcon_kds.dvadmin_pqkds_nodes n join falcon_kds.dvadmin_pqkds_user_node_authorizations a on a.node_id=n.id where a.user_id=${USER_ID} and a.status='active';`)
const nodes = nodeRows.split('\n').filter(Boolean).map((l) => {
  const [id, code, falconLen] = l.split('\t')
  return { id: Number(id), code, hasFalcon: Number(falconLen) > 0 }
})
console.log(`  可分发节点: ${JSON.stringify(nodes)}`)
check('该用户有已授权的节点', nodes.length > 0)
check('源密钥是有效的 SM2/SSCL', /SM2|SSCL/.test(sql(`select encryt_name from kms.keymanage where key_id=${KEY_ID} and status='0';`)))

console.log('\n=== 1. 用 Kyber 分发（默认算法）===')
const beforeKyber = sql(`select count(*) from falcon_kds.dvadmin_pqkds_pre_distributed_keys;`)
const kyber = await distribute({ source_key_id: KEY_ID, node_ids: [nodes[0].id], count: 1, node_wrapping_algorithm: 'kyber_kem' })
check('接口返回成功', kyber.status === 200 && kyber.json?.code === 200, JSON.stringify(kyber.json)?.slice(0, 140))
check('回显的节点腿算法是 kyber_kem', kyber.json?.data?.nodeWrappingAlgorithm === 'kyber_kem', String(kyber.json?.data?.nodeWrappingAlgorithm))
const kyberBatch = kyber.json?.data?.batchId || ''
const kyberAlgo = kyberBatch ? sql(`select distinct algorithm from falcon_kds.dvadmin_pqkds_pre_distributed_keys where pool_id='${kyberBatch}';`) : ''
check('库内该批次算法为 kyber_kem', kyberAlgo === 'kyber_kem', `实际=${kyberAlgo}`)
check('确实新增了行', Number(sql(`select count(*) from falcon_kds.dvadmin_pqkds_pre_distributed_keys;`)) > Number(beforeKyber))

console.log('\n=== 2. 用 Falcon 分发（本次新增能力）===')
const falconNode = nodes.find((n) => n.hasFalcon)
if (!falconNode) {
  check('存在具备 Falcon 公钥的接收方节点', false, '（本地节点都还没有 Falcon 公钥。新建节点会自动带上；若是历史节点，用节点管理页的「批量生成 Falcon」补）')
} else {
  const falcon = await distribute({ source_key_id: KEY_ID, node_ids: [falconNode.id], count: 1, node_wrapping_algorithm: 'falcon_lattice' })
  check('接口返回成功', falcon.status === 200 && falcon.json?.code === 200, JSON.stringify(falcon.json)?.slice(0, 160))
  check('回显的节点腿算法是 falcon_lattice', falcon.json?.data?.nodeWrappingAlgorithm === 'falcon_lattice', String(falcon.json?.data?.nodeWrappingAlgorithm))
  const falconBatch = falcon.json?.data?.batchId || ''
  const algo = falconBatch ? sql(`select distinct algorithm from falcon_kds.dvadmin_pqkds_pre_distributed_keys where pool_id='${falconBatch}';`) : ''
  check('库内该批次算法为 falcon_lattice', algo === 'falcon_lattice', `实际=${algo}`)
  // 信封里 ciphertext 有几千字符，前 400 字符全被它占满 —— 算法字段在尾部，取 right()
  const head = falconBatch
    ? sql(`select left(encrypted_key_data, 40) from falcon_kds.dvadmin_pqkds_pre_distributed_keys where pool_id='${falconBatch}' limit 1;`)
    : ''
  const tail = falconBatch
    ? sql(`select right(encrypted_key_data, 220) from falcon_kds.dvadmin_pqkds_pre_distributed_keys where pool_id='${falconBatch}' limit 1;`)
    : ''
  console.log(`  信封头: ${head}`)
  console.log(`  信封尾: ${tail}`)
  check('信封含 Falcon 密文（ciphertext）', /"ciphertext"/.test(head), head)
  check('信封尾部标出 Falcon 算法与 SM4 载荷',
    /Falcon/i.test(tail) && /SM4/i.test(tail) && /falcon_lattice/.test(tail), tail.slice(-90))
  check('该批次节点全部送达', (falcon.json?.data?.nodeResults || []).every((r) => r.delivered), JSON.stringify(falcon.json?.data?.nodeResults))
}

console.log('\n=== 3. 非法算法应被拒 ===')
const bad = await distribute({ source_key_id: KEY_ID, node_ids: [nodes[0].id], count: 1, node_wrapping_algorithm: 'sm2_gm' })
check('非法算法被拒（400）', bad.status === 400, `HTTP ${bad.status} ${JSON.stringify(bad.json)?.slice(0, 120)}`)

console.log('\n=== 3b. 国密节点腿（gm_sm2 / gm_sscl）===')
for (const algo of ['gm_sm2', 'gm_sscl']) {
  const r = await distribute({ source_key_id: KEY_ID, node_ids: [nodes[0].id], count: 1, node_wrapping_algorithm: algo })
  const ok = r.status === 200 && r.json?.code === 200
  check(`${algo} 分发成功`, ok, JSON.stringify(r.json)?.slice(0, 150))
  if (!ok) continue
  const batch = r.json?.data?.batchId || ''
  const stored = sql(`select distinct algorithm from falcon_kds.dvadmin_pqkds_pre_distributed_keys where pool_id='${batch}';`)
  check(`${algo} 库内批次算法一致`, stored === algo, `实际=${stored}`)
  // 国密信封由 SM2 原语生成：algorithm 字段必须是 'sm2'（SM2Crypto.decrypt 会校验它），
  // 用哪种国密体系由 wrapping_algorithm 表达
  const head = sql(`select left(encrypted_key_data, 60) from falcon_kds.dvadmin_pqkds_pre_distributed_keys where pool_id='${batch}' limit 1;`)
  console.log(`  ${algo} 信封: ${head}`)
  check(`${algo} 信封是 SM2 公钥加密形状`, /"ciphertext"|"C1"|"c1"/.test(head) || head.startsWith('{'), head.slice(0, 60))
  check(`${algo} 节点全部送达`, (r.json?.data?.nodeResults || []).every((x) => x.delivered), JSON.stringify(r.json?.data?.nodeResults))
}

console.log('\n=== 4. 接收方没有 Falcon 公钥时如实报告 ===')
const noFalcon = nodes.find((n) => !n.hasFalcon)
if (!noFalcon) {
  console.log('  （跳过：本地每个已授权节点都有 Falcon 公钥）')
} else {
  const r = await distribute({ source_key_id: KEY_ID, node_ids: [noFalcon.id], count: 1, node_wrapping_algorithm: 'falcon_lattice' })
  const results_ = r.json?.data?.nodeResults || []
  console.log(`  nodeResults: ${JSON.stringify(results_)}  failed: ${JSON.stringify(r.json?.data?.failed)}`)
  check('未送达的节点被如实标记（不谎报成功）',
    r.status === 200 && results_.some((x) => !x.delivered) &&
    (r.json?.data?.failed || []).some((f) => /Falcon/.test(f)),
    JSON.stringify(r.json?.data?.failed)?.slice(0, 120))
}

const pass = results.filter((r) => r.pass).length
console.log(`\n=== 结果：${pass}/${results.length} 通过 ===`)
if (pass !== results.length) {
  console.log('未通过项：')
  results.filter((r) => !r.pass).forEach((r) => console.log(`  - ${r.name}  ${r.detail}`))
  process.exitCode = 1
}
