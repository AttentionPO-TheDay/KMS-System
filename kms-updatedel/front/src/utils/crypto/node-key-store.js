/**
 * 节点本地密钥库（文档 §4.4）。
 *
 * 存的什么
 * --------
 * 节点**自己的**私密材料：Kyber / Falcon 私钥、SM2 / SSCL 的秘密份额 `u`。
 * 这些材料**只在节点侧产生和使用，永不上传** KMS / KGC。
 *
 * 为什么不放 localStorage
 * ----------------------
 * 原先的 `store/modules/keyring.js` 把 `d_A` **明文**写进 localStorage，
 * 同源任何脚本都能直接读走。本模块改存 IndexedDB，且**先加密再落库**。
 *
 * 保护密钥怎么来（这是本模块的核心决定）
 * --------------------------------------
 * 用 `crypto.subtle.generateKey(..., extractable = false)` 生成一把
 * **不可导出**的 AES-GCM 密钥，再把这个 CryptoKey 对象**直接存进 IndexedDB**
 * （结构化克隆支持 CryptoKey）。密钥的字节形式**从未存在过** ——
 * 因此同源脚本即使拿到整个数据库，也无法把保护密钥导出带走。
 *
 * ⚠️ 这条边界必须写清楚，否则后人会以为"已经安全了"：
 *    **不可导出防的是「密钥被带走」，不是「密钥被使用」。**
 *    同源 XSS 在页面内仍然可以调用 unseal() 拿到明文 ——
 *    这是纯浏览器方案**消除不了**的，也正是 CryptoProvider 抽象
 *    留给 AgentCryptoProvider（节点本地 Agent / TPM / HSM）的位置。
 *
 * ⚠️ 第二条边界：IndexedDB 按**源**隔离，用户清站点数据即丢失全部密钥。
 *    这不是缺陷 —— 它正是"密钥与设备绑定"这条要求的物理基础
 *    （见 §4.4：新设备登录时本地没有密钥材料，应重新初始化或轮换，
 *    而**不是**从服务器恢复私钥）。
 */

const DB_NAME = 'kms-node-keystore'
// ⚠️ 本模块是这座 IndexedDB 的**唯一 schema 所有者**。
//    别的模块（如 device-credential.js）只通过本模块的导出读写同一个库，
//    **不得**自己调 `indexedDB.open(name, 别的版本号)` —— 同名不同版本会互相
//    触发 VersionError，表现为"本地密钥库打不开"，且只在某些加载顺序下出现。
//    要新增 object store 就在这里加，并把版本号 +1。
//    v2：新增 STORE_DEVICE_KEYS（设备认证私钥的 CryptoKey 对象，见 device-credential.js）。
const DB_VERSION = 2
const STORE_META = 'meta'
const STORE_KEYS = 'keys'
const STORE_DEVICE_KEYS = 'deviceKeys'

const META_PROTECTOR = 'protector'
const META_DEVICE = 'deviceId'

/** 私密材料在库里的形状：`{ keyRef, algorithm, version, deviceId, publicKey, iv, sealed, createdAt }` */
const textEncoder = new TextEncoder()

let dbPromise = null

function openDb() {
  if (dbPromise) {
    return dbPromise
  }
  dbPromise = new Promise((resolve, reject) => {
    if (typeof indexedDB === 'undefined') {
      reject(new Error('当前环境不支持 IndexedDB，无法建立节点本地密钥库'))
      return
    }
    const request = indexedDB.open(DB_NAME, DB_VERSION)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(STORE_META)) {
        db.createObjectStore(STORE_META, { keyPath: 'k' })
      }
      if (!db.objectStoreNames.contains(STORE_KEYS)) {
        db.createObjectStore(STORE_KEYS, { keyPath: 'keyRef' })
      }
      if (!db.objectStoreNames.contains(STORE_DEVICE_KEYS)) {
        // 设备认证私钥的 CryptoKey **对象**（不可导出，字节形式从未存在过）。
        // 单独一个 store 而不是塞进 keys：keys 里的记录都要走
        // 「AES-GCM 加密后存字节」那条路，而 CryptoKey 对象是结构化克隆直存的，
        // 两种形态混在一个 store 里，读取方要先判断类型才能决定怎么解 ——
        // 那是"看起来能用、出错时极难定位"的设计。
        db.createObjectStore(STORE_DEVICE_KEYS, { keyPath: 'keyRef' })
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(new Error(`打开本地密钥库失败：${request.error?.message || '未知错误'}`))
  })
  return dbPromise
}

function tx(storeName, mode, run) {
  return openDb().then(
    (db) =>
      new Promise((resolve, reject) => {
        const transaction = db.transaction(storeName, mode)
        const store = transaction.objectStore(storeName)
        let result
        try {
          result = run(store)
        } catch (error) {
          reject(error)
          return
        }
        transaction.oncomplete = () => resolve(result)
        transaction.onerror = () => reject(new Error(transaction.error?.message || '本地密钥库操作失败'))
        transaction.onabort = () => reject(new Error('本地密钥库操作被中止'))
      })
  )
}

function req(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(new Error(request.error?.message || 'IndexedDB 请求失败'))
  })
}

function metaGet(key) {
  return tx(STORE_META, 'readonly', (store) => req(store.get(key)))
}

function metaPut(value) {
  return tx(STORE_META, 'readwrite', (store) => req(store.put(value)))
}

/**
 * 取（或首次生成）保护密钥。
 *
 * `extractable: false` 是这个模块存在的理由本身 —— 不要"为了方便调试"改成 true：
 * 一旦可导出，同源脚本就能把密钥取走并离线解开整库，
 * 本模块相对 localStorage 明文的那点优势会**全部消失**，而代码看不出区别。
 */
async function getOrCreateProtector() {
  const existing = await metaGet(META_PROTECTOR)
  if (existing?.key) {
    return existing.key
  }
  if (!globalThis.crypto?.subtle) {
    throw new Error('当前环境不支持 WebCrypto，无法建立加密的本地密钥库')
  }
  const key = await crypto.subtle.generateKey(
    { name: 'AES-GCM', length: 256 },
    false, // ← 不可导出，见上方说明
    ['encrypt', 'decrypt']
  )
  await metaPut({ k: META_PROTECTOR, key })
  return key
}

/** 本设备的标识。随机生成后持久化，用于"密钥与设备绑定"。 */
async function getDeviceId() {
  const existing = await metaGet(META_DEVICE)
  if (existing?.value) {
    return existing.value
  }
  const id = crypto.randomUUID ? crypto.randomUUID() : `dev-${Date.now()}-${Math.random().toString(36).slice(2)}`
  await metaPut({ k: META_DEVICE, value: id })
  return id
}

/**
 * 把一份私密材料加密后写入密钥库。
 *
 * @param {string} keyRef        逻辑引用（调用方用来再取回；建议用 key_id 或节点内唯一名）
 * @param {object} input
 * @param {string} input.algorithm 算法名
 * @param {Uint8Array|string} input.secret 私密材料本体（字节或 hex/base64 文本）
 * @param {string} [input.publicKey] 对应公钥 —— **公开量，明文存**，便于不解封就能列出
 * @param {number} [input.version]
 * @returns {Promise<object>} 落库后的记录（**不含明文**）
 */
export async function sealSecret(keyRef, { algorithm, secret, publicKey = '', version = 1 }) {
  if (!keyRef) {
    throw new Error('缺少 keyRef：本地密钥库的每条记录都必须能被再取回')
  }
  const bytes = typeof secret === 'string' ? textEncoder.encode(secret) : secret
  if (!bytes || !bytes.length) {
    throw new Error('私密材料为空，拒绝写入 —— 存一条空记录只会让"为什么解不开"变成一个查不出来的问题')
  }
  const protector = await getOrCreateProtector()
  // 每次都用新的随机 IV：AES-GCM 下 IV 重用会直接毁掉机密性，且**不会报错**
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const sealed = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, protector, bytes)
  const deviceId = await getDeviceId()

  const record = {
    keyRef: String(keyRef),
    algorithm: String(algorithm || '').toUpperCase(),
    version: Number(version) || 1,
    deviceId,
    publicKey: String(publicKey || ''),
    iv,
    sealed,
    createdAt: new Date().toISOString()
  }
  await tx(STORE_KEYS, 'readwrite', (store) => req(store.put(record)))
  // 返回值刻意**不带 sealed/iv 之外的任何东西**也只是形式；
  // 真正要守住的是：调用方拿不到 secret —— 它只在上面那个闭包里存在过。
  return { ...record, sealed: undefined, iv: undefined }
}

/**
 * 取回并解密一份私密材料。
 *
 * @returns {Promise<Uint8Array>} 明文
 * @throws 记录不存在、或解密失败（保护密钥换了 / 数据被改动）时抛出
 */
export async function unsealSecret(keyRef) {
  const record = await tx(STORE_KEYS, 'readonly', (store) => req(store.get(String(keyRef))))
  if (!record) {
    throw new Error(`本地密钥库中没有 ${keyRef} 的记录`)
  }
  const protector = await getOrCreateProtector()
  try {
    const plain = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: record.iv },
      protector,
      record.sealed
    )
    return new Uint8Array(plain)
  } catch {
    // GCM 校验失败 → 要么保护密钥不是当初那把（用户清了元数据但没清记录），
    // 要么数据被改过。两种都不该"尽力而为"地返回半截内容。
    throw new Error(`本地密钥库中的 ${keyRef} 解密失败：保护密钥不匹配或数据已被改动`)
  }
}

/** 该记录是否存在于本地密钥库 */
export async function hasSecret(keyRef) {
  const record = await tx(STORE_KEYS, 'readonly', (store) => req(store.get(String(keyRef))))
  return Boolean(record)
}

/** 列出全部记录摘要（**不含任何私密材料**，用于界面展示与设备绑定判断） */
export async function listSecrets() {
  const all = await tx(STORE_KEYS, 'readonly', (store) => req(store.getAll()))
  return (all || []).map((r) => ({
    keyRef: r.keyRef,
    algorithm: r.algorithm,
    version: r.version,
    deviceId: r.deviceId,
    publicKey: r.publicKey,
    createdAt: r.createdAt
  }))
}

export async function removeSecret(keyRef) {
  await tx(STORE_KEYS, 'readwrite', (store) => req(store.delete(String(keyRef))))
}

// ---------------------------------------------------------------------------
// 设备认证密钥（文档 §3.1 / §5）
// ---------------------------------------------------------------------------
// 与上面那批的区别：这里存的是 **CryptoKey 对象本身**（结构化克隆直存），
// 不是"加密后的字节"。因为设备私钥以 `extractable: false` 生成，
// **根本没有字节形态可取** —— 这正是它比"加密后存盘"更强的地方：
// 同源脚本即使拿到整座数据库，也无法把私钥导出带走。

/**
 * 写入某节点的设备认证密钥对。
 *
 * ⚠️ 只允许本模块写这个 store —— 其它地方要存设备凭据请走
 *    `device-credential.js` 的 `ensureDeviceKey()`，
 *    不要自己 open 数据库（同库不同版本会 VersionError）。
 */
export async function putDeviceKeyPair(keyRef, keyPair) {
  await tx(STORE_DEVICE_KEYS, 'readwrite', (store) => req(store.put({
    keyRef: String(keyRef),
    publicKey: keyPair.publicKey,
    privateKey: keyPair.privateKey,
    createdAt: new Date().toISOString(),
  })))
}

/** 取设备认证私钥（CryptoKey）；不存在或损坏返回 null。 */
export async function getDevicePrivateKey(keyRef) {
  try {
    const record = await tx(STORE_DEVICE_KEYS, 'readonly', (store) => req(store.get(String(keyRef))))
    return record?.privateKey || null
  } catch {
    return null
  }
}

/** 取设备认证公钥（CryptoKey）；不存在返回 null。 */
export async function getDevicePublicKey(keyRef) {
  try {
    const record = await tx(STORE_DEVICE_KEYS, 'readonly', (store) => req(store.get(String(keyRef))))
    return record?.publicKey || null
  } catch {
    return null
  }
}

/** 删除设备认证密钥对（幂等）。 */
export async function removeDeviceKeyPair(keyRef) {
  await tx(STORE_DEVICE_KEYS, 'readwrite', (store) => req(store.delete(String(keyRef))))
}

/**
 * 列出所有设备认证密钥的 keyRef。
 *
 * ⚠️ 它读的是 `deviceKeys` store，**不是** `listSecrets()` 读的那个 `keys` store。
 *    两者装的东西不同：`keys` 是「加密后的字节」，`deviceKeys` 是 CryptoKey 对象。
 *    混用会得到恒空的结果 —— 而且不报错，只是列表莫名其妙没东西。
 */
export async function listDeviceKeyRefs() {
  try {
    const all = await tx(STORE_DEVICE_KEYS, 'readonly', (store) => req(store.getAll()))
    return (all || []).map((r) => String(r.keyRef || '')).filter(Boolean)
  } catch {
    return []
  }
}

/**
 * 清空整个密钥库（含保护密钥与设备标识）。
 *
 * ⚠️ 调用方必须清楚后果：清掉之后**本设备再也解不开**已分发的信封，
 *    且按 §4.4 的要求，**不从服务器恢复私钥** —— 只能重新初始化或轮换。
 *    所以这个函数不该出现在任何"顺手清理"的路径上。
 */
export async function clearAll() {
  await tx(STORE_KEYS, 'readwrite', (store) => req(store.clear()))
  await tx(STORE_META, 'readwrite', (store) => req(store.clear()))
}

/** 供测试用：确认保护密钥确实不可导出 */
export async function assertProtectorNotExportable() {
  const protector = await getOrCreateProtector()
  try {
    await crypto.subtle.exportKey('raw', protector)
  } catch {
    return true
  }
  return false
}

/**
 * 本机是否持有该节点的密钥材料（§4.4 设备绑定的判断基础）。
 *
 * 判据是"**任意一套**基础密钥在不在本机"，而不是"四套都在"：
 * 初始化可能做到一半（比如生成完 SM2 就断网了），
 * 那种情况下本机**确实**有材料，只是不全 —— 与"新设备什么都没有"
 * 是两回事，处置也不同（前者续做，后者要重新初始化）。
 *
 * @param {string} nodeId 节点编号（前端生成密钥时用它拼 keyRef）
 * @returns {Promise<{present: boolean, algorithms: string[]}>}
 */
export async function inspectNodeKeys(nodeId) {
  const suffix = `-${String(nodeId || '').trim()}`
  if (!suffix.trim() || suffix === '-') {
    return { present: false, algorithms: [] }
  }
  const all = await listSecrets()
  const mine = all.filter((r) => String(r.keyRef || '').endsWith(suffix))
  return {
    present: mine.length > 0,
    algorithms: mine.map((r) => r.algorithm),
  }
}

export { getDeviceId, STORE_DEVICE_KEYS, DB_NAME }