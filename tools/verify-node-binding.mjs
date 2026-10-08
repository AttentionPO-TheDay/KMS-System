// =============================================================================
// verify-node-binding.mjs —— 激活凭证打码 + 登录绑定文件 + 换节点清旧绑定
// -----------------------------------------------------------------------------
// 本轮三件事，每件都在这一个闭环里走到：
//
//   1. **激活凭证按密码展示**：管理员建节点后，弹窗里的凭证默认打码
//      （`.code-text.is-masked`，内容是一串点而不是凭证），点「显示」才现原文。
//      ⚠️ 判据必须落在**元素文本**上，不能拿整页文本查"凭证有没有出现" ——
//         弹窗本身有说明文字，很容易自证。
//
//   2. **登录即生成绑定文件**：节点激活/登录成功后，本机 IndexedDB 的 meta store
//      里出现 `binding:node-XXX`（节点、设备公钥指纹、首次/最近登录、登录次数）。
//      加密保护密钥也存在同一个 store（`protector`），所以读取时**只挑基本类型字段**，
//      直接 getAll 返回会把 CryptoKey 塞进 CDP 序列化。
//
//   3. **登录新节点删除前一份绑定**：本机已有 A 的绑定时点 B →
//      先弹确认框（取消则什么都不发生）；确认后 A 的绑定记录与**设备凭据**
//      一起被清掉，只留 B。最后回登录页，列表里只剩 B。
//
// ⚠️ 会真建两个节点、真激活、真清绑定。新建的节点结尾自建自清。
// 用法：node tools/verify-node-binding.mjs
// =============================================================================
import { execFileSync, spawn } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const ORIGIN = 'http://127.0.0.1'
const BASE = '/updatedel'
const PORT = 9391
const SEED = Date.now().toString(36).toUpperCase().slice(-6)
const NODE_A = `Node-BND-A-${SEED}`
const NODE_B = `Node-BND-B-${SEED}`
const CHROME = ['C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find((p) => existsSync(p))
if (!CHROME) { console.log('找不到浏览器'); process.exit(1) }

const results = []
const check = (n, p, d = '') => { results.push({ n, p, d }); console.log(`  ${p ? '[PASS]' : '[FAIL]'} ${n}${d ? '  → ' + d : ''}`) }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

function captcha(uuid) {
  const raw = execFileSync('docker', ['exec', 'kms_redis', 'redis-cli', 'get', `captcha_codes:${uuid}`], { encoding: 'utf8' }).trim()
  return raw ? raw.replace(/^"(.*)"$/s, '$1') : ''
}

const dir = mkdtempSync(join(tmpdir(), 'nodebinding-'))
const chrome = spawn(CHROME, [`--remote-debugging-port=${PORT}`, `--user-data-dir=${dir}`,
  '--headless=new', '--no-first-run', '--window-size=1680,1000', 'about:blank'], { stdio: 'ignore' })

let ws, id = 0
let pageCaptchaUuid = ''
const rpc = (m, p = {}) => new Promise((res, rej) => {
  const n = ++id
  const on = (e) => {
    const x = JSON.parse(typeof e.data === 'string' ? e.data : e.data.toString())
    if (x.id === n) { ws.removeEventListener('message', on); x.error ? rej(new Error(JSON.stringify(x.error))) : res(x.result) }
  }
  ws.addEventListener('message', on); ws.send(JSON.stringify({ id: n, method: m, params: p }))
})
const ev = async (e, timeoutMs = 60000) => {
  const r = await Promise.race([
    rpc('Runtime.evaluate', { expression: e, awaitPromise: true, returnByValue: true }),
    new Promise((_, j) => setTimeout(() => j(new Error('页面求值超时')), timeoutMs)),
  ])
  if (r.exceptionDetails) return { __err: r.exceptionDetails.exception?.description || r.exceptionDetails.text }
  return r.result?.value
}
const SET = `(el,v)=>{const s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;s.call(el,v);el.dispatchEvent(new Event('input',{bubbles:true}))}`

/** 本机 IndexedDB 读取。**只挑基本类型字段**：meta store 里住着 CryptoKey，
 *  直接把记录返回给 CDP 序列化会失败（或得到空对象），而误判成"没有这条记录"。 */
const readMeta = () => ev(`(async () => {
  const db = await new Promise((res,rej)=>{const r=indexedDB.open('kms-node-keystore');r.onsuccess=()=>res(r.result);r.onerror=()=>rej(r.error)})
  if(!db.objectStoreNames.contains('meta')) return {exists:false, keys:[]}
  const rows = await new Promise((res,rej)=>{const tx=db.transaction('meta','readonly');const q=tx.objectStore('meta').getAll();q.onsuccess=()=>res(q.result);q.onerror=()=>rej(q.error)})
  return {exists:true, keys: rows.map(r=>String(r.k||'')),
    bindings: rows.filter(r=>String(r.k||'').endsWith('-binding')).map(r=>({
      k:String(r.k||''), nodeId:String(r.nodeId||''), name:String(r.name||''),
      nodeName:String(r.nodeName||''), deviceFingerprint:String(r.deviceFingerprint||''),
      createdAt:String(r.createdAt||''), lastLoginAt:String(r.lastLoginAt||''), loginCount:Number(r.loginCount||0)}))}
})()`)

const readDeviceKeys = () => ev(`(async () => {
  const db = await new Promise((res,rej)=>{const r=indexedDB.open('kms-node-keystore');r.onsuccess=()=>res(r.result);r.onerror=()=>rej(r.error)})
  if(!db.objectStoreNames.contains('deviceKeys')) return []
  const rows = await new Promise((res,rej)=>{const tx=db.transaction('deviceKeys','readonly');const q=tx.objectStore('deviceKeys').getAll();q.onsuccess=()=>res(q.result);q.onerror=()=>rej(q.error)})
  return rows.map(r=>String(r.keyRef||''))
})()`)

function hookCaptcha() {
  ws.addEventListener('message', (e) => {
    const m = JSON.parse(typeof e.data === 'string' ? e.data : e.data.toString())
    if (m.method === 'Network.responseReceived' && /captchaImage/.test(m.params?.response?.url || '')) {
      rpc('Network.getResponseBody', { requestId: m.params.requestId })
        .then((r) => { try { pageCaptchaUuid = JSON.parse(r.body).uuid || '' } catch { /* 非 JSON */ } })
        .catch(() => { /* 响应体可能已被丢弃 */ })
    }
  })
}

async function loginAdmin() {
  pageCaptchaUuid = ''
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/login` })
  await sleep(4000)
  const inputs = `[...document.querySelectorAll('.login-form input:not([type=radio]):not([type=checkbox])')]`
  await ev(`(() => { const set=${SET}; const ins=${inputs}
    set(ins[0],'admin'); set(ins[1],'admin123'); set(ins[2],${JSON.stringify(captcha(pageCaptchaUuid))}); return true })()`)
  await sleep(400)
  await ev(`(() => { const b=[...document.querySelectorAll('.login-form button')].find(x=>x.innerText.includes('登')); b.click(); return true })()`)
  await sleep(7000)
  return ev(`location.pathname`)
}

async function switchToNodeTab() {
  await ev(`(() => {
    const b=[...document.querySelectorAll('.principal-switch .el-radio-button')].find(x=>x.innerText.trim()==='节点')
    if(!b) return false; b.querySelector('input').click(); b.click(); return true })()`)
  await sleep(1200)
}

async function logout() {
  await ev(`document.cookie='Admin-Token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'`)
}

try {
  let t = null
  for (let i = 0; i < 40 && !t; i++) {
    try { t = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find((x) => x.type === 'page') } catch { /* not up */ }
    if (!t) await sleep(500)
  }
  if (!t) throw new Error('拿不到 CDP page target')
  ws = new WebSocket(t.webSocketDebuggerUrl)
  await new Promise((r) => ws.addEventListener('open', r, { once: true }))
  await rpc('Runtime.enable'); await rpc('Page.enable'); await rpc('Network.enable')
  hookCaptcha()

  // ===== 1. 管理员登录 → 界面上建节点 A =====
  console.log('\n== 1. 管理员建节点（界面上拿激活凭证）==')
  const adminPath = await loginAdmin()
  check('管理员登录后进站', !adminPath.includes('/login'), adminPath)
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/nodegov/nodes` })
  await sleep(6000)

  const opened = await ev(`(() => {
    const b=[...document.querySelectorAll('button')].find(x=>/新建|新增|创建/.test(x.innerText))
    if (!b) return false; b.click(); return true })()`)
  check('节点管理页有「新建」入口', opened === true)
  await sleep(2500)

  const filled = await ev(`(() => {
    const set=${SET}
    const dlg=document.querySelector('.el-dialog')
    if(!dlg) return {ok:false, why:'no dialog'}
    const itemByLabel=(re)=>{
      const items=[...dlg.querySelectorAll('.el-form-item')]
      return items.find(it=>{ const lb=it.querySelector('.el-form-item__label'); return lb && re.test(lb.innerText.trim()) })
    }
    const control=(it)=> it ? it.querySelector('input, textarea') : null
    const setItem=(re,val)=>{ const c=control(itemByLabel(re)); if(!c) return false; set(c,val); return true }
    const r={}
    r.id   = setItem(/^节点ID$/, ${JSON.stringify(NODE_A)})
    r.name = setItem(/^节点名称$/, ${JSON.stringify(NODE_A)})
    r.ip   = setItem(/IP 地址|IP地址/, '127.0.0.1')
    r.port = setItem(/^端口$/, '${9100 + Math.floor(Math.random() * 800)}')
    return {ok: r.id && r.name && r.ip && r.port, filled:r}
  })()`)
  check('建节点表单已填必填项', filled?.ok === true, JSON.stringify(filled))
  await ev(`(() => {
    const dlg=document.querySelector('.el-dialog')
    const b=[...dlg.querySelectorAll('button')].find(x=>/确 定|确定|保 存|保存|提 交|提交/.test(x.innerText))
    if(!b) return false; b.click(); return true })()`)
  console.log('  （建节点中，需等待服务端处理…）')
  await sleep(20000)

  // ===== 2. 激活凭证：默认打码，点「显示」才现原文 =====
  console.log('\n== 2. 激活凭证按密码展示 ==')
  const masked = await ev(`(() => {
    const el=document.querySelector('.el-dialog .code-text')
    return el ? {text: el.innerText.trim(), masked: el.classList.contains('is-masked'),
                 buttons:[...document.querySelectorAll('.el-dialog button')].map(b=>b.innerText.trim())} : null
  })()`)
  // 判据：内容是一串点（不是 30+ 位字母数字串），且带 is-masked 类
  check('凭证弹窗里的凭证**默认打码**（不是明文）',
    Boolean(masked) && masked.masked === true && /^[•·*]+$/.test(masked.text),
    masked ? `class=is-masked=${masked.masked} text=${JSON.stringify(masked.text.slice(0, 20))}` : '（没找到 .code-text）')
  check('弹窗里有「显示」按钮（打码不是不可逆的）',
    (masked?.buttons || []).some((b) => b === '显示'), JSON.stringify(masked?.buttons || []))

  const revealed = await ev(`(() => {
    const b=[...document.querySelectorAll('.el-dialog button')].find(x=>x.innerText.trim()==='显示')
    if(!b) return {ok:false}
    b.click()
    return {ok:true}
  })()`)
  await sleep(600)
  const shown = await ev(`(() => {
    const el=document.querySelector('.el-dialog .code-text')
    return el ? {text: el.innerText.trim(), masked: el.classList.contains('is-masked')} : null
  })()`)
  const codeA = shown?.text || ''
  check('★ 点「显示」后现出凭证原文（43 位左右的 URL-safe 随机串）',
    revealed?.ok === true && /^[A-Za-z0-9_-]{30,}$/.test(codeA) && shown?.masked === false,
    `长度=${codeA.length} 前 8 位=${codeA.slice(0, 8)}…`)
  check('★★ 打码是**真的藏住了**：未点显示时弹窗里不存在凭证原文',
    Boolean(codeA) && (masked?.text || '').indexOf(codeA) === -1 && (masked?.text || '').length < 40,
    `打码态文本长度=${(masked?.text || '').length}`)

  // 建节点 B（用接口，省一次 20 秒的界面等待；凭证掩码的界面断言已覆盖）
  const adminToken = await ev(`document.cookie.match(/Admin-Token=([^;]+)/)?.[1] || ''`)
  const regB = await ev(`fetch('${ORIGIN}/pqkds-api/pqkds/nodes/register/',{method:'POST',
    headers:{'Content-Type':'application/json','Authorization':'Bearer ${adminToken}'},
    body:JSON.stringify({node_id:${JSON.stringify(NODE_B)},name:${JSON.stringify(NODE_B)},
      ip_address:'127.0.0.1',port:${9200 + Math.floor(Math.random() * 700)},node_type:'full',
      permission_level:'L2',domain_id:'bnd-verify'})}).then(r=>r.json())`)
  const codeB = regB?.data?.activation_code || ''
  check('第二个节点（B）经接口创建并拿到凭证', Boolean(codeB),
    codeB ? `长度 ${codeB.length}` : JSON.stringify(regB).slice(0, 160))
  if (!codeB) throw new Error('节点 B 没拿到凭证，无法继续')

  // ===== 3. 节点 A 激活：凭证输入框是密码型 + 绑定文件落库 =====
  console.log('\n== 3. 节点 A 激活（凭证输入框按密码型）==')
  await logout()
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/login` })
  await sleep(3500)
  await switchToNodeTab()

  const inputKinds = await ev(`(() => {
    const ins=[...document.querySelectorAll('.login-form input')]
    return ins.map(i=>({type:i.type, ph:i.placeholder}))
  })()`)
  check('★ 激活凭证输入框是 **password** 型（明文不出现在屏幕上）',
    (inputKinds || []).some((i) => i.type === 'password' && /激活凭证/.test(i.ph || '')),
    JSON.stringify(inputKinds))

  const inputs = `[...document.querySelectorAll('.login-form input:not([type=radio]):not([type=checkbox])')]`
  await ev(`(() => { const set=${SET}; const ins=${inputs}
    set(ins[0],${JSON.stringify(NODE_A)}); set(ins[1],${JSON.stringify(codeA)}); return true })()`)
  await ev(`(() => { const b=[...document.querySelectorAll('.login-form button')].find(x=>x.innerText.includes('激活')); b.click(); return true })()`)
  await sleep(8000)
  const afterActivate = await ev(`location.pathname`)
  check('激活成功并进入系统', !afterActivate.includes('/login'), afterActivate)

  const meta1 = await readMeta()
  const bindingA = (meta1?.bindings || []).find((b) => b.nodeId === NODE_A)
  check('★★ 登录后本机写下了**绑定文件**（meta store 里的 node-A-binding）',
    Boolean(bindingA) && meta1.keys.includes(`node-${NODE_A}-binding`),
    bindingA ? `nodeId=${bindingA.nodeId} name=${bindingA.name}` : `keys=${JSON.stringify(meta1?.keys || [])}`)
  check('绑定文件带设备公钥指纹（32 位十六进制，与 §4.4 的设备绑定同一个值）',
    /^[0-9a-f]{32}$/.test(bindingA?.deviceFingerprint || ''), bindingA?.deviceFingerprint || '（为空）')
  check('绑定文件带首次登录时间与登录次数',
    Boolean(bindingA?.createdAt) && bindingA.loginCount >= 1 && Boolean(bindingA?.lastLoginAt),
    `createdAt=${bindingA?.createdAt} count=${bindingA?.loginCount}`)
  // ⚠️ 判据是"**有没有**私密材料"，不是"文本里出现没出现某些词"：
  //    节点编号本身可能含 `d_`（基 36 随机段里 `10` → 'A'，`13` → 'D'…），
  //    而绑定记录里必然出现节点编号 —— 拿 /d_/ 去查会**假失败**，
  //    且失败的那一条看起来像"真的把私钥写进去了"。所以按**字段名**判。
  const bindingFields = Object.keys(bindingA || {})
  check('绑定文件里**没有**任何私密材料（只有公开量与记账字段）',
    bindingFields.every((f) => ['k', 'name', 'nodeId', 'nodeName', 'deviceFingerprint',
      'createdAt', 'lastLoginAt', 'loginCount'].includes(f)),
    JSON.stringify(bindingFields))
  check('本机设备凭据仍在（绑定文件是记账，登录靠它）',
    (await readDeviceKeys()).includes(`node-${NODE_A}-device-auth`),
    JSON.stringify(await readDeviceKeys()))

  // ===== 4. 本地密钥环境页把绑定文件展示出来 =====
  // ⚠️ 必须先完成初始化（或显式访问该页）：PENDING_INIT 的节点被路由守卫
  //    拦在 /node-init，直接导航 /selfzone/keystore 会**被弹回**到
  //    "节点首次初始化"页 —— 于是这一段的断言全落在一个没渲染出来的页面上。
  //    （实测踩到：页面上当然找不到「绑定文件」四个字。）
  console.log('\n== 4. 完成初始化后，「本地密钥环境」页展示绑定文件 ==')
  // 等按钮从禁用变为可用再点 —— 页面刚挂载时 node-self 还没回来，
  // 按钮是 `:disabled="loading || !mapped"`，点它是静默无效的。
  let initClick = 'TIMEOUT'
  for (let i = 0; i < 15; i++) {
    initClick = await ev(`(() => {
      const b=[...document.querySelectorAll('button')].find(x=>/开始初始化/.test(x.innerText))
      if(!b) return 'NOT_FOUND'
      if(b.disabled) return 'DISABLED'
      b.click(); return 'CLICKED'
    })()`)
    if (initClick === 'CLICKED') break
    await sleep(1000)
  }
  check('在「节点首次初始化」页点击开始初始化', initClick === 'CLICKED', String(initClick))
  let inited = ''
  for (let i = 0; i < 40; i++) {
    await sleep(2000)
    const body = String(await ev(`document.body.innerText`) || '')
    if (body.includes('初始化已完成')) { inited = 'DONE'; break }
    inited = body.replace(/\s+/g, ' ').slice(0, 80)
  }
  check('节点初始化完成（四套公钥本机生成并登记）', inited === 'DONE', inited)

  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/selfzone/keystore` })
  await sleep(5000)
  const ksText = String(await ev(`document.body.innerText`) || '')
  check('★ 「本地密钥环境」页有「登录绑定文件」一节', ksText.includes('登录绑定文件'),
    ksText.split('\n').map((l) => l.trim()).filter((l) => l.includes('绑定')).slice(0, 3).join(' | ').slice(0, 120))
  check('★ 页面上能看到该节点的绑定节点名与设备公钥指纹',
    ksText.includes('绑定节点') && ksText.includes('设备公钥指纹') && ksText.includes(NODE_A),
    `含节点名=${ksText.includes(NODE_A)} 含指纹标签=${ksText.includes('设备公钥指纹')}`)

  // ===== 5. 同节点免输入登录：不弹确认（没有"切换"发生） =====
  console.log('\n== 5. 同节点免输入登录：不弹确认框 ==')
  await logout()
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/login` })
  await sleep(3500)
  await switchToNodeTab()
  const listedMeta = await ev(`[...document.querySelectorAll('.activated-meta')].map(e=>e.innerText.trim())`)
  check('★ 已激活节点条目上显示了绑定文件的「上次登录」',
    (listedMeta || []).some((t) => t.includes('上次登录')), JSON.stringify(listedMeta))
  await ev(`(() => { const b=[...document.querySelectorAll('.activated-item')].find(x=>x.innerText.includes(${JSON.stringify(NODE_A)})); if(!b) return false; b.click(); return true })()`)
  await sleep(1000)
  const boxSame = await ev(`Boolean(document.querySelector('.node-switch-confirm'))`)
  await sleep(7000)
  const afterSame = await ev(`location.pathname`)
  check('同节点登录**不弹**切换确认框', boxSame === false, `messagebox=${boxSame}`)
  check('同节点免输入登录成功', !afterSame.includes('/login'), afterSame)

  const metaSame = await readMeta()
  const bindingA2 = (metaSame?.bindings || []).find((b) => b.nodeId === NODE_A)
  check('★ 再次登录刷新了绑定文件（登录次数 +1，首登时间不变）',
    bindingA2?.loginCount >= 2 && bindingA2.createdAt === bindingA?.createdAt,
    `count ${bindingA?.loginCount} → ${bindingA2?.loginCount}，createdAt ${bindingA2?.createdAt === bindingA?.createdAt ? '未变' : '变了'}`)

  // ===== 6. 激活节点 B：先弹确认；取消 → 什么都不发生 =====
  console.log('\n== 6. 换节点（激活 B）：确认框，先取消 ==')
  await logout()
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/login` })
  await sleep(3500)
  await switchToNodeTab()
  // ⚠️ 本机此刻已有可免密登录的节点 A，而登录页因此**默认收起**了激活表单
  //    （2026-10-08 改：有已登录节点时先展示免密登录）。不点开这个按钮，
  //    下面的 fillB 会往**不存在的输入框**里填值 → 一句"填入失败"，
  //    看起来像"表单坏了"，其实是没展开。
  const expandForm = await ev(`(() => {
    const b=[...document.querySelectorAll('button')].find(x=>(x.innerText||'').trim()==='登录其它节点')
    if(!b) return 'NO_BUTTON'; b.click(); return 'CLICKED'
  })()`)
  check('★ 有已激活节点时表单默认收起，点「登录其它节点」展开', expandForm === 'CLICKED', String(expandForm))
  await sleep(800)
  const inputsB = `[...document.querySelectorAll('.login-form input:not([type=radio]):not([type=checkbox])')]`
  const fillB = `(() => { const set=${SET}; const ins=${inputsB}
    set(ins[0],${JSON.stringify(NODE_B)}); set(ins[1],${JSON.stringify(codeB)}); return true })()`
  const clickActivate = `(() => { const b=[...document.querySelectorAll('.login-form button')].find(x=>x.innerText.includes('激活')); if(!b) return false; b.click(); return true })()`

  await ev(fillB)
  await ev(clickActivate)
  await sleep(1500)
  const boxText = await ev(`document.querySelector('.node-switch-confirm')?.innerText || ''`)
  check('★★ 激活新节点时弹出确认框（说清会清除旧绑定）',
    boxText.includes('清除') && boxText.includes(NODE_A) && boxText.includes(NODE_B),
    boxText.replace(/\s+/g, ' ').slice(0, 130))
  await ev(`(() => { const b=[...document.querySelectorAll('.node-switch-confirm button')].find(x=>x.innerText.trim()==='取消'); if(!b) return false; b.click(); return true })()`)
  await sleep(1500)
  const afterCancel = await ev(`(() => ({path: location.pathname, box: Boolean(document.querySelector('.node-switch-confirm'))}))()`)
  const metaCancel = await readMeta()
  check('★ 取消后**没有副作用**：未发起激活、A 的绑定与凭据原样',
    afterCancel?.path.includes('/login') && !afterCancel?.box
    && (metaCancel?.bindings || []).some((b) => b.nodeId === NODE_A)
    && !(metaCancel?.bindings || []).some((b) => b.nodeId === NODE_B)
    && (await readDeviceKeys()).includes(`node-${NODE_A}-device-auth`),
    `path=${afterCancel?.path} bindings=${JSON.stringify((metaCancel?.bindings || []).map((b) => b.nodeId))}`)

  // ===== 7. 确认：激活并登录 B，清除 A 的绑定与登录身份 =====
  console.log('\n== 7. 确认换节点：旧绑定与设备凭据被清除 ==')
  await ev(fillB) // 确认框取消不会清空输入，但重填一次更稳（表单状态与上次一致）
  await ev(clickActivate)
  await sleep(1500)
  const confirmed = await ev(`(() => {
    const box=document.querySelector('.node-switch-confirm')
    if(!box) return 'NO_BOX'
    const b=[...box.querySelectorAll('button')].find(x=>/清除旧绑定并登录|确定/.test(x.innerText))
    if(!b) return 'NO_BUTTON'
    b.click(); return 'CLICKED'
  })()`)
  check('确认框有「清除旧绑定并登录」按钮并点了', confirmed === 'CLICKED', String(confirmed))
  await sleep(9000)
  const afterSwitch = await ev(`location.pathname`)
  check('换节点后激活/登录成功', !afterSwitch.includes('/login'), afterSwitch)

  const meta2 = await readMeta()
  const ids2 = (meta2?.bindings || []).map((b) => b.nodeId)
  check('★★ 新节点（B）的绑定文件已写下', ids2.includes(NODE_B), JSON.stringify(ids2))
  check('★★ 前一份绑定（A）已被删除', !ids2.includes(NODE_A), JSON.stringify(ids2))
  const keys2 = await readDeviceKeys()
  check('★★ A 的设备凭据也被清除（否则"没有绑定却还能登录"）',
    !keys2.includes(`node-${NODE_A}-device-auth`), JSON.stringify(keys2))
  check('B 的设备凭据在场', keys2.includes(`node-${NODE_B}-device-auth`), JSON.stringify(keys2))

  // ===== 8. 回登录页：列表里只剩 B =====
  console.log('\n== 8. 换节点后的登录页 ==')
  await logout()
  await rpc('Page.navigate', { url: `${ORIGIN}${BASE}/login` })
  await sleep(3500)
  await switchToNodeTab()
  const listed = await ev(`[...document.querySelectorAll('.activated-name')].map(e=>e.innerText.trim())`)
  check('★★ 已激活列表只剩 B（A 的本机登录身份已清）',
    Array.isArray(listed) && listed.includes(NODE_B) && !listed.includes(NODE_A),
    JSON.stringify(listed))

  console.log('\n===== 汇总 =====')
  const failed = results.filter((r) => !r.p)
  console.log(`总计 ${results.length}，通过 ${results.length - failed.length}，失败 ${failed.length}`)
  failed.forEach((f) => console.log(`  - ${f.n}  ${f.d}`))
  console.log(`\n本次使用的节点：${NODE_A} / ${NODE_B}（结尾清理）`)
  process.exitCode = failed.length ? 1 : 0
} catch (e) {
  console.error('\n[ERROR]', e.message)
  process.exitCode = 1
} finally {
  // 清理：删掉本脚本建的两个节点（级联删长期密钥/会话等）
  try {
    const out = execFileSync('docker', ['exec', '-i', '-w', '/backend', 'dvadmin3-django', 'python', '-'], {
      input: `
import os, sys
sys.path.insert(0, '/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
import django
django.setup()
from pqkds.models import Node
rows = list(Node.objects.filter(node_id__in=['${NODE_A}', '${NODE_B}']))
ids = [n.pk for n in rows]
deleted, _ = Node.objects.filter(pk__in=ids).delete()
left = Node.objects.filter(node_id__in=['${NODE_A}', '${NODE_B}']).count()
print('nodes=%d deleted=%d left=%d' % (len(ids), deleted, left))
`,
      encoding: 'utf8', env: { ...process.env, MSYS_NO_PATHCONV: '1' }
    }).trim()
    console.log(`  [info] 清理：${out}`)
  } catch (error) {
    console.log(`  [info] 清理失败：${String(error?.stderr || error?.message || error).slice(0, 200)}`)
  }
  try { ws?.close() } catch { /* noop */ }
  try { chrome.kill() } catch { /* noop */ }
}
