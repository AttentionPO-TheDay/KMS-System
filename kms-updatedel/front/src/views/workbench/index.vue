<template>
  <section class="app-container workbench-page">

    <el-card shadow="never" class="hero-card">
      <div class="hero-layout">
        <div class="hero-user">
          <el-avatar :src="userStore.avatar" :size="56" />
          <div class="hero-user-text">
            <h2 class="hero-name">{{ greeting }}，{{ userStore.name || '未登录用户' }}</h2>
            <div class="hero-meta">
              <el-tag size="small" effect="plain">{{ levelText }}</el-tag>
              <span class="hero-tip">以下数据仅统计你本人的密钥与分发记录</span>
            </div>
          </div>
        </div>
        <div class="hero-actions">
          <span v-if="updatedAt" class="hero-updated">更新于 {{ updatedAt }}</span>
          <el-button :icon="Refresh" :loading="loading" @click="loadAll">刷新</el-button>
        </div>
      </div>
    </el-card>


    <section class="subsystem-portal" aria-labelledby="subsystem-portal-title">
      <div class="portal-heading">
        <h3 id="subsystem-portal-title">业务子系统</h3>
        <p>每个子系统负责密钥生命周期的一个阶段，进入后侧边栏只显示该子系统的功能。</p>
      </div>
      <div class="subsystem-grid">
        <button
          v-for="entry in subsystemEntries"
          :key="entry.key"
          type="button"
          class="subsystem-card"
          :data-subsystem-key="entry.key"
          :data-subsystem-path="entry.path || ''"
          :class="{ 'is-disabled': !entry.available }"
          :disabled="!entry.available"
          :aria-label="entry.available ? `进入${entry.title}` : `${entry.title}不可用：${entry.disabledReason}`"
          :title="entry.available ? `进入${entry.title}` : entry.disabledReason"
          @click="openSubsystem(entry)"
        >
          <span class="subsystem-icon" aria-hidden="true">
            <el-icon><component :is="entry.iconComponent" /></el-icon>
          </span>
          <span class="subsystem-copy">
            <strong>{{ entry.title }}</strong>
            <span>{{ entry.description }}</span>
          </span>
          <span class="subsystem-action" aria-hidden="true">
            {{ entry.available ? '进入' : '暂无权限' }}
            <el-icon v-if="entry.available"><ArrowRight /></el-icon>
          </span>
        </button>
      </div>
    </section>


    <el-row :gutter="16">
      <el-col v-for="item in kpiCards" :key="item.title" :xs="24" :sm="12" :lg="6">
        <el-card shadow="never" class="kpi-card">
          <div class="kpi-head">
            <el-icon class="kpi-icon"><component :is="item.icon" /></el-icon>
            <span>{{ item.title }}</span>
          </div>
          <div class="kpi-value">{{ item.value }}</div>
          <div class="kpi-hint">{{ item.hint }}</div>
        </el-card>
      </el-col>
    </el-row>


    <el-row :gutter="16">

      <el-col :xs="24" :lg="16">
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="section-head">
              <span>近 7 天密钥生成趋势</span>
              <span class="section-sub">{{ sourceHint('generate', `近 7 天新增 ${trend.total} 把`) }}</span>
            </div>
          </template>
          <div v-loading="isLoading('generate')" class="chart-wrap" :class="{ 'is-unavailable': sourceState.generate !== STAT_READY }">
            <div ref="trendChartRef" class="chart-box chart-box-tall" :class="{ 'is-empty': trend.total === 0 }"></div>
            <p v-if="chartNotice('generate', trend.total === 0, '近 7 天无新增')" class="chart-notice">
              {{ chartNotice('generate', trend.total === 0, '近 7 天无新增') }}
            </p>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="8">
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="section-head">
              <span>密钥算法分布</span>
              <span class="section-sub">累计 {{ countText(generateTotal) }} 把</span>
            </div>
          </template>
          <div v-loading="isLoading('generate')" class="chart-wrap" :class="{ 'is-unavailable': sourceState.generate !== STAT_READY }">
            <div ref="algorithmChartRef" class="chart-box chart-box-tall"></div>
            <p v-if="chartNotice('generate', generateTotal === 0, '尚未登记密钥')" class="chart-notice">
              {{ chartNotice('generate', generateTotal === 0, '尚未登记密钥') }}
            </p>
          </div>
        </el-card>
      </el-col>

    </el-row>


    <el-row :gutter="16">
      <el-col :xs="24" :lg="8">
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="section-head">
              <span>密钥状态分布</span>
              <span class="section-sub">每把密钥的最新版本</span>
            </div>
          </template>
          <div v-loading="isLoading('lifecycle')" class="chart-wrap" :class="{ 'is-unavailable': sourceState.lifecycle !== STAT_READY }">
            <div ref="keyStatusChartRef" class="chart-box"></div>
            <p v-if="chartNotice('lifecycle', lifecycleTotal === 0, '尚未登记密钥')" class="chart-notice">
              {{ chartNotice('lifecycle', lifecycleTotal === 0, '尚未登记密钥') }}
            </p>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="8">
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="section-head">
              <span>上链状态分布</span>
              <span class="section-sub">最新版本的登记存证</span>
            </div>
          </template>
          <div v-loading="isLoading('generate')" class="chart-wrap" :class="{ 'is-unavailable': sourceState.generate !== STAT_READY }">
            <div ref="chainChartRef" class="chart-box"></div>
            <p v-if="chartNotice('generate', generateTotal === 0, '尚无密钥登记存证')" class="chart-notice">
              {{ chartNotice('generate', generateTotal === 0, '尚无密钥登记存证') }}
            </p>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="8">
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="section-head">
              <span>分发状态分布</span>
              <span class="section-sub">{{ sampleText(distributeRecords.length, distributeTotal) }}</span>
            </div>
          </template>
          <div v-loading="isLoading('distribute')" class="chart-wrap" :class="{ 'is-unavailable': sourceState.distribute !== STAT_READY }">
            <div ref="distributeChartRef" class="chart-box"></div>
            <p v-if="chartNotice('distribute', distributeTotal === 0, '尚未发起密钥分发')" class="chart-notice">
              {{ chartNotice('distribute', distributeTotal === 0, '尚未发起密钥分发') }}
            </p>
          </div>
        </el-card>
      </el-col>
    </el-row>


    <el-row :gutter="16">
      <el-col :span="24">
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="section-head">
              <span>当前生产密钥</span>
              <span class="section-sub">
                初始化与后续生成统一登记，更新保留 keyId 并递增版本
              </span>
            </div>
          </template>
          <div v-loading="isLoading('nodeKey')" class="base-key-layout">
            <div class="base-key-list">
              <div v-for="item in baseKeys" :key="item.algo" class="base-key-row">
                <span class="base-key-name">{{ item.label }}</span>
                <el-tag
                  size="small"
                  :type="baseKeyTagType(item)"
                  effect="plain"
                >
                  {{ item.current ? item.current.statusLabel : '未登记' }}
                </el-tag>
                <span class="base-key-id mono">
                  <template v-if="item.current">
                    {{ item.current.keyId }} · v{{ item.current.keyVersion }}
                  </template>
                  <template v-else>—</template>
                </span>
                <span class="base-key-meta">

                  <template v-if="item.versions > 1">共 {{ item.versions }} 版 · </template>
                  <template v-if="item.current?.publicKeyHash">
                    指纹 {{ String(item.current.publicKeyHash).slice(0, 16) }}…
                  </template>
                </span>
              </div>
              <p v-if="nodeKeyNotice" class="base-key-notice">{{ nodeKeyNotice }}</p>
            </div>

            <div class="feature-list">
              <div class="feature-heading">当前可用能力</div>
              <div v-for="item in featureItems" :key="item.code" class="feature-item">
                <div>
                  <div class="feature-name">{{ item.name }}</div>
                  <div class="feature-system">{{ item.system }}</div>
                </div>
                <el-tag size="small" :type="item.granted ? 'success' : 'info'" effect="light">
                  {{ item.granted ? '已具备' : '待申请' }}
                </el-tag>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </section>
</template>

<script setup>
import { computed, markRaw, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ArrowRight, CircleCheck, Key, Refresh, Share } from '@element-plus/icons-vue'
import * as echarts from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TitleComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import useUserStore from '@/store/modules/user'
import { listDistributionBatches } from '@/services/user-distribution-api'
import { getSelfWorkbench } from '@/api/pqkds/node-self'
import { formatGenerationName } from '@/utils/crypto/generation-scheme.js'
import { permissionFeatures } from '@/services/permission-api'
import { isAdminLevel, roleLevelText } from '@/utils/role'
import usePermissionStore from '@/store/modules/permission'
import { SUBSYSTEMS, findSubsystemRoute } from '@/utils/subsystems'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { IS_DEMO } from '@/utils/entry-mode'
import { getDemoContext } from '@/utils/demo-context'

const router = useRouter()


echarts.use([LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent, CanvasRenderer])


const CHART_COLORS = {
  brand: '#1677ff',
  brandSubtle: '#e6f4ff',
  success: '#00b42a',
  warning: '#ff7d00',
  danger: '#f53f3f',
  neutral: '#8a919f',
  violet: '#7c5cff',
  border: '#e5e7eb',
  borderStrong: '#d0d5dd',
  borderSubtle: '#f0f2f5',
  surface: '#fafbfd',
  textPrimary: '#1f2329',
  textSecondary: '#646a73'
}

const CHART_PALETTE = [
  CHART_COLORS.brand,
  CHART_COLORS.success,
  CHART_COLORS.warning,
  CHART_COLORS.violet,
  CHART_COLORS.neutral
]

// 阶段 3：新签发的记录用 Kyber / Falcon；CL-* 留在末尾，
// 只为让历史记录的排序位置保持稳定，不再产生新值。
const ALGORITHM_ORDER = ['SM2', 'SSCL', 'KYBER', 'FALCON_CL_V1', 'FALCON']

// 生命周期状态：0 有效 / 1 已冻结 / 2 已更新 / 3 已回收（文本状态为英文别名）
const KEY_STATUS_META = [
  { code: 'ACTIVE', label: '可用', color: CHART_COLORS.success },
  { code: 'RETIRED', label: '已被取代', color: CHART_COLORS.brand },
  { code: 'REVOKED', label: '已回收', color: CHART_COLORS.neutral },
  { code: 'EXPIRED', label: '已过期', color: CHART_COLORS.warning },
  { code: 'PENDING', label: '待启用', color: CHART_COLORS.violet },
  { code: 'LEGACY', label: '历史记录', color: CHART_COLORS.neutral }
]

// 上链状态：0 待上链 / 1 已上链 / 2 上链失败
const CHAIN_STATUS_META = [
  { code: 'confirmed', label: '已上链', color: CHART_COLORS.success },
  { code: 'pending', label: '待确认', color: CHART_COLORS.warning },
  { code: 'failed', label: '上链失败', color: CHART_COLORS.danger },
  { code: 'unregistered', label: '未提交', color: CHART_COLORS.neutral }
]

// 分发状态：0 待分发 / 1 分发中 / 2 分发成功 / 3 分发失败
const DISTRIBUTE_STATUS_META = [
  { code: '2', label: '分发成功', color: CHART_COLORS.success },
  { code: '1', label: '分发中', color: CHART_COLORS.brand },
  { code: '0', label: '待分发', color: CHART_COLORS.warning },
  { code: '3', label: '分发失败', color: CHART_COLORS.danger }
]

// （原「权限申请状态」的 PERMISSION_STATUS_META 已随阶段 8 下线的审批流一并删除：
//   它喂的进度条恒为空，留着只会让人以为"还有这么个流程"。）

const STAT_LOADING = 'loading'
const STAT_READY = 'ready'
const STAT_ERROR = 'error'
const STAT_NA = 'na'
const STATE_TEXT = {
  [STAT_LOADING]: '加载中…',
  [STAT_ERROR]: '数据获取失败',
  [STAT_NA]: '未获取到用户信息'
}

// 单次统计拉取的上限，超过时卡片会标注「已统计 N 条」
const FETCH_PAGE_SIZE = 200
const TREND_DAYS = 7

const userStore = useUserStore()

const loading = ref(false)
const updatedAt = ref('')
const sourceState = reactive({
  generate: STAT_LOADING,
  lifecycle: STAT_LOADING,
  distribute: STAT_LOADING,
  // 权限申请那一路（`permission`）在阶段 8 之后恒为空 —— 它原先只喂一张死卡片。
  // 现在这一格归**本节点的基础密钥**（`NodeLongTermKey`，走 `/node-self/keys/`）。
  nodeKey: STAT_LOADING
})

const generateTotal = ref(null)
const lifecycleTotal = ref(null)
const distributeRecords = ref([])
const distributeTotal = ref(null)
const nodeKeys = ref([])
const keySummary = ref(null)
const featureAccess = reactive({
  AUTO_UPDATE: false
})

const trendChartRef = ref(null)
const algorithmChartRef = ref(null)
const keyStatusChartRef = ref(null)
const chainChartRef = ref(null)
const distributeChartRef = ref(null)
const chartInstances = new Map()

let resizeFrame = 0
let unmounted = false

const greeting = computed(() => {
  const hour = new Date().getHours()
  if (hour < 6) return '凌晨好'
  if (hour < 12) return '上午好'
  if (hour < 14) return '中午好'
  if (hour < 18) return '下午好'
  return '晚上好'
})

const levelText = computed(() => roleLevelText(userStore.roleLevel))

// ---------------------------------------------------------------------------
// 业务子系统入口
// ---------------------------------------------------------------------------
const permissionStore = usePermissionStore()


const SUBSYSTEM_ICONS = { Key: markRaw(Key), Refresh: markRaw(Refresh), Share: markRaw(Share) }


const subsystemEntries = computed(() =>
  SUBSYSTEMS.map((sub) => {
    const found = findSubsystemRoute(permissionStore.sidebarRouters, sub)
    // 第一个子菜单就是该子系统的入口页（§11.2 每个分区下第一项都是主功能）
    const firstChild = found?.children?.[0] || null
    const path = firstChild
      ? `${String(found.zone.path || '').replace(/\/+$/, '')}/${String(firstChild.path || '').replace(/^\/+/, '')}`
      : null
    return {
      ...sub,
      iconComponent: SUBSYSTEM_ICONS[sub.icon],
      path,
      available: Boolean(path),
      disabledReason: found ? '该子系统下没有可访问的页面' : '当前账号没有该子系统的权限'
    }
  })
)

function openSubsystem(entry) {
  if (!entry.available || !entry.path) {
    ElMessage.warning(`${entry.title}不可用：${entry.disabledReason}`)
    return
  }
  // 确认目标路由真的注册过，避免点了落到 404。
  // 这类失败不报错、只显示 404 页，事后很难追 —— 宁可在这里先说清楚。
  const resolved = router.resolve(entry.path)
  if (!resolved.matched.length || resolved.matched.some((r) => r.path === '/:pathMatch(.*)*')) {
    ElMessage.warning(`${entry.title}页面尚未加载，请刷新后重试`)
    return
  }
  router.push(entry.path)
}

const kpiCards = computed(() => [
  {
    title: '累计生成密钥',
    icon: markRaw(Key),
    value: displayCount('generate', generateTotal.value),
    hint: sourceHint('generate', `含初始化 · 近 7 天新增 ${trend.value.total} 把`)
  },
  {
    title: '有效密钥',
    icon: markRaw(CircleCheck),
    value: displayCount('lifecycle', activeKeyCount.value),
    hint: sourceHint('lifecycle', `已回收 ${revokedKeyCount.value} 个 · 累计 ${countText(lifecycleTotal.value)} 个`)
  },
  {
    title: '分发记录',
    icon: markRaw(Share),
    value: displayCount('distribute', distributeTotal.value),
    hint: sourceHint('distribute', `分发成功 ${distributeSucceeded.value} 条`)
  },
  {
    title: '已上链密钥',
    icon: markRaw(CircleCheck),
    value: displayCount('generate', keySummary.value?.chain?.confirmed || 0),
    hint: sourceHint('generate', `登记版本 ${countText(keySummary.value?.versionTotal || 0)} 版 · 更新不新增密钥数`)
  }
])

const trend = computed(() => {
  const rows = keySummary.value?.trend || buildRecentDays(TREND_DAYS).map(day => ({ date: day.key, count: 0 }))
  return { labels: rows.map(row => `${Number(row.date.slice(5, 7))}/${Number(row.date.slice(8, 10))}`),
    values: rows.map(row => row.count), total: rows.reduce((sum, row) => sum + row.count, 0) }
})

const algorithmItems = computed(() => {
  const counts = keySummary.value?.algorithms || {}
  const names = [...ALGORITHM_ORDER, ...Object.keys(counts).filter(name => !ALGORITHM_ORDER.includes(name))]
  const labels = { SM2: 'SM2', SSCL: 'SSCL', KYBER: 'Kyber 核心', FALCON: 'Falcon 签名', FALCON_CL_V1: '无证书格加密' }
  return names.map((name, index) => ({ name: labels[name] || name, value: counts[name] || 0,
    itemStyle: { color: CHART_PALETTE[index % CHART_PALETTE.length] } }))
})

const keyStatusItems = computed(() => KEY_STATUS_META.map(meta => ({ name: meta.label,
  value: keySummary.value?.statuses?.[meta.code] || 0, itemStyle: { color: meta.color } })))

const chainItems = computed(() => CHAIN_STATUS_META.map(meta => ({ name: meta.label,
  value: keySummary.value?.chain?.[meta.code] || 0, itemStyle: { color: meta.color } })))

const distributeItems = computed(() =>
  groupCount(distributeRecords.value, DISTRIBUTE_STATUS_META, (row) =>
    row?.distributeStatus == null ? '' : String(row.distributeStatus)
  )
)

const activeKeyCount = computed(() => keySummary.value?.active || 0)
const revokedKeyCount = computed(() => keySummary.value?.revoked || 0)
const distributeSucceeded = computed(
  () => distributeRecords.value.filter((row) => String(row?.distributeStatus) === '2').length
)

// ---------------------------------------------------------------------------
// 基础密钥（本节点那四套）
// ---------------------------------------------------------------------------

const BASE_KEY_ALGOS = [
  { algo: 'KYBER', label: 'Kyber', role: '后量子密钥封装' },
  { algo: 'SSCL', label: 'SSCL', role: '保护 SM4 会话密钥' },
  { algo: 'SM2', label: 'SM2', role: '保护 SM4 会话密钥' },
  { algo: 'FALCON', label: 'Falcon', role: '签名与验签' },
  { algo: 'FALCON_CL_V1', label: '格加密', role: '保护 SM4 会话密钥' }
]


const baseKeys = computed(() =>
  BASE_KEY_ALGOS.map((def) => {
    const rows = nodeKeys.value.filter((k) => String(k?.algorithm || '').toUpperCase() === def.algo)
    const current = rows.find((k) => k?.allowsNewWork === true) || rows[0] || null
    return {
      ...def,
      label: current ? formatGenerationName(def.algo, current.generation) : def.label,
      versions: current?.versions || rows.length,
      current
      // 没有 allowsNewWork 的行（全部已被取代/回收）时 current 为 null，
      // 页面显示「未登记」—— 这是如实的（当前确实没有可用的那一把）。
    }
  })
)

const baseKeyNotice = computed(() => {
  if (sourceState.nodeKey === STAT_NA) {
    return '管理员账号不映射到节点，因此没有本机基础密钥。'
  }
  if (sourceState.nodeKey !== STAT_READY) {
    return STATE_TEXT[sourceState.nodeKey] || ''
  }
  return nodeKeys.value.length ? '' : '当前没有可用的生产密钥，请在密钥生成中登记新密钥。'
})


function baseKeyTagType(item) {
  if (!item.current) {
    return 'info'
  }
  const label = String(item.current.statusLabel || '')
  if (label.includes('可用')) return 'success'
  if (label.includes('回收') || label.includes('过期')) return 'danger'
  return 'warning'
}

const featureItems = computed(() => [
  {
    code: 'AUTO_UPDATE',
    name: permissionFeatures.AUTO_UPDATE.label,
    system: '生命周期域',
    granted: isAdminLevel(userStore.roleLevel) || featureAccess.AUTO_UPDATE
  }
])

function isLoading(source) {
  return sourceState[source] === STAT_LOADING
}

function countText(value) {
  if (value == null) return '—'
  const number = Number(value)
  return Number.isFinite(number) ? number.toLocaleString('zh-CN') : '-'
}

function displayCount(source, value) {
  return sourceState[source] === STAT_READY ? countText(value) : '-'
}

function sourceHint(source, text) {
  return sourceState[source] === STAT_READY ? text : STATE_TEXT[sourceState[source]] || ''
}

function sampleText(shown, total) {
  if (total == null) {
    return shown ? `已统计 ${shown} 条` : ''
  }
  return Number(total) > Number(shown) ? `共 ${countText(total)} 条 · 已统计 ${shown} 条` : `共 ${countText(total)} 条`
}

// Empty data remains distinct from request failures; categories retain their zero counts.
function chartNotice(source, isEmpty, emptyText = '') {
  return sourceState[source] === STAT_READY ? (isEmpty ? emptyText : '') : STATE_TEXT[sourceState[source]] || ''
}

function groupCount(rows, metaList, resolveCode) {
  const buckets = new Map(metaList.map((meta) => [meta.code, 0]))
  let unknown = 0
  rows.forEach((row) => {
    const code = resolveCode(row)
    if (buckets.has(code)) {
      buckets.set(code, buckets.get(code) + 1)
    } else {
      unknown += 1
    }
  })
  const items = metaList.map((meta) => ({
    name: meta.label,
    value: buckets.get(meta.code),
    itemStyle: { color: meta.color }
  }))
  if (unknown > 0) {
    items.push({ name: '未知', value: unknown, itemStyle: { color: CHART_COLORS.neutral } })
  }
  return items
}

function buildRecentDays(days) {
  const result = []
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  for (let offset = days - 1; offset >= 0; offset -= 1) {
    const date = new Date(today)
    date.setDate(today.getDate() - offset)
    result.push({
      key: toDateKey(date),
      label: `${date.getMonth() + 1}/${date.getDate()}`
    })
  }
  return result
}

// 后端 cre_time 为字符串，统一按前 10 位取本地日期，避免时区偏移
function toDateKey(value) {
  if (!value) {
    return ''
  }
  if (value instanceof Date) {
    const month = String(value.getMonth() + 1).padStart(2, '0')
    const day = String(value.getDate()).padStart(2, '0')
    return `${value.getFullYear()}-${month}-${day}`
  }
  const matched = String(value).match(/^(\d{4})-(\d{2})-(\d{2})/)
  return matched ? `${matched[1]}-${matched[2]}-${matched[3]}` : ''
}

function errorText(error) {
  if (typeof error === 'string') {
    return error
  }
  return error?.message || '请求失败'
}

async function ensureIdentity() {
  // Demo 会话不写普通模式的 Admin-Token；其身份由受控 Demo 上下文和请求头携带。
  // 不能把“没有普通 token”误判成“没有用户信息”，否则连本节点基础密钥
  // (`/node-self/keys/`) 都不会查询，工作台所有卡片都会显示未获取到用户信息。
  if (IS_DEMO) {
    const demo = getDemoContext()
    return Boolean(demo?.principalType)
  }
  if (!userStore.token) {
    return false
  }
  if (userStore.id) {
    return true
  }
  try {
    await userStore.getInfo()
  } catch {
    return Boolean(userStore.id)
  }
  return Boolean(userStore.id)
}


const BATCH_STATUS_TO_CODE = {
  success: '2', // 分发成功
  partial: '1', // 部分成功（图表该档标签是"分发中"，语义上并入同一档）
  pending: '0', // 待分发
  failed: '3' // 分发失败
}

async function loadDistribute() {
  try {
    const data = await listDistributionBatches({ limit: FETCH_PAGE_SIZE })
    const rows = (Array.isArray(data?.items) ? data.items : []).map((batch) => ({
      ...batch,
      // 映射成图表认的数字码，字段名沿用旧的，前端其余部分无需改动
      distributeStatus: BATCH_STATUS_TO_CODE[String(batch?.status)] ?? '0',
      distributeTime: batch?.createdAt
    }))
    distributeRecords.value = rows
    distributeTotal.value = data?.total == null ? rows.length : Number(data.total)
    sourceState.distribute = STAT_READY
  } catch {
    distributeRecords.value = []
    distributeTotal.value = null
    sourceState.distribute = STAT_ERROR
  }
}


function loadPermission() {
  featureAccess.AUTO_UPDATE = true
}

// 阶段 8：hasApprovedTemporaryRequest 已随审批流一并移除
// （不再有"已批准的临时申请"这个概念可供判断）。

// Initialization, generation and rotation share the same registry and aggregate contract.
async function loadNodeKeys() {
  try {
    const identity = getDemoContext()
    const data = await getSelfWorkbench()
    if (IS_DEMO && identity?.nodeId && data?.nodeId !== identity.nodeId) throw new Error('节点统计身份不一致')
    keySummary.value = data
    nodeKeys.value = Array.isArray(data?.currentKeys) ? data.currentKeys : []
    generateTotal.value = data.total
    lifecycleTotal.value = data.total
    for (const source of ['nodeKey', 'generate', 'lifecycle']) sourceState[source] = STAT_READY
  } catch {
    keySummary.value = null
    nodeKeys.value = []
    generateTotal.value = null
    lifecycleTotal.value = null
    for (const source of ['nodeKey', 'generate', 'lifecycle']) sourceState[source] = STAT_ERROR
  }
}

async function loadAll() {
  loading.value = true
  try {
    const ready = await ensureIdentity()
    if (!ready) {
      Object.keys(sourceState).forEach((key) => {
        sourceState[key] = STAT_NA
      })
      return
    }
    // 数据源并行拉取，单个失败只影响对应卡片
    Object.keys(sourceState).forEach(key => { sourceState[key] = STAT_LOADING })
    await Promise.allSettled([loadDistribute(), loadPermission(), loadNodeKeys()])
    updatedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  } finally {
    loading.value = false
    await renderCharts()
  }
}

function buildTrendOption() {
  return {
    animation: false,
    grid: { left: 12, right: 22, top: 20, bottom: 28, containLabel: true },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (value) => `${value} 个`
    },
    xAxis: {
      type: 'category',
      boundaryGap: true,
      data: trend.value.labels,
      axisLine: { lineStyle: { color: CHART_COLORS.border } },
      axisTick: { show: false },
      axisLabel: { color: CHART_COLORS.textSecondary, fontSize: 12 }
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: CHART_COLORS.borderSubtle } },
      axisLabel: { color: CHART_COLORS.textSecondary, fontSize: 12 }
    },
    series: [
      {
        name: '新增密钥',
        type: 'line',
        smooth: false,
        symbol: 'circle',
        symbolSize: 7,
        data: trend.value.values,
        lineStyle: { width: 2, color: CHART_COLORS.brand },
        itemStyle: { color: CHART_COLORS.brand, borderColor: CHART_COLORS.surface, borderWidth: 2 },
        areaStyle: { color: CHART_COLORS.brandSubtle }
      }
    ]
  }
}

function buildDistributionOption(items) {
  const total = items.reduce((sum, item) => sum + item.value, 0)
  return {
    animation: false,
    grid: { left: 4, right: 46, top: 16, bottom: 30, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' },
      formatter: params => `${params[0].name}：${params[0].value}（${total ? (params[0].value / total * 100).toFixed(1) : '0'}%）` },
    xAxis: { type: 'value', show: false, minInterval: 1, max: Math.max(1, ...items.map(item => item.value)) * 1.18 },
    yAxis: { type: 'category', inverse: true, data: items.map(item => item.name),
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: CHART_COLORS.textSecondary, fontSize: 12, width: 160, overflow: 'truncate' } },
    series: [{ type: 'bar', barMaxWidth: 14, showBackground: true,
      backgroundStyle: { color: CHART_COLORS.borderSubtle, borderRadius: 4 },
      data: items.map(item => ({ value: item.value, itemStyle: { color: item.itemStyle.color, borderRadius: 4 } })),
      label: { show: true, position: 'right', distance: 10, color: CHART_COLORS.textPrimary, fontSize: 13,
        formatter: ({ value }) => String(value) } }]
  }
}

function renderChart(key, elementRef, option) {
  const element = elementRef.value
  if (!element) {
    return
  }
  let instance = chartInstances.get(key)
  if (instance && instance.isDisposed()) {
    chartInstances.delete(key)
    instance = null
  }
  if (!instance) {
    instance = echarts.init(element)
    chartInstances.set(key, instance)
  }
  instance.setOption(option, true)
}

async function renderCharts() {
  await nextTick()
  // 数据返回时组件可能已卸载，此时不再初始化实例
  if (unmounted) {
    return
  }
  renderChart('trend', trendChartRef, buildTrendOption())
  renderChart('algorithm', algorithmChartRef, buildDistributionOption(algorithmItems.value))
  renderChart('keyStatus', keyStatusChartRef, buildDistributionOption(keyStatusItems.value))
  renderChart('chain', chainChartRef, buildDistributionOption(chainItems.value))
  renderChart('distribute', distributeChartRef, buildDistributionOption(distributeItems.value))
}

function handleResize() {
  if (resizeFrame) {
    return
  }
  resizeFrame = window.requestAnimationFrame(() => {
    resizeFrame = 0
    chartInstances.forEach((instance) => {
      if (instance && !instance.isDisposed()) {
        instance.resize()
      }
    })
  })
}

function disposeCharts() {
  chartInstances.forEach((instance) => {
    if (instance && !instance.isDisposed()) {
      instance.dispose()
    }
  })
  chartInstances.clear()
}

onMounted(() => {
  window.addEventListener('resize', handleResize)
  loadAll()
})

onBeforeUnmount(() => {
  unmounted = true
  window.removeEventListener('resize', handleResize)
  if (resizeFrame) {
    window.cancelAnimationFrame(resizeFrame)
    resizeFrame = 0
  }
  disposeCharts()
})
</script>

<style scoped>
.workbench-page {
  display: block;
  padding-bottom: var(--kms-space-1);
}

/* el-row 是 flex 容器，列的下外边距不会与外层折叠，可直接用它做行间距 */
.workbench-page .el-col {
  margin-bottom: var(--kms-space-4);
}

.hero-card,
.kpi-card,
.section-card {
  border-radius: var(--kms-radius-lg);
}

.hero-layout {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--kms-space-6);
  flex-wrap: wrap;
}

.hero-user {
  display: flex;
  align-items: center;
  gap: var(--kms-space-4);
  min-width: 0;
}

.hero-user-text {
  min-width: 0;
}

.hero-name {
  margin: 0;
  font-size: var(--kms-font-size-xl);
  font-weight: var(--kms-font-weight-semibold);
  color: var(--kms-text-primary);
  line-height: var(--kms-line-height-tight);
}

.hero-meta {
  display: flex;
  align-items: center;
  gap: var(--kms-space-3);
  margin-top: var(--kms-space-2);
  flex-wrap: wrap;
  color: var(--kms-text-secondary);
  font-size: var(--kms-font-size-sm);
}

.hero-tip {
  color: var(--kms-text-tertiary);
  font-size: var(--kms-font-size-xs);
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: var(--kms-space-3);
}

.hero-updated {
  color: var(--kms-text-tertiary);
  font-size: var(--kms-font-size-xs);
}

.kpi-card :deep(.el-card__body) {
  display: flex;
  flex-direction: column;
  gap: var(--kms-space-2);
}

.kpi-head {
  display: flex;
  align-items: center;
  gap: var(--kms-space-2);
  color: var(--kms-text-secondary);
  font-size: var(--kms-font-size-sm);
}

.kpi-icon {
  color: var(--kms-brand);
  font-size: 16px;
}

.kpi-value {
  color: var(--kms-text-primary);
  font-size: var(--kms-font-size-xxl);
  font-weight: var(--kms-font-weight-bold);
  line-height: var(--kms-line-height-tight);
  font-variant-numeric: tabular-nums;
}

.kpi-hint {
  color: var(--kms-text-tertiary);
  font-size: var(--kms-font-size-xs);
}

.section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--kms-space-3);
}

.section-head > span:first-child {
  color: var(--kms-text-primary);
  font-weight: var(--kms-font-weight-semibold);
}

.section-sub {
  color: var(--kms-text-tertiary);
  font-size: var(--kms-font-size-xs);
  font-weight: var(--kms-font-weight-normal);
}

.chart-wrap {
  position: relative;
}

/* echarts 需要容器有确定高度，否则初始化时高度为 0 会渲染空白 */
.chart-box {
  width: 100%;
  height: 214px;
}

.chart-box-tall {
  height: 252px;
}

/* ---------------------------------------------------------------------------
   业务子系统入口（本页主元素）
   --------------------------------------------------------------------------- */
.subsystem-portal {
  margin: 16px 0;
}

.portal-heading {
  margin-bottom: 12px;
}

.portal-heading h3 {
  margin: 0 0 4px;
  font-size: 16px;
  font-weight: 600;
  color: var(--kms-text-primary);
}

.portal-heading p {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--kms-text-secondary);
}

.subsystem-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.subsystem-card {
  display: flex;
  align-items: center;
  width: 100%;
  min-height: 108px;
  padding: 20px;
  gap: 16px;
  border: 1px solid var(--kms-border);
  border-radius: 12px;
  background: var(--kms-surface-1);
  color: var(--kms-text-primary);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease, background-color 0.2s ease;
}

.subsystem-card:hover:not(:disabled) {
  border-color: var(--kms-brand-border);
  background: var(--kms-surface-3);
  box-shadow: var(--kms-shadow-md);
  transform: translateY(-2px);
}

.subsystem-card:focus-visible {
  outline: 3px solid var(--kms-brand-border);
  outline-offset: 3px;
}

.subsystem-card:disabled,
.subsystem-card.is-disabled {
  border-color: var(--kms-border);
  background: var(--kms-surface-2);
  color: var(--kms-text-disabled);
  cursor: not-allowed;
  opacity: 0.68;
}

.subsystem-icon {
  display: inline-flex;
  flex: 0 0 48px;
  width: 48px;
  height: 48px;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  background: var(--kms-brand-subtle);
  color: var(--kms-brand-text);
  font-size: 24px;
}

.subsystem-card:nth-child(2) .subsystem-icon {
  background: var(--kms-warning-subtle);
  color: var(--kms-warning-strong);
}

.subsystem-card:nth-child(3) .subsystem-icon {
  background: var(--kms-success-subtle);
  color: var(--kms-success-strong);
}

.subsystem-copy {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-direction: column;
  gap: 6px;
}

.subsystem-copy strong {
  font-size: 16px;
  font-weight: 600;
}

.subsystem-copy span {
  font-size: 13px;
  line-height: 1.5;
  color: var(--kms-text-secondary);
}

.subsystem-action {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 4px;
  font-size: 14px;
  color: var(--kms-text-secondary);
  white-space: nowrap;
  transition: transform 0.2s ease, color 0.2s ease;
}

.subsystem-card:hover:not(:disabled) .subsystem-action,
.subsystem-card:focus-visible .subsystem-action {
  color: var(--kms-brand-text);
  transform: translateX(3px);
}

.subsystem-card:disabled .subsystem-action,
.subsystem-card.is-disabled .subsystem-action {
  color: var(--kms-text-disabled);
}

@media (max-width: 900px) {
  .subsystem-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 720px) {
  .subsystem-grid { grid-template-columns: minmax(0, 1fr); }
  .subsystem-card { min-height: 92px; padding: 16px; }
}

@media (prefers-reduced-motion: reduce) {
  .subsystem-card,
  .subsystem-action { transition: none; }
}

.chart-notice {
  position: absolute;
  inset: auto 0 0;
  margin: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--kms-text-secondary);
  font-size: var(--kms-font-size-xs);
  line-height: 24px;
}

/* 基础密钥区块：左列四套明细、右列当前可用能力。
   左列份额略大（原来的 1.15fr）—— 每行有 算法名 / 状态标签 / keyId / 指纹，
   比右侧那两行"名称 + 状态标签"宽。 */
.base-key-layout {
  display: grid;
  grid-template-columns: minmax(0, 3fr) minmax(200px, 1fr);
  gap: var(--kms-space-6);
}

.base-key-list {
  display: grid;
  align-content: start;
  gap: var(--kms-space-3);
}

.base-key-row {
  display: grid;
  grid-template-columns: minmax(150px, 1fr) 88px minmax(0, 1.2fr) minmax(0, auto);
  align-items: center;
  gap: var(--kms-space-3);
  padding: var(--kms-space-3) 0;
  border-bottom: 1px solid var(--kms-border);
}

.base-key-row:last-of-type {
  border-bottom: none;
}

.base-key-name {
  font-weight: 600;
  color: var(--kms-text-primary);
}

.base-key-id {
  color: var(--kms-text-secondary);
  font-size: var(--kms-font-size-sm);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.base-key-meta {
  text-align: right;
  color: var(--kms-text-tertiary);
  font-size: var(--kms-font-size-xs, 12px);
}

.base-key-notice {
  margin: var(--kms-space-3) 0 0;
  color: var(--kms-text-tertiary);
  font-size: var(--kms-font-size-sm);
}

.feature-heading {
  color: var(--kms-text-secondary);
  font-size: var(--kms-font-size-sm);
  font-weight: 600;
}

.feature-list {
  display: grid;
  align-content: start;
  gap: var(--kms-space-3);
}

.feature-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--kms-space-3);
  padding: var(--kms-space-3) var(--kms-space-4);
  border: 1px solid var(--kms-border);
  border-radius: var(--kms-radius);
  background: var(--kms-surface-2);
}

.feature-name {
  color: var(--kms-text-primary);
  font-size: var(--kms-font-size-sm);
}

.feature-system {
  margin-top: var(--kms-space-1);
  color: var(--kms-text-tertiary);
  font-size: var(--kms-font-size-xs);
}

@media (max-width: 991.98px) {
  .perm-layout {
    grid-template-columns: minmax(0, 1fr);
  }
}
.chart-wrap.is-unavailable .chart-box { visibility: hidden; }
.chart-wrap.is-unavailable .chart-notice { inset: 0; }
@media (max-width: 767px) {
  .section-head { align-items: flex-start; flex-wrap: wrap; }
  .chart-box-tall { height: 228px; }
  .base-key-layout { grid-template-columns: minmax(0, 1fr); }
  .base-key-row { grid-template-columns: minmax(0, 1fr) auto; gap: 8px; }
  .base-key-id, .base-key-meta { grid-column: 1 / -1; }
  .base-key-id { overflow-wrap: anywhere; }
}
</style>
