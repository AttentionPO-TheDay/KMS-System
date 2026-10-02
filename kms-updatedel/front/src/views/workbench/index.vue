<template>
  <section class="app-container workbench-page">
    <!-- 顶部：身份信息与整体刷新 -->
    <el-card shadow="never" class="hero-card">
      <div class="hero-layout">
        <div class="hero-user">
          <el-avatar :src="userStore.avatar" :size="56" />
          <div class="hero-user-text">
            <h2 class="hero-name">{{ greeting }}，{{ userStore.name || '未登录用户' }}</h2>
            <div class="hero-meta">
              <el-tag size="small" effect="plain">{{ levelText }}</el-tag>
              <span class="hero-tip">以下数据仅统计你本人的密钥与权限申请</span>
            </div>
          </div>
        </div>
        <div class="hero-actions">
          <span v-if="updatedAt" class="hero-updated">更新于 {{ updatedAt }}</span>
          <el-button :icon="Refresh" :loading="loading" @click="loadAll">刷新</el-button>
        </div>
      </div>
    </el-card>

    <!--
      业务子系统入口 —— **本页的主元素**，放在所有统计之上。
      它是"接下来要做什么"的起点；下面的 KPI 与图表是"现在是什么状态"。
      顺序不能反：先选去处，再看现状。

      卡片不硬编码路径：按 menuId 从侧边栏路由里找（见 utils/subsystems.js）。
    -->
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

    <!-- 关键指标 -->
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

    <!-- 生成趋势 + 算法分布 -->
    <el-row :gutter="16">
      <el-col :xs="24" :lg="16">
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="section-head">
              <span>近 7 天密钥生成趋势</span>
              <span class="section-sub">{{ sampleText(generateKeys.length, generateTotal) }}</span>
            </div>
          </template>
          <div v-loading="isLoading('generate')" class="chart-wrap">
            <div ref="trendChartRef" class="chart-box chart-box-tall"></div>
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
              <span class="section-sub">按算法名称统计</span>
            </div>
          </template>
          <div v-loading="isLoading('generate')" class="chart-wrap">
            <div ref="algorithmChartRef" class="chart-box chart-box-tall"></div>
            <p v-if="chartNotice('generate', algorithmItems.length === 0)" class="chart-notice">
              {{ chartNotice('generate', algorithmItems.length === 0) }}
            </p>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 密钥状态 / 上链状态 / 分发状态 -->
    <el-row :gutter="16">
      <el-col :xs="24" :lg="8">
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="section-head">
              <span>密钥状态分布</span>
              <span class="section-sub">{{ sampleText(lifecycleKeys.length, lifecycleTotal) }}</span>
            </div>
          </template>
          <div v-loading="isLoading('lifecycle')" class="chart-wrap">
            <div ref="keyStatusChartRef" class="chart-box"></div>
            <p v-if="chartNotice('lifecycle', lifecycleKeys.length === 0, '暂无密钥记录')" class="chart-notice">
              {{ chartNotice('lifecycle', lifecycleKeys.length === 0, '暂无密钥记录') }}
            </p>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="8">
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="section-head">
              <span>上链状态分布</span>
              <span class="section-sub">取链上最新状态</span>
            </div>
          </template>
          <div v-loading="isLoading('generate')" class="chart-wrap">
            <div ref="chainChartRef" class="chart-box"></div>
            <p v-if="chartNotice('generate', chainItems.length === 0)" class="chart-notice">
              {{ chartNotice('generate', chainItems.length === 0) }}
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
          <div v-loading="isLoading('distribute')" class="chart-wrap">
            <div ref="distributeChartRef" class="chart-box"></div>
            <p v-if="chartNotice('distribute', distributeItems.length === 0)" class="chart-notice">
              {{ chartNotice('distribute', distributeItems.length === 0) }}
            </p>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 权限申请 -->
    <el-row :gutter="16">
      <el-col :span="24">
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="section-head">
              <span>权限申请</span>
              <span class="section-sub">临时授权的审批进度与当前可用能力</span>
            </div>
          </template>
          <div v-loading="isLoading('permission')" class="perm-layout">
            <div>
              <div v-for="item in permissionStatusItems" :key="item.code" class="perm-row">
                <span class="perm-label">{{ item.label }}</span>
                <span class="perm-track">
                  <span class="perm-fill" :class="item.className" :style="{ width: item.percent + '%' }"></span>
                </span>
                <span class="perm-count">{{ item.count }}</span>
              </div>
              <p v-if="permissionNotice" class="perm-notice">{{ permissionNotice }}</p>
            </div>

            <div class="feature-list">
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
import { ArrowRight, Bell, CircleCheck, Key, Refresh, Share } from '@element-plus/icons-vue'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TitleComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import useUserStore from '@/store/modules/user'
import { batchGetGenerateChainStatus, listGenerateKeys } from '@/services/generate-api'
import { listLifecycleKeys } from '@/services/lifecycle-api'
import { listDistributionBatches } from '@/services/user-distribution-api'
import { permissionFeatures } from '@/services/permission-api'
import { isAdminLevel, roleLevelText } from '@/utils/role'
import usePermissionStore from '@/store/modules/permission'
import { SUBSYSTEMS, findSubsystemRoute } from '@/utils/subsystems'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'

const router = useRouter()

/**
 * 注册 ECharts 组件。
 *
 * ⚠️ `TitleComponent` 必须在这里（2026-09-30 补）：饼图中心那个"总数"用的是
 *    `title`，而 ECharts 对**未注册的组件是静默忽略**的 —— 不报错、只是不画。
 *    所以此前中心数字**从来没出现过**（有数据时也没有，不只是空数据），
 *    而现象上看起来只像"这个图就是这个样子"，很难联想到是漏注册。
 */
echarts.use([LineChart, PieChart, BarChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent, CanvasRenderer])

/**
 * canvas 渲染器无法解析 CSS 变量，图表配色只能写字面量。
 * 下列取值与 design-tokens/tokens.scss 中的 --kms-* 一一对应，
 * 修改令牌时需同步本表，禁止在 echarts 配置里写 var(--kms-*)。
 * neutral / violet 无对应令牌，仅供图表分类区分使用。
 */
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
  surface: '#ffffff',
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
const ALGORITHM_ORDER = ['SM2', 'SSCL', 'Kyber', 'Falcon', 'CL-Kyber', 'CL-Falcon']

// 生命周期状态：0 有效 / 1 已冻结 / 2 已更新 / 3 已回收（文本状态为英文别名）
const KEY_STATUS_META = [
  { code: '0', label: '有效', color: CHART_COLORS.success },
  { code: '1', label: '已冻结', color: CHART_COLORS.warning },
  { code: '2', label: '已更新', color: CHART_COLORS.brand },
  { code: '3', label: '已回收', color: CHART_COLORS.neutral }
]

const KEY_STATUS_ALIAS = {
  Valid: '0',
  Active: '0',
  ACTIVE: '0',
  Frozen: '1',
  FROZEN: '1',
  Replaced: '2',
  Rotated: '2',
  ROTATED: '2',
  Revoked: '3',
  REVOKED: '3'
}

// 上链状态：0 待上链 / 1 已上链 / 2 上链失败
const CHAIN_STATUS_META = [
  { code: '1', label: '已上链', color: CHART_COLORS.success },
  { code: '0', label: '待上链', color: CHART_COLORS.warning },
  { code: '2', label: '上链失败', color: CHART_COLORS.danger }
]

// 分发状态：0 待分发 / 1 分发中 / 2 分发成功 / 3 分发失败
const DISTRIBUTE_STATUS_META = [
  { code: '2', label: '分发成功', color: CHART_COLORS.success },
  { code: '1', label: '分发中', color: CHART_COLORS.brand },
  { code: '0', label: '待分发', color: CHART_COLORS.warning },
  { code: '3', label: '分发失败', color: CHART_COLORS.danger }
]

// 权限申请状态：0 待审批 / 1 已通过 / 2 已拒绝 / 3 已回退
const PERMISSION_STATUS_META = [
  { code: '0', label: '待审批', className: 'is-pending' },
  { code: '1', label: '已通过', className: 'is-approved' },
  { code: '2', label: '已拒绝', className: 'is-rejected' },
  { code: '3', label: '已回退', className: 'is-rolled' }
]

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
  permission: STAT_LOADING
})

const generateKeys = ref([])
const generateTotal = ref(null)
const lifecycleKeys = ref([])
const lifecycleTotal = ref(null)
const distributeRecords = ref([])
const distributeTotal = ref(null)
const permissionRows = ref([])
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

/** 图标必须是组件（markRaw 避免被 Vue 做成响应式代理） */
const SUBSYSTEM_ICONS = { Key: markRaw(Key), Refresh: markRaw(Refresh), Share: markRaw(Share) }

/**
 * 三个业务子系统的入口卡片。
 *
 * ⚠️ 路径**不硬编码**：由后端 `sys_menu` 下发，这里按 `menuId` 从侧边栏路由里找。
 *    硬编码会在任何一次菜单重排后失效，而且**不报错** —— 只是卡片点不动。
 */
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
    title: '我的密钥',
    icon: markRaw(Key),
    value: displayCount('generate', generateTotal.value),
    hint: sourceHint('generate', `近 7 天新增 ${trend.value.total} 个`)
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
    title: '待审批申请',
    icon: markRaw(Bell),
    value: displayCount('permission', pendingPermissionCount.value),
    hint: sourceHint('permission', `累计申请 ${permissionRows.value.length} 条`)
  }
])

const trend = computed(() => {
  const days = buildRecentDays(TREND_DAYS)
  const counter = new Map(days.map((day) => [day.key, 0]))
  generateKeys.value.forEach((item) => {
    const key = toDateKey(item?.creTime)
    if (counter.has(key)) {
      counter.set(key, counter.get(key) + 1)
    }
  })
  const values = days.map((day) => counter.get(day.key))
  return {
    labels: days.map((day) => day.label),
    values,
    total: values.reduce((sum, value) => sum + value, 0)
  }
})

const algorithmItems = computed(() => {
  const counter = new Map()
  generateKeys.value.forEach((item) => {
    const name = String(item?.encrytName || '').trim() || '未标注'
    counter.set(name, (counter.get(name) || 0) + 1)
  })
  // ⚠️ 没有数据时也要给出**完整的分类骨架**（值为 0），而不是空数组
  //    （2026-09-30 改）。改前返回空 → 图表没东西可画 → 页面盖一句"暂无数据"，
  //    用户分不清"真的是 0"还是"没查到"。现在渲染出四个 0 条柱，
  //    "这类密钥一个都没有"这件事是看得见的。
  //
  //    只在**确实一条都没有**时才铺骨架：有任何数据时就按实际出现的分类走，
  //    免得凭空多出四条空柱噪音。
  if (!generateKeys.value.length) {
    return ALGORITHM_ORDER
      .filter((name) => !name.startsWith('CL-'))   // 退役算法不再出现在空骨架里
      .map((name, index) => ({
        name,
        value: 0,
        itemStyle: { color: CHART_PALETTE[index % CHART_PALETTE.length] }
      }))
  }
  const known = ALGORITHM_ORDER.filter((name) => counter.has(name))
  const rest = [...counter.keys()].filter((name) => !ALGORITHM_ORDER.includes(name)).sort()
  return [...known, ...rest].map((name, index) => ({
    name,
    value: counter.get(name),
    itemStyle: { color: CHART_PALETTE[index % CHART_PALETTE.length] }
  }))
})

const keyStatusItems = computed(() =>
  groupCount(lifecycleKeys.value, KEY_STATUS_META, (row) => {
    const raw = row?.status == null ? '' : String(row.status)
    return KEY_STATUS_ALIAS[raw] ?? raw
  })
)

const chainItems = computed(() =>
  groupCount(generateKeys.value, CHAIN_STATUS_META, (row) => (row?.chainStatus == null ? '' : String(row.chainStatus)))
)

const distributeItems = computed(() =>
  groupCount(distributeRecords.value, DISTRIBUTE_STATUS_META, (row) =>
    row?.distributeStatus == null ? '' : String(row.distributeStatus)
  )
)

const activeKeyCount = computed(() => countByStatus('0'))
const revokedKeyCount = computed(() => countByStatus('3'))
const distributeSucceeded = computed(
  () => distributeRecords.value.filter((row) => String(row?.distributeStatus) === '2').length
)
const pendingPermissionCount = computed(
  () => permissionRows.value.filter((row) => String(row?.status) === '0').length
)

const permissionStatusItems = computed(() => {
  const total = permissionRows.value.length
  return PERMISSION_STATUS_META.map((meta) => {
    const count = permissionRows.value.filter((row) => String(row?.status) === meta.code).length
    return {
      ...meta,
      count,
      percent: total ? Math.round((count / total) * 100) : 0
    }
  })
})

const permissionNotice = computed(() => {
  if (sourceState.permission === STAT_READY) {
    return permissionRows.value.length ? '' : '暂无权限申请记录'
  }
  return STATE_TEXT[sourceState.permission] || ''
})

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

/**
 * 图表上的提示文字。
 *
 * ⚠️ **只用于"加载中 / 取数失败"**，不再用于"没有数据"（2026-09-30 改）。
 *
 * 改前：数据为空时用一句"暂无数据"把整个图表**盖住**。用户看到的是一块空白，
 *       分不清"系统里真的是 0"还是"没查到 / 加载失败"。
 * 改后：数据为空**照常渲染图表**，各分类显示 0 ——
 *       "0 个已回收"与"页面坏了"是完全不同的两件事，界面必须能区分。
 *
 * `isEmpty` 参数保留但**不再用于生成文案**：调用处仍会传，是为了让签名稳定，
 * 免得日后有人加回"空就盖住"的行为时又要改一圈调用点。
 */
function chartNotice(source, isEmpty, emptyText = '') {
  const state = sourceState[source]
  if (state === STAT_READY) {
    // 就绪但为空 → 不给提示，让图表自己把 0 画出来。
    // emptyText 仍保留形参，但不渲染（见上方说明）。
    return ''
  }
  return STATE_TEXT[state] || ''
}

function countByStatus(code) {
  return lifecycleKeys.value.filter((row) => {
    const raw = row?.status == null ? '' : String(row.status)
    return (KEY_STATUS_ALIAS[raw] ?? raw) === code
  }).length
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

async function loadGenerate() {
  try {
    const data = await listGenerateKeys({
      pageNum: 1,
      pageSize: FETCH_PAGE_SIZE,
      userId: userStore.id || ''
    })
    const rows = Array.isArray(data?.rows) ? data.rows : []
    generateTotal.value = data?.total == null ? rows.length : Number(data.total)
    generateKeys.value = await mergeChainStatus(rows)
    sourceState.generate = STAT_READY
  } catch {
    generateKeys.value = []
    generateTotal.value = null
    sourceState.generate = STAT_ERROR
  }
}

/**
 * 生成记录里的 chain_status 可能是发起时的快照，
 * 这里用批量链上状态接口刷新一次；该接口失败时保留列表原值。
 */
async function mergeChainStatus(rows) {
  if (!rows.length) {
    return rows
  }
  try {
    const chainMap = await batchGetGenerateChainStatus(rows.map((item) => item.keyId))
    return rows.map((item) => {
      const latest = chainMap?.[item.keyId]
      if (!latest || typeof latest !== 'object') {
        return item
      }
      return {
        ...item,
        chainStatus: latest.chainStatus ?? item.chainStatus
      }
    })
  } catch {
    return rows
  }
}

async function loadLifecycle() {
  try {
    const data = await listLifecycleKeys({
      pageNum: 1,
      pageSize: FETCH_PAGE_SIZE,
      userId: userStore.id || ''
    })
    const rows = Array.isArray(data?.rows) ? data.rows : []
    lifecycleKeys.value = rows
    lifecycleTotal.value = data?.total == null ? rows.length : Number(data.total)
    sourceState.lifecycle = STAT_READY
  } catch {
    lifecycleKeys.value = []
    lifecycleTotal.value = null
    sourceState.lifecycle = STAT_ERROR
  }
}

/**
 * 分发状态分布：改读**新链路**的批次表（P5 第 1 步：先迁移消费方，再删旧表）。
 *
 * 旧来源是 `/distribute-api/distribute/record/list`（kms-distribute Java + `kms.key_distribute_record`），
 * 整条链路都在 P5 的删除清单里。**必须先迁移这里再删** —— 否则这张图立刻空掉，
 * 而计划 §3.6.5 把"5 张图表均有数据"列为硬性约束。
 *
 * ⚠️ 不是简单换个接口：新批次表的状态是**字符串**
 * （`success` / `partial` / `pending` / `failed`），而这张图的
 * `DISTRIBUTE_STATUS_META` 按**数字码**分组。直接换接口的话
 * `groupCount` 一个都匹配不上 —— 图会"成功渲染但永远为空"，
 * 这种失败比报错更难发现。所以在这一层做映射，图表代码不动。
 */
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

/**
 * 阶段 8：权限申请已整体下线，这里**不再调用**已删除的审批接口。
 *
 * 原实现会去拉 `listPermissionRequests('AUTO_UPDATE')`，失败时把
 * `sourceState.permission` 置成 STAT_ERROR —— 接口删掉之后，工作台
 * 每次打开都会挂一条错误提示，看起来像故障，实际是"这个功能没有了"。
 *
 * 新的判定口径：密钥自动更新不再需要申请。
 * 准入由**资源属主**决定（LifecycleKeyController 的 canAccess：
 * 属主或管理员），不再是"管理员或持有临时授权"。
 * 所以这里直接按属主为真的口径展示，不再有"待审批"这类状态。
 */
async function loadPermission() {
  permissionRows.value = []
  featureAccess.AUTO_UPDATE = true
  sourceState.permission = STAT_READY
}

// 阶段 8：hasApprovedTemporaryRequest 已随审批流一并移除
// （不再有"已批准的临时申请"这个概念可供判断）。

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
    // 四个数据源并行拉取，单个失败只影响对应卡片
    await Promise.allSettled([loadGenerate(), loadLifecycle(), loadDistribute(), loadPermission()])
    updatedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  } finally {
    loading.value = false
    await renderCharts()
  }
}

function buildTrendOption() {
  return {
    grid: { left: 4, right: 12, top: 16, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (value) => `${value} 个`
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
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
        smooth: true,
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

function buildPieOption(items) {
  // ⚠️ **不过滤 0 值**（2026-09-30 改）。
  //    改前是 `items.filter(v => v > 0)`：某一类为 0 时它连同图例一起消失，
  //    全为 0 时整张图什么都不画 —— 用户无从知道"是 0"还是"没数据"。
  //    现在全部分类都进图例、都显示计数（0 就是 0）。
  //
  //    副作用要知道：饼图**画不出 0 值的扇区**（角度为 0），所以全 0 时
  //    圆环是空的 —— 但图例、中心数字、tooltip 都还在，语义是清楚的。
  const data = items
  const total = data.reduce((sum, item) => sum + item.value, 0)
  // 图例带上**每类的计数**，这样"某类为 0"是看得见的。
  // 只列名字的话，用户只知道有这几类，不知道各有多少 —— 而"零也要看得见"
  // 恰恰要求把 0 写出来。
  const countByName = new Map(data.map((item) => [item.name, item.value]))
  return {
    tooltip: { trigger: 'item', formatter: '{b}：{c} 个（{d}%）' },
    color: data.map((item) => item.itemStyle?.color || CHART_COLORS.brand),
    legend: {
      bottom: 0,
      left: 'center',
      icon: 'circle',
      itemWidth: 8,
      itemHeight: 8,
      itemGap: 12,
      textStyle: { color: CHART_COLORS.textSecondary, fontSize: 12 },
      data: data.map((item) => item.name),
      // 例：已回收 0 · 有效 0 …（有数据时是「有效 12」这样）
      formatter: (name) => `${name} ${countByName.get(name) ?? 0}`
    },
    title: {
      // 中心数字始终显示（0 也显示 0）。需要 TitleComponent 已注册，见 echarts.use。
      text: String(total),
      subtext: '个',
      left: 'center',
      top: '30%',
      textStyle: { color: CHART_COLORS.textPrimary, fontSize: 22, fontWeight: 600 },
      subtextStyle: { color: CHART_COLORS.textSecondary, fontSize: 12 }
    },
    series: [
      {
        type: 'pie',
        radius: ['54%', '74%'],
        center: ['50%', '42%'],
        avoidLabelOverlap: true,
        label: { show: false },
        labelLine: { show: false },
        itemStyle: { borderColor: CHART_COLORS.surface, borderWidth: 2 },
        // ⚠️ 关掉 ECharts 的"空数据占位圆"（PieView 的 `showEmptyCircle`）。
        //    默认 true 时，数据全被过滤掉的饼图会画一个 **lightgray 整圆**
        //    —— 它长得跟"有数据的实心圆环"几乎一样，比"暂无数据"更容易误读：
        //    用户会以为"有一大块"，而实际是 0。
        showEmptyCircle: false,
        // ⚠️ **必须关掉 `stillShowZeroSum`**（默认 true，见 PieSeries.js:140）。
        //    它是"全 0 时仍然画出扇区"的意思，实现是 `pieLayout.js:156` 的
        //    `sum === 0 ? unitRadian : ...` —— 即**每个扇区均分整圆**。
        //    后果（2026-09-30 实测截图）：四个分类都是 0 时，圆环被画成
        //    四个等分扇形，看起来像"四类各占 25%"—— 比灰色空环更误导。
        //    关掉后全 0 不画扇区，只留中心 0 与图例的 0，语义才是对的。
        stillShowZeroSum: false,
        // ⚠️ **始终传完整 data，不要在空数据时传 []**（2026-09-30 实测踩到）：
        //    ECharts 的**图例项来自 series.data 的 name**。传 [] 就没有图例项，
        //    于是"图例列出各分类的 0"这条要求会静默失效 —— 中心有 0、图例全空。
        //    传完整 data（配合 stillShowZeroSum:false）时，0 值扇区角度为 0
        //    画不出来，但**图例项照样生成** —— 这正是"零也要看得见"要的效果。
        data
      }
    ]
  }
}

function buildKeyStatusOption() {
  const items = keyStatusItems.value
  return {
    grid: { left: 4, right: 12, top: 24, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      valueFormatter: (value) => `${value} 个`
    },
    xAxis: {
      type: 'category',
      data: items.map((item) => item.name),
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
        type: 'bar',
        barWidth: 28,
        data: items.map((item) => ({
          value: item.value,
          itemStyle: { color: item.itemStyle.color, borderRadius: [4, 4, 0, 0] }
        })),
        label: {
          show: true,
          position: 'top',
          color: CHART_COLORS.textSecondary,
          fontSize: 12,
          // ⚠️ 零值也要显示 "0"（2026-09-30 改）。
          //    改前是 `value ? String(value) : ''` —— 0 被当成"没有"而返回空串，
          //    于是全 0 时柱子上方什么都没有：用户看到一张空图，
          //    分不清"真的是 0"还是"没查到"。
          //    注意判据必须是 `value == null`（缺值）而不是 `!value`（0 也是假值），
          //    否则 0 又会被吃掉 —— 这正是改前那行的毛病。
          formatter: ({ value }) => (value == null ? '' : String(value))
        }
      }
    ]
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
  renderChart('algorithm', algorithmChartRef, buildPieOption(algorithmItems.value))
  renderChart('keyStatus', keyStatusChartRef, buildKeyStatusOption())
  renderChart('chain', chainChartRef, buildPieOption(chainItems.value))
  renderChart('distribute', distributeChartRef, buildPieOption(distributeItems.value))
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
  height: 240px;
}

.chart-box-tall {
  height: 260px;
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
  inset: 0;
  margin: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--kms-surface-1);
  color: var(--kms-text-tertiary);  font-size: var(--kms-font-size-sm);
}

.perm-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr);
  gap: var(--kms-space-6);
}

.perm-row {
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr) 56px;
  align-items: center;
  gap: var(--kms-space-3);
}

.perm-row + .perm-row {
  margin-top: var(--kms-space-3);
}

.perm-label {
  color: var(--kms-text-secondary);
  font-size: var(--kms-font-size-sm);
}

.perm-track {
  display: block;
  height: 8px;
  border-radius: var(--kms-radius-pill);
  background: var(--kms-surface-3);
  overflow: hidden;
}

.perm-fill {
  display: block;
  height: 100%;
  border-radius: var(--kms-radius-pill);
  background: var(--kms-border-strong);
  transition: width var(--kms-transition);
}

.perm-fill.is-pending {
  background: var(--kms-warning);
}

.perm-fill.is-approved {
  background: var(--kms-success);
}

.perm-fill.is-rejected {
  background: var(--kms-danger);
}

.perm-fill.is-rolled {
  background: var(--kms-text-tertiary);
}

.perm-count {
  text-align: right;
  color: var(--kms-text-primary);
  font-size: var(--kms-font-size-sm);
  font-variant-numeric: tabular-nums;
}

.perm-notice {
  margin: var(--kms-space-4) 0 0;
  color: var(--kms-text-tertiary);
  font-size: var(--kms-font-size-sm);
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
</style>
