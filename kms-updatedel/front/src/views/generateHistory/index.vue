<template>
  <div class="app-container gen-history">
    <el-card shadow="never" class="gen-history__card">
      <template #header>
        <div class="gen-history__header">
          <h2>密钥历史</h2>
          <div class="gen-history__header-side">
            <el-tag v-if="node.nodeId" type="info" size="small">{{ node.nodeId }}</el-tag>
            <el-button size="small" :loading="loading" @click="load">刷新</el-button>
          </div>
        </div>
      </template>

      <el-alert
        v-if="!loading && !mapped"
        type="warning"
        :closable="false"
        show-icon
        title="当前账号未关联任何节点"
        description="密钥历史是节点的账本。请用节点账号登录。"
      />

      <template v-else>
        <p class="gen-history__lead">
          这里是<strong>平台登记的</strong>本节点长期密钥，含被取代、已回收的历史版本。
          私钥不在本表、也不在服务端 —— 它是本机生成的，只存在于本机加密密钥库。
          「本机材料」一列说的是<strong>当前这台浏览器</strong>有没有对应的私钥。
        </p>

        <!-- 换了设备 / 清过站点数据：本页最要紧的一条结论。
             不提示的话，表格里每行都写着"平台有、本机无私钥"，用户只会以为页面坏了。 -->
        <el-alert
          v-if="foreignDevice"
          class="gen-history__alert"
          type="warning"
          :closable="false"
          show-icon
          title="平台上有本节点的密钥，本机却没有任何一把私钥"
          description="这说明密钥是在另一台设备（或另一个浏览器配置）上生成的 —— 本机解不开平台按它们分发的信封。请改回原设备；确实换机了就在「节点首次初始化」里用本机重新生成并登记一套。"
        />

        <!-- 后端一次最多回 200 行且没有分页参数。到顶时**必须**说出来：
             不说的话页面看起来"就这些"，而少掉的那些是更早的版本。 -->
        <el-alert
          v-if="possiblyTruncated"
          class="gen-history__alert"
          type="info"
          :closable="false"
          show-icon
          :title="`只显示了最近 ${SERVER_ROW_LIMIT} 条`"
          description="本节点登记过的密钥行数达到接口上限，更早的版本没有列出来。需要完整历史请直接查服务端 dvadmin_pqkds_node_long_term_keys 表。"
        />

        <el-form inline class="gen-history__filter" @submit.prevent>
          <el-form-item label="算法">
            <el-select v-model="algoFilter" clearable placeholder="全部" class="gen-history__filter-select">
              <el-option v-for="a in algorithmOptions" :key="a" :label="a" :value="a" />
            </el-select>
          </el-form-item>
          <el-form-item label="状态">
            <el-select v-model="statusFilter" clearable placeholder="全部" class="gen-history__filter-select">
              <el-option v-for="o in statusOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="keyId">
            <el-input v-model="keyword" clearable placeholder="包含匹配" style="width: 200px" />
          </el-form-item>
          <el-form-item>
            <el-button @click="resetFilters">重置</el-button>
          </el-form-item>
        </el-form>

        <p class="gen-history__summary">
          共 {{ rows.length }} 条<template v-if="filtered.length !== rows.length">，筛出 {{ filtered.length }} 条</template>
          · 在产 {{ activeCount }} 条
          · 本机持 {{ localCount }} 条
          <span v-if="attentionCount" class="is-bad">· 对账异常 {{ attentionCount }} 条</span>
        </p>

        <el-table v-loading="loading" :data="filtered" size="small" border class="gen-history__table">
          <el-table-column label="算法" width="92" prop="algorithm" />
          <el-table-column label="keyId" min-width="210" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="mono">{{ row.keyId || '（未记录）' }}</span>
              <el-tag v-if="row.server?.legacy" size="small" type="warning" effect="plain" class="gen-history__legacy">历史导入</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="版本" width="70">
            <template #default="{ row }">v{{ row.version }}</template>
          </el-table-column>
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <el-tag v-if="row.server" :type="statusTagType(row.server.status)" size="small">
                {{ row.server.statusLabel }}
              </el-tag>
              <el-tag v-else type="warning" size="small" effect="plain">未登记</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="可用性" width="130">
            <template #default="{ row }">{{ usableText(row) }}</template>
          </el-table-column>
          <el-table-column label="本机材料" width="100">
            <template #default="{ row }">
              <span :class="row.local ? 'is-ok' : 'is-muted'">{{ row.local ? '有私钥' : '无私钥' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="对账" min-width="150">
            <template #default="{ row }">
              <span :class="row.reconcile.ok ? 'is-ok' : 'is-bad'">{{ row.reconcile.text }}</span>
            </template>
          </el-table-column>
          <el-table-column label="公钥体积" width="130">
            <template #default="{ row }">{{ keySizeText(row) }}</template>
          </el-table-column>
          <el-table-column label="绑定设备" min-width="150" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="mono">{{ row.server?.deviceId || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="登记时间" width="160">
            <template #default="{ row }">{{ formatTime(row.createdAt) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="80" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="openDetail(row)">详情</el-button>
            </template>
          </el-table-column>
        </el-table>
        <p v-if="!loading && !filtered.length" class="gen-history__empty">
          {{ rows.length ? '没有符合筛选条件的密钥。' : '这个节点还没有登记过任何长期密钥。到「密钥生成」页生成第一把。' }}
        </p>
      </template>
    </el-card>

    <el-dialog title="密钥详情" v-model="detailOpen" width="780px" append-to-body destroy-on-close>
      <template v-if="detail">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="算法">{{ detail.algorithm }}</el-descriptions-item>
          <el-descriptions-item label="版本">v{{ detail.version }}</el-descriptions-item>
          <el-descriptions-item label="keyId"><span class="mono">{{ detail.keyId || '（未记录）' }}</span></el-descriptions-item>
          <el-descriptions-item label="平台状态">
            <el-tag v-if="detail.server" :type="statusTagType(detail.server.status)" size="small">
              {{ detail.server.statusLabel }}
            </el-tag>
            <el-tag v-else type="warning" size="small" effect="plain">平台未登记</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="可用性">{{ usableText(detail) }}</el-descriptions-item>
          <el-descriptions-item label="安全级别">{{ detail.server?.securityLevel || '—' }}</el-descriptions-item>
          <el-descriptions-item label="公钥体积">{{ keySizeText(detail) }}</el-descriptions-item>
          <el-descriptions-item label="公钥摘要">
            <span class="mono">{{ detail.server?.publicKeyHash || '—' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="绑定设备">
            <span class="mono">{{ detail.server?.deviceId || '—' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="登记时间">{{ formatTime(detail.createdAt) }}</el-descriptions-item>
          <el-descriptions-item label="生效时间">{{ formatTime(detail.server?.effectiveAt) }}</el-descriptions-item>
          <el-descriptions-item label="失效时间">{{ formatTime(detail.server?.expiresAt) }}</el-descriptions-item>
          <el-descriptions-item label="回收时间">{{ formatTime(detail.server?.revokedAt) }}</el-descriptions-item>
          <el-descriptions-item label="回收原因">{{ detail.server?.revokedReason || '—' }}</el-descriptions-item>
          <el-descriptions-item label="历史来源" :span="2">
            {{ detail.server?.legacy ? (detail.server.legacySource || '由旧路径导入（非节点本地生成）') : '节点本地生成' }}
          </el-descriptions-item>
        </el-descriptions>

        <div class="gen-history__reconcile-box">
          <div class="gen-history__reconcile-head">
            <span class="gen-history__reconcile-title">本机对账</span>
            <span :class="detail.reconcile.ok ? 'is-ok' : 'is-bad'">{{ detail.reconcile.text }}</span>
          </div>
          <p class="gen-history__reconcile-body">
            <template v-if="detail.local">
              本机密钥库里有对应的私钥，引用为 <span class="mono">{{ detail.local.keyRef }}</span>。
            </template>
            <template v-else>
              本机密钥库里<strong>没有</strong>对应的私钥。
            </template>
            <template v-if="!detail.reconcile.ok"> 该结论的处置方式见「密钥生成」页对应算法的卡片。</template>
          </p>
        </div>

        <div class="gen-history__pk-box">
          <div class="gen-history__pk-label">公钥（十六进制）</div>
          <div class="gen-history__pk-value">{{ detail.server?.publicKey || detail.local?.publicKey || '（无）' }}</div>
          <p class="gen-history__pk-note">
            公钥是公开量，可以自由展示。私钥<strong>不在本页</strong>，也不在服务端 ——
            本页与后端接口都不提供私钥读取或导出。
          </p>
        </div>
      </template>
      <template #footer>
        <el-button type="primary" @click="detailOpen = false">关 闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="NodeKeyHistory">
/**
 * 密钥历史（菜单 9011，节点端 `/genzone/history`）。
 *
 * 改造前后是两件事
 * ----------------
 * 改造前这里是**用户腿**的「生成历史」：数据来自 `listKeymanage`（`keymanage` 模型，
 * 列是 userId / userName / encrytName / keyValue …），还带一个「新增」弹窗，
 * 让人**手工把密钥值贴进表单**写库（`form.keyValue` 是 textarea 明文）。
 * 那与 §4.4「私钥在节点本地生成并保管、服务端只收公钥」直接冲突 ——
 * 一个把私钥当业务数据填写和展示的页面。
 *
 * 现在它是**只读**的：数据来自 §4.4 的唯一事实来源 `NodeLongTermKey`
 * （`GET /node-self/keys/`），本机侧读加密密钥库（`inspectNodeKeys`），
 * 两边按 `@/utils/crypto/node-key-compare` 的口径对账。
 * **没有新增入口，也没有任何写私钥的路径** —— 密钥只能由「密钥生成」页在
 * 本机产生，这一页只负责把事情说清楚。
 *
 * 为什么不链到「密钥更新与回收」
 * ------------------------------
 * 那个页面（菜单 5000，`parent_id=9410`）是**用户腿**的 `keyupdate`，
 * 操作的是 `keymanage` 模型里的用户密钥，与本页这些节点长期密钥**不是同一批实体**。
 * 链过去会让人以为在处置节点密钥，实际动的是另一套数据，且两边都不会报错。
 *
 * 关于筛选
 * --------
 * 后端这个 GET **不读任何 query**（见 `@/api/pqkds/node-self.js` 的说明），
 * 一律返回本节点全部行。所以筛选在本地做，选项从**已载入的数据**里派生 ——
 * 写死一份算法/状态清单就会在服务端新增状态时静默漏掉。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getSelfNode, listSelfNodeKeys } from '@/api/pqkds/node-self'
import { compareNodeKeys } from '@/utils/crypto/node-key-compare.js'
import { cryptoProvider, KYBER_PK_LENGTHS } from '@/utils/crypto/browser-provider.js'

/**
 * 后端 `_long_term_keys_payload(node, limit=200)` 的条数上限，**与后端同改**。
 * 它只是用来在到顶时提醒"可能被截断"，不参与分页。
 */
const SERVER_ROW_LIMIT = 200

/** 本机独有行在「状态」筛选里的伪取值（它们没有平台状态）。 */
const UNREGISTERED = '__unregistered__'

/**
 * 状态 → 标签颜色。**只有颜色**是前端的：文案一律用服务端下发的 `statusLabel`
 * （`api_contract.KEY_STATUS_CHOICES`）。前端再写一份中文表，漂移的表现就是
 * "界面写着正常、实际已被取代"，而没有任何一处会报错。
 */
const STATUS_TAG_TYPE = { ACTIVE: 'success', PENDING: 'warning', REVOKED: 'danger' }

const loading = ref(true)
const mapped = ref(false)
const node = ref({})
const serverKeys = ref([])
const localKeys = ref([])

const algoFilter = ref('')
const statusFilter = ref('')
const keyword = ref('')

const detailOpen = ref(false)
const detail = ref(null)

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

    // 两边各取一次、各报各的错：合成一个 try 会让"平台读不到"表现成
    // "本机密钥全没了"，而后者会诱导用户去重新生成（私钥本来好好的）。
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
      localKeys.value = []
      ElMessage.error(`读取本机密钥库失败：${local.reason?.message || local.reason}`)
    }
  } catch (error) {
    ElMessage.error(`读取节点信息失败：${error.message}`)
  } finally {
    loading.value = false
  }
}

/** 平台行 ∪ 本机独有行。本机独有的那些必须列出来，否则它们对用户是隐形的。 */
const rows = computed(() =>
  compareNodeKeys({ serverKeys: serverKeys.value, localKeys: localKeys.value })
)

const algorithmOptions = computed(() => [...new Set(rows.value.map((r) => r.algorithm))].sort())

const statusOptions = computed(() => {
  const seen = new Map()
  let hasLocalOnly = false
  for (const row of rows.value) {
    if (row.server) seen.set(row.server.status, row.server.statusLabel)
    else hasLocalOnly = true
  }
  const options = [...seen].map(([value, label]) => ({ value, label }))
  // 本机未登记的行没有任何平台状态，但**筛"全部"时它在**：
  // 不给它一个选项，用户按状态筛过一遍就再也看不到它了。
  if (hasLocalOnly) options.push({ value: UNREGISTERED, label: '平台未登记' })
  return options
})

const filtered = computed(() =>
  rows.value.filter((row) => {
    if (algoFilter.value && row.algorithm !== algoFilter.value) return false
    if (statusFilter.value) {
      const status = row.server ? row.server.status : UNREGISTERED
      if (status !== statusFilter.value) return false
    }
    if (keyword.value) {
      const wanted = keyword.value.trim().toLowerCase()
      if (wanted && !String(row.keyId || '').toLowerCase().includes(wanted)) return false
    }
    return true
  })
)

const activeCount = computed(() => rows.value.filter((r) => r.server?.allowsNewWork).length)
const localCount = computed(() => rows.value.filter((r) => r.local).length)
/** 需要人来处置的行数：`reconcile.ok` 只在"两边都有且逐字节相同"时为真。 */
const attentionCount = computed(() => rows.value.filter((r) => !r.reconcile.ok).length)
const foreignDevice = computed(
  () => !loading.value && mapped.value && serverKeys.value.length > 0 && localKeys.value.length === 0
)
const possiblyTruncated = computed(() => serverKeys.value.length >= SERVER_ROW_LIMIT)

function resetFilters() {
  algoFilter.value = ''
  statusFilter.value = ''
  keyword.value = ''
}

function statusTagType(status) {
  return STATUS_TAG_TYPE[status] || 'info'
}

/** 「还能干什么」由服务端下发的两个布尔量拼出，前端不另写可用性判据。 */
function usableText(row) {
  if (!row.server) return '—'
  if (row.server.allowsNewWork) return '可用于新会话'
  if (row.server.allowsUnwrap) return '仅可解开旧信封'
  return '不可用'
}

/**
 * 公钥体积。Kyber 的变体由**公钥长度**自描述（800/1184/1568），
 * 所以这里顺手把变体标出来 —— 变体对不上是"封装出来的密文对方解不开"
 * 的直接线索，而它在界面上只表现为一个字节数。
 */
function keySizeText(row) {
  const bytes = row.publicKeyBytes
  if (!bytes) return '—'
  if (row.algorithm === 'KYBER') {
    const variant = KYBER_PK_LENGTHS[bytes]
    return variant ? `${bytes} B（Kyber-${variant}）` : `${bytes} B（变体未知）`
  }
  return `${bytes} B`
}

function openDetail(row) {
  detail.value = row
  detailOpen.value = true
}

function formatTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

onMounted(load)
</script>

<style scoped>
.gen-history__card { max-width: 1320px; margin: 24px auto; }
.gen-history__header { display: flex; align-items: center; justify-content: space-between; }
.gen-history__header h2 { margin: 0; font-size: 18px; }
.gen-history__header-side { display: flex; align-items: center; gap: 8px; }
.gen-history__lead { margin: 0 0 16px; color: var(--kms-text-secondary, #606266); line-height: 1.7; }
.gen-history__alert { margin-bottom: 12px; }
.gen-history__filter { margin-bottom: 4px; }
.gen-history__filter-select { width: 160px; }
.gen-history__summary { margin: 0 0 12px; font-size: 13px; color: var(--kms-text-secondary, #606266); }
.gen-history__table { margin-bottom: 12px; }
.gen-history__legacy { margin-left: 6px; }
.gen-history__empty { margin: 0; color: var(--kms-text-secondary, #909399); font-size: 13px; }
.gen-history__reconcile-box {
  margin-top: 12px; padding: 10px 14px; border-radius: 6px;
  background: var(--el-fill-color-light, #f5f7fa);
}
.gen-history__reconcile-head { display: flex; gap: 12px; align-items: baseline; }
.gen-history__reconcile-title { font-weight: 600; font-size: 13px; }
.gen-history__reconcile-body { margin: 6px 0 0; font-size: 13px; line-height: 1.7; color: var(--kms-text-secondary, #606266); }
.gen-history__pk-box { margin-top: 12px; }
.gen-history__pk-label { font-size: 13px; font-weight: 600; margin-bottom: 6px; }
.gen-history__pk-value {
  background: #282c34; color: #abb2bf; padding: 10px; border-radius: 4px;
  font-family: Consolas, Monaco, monospace; font-size: 12px;
  word-break: break-all; max-height: 180px; overflow: auto;
}
.gen-history__pk-note { margin: 8px 0 0; font-size: 12px; color: var(--kms-text-secondary, #909399); line-height: 1.7; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.is-ok { color: var(--el-color-success, #67c23a); }
.is-bad { color: var(--el-color-danger, #f56c6c); }
.is-muted { color: var(--kms-text-secondary, #909399); }
</style>
