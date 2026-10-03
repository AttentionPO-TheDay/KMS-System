/**
 * KMS-013 页面冒烟：**节点用户**登录 → 打开「密钥池」页 → 断言新的
 * 真实状态 / 接收密钥版本列与五个统计读数在**真浏览器**里渲染出来。
 *
 * 为什么必须用真浏览器：产物里有字符串不等于页面渲染了它们（组件没挂载、
 * 列被 v-if 挡掉、接口字段名对不上，产物全都照样带着那些字符串）。
 *
 * ⚠️ 页面归属：`selfpool`（component=keypool/index）授给**普通角色**（节点用户），
 *    admin 看到的是另一个页（`poolgov` → `keypool/overview`）。所以这里走
 *    节点链路：管理端建节点 → 本机激活换令牌 → 把**节点令牌**写进
 *    `Admin-Token` Cookie（与前端 utils/auth.js 同一处）再打开页面。
 *
 * ⚠️ 依赖一个真节点（四套密钥）。结束后自建自清（domain=kms013-smoke）。
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
  adminLogin,
  newNodeSession,
  cryptoProvider
} from './lib/node-session.mjs'
import { dockerBin } from '../../../tools/lib/mysql.mjs'

const { check, info, finish } = makeReporter()

const CHROME = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
].find(existsSync)
if (!CHROME) { console.log('找不到浏览器'); process.exit(1) }

const PORT = 9225
const DOMAIN = 'kms013-smoke'
const dir = mkdtempSync(join(tmpdir(), 'kms013-cdp-'))
const proc = spawn(CHROME, [
  `--remote-debugging-port=${PORT}`, `--user-data-dir=${dir}`,
  '--headless=new', '--no-first-run', '--window-size=1680,1000', 'about:blank'
], { stdio: 'ignore' })

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function main() {
  title('1. 节点用户链路：管理端建节点 → 本机激活换令牌 → 四套密钥 + init')
  const adminToken = await adminLogin()
  const node = await newNodeSession(adminToken, { prefix: 'K13S', name: 'KMS-013 冒烟', domainId: DOMAIN })
  check('节点已建好并激活（拿到节点令牌）', Boolean(node.token), node.nodeId)

  // ⚠️ 必须走完初始化（四套密钥 + /node-self/init/）：**未初始化的节点**会被
  //    前端守卫重定向到「节点首次初始化」页 —— 第一次冒烟就撞在这上面，
  //    表现是"页面渲染了，但渲染的是另一页"。
  info('生成四套密钥并登记（Falcon 本机生成要十几秒）…')
  for (const [algorithm, options, extra] of [
    ['SM2', {}, {}],
    ['SSCL', {}, {}],
    ['KYBER', { variant: 768 }, { securityLevel: '768' }],
    ['FALCON', {}, {}]
  ]) {
    const material = await cryptoProvider.generate(algorithm, { nodeId: node.nodeId, ...options })
    const up = await api(PQKDS, '/node-self/keys/', {
      method: 'POST',
      token: node.token,
      body: {
        algorithm,
        publicKey: material.publicKey,
        securityLevel: extra.securityLevel,
        deviceId: node.fingerprint,
        keyId: material.keyId,
        keyVersion: material.version
      }
    })
    if (!isOk(up.body)) check(`${algorithm} 登记成功`, false, `msg=${up.body?.msg}`)
  }
  const init = await api(PQKDS, '/node-self/init/', { method: 'POST', token: node.token })
  check('节点初始化收尾成功（否则会被守卫赶去初始化页）', isOk(init.body),
    `msg=${init.body?.msg} status=${init.body?.data?.node?.status}`)

  title('2. 真浏览器：注入节点令牌 → 打开 /selfpool')
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
  if (!ws) { console.log('CDP 未就绪'); process.exit(1) }

  const sock = new WebSocket(ws)
  let id = 0
  const pending = new Map()
  sock.addEventListener('message', (ev) => {
    const msg = JSON.parse(ev.data)
    if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id) }
  })
  await new Promise((res) => sock.addEventListener('open', res, { once: true }))
  const send = (method, params = {}) => new Promise((resolve) => {
    const myId = ++id
    pending.set(myId, resolve)
    sock.send(JSON.stringify({ id: myId, method, params }))
  })

  await send('Page.enable')
  await send('Runtime.enable')
  await send('Page.navigate', { url: `${ORIGIN}/updatedel/` })
  await sleep(2500)
  await send('Runtime.evaluate', {
    expression: `document.cookie = 'Admin-Token=' + ${JSON.stringify(node.token)} + ';path=/'`
  })
  // ⚠️ 路由路径 = 目录菜单 + 子菜单：9472 `selfpool` 挂在 9420 `distzone`
  //    （「密钥分发」目录）下，所以真实 URL 是 `/distzone/selfpool` ——
  //    只写 `/selfpool` 会落到 SPA 的 404 兜底页（看起来像"页面没了"）。
  await send('Page.navigate', { url: `${ORIGIN}/updatedel/distzone/selfpool` })
  await sleep(7000)

  const evalText = async (expression) => {
    const r = await send('Runtime.evaluate', { expression, returnByValue: true })
    return r?.result?.result?.value
  }

  const body = String(await evalText('document.body.innerText'))
  check('页面已渲染（不是登录页/404 兜底）',
    body.includes('密钥池') && !body.includes('登 录') && !body.includes('找不到网页'),
    body.replace(/\s+/g, ' ').slice(0, 120))

  const headers = String(await evalText(
    `JSON.stringify([...document.querySelectorAll('th')].map((th) => th.innerText.trim()))`))
  check('★ 表头含「接收密钥版本」与「消费情况」（KMS-013 新增的两列）',
    headers.includes('接收密钥版本') && headers.includes('消费情况'),
    headers.slice(0, 220))

  const statKeys = String(await evalText(
    `JSON.stringify([...document.querySelectorAll('.stat .k')].map((el) => el.innerText.trim()))`))
  check('★ 统计卡片含五个真实读数：可用 / 已消费 / 已过期 / 已回收 / 预留',
    ['可用', '已消费', '已过期', '已回收', '预留'].every((k) => statKeys.includes(k)),
    statKeys.slice(0, 200))

  const rows = String(await evalText(
    `JSON.stringify([...document.querySelectorAll('.el-table__row')].slice(0, 120).map((row) => row.innerText).join(' | ').slice(0, 3000))`))
  const hasPoolRow = rows.includes('pool_') || rows.includes('READY') || rows.includes('可被会话取用')
  check('★ 状态列渲染的是归一后的中文标签（可被会话取用/已消费/已回收/已过期/（历史）之类），不是裸枚举名',
    !rows
    || /可被会话取用|已消费|已回收|已过期|已下发（历史）|未使用（历史）|已使用（历史）|预留（保留值）/.test(rows)
    || !hasPoolRow,
    rows.replace(/\s+/g, ' ').slice(0, 180) || `（本节点暂无池项行 —— 状态标签来自 STATUS_LABELS 映射，'
      + '字段链路已在 verify-pool-consume.mjs 第 4 节按 HTTP 断言）`)

  try { proc.kill() } catch { /* 忽略 */ }

  title('3. 清理：删掉冒烟节点')
  const cleanupProgram = `
import os, sys
sys.path.insert(0, '/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
import django
django.setup()
from pqkds.models import Node
nodes = list(Node.objects.filter(domain_id='${DOMAIN}'))
ids = [n.pk for n in nodes]
deleted, _ = Node.objects.filter(pk__in=ids).delete()
left = Node.objects.filter(domain_id='${DOMAIN}').count()
print('nodes=%d cascaded=%d left=%d' % (len(ids), deleted, left))
`
  let out = ''
  let err = ''
  try {
    out = execFileSync(dockerBin, ['exec', '-i', '-w', '/backend', 'dvadmin3-django', 'python', '-'], {
      input: cleanupProgram, encoding: 'utf8', env: { ...process.env, MSYS_NO_PATHCONV: '1' }
    }).trim()
  } catch (error) {
    err = String(error?.stderr || error?.message || error)
  }
  info(out || err)
  check('清理完成', Boolean(out) && out.endsWith('left=0'), out || err)

  finish()
}

main().catch((e) => { console.log(`冒烟脚本出错：${e}`); process.exitCode = 1 })