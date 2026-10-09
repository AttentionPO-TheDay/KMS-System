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

    <!-- 生成趋势 + 算法分布 + 基础密钥状态 -->
    <el-row :gutter="16">
      <!-- ⚠️ 三列等宽（原为 16/8 两列）：新增的「基础密钥状态」与它们同级。
           趋势图从 2/3 宽缩到 1/3 宽，7 个点的折线仍然读得清；
           换来的是三张图对齐，不再有"一张特别宽"的突兀感。 -->
      <el-col :xs="24" :lg="8">
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
      <!--
        ⚠️ 这里**不再**新增一张「基础密钥状态」图。
           工作台有硬约束：**KPI 4 张 / 图表 5 张**（tools/verify-workbench-shape.mjs
           钉着，是用户明确要求保留的数字）。基础密钥的"状态"已经由下面
           「基础密钥」区块逐行列全（算法 / 状态 / keyId / 版本 / 指纹）——
           再补一张状态饼图是重复表达，而代价是破坏那个数字。
           要看历史版本的分布时，区块里那句「共 N 版」已经在回答。
      -->
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

    <!--
      基础密钥（原「权限申请」区块）。

      ⚠️ 这个位置原本是一整套「权限申请」进度条 —— 那是阶段 8 下线的审批流
         （`35_remove_permission_request_menu.sql`），接口早已删除，页面把
         `permissionRows` 硬编码成空数组，于是它**永远**显示"暂无权限申请记录"。
         一块永远空着的区块比没有更糟：用户会以为"我还没有申请资格"。

      换成**本节点自己那四套基础密钥**的明细 —— 那是节点一切能力的地基
      （生成/更新/分发都建立在它们之上），也回答了"初始化生成的密钥在哪"：
      它们登记在**分发模块**的 `NodeLongTermKey`（`/node-self/keys/`），
      而不是下面那几张图所用的 generate / lifecycle 两套记录。
    -->
    <el-row :gutter="16">
      <el-col :span="24">
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="section-head">
              <span>基础密钥</span>
              <span class="section-sub">
                节点首次初始化时在本机生成、公钥登记于此（私钥不出本机）
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
                  <!-- 有历史版本就说出来：只显示"当前那把"会让人以为旧版本不存在，
                       而"上一版已被取代"恰恰是密钥更新要看的 -->
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
import { ArrowRight, Bell, CircleCheck, Key, Refresh, Share } from '@element-plus/icons-vue'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TitleComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import useUserStore from '@/store/modules/user'
import { batchGetGenerateChainStatus, listGenerateKeys } from '@/services/generate-api'
import { listLifecycleKeys } from '@/services/lifecycle-api'
import { listDistributionBatches } from '@/services/user-distribution-api'
import { getSelfNode, listSelfNodeKeys } from '@/api/pqkds/node-self'
import { formatGenerationName } from '@/utils/crypto/generation-scheme.js'
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

const generateKeys = ref([])
const generateTotal = ref(null)
const lifecycleKeys = ref([])
const lifecycleTotal = ref(null)
const distributeRecords = ref([])
const distributeTotal = ref(null)
const nodeKeys = ref([])
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
    title: '基础密钥',
    icon: markRaw(Bell),
    value: displayCount('nodeKey', baseKeyReadyCount.value),
    hint: sourceHint(
      'nodeKey',
      baseKeyReadyCount.value === BASE_KEY_ALGOS.length
        ? `四套齐全：${baseKeys.value.map((a) => a.label).join(' / ')}`
        : `缺失：${baseKeys.value.filter((a) => !a.current)
          .map((a) => a.label).join('、') || '—'}`
    )
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

// ---------------------------------------------------------------------------
// 基础密钥（本节点那四套）
// ---------------------------------------------------------------------------
/** 四套基础密钥的固定顺序与展示名。与初始化页/「当前节点」页同一套口径。 */
const BASE_KEY_ALGOS = [
  { algo: 'KYBER', label: 'Kyber', role: '后量子密钥封装' },
  { algo: 'SSCL', label: 'SSCL', role: '保护 SM4 会话密钥' },
  { algo: 'SM2', label: 'SM2', role: '保护 SM4 会话密钥' },
  { algo: 'FALCON', label: 'Falcon', role: '签名与验签' }
]

/**
 * 每个算法当前那把 + 版本数。
 *
 * ⚠️ "当前"的判据用服务端下发的 `allowsNewWork`（只有 ACTIVE 为真），
 *    **不在前端按 status 字符串自己判** —— 那是 `api_contract` 的取值，
 *    前端另写一份必然漂移，而漂移的表现是"界面说能用、实际已被取代"。
 */
const baseKeys = computed(() =>
  BASE_KEY_ALGOS.map((def) => {
    const rows = nodeKeys.value.filter((k) => String(k?.algorithm || '').toUpperCase() === def.algo)
    const current = rows.find((k) => k?.allowsNewWork === true) || null
    return {
      ...def,
      label: formatGenerationName(def.algo, current?.generation),
      versions: rows.length,
      current
      // 没有 allowsNewWork 的行（全部已被取代/回收）时 current 为 null，
      // 页面显示「未登记」—— 这是如实的（当前确实没有可用的那一把）。
    }
  })
)

/** 四套里当前可用的套数。 */
const baseKeyReadyCount = computed(() => baseKeys.value.filter((item) => item.current).length)

const baseKeyNotice = computed(() => {
  if (sourceState.nodeKey === STAT_NA) {
    return '管理员账号不映射到节点，因此没有本机基础密钥。'
  }
  if (sourceState.nodeKey !== STAT_READY) {
    return STATE_TEXT[sourceState.nodeKey] || ''
  }
  return nodeKeys.value.length ? '' : '当前节点尚未登记基础密钥 —— 请到「节点首次初始化」完成四套密钥的生成。'
})

/**
 * 基础密钥行上状态标签的颜色。
 *
 * ⚠️ 按服务端下发的**状态文案**（`statusLabel`）判颜色，而不是按 status 码
 *    在前端再写一张表 —— 那张表必然与 `api_contract.KEY_STATUS_CHOICES` 漂移，
 *    而漂移的表现是"已回收的密钥显示成绿色"。文案本身就是后端契约的一部分
 *    （`KEY_STATUS_CHOICES`），这里只是给它上色。
 */
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
 * 「当前可用能力」那一列的数据来源。
 *
 * ⚠️ 它**不是**一个"拉数据"的函数，也不该再往 `sourceState` 里写东西：
 *    审批流阶段 8 已整体下线，"密钥自动更新是否需要申请"这个问题
 *    现在的答案是**恒不需要** —— 准入由资源属主决定（`LifecycleKeyController`
 *    的 `canAccess`：属主或管理员），不再有"管理员或持有临时授权"这种中间态。
 *
 *    它的前身会把 `sourceState.permission` 置成 READY，而那一格现在归
 *    **基础密钥**（`loadNodeKeys`）。两件事挤在同一格的状态机会互相覆盖 ——
 *    所以这里只写 `featureAccess`，不碰 `sourceState`。
 */
function loadPermission() {
  featureAccess.AUTO_UPDATE = true
}

// 阶段 8：hasApprovedTemporaryRequest 已随审批流一并移除
// （不再有"已批准的临时申请"这个概念可供判断）。

/**
 * 本节点的**基础密钥**（Kyber / SM2 / SSCL / Falcon）。
 *
 * ⚠️ 为什么单独一个数据源：这四套是**节点首次初始化**时生成、登记在
 *    分发模块的 `NodeLongTermKey`（`GET /node-self/keys/`）。而上面那几张图／卡
 *    用的是 **generate / lifecycle 两个子系统**的记录（`kms` 库）——
 *    两套是不同的事实来源。用户在"初始化完却看不到密钥"时踩的正是这个缝：
 *    数据一直在，只是工作台从来没问过它。
 *
 * ⚠️ 管理员账号不映射到节点（`mapped=false`）——那不是"加载失败"，是**不适用**，
 *    所以走 STAT_NA 而不是 STAT_ERROR（否则管理员打开工作台会看到一句红字）。
 */
async function loadNodeKeys() {
  try {
    const self = await getSelfNode()
    if (!self?.mapped) {
      nodeKeys.value = []
      sourceState.nodeKey = STAT_NA
      return
    }
    const data = await listSelfNodeKeys()
    nodeKeys.value = Array.isArray(data?.keys) ? data.keys : []
    sourceState.nodeKey = STAT_READY
  } catch {
    nodeKeys.value = []
    sourceState.nodeKey = STAT_ERROR
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
    await Promise.allSettled([
      loadGenerate(), loadLifecycle(), loadDistribute(), loadPermission(), loadNodeKeys()
    ])
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

/* 基础密钥区块：左列四套明细、右列当前可用能力。
   左列份额略大（原来的 1.15fr）—— 每行有 算法名 / 状态标签 / keyId / 指纹，
   比右侧那两行"名称 + 状态标签"宽。 */
.base-key-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr);
  gap: var(--kms-space-6);
}

.base-key-list {
  display: grid;
  align-content: start;
  gap: var(--kms-space-3);
}

.base-key-row {
  display: grid;
  grid-template-columns: 72px 88px minmax(0, 1fr) minmax(0, auto);
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
</style>
