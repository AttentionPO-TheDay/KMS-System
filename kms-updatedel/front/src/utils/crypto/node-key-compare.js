/**
 * 「平台登记的那把」与「本机持有的那把」对账（计划 §7 阶段 1 / §4.4）。
 *
 * 为什么单独一个文件
 * ----------------
 * 生成页与新加的密钥历史页都要回答同一个问题：**服务端记下的公钥，是不是
 * 本机这把私钥对应的那把**。这个判断有三处容易各写一套而又互相漂移：
 *
 *   1. 公钥的比较口径（一律小写 hex、逐字节相等，不做大小写兜底）；
 *   2. 配对的键（算法 + keyId + **版本**三段，缺一段就会把两把不同的密钥
 *      当成同一把 —— 而"当成同一把"的表现是界面显示"一致"，没有任何报错）；
 *   3. 五种结论各自的**下一步**（换设备、重新登记、查平台记录原文……）。
 *
 * 这三处一旦在两个页面里各写一遍，漂移不会报错，只会让某一页给出错误的
 * 处置建议。所以收在这里，两个页面都只负责渲染。
 *
 * 平台侧公钥是**比对形式**（`node_self_views._public_key_hex` 已把 Kyber 的
 * base64 换算成 hex），本机侧 `cryptoProvider` 一律存 hex —— 两端同形是这里
 * 能纯字节比对的前提。
 *
 * 本模块**不接触私密材料**：只比公钥、只读摘要字段。
 */

/** 对账结论。取值只在这一个地方定义，页面按它分支渲染。 */
export const RECONCILE = Object.freeze({
  /** 平台与本机都有，且公钥逐字节相同 —— 唯一"可以放心用"的结论 */
  MATCH: 'MATCH',
  /** 平台登记着、本机没有对应私钥：换了设备，或清过站点数据 */
  LOCAL_MISSING: 'LOCAL_MISSING',
  /** 同 (算法, keyId, 版本) 下公钥不同：正常路径不会出现 */
  MISMATCH: 'MISMATCH',
  /** 平台那行的公钥换算不出可比对的形式（历史编码），**无法判断**而非"不一致" */
  SERVER_EMPTY_PK: 'SERVER_EMPTY_PK',
  /** 本机有材料、平台没有对应行：登记失败，或换节点后遗留 */
  LOCAL_ONLY: 'LOCAL_ONLY'
})

/** 结论 → 一句话。表格与卡片共用，避免同一结论在两页里说法不一。 */
export const RECONCILE_TEXT = Object.freeze({
  [RECONCILE.MATCH]: '一致',
  [RECONCILE.LOCAL_MISSING]: '平台有、本机无私钥',
  [RECONCILE.MISMATCH]: '同 keyId 公钥不同',
  [RECONCILE.SERVER_EMPTY_PK]: '平台公钥无法比对',
  [RECONCILE.LOCAL_ONLY]: '本机有、平台未登记'
})

/** 只有 MATCH 是"可以放心用"。其余四种都要人来处置，不能只看成败着色。 */
export function reconcileOk(state) {
  return state === RECONCILE.MATCH
}

/**
 * 两把公钥是不是同一把。
 *
 * **不做大小写兜底、不做 trim**：真出现形态差异时要让它显示成"不一致"，
 * 而不是被宽容掉 —— 宽容会掩盖"本机这把其实不是平台那把"。
 * 空值一律不等（"没有公钥"不能算"相同"）。
 */
export function samePublicKey(a, b) {
  const left = String(a ?? '')
  const right = String(b ?? '')
  return Boolean(left) && Boolean(right) && left === right
}

/**
 * 配对的三段键：`算法|keyId|版本`。
 *
 * ⚠️ 三段缺一不可。只按算法配（"我 KYBER 有材料、平台也有 KYBER 行 → 一致"）
 *    在换过密钥之后就**恒定误判为一致**：平台在用的是新那把，本机躺的是旧的。
 *
 *    版本段的类型差异（平台侧 int、本机侧 Number、某处传了字符串 `'1'`）
 *    **不影响配对**：`compareKey` 是模板串拼接，两侧都渲染成同一段文本，
 *    `1` 与 `'1'` 落成同一个键 —— 这正是想要的，版本是**数值**，
 *    两种写法指的就是同一版。要防的是版本**取值不同**（那会落成两个键，
 *    表现为同一把密钥两边各有一行、谁也不配对），不是类型不同。
 */
export function compareKey({ algorithm, keyId, version }) {
  return `${algorithm}|${keyId}|${version}`
}

/** 在本地材料里按 (算法, keyId, 版本) 精确找那一条。找不到返回 null。 */
export function findLocalKey(localKeys, { algorithm, keyId, version }) {
  const rows = Array.isArray(localKeys) ? localKeys : []
  const wanted = compareKey({ algorithm, keyId, version })
  return rows.find((k) => compareKey(k) === wanted) || null
}

/** 单行结论。`server` 为平台行（可为 null=本机独有），`local` 为本机材料（可为 null）。 */
export function reconcileRow(server, local) {
  if (!server) {
    return { state: RECONCILE.LOCAL_ONLY, ok: false, text: RECONCILE_TEXT[RECONCILE.LOCAL_ONLY] }
  }
  if (!local) {
    return { state: RECONCILE.LOCAL_MISSING, ok: false, text: RECONCILE_TEXT[RECONCILE.LOCAL_MISSING] }
  }
  // 空的平台公钥 = 换算不出比对形式 = **无法判断**。与"不一致"合并会给出
  // 错误的下一步（让人去查本机密钥库，而该查的是平台那行原文）。
  if (!server.publicKey) {
    return { state: RECONCILE.SERVER_EMPTY_PK, ok: false, text: RECONCILE_TEXT[RECONCILE.SERVER_EMPTY_PK] }
  }
  const state = samePublicKey(local.publicKey, server.publicKey)
    ? RECONCILE.MATCH
    : RECONCILE.MISMATCH
  return { state, ok: reconcileOk(state), text: RECONCILE_TEXT[state] }
}

/**
 * 平台行 ∪ 本机独有行 → 表格行。
 *
 * 本机独有的那些**必须列出来**：登记失败、或换过节点后遗留的材料都在这里。
 * 不列的话它们对用户是隐形的，而它们确实占着密钥库、也确实能用。
 *
 * 平台行保持传入顺序（接口按 `algorithm, -id` 排好），本机独有行追加在后。
 * 每行带 `id`（`serverKeys` 里 keyId 可能为空 → 回退到下标，避免 Vue 复用一个
 * 已变内容的行）。
 */
export function compareNodeKeys({ serverKeys = [], localKeys = [] } = {}) {
  const out = []
  const matched = new Set()
  const servers = Array.isArray(serverKeys) ? serverKeys : []
  const locals = Array.isArray(localKeys) ? localKeys : []

  servers.forEach((s, i) => {
    const local = findLocalKey(locals, {
      algorithm: s.algorithm,
      keyId: s.keyId,
      version: s.keyVersion
    })
    if (local) matched.add(local.keyRef)
    out.push({
      id: `s-${s.algorithm}-${s.keyId || i}-${s.keyVersion}`,
      algorithm: s.algorithm,
      keyId: s.keyId,
      version: s.keyVersion,
      server: s,
      local: local || null,
      publicKeyBytes: s.publicKeyBytes || 0,
      createdAt: s.createdAt,
      reconcile: reconcileRow(s, local)
    })
  })

  for (const k of locals) {
    if (matched.has(k.keyRef)) continue
    out.push({
      id: `l-${k.keyRef}`,
      algorithm: k.algorithm,
      keyId: k.keyId,
      version: k.version,
      server: null,
      local: k,
      // 本机材料字节数由 hex 长度算（本机一律 hex 文本）
      publicKeyBytes: k.publicKey ? String(k.publicKey).length / 2 : 0,
      createdAt: k.createdAt,
      reconcile: reconcileRow(null, k)
    })
  }
  return out
}

/**
 * 某算法**当前在产**的那一行（`allowsNewWork`），没有则 null。
 *
 * 用 `allowsNewWork` 而不是"状态等于 ACTIVE"：可用性判断归 `api_contract`
 * （`KEY_STATUS_USABLE_FOR_NEW_WORK`，还额外与"未过期"相与）。前端再写一句
 * `status === 'ACTIVE'` 就是第二份口径，而后端将来给它加任何条件，这里
 * 都会静默地继续用错的判据。
 */
export function activeServerKey(serverKeys, algorithm) {
  const rows = Array.isArray(serverKeys) ? serverKeys : []
  return rows.find((r) => r.algorithm === algorithm && r.allowsNewWork) || null
}
