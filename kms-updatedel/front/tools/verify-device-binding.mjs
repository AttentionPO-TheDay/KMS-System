/**
 * §4.4 设备绑定验证（KMS-005 重写）。
 *
 * 要证明的是：**换了一台设备登录时，系统能发现**，并且这个发现是
 * 有依据的（服务端记着密钥绑在哪台设备，本机知道自己是哪台）。
 *
 * 为什么这件事非做不可：私钥只在节点侧，服务端**从密钥本身看不出**
 * 它属于哪台设备。没有绑定记录，"新设备登录"与"同一台设备"在服务端
 * 看来完全一样 —— 而两者的正确处置是相反的。
 * 后果是静默的：界面一切正常，直到某天某个信封解不开。
 *
 * KMS-005 重写的三处（旧版本在这三处都必然失败）
 * ----------------------------------------------
 *   1. **节点口令登录不再存在**（口令随机生成、从不下发），改走
 *      「建节点拿激活凭证 → 本机生成设备密钥 → 激活换令牌」，
 *      见 `lib/node-session.mjs`。旧脚本那句 `login(..., NODE_ID, 'admin123')`
 *      现在恒失败，而现象只是"后面全 401"，看起来像接口挂了。
 *   2. **`deviceId` 是设备公钥指纹**（`sha256("{crv}|{x}|{y}")[:32]`），
 *      与激活时写进 `Node.key_device_id` 的是同一个值。旧脚本用的是
 *      `store.getDeviceId()`（浏览器随机 id）——**两者永不相等**，
 *      而失败信息看起来像"设备绑定坏了"。
 *   3. **模拟"另一台设备"必须连设备凭据一起换**：`clearAll()` 刻意**不清**
 *      `deviceKeys`（那是登录身份，不是分发密钥，见 `node-key-store.js`）。
 *      只清长期密钥材料的话，本机还是原来那台设备、指纹一字不变，
 *      "换设备被拒"这条就变成了自证。
 */
import { PQKDS, api, isOk, title, makeReporter, adminLogin, newNodeSession, deviceLogin, cryptoProvider } from './lib/node-session.mjs'
import { sqlScalar } from '../../../tools/lib/mysql.mjs'

const store = await import('../src/utils/crypto/node-key-store.js')
const { ensureDeviceKey, deviceFingerprint, removeDeviceKey } = await import('../src/utils/crypto/device-credential.js')

const { check, info, finish } = makeReporter()

title('1. 建节点 → 激活（设备 A）')
const admin = await adminLogin()
const session = await newNodeSession(admin, { prefix: 'NDV', domainId: 'ddv', permissionLevel: 'L2' })
const NODE_ID = session.nodeId
const deviceA = session.fingerprint
const token = session.token
check('本机（设备 A）有设备公钥指纹', Boolean(deviceA), `deviceA=${deviceA.slice(0, 12)}…`)

const ALGOS = [['SM2', {}], ['SSCL', {}], ['KYBER', { variant: 768 }], ['FALCON', {}]]
for (const [algo, opts] of ALGOS) {
  const kp = await cryptoProvider.generate(algo, { nodeId: NODE_ID, ...opts })
  const up = await api(PQKDS, '/node-self/keys/', { method: 'POST', token, body: {
    algorithm: algo, publicKey: kp.publicKey, deviceId: deviceA,
    keyId: kp.keyId, keyVersion: kp.version,
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
  aKeys.present === true && ALGOS.every(([a]) => aList.includes(a)),
  `present=${aKeys.present} algorithms=${JSON.stringify(aKeys.algorithms)}`)

const fin = await api(PQKDS, '/node-self/init/', { method: 'POST', token })
check('初始化完成', isOk(fin.body) && fin.body?.data?.node?.status === 'ACTIVE',
  `status=${fin.body?.data?.node?.status}`)

title('2. 服务端记下了绑定设备')
// 查库走 `tools/lib/mysql.mjs`：旧版那份内联 sql() 在 Windows 上**静默失败**
// （Node 的 execSync 走 cmd.exe，PATH 里没有 docker），空结果会被当成"绑定为空"。
const bound = sqlScalar(`SELECT key_device_id FROM falcon_kds.dvadmin_pqkds_nodes WHERE node_id='${NODE_ID}';`)
check('★ 库里记录了绑定设备（激活时写入的设备公钥指纹）', bound === deviceA,
  `bound=${String(bound).slice(0, 12)}… 本机指纹=${deviceA.slice(0, 12)}…`)

const self = await api(PQKDS, '/node-self/', { token })
check('★ /node-self/ 下发 keyDeviceId（前端靠它判断）',
  self.body?.data?.node?.keyDeviceId === deviceA,
  `keyDeviceId=${String(self.body?.data?.node?.keyDeviceId).slice(0, 12)}…`)

title('3. ★ 换设备：登录与上报都必须被拒（这是本项的核心）')
info('清长期密钥材料 + 换掉设备凭据，模拟"另一台设备"')
await store.clearAll()
// ⚠️ 必须单独删：clearAll() 刻意不清 deviceKeys —— 少了这一步，本机指纹
//    一字不变，下面的"新设备被拒"就永远测的是同一台设备。
await removeDeviceKey(NODE_ID)
check('清掉设备凭据后本机不再有指纹', (await deviceFingerprint(NODE_ID)) === '', 'deviceFingerprint(NODE_ID) === \'\'')

await ensureDeviceKey(NODE_ID) // 新设备：生成一把新的设备凭据
const deviceB = await deviceFingerprint(NODE_ID)
check('新设备拿到**不同**的指纹', Boolean(deviceB) && deviceB !== deviceA,
  `deviceB=${deviceB.slice(0, 12)}…`)

const bKeys = await cryptoProvider.inspectNodeKeys(NODE_ID)
check('★ 新设备本机没有任何该节点的密钥材料', bKeys.present === false, `algorithms=${JSON.stringify(bKeys.algorithms)}`)

// 服务端侧的第一道：新设备的私钥签出的挑战应答验不过（登记的公钥是设备 A 的）
try {
  await deviceLogin(NODE_ID)
  check('★ 新设备无法登录（服务端按设备公钥验签）', false, '竟然登录成功了 —— 设备凭据没起作用')
} catch (error) {
  check('★ 新设备无法登录（服务端按设备公钥验签）', /签名|设备/.test(String(error.message)),
    String(error.message).slice(0, 90))
}

// 服务端侧的第二道：拿有效令牌上报，但 deviceId 与已绑定的不符
const kpB = await cryptoProvider.generate('KYBER', { nodeId: NODE_ID, variant: 768 })
const rejected = await api(PQKDS, '/node-self/keys/', { method: 'POST', token, body: {
  algorithm: 'KYBER', publicKey: kpB.publicKey, deviceId: deviceB } })
check('★★ 新设备上报公钥被拒（令牌有效也拦得住）', !isOk(rejected.body),
  `code=${rejected.body?.code} msg=${String(rejected.body?.msg || '').slice(0, 70)}`)
// 判据用**可编程的错误码**，不匹配文案：文案随时会改，改一个字断言就断
check('★ 拒绝理由是"设备不一致"（可处置的业务码，不是笼统参数错）',
  rejected.body?.code === 409 && rejected.body?.data?.error_code === 'DEVICE_MISMATCH',
  `code=${rejected.body?.code} error_code=${rejected.body?.data?.error_code}`)

title('4. 同设备重试仍可通行（没有把正常路径一起挡掉）')
// 用设备 A 的指纹字符串（本机设备凭据已换成 B 的，但服务端只认"上报值 vs 已绑定值"）
const okSame = await api(PQKDS, '/node-self/keys/', { method: 'POST', token, body: {
  algorithm: 'KYBER', publicKey: kpB.publicKey, deviceId: deviceA, keyId: kpB.keyId, keyVersion: kpB.version } })
check('★ 设备一致时正常登记（幂等重试不被误拦）', isOk(okSame.body), `${okSame.body?.msg || ''}`)

title('5. 未上报 deviceId 时不做拦截（兼容旧调用方）')
const noDev = await api(PQKDS, '/node-self/keys/', { method: 'POST', token, body: {
  algorithm: 'SM2', publicKey: await (await cryptoProvider.generate('SM2', { nodeId: NODE_ID })).publicKey } })
check('不带 deviceId 时不因设备检查失败', isOk(noDev.body),
  `code=${noDev.body?.code} msg=${String(noDev.body?.msg || '').slice(0, 50)}`)

finish()
