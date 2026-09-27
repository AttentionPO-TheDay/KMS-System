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
import { Bell, CircleCheck, Key, Refresh, Share } from '@element-plus/icons-vue'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import useUserStore from '@/store/modules/user'
import { batchGetGenerateChainStatus, listGenerateKeys } from '@/services/generate-api'
import { listLifecycleKeys } from '@/services/lifecycle-api'
import { listDistributionBatches } from '@/services/user-distribution-api'
import { listPermissionRequests, permissionFeatures } from '@/services/permission-api'
import { isAdminLevel, roleLevelText } from '@/utils/role'

echarts.use([LineChart, PieChart, BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

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

function chartNotice(source, isEmpty, emptyText = '暂无数据') {
  const state = sourceState[source]
  if (state === STAT_READY) {
    return isEmpty ? emptyText : ''
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

async function loadPermission() {
  try {
    const autoUpdateData = await listPermissionRequests('AUTO_UPDATE', Number(userStore.id))
    permissionRows.value = autoUpdateData?.rows || []
    featureAccess.AUTO_UPDATE = hasApprovedTemporaryRequest(autoUpdateData?.rows)
    sourceState.permission = STAT_READY
  } catch {
    permissionRows.value = []
    featureAccess.AUTO_UPDATE = false
    sourceState.permission = STAT_ERROR
  }
}

function hasApprovedTemporaryRequest(rows = []) {
  return rows.some((item) => String(item?.status) === '1' && Number(item?.isTemp) === 1)
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
  const data = items.filter((item) => item.value > 0)
  const total = data.reduce((sum, item) => sum + item.value, 0)
  const hasData = data.length > 0 && total > 0
  return {
    tooltip: { trigger: 'item', formatter: '{b}：{c} 个（{d}%）' },
    color: data.map((item) => item.itemStyle?.color || CHART_COLORS.brand),
    legend: hasData
      ? {
          bottom: 0,
          left: 'center',
          icon: 'circle',
          itemWidth: 8,
          itemHeight: 8,
          itemGap: 12,
          textStyle: { color: CHART_COLORS.textSecondary, fontSize: 12 }
        }
      : { show: false },
    title: hasData
      ? {
          text: String(total),
          subtext: '个',
          left: 'center',
          top: '30%',
          textStyle: { color: CHART_COLORS.textPrimary, fontSize: 22, fontWeight: 600 },
          subtextStyle: { color: CHART_COLORS.textSecondary, fontSize: 12 }
        }
      : undefined,
    series: [
      {
        type: 'pie',
        radius: ['54%', '74%'],
        center: ['50%', '42%'],
        avoidLabelOverlap: true,
        label: { show: false },
        labelLine: { show: false },
        itemStyle: { borderColor: CHART_COLORS.surface, borderWidth: 2 },
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
          formatter: ({ value }) => (value ? String(value) : '')
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

.chart-notice {
  position: absolute;
  inset: 0;
  margin: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--kms-surface-1);
  color: var(--kms-text-tertiary);
  font-size: var(--kms-font-size-sm);
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
