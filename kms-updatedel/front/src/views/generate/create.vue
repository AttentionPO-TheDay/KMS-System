<template>
  <div class="app-container gen-create">
    <el-card shadow="never" class="gen-create__card">
      <template #header>
        <div class="gen-create__header">
          <h2>密钥生成</h2>
          <div class="gen-create__header-side">
            <el-tag v-if="node.nodeId" type="info" size="small">{{ node.nodeId }}</el-tag>
            <el-button size="small" :loading="loading" @click="load">刷新</el-button>
          </div>
        </div>
      </template>

      <!-- 账号没关联节点：管理员账号，或数据异常。与「节点首次初始化」同一判据。 -->
      <el-alert
        v-if="!loading && !mapped"
        type="warning"
        :closable="false"
        show-icon
        title="当前账号未关联任何节点"
        description="密钥生成是节点的动作。请用节点账号登录，或在「节点管理」里创建节点后再由节点自行登录。"
      />

      <template v-else>
        <p class="gen-create__lead">
          私钥在<strong>本机</strong>生成并留在本机，平台只收到<strong>公钥</strong>。
          按算法独立生成 —— 用哪几种就生成哪几种，不要求四套成套。
        </p>

        <!-- 设备不一致**提前**说。等到用户点了生成、转完 Falcon 的几秒、
             再吃一个 409 才知道，是最坏的顺序：他会以为生成坏了。
             判据与 §4.4 一致：服务端已绑定设备指纹，而本机不是那一台。 -->
        <el-alert
          v-if="deviceWarning"
          class="gen-create__device"
          type="warning"
          :closable="false"
          show-icon
          :title="deviceWarning.title"
        >
          <template #default>
            <p>{{ deviceWarning.detail }}</p>
          </template>
        </el-alert>

        <div class="gen-create__grid">
          <div
            v-for="c in cards"
            :key="c.algorithm"
            class="gen-create__algo"
            :class="{ 'is-active': c.active, 'is-warn': c.reconcile && !c.reconcile.ok && c.reconcile.state !== RECONCILE.LOCAL_ONLY }"
          >
            <div class="gen-create__algo-head">
              <span class="gen-create__algo-name">{{ c.label }}</span>
              <el-tag v-if="c.active" :type="c.active.allowsNewWork ? 'success' : 'info'" size="small">
                {{ c.active.statusLabel }}
              </el-tag>
              <el-tag v-else type="info" size="small" effect="plain">未登记</el-tag>
            </div>
            <p class="gen-create__algo-role">{{ c.role }}</p>

            <dl class="gen-create__facts">
              <div class="gen-create__fact">
                <dt>平台登记</dt>
                <dd v-if="c.active" class="mono">
                  {{ c.active.keyId }} · v{{ c.active.keyVersion }}
                  <span class="gen-create__fact-note">{{ usableText(c.active) }}</span>
                </dd>
                <dd v-else class="is-muted">—</dd>
              </div>
              <div class="gen-create__fact">
                <dt>本机材料</dt>
                <dd :class="c.localKey ? 'is-ok' : 'is-muted'">{{ c.localText }}</dd>
              </div>
            </dl>

            <!-- 对账结论：把"登记成功了"与"这把真能用"分开说。
                 四种不一致各有各的下一步，**不能合成一句"异常"** ——
                 合成之后用户唯一能做的就是重新初始化，而那往往是错的。 -->
            <el-alert
              v-if="c.reconcile && c.reconcile.state === RECONCILE.LOCAL_MISSING"
              class="gen-create__reconcile"
              type="error"
              :closable="false"
              show-icon
              title="平台记着这把公钥，本机却没有对应私钥"
              description="该密钥是在另一台设备上生成的。本机解不开平台按它分发的信封 —— 需要在「节点首次初始化」里用本机重新生成并登记。"
            />
            <el-alert
              v-else-if="c.reconcile && c.reconcile.state === RECONCILE.MISMATCH"
              class="gen-create__reconcile"
              type="error"
              :closable="false"
              show-icon
              title="同一 keyId 下，本机公钥与平台记录不一致"
              description="正常路径不会出现。请勿继续用它分发 —— 先确认本机密钥库是否被导入或被改写过。"
            />
            <el-alert
              v-else-if="c.reconcile && c.reconcile.state === RECONCILE.SERVER_EMPTY_PK"
              class="gen-create__reconcile"
              type="info"
              :closable="false"
              show-icon
              title="平台记录的公钥无法换算成可比对的形式"
              description="可能是历史行（编码与当前口径不同）。登录服务器查该行原文，不要据本页判断它是否可用。"
            />
            <div v-else-if="c.reconcile && c.reconcile.state === RECONCILE.LOCAL_ONLY" class="gen-create__pending">
              本机已生成，平台上<strong>没有</strong>登记 —— 点下面的按钮重新登记一次。
            </div>
            <div v-else-if="c.reconcile && c.reconcile.state === RECONCILE.MATCH" class="gen-create__match">
              <el-icon><CircleCheck /></el-icon>
              <span>本机这把公钥与平台记录逐字节相同</span>
            </div>

            <div v-if="selfTestOf(c)" class="gen-create__selftest" :class="selfTestOf(c).ok ? 'is-ok' : 'is-bad'">
              {{ selfTestOf(c).ok ? '自检通过' : '自检未过' }}：{{ selfTestOf(c).detail }}
            </div>

            <div class="gen-create__algo-actions">
              <el-select
                v-if="c.algorithm === 'KYBER'"
                v-model="kyberVariant"
                size="small"
                class="gen-create__variant"
                :disabled="Boolean(generating)"
              >
                <el-option label="Kyber-512（NIST 1 级）" :value="512" />
                <el-option label="Kyber-768（NIST 3 级）" :value="768" />
                <el-option label="Kyber-1024（NIST 5 级）" :value="1024" />
              </el-select>
              <el-button
                type="primary"
                size="small"
                :loading="generating === c.algorithm"
                :disabled="Boolean(generating) && generating !== c.algorithm"
                @click="handleGenerate(c)"
              >
                {{ generating === c.algorithm ? '生成中…' : (c.active ? '生成新密钥' : '生成并登记') }}
              </el-button>
              <el-button
                v-if="selfTestKeyRef(c)"
                size="small"
                :loading="testing === selfTestKeyRef(c)"
                :disabled="Boolean(testing)"
                @click="runSelfTest(c.algorithm, selfTestKeyRef(c))"
              >
                自检
              </el-button>
            </div>
          </div>
        </div>

        <!-- 说明两条硬事实：换新密钥之后旧版本还在（信封要能解），以及本页不提供导出。 -->
        <p class="gen-create__note">
          平台已有在产版本时，再生成一把会把它<strong>降为「已被取代」</strong>：
          不再用于新会话，但仍能解开按它分发的旧信封 —— 需要彻底作废请用「密钥更新与回收」。
          私钥<strong>不提供导出</strong>：它只存在于本机加密密钥库，换机器只能重新生成一套。
        </p>

        <h3 class="gen-create__section-title">
          本节点密钥对照
          <span class="gen-create__section-note">
            只列 {{ node.nodeId }} 的密钥 —— 同一浏览器上其它节点的材料不会出现在这里
          </span>
        </h3>
        <el-table :data="rows" size="small" border class="gen-create__table">
          <el-table-column label="算法" width="90">
            <template #default="{ row }">{{ row.algorithm }}</template>
          </el-table-column>
          <el-table-column label="keyId" min-width="220">
            <template #default="{ row }">
              <span class="mono">{{ row.keyId || '（平台铸造）' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="版本" width="70">
            <template #default="{ row }">v{{ row.version }}</template>
          </el-table-column>
          <el-table-column label="平台" width="150">
            <template #default="{ row }">
              <el-tag v-if="row.server" :type="row.server.allowsNewWork ? 'success' : 'info'" size="small">
                {{ row.server.statusLabel }}
              </el-tag>
              <el-tag v-else type="warning" size="small" effect="plain">未登记</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="本机" width="100">
            <template #default="{ row }">
              <span :class="row.local ? 'is-ok' : 'is-muted'">{{ row.local ? '有私钥' : '无私钥' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="对账" min-width="160">
            <template #default="{ row }">
              <span :class="row.reconcile.ok ? 'is-ok' : 'is-bad'">{{ row.reconcile.text }}</span>
            </template>
          </el-table-column>
          <el-table-column label="公钥字节" width="90">
            <template #default="{ row }">{{ row.publicKeyBytes || '—' }}</template>
          </el-table-column>
          <el-table-column label="登记时间" min-width="160">
            <template #default="{ row }">{{ formatTime(row.createdAt) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="80" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="row.local"
                link
                type="primary"
                size="small"
                :disabled="Boolean(testing)"
                @click="runSelfTest(row.algorithm, row.local.keyRef)"
              >
                自检
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <p v-if="!loading && !rows.length" class="gen-create__empty">
          这个节点还没有任何长期密钥。用上面的卡片生成第一把。
        </p>
      </template>
    </el-card>
  </div>
</template>

<script setup>
/**
 * 密钥生成（菜单 9054，节点端 `/genzone/create`）。
 *
 * 这个页面在做什么
 * ----------------
 * 计划 §7 阶段 1：「生成页按算法独立生成，不强制四种算法成套生成；服务端只接收
 * 公钥和公开元数据；节点初始化、后续生成、更新都使用同一套本地保存接口」。
 *
 * 所以本页的动作只有两个：**在本机生成**（`cryptoProvider.generate`，私钥落
 * `NodeKeyStore`）与**把公钥登记到平台**（`POST /node-self/keys/`）。
 * 没有任何一步会把私钥发出去，也**不提供导出** —— 这是阶段 1 判据②要看的。
 *
 * 为什么整页重写
 * --------------
 * 改造前这里是**用户腿**流程（`SM2.generateKeyPair()` → `createGenerateKey({uA})`
 * 交给 generate-java 算部分私钥 → 前端合成 d_A → 导出密钥文件 → `useKeyringStore`
 * 收进浏览器钥匙串）。那是"客户端密钥"的概念，与 §4.4「节点在本地生成并保管
 * 长期密钥、服务端只收公钥」是两回事；两者混在一个页面里的表现是：
 * 用户以为在给**节点**生成密钥，实际生成的是自己这把**用户**密钥。
 *
 * 数据来源
 * --------
 * - 平台侧：`GET /node-self/keys/`（本节点的全部长期密钥行，含历史版本）
 * - 本机侧：`cryptoProvider.inspectNodeKeys(nodeId)`（加密 IndexedDB，**按 nodeId 过滤**）
 * 两边的对账口径（配对三元组、公钥比较、五种结论的文案）收在
 * `@/utils/crypto/node-key-compare`，本页只负责渲染。
 *
 * 为什么不按权限能力禁用按钮
 * --------------------------
 * `capabilities` 里有 `generate` 才允许生成，看着更严谨，但**现在不能这么做**：
 * `node_self_views` 只在 `GET/POST /node-self/keys/` 上校验登录，**没有**校验
 * `CAP_GENERATE`（`node_permission.require_capability` 全仓只有分发的
 * `user_distribution_views` 在用）；而 `Node.permission_level` 默认 `'L1'`，
 * 既有节点绝大多数就是 L1 且已初始化成功 —— 前端一加门禁，就会出现
 * 「初始化页能生成、生成页不能」的自相矛盾。
 * 真要收紧，应当先在后端登记路径上校验能力（届时前端读 `capabilities` 即可），
 * 而不是在界面上单方面拦住用户。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { CircleCheck } from '@element-plus/icons-vue'
import {
  getSelfNode,
  listSelfNodeKeys,
  registerSelfNodePublicKey,
  NODE_SELF_ERR
} from '@/api/pqkds/node-self'
import {
  RECONCILE,
  activeServerKey,
  compareNodeKeys,
  findLocalKey,
  reconcileRow
} from '@/utils/crypto/node-key-compare.js'
import { cryptoProvider } from '@/utils/crypto/browser-provider.js'
import { deviceFingerprint, hasDeviceKey } from '@/utils/crypto/device-credential.js'
import { IS_DEMO } from '@/utils/entry-mode'

const loading = ref(true)
const mapped = ref(false)
const node = ref({})

/** 平台登记的行（`GET /node-self/keys/` 原样） */
const serverKeys = ref([])
/** 本机密钥库里属于**这个节点**的材料 */
const localKeys = ref([])
const hasDeviceCredential = ref(false)
const deviceFingerprintValue = ref('')

/** 正在生成的算法名（同时只允许生成一个 —— 生成是重计算，并发只会更慢） */
const generating = ref('')
/** 正在自检的 keyRef */
const testing = ref('')
/** keyRef → {ok, detail}，自检结论。不持久化：自检是"此刻这把能不能用" */
const selfTestResults = ref({})

const kyberVariant = ref(768)

const ALGO_META = [
  {
    algorithm: 'KYBER',
    label: 'Kyber',
    role: '密钥封装（KEM）：与其它节点协商共享秘密。抗量子，是节点腿的默认档位。'
  },
  {
    algorithm: 'SSCL',
    label: 'SSCL',
    role: '国密无证书：封装 SM4 会话密钥。'
  },
  {
    algorithm: 'SM2',
    label: 'SM2',
    role: '国密：封装 SM4 会话密钥。'
  },
  {
    algorithm: 'FALCON',
    label: 'Falcon',
    role: '对分发消息签名与验签。签名算法，不做封装 —— 要封装请选 Kyber。'
  }
]

// ---------------------------------------------------------------------------
// 载入
// ---------------------------------------------------------------------------
async function load() {
  loading.value = true
  try {
    const data = await getSelfNode()
    mapped.value = Boolean(data?.mapped)
    node.value = data?.node || {}
    if (!mapped.value) {
      serverKeys.value = []
      localKeys.value = []
      return
    }

    // 平台侧与本机侧**各取一次**，哪边失败就说哪边。
    // 合成一次 try 的话，"平台读不到"会表现成"本机密钥全没了" —— 那会诱导
    // 用户去重新生成（而私钥本来好好的）。
    const [platform, local] = await Promise.allSettled([
      listSelfNodeKeys(),
      cryptoProvider.inspectNodeKeys(node.value.nodeId)
    ])

    if (platform.status === 'fulfilled') {
      serverKeys.value = platform.value?.keys || []
    } else {
      serverKeys.value = []
      ElMessage.error(`读取平台登记记录失败：${platform.reason?.message || platform.reason}`)
    }

    if (local.status === 'fulfilled') {
      localKeys.value = local.value?.keys || []
    } else {
      // 密钥库不可用（隐私模式 / 浏览器禁用 IndexedDB）。此处**不能**当成
      // "本机没有" —— 那会让人以为私钥丢了。列空表 + 明确报错。
      localKeys.value = []
      ElMessage.error(`读取本机密钥库失败：${local.reason?.message || local.reason}`)
    }

    if (IS_DEMO) return // Demo provenance is supplied by the trusted server context, not a device credential.
    try {
      hasDeviceCredential.value = await hasDeviceKey(node.value.nodeId)
      deviceFingerprintValue.value = await deviceFingerprint(node.value.nodeId)
    } catch {
      hasDeviceCredential.value = false
      deviceFingerprintValue.value = ''
    }
  } catch (error) {
    ElMessage.error(`读取节点信息失败：${error.message}`)
  } finally {
    loading.value = false
  }
}

// ---------------------------------------------------------------------------
// 卡片：按算法对「平台在产的那一版」做对账
// ---------------------------------------------------------------------------
const cards = computed(() =>
  ALGO_META.map((meta) => {
    const active = activeServerKey(serverKeys.value, meta.algorithm)
    const local = active
      ? findLocalKey(localKeys.value, {
          algorithm: meta.algorithm,
          keyId: active.keyId,
          version: active.keyVersion
        })
      : null
    // 平台还没有这一算法的在产行时，比对的是"这一算法本机有没有材料"，
    // 而不是某一对具体的行 —— 那种情况下结论只能是 LOCAL_ONLY。
    const mine = localKeys.value.filter((k) => k.algorithm === meta.algorithm)
    const reconcile = active
      ? reconcileRow(active, local)
      : (mine.length ? reconcileRow(null, mine[mine.length - 1]) : null)

    return {
      ...meta,
      active,
      localKey: local,
      reconcile,
      localText: local
        ? `有（${local.keyRef}）`
        : (mine.length
            ? `有 ${mine.length} 把，但都不是平台在产的那一版`
            : (meta.algorithm === 'KYBER' ? `无（将按 Kyber-${kyberVariant.value} 生成）` : '无'))
    }
  })
)

/** 「这把还能干什么」由服务端下发的两个布尔量拼出，前端不另写状态表。 */
function usableText(row) {
  if (row.allowsNewWork) return '可用于新会话'
  if (row.allowsUnwrap) return '仅可解开旧信封'
  return '不可用'
}

// ---------------------------------------------------------------------------
// 表格：平台行 ∪ 本机独有行（对账口径见 node-key-compare）
// ---------------------------------------------------------------------------
const rows = computed(() =>
  compareNodeKeys({ serverKeys: serverKeys.value, localKeys: localKeys.value })
)

// ---------------------------------------------------------------------------
// 设备一致性提示
// ---------------------------------------------------------------------------
const deviceWarning = computed(() => {
  if (IS_DEMO) return null
  const bound = String(node.value.keyDeviceId || '').trim()
  // 服务端还没绑定设备 → 这台就是"第一台"，首次上报会把本机绑上去。
  if (!bound) return null
  if (!hasDeviceCredential.value) {
    return {
      title: '本机没有该节点的设备凭据',
      detail: '该节点的密钥是在另一台设备上生成的，登记公钥会被平台按「设备不一致」拒绝。请改回原设备，或在「节点首次初始化」里用本机重新生成一套。'
    }
  }
  // 私钥在，但公钥读不出来（记录损坏）。这与"换设备"不同：能做的只有重新激活。
  if (!deviceFingerprintValue.value) {
    return {
      title: '本机的设备凭据读不出公钥',
      detail: '该节点的设备私钥在，但对应的公钥记录损坏。登记公钥会被平台按「设备不一致」拒绝，需要重新激活该节点。'
    }
  }
  if (deviceFingerprintValue.value !== bound) {
    return {
      title: '本机设备与平台绑定的不是同一台',
      detail: '本机持有一个设备凭据，但与平台记录的不是同一台设备。登记公钥同样会被拒绝，请确认是否用过另一个浏览器配置或另一台机器。'
    }
  }
  return null
})

// ---------------------------------------------------------------------------
// 生成并登记
// ---------------------------------------------------------------------------
function selfTestOf(card) {
  const ref = selfTestKeyRef(card)
  return ref ? selfTestResults.value[ref] : null
}

/** 自检对象：优先平台在产那一版对应的本机材料；没有则用本机最新的一把。 */
function selfTestKeyRef(card) {
  if (card.localKey) return card.localKey.keyRef
  const mine = localKeys.value.filter((k) => k.algorithm === card.algorithm)
  return mine.length ? mine[mine.length - 1].keyRef : ''
}

/**
 * 生成一把新密钥并登记公钥。
 *
 * ⚠️ **每次生成都铸一个新的 keyId**（`cryptoProvider.generate` 内部按
 *    `mintKeyId(nodeId, algorithm)` 铸），所以平台侧是"新的一行"，旧行被降级为
 *    RETIRED —— 这正是阶段 1 判据④要看的：新逻辑密钥**不复用**旧的 SM2/SSCL `u`。
 *    如果这里复用旧 keyId，平台会走"同 keyId 同版本"的幂等分支原地返回，
 *    界面显示"登记成功"而密钥其实没换。
 *
 * ⚠️ `keyId` / `keyVersion` **必须**转发 `generate()` 的返回值（节点本地 keyRef
 *    里的那两段）。不转发的话服务端会自己铸一个 keyId 并"成功"落库 ——
 *    两边各自正常，只是从此按引用找不到那把密钥。
 */
async function handleGenerate(card) {
  if (generating.value) return
  generating.value = card.algorithm
  try {
    const options = { nodeId: node.value.nodeId }
    if (card.algorithm === 'KYBER') options.variant = kyberVariant.value

    const generated = await cryptoProvider.generate(card.algorithm, options)
    const result = await registerSelfNodePublicKey(
      card.algorithm,
      generated.publicKey,
      card.algorithm === 'KYBER' ? String(generated.variant) : undefined,
      // 传**设备公钥指纹**（与激活时服务端写进 `Node.key_device_id` 的是同一个值），
      // 不是浏览器级的随机串 —— 后者是自报身份，服务端验证不了。
      deviceFingerprintValue.value,
      generated.keyId,
      generated.version
    )

    await load()

    // 登记成功 = "平台收到了这把公钥"，不等于"这把真能用"。
    // 两者分开报：生成页当场自检一次，把故障挡在第一次真实分发之前。
    const check = await cryptoProvider.selfTest(card.algorithm, generated.keyRef)
    selfTestResults.value = { ...selfTestResults.value, [generated.keyRef]: check }

    const head = card.active
      ? `${card.label} 新密钥已登记，旧的（${card.active.keyId}）已降为「已被取代」`
      : `${card.label} 公钥已登记`
    if (check.ok) {
      ElMessage.success(`${head}；自检通过`)
    } else {
      ElMessage.warning(`${head}；但自检未过：${check.detail}`)
    }
  } catch (error) {
    ElMessage.error(`${card.label} 生成/登记失败：${describeError(error)}`)
  } finally {
    generating.value = ''
  }
}

/** 自检：用本地这份材料真跑一轮往返。失败**不抛错**（`selfTest` 把失败当结论返回）。 */
async function runSelfTest(algorithm, keyRef) {
  if (!keyRef || testing.value) return
  testing.value = keyRef
  try {
    const result = await cryptoProvider.selfTest(algorithm, keyRef)
    selfTestResults.value = { ...selfTestResults.value, [keyRef]: result }
  } finally {
    testing.value = ''
  }
}

/**
 * 把失败翻译成"下一步该做什么"。
 *
 * 分支**按错误码**，不按文案：`error.errorCode` 来自冻结契约
 * （`api_contract.ERR_*`，经 `@/api/pqkds/http` 附在错误对象上），
 * 文案改了也不会让分支走错。
 */
function describeError(error) {
  const message = error?.message || String(error)
  switch (error?.errorCode) {
    case NODE_SELF_ERR.DEVICE_MISMATCH:
      return `${message}。本机不是该节点绑定的设备：请改回原设备，或在「节点首次初始化」里用本机重新生成一套`
    case NODE_SELF_ERR.KEY_VERSION_MISMATCH:
      return `${message}。本地记录的 keyId 与平台已有行冲突，请重新生成（不要手工指定 keyId）`
    case NODE_SELF_ERR.ALGORITHM_NOT_ALLOWED:
      return `${message}。平台只接受 SM2 / SSCL / KYBER / FALCON 四个规范名`
    default:
      return message
  }
}

function formatTime(value) {
  if (!value) return '—'
  // 后端下发 ISO（`_iso`）。按本机时间展示，不换算时区 —— 与其它节点侧页面一致。
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

onMounted(load)
</script>

<style scoped>
.gen-create__card { max-width: 1180px; margin: 24px auto; }
.gen-create__header { display: flex; align-items: center; justify-content: space-between; }
.gen-create__header h2 { margin: 0; font-size: 18px; }
.gen-create__header-side { display: flex; align-items: center; gap: 8px; }
.gen-create__lead { margin: 0 0 16px; color: var(--kms-text-secondary, #606266); line-height: 1.7; }
.gen-create__device { margin-bottom: 16px; }
.gen-create__device p { margin: 6px 0 0; line-height: 1.7; }
.gen-create__grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 12px; margin-bottom: 20px;
}
.gen-create__algo {
  border: 1px solid var(--el-border-color, #dcdfe6); border-radius: 6px;
  padding: 12px 14px; display: flex; flex-direction: column; gap: 8px;
}
.gen-create__algo.is-active { border-color: var(--el-color-success, #67c23a); }
.gen-create__algo.is-warn { border-color: var(--el-color-danger, #f56c6c); }
.gen-create__algo-head { display: flex; align-items: center; justify-content: space-between; }
.gen-create__algo-name { font-weight: 600; }
.gen-create__algo-role { margin: 0; font-size: 12px; color: var(--kms-text-secondary, #909399); line-height: 1.6; }
.gen-create__facts { margin: 0; }
.gen-create__fact { display: flex; gap: 8px; font-size: 12px; line-height: 1.9; }
.gen-create__fact dt { color: var(--kms-text-secondary, #909399); flex: 0 0 60px; }
.gen-create__fact dd { margin: 0; word-break: break-all; }
.gen-create__fact-note { color: var(--kms-text-secondary, #909399); margin-left: 6px; }
.gen-create__reconcile { margin: 4px 0; }
.gen-create__pending { font-size: 12px; color: var(--el-color-warning, #e6a23c); line-height: 1.6; }
.gen-create__match { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--el-color-success, #67c23a); }
.gen-create__selftest { font-size: 12px; line-height: 1.6; word-break: break-all; }
.gen-create__algo-actions { display: flex; align-items: center; gap: 8px; margin-top: auto; }
.gen-create__variant { width: 170px; }
.gen-create__note {
  margin: 0 0 24px; padding: 10px 14px; border-radius: 6px;
  background: var(--el-fill-color-light, #f5f7fa);
  font-size: 13px; color: var(--kms-text-secondary, #606266); line-height: 1.8;
}
.gen-create__section-title { margin: 0 0 12px; font-size: 15px; }
.gen-create__section-note { margin-left: 8px; font-size: 12px; font-weight: 400; color: var(--kms-text-secondary, #909399); }
.gen-create__table { margin-bottom: 12px; }
.gen-create__empty { margin: 0; color: var(--kms-text-secondary, #909399); font-size: 13px; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.is-ok { color: var(--el-color-success, #67c23a); }
.is-bad { color: var(--el-color-danger, #f56c6c); }
.is-muted { color: var(--kms-text-secondary, #909399); }
</style>
