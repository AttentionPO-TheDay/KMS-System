/**
 * 验证「节点初始化页」这条**界面路径**真的能走通（KMS-005 重写）。
 *
 * 为什么单独做这一条
 * ------------------
 * §4.4 的密钥生成能力是脚本验证过的，但当时 **UI 一行没改** ——
 * 页面上点"开始初始化"会直接失败（服务端只说"公钥尚未登记"），
 * 而页面不会告诉你为什么。脚本验证通过 ≠ 用户点得到。
 *
 * 所以这里不测底层能力，只测「页面里那几个函数的调用顺序能不能跑通」：
 *     管理员建节点（拿一次性激活凭证）
 *   → 本机生成设备密钥 + 激活换令牌
 *   → cryptoProvider.generate（本机生成四套）
 *   → registerSelfNodePublicKey（只上传公钥，带上 deviceId / keyId / keyVersion）
 *   → initSelfNodeKeys（收尾）
 *
 * KMS-005 改掉的两处（旧版本在这里必然失败，且失败信息指向别处）
 * --------------------------------------------------------------
 *   1. **节点口令登录不存在了**。节点账号的口令是随机生成、从不下发的
 *      （`node_account_service.py`），旧脚本那句
 *      `login(ORIGIN, '/updatedel-api', NODE_ID, 'admin123')` 现在恒失败，
 *      而现象只是"后面全 401"。唯一入口是激活凭证，见 `lib/node-session.mjs`。
 *   2. **`deviceId` 不再是浏览器随机 id**，而是**设备公钥指纹**
 *      （服务端激活时把它写进 `Node.key_device_id`）。上报时给错这一项，
 *      轻则设备守卫按"另一台设备"拒绝（409），重则两边记的不是一回事。
 *
 * 判据是"这些调用串起来能不能过"，不是"某个接口返回 200"。
 */
import { PQKDS, api, isOk, title, makeReporter, adminLogin, newNodeSession, deviceLogin, cryptoProvider } from './lib/node-session.mjs'

const { check, info, finish } = makeReporter()

title('1. 建节点 → 激活（旧的节点口令登录已不存在）')
const admin = await adminLogin()
const session = await newNodeSession(admin, { prefix: 'NUI', domainId: 'dui', permissionLevel: 'L2' })
const NODE_ID = session.nodeId
check('节点已创建并拿到激活凭证', Boolean(session.activationCode), `nodeId=${NODE_ID}`)
check('激活换到节点令牌', Boolean(session.token), `fingerprint=${session.fingerprint.slice(0, 12)}…`)
info('激活凭证是一次性的：库里只存 sha256，明文只出现这一次，用完即失效')

title('2. ★ 按 nodeInit 页的顺序走：本机生成 → 上报公钥 → 收尾')
// 与页面里的 KEY_META 顺序一致（Falcon 放最后，它最慢）
const ALGOS = [['SM2', {}], ['SSCL', {}], ['KYBER', { variant: 768 }], ['FALCON', {}]]
const localKeyIds = {}
const t0 = Date.now()
for (const [algo, opts] of ALGOS) {
  const tGen = Date.now()
  // keyRef 由 generate 自己拼（规范格式），这里不再手写字符串
  const generated = await cryptoProvider.generate(algo, { nodeId: NODE_ID, ...opts })
  const genMs = Date.now() - tGen
  check(`${algo} 本机生成`, Boolean(generated?.publicKey), `${generated.publicKey.length} hex 字符，耗时 ${genMs}ms`)
  check(`${algo} keyRef 挂在节点下（页面靠它做本机对账）`,
    String(generated.keyRef).startsWith(`node/${NODE_ID}/${algo}/`), generated.keyRef)
  localKeyIds[algo] = generated.keyId

  const up = await api(PQKDS, '/node-self/keys/', { method: 'POST', token: session.token, body: {
    algorithm: algo, publicKey: generated.publicKey,
    // 页面传的是设备公钥指纹（不是浏览器随机 id）
    deviceId: session.fingerprint,
    keyId: generated.keyId, keyVersion: generated.version,
    securityLevel: algo === 'KYBER' ? '768' : undefined } })
  check(`${algo} 公钥上报`, isOk(up.body), `${up.body?.msg || ''}`)
  // 服务端回传落库后的身份：与本地铸的那一份必须是同一串，否则从此谁也对不上谁
  check(`${algo} 服务端记下的 keyId 与本地一致`, up.body?.data?.keyId === generated.keyId,
    `server=${up.body?.data?.keyId} local=${generated.keyId}`)
}
const totalMs = Date.now() - t0
info(`四套生成+上报总耗时 ${totalMs}ms（页面文案写的是"约 2~5 秒"，需与实测相符）`)

const fin = await api(PQKDS, '/node-self/init/', { method: 'POST', token: session.token })
check('收尾成功', isOk(fin.body), `${fin.body?.msg || ''}`)
check('节点进入 ACTIVE', fin.body?.data?.node?.status === 'ACTIVE', `status=${fin.body?.data?.node?.status}`)

title('3. 页面依赖的字段都在')
const self = await api(PQKDS, '/node-self/', { token: session.token })
const n = self.body?.data?.node
check('/node-self/ 返回 node.keys（页面用它显示四套就绪状态）',
  n?.keys && ['kyber', 'falcon', 'sm2', 'sscl'].every((k) => n.keys[k] === true),
  JSON.stringify(n?.keys))
check('返回 status 供页面判断 isActive', n?.status === 'ACTIVE', `status=${n?.status}`)
check('返回 keyDeviceId（「当前节点」页展示绑定设备，采集自激活时的设备公钥指纹）',
  n?.keyDeviceId === session.fingerprint,
  `keyDeviceId=${String(n?.keyDeviceId).slice(0, 12)}… 本机指纹=${session.fingerprint.slice(0, 12)}…`)

// ★ KMS-005：初始化页生成完之后，"本机持有哪些"必须真的答得出来 ——
//   它同时是「密钥历史」页对账列的依据（present=false 会让整页显示"本机无私钥"）。
const local = await cryptoProvider.inspectNodeKeys(NODE_ID)
const localAlgos = (local.algorithms || []).map((a) => String(a).toUpperCase())
check('★ 本机认得出刚生成的这四套（密钥历史页的对账依据）',
  local.present === true && ALGOS.every(([a]) => localAlgos.includes(a)),
  `present=${local.present} algorithms=${JSON.stringify(local.algorithms)}`)
check('本机记下的 keyId 与上报的一致（服务端回传那份）',
  local.keys?.every((k) => localKeyIds[k.algorithm] === k.keyId),
  JSON.stringify((local.keys || []).map((k) => `${k.algorithm}:${k.keyId}`)))

title('4. 幂等：重复点初始化不该出错')
const again = await api(PQKDS, '/node-self/init/', { method: 'POST', token: session.token })
check('重复初始化被幂等处理', isOk(again.body) && again.body?.data?.alreadyInitialized === true,
  `alreadyInitialized=${again.body?.data?.alreadyInitialized}`)

title('5. 刷新页面后靠设备私钥重新进站（不碰激活凭证）')
// 页面刷新走的正是这条：本机那把**不可导出**的设备私钥签一个服务端给的挑战。
// 激活凭证这时早已作废，能过就说明登录凭据确实落在设备上。
const relogin = await deviceLogin(NODE_ID)
check('挑战-应答登录换到新令牌', Boolean(relogin.token), `name=${relogin.name}`)
const afterRelogin = await api(PQKDS, '/node-self/', { token: relogin.token })
check('新令牌能读到同一个节点', afterRelogin.body?.data?.node?.nodeId === NODE_ID,
  `nodeId=${afterRelogin.body?.data?.node?.nodeId}`)

finish()
