/**
 * 节点本地密钥库（文档 §4.4）。
 *
 * 存的什么
 * --------
 * 节点**自己的**私密材料：Kyber / Falcon 私钥、SM2 / SSCL 的秘密份额 `u`。
 * 这些材料**只在节点侧产生和使用，永不上传** KMS / KGC。
 *
 * 引用格式（KMS-003）
 * ------------------
 * 库里每条记录的 keyRef 一律是 `node/{nodeId}/{算法}/{keyId}/{版本}`；
 * 拼接/解析**只在 `key-ref.js`**（后端 api_contract.py 指定的前端对应物）——
 * 本文件不自己拼字符串，只在封存时校验、查询时按段精确相等过滤。
 * v3 升级会把 v2 的旧格式 ref 就地迁移（见 `migrateLegacyRefs`）。
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

import { ALGORITHMS, normalizeAlgorithm } from './provider.js'
import {
  buildKeyRef,
  parseKeyRef,
  KeyRefError,
  ERR_INVALID_PARAMETER,
  ERR_KEY_VERSION_MISMATCH,
  ERR_KEY_LOCAL_MISSING,
  DEVICE_AUTH_ALGORITHM
} from './key-ref.js'

import { KEYSTORE_DB_NAME } from '../entry-mode.js'

const DB_NAME = KEYSTORE_DB_NAME
// ⚠️ 本模块是这座 IndexedDB 的**唯一 schema 所有者**。
//    别的模块（如 device-credential.js）只通过本模块的导出读写同一个库，
//    **不得**自己调 `indexedDB.open(name, 别的版本号)` —— 同名不同版本会互相
//    触发 VersionError，表现为"本地密钥库打不开"，且只在某些加载顺序下出现。
//    要新增 object store 就在这里加，并把版本号 +1。
//    v2：新增 STORE_DEVICE_KEYS（设备认证私钥的 CryptoKey 对象，见 device-credential.js）。
//    v3：keyRef 统一为 `node/{nodeId}/{算法}/{keyId}/{版本}`（KMS-003），
//        并在升级事务里把 v2 的旧格式记录就地迁移（见 migrateLegacyRefs）。
//    v4：新增 STORE_SESSION_KEYS（会话密钥 K，KMS-012 的"解封后保存到本地
//        会话密钥库"）。它与 keys 用同一套"保护密钥加密后存字节"的形态，
//        但**不共用 keys**：keys 的记录都要能被 parseKeyRef 解析成
//        node/设备引用，而会话材料的主键是会话 ID —— 塞进 keys 会被
//        canonicalRefForLookup 拒（或更糟：被当成人造 ref 存进去、
//        永远查不出来）。
const DB_VERSION = 4
const STORE_META = 'meta'
const STORE_KEYS = 'keys'
const STORE_DEVICE_KEYS = 'deviceKeys'
const STORE_SESSION_KEYS = 'sessionKeys'

const META_PROTECTOR = 'protector'
const META_DEVICE = 'deviceId'

/** 私密材料在库里的形状：`{ keyRef, algorithm, version, deviceId, publicKey, iv, sealed, createdAt, nodeId, keyId, kind, migrated }` */
const textEncoder = new TextEncoder()

/**
 * 本机没有私钥时给调用方的处置提示。与后端
 * `api_contract.ERROR_HINTS[ERR_KEY_LOCAL_MISSING]` 是同一句话 —— 改一处要改两处，
 * 否则同一个错误在前端说"重新初始化"、在后端说"联系管理员"，而实际情况只有一个。
 */
const LOCAL_MISSING_HINT = '本机没有这把密钥的私钥。按设计私钥只在生成它的那台设备上、不从服务器恢复 —— 请改回原设备，或在本机重新初始化并回收旧密钥。'

// 历史引用格式（v2 及以前）：`node-{id}-{ALGO}`，用 `-` 分隔、无版本段。
// ⚠️ 算法尾巴必须允许数字：SM2 以 `2` 结尾，写成 `[A-Za-z]+` 会漏掉它，
//    而漏掉的表现是"这条记录没被迁移"——不报错，只是它永远匹配不上新格式查询。
const LEGACY_REF_RE = /^node-(.+)-([A-Za-z0-9]+)$/

let dbPromise = null

/** 6 位小写 hex（迁移生成的 keyId 后缀）。 */
function randomSuffix() {
  return [...crypto.getRandomValues(new Uint8Array(3))]
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('')
}

/**
 * 把 v2 的旧格式 keyRef 就地迁移成统一格式（KMS-003）。
 *
 * ⚠️⚠️ 这里**绝对不能用 `tx()` / `req()`，也不能 async/await 起新事务**。
 *    本函数在 `onupgradeneeded` 里被调用，此时 versionchange 事务尚未提交；
 *    IndexedDB 会把任何新事务排在它后面，而升级回调又在等新事务 —— 双向等待
 *    直接死锁，表现是"打开密钥库时浏览器卡住"。只允许用**升级事务自己**的
 *    `transaction.objectStore(...)`，并且只在 onsuccess 回调里链下一个请求：
 *    请求链不断，事务就还活着，全部读写都在这一个事务里完成。
 *
 * 迁移规则（幂等）：
 *   * 已能按新格式解析（parseKeyRef 返回 node kind）→ 跳过，重复运行不再改；
 *   * 旧格式且算法尾巴能归一到白名单 → 换 ref（`-legacy-` + 6 位随机 hex）；
 *   * 设备 ref（`node-{id}-device-auth[-pub]`，尾巴是 auth/pub）与无法解析的
 *     垃圾 → **原样不动**。设备 ref 那条 JWK 副本是登录凭据的一部分，绝不能碰。
 *
 * 为什么是"迁移"而不是"解密重封"：只改 keyRef/元数据字段，`iv`/`sealed`/
 * `deviceId`/`publicKey`/`createdAt` 逐字节保留 —— 密文从未被解过、再封一次，
 * 所以解出的私钥还是同一把（子进程验收里会真的 unseal 验证这一点）。
 */
function migrateLegacyRefs(transaction) {
  const store = transaction.objectStore(STORE_KEYS)
  const request = store.getAll()
  request.onerror = () => {
    // 读不到就不能猜着迁移；旧记录保持原样（之后查不到，但数据不丢）。
    console.warn('[NodeKeyStore] 旧 keyRef 迁移读取失败，本次未迁移：', request.error?.message || request.error)
  }
  request.onsuccess = () => {
    const records = request.result || []
    // 已有 ref 快照，做冲突兜底；迁移一条就换一条，保证判断基于迁移后的真实状态。
    const taken = new Set(records.map((r) => String(r.keyRef || '')))
    let migratedCount = 0
    for (const record of records) {
      const oldRef = String(record.keyRef || '')
      // 已经是新格式 → 幂等跳过（"迁移跑了第二次"走的正是这条）。
      if (parseKeyRef(oldRef)?.kind === 'node') {
        continue
      }
      const match = LEGACY_REF_RE.exec(oldRef)
      if (!match) {
        continue
      }
      const nodeId = match[1]
      const algorithm = normalizeAlgorithm(match[2])
      if (!ALGORITHMS.includes(algorithm)) {
        continue // 尾巴不是算法名 → 设备 ref 或垃圾，原样不动
      }
      const rawVersion = Number(record.version)
      const version = Number.isInteger(rawVersion) && rawVersion >= 1 ? rawVersion : 1
      const safeNode = String(nodeId).replace(/[^A-Za-z0-9_.-]/g, '-')
      let newRef = ''
      let newKeyId = ''
      let buildError = null
      // 冲突兜底：候选撞上已有 ref 就换随机后缀重试。极少发生，但发生了也
      // 绝不能覆盖别人 —— `put` 撞同一个 keyRef 是**静默覆盖**，那才是真丢记录。
      for (let attempt = 0; attempt < 5 && !newRef; attempt++) {
        const candidateKeyId = `${safeNode}-${algorithm}-legacy-${randomSuffix()}`
        let candidateRef = ''
        try {
          candidateRef = buildKeyRef({ nodeId, algorithm, keyId: candidateKeyId, version })
        } catch (error) {
          // nodeId 含 `/` 之类构不成合法新 ref 的历史记录：告警后留旧格式。
          // 它的密文还能解，只是新查询找不到 —— 但"丢了"比"找不到"严重得多。
          buildError = error
          break
        }
        if (!taken.has(candidateRef)) {
          newRef = candidateRef
          newKeyId = candidateKeyId
        }
      }
      if (!newRef) {
        console.warn(
          `[NodeKeyStore] 旧 ref ${oldRef} 未能迁移，记录保留原样：` +
          (buildError ? buildError.message : '候选 ref 连续冲突')
        )
        continue
      }
      // delete + put 在同一个升级事务里：中途失败整体回滚，不会出现
      // "旧的删了、新的没写"的半截状态。
      store.delete(oldRef)
      store.put({
        ...record,
        keyRef: newRef,
        nodeId,
        keyId: newKeyId,
        algorithm,
        kind: 'node',
        version,
        migrated: true,
        migratedFrom: oldRef
      })
      taken.delete(oldRef)
      taken.add(newRef)
      migratedCount += 1
    }
    if (migratedCount > 0) {
      console.info(`[NodeKeyStore] 已迁移 ${migratedCount} 条旧格式 keyRef 到 node/{nodeId}/{算法}/{keyId}/{版本}`)
    }
  }
}

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
    request.onupgradeneeded = (event) => {
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
      if (!db.objectStoreNames.contains(STORE_SESSION_KEYS)) {
        // KMS-012：会话密钥 K（SM4）的**本机副本**。形态与 keys 相同
        // （保护密钥 AES-GCM 封装后存字节），主键是会话 ID。
        // 它与 keys 分开的理由见文首 v4 那段：会话材料没有 keyRef。
        db.createObjectStore(STORE_SESSION_KEYS, { keyPath: 'sessionId' })
      }
      if (event.oldVersion < 3) {
        // 迁移必须用升级事务自己的 objectStore 请求完成 —— 见 migrateLegacyRefs
        // 顶部那段死锁说明。这里**不要** await 任何东西。
        migrateLegacyRefs(request.transaction)
      }
    }
    // 升级失败的原因可能是"别的标签页还开着旧连接"：此时 open 请求既不成功也不
    // 失败，**静默挂起**，页面表现成"密钥库打不开"、连报错都没有。运行旧包的
    // 标签页没有下面的让位处理，只能靠用户关掉 —— 所以这里至少把原因说出来。
    request.onblocked = () => {
      console.warn(
        '[NodeKeyStore] 本地密钥库升级被本站点其它已打开的页面占用。请关闭其它标签页 —— ' +
        '它们关闭后升级会自动继续（期间本页的密钥库操作会一直等待，不会失败）。'
      )
    }
    request.onsuccess = () => {
      const db = request.result
      // 让位处理：别的标签页要升级库时，主动关闭本连接并丢弃缓存，本页下次操作
      // 会按新版本重开。不让位的话，对方的升级会被本连接静默阻塞（见上）。
      // 中途正在跑的事务会中止并在调用方那里报错一次 —— IndexedDB 事务是原子的，
      // 不会留下半截数据。
      db.onversionchange = () => {
        db.close()
        dbPromise = null
      }
      resolve(db)
    }
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

// ---------------------------------------------------------------------------
// meta store 的**通用**读写出口（保护密钥、设备标识、绑定文件共用同一座 store）
// ---------------------------------------------------------------------------
// 为什么要开出来：本模块是这座 IndexedDB 的**唯一 schema 所有者**
// （见文首那条纪律），别的模块不得自己 `indexedDB.open`。
// 绑定文件（`node-binding.js`）与设备标识、保护密钥同住 `meta` store ——
// 它的记录形状由绑定模块自己定义，本模块只保证"存取在同一个库、同一把锁下"。

/** 读一条 meta 记录；不存在返回 null。 */
export async function readMetaRecord(key) {
  const record = await metaGet(String(key))
  return record ?? null
}

/**
 * 写一条 meta 记录。**必须带 `k`**（本 store 的主键）。
 *
 * 少写 `k` 的记录不是"报错"，是**写进去之后再也取不出来** ——
 * 读的一方只会看到"没有这条记录"，与"从没写过"完全不可区分。
 * 所以在这里拦下，而不是等调用方发现绑定莫名其妙丢了。
 */
export async function writeMetaRecord(record) {
  const key = String(record?.k ?? '')
  if (!key) {
    throw new Error('meta 记录必须带 k（主键），否则写进去取不出来')
  }
  await metaPut(record)
  return record
}

/** 删一条 meta 记录（幂等：不存在也算删成功）。 */
export async function deleteMetaRecord(key) {
  await tx(STORE_META, 'readwrite', (store) => req(store.delete(String(key))))
}

/** 按前缀列出 meta 记录（`''` = 全部）。用于"本机有哪些绑定"这类枚举。 */
export async function listMetaRecords(prefix = '') {
  const all = await tx(STORE_META, 'readonly', (store) => req(store.getAll()))
  const head = String(prefix ?? '')
  return (all || []).filter((r) => String(r?.k || '').startsWith(head))
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
 * 把一条库内记录转成对外的摘要（**不含任何私密材料**）。
 *
 * `listSecrets` 与 `requireLocalKey` 共用它，保证"单行形状"只有一处定义 ——
 * 两处各映射一遍，迟早一个多一个字段，而调用方看到的是"有时有有时没有"。
 */
function toSummary(record) {
  const parsed = parseKeyRef(record.keyRef)
  const nodeRef = parsed?.kind === 'node' ? parsed : null
  return {
    keyRef: record.keyRef,
    algorithm: record.algorithm,
    version: record.version,
    deviceId: record.deviceId,
    publicKey: record.publicKey,
    createdAt: record.createdAt,
    // 迁移前的记录（或迁移被跳过的）可能没有这些字段：能从 ref 推的就推出来，
    // 推不出来的给稳定默认值。上层拿到的形状必须一致。
    nodeId: record.nodeId || parsed?.nodeId || '',
    keyId: record.keyId !== undefined && record.keyId !== null ? record.keyId : (nodeRef?.keyId ?? null),
    kind: record.kind || parsed?.kind || '',
    migrated: record.migrated === true,
    migratedFrom: record.migratedFrom || ''
  }
}

/**
 * 把一份私密材料加密后写入密钥库。
 *
 * 引用**必须**能按规范格式解析（`node/{nodeId}/{算法}/{keyId}/{版本}`，或设备 ref）：
 * 旧格式 `node-N1-KYBER`、裸名 `probe-1` 直接拒绝；别名文本（`kyber_kem`、大小写
 * 混杂）按解析结果**重建为规范文本落库** —— 存原样会让"写的那串"与"查的那串"
 * 只要有一处不一致就静默失配。
 * 封存即校验：node ref 的 algorithm/version **以 ref 为唯一权威** ——
 * 调用方显式传了不一致的值就抛 `KeyRefError`。既不"以参数为准"，也不
 * "悄悄纠正"：静默纠正会让调用方以为写入的是 A、实际是 B，
 * 之后版本检查报错还找不到原因。
 *
 * @param {string} keyRef  规范引用。旧格式 `node-N1-KYBER`、裸名 `probe-1` 一律拒绝；
 *   别名文本可解析但会按解析结果重建后落库，不会存成第二份拼写
 * @param {object} input
 * @param {string} [input.algorithm] 算法名；node ref 可省略（从 ref 派生），给了就必须与 ref 一致
 * @param {Uint8Array|string} input.secret 私密材料本体（字节或 hex/base64 文本）
 * @param {string} [input.publicKey] 对应公钥 —— **公开量，明文存**，便于不解封就能列出
 * @param {number} [input.version] 版本；node ref 可省略（从 ref 派生），给了就必须与 ref 一致
 * @returns {Promise<object>} 落库后的记录（**不含明文**）
 */
export async function sealSecret(keyRef, { algorithm, secret, publicKey = '', version } = {}) {
  const ref = String(keyRef ?? '')
  const parsed = parseKeyRef(ref)
  if (!parsed) {
    throw new KeyRefError(`不是规范的本地密钥引用：${ref}（应为 node/{nodeId}/{算法}/{keyId}/{版本}）`)
  }
  // version 的默认值刻意**不是** 1 而是"未传"：否则 ref 里写着 v3、调用方
  // 没传 version 时会被默认的 1 判成冲突，而正确语义是"从 ref 派生"。
  let resolvedAlgorithm = ''
  let resolvedVersion = 1
  if (parsed.kind === 'node') {
    if (algorithm != null && String(algorithm).trim() !== '') {
      const given = normalizeAlgorithm(algorithm)
      if (given !== parsed.algorithm) {
        throw new KeyRefError(
          `算法与 ref 冲突：ref 是 ${parsed.algorithm}，调用方传的是 ${given}（ref 是唯一权威，不要传与 ref 不符的算法）`
        )
      }
    }
    if (version !== undefined && version !== null) {
      const given = Number(version)
      if (!Number.isInteger(given) || given < 1) {
        throw new KeyRefError(`版本号必须是 ≥1 的整数：${version}`)
      }
      if (given !== parsed.version) {
        throw new KeyRefError(
          `版本与 ref 冲突：ref 是 v${parsed.version}，调用方传的是 v${given}（同一 keyId 的版本以 ref 为准）`,
          ERR_KEY_VERSION_MISMATCH
        )
      }
    }
    resolvedAlgorithm = parsed.algorithm
    resolvedVersion = parsed.version
  } else {
    // 设备命名空间：算法名不归一化、不进白名单 —— 设备凭据是独立体系，
    // 别把 ECDSA-P256 之外的能力焊死（见 key-ref.js 的文件头）。
    resolvedAlgorithm = String(algorithm || DEVICE_AUTH_ALGORITHM).toUpperCase()
    if (version !== undefined && version !== null) {
      const given = Number(version)
      if (!Number.isInteger(given) || given < 1) {
        throw new KeyRefError(`版本号必须是 ≥1 的整数：${version}`)
      }
      resolvedVersion = given
    }
  }

  // ref 的**语义**由 parseKeyRef 唯一确定，但**文本形态**可能是别名写法
  // （`kyber_kem`、大小写混杂）。若原样存文本，写进去的是这一串、之后按规范
  // ref 查的是另一串 —— 记录其实存在却报 KEY_LOCAL_MISSING，又回到"存得进、
  // 查不到"的静默失配（独立复核用探针实测过）。所以 node ref 一律按解析结果
  // 重建规范文本落库；「ref 是唯一权威」不受影响 —— 各字段仍全部取自 ref。
  // 设备 ref 是**字节契约**（已激活浏览器的登录凭据），原样保留、绝不重建。
  const canonicalRef = parsed.kind === 'node' ? buildKeyRef(parsed) : ref
  if (parsed.kind === 'node' && canonicalRef !== ref) {
    console.info(`[NodeKeyStore] keyRef 文本已规范化后落库：${ref} → ${canonicalRef}`)
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
    keyRef: canonicalRef,
    algorithm: resolvedAlgorithm,
    version: resolvedVersion,
    deviceId,
    publicKey: String(publicKey || ''),
    iv,
    sealed,
    createdAt: new Date().toISOString(),
    // 以下四个字段是 KMS-003 的记录身份信息：查询（inspectNodeKeys /
    // requireLocalKey）按 kind + nodeId 精确相等过滤，不再做任何后缀匹配。
    nodeId: parsed.nodeId,
    keyId: parsed.kind === 'node' ? parsed.keyId : null,
    kind: parsed.kind,
    migrated: false
  }
  await tx(STORE_KEYS, 'readwrite', (store) => req(store.put(record)))
  // 返回值刻意**不带 sealed/iv 之外的任何东西**也只是形式；
  // 真正要守住的是：调用方拿不到 secret —— 它只在上面那个闭包里存在过。
  return { ...record, sealed: undefined, iv: undefined }
}

/**
 * 把**查询/删除**入参规范成库内实际存的文本 —— 与 `sealSecret` 的落库规则同一条。
 *
 * 为什么读侧也要做：写侧把可解析的别名文本重建为规范文本落库之后，读/删侧若仍按
 * 入参原文 `store.get`，就会出现反方向的"存得进、同一串查不到"——
 * `sealSecret('node/N1/kyber_kem/k/1', …)` 成功，而用**同一别名文本**回读为 false、
 * `removeSecret` 静默 no-op（第二轮独立复核实测）。所以：
 *   - 可解析的 node ref → 按解析结果重建规范文本（与写入落在同一文本上）；
 *   - 设备 ref → 原样（`node-{id}-device-auth[-pub]` 是字节契约，绝不重建）；
 *   - 解析不出的（旧格式 / 裸名 / 垃圾）→ 与写入侧一样抛 `KeyRefError`。
 *     静默返回"没有这条记录"、静默不删，会把调用方的拼写错误伪装成"密钥不在本机"。
 */
function canonicalRefForLookup(keyRef) {
  const ref = String(keyRef ?? '')
  const parsed = parseKeyRef(ref)
  if (!parsed) {
    throw new KeyRefError(`不是规范的本地密钥引用：${ref}（应为 node/{nodeId}/{算法}/{keyId}/{版本}）`)
  }
  return parsed.kind === 'node' ? buildKeyRef(parsed) : ref
}

/**
 * 取回并解密一份私密材料。
 *
 * 入参与 `sealSecret` 同一套接受规则（见 `canonicalRefForLookup`）：别名/零填充
 * 版本这类可解析文本按规范文本查，设备 ref 原样，解析不出的抛 `KeyRefError`。
 *
 * @returns {Promise<Uint8Array>} 明文
 * @throws 引用不合法、记录不存在、或解密失败（保护密钥换了 / 数据被改动）时抛出
 */
export async function unsealSecret(keyRef) {
  const ref = canonicalRefForLookup(keyRef)
  const record = await tx(STORE_KEYS, 'readonly', (store) => req(store.get(ref)))
  if (!record) {
    throw new Error(`本地密钥库中没有 ${ref} 的记录`)
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
    throw new Error(`本地密钥库中的 ${ref} 解密失败：保护密钥不匹配或数据已被改动`)
  }
}

/**
 * 该记录是否存在于本地密钥库。
 *
 * 与 `sealSecret` 同一套接受规则（见 `canonicalRefForLookup`）：别名文本照样命中
 * 规范记录；解析不出的参照旧抛 `KeyRefError` —— 静默返回 false 与"本机没有这把
 * 密钥"不可区分，会让拼写错误伪装成"材料不在本机"。
 */
export async function hasSecret(keyRef) {
  const record = await tx(STORE_KEYS, 'readonly', (store) => req(store.get(canonicalRefForLookup(keyRef))))
  return Boolean(record)
}

/** 列出全部记录摘要（**不含任何私密材料**，用于界面展示与设备绑定判断） */
export async function listSecrets() {
  const all = await tx(STORE_KEYS, 'readonly', (store) => req(store.getAll()))
  return (all || []).map(toSummary)
}

/**
 * 删除一条记录。入参按 `canonicalRefForLookup` 规范化 —— 否则用非规范文本删除
 * 会**静默不删**（调用方以为清掉了，实际还在），这比报错更糟。
 */
export async function removeSecret(keyRef) {
  await tx(STORE_KEYS, 'readwrite', (store) => req(store.delete(canonicalRefForLookup(keyRef))))
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
 * 清空长期密钥材料：`keys` store（全部私密材料密文）+ `meta`（保护密钥与设备标识）。
 *
 * ⚠️ **刻意不清 `deviceKeys`**（设备凭据 / 登录身份），这不是遗漏：
 *    * 它是登录凭据、不是分发密钥 —— 服务端仍登记着它的公钥，清掉它这台浏览器
 *      就再也登录不上，要拿回登录能力得管理员重发激活凭证；
 *    * "重置本地密钥材料"不该附带"把已激活设备变成登录不了"这个后果。
 *    真要连设备身份一起抹掉（例如整机移交），单独调 `removeDeviceKeyPair`。
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

// ---------------------------------------------------------------------------
// 会话密钥（KMS-012）：解封得到 / 分发产出的 K 的**本机副本**
// ---------------------------------------------------------------------------
// 计划 §7 阶段 4 的原文是「解封得到 SM4 后保存到本地会话密钥库，不上传 SM4」——
// 这个 store 就是那句话的落点。它同时服务两侧：
//   * 接收方：解封成功后存 K，之后每次确认在本地算 HMAC proof；
//   * 发送方：分发成功后存这把 K（它就是自己生成的），提交确认时同样在本地算。
//
// ⚠️ 服务端那一半是"看不到 K"（不变量），这一半是"K 留在本机、跨页面刷新
//    仍在"（可用性）。两者缺一不可：只在内存里存 K 的话，刷新一次就再也
//    提交不了确认，而页面上没有任何一处会说得出为什么。
//
// ⚠️ 与 keys 同一个保护密钥（`getOrCreateProtector`，不可导出）。
//    不要为了"方便调试"另开一个可导出的保护或明文存 —— 那等于把整库的优势
//    一次性抹掉，而代码看不出区别（该函数上方写着同一条纪律）。

/**
 * 保存会话密钥。`payloadKey` 必须是 16 字节的 SM4 载荷密钥。
 *
 * ⚠️ 长度在这里就拦：存错长度（例如把 32 字节的共享秘密当 K 存了）不会报错，
 *    但之后算出来的 proof 与对方恒不一致 —— 表现是"证明不一致"，
 *    看起来像两边拿错了密钥。所以**存的时候就判**。
 */
export async function sealSessionSecret(sessionId, payloadKey) {
  const id = String(sessionId ?? '').trim()
  if (!id) {
    throw new Error('sealSessionSecret：会话 ID 不能为空')
  }
  const bytes = payloadKey instanceof Uint8Array ? payloadKey : new Uint8Array(payloadKey || [])
  if (bytes.length !== 16) {
    throw new Error(`sealSessionSecret：会话密钥必须是 16 字节 SM4（收到 ${bytes.length} 字节）`)
  }
  const protector = await getOrCreateProtector()
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const sealed = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, protector, bytes)
  await tx(STORE_SESSION_KEYS, 'readwrite', (store) => req(store.put({
    sessionId: id,
    iv,
    sealed,
    createdAt: new Date().toISOString(),
  })))
  return { sessionId: id, bytes: bytes.length }
}

/** 读回会话密钥明文（本机）。没有该会话或解密失败时抛错 —— 不返回半截内容。 */
export async function unsealSessionSecret(sessionId) {
  const id = String(sessionId ?? '').trim()
  const record = await tx(STORE_SESSION_KEYS, 'readonly', (store) => req(store.get(id)))
  if (!record) {
    throw new Error(`本地会话密钥库里没有 ${id} 的记录（换过设备或清过站点数据？）`)
  }
  const protector = await getOrCreateProtector()
  try {
    const plain = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: record.iv }, protector, record.sealed
    )
    return new Uint8Array(plain)
  } catch {
    throw new Error(`本地会话密钥库中的 ${id} 解密失败：保护密钥不匹配或数据已被改动`)
  }
}

/** 本机是否有该会话的密钥副本。 */
export async function hasSessionSecret(sessionId) {
  const id = String(sessionId ?? '').trim()
  const record = await tx(STORE_SESSION_KEYS, 'readonly', (store) => req(store.get(id)))
  return Boolean(record)
}

/** 列出本机持有的会话密钥摘要（**不含任何密钥字节**，仅供界面显示）。 */
export async function listSessionSecrets() {
  const all = await tx(STORE_SESSION_KEYS, 'readonly', (store) => req(store.getAll()))
  return (all || []).map((record) => ({
    sessionId: record.sessionId,
    createdAt: record.createdAt,
  }))
}

/**
 * 删除一条会话密钥（会话关闭后调用）。
 *
 * ⚠️ 调用时机在**服务端关闭成功之后**：反过来先删本地再关服务端，一旦关闭
 *    请求失败，本机就再也算不出 proof、也再也确认不了这条会话 ——
 *    而服务端那边它还活着。
 */
export async function removeSessionSecret(sessionId) {
  const id = String(sessionId ?? '').trim()
  await tx(STORE_SESSION_KEYS, 'readwrite', (store) => req(store.delete(id)))
}

/**
 * 本机是否持有该节点的密钥材料（§4.4 设备绑定的判断基础）。
 *
 * 判据是"**任意一套**基础密钥在不在本机"，而不是"四套都在"：
 * 初始化可能做到一半（比如生成完 SM2 就断网了），
 * 那种情况下本机**确实**有材料，只是不全 —— 与"新设备什么都没有"
 * 是两回事，处置也不同（前者续做，后者要重新初始化）。
 *
 * ⚠️ 过滤用 `kind === 'node' && nodeId === 精确相等`，**不再有任何后缀/子串匹配**。
 *    旧实现是 `endsWith('-' + nodeId)`，对线上真实 ref（`node-{id}-{ALGO}`，
 *    大写算法名、无版本）恒不命中且不报错 —— present 永远是 false；
 *    而且 `-` 分隔下 node `A` 与 `A-B` 会互相串。新格式用 `/` 分段 + 精确相等，
 *    这两类问题从根上没有了。
 *
 * @param {string} nodeId 节点编号
 * @returns {Promise<{present: boolean, algorithms: string[], keys: object[]}>}
 */
export async function inspectNodeKeys(nodeId) {
  const id = String(nodeId ?? '').trim()
  if (!id) {
    return { present: false, algorithms: [], keys: [] }
  }
  const all = await listSecrets()
  const mine = all.filter((r) => r.kind === 'node' && r.nodeId === id)
  const keys = mine.map((r) => ({
    keyRef: r.keyRef,
    nodeId: r.nodeId,
    algorithm: r.algorithm,
    keyId: r.keyId,
    version: r.version,
    publicKey: r.publicKey,
    createdAt: r.createdAt,
    migrated: r.migrated
  }))
  return {
    present: keys.length > 0,
    algorithms: [...new Set(keys.map((k) => k.algorithm).filter(Boolean))].sort(),
    keys
  }
}

/**
 * 取本机某把长期密钥的元信息；不存在或归属/算法/版本不符就抛**带错误码**的
 * `KeyRefError`（计划 §7 阶段 1：「增加本地密钥存在性、算法、版本和节点归属检查」）。
 *
 * 为什么要有这个函数，而不是调用方自己 `listSecrets` 再挑一遍：判据必须只有
 * 一份。四处各写"我再过滤一下"，每个调用点就会各松一点，而"松"在这里的表现
 * 是静默用了不该用的密钥 —— 比如版本不符却拿旧版本算出了另一个会话密钥。
 *
 * 检查顺序：ref 形状 → 拒绝设备 ref → 节点归属 → 算法 → 版本 → 本机是否存在。
 *
 * @param {string} keyRef 规范引用
 * @param {{nodeId?: string, algorithm?: string, version?: number}} [expect]
 * @returns {Promise<object>} 与 `listSecrets` 单行同形状的元信息（不含 iv/sealed）
 */
export async function requireLocalKey(keyRef, { nodeId = '', algorithm = '', version = 0 } = {}) {
  const ref = String(keyRef ?? '')
  const parsed = parseKeyRef(ref)
  if (!parsed) {
    throw new KeyRefError(`不是规范的本地密钥引用：${ref}（应为 node/{nodeId}/{算法}/{keyId}/{版本}）`)
  }
  if (parsed.kind !== 'node') {
    throw new KeyRefError(
      `设备凭据不是可用的长期密钥：${ref}（设备凭据只用于对服务端挑战签名，不参与分发、解封或业务签名）`
    )
  }
  if (nodeId && String(nodeId).trim() !== parsed.nodeId) {
    throw new KeyRefError(
      `节点归属不符：引用属于节点 ${parsed.nodeId}，调用方要求 ${String(nodeId).trim()}（不同节点的同名 keyId 不是同一把密钥）`
    )
  }
  if (algorithm && normalizeAlgorithm(algorithm) !== parsed.algorithm) {
    throw new KeyRefError(`算法不符：引用是 ${parsed.algorithm}，调用方要求 ${normalizeAlgorithm(algorithm)}`)
  }
  if (version) {
    const given = Number(version)
    if (!Number.isInteger(given) || given < 1) {
      throw new KeyRefError(`版本号必须是 ≥1 的整数：${version}`)
    }
    if (given !== parsed.version) {
      throw new KeyRefError(
        `版本不符：引用是 v${parsed.version}，调用方要求 v${given}（版本不符必须重新生成/轮换，不能拿旧版本顶上）`,
        ERR_KEY_VERSION_MISMATCH
      )
    }
  }
  // 查到这一步的 ref 已经过上面全部检查（parse 出的 node ref）。查库前重建规范
  // 文本，与写侧落库规则同一口径 —— 否则别名/零填充版本（`kyber_kem`、`01`）
  // 这类可解析文本会"记录在、查不到"，报一个误导性的 KEY_LOCAL_MISSING。
  const lookupRef = buildKeyRef(parsed)
  const record = await tx(STORE_KEYS, 'readonly', (store) => req(store.get(lookupRef)))
  if (!record) {
    throw new KeyRefError(`${LOCAL_MISSING_HINT}（引用：${lookupRef}）`, ERR_KEY_LOCAL_MISSING)
  }
  return toSummary(record)
}

export { getDeviceId, STORE_DEVICE_KEYS, DB_NAME, META_PROTECTOR as PROTECTOR_META_KEY }
