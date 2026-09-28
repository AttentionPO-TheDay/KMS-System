/**
 * 验证「密钥更新」页（**菜单实际指向的那个页面**）的部分刷新路径。
 *
 * 为什么单独做这一条
 * ------------------
 * §5.3 的客户端合成此前只做在 `views/lifecycle/index.vue` 上，
 * 而那个页面**没有路由、不在任何菜单里**（1696 行、全仓库无引用）——
 * 于是"部分刷新"在后端做完并验证通过之后，用户**在界面上够不到**。
 * 本用例守的是**活页面** `keyupdate/index.vue` 的这条路径。
 *
 * 走的是页面 submitForm 的实际调用顺序：
 *   取当前 uA → updateKeymanage({rotate:true, ua}) → 本机合成新 d_A
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

const { composeUpdatedPrivateKey } = await import('../src/utils/cl-key.js')
const { buildKeyFile, parseKeyFile } = await import('../src/utils/key-file.js')
const { login } = await import('../../../tools/lib/captcha.mjs')

const api = async (p, { method = 'GET', token, body } = {}) => {
  const r = await fetch(`${ORIGIN}/updatedel-api${p}`, { method, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}) }, ...(body ? { body: JSON.stringify(body) } : {}) })
  return { status: r.status, body: await r.json().catch(() => null) }
}
const norm = (r) => r && ({ keyId: r.key_id ?? r.keyId, version: r.version, ua: r.ua, keyValue: r.key_value ?? r.keyValue, encrytName: r.encryt_name ?? r.encrytName, encrytType: r.encryt_type ?? r.encrytType })

const admin = await login(ORIGIN, '/updatedel-api', 'admin', 'admin123')
// 真实在 sm2p256v1 上的点 —— KGC 会校验曲线方程
const UA = '04573e32965ced2ca54c9f9a26be3c5115f83f61bc0d7ed72b90ffb9bce6b741235c0e249f323ad7703340983665e5147c6893490242af26fa642372a899a74c30'.replace('ffb9bce6', 'ffb9cce6')
const STAMP = Date.now().toString(36).toUpperCase().slice(-6)

console.log('\n=== 1. 建一把 SM2 密钥（含真实 uA）===')
const created = await api('/lifecycle/keymanage', { method: 'POST', token: admin, body: {
  userId: 1, userName: 'admin', encrytType: '无证书非对称加密', encrytName: 'SM2',
  keyName: `kur-${STAMP}`, keyUse: 'verify', keyDomain: 'A', ua: UA, status: '0' } })
const key = norm(created.body?.data)
check('密钥已建', created.body?.code === 200 && !!key?.keyId, `keyId=${key?.keyId} ${created.body?.msg || ''}`)
if (!key?.keyId) { console.log('无法继续'); process.exit(1) }

console.log('\n=== 2. 模拟本机密钥环：为这把密钥准备一份 d_A 密钥文件 ===')
// 节点侧秘密份额 u（真实场景由浏览器生成；这里造一个合法的 64 位标量）
const u = 'a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90'
const keyFile = await buildKeyFile({ keyId: key.keyId, userId: 1, algorithm: 'SM2', privateShare: u, publicKey: '' })
const parsed = await parseKeyFile(JSON.stringify(keyFile))
check('密钥文件可往返解析（页面从密钥环取它）', parsed.private_share === u)

console.log('\n=== 3. ★ 按页面 submitForm 的顺序提交部分刷新 ===')
check('提交前 version=1', Number(key.version) === 1, `version=${key.version}`)
const rot = await api('/lifecycle/keymanage', { method: 'PUT', token: admin, body: {
  keyId: key.keyId, keyName: `kur-${STAMP}`, keyUse: 'verify', keyDomain: 'A',
  rotate: true, ua: key.ua } })
const after = norm(rot.body?.data)
check('轮换请求成功', rot.body?.code === 200, `${rot.body?.msg || ''}`)
check('★ version 递增到 2', Number(after?.version) === 2, `version=${after?.version}`)
check('★★ uA 保持不变（§5.3 核心）', after?.ua === key.ua,
  `后=${String(after?.ua).slice(0, 16)}… 前=${String(key.ua).slice(0, 16)}…`)
check('★ KGC 部分密钥已换新', !!after?.keyValue && after.keyValue !== key.keyValue)

console.log('\n=== 4. ★ 本机合成新版本 d_A ===')
const composed = composeUpdatedPrivateKey({
  algorithm: 'SM2', keyValue: after.keyValue, clientPrivateHex: parsed.private_share })
check('合成出 64 位十六进制私钥', /^[0-9a-f]{64}$/.test(composed.finalPrivateKey),
  `${composed.finalPrivateKey.slice(0, 16)}…`)
check('★ 新 d_A 与旧的**不同**（否则等于没换）',
  composed.finalPrivateKey !== u)
const nextFile = await buildKeyFile({ keyId: key.keyId, userId: 1, algorithm: 'SM2',
  privateShare: composed.finalPrivateKey, publicKey: composed.finalPublicKey || '' })
const nextParsed = await parseKeyFile(JSON.stringify(nextFile))
check('新密钥文件可解析且私钥与新 d_A 一致', nextParsed.private_share === composed.finalPrivateKey)

console.log('\n=== 5. 只改元数据时不轮换（没有把正常路径变成轮换）===')
const meta = await api('/lifecycle/keymanage', { method: 'PUT', token: admin, body: {
  keyId: key.keyId, keyName: `kur-${STAMP}-renamed`, keyUse: 'verify', keyDomain: 'A' } })
const metaAfter = norm(meta.body?.data)
check('★ 不带 rotate 时 version **不变**', Number(metaAfter?.version) === 2,
  `version=${metaAfter?.version}`)
check('★ 不带 rotate 时材料**不变**', metaAfter?.keyValue === after.keyValue)

const pass = results.filter((r) => r.p).length
console.log(`\n=== 结果：${pass}/${results.length} 项通过 ===`)
if (pass !== results.length) { results.filter((r) => !r.p).forEach((r) => console.log(`  - ${r.n}  ${r.d}`)); process.exitCode = 1 }
