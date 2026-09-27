// =============================================================================
// verify-node-batch-falcon.mjs —— 验证「批量生成 Falcon」与**单节点失败隔离**
// -----------------------------------------------------------------------------
// 背景（2026-09-26）：Falcon 改为注册时自动生成后，失败只记日志、不阻断注册，
// 于是需要一个补生成的入口。节点管理页新增了「批量生成 Falcon」按钮。
//
// 本脚本验证三件事（都是"能显示"之外的真实行为）：
//   1) 缺 Falcon 的节点，按钮会带上正确计数，点击后有确认框（讲明数量与耗时）；
//   2) 批量生成**真的补齐**了公钥（落库可查），列表随之变为"已就绪"；
//   3) 其中一个节点生成失败时，**整批不中断** —— 失败行标红、其余照常成功。
//
// 失败注入方式：把某行的 falcon_security_level 改成 'abc'。
//   服务端 `int(getattr(node,'falcon_security_level','512') or '512')` 会抛
//   ValueError，被 generate_falcon_keys_v2 的 try 捕获并返回 success=False，
//   接口回错误 —— 正好是"单个节点失败"的真实场景。
//
// 用法：node tools/verify-node-batch-falcon.mjs [--port 9222]
// =============================================================================
import { login } from './lib/captcha.mjs'
import { sql, sqlScalar, dockerBin } from './lib/mysql.mjs'

const argv = process.argv.slice(2)
const arg = (n, d) => { const i = argv.indexOf(`--${n}`); return i >= 0 ? argv[i + 1] : d }
const PORT = arg('port', '9222')
const ORIGIN = 'http://127.0.0.1'
const STAMP = Date.now().toString().slice(-6)

const GOOD_A = `BATCH-GOOD-A-${STAMP}`
const GOOD_B = `BATCH-GOOD-B-${STAMP}`
const BAD = `BATCH-BAD-${STAMP}`
const ALL = [GOOD_A, GOOD_B, BAD]

const results = []
function check(name, pass, detail = '') {
  results.push({ name, pass, detail })
  console.log(`${pass ? '  [PASS]' : '  [FAIL]'} ${name}${detail ? '  → ' + detail : ''}`)
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// SQL 走 lib/mysql.mjs：它用 docker 绝对路径调用（Node 在 Windows 上走 cmd.exe，
// PATH 里没有 docker），且不吞 stderr —— 这两点都是踩过的坑，详见该文件顶部。
const base = `http://127.0.0.1:${PORT}`
const list = await (await fetch(`${base}/json/list`)).json()
let target = list.find((t) => t.type === 'page')
if (!target) target = await (await fetch(`${base}/json/new?about:blank`)).json()
const ws = new WebSocket(target.webSocketDebuggerUrl)
let id = 0
const pending = new Map()
ws.addEventListener('message', (evt) => {
  const m = JSON.parse(evt.data)
  if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.reject(new Error(JSON.stringify(m.error))) : p.resolve(m.result) }
})
const send = (method, params = {}) => new Promise((resolve, reject) => { const i = ++id; pending.set(i, { resolve, reject }); ws.send(JSON.stringify({ id: i, method, params })) })
const ev = async (e) => { const r = await send('Runtime.evaluate', { expression: e, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error('JS异常: ' + r.exceptionDetails.exception?.description); return r.result.value }

/** 读某行三列状态 */
const rowState = (nodeId) => ev(`(() => {
  const tr = [...document.querySelectorAll('.el-table__body tbody tr')].find(t => t.innerText.includes(${JSON.stringify(nodeId)}))
  if (!tr) return null
  const headers = [...document.querySelectorAll('.el-table__header th')].map(th => th.innerText.trim())
  const tds = [...tr.querySelectorAll('td')]
  return { falcon: tds[headers.indexOf('Falcon 密钥')]?.innerText.trim() }
})()`)

try {
  await new Promise((res) => ws.addEventListener('open', res, { once: true }))
  await send('Page.enable'); await send('Runtime.enable')

  const token = await login(ORIGIN, '/updatedel-api', 'admin', 'admin123')
  const H = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }

  // ---------------------------------------------------------- 造 3 个缺 Falcon 的节点
  console.log('\n=== 0. 准备：新建 3 个节点（自动带 Falcon），再把 Falcon 清掉 ===')
  for (const [i, nid] of ALL.entries()) {
    const r = await fetch(`${ORIGIN}/pqkds-api/nodes/register/`, {
      method: 'POST', headers: H,
      body: JSON.stringify({ node_id: nid, name: `批量Falcon验证${i}`, ip_address: `127.0.0.${160 + i}`, port: 9300 + i })
    })
    const j = await r.json().catch(() => null)
    check(`节点 ${nid} 已创建（含自动 Falcon）`, j?.code === 2000, j?.msg)
  }
  // 清掉 Falcon 公/私钥，模拟"历史节点还没来得及补"的状态
  sql(`UPDATE falcon_kds.dvadmin_pqkds_nodes SET falcon_public_key='', falcon_private_key='' WHERE node_id IN ('${GOOD_A}','${GOOD_B}','${BAD}');`)
  // 失败注入：第三个节点安全级别非法，服务端 int() 会抛错
  sql(`UPDATE falcon_kds.dvadmin_pqkds_nodes SET falcon_security_level='abc' WHERE node_id='${BAD}';`)
  const cleared = sql(`SELECT COUNT(*) FROM falcon_kds.dvadmin_pqkds_nodes WHERE node_id IN ('${GOOD_A}','${GOOD_B}','${BAD}') AND falcon_public_key='';`)
  check('3 个节点已处于「缺 Falcon」状态', cleared === '3', `clear=${cleared}`)

  // ---------------------------------------------------------- 进页面
  await send('Page.navigate', { url: `${ORIGIN}/updatedel/` })
  await sleep(2500)
  await ev(`document.cookie = 'Admin-Token=${token}; path=/'`)
  await send('Page.navigate', { url: `${ORIGIN}/updatedel/distchain/nodes` })
  let ok = false
  for (let i = 0; i < 40 && !ok; i++) { ok = await ev(`document.querySelectorAll('.el-table__body tbody tr').length > 0`); if (!ok) await sleep(500) }
  check('节点管理页已渲染', ok)

  // ---------------------------------------------------------- 按钮计数
  console.log('\n=== 1. 批量按钮的计数与确认框 ===')
  const btnText = await ev(`(() => {
    const b = [...document.querySelectorAll('button')].find(x => x.innerText.includes('批量生成 Falcon'))
    return b ? b.innerText.replace(/\\s+/g, ' ').trim() : null
  })()`)
  console.log(`  按钮文案: ${btnText}`)
  check('按钮显示缺失数量', /\d+/.test(btnText || ''), btnText)

  const before = await rowState(BAD)
  check('失败注入行的 Falcon 显示未生成', /未生成/.test(before?.falcon || ''), before?.falcon)

  // ---------------------------------------------------------- 执行批量
  console.log('\n=== 2. 点击批量生成 ===')
  check('点击按钮', (await ev(`(() => {
    const b = [...document.querySelectorAll('button')].find(x => x.innerText.includes('批量生成 Falcon'))
    if (b) { b.click(); return true } return false
  })()`)) === true)
  await sleep(1200)
  const boxText = await ev(`(() => {
    const b = [...document.querySelectorAll('.el-message-box')][0]
    return b ? b.innerText.replace(/\\s+/g, ' ').trim() : null
  })()`)
  console.log(`  确认框: ${boxText}`)
  check('确认框讲明了数量与耗时', /3\s*个节点/.test(boxText || '') && /分钟|十几秒/.test(boxText || ''), boxText?.slice(0, 90))
  check('确认框有「开始生成」', /开始生成/.test(boxText || ''))
  check('确认继续', (await ev(`(() => {
    const b = [...document.querySelectorAll('.el-message-box')][0]
    const btn = b && [...b.querySelectorAll('button')].find(x => /开始生成|确定/.test(x.innerText))
    if (btn) { btn.click(); return true } return false
  })()`)) === true)

  // 运行中：按钮应变为"生成中 n/m"且不可再点
  await sleep(3000)
  const runningText = await ev(`(() => {
    const b = [...document.querySelectorAll('button')].find(x => /生成中|批量生成 Falcon/.test(x.innerText))
    return b ? { text: b.innerText.replace(/\\s+/g, ' ').trim(), disabled: b.disabled } : null
  })()`)
  console.log(`  运行中按钮: ${JSON.stringify(runningText)}`)
  check('运行中按钮显示进度且被禁用', /生成中/.test(runningText?.text || '') && runningText?.disabled === true, JSON.stringify(runningText))

  // ---------------------------------------------------------- 等结果
  // 2 个成功 × 约 20s + 1 个快速失败
  console.log('\n=== 3. 等待整批结束 ===')
  let goodA = null, goodB = null, badRow = null
  for (let i = 0; i < 180; i++) {
    goodA = await rowState(GOOD_A); goodB = await rowState(GOOD_B); badRow = await rowState(BAD)
    const doneA = /已就绪/.test(goodA?.falcon || '')
    const doneB = /已就绪/.test(goodB?.falcon || '')
    const badDone = /生成失败/.test(badRow?.falcon || '')
    if (doneA && doneB && badDone) break
    await sleep(2000)
  }
  console.log(`  ${GOOD_A}: ${JSON.stringify(goodA)}`)
  console.log(`  ${GOOD_B}: ${JSON.stringify(goodB)}`)
  console.log(`  ${BAD}: ${JSON.stringify(badRow)}`)

  check('节点 A 生成成功并显示已就绪', /已就绪/.test(goodA?.falcon || ''), goodA?.falcon)
  check('节点 B 生成成功并显示已就绪', /已就绪/.test(goodB?.falcon || ''), goodB?.falcon)
  check('失败节点如实标为「生成失败」（整批未中断）', /生成失败/.test(badRow?.falcon || ''), badRow?.falcon)

  // ---------------------------------------------------------- 落库核对
  console.log('\n=== 4. 落库核对 ===')
  const dbA = sql(`SELECT CHAR_LENGTH(COALESCE(falcon_public_key,'')) FROM falcon_kds.dvadmin_pqkds_nodes WHERE node_id='${GOOD_A}';`)
  const dbB = sql(`SELECT CHAR_LENGTH(COALESCE(falcon_public_key,'')) FROM falcon_kds.dvadmin_pqkds_nodes WHERE node_id='${GOOD_B}';`)
  const dbBad = sql(`SELECT CHAR_LENGTH(COALESCE(falcon_public_key,'')) FROM falcon_kds.dvadmin_pqkds_nodes WHERE node_id='${BAD}';`)
  check('节点 A 的 Falcon 公钥确实落库', Number(dbA) > 100000, `${dbA} 字符`)
  check('节点 B 的 Falcon 公钥确实落库', Number(dbB) > 100000, `${dbB} 字符`)
  check('失败节点未写入 Falcon 公钥', Number(dbBad) === 0, `${dbBad} 字符`)

  // 停写 falcon_lattice_params 的回归断言：新生成的这批也不该写它
  const lattice = sql(`SELECT CHAR_LENGTH(COALESCE(falcon_lattice_params,'')) FROM falcon_kds.dvadmin_pqkds_nodes WHERE node_id='${GOOD_A}';`)
  check('未再写入 falcon_lattice_params（10.2MB 死字段）', Number(lattice) === 0, `${lattice} 字符`)

  // ---------------------------------------------------------- 收尾提示
  const endMsg = await ev(`(document.body.innerText || '').replace(/\\s+/g, ' ')`)
  check('结束时如实报告成功/失败数量', /成功\s*2|失败\s*1/.test(endMsg), (endMsg.match(/批量生成结束[^。]*。/) || [''])[0])
} catch (error) {
  check('脚本执行', false, error.message)
} finally {
  // ---------------------------------------------------------- 清理
  console.log('\n=== 5. 清理测试节点 ===')
  try {
    for (const nid of ALL) {
      // 用 sqlScalar：查不到返回 null，避免把空串当成功（`if (row)` 对空串为假，
      // 会让清理**静默跳过**，节点留在演示数据里）
      const row = sqlScalar(`SELECT id FROM falcon_kds.dvadmin_pqkds_nodes WHERE node_id='${nid}';`)
      if (row) {
        await fetch(`${ORIGIN}/pqkds-api/nodes/${row}/`, { method: 'DELETE' }).catch(() => {})
      }
    }
    const left = sqlScalar(`SELECT COUNT(*) FROM falcon_kds.dvadmin_pqkds_nodes WHERE node_id LIKE 'BATCH-%-${STAMP}';`)
    check('测试节点已清理', left === '0', `剩余 ${left}`)
  } catch (e) { check('测试节点已清理', false, e.message) }

  const pass = results.filter((r) => r.pass).length
  console.log(`\n=== 结果：${pass}/${results.length} 通过 ===`)
  if (pass !== results.length) {
    console.log('未通过项：')
    results.filter((r) => !r.pass).forEach((r) => console.log(`  - ${r.name}  ${r.detail}`))
    process.exitCode = 1
  }
  try { ws.close() } catch {}
}
