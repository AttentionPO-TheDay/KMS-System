/**
 * KMS-017 验收：`GET /distribution-batches/`（我的分发批次）的**读路径**。
 *
 * 为什么判据是这些，而不是"接口返回 200"
 * ----------------------------------------
 * 这条读路径上曾经同时躺着两个缺陷，且**都只在"有数据"时才现形**：
 *
 *   * 后端：`distribution_batches` 一直在调一个**从未定义过**的 `_safe(...)`
 *     （KMS-017 修）。0 条批次时循环体不执行 → 200 空列表，一切正常；
 *     **≥1 条批次**就 NameError → 500。所以"空账号"与"有批次账号"两态
 *     都必须断言 —— 只测空账号的脚本会全绿，而它什么都不证明。
 *     库中 0 条批次正是这个缺陷长期不可见的全部原因。
 *   * 前端：crossDomain 页只认裸数组 / DRF 分页的 `results`，读不出
 *     `{items,total}`（KMS-017 修）。它失败的样子是**表格空着且控制台干净**
 *     —— 脚本若不打开真浏览器就永远看不见：产物里有字符串 ≠ 页面渲染了它们。
 *
 * 判据的分工：
 *   1. 部署探针（无令牌 → 401）：路由在不在**跑着的进程**里（代码打进镜像，
 *      不重建 = 白跑）；
 *   2. 空账号态：0 条批次必须是 200 + 空数组（护栏：不许回归成 500）；
 *   3. 种三条批次 + 两条会话后按 HTTP 断言：items/total/sessionCount
 *      与**库中 LIKE 计数**逐一对齐（0 与 2 两态各一条，0 是有效值）；
 *   4. 真浏览器打开 `/updatedel/distgov/crossdom`：统计卡数字与表格行数
 *      必须由**接口数据**渲染出来，且渲染的是本脚本种的批次号。
 *
 * ⚠️ 会建真数据（两个节点 + 三条批次 + 两条会话，均打 TAG 前缀），
 *    结尾自建自清。只在本地验证环境跑。
 * ⚠️ userId 取**自省结果**（与后端 `require_kms_user` 同一条路），不猜表结构：
 *    DistributionBatch.user_id 是按它过滤的，取错人的话列表会是空的。
 */
import { spawn, execFileSync } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import {
  ORIGIN,
  PQKDS,
  api,
  isOk,
  title,
  makeReporter,
  adminLogin
} from './lib/node-session.mjs'
import { sqlScalar, dockerBin } from '../../../tools/lib/mysql.mjs'

const { check, info, finish } = makeReporter()

const TAG = `kms017-${Date.now().toString(36)}`
const BATCH_TABLE = 'falcon_kds.dvadmin_pqkds_distribution_batches'
const SESSION_TABLE = 'falcon_kds.dvadmin_pqkds_session_keys'

const adminToken = await adminLogin()

/** 在 Django 容器里跑一段程序（种子/清理共用），返回 stdout。 */
function runInDjango(program) {
  return execFileSync(dockerBin, ['exec', '-i', '-w', '/backend', 'dvadmin3-django', 'python', '-'], {
    input: program, encoding: 'utf8', env: { ...process.env, MSYS_NO_PATHCONV: '1' }
  })
}

// ---------------------------------------------------------------------------
// 1. ★ 部署探针：路由在跑着的进程里
// ---------------------------------------------------------------------------
title('1. ★ 部署探针：/distribution-batches/ 已注册（不是 404/405）')
const noToken = await api(PQKDS, '/distribution-batches/')
check('★ 无令牌 → 401（`require_kms_user` 先于视图拦下；404/405 说明镜像没重建）',
  noToken.status === 401, `HTTP=${noToken.status} body=${JSON.stringify(noToken.body).slice(0, 120)}`)
if (noToken.status === 404 || noToken.status === 405) {
  info('路由没注册：后面的用例一条都不跑 —— 先重建 dvadmin3-django 镜像，再重跑。')
  finish()
  process.exit(1)
}

// ---------------------------------------------------------------------------
// 2. 空账号态（先于种数据）：0 条批次 = 200 + 空数组，不是 500
// ---------------------------------------------------------------------------
title('2. 空账号态：0 条批次必须是 200 空列表（修前这里是 200；防的是回归成 500）')
const adminUserId = Number(sqlScalar("SELECT user_id FROM kms.sys_user WHERE user_name='admin' LIMIT 1"))
check('admin 的 userId 从 kms.sys_user 读到', Number.isInteger(adminUserId) && adminUserId > 0, `userId=${adminUserId}`)

const preCount = Number(sqlScalar(
  `SELECT COUNT(*) FROM ${BATCH_TABLE} WHERE user_id=${adminUserId}`) || 0)
if (preCount === 0) {
  const empty = await api(PQKDS, '/distribution-batches/', { token: adminToken })
  check('★ 0 条批次：HTTP 200 且 items 为空数组（不是 500、不是 null）',
    empty.status === 200 && isOk(empty.body)
    && Array.isArray(empty.body?.data?.items) && empty.body.data.items.length === 0,
    `HTTP=${empty.status} items=${JSON.stringify(empty.body?.data?.items)?.slice(0, 80)}`)
} else {
  info(`该账号库中已有 ${preCount} 条批次，空态断言不适用，跳过（不是失败）`)
}

// ---------------------------------------------------------------------------
// 3. 种数据：两个节点 + 三条批次（跨/同/混合）+ 两条会话
// ---------------------------------------------------------------------------
title('3. 种数据（两个节点 + 三条批次 + 两条会话，全打 TAG）')
const seedProgram = `
import os, sys, json
sys.path.insert(0, '/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
import django
django.setup()
from datetime import timedelta
from django.utils import timezone
from pqkds.models import Node, DistributionBatch, SessionKey
from pqkds import kms_service_client as kms

TAG = ${JSON.stringify(TAG)}
uid = kms.introspect(${JSON.stringify(adminToken)})['userId']

n1 = Node.objects.create(node_id=TAG + '-n1', name=TAG + ' 节点一',
                         ip_address='10.233.17.1', port=62171)
n2 = Node.objects.create(node_id=TAG + '-n2', name=TAG + ' 节点二',
                         ip_address='10.233.17.2', port=62172)

dom_a = TAG + '-dom-a'
dom_b = TAG + '-dom-b'

b_cross = DistributionBatch.objects.create(
    batch_id=TAG + '-cross', user_id=uid, wrapping_algorithm='SM2',
    node_ids=json.dumps([n1.id, n2.id]), node_success_count=1,
    user_envelope_ok=True, status='partial',
    source_domain_id=dom_a, target_domain_ids=json.dumps([dom_b]),
    distribution_type='cross')
b_same = DistributionBatch.objects.create(
    batch_id=TAG + '-same', user_id=uid, wrapping_algorithm='SSCL',
    node_ids=json.dumps([n1.id]), node_success_count=1,
    user_envelope_ok=True, status='success',
    source_domain_id=dom_a, target_domain_ids=json.dumps([dom_a]),
    distribution_type='same')
b_cross2 = DistributionBatch.objects.create(
    batch_id=TAG + '-cross2', user_id=uid, wrapping_algorithm='SM2',
    node_ids=json.dumps([n1.id, n2.id]), node_success_count=0,
    user_envelope_ok=False, status='failed',
    source_domain_id=dom_a, target_domain_ids=json.dumps([dom_b, dom_a]),
    distribution_type='mixed')

now = timezone.now()
for i in (1, 2):
    SessionKey.objects.create(
        session_id=b_cross.batch_id + '-n%d' % i, node1=n1, node2=n2,
        encrypted_session_key='KMS-017 种子（非真实密文，仅计数用）',
        key_exchange_data='{}', session_type='gm_sm2', status='initiated',
        expires_at=now + timedelta(hours=2))

print('KMS017_SEED=' + json.dumps({
    'userId': uid, 'cross': b_cross.batch_id, 'same': b_same.batch_id,
    'cross2': b_cross2.batch_id, 'domA': dom_a, 'domB': dom_b,
}, ensure_ascii=False))
`
let seed = null
let seedRaw = ''
try {
  seedRaw = runInDjango(seedProgram)
  const line = seedRaw.split('\n').find((l) => l.startsWith('KMS017_SEED='))
  seed = JSON.parse(line.slice('KMS017_SEED='.length))
} catch (error) {
  info(String(error?.stderr || error?.message || error).slice(0, 600))
}
check('种子数据写入成功（拿到批次号）', Boolean(seed?.cross), seed ? `cross=${seed.cross}` : seedRaw.slice(-300))

// 自省 userId 与表里读到的 admin userId 必须一致 —— 否则批次种在了别人名下，
// 接口按令牌过滤时会"查无此批"，而报错看起来像接口坏了。
check('自省 userId == kms.sys_user 里 admin 的 user_id（种对人）',
  seed?.userId === adminUserId, `introspect=${seed?.userId} table=${adminUserId}`)

// ---------------------------------------------------------------------------
// 4. HTTP 断言：items / total / sessionCount 与库逐一对齐
// ---------------------------------------------------------------------------
title('4. HTTP：有批次 → 200，items/total 与库一致，sessionCount 0 与 2 两态')
const res = await api(PQKDS, '/distribution-batches/', { token: adminToken })
check('★ 有批次：HTTP 200（修前这里 NameError → 500）',
  res.status === 200 && isOk(res.body), `HTTP=${res.status} code=${res.body?.code}`)

const items = res.body?.data?.items
check('items 是数组，total == len(items)',
  Array.isArray(items) && res.body?.data?.total === items.length,
  `total=${res.body?.data?.total} len=${Array.isArray(items) ? items.length : 'n/a'}`)

const dbCount = Number(sqlScalar(`SELECT COUNT(*) FROM ${BATCH_TABLE} WHERE user_id=${adminUserId}`) || 0)
check('★ 列表条数 == 库中该用户的批次条数（接口不是读的别人的行）',
  items?.length === dbCount, `api=${items?.length} db=${dbCount}`)

const byId = Object.fromEntries((items || []).map((b) => [b.batchId, b]))
const A = byId[seed?.cross]
const B = byId[seed?.same]
const C = byId[seed?.cross2]
check('三条种子批次都在列表里', Boolean(A && B && C),
  `cross=${Boolean(A)} same=${Boolean(B)} cross2=${Boolean(C)}`)

const dbSessA = Number(sqlScalar(
  `SELECT COUNT(*) FROM ${SESSION_TABLE} WHERE session_id LIKE '${seed?.cross}-%'`) || 0)
check('★ sessionCount 与库中 LIKE 计数一致（跨域批 = 2 条会话）',
  A?.sessionCount === 2 && dbSessA === 2, `api=${A?.sessionCount} db=${dbSessA}`)
check('★ 0 条会话的批次：sessionCount 是 0 而不是 null（0 是有效值，不得混成"没统计到"）',
  B?.sessionCount === 0, `api=${JSON.stringify(B?.sessionCount)}`)

check('字段完整且取值如实：封装算法 / 状态 / 节点成功数 / 用户信封 / 域字段',
  A?.wrappingAlgorithm === 'SM2' && A?.status === 'partial' && A?.nodeSuccessCount === 1
  && A?.userEnvelopeOk === true && A?.sourceDomainId === seed?.domA
  && Array.isArray(A?.targetDomainIds) && A.targetDomainIds.join() === seed?.domB
  && A?.distributionType === 'cross',
  JSON.stringify(A).slice(0, 240))
check('失败批次如实：nodeSuccessCount=0 且 userEnvelopeOk=false（不是被粉饰）',
  C?.nodeSuccessCount === 0 && C?.userEnvelopeOk === false,
  JSON.stringify(C).slice(0, 200))

// ---------------------------------------------------------------------------
// 5. 真浏览器：跨域分发页渲染行与统计卡
// ---------------------------------------------------------------------------
title('5. 真浏览器：/updatedel/distgov/crossdom 的统计卡与表格')
const CHROME = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
].find(existsSync)
if (!CHROME) { console.log('找不到浏览器'); process.exit(1) }

const PORT = 9227
const dir = mkdtempSync(join(tmpdir(), 'kms017-cdp-'))
const proc = spawn(CHROME, [
  `--remote-debugging-port=${PORT}`, `--user-data-dir=${dir}`,
  '--headless=new', '--no-first-run', '--window-size=1680,1000', 'about:blank'
], { stdio: 'ignore' })

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

let sock = null
try {
  let ws = null
  for (let i = 0; i < 40; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/json/list`)
      const tabs = await r.json()
      const page = tabs.find((t) => t.type === 'page')
      if (page?.webSocketDebuggerUrl) { ws = page.webSocketDebuggerUrl; break }
    } catch { /* 还没起来 */ }
    await sleep(250)
  }
  if (!ws) throw new Error('CDP 未就绪')

  sock = new WebSocket(ws)
  let id = 0
  const pending = new Map()
  sock.addEventListener('message', (ev) => {
    const msg = JSON.parse(ev.data)
    if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id) }
  })
  await new Promise((res2) => sock.addEventListener('open', res2, { once: true }))
  const send = (method, params = {}) => new Promise((resolve) => {
    const myId = ++id
    pending.set(myId, resolve)
    sock.send(JSON.stringify({ id: myId, method, params }))
  })
  const evalText = async (expression) => {
    const r = await send('Runtime.evaluate', { expression, returnByValue: true })
    return r?.result?.result?.value
  }

  await send('Page.enable')
  await send('Runtime.enable')
  await send('Page.navigate', { url: `${ORIGIN}/updatedel/` })
  await sleep(2500)
  await send('Runtime.evaluate', {
    expression: `document.cookie = 'Admin-Token=' + ${JSON.stringify(adminToken)} + ';path=/'`
  })
  // 真实 URL = 目录菜单 9460 `distgov` + 子菜单 9453 `crossdom`
  // （只写 /crossdom 会落到 404 兜底页，看起来像"页面没了"）。
  await send('Page.navigate', { url: `${ORIGIN}/updatedel/distgov/crossdom` })
  await sleep(7000)

  const body = String(await evalText('document.body.innerText'))
  check('页面已渲染（不是登录页/404 兜底）',
    body.includes('跨域分发') && !body.includes('登 录') && !body.includes('找不到网页'),
    body.replace(/\s+/g, ' ').slice(0, 120))

  // 页面默认视图是「仅跨域」：行数应等于接口数据里跨域批次数。
  const crossExpected = (items || []).filter((b) => String(b.sourceDomainId || '')
    && (b.targetDomainIds || []).some((d) => d !== b.sourceDomainId)).length
  const rowCount = Number(await evalText(`document.querySelectorAll('.el-table__row').length`))
  check('★ 表格行数 == 接口数据里的跨域批次数（修前这里是 0：静默空表）',
    rowCount === crossExpected && rowCount >= 2, `rows=${rowCount} expected=${crossExpected}`)

  const stats = JSON.parse(String(await evalText(
    `JSON.stringify([...document.querySelectorAll('.stat')].map((el) => [`
    + `el.querySelector('.k') ? el.querySelector('.k').innerText.trim() : '', `
    + `el.querySelector('.v') ? el.querySelector('.v').innerText.trim() : '']))`)) || '[]')
  const statMap = Object.fromEntries(stats)
  check('★ 统计卡「分发批次」== 接口 items 总数（数字来自真实数据，不是硬编码）',
    statMap['分发批次'] === String(items?.length), `卡=${statMap['分发批次']} api=${items?.length}`)
  check('★ 统计卡「跨域」== 接口数据计算的跨域数',
    statMap['跨域'] === String(crossExpected), `卡=${statMap['跨域']} expected=${crossExpected}`)

  const tableText = String(await evalText(
    `[...document.querySelectorAll('.el-table__row')].map((r) => r.innerText).join(' | ')`))
  check('★ 表格渲染出本脚本种的两条跨域批次号',
    tableText.includes(seed?.cross) && tableText.includes(seed?.cross2),
    tableText.replace(/\s+/g, ' ').slice(0, 160))
  check('默认「仅跨域」视图不显示同域批次（筛选在真的生效）',
    !tableText.includes(seed?.same), `same=${seed?.same}`)
} catch (error) {
  check('浏览器步骤执行完成', false, String(error?.message || error))
} finally {
  try { sock?.close() } catch { /* 忽略 */ }
  try { proc.kill() } catch { /* 忽略 */ }
}

// ---------------------------------------------------------------------------
// 6. 清理：只删本脚本种的行（TAG 前缀），杜绝残留
// ---------------------------------------------------------------------------
title('6. 清理：删掉本脚本种的会话 / 批次 / 节点')
const cleanupProgram = `
import os, sys
sys.path.insert(0, '/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
import django
django.setup()
from pqkds.models import Node, DistributionBatch, SessionKey

TAG = ${JSON.stringify(TAG)}
s, _ = SessionKey.objects.filter(session_id__startswith=TAG).delete()
b, _ = DistributionBatch.objects.filter(batch_id__startswith=TAG).delete()
n, _ = Node.objects.filter(node_id__startswith=TAG).delete()
left = (SessionKey.objects.filter(session_id__startswith=TAG).count()
        + DistributionBatch.objects.filter(batch_id__startswith=TAG).count()
        + Node.objects.filter(node_id__startswith=TAG).count())
print('sessions=%d batches=%d nodes=%d left=%d' % (s, b, n, left))
`
let out = ''
let err = ''
try {
  out = runInDjango(cleanupProgram).trim()
} catch (error) {
  err = String(error?.stderr || error?.message || error)
}
info(out || err)
check('清理完成（left=0）', Boolean(out) && out.endsWith('left=0'), out || err)

finish()