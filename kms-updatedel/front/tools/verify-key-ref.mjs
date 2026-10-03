#!/usr/bin/env node
/**
 * KMS-003 本地密钥引用（keyRef）格式的验收
 * =============================================================================
 * 判据都是"用户真的走得通"，不是"函数存在"：
 *
 *   1. `key-ref.js` 的构造/解析：`/` 分段、算法归一、版本严格、旧格式一律 null；
 *   2. `NodeKeyStore` 封存即校验：旧格式 `node-N1-KYBER` 与裸名 `probe-1` 被拒绝，
 *      而不是"写进去了、之后永远查不到"—— 静默查不到正是本次要根除的东西；
 *   3. 规范文本与空白口径：可解析但非规范的写法（`kyber_kem`、大小写混杂、
 *      首尾空白）不产生"写进去一串、查的是另一串"的第二份拼写 —— 写入重建落库、
 *      读/删侧共用同一条规则（同一别名文本回读/解封/删除同样命中），
 *      写侧拒绝的文本（旧格式/裸名/含空白）在读/删侧同样抛错而不是静默放过；
 *   4. `importSecret` 返回**落库后**的 ref（返回入参那份会让调用方静默查不到）；
 *   5. `clearAll` 的边界：长期材料清空、**设备凭据刻意保留**（清掉 = 已激活
 *      设备再也登录不上）；
 *   6. v2 → v3 迁移：旧记录换 ref 后**密文逐字节不变、原明文仍能解出**。
 *      只改元数据、不解密重封，是这条迁移最容易被"顺手改成解一遍再存"的地方，
 *      所以子进程验收里真的执行一次 `unsealSecret`。
 *
 * 为什么迁移用例要跑在子进程里
 * ----------------------------
 * 升级只在"库的版本比代码低"时发生，而 fake-indexeddb 在同一个进程里打开过 v3 后，
 * 就再也造不出 v2 现场。只有独立进程能先种 v2、再加载模块触发升级 ——
 * 这也正是浏览器里真实发生的顺序（老用户的库是 v2，代码先加载、首次用库时升级）。
 *
 * 本脚本导入 browser-provider.js 只为验证 `importSecret` 的返回值语义（第 4 节）；
 * gm-crypto / crystals-kyber 都是惰性动态 import，测试路径碰不到，Node 下直接可跑。
 *
 * 用法（不需要 docker）：
 *     cd kms-updatedel/front && node tools/verify-key-ref.mjs
 */
import 'fake-indexeddb/auto'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const HERE = fileURLToPath(import.meta.url)

const results = []
const check = (name, pass, detail = '') => {
  results.push({ name, pass, detail })
  console.log(`  ${pass ? '[PASS]' : '[FAIL]'} ${name}${detail ? '  → ' + detail : ''}`)
}

const j = (value) => JSON.stringify(value)
const hex = (buf) => (buf ? [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('') : '')
const text = (buf) => new TextDecoder().decode(buf)

/** 跑一个应当抛错的调用，返回捕获到的错误；没抛返回 null。 */
async function caught(run) {
  try {
    await run()
    return null
  } catch (error) {
    return error
  }
}

if (process.argv.includes('--migration-child')) {
  await runMigrationChild()
} else {
  await runParent()
}

const pass = results.filter((r) => r.pass).length
console.log(`\n=== 结果：${pass}/${results.length} 项通过 ===`)
if (pass !== results.length) {
  results.filter((r) => !r.pass).forEach((r) => console.log(`  - ${r.name}  ${r.detail}`))
  process.exitCode = 1
}

// ===========================================================================
// 父进程：构造/解析、封存校验、存储行为，最后拉起子进程跑迁移
// ===========================================================================
async function runParent() {
  const ref = await import('../src/utils/crypto/key-ref.js')
  const store = await import('../src/utils/crypto/node-key-store.js')

  console.log('\n=== 1. 构造 / 解析：格式只有一处实现 ===')
  const built = ref.buildKeyRef({ nodeId: 'N1', algorithm: 'KYBER', keyId: 'k1', version: 1 })
  check('buildKeyRef 产出 node/{nodeId}/{算法}/{keyId}/{版本}', built === 'node/N1/KYBER/k1/1', built)
  const roundTrip = ref.parseKeyRef(built)
  check(
    'parseKeyRef 往返得到同一组分段',
    j(roundTrip) === j({ kind: 'node', nodeId: 'N1', algorithm: 'KYBER', keyId: 'k1', version: 1 }),
    j(roundTrip)
  )

  // 别名归一：库里历史写法混杂（kyber_kem / gm_sm2 / cl-falcon），
  // 进 ref 必须变成规范大写名，否则"同一把密钥两种拼写"又是第二份口径。
  check(
    '算法别名在构造时归一为大写规范名（kyber_kem → KYBER）',
    ref.buildKeyRef({ nodeId: 'N1', algorithm: 'kyber_kem', keyId: 'k1', version: 1 }) === 'node/N1/KYBER/k1/1'
  )
  check('解析时 gm_sm2 → SM2', ref.parseKeyRef('node/N1/gm_sm2/k1/1')?.algorithm === 'SM2')
  check('解析时 cl-falcon → FALCON', ref.parseKeyRef('node/N1/cl-falcon/k1/1')?.algorithm === 'FALCON')

  check('DEVICE_AUTH_ALGORITHM 与后端 node_auth_views 同值', ref.DEVICE_AUTH_ALGORITHM === 'ECDSA-P256', ref.DEVICE_AUTH_ALGORITHM)
  check('DEVICE_PUB_SUFFIX 与设备公钥副本命名同值', ref.DEVICE_PUB_SUFFIX === '-pub', ref.DEVICE_PUB_SUFFIX)

  // "/" 是分段符：含 "/" 的段会让切段错位，而错位不报错、只表现为"找不到密钥"。
  // 所以必须在构造入口就拒绝，而不是等到查询时才莫名查不到。
  const slashNode = await caught(() => ref.buildKeyRef({ nodeId: 'N/1', algorithm: 'KYBER', keyId: 'k1', version: 1 }))
  check(
    'nodeId 含 "/" 时抛 KeyRefError / INVALID_PARAMETER',
    slashNode instanceof ref.KeyRefError && slashNode.code === ref.ERR_INVALID_PARAMETER,
    slashNode?.message
  )
  const slashKey = await caught(() => ref.buildKeyRef({ nodeId: 'N1', algorithm: 'KYBER', keyId: 'k/1', version: 1 }))
  check('keyId 含 "/" 时抛 KeyRefError', slashKey instanceof ref.KeyRefError && slashKey.code === ref.ERR_INVALID_PARAMETER)
  const emptyNode = await caught(() => ref.buildKeyRef({ nodeId: '', algorithm: 'KYBER', keyId: 'k1', version: 1 }))
  check('空 nodeId 被拒绝（引用必须能定位到具体节点）', emptyNode instanceof ref.KeyRefError)

  for (const [label, badVersion] of [['0', 0], ['1.5', 1.5], ["'x'", 'x'], ["'1'（字符串）", '1']]) {
    const err = await caught(() => ref.buildKeyRef({ nodeId: 'N1', algorithm: 'KYBER', keyId: 'k1', version: badVersion }))
    check(`版本 ${label} 被拒绝（必须 ≥1 的整数）`, err instanceof ref.KeyRefError, err ? '' : '没有抛错')
  }
  const aes = await caught(() => ref.buildKeyRef({ nodeId: 'N1', algorithm: 'AES', keyId: 'k1', version: 1 }))
  check(
    "不认识的算法 'AES' 被拒绝（白名单只有 SM2/SSCL/KYBER/FALCON）",
    aes instanceof ref.KeyRefError && aes.code === ref.ERR_INVALID_PARAMETER,
    aes?.message
  )

  // 解析器不宽容：越宽容，错格式越晚暴露，而晚暴露 = 静默找不到密钥。
  const nullCases = [
    ['旧格式 node-N1-KYBER（无 "/"）', 'node-N1-KYBER'],
    ['垃圾串 junk', 'junk'],
    ['空串', ''],
    ['null', null],
    ['段数不足 node/N1/KYBER/k1', 'node/N1/KYBER/k1'],
    ['段数过多 node/N1/KYBER/k1/1/extra', 'node/N1/KYBER/k1/1/extra'],
    ['版本 0', 'node/N1/KYBER/k1/0'],
    ['版本不是整数 node/N1/KYBER/k1/1.5', 'node/N1/KYBER/k1/1.5'],
    ['版本带空格 node/N1/KYBER/k1/"1 "', 'node/N1/KYBER/k1/1 '],
    ['不认识的算法 node/N1/AES/k1/1', 'node/N1/AES/k1/1']
  ]
  const nullFailures = nullCases.filter(([, value]) => ref.parseKeyRef(value) !== null)
  check('旧格式 / 垃圾 / 空 / 段数错 / 版本错一律返回 null（不 trim、不宽容）', nullFailures.length === 0, nullFailures.map(([label]) => label).join('、'))

  check('parseKeyRef 识别设备 ref（kind:device）', j(ref.parseKeyRef('node-N1-device-auth')) === j({ kind: 'device', nodeId: 'N1', pub: false }))
  check('parseKeyRef 识别公钥副本（pub:true）', j(ref.parseKeyRef('node-N1-device-auth-pub')) === j({ kind: 'device', nodeId: 'N1', pub: true }))
  const dashed = ref.parseKeyRef('node-A-B-device-auth-pub')
  check('节点编号含 "-" 时设备 ref 仍解析正确（贪婪回溯 → id=A-B）', dashed?.kind === 'device' && dashed.nodeId === 'A-B' && dashed.pub === true, j(dashed))

  // 已激活设备的登录凭据就是这串字节，差一个字符 = 所有老设备登录不上。
  check('buildDeviceRef 与历史字符串逐字节一致', ref.buildDeviceRef('N1') === 'node-N1-device-auth', ref.buildDeviceRef('N1'))
  check('公钥副本带 -pub 后缀', ref.buildDeviceRef('N1', { pub: true }) === 'node-N1-device-auth-pub', ref.buildDeviceRef('N1', { pub: true }))
  const noNode = await caught(() => ref.buildDeviceRef(''))
  check('设备 ref 缺节点编号时抛错', noNode instanceof ref.KeyRefError, noNode?.message)
  check('parseDeviceRef 对长期密钥 ref 返回 null', ref.parseDeviceRef('node/N1/KYBER/k1/1') === null)

  // keyId 形状镜像后端 node_key_registry.new_key_id()：{safe_node}-{ALGO}-{8位小写hex}
  const minted = ref.mintKeyId('N1', 'KYBER')
  check('mintKeyId 形状与后端 new_key_id 一致', /^N1-KYBER-[0-9a-f]{8}$/.test(minted), minted)
  const mintedSafe = ref.mintKeyId('N/1 x', 'SM2')
  check('mintKeyId 把不安全字符替换为 "-"（keyId 里绝不能出现 "/"）', /^N-1-x-SM2-[0-9a-f]{8}$/.test(mintedSafe), mintedSafe)

  console.log('\n=== 2. 封存即校验：旧格式与裸名一律拒绝 ===')
  const oldRef = await caught(() => store.sealSecret('node-N1-KYBER', { algorithm: 'KYBER', secret: 'SHOULD-NOT-BE-STORED' }))
  check(
    '旧格式 ref 被拒绝（KeyRefError / INVALID_PARAMETER）',
    oldRef instanceof ref.KeyRefError && oldRef.code === ref.ERR_INVALID_PARAMETER,
    oldRef?.message
  )
  const bare = await caught(() => store.sealSecret('probe-1', { secret: 'SHOULD-NOT-BE-STORED' }))
  check('裸名 ref（probe-1）被拒绝 —— 旧写法会静默存成永远查不到的记录', bare instanceof ref.KeyRefError, bare?.message)

  const algoClash = await caught(() => store.sealSecret('node/N1/KYBER/k1/1', { algorithm: 'FALCON', secret: 'x' }))
  check(
    '算法与 ref 冲突时抛 INVALID_PARAMETER（ref 是唯一权威，不悄悄纠正）',
    algoClash instanceof ref.KeyRefError && algoClash.code === ref.ERR_INVALID_PARAMETER,
    algoClash?.message
  )
  const verClash = await caught(() => store.sealSecret('node/N1/KYBER/k1/1', { version: 2, secret: 'x' }))
  check(
    '版本与 ref 冲突时抛 KEY_VERSION_MISMATCH',
    verClash instanceof ref.KeyRefError && verClash.code === ref.ERR_KEY_VERSION_MISMATCH,
    verClash?.message
  )
  const emptySecret = await caught(() => store.sealSecret('node/N1/KYBER/k1/1', { secret: '' }))
  check('空私密材料仍被拒绝（既有约束不放宽）', emptySecret instanceof Error)

  // 设备命名空间：算法不进长期密钥白名单，默认就是设备凭据算法。
  const devicePlain = JSON.stringify({ crv: 'P-256', x: 'aa', y: 'bb' })
  const deviceRecord = await store.sealSecret('node-N1-device-auth-pub', { secret: devicePlain })
  check(
    '设备 ref 可封存，算法默认 ECDSA-P256、kind=device（独立命名空间）',
    deviceRecord.kind === 'device' && deviceRecord.algorithm === ref.DEVICE_AUTH_ALGORITHM && deviceRecord.nodeId === 'N1',
    `algorithm=${deviceRecord.algorithm}`
  )
  check('设备 ref 取回逐字节还原', text(await store.unsealSecret('node-N1-device-auth-pub')) === devicePlain)
  // 设备 ref 是字节契约，不参与读侧规范化（别名重建只针对 node ref）。
  check('设备 ref 的查询同样原样（不被规范化碰）', await store.hasSecret('node-N1-device-auth-pub'))

  console.log('\n=== 3. 存储与查询：按段精确相等（旧实现的后缀匹配正是缺陷根源） ===')
  await store.sealSecret('node/NODE-A/KYBER/kA/1', { secret: 'A-KYBER-material', publicKey: 'pk-a' })
  await store.sealSecret('node/NODE-A/KYBER/k1/3', { secret: 'A-KYBER-v3-material' })
  await store.sealSecret('node/NODE-A-B/KYBER/kAB/1', { secret: 'AB-KYBER-material', publicKey: 'pk-ab' })

  const insA = await store.inspectNodeKeys('NODE-A')
  const insAB = await store.inspectNodeKeys('NODE-A-B')
  check('★ NODE-A 能查到自己（旧实现 endsWith 恒不命中 → 永远 present:false）', insA.present === true, `keys=${insA.keys.length}`)
  check('算法集合去重（两条 KYBER 只报一个）', j(insA.algorithms) === j(['KYBER']), j(insA.algorithms))
  check('每条 key 的 nodeId 都精确等于查询的节点', insA.keys.length === 2 && insA.keys.every((k) => k.nodeId === 'NODE-A'))
  check('前缀陷阱：NODE-A 的结果里没有 NODE-A-B 的记录', !insA.keys.some((k) => k.keyRef.includes('NODE-A-B')))
  check(
    '前缀陷阱反向：NODE-A-B 只看到自己（A 与 A-B 不再互相串）',
    insAB.keys.length === 1 && insAB.keys[0].nodeId === 'NODE-A-B' && insAB.keys[0].keyId === 'kAB'
  )
  const emptyInspect = await store.inspectNodeKeys('')
  check(
    '空 nodeId 返回空结果，而不是退化成全量',
    emptyInspect.present === false && emptyInspect.keys.length === 0 && emptyInspect.algorithms.length === 0
  )

  const meta = await store.requireLocalKey('node/NODE-A/KYBER/k1/3', { nodeId: 'NODE-A', algorithm: 'KYBER', version: 3 })
  check('requireLocalKey 命中：版本/算法/归属全一致，version 原样带出', meta.version === 3 && meta.keyId === 'k1' && meta.nodeId === 'NODE-A' && meta.kind === 'node')
  check('返回的元信息里没有 iv / sealed（私密材料不出库）', !('sealed' in meta) && !('iv' in meta))

  const cases = [
    ['★ 引用不存在 → KEY_LOCAL_MISSING', 'node/NODE-A/KYBER/nope/1', {}, ref.ERR_KEY_LOCAL_MISSING],
    ['节点归属不符 → INVALID_PARAMETER', 'node/NODE-A/KYBER/kA/1', { nodeId: 'NODE-A-B' }, ref.ERR_INVALID_PARAMETER],
    ['算法不符 → INVALID_PARAMETER', 'node/NODE-A/KYBER/kA/1', { algorithm: 'FALCON' }, ref.ERR_INVALID_PARAMETER],
    ['版本不符 → KEY_VERSION_MISMATCH（不能拿旧版本顶上）', 'node/NODE-A/KYBER/k1/3', { version: 2 }, ref.ERR_KEY_VERSION_MISMATCH],
    ['旧格式 ref → INVALID_PARAMETER', 'probe-1', {}, ref.ERR_INVALID_PARAMETER],
    ['设备 ref 不是可用的长期密钥 → INVALID_PARAMETER', 'node-N1-device-auth', {}, ref.ERR_INVALID_PARAMETER]
  ]
  for (const [name, kref, expect, code] of cases) {
    const err = await caught(() => store.requireLocalKey(kref, expect))
    check(name, err instanceof ref.KeyRefError && err.code === code, err ? `${err.code}：${err.message}` : '没有抛错')
  }
  const missing = await caught(() => store.requireLocalKey('node/NODE-A/KYBER/nope/1'))
  check('KEY_LOCAL_MISSING 的提示与后端 ERROR_HINTS 同口径（含"不从服务器恢复"）', missing?.message?.includes('不从服务器恢复'), missing?.message)

  const rows = await store.listSecrets()
  const rowA = rows.find((r) => r.keyRef === 'node/NODE-A/KYBER/kA/1')
  check('listSecrets 行带 kind/nodeId/keyId（查询不再靠解析字符串）', rowA?.kind === 'node' && rowA?.nodeId === 'NODE-A' && rowA?.keyId === 'kA' && rowA?.version === 1)

  console.log('\n=== 4. 规范文本与空白口径（独立复核发现的静默失配缺口） ===')
  // 「可解析但非规范」的文本：语义一样（kyber_kem ≡ KYBER），文本不同。
  // 存原始文本 = 写进去是这一串、之后按规范 ref 查的是另一串 —— 又是静默失配
  // （复核探针实测：存别名后 hasSecret(规范 ref) 为 false，记录像"丢了"一样）。
  const aliasSealed = await store.sealSecret('node/PROBE/kyber_kem/ak/1', { secret: 'ALIAS-MATERIAL' })
  const aliasStored = await store.hasSecret('node/PROBE/KYBER/ak/1')
  check(
    '★ 别名写法（kyber_kem）封存后按规范 ref 查得到（落库文本被重建为规范形式）',
    aliasSealed.keyRef === 'node/PROBE/KYBER/ak/1' && aliasStored,
    aliasSealed.keyRef
  )

  // 反方向（第二轮复核缺陷 1）：写别名 → 用**同一别名文本**读/删也必须命中。
  // 写侧重建落库、读/删侧却按入参原文 get，就会出现同一串"封存成功、查不到"，
  // 且 removeSecret 静默 no-op（不报错、记录还在）—— 比报错更糟。
  const aliasByRaw = await store.hasSecret('node/PROBE/kyber_kem/ak/1')
  check('★ 同一别名原文回读命中（读侧与写侧共用同一条规范化规则）', aliasByRaw === true)
  check('别名原文可解封（调用方手上的入参文本能直接用来读）', text(await store.unsealSecret('node/PROBE/kyber_kem/ak/1')) === 'ALIAS-MATERIAL')
  check('别名与规范文本只对应一条记录（不会同时留下两份拼写）', (await store.listSecrets()).filter((r) => r.keyId === 'ak').length === 1)
  const aliasProbe = await caught(() => store.requireLocalKey('node/PROBE/KYBER/ak/1', { nodeId: 'PROBE', algorithm: 'KYBER', version: 1 }))
  check('requireLocalKey 对重建后的规范 ref 命中（不是"记录在、查不到"）', aliasProbe === null, aliasProbe?.message)

  // 零填充版本（`01`）：parseKeyRef 能解析（version=1），写侧落库为规范 `1`；
  // 读侧同样先重建再查 —— "能解析、行为不符"在这里收口。
  const zpSealed = await store.sealSecret('node/PROBE/SM2/zk/01', { secret: 'ZP-MATERIAL' })
  check('零填充版本 01 落库为规范 1', zpSealed.keyRef === 'node/PROBE/SM2/zk/1', zpSealed.keyRef)
  const zpProbe = await caught(() => store.requireLocalKey('node/PROBE/SM2/zk/01', { nodeId: 'PROBE', algorithm: 'SM2', version: 1 }))
  check('★ 零填充版本文本查询同样命中（可解析但不规范 ≠ 查不到）', zpProbe === null, zpProbe?.message)

  // 删除侧：非规范文本删除必须真的删掉，而不是静默 no-op。
  await store.removeSecret('node/PROBE/kyber_kem/ak/1')
  check('★ removeSecret 用别名原文删到规范记录（不再静默 no-op）', !(await store.hasSecret('node/PROBE/KYBER/ak/1')))

  // 空白口径：构造侧拒绝首尾空白，与查询侧的 trim 对齐 —— 此前构造侧不拦，
  // 复核探针实测 `node/ WS /KYBER/wk/1` 存得进、而 inspect(' WS ') 与
  // inspect('WS') **两个拼写都查不到**（存了个谁也够不着的东西）。
  const wsBuild = await caught(() => ref.buildKeyRef({ nodeId: ' WS ', algorithm: 'KYBER', keyId: 'wk', version: 1 }))
  check(
    'nodeId 首尾空白在构造入口被拒绝（拒绝而非静默 trim —— 静默纠正会让调用方以为存的是 A）',
    wsBuild instanceof ref.KeyRefError && wsBuild.code === ref.ERR_INVALID_PARAMETER,
    wsBuild?.message
  )
  const wsSeal = await caught(() => store.sealSecret('node/ WS /KYBER/wk/1', { secret: 'x' }))
  check('带空白 nodeId 的 ref 封存被拒（存得进、查不到 = 静默失配）', wsSeal instanceof ref.KeyRefError, wsSeal?.message)
  // 读/删侧与写侧同规则：写侧拒绝的文本，读/删侧不能静默当"没有这条记录"。
  const wsRead = await caught(() => store.hasSecret('node/ WS /KYBER/wk/1'))
  check(
    '读侧对带空白 ref 抛 INVALID_PARAMETER，而不是静默 false',
    wsRead instanceof ref.KeyRefError && wsRead.code === ref.ERR_INVALID_PARAMETER,
    wsRead?.message
  )
  const junkRemove = await caught(() => store.removeSecret('probe-1'))
  check('删侧对裸名 ref 抛错（删除不再静默 no-op）', junkRemove instanceof ref.KeyRefError, junkRemove?.message)
  check(
    '设备 ref 的 trim 语义保持不变（历史字节兼容：含空格仍拼出同一串）',
    ref.buildDeviceRef(' N1 ') === 'node-N1-device-auth',
    ref.buildDeviceRef(' N1 ')
  )

  // importSecret 的返回值必须是**落库后**的 ref —— 返回入参那份，调用方随后
  // 拿它去 sign/decapsulate 就会静默查不到。
  const { cryptoProvider } = await import('../src/utils/crypto/browser-provider.js')
  const imported = await cryptoProvider.importSecret('node/PROBE/kyber_kem/ak/2', { secret: 'IMPORT-MATERIAL' })
  check('importSecret 返回落库后的规范 ref（kyber_kem → KYBER）', imported.keyRef === 'node/PROBE/KYBER/ak/2', imported.keyRef)
  check('importSecret 落库后可解密（材料真的写进去了）', text(await store.unsealSecret(imported.keyRef)) === 'IMPORT-MATERIAL')
  const importClash = await caught(() => cryptoProvider.importSecret('node/PROBE/KYBER/ak/3', { algorithm: 'FALCON', secret: 'x' }))
  check(
    'importSecret 对算法冲突仍抛 INVALID_PARAMETER（既有约束不放宽）',
    importClash instanceof ref.KeyRefError && importClash.code === ref.ERR_INVALID_PARAMETER
  )

  console.log('\n=== 5. clearAll 的边界：长期材料清空、设备身份刻意保留 ===')
  // ⚠️ clearAll 会清空本进程的库 —— 本节必须**留在父进程最后**（迁移在子进程里跑，
  //    不受影响）。设备私钥是登录身份且不可导出：清掉它，这台浏览器就再也登录不上，
  //    服务端还登记着它的公钥，恢复要管理员重发激活凭证 —— 代价与"重置密钥材料"不成比例。
  await store.sealSecret('node/CL/SM2/ck/1', { secret: 'CL-MATERIAL' })
  await store.putDeviceKeyPair('node-CL-device-auth', { publicKey: 'pub', privateKey: 'priv' })
  await store.clearAll()
  check('clearAll 清掉长期密钥材料（keys store 全空）', (await store.listSecrets()).length === 0)
  check(
    '★ clearAll 保留设备凭据（清掉 = 已激活设备再也登录不上）',
    (await store.listDeviceKeyRefs()).includes('node-CL-device-auth')
  )

  console.log('\n=== 6. v2 → v3 迁移（子进程：旧 ref 就地换名、密文不重封） ===')
  let childOk = true
  let childDetail = ''
  try {
    execFileSync(process.execPath, [HERE, '--migration-child'], { stdio: 'inherit' })
  } catch (error) {
    childOk = false
    childDetail = `子进程退出码 ${error.status ?? '未知'}`
  }
  check('★ 子进程：旧格式迁移后密文未动，unsealSecret 仍能解出原明文', childOk, childDetail)
}

// ===========================================================================
// 子进程：先种一个 v2 库（老用户现场），再加载模块触发升级与迁移，最后校验
// ===========================================================================
async function runMigrationChild() {
  console.log('\n=== 6. v2 → v3 迁移（子进程内造 v2 现场，再加载模块触发升级）===')
  const DB = 'kms-node-keystore'
  const LEGACY_SECRET = 'LEGACY-SECRET-1'
  const LEGACY_SM2_SECRET = 'LEGACY-SM2-SECRET'

  // ---- 6.1 造 v2 现场：只有 v2 的三张表，记录里没有 nodeId/keyId/kind 字段 ----
  const v2 = await new Promise((resolve, reject) => {
    const request = indexedDB.open(DB, 2)
    request.onupgradeneeded = () => {
      const db = request.result
      db.createObjectStore('meta', { keyPath: 'k' })
      db.createObjectStore('keys', { keyPath: 'keyRef' })
      db.createObjectStore('deviceKeys', { keyPath: 'keyRef' })
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })

  // 保护密钥照真实形态生成（不可导出），存进 meta —— 迁移不解密，
  // 但迁移之后 unsealSecret 要用它，这一步必须是真的。
  const protector = await crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt'])
  const iv = Uint8Array.from({ length: 12 }, (_, i) => i + 1)
  const sealed = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, protector, new TextEncoder().encode(LEGACY_SECRET))
  const ivSm2 = Uint8Array.from({ length: 12 }, (_, i) => 100 + i)
  const sealedSm2 = await crypto.subtle.encrypt({ name: 'AES-GCM', iv: ivSm2 }, protector, new TextEncoder().encode(LEGACY_SM2_SECRET))

  const seeded = [
    // ① 旧格式（无版本段）—— 迁移的主对象
    { keyRef: 'node-LEG-N1-KYBER', algorithm: 'KYBER', version: 1, deviceId: 'dev-legacy', publicKey: 'aa', iv, sealed, createdAt: '2025-01-01T00:00:00.000Z' },
    // ② 旧格式且算法尾巴含数字（SM2）—— 用 [A-Za-z]+ 的正则会静默漏掉它
    { keyRef: 'node-LEG-N1-sm2', algorithm: 'SM2', version: 1, deviceId: 'dev-legacy', publicKey: 'bb', iv: ivSm2, sealed: sealedSm2, createdAt: '2025-01-02T00:00:00.000Z' },
    // ③ 已是新格式 —— 迁移必须跳过（幂等的证据在这条上）
    { keyRef: 'node/LEG-N1/FALCON/fixed-key/2', algorithm: 'FALCON', version: 2, deviceId: 'dev-legacy', publicKey: 'cc', iv, sealed, createdAt: '2025-01-03T00:00:00.000Z' },
    // ④ 设备公钥副本 —— 登录凭据的一部分，绝不能碰
    { keyRef: 'node-LEG-N1-device-auth-pub', algorithm: 'ECDSA-P256', version: 1, deviceId: 'dev-legacy', publicKey: 'DEVICE-JWK-COPY', iv, sealed, createdAt: '2025-01-04T00:00:00.000Z' },
    // ⑤ 无法解析的垃圾 —— 原样保留，不静默丢弃
    { keyRef: 'not-a-ref', algorithm: 'X', version: 1, deviceId: 'dev-legacy', publicKey: 'junk-marker', iv, sealed, createdAt: '2025-01-05T00:00:00.000Z' }
  ]
  await new Promise((resolve, reject) => {
    const tx = v2.transaction(['meta', 'keys'], 'readwrite')
    tx.objectStore('meta').put({ k: 'protector', key: protector })
    const keys = tx.objectStore('keys')
    for (const record of seeded) keys.put(record)
    tx.oncomplete = resolve
    tx.onerror = () => reject(tx.error)
  })
  v2.close()

  // ---- 6.2 关库之后才加载模块：首次用库触发 v2 → v3 升级 ----
  // 顺序是刻意的：模块若在种库前加载，就可能（现在不会、将来可能）先按 v3 打开。
  const store = await import('../src/utils/crypto/node-key-store.js')
  check(
    'PROTECTOR_META_KEY 与种子字面量一致（导出漂移会让旧库保护密钥读不出来）',
    store.PROTECTOR_META_KEY === 'protector',
    String(store.PROTECTOR_META_KEY)
  )
  const listed = await store.listSecrets()
  check('升级触发后能列出记录（迁移没有把升级事务卡死）', listed.length === 5, `记录数=${listed.length}`)

  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open(DB)
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
  const raw = await new Promise((resolve, reject) => {
    const tx = db.transaction('keys', 'readonly')
    const q = tx.objectStore('keys').getAll()
    q.onsuccess = () => resolve(q.result)
    q.onerror = () => reject(q.error)
  })
  db.close()

  const migrated = raw.find((r) => r.migratedFrom === 'node-LEG-N1-KYBER')
  check('旧 ref node-LEG-N1-KYBER 已不存在', raw.find((r) => r.keyRef === 'node-LEG-N1-KYBER') === undefined)
  check('迁移记录带 migratedFrom（能追溯它从哪来）', migrated !== undefined)
  check(
    '新 ref 形状正确：node/{nodeId}/{算法}/{keyId}/{版本}（keyId 含 legacy 标记）',
    /^node\/LEG-N1\/KYBER\/LEG-N1-KYBER-legacy-[0-9a-f]{6}\/1$/.test(migrated?.keyRef || ''),
    migrated?.keyRef || '（无迁移记录）'
  )
  check(
    '记录字段 kind=node / migrated=true / 版本保持 1',
    migrated?.kind === 'node' && migrated?.migrated === true && migrated?.version === 1 && migrated?.nodeId === 'LEG-N1'
  )
  const seg = String(migrated?.keyRef || '').split('/')
  check('记录里的 algorithm/keyId 与 ref 分段一致（没有各写一份）', migrated?.algorithm === seg[2] && migrated?.keyId === seg[3], `algorithm=${migrated?.algorithm} keyId=${migrated?.keyId}`)

  // 逐字节保留 = 迁移只动了元数据。若实现改成"解出来再封一遍"，
  // IV 会重新随机、密文会变，这条立刻失败。
  check(
    '★ iv / sealed / publicKey / deviceId / createdAt 逐字节保留（迁移 ≠ 解密重封）',
    hex(migrated?.iv) === hex(iv) &&
      hex(migrated?.sealed) === hex(sealed) &&
      migrated?.publicKey === 'aa' &&
      migrated?.deviceId === 'dev-legacy' &&
      migrated?.createdAt === '2025-01-01T00:00:00.000Z'
  )

  // 这条才是"迁移没毁掉私钥"的真证据：不解一次，永远不知道 keyId/ref 换对了没有。
  let restored = ''
  let restoreError = ''
  try {
    restored = text(await store.unsealSecret(migrated.keyRef))
  } catch (error) {
    restoreError = error.message
  }
  check('★★ 迁移后仍能解出原明文 LEGACY-SECRET-1（私钥没有被迁移毁掉）', restored === LEGACY_SECRET, restoreError || restored)

  const migratedSm2 = raw.find((r) => r.migratedFrom === 'node-LEG-N1-sm2')
  check(
    '算法尾巴含数字的旧 ref 也被迁移（SM2 —— [A-Za-z]+ 会静默漏掉它）',
    /^node\/LEG-N1\/SM2\/LEG-N1-SM2-legacy-[0-9a-f]{6}\/1$/.test(migratedSm2?.keyRef || ''),
    migratedSm2?.keyRef || '（无迁移记录）'
  )
  let sm2Plain = ''
  try {
    sm2Plain = text(await store.unsealSecret(migratedSm2.keyRef))
  } catch { /* 下面 check 报失败 */ }
  check('SM2 旧记录迁移后仍可解、算法已归一为大写', sm2Plain === LEGACY_SM2_SECRET)

  const deviceCopy = raw.find((r) => r.keyRef === 'node-LEG-N1-device-auth-pub')
  check(
    '设备凭据 ref 原样未动（已激活设备的登录凭据就是这串字节）',
    deviceCopy !== undefined && deviceCopy.publicKey === 'DEVICE-JWK-COPY' && deviceCopy.migratedFrom === undefined
  )
  const junk = raw.find((r) => r.keyRef === 'not-a-ref')
  check('无法解析的垃圾 ref 原样保留（不静默丢弃）', junk !== undefined && junk.publicKey === 'junk-marker')

  const untouched = raw.find((r) => r.keyRef === 'node/LEG-N1/FALCON/fixed-key/2')
  check(
    '已是新格式的记录被跳过：ref/版本不变、密文与 IV 未被重新封（迁移幂等）',
    untouched !== undefined && untouched.migratedFrom === undefined && untouched.version === 2 && hex(untouched.iv) === hex(iv)
  )
  check('迁移只影响该迁移的记录：恰好 2 条带 migratedFrom', raw.filter((r) => r.migratedFrom).length === 2)

  const inspected = await store.inspectNodeKeys('LEG-N1')
  check(
    '迁移后 inspectNodeKeys 能查到该节点（旧实现恒 present:false）',
    inspected.present === true && inspected.algorithms.includes('KYBER') && inspected.algorithms.includes('SM2'),
    j(inspected.algorithms)
  )
  const firstList = j((await store.listSecrets()).map((r) => r.keyRef).sort())
  const secondList = j((await store.listSecrets()).map((r) => r.keyRef).sort())
  check('再次读取不再发生改写（幂等）', firstList === secondList)
}
