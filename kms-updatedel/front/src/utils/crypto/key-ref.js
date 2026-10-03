/**
 * 本地密钥引用（keyRef）的**唯一实现**（计划 §7 阶段 1 / KMS-003）。
 *
 * 为什么单独一个文件
 * ----------------
 * 后端冻结契约 `pqkds/api_contract.py` 的文件头写明："前端对应物在
 * `kms-updatedel/front/src/utils/crypto/key-ref.js` 与 `constants/contract.js`"。
 * 本文件就是那句话的前端一侧：ref 长什么样、怎么拼、怎么拆，**只允许在这里定义**。
 * 别处再写一遍 `node-${id}-...` 就是在制造第二份口径，而两份口径漂移的后果
 * 不是报错，是"找不到密钥"—— `-` 或 `/` 切错段不会抛异常，只会让查询恒不命中。
 *
 * 格式
 * ----
 *     node/{nodeId}/{算法}/{keyId}/{版本}     例：node/N1/KYBER/N1-KYBER-1a2b3c4d/1
 *
 * keyId 的形状与后端 `node_key_registry.new_key_id()` 一致：
 * `{safe_node}-{ALGO}-{前8位随机 hex}`，其中 safe_node = nodeId 里
 * `[^A-Za-z0-9_.-]` 全部替换成 `-`（后端 `_ID_SAFE` 同一规则，见 `mintKeyId`）。
 *
 * ⚠️ 改格式要**两处同改**：后端 `api_contract.py` 的文件头 / `new_key_id` docstring
 *    与本文件 —— 跨语言没有共享常量的办法，只能靠这两行提示。
 *
 * 为什么用 `/` 而不是 `-` 分隔
 * ---------------------------
 * 历史格式 `node-{id}-{ALGO}` 用 `-` 分隔，而 node id 与 keyId 里都可能含 `-`：
 *   * node `A` 与 node `A-B` 会互相串（后缀匹配歧义）；
 *   * 旧 `inspectNodeKeys` 用 `endsWith('-' + nodeId)` 过滤，对线上真实 ref
 *     （大写算法名、无版本）**恒不命中且不报错**，present 永远是 false。
 * `/` 分段 + 精确相等从根上消除这两类问题；keyId 里禁止出现 `/`
 * 正是为了保住"切段不歧义"。
 *
 * 设备凭据是**另一套命名空间**
 * ---------------------------
 * `node-{id}-device-auth[-pub]`（见 device-credential.js §3.1/§5）。本文件同时
 * 提供它的构造/解析，但**字节形式不得改动** —— 已激活浏览器的登录凭据就是这串
 * 字符串，改一个字符等于让所有老设备登录不上。
 */

import { ALGORITHMS, normalizeAlgorithm } from './provider.js'

/**
 * 设备凭据的算法名。与后端 `node_auth_views.DEVICE_AUTH_ALGORITHM` 必须一致，
 * 改一处要改两处 —— 它的作用域**仅限设备命名空间**，不要拿它去套长期密钥白名单。
 */
export const DEVICE_AUTH_ALGORITHM = 'ECDSA-P256'

/** 设备公钥 JWK 那一份副本的 ref 后缀（公开量，见 device-credential.js）。 */
export const DEVICE_PUB_SUFFIX = '-pub'

// 错误码取值与后端 api_contract.py 的 ERR_* 一致（跨语言各写一份，改一处要改两处）。
/** 本机没有这把密钥的私钥（换了设备 / 清过站点数据）。 */
export const ERR_KEY_LOCAL_MISSING = 'KEY_LOCAL_MISSING'
/** 引用的版本与调用方要求的版本不一致。 */
export const ERR_KEY_VERSION_MISMATCH = 'KEY_VERSION_MISMATCH'
/** 参数不合法（ref 形状错、算法不认识、节点归属不符……）。 */
export const ERR_INVALID_PARAMETER = 'INVALID_PARAMETER'

/**
 * 带错误码的引用错误。
 *
 * 调用方按 `err.code` 处置（与后端错误码同一套取值），**不要去匹配文案** ——
 * 匹配文案等于把提示语变成接口契约，改一个字就断。
 */
export class KeyRefError extends Error {
  constructor(message, code = ERR_INVALID_PARAMETER) {
    super(message)
    this.name = 'KeyRefError'
    this.code = code
  }
}

// 设备 ref：贪婪回溯保证 node-A-B-device-auth-pub 解析成 id=A-B、pub=true，
// 而不是把 auth 之类吃进 id（id 里的 `-device-auth` 也会被正确地当作 id 的一部分）。
const DEVICE_REF_RE = /^node-(.+)-device-auth(-pub)?$/
const DECIMAL_RE = /^\d+$/
const ID_SAFE_RE = /[^A-Za-z0-9_.-]/g

/** 校验 ref 的一个分段：非空、不含 `/`（含 `/` 会让切段错位，而错位不报错）、首尾无空白。 */
function requireRefPart(value, label) {
  const text = String(value ?? '')
  if (!text) {
    throw new KeyRefError(`缺少${label}：本地密钥引用必须能定位到具体节点与密钥`)
  }
  // 查询侧（inspectNodeKeys / requireLocalKey）会对节点编号 trim，构造侧不拦的话，
  // 带空白的 ref 会「存得进、两个拼写都查不到」—— 又是本文件要根除的静默失配。
  // 刻意不静默 trim，而是拒绝：静默纠正会让调用方以为存的是 A、实际是 B。
  if (text !== text.trim()) {
    throw new KeyRefError(
      `${label}首尾不能有空白：${JSON.stringify(text)}（查询侧会 trim，带空白的 ref 存得进、却永远查不到）`
    )
  }
  if (text.includes('/')) {
    throw new KeyRefError(
      `${label}不能包含 "/"：ref 按 "/" 切段，含 "/" 会切错段 —— 而切错不报错，只表现为"找不到密钥"（${text}）`
    )
  }
  return text
}

/**
 * 拼一个新格式引用。**所有新写入的 node ref 都必须经过这里**。
 *
 * 校验从严（抛 `KeyRefError`）：
 *   * `nodeId` / `keyId`：非空且不含 `/`；
 *   * `algorithm`：归一化后必须在 `ALGORITHMS` 白名单里（别名 `kyber_kem` /
 *     `gm_sm2` / `cl-falcon` 接受，输出一律规范大写名）；
 *   * `version`：**整数**且 ≥ 1。不接字符串 `'1'` —— 版本参与"这是哪一版"
 *     的精确判断，类型松一次，之后每个读路径都要各自兜底。
 */
export function buildKeyRef({ nodeId, algorithm, keyId, version } = {}) {
  const id = requireRefPart(nodeId, '节点编号')
  const kid = requireRefPart(keyId, 'keyId')
  const name = normalizeAlgorithm(algorithm)
  if (!ALGORITHMS.includes(name)) {
    throw new KeyRefError(`不认识的算法：${algorithm}（允许：${ALGORITHMS.join('、')}）`)
  }
  if (typeof version !== 'number' || !Number.isInteger(version) || version < 1) {
    throw new KeyRefError(`版本号必须是 ≥1 的整数：${version}（版本参与"哪一版"的精确判断，不接受字符串或小数）`)
  }
  return `node/${id}/${name}/${kid}/${version}`
}

/**
 * 解析引用。**永不抛** —— 解析不出来返回 `null`。
 *
 * @returns {{kind:'node', nodeId:string, algorithm:string, keyId:string, version:number}
 *         | {kind:'device', nodeId:string, pub:boolean}
 *         | null}
 *
 * 不 trim、不宽容：带空格、段数不对、旧格式 `node-N1-KYBER`（无 `/`）一律 null。
 * 解析器越宽容，错格式越晚暴露；而"晚暴露"在这里的表现是静默找不到密钥 ——
 * 那正是本文件要根除的东西，所以宁可在这里就说不认识。
 */
export function parseKeyRef(ref) {
  const text = typeof ref === 'string' ? ref : ''
  if (!text) {
    return null
  }
  // 设备 ref 先判：它第一段是 `node-`，新格式是 `node/`，两者不会互相吃掉。
  const device = DEVICE_REF_RE.exec(text)
  if (device) {
    return { kind: 'device', nodeId: device[1], pub: Boolean(device[2]) }
  }
  const parts = text.split('/')
  if (parts.length !== 5) {
    return null
  }
  const [head, nodeId, rawAlgorithm, keyId, rawVersion] = parts
  if (head !== 'node' || !nodeId || !keyId) {
    return null
  }
  const algorithm = normalizeAlgorithm(rawAlgorithm)
  if (!ALGORITHMS.includes(algorithm)) {
    return null
  }
  if (!DECIMAL_RE.test(rawVersion)) {
    return null
  }
  const version = Number(rawVersion)
  if (!Number.isInteger(version) || version < 1) {
    return null
  }
  return { kind: 'node', nodeId, algorithm, keyId, version }
}

/**
 * 拼设备凭据引用。
 *
 * ⚠️ 输出必须与 device-credential.js 现有的 `node-${id}-device-auth`（加 `-pub`）
 *    **逐字节相同** —— 已激活浏览器的登录凭据就是这串字符串。
 *
 * 与 `deviceKeyRef` 的唯一差别：含 `/` 的 nodeId 在这里就拒绝（那种 id 会让新格式
 * ref 切段歧义），而 deviceKeyRef 会原样拼出去。正常节点编号不受影响。
 */
export function buildDeviceRef(nodeId, { pub = false } = {}) {
  const id = String(nodeId ?? '').trim()
  if (!id) {
    throw new KeyRefError('缺少节点编号：设备凭据必须挂在具体节点下')
  }
  if (id.includes('/')) {
    throw new KeyRefError(`节点编号不能包含 "/"：设备凭据与长期密钥共用同一套节点编号规则（${id}）`)
  }
  return `node-${id}-device-auth${pub ? DEVICE_PUB_SUFFIX : ''}`
}

/** 解析设备引用；不是设备 ref 返回 `null`。`pub` 表示这是公钥 JWK 那份副本。 */
export function parseDeviceRef(ref) {
  const text = typeof ref === 'string' ? ref : ''
  if (!text) {
    return null
  }
  const match = DEVICE_REF_RE.exec(text)
  if (!match) {
    return null
  }
  return { nodeId: match[1], pub: Boolean(match[2]) }
}

/**
 * 生成一个新 keyId。**形状必须镜像后端 `node_key_registry.new_key_id()`**：
 *
 *     {safe_node}-{ALGO}-{8位小写hex}
 *
 * 后端用 uuid4 前 8 位、这里用 `getRandomValues(4B)`：值不同但形状相同。
 * 前端不需要与后端算出同一个 id，需要的是"两边生成的 id 放进 ref 都切不坏段"。
 *
 * ⚠️ keyId 里**不能出现 `/`**：ref 按 `/` 切段，切错不报错、只是找不到密钥。
 *    替换规则已保证这一点（`/` 不在白名单字符里，会被换成 `-`）。
 */
export function mintKeyId(nodeId, algorithm) {
  const name = normalizeAlgorithm(algorithm)
  if (!ALGORITHMS.includes(name)) {
    throw new KeyRefError(`不认识的算法：${algorithm}（允许：${ALGORITHMS.join('、')}）`)
  }
  const safeNode = String(nodeId ?? '').replace(ID_SAFE_RE, '-')
  const hex = [...crypto.getRandomValues(new Uint8Array(4))]
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('')
  return `${safeNode}-${name}-${hex}`
}
