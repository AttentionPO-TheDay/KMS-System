<template>
  <div class="app-container">
    <el-card shadow="never">
      <template #header>
        <div class="panel-head">
          <span>生成统计</span>
          <el-button size="small" :loading="loading" @click="load">刷 新</el-button>
        </div>
      </template>

      <!--
        §9.1 / §11.1 密钥生成监管 → 生成统计。

        ⚠️ 这里刻意**不合成一个"密钥总览"**，因为库里根本没有"生成的密钥"这张表。
        "生成密钥"这个动作在系统里的落点就是往 keymanage 表里插一行，
        因此：
          生成量  = keymanage 表里**还没有更新/回收记录**的那一部分
          更新量  = 生命周期仪表盘（/lifecycle/keymanage/dashboard/summary）里的累计更新
        两个数来自不同接口，口径不同，不能相加，也不能互相校验。
        本页把它们分列展示并标注口径，而不是给一个看起来很整齐的"总数"。
      -->

      <el-row :gutter="12" class="stat-row mb16">
        <el-col :span="6">
          <div class="stat">
            <div class="k">当前密钥总数</div>
            <div class="v">{{ keyTotal }}</div>
            <div class="n">keymanage 表当前记录数</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat">
            <div class="k">ACTIVE</div>
            <div class="v ok">{{ statusCount('ACTIVE') }}</div>
            <div class="n">可继续参与分发的密钥</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat">
            <div class="k">累计更新</div>
            <div class="v">{{ summary.totalUpdates ?? '-' }}</div>
            <div class="n">来自生命周期仪表盘</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat">
            <div class="k">累计回收</div>
            <div class="v warn">{{ summary.totalRevokes ?? '-' }}</div>
            <div class="n">来自生命周期仪表盘</div>
          </div>
        </el-col>
      </el-row>

      <el-row :gutter="20">
        <el-col :span="10">
          <div class="section-title">按算法分布</div>
          <el-table :data="byAlgorithm" border empty-text="暂无数据">
            <el-table-column label="算法" prop="label" min-width="170" />
            <el-table-column label="数量" width="100" align="center" prop="count" />
            <el-table-column label="占比" min-width="160">
              <template #default="{ row }">
                <el-progress :percentage="row.percent" :stroke-width="12" />
              </template>
            </el-table-column>
          </el-table>
        </el-col>
        <el-col :span="14">
          <div class="section-title">按状态分布</div>
          <el-table :data="byStatus" border empty-text="暂无数据">
            <el-table-column label="状态" width="140">
              <template #default="{ row }">
                <el-tag size="small" :type="statusTagType(row.status)">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="数量" width="100" align="center" prop="count" />
            <el-table-column label="占比" min-width="160">
              <template #default="{ row }">
                <el-progress :percentage="row.percent" :stroke-width="12" />
              </template>
            </el-table-column>
          </el-table>
        </el-col>
      </el-row>

      <div class="section-title" style="margin-top: 24px;">近 7 天更新与回收活动</div>
      <div class="chart-container" ref="chartRef"></div>
    </el-card>
  </div>
</template>

<script setup>
/**
 * §11.1 密钥生成监管 → 生成统计。
 *
 * 数据来源两个既有接口，本页不新增后端：
 *   GET /lifecycle/keymanage/list                → 密钥列表（算算法/状态分布）
 *   GET /lifecycle/keymanage/dashboard/summary   → 累计更新/回收与近 7 天趋势
 *
 * 生成系统那一侧另有 `/generate/key/dashboard/summary`，但它的数据源是
 * 生成系统的库，与本管理端的 keymanage 不是同一份。混用会得到
 * "同一件事两个数"，所以本页只用 lifecycle 这一套。
 */
import { computed, onMounted, onUnmounted, ref, markRaw } from 'vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import { getDashboardSummary, listKeymanage } from '@/api/lifecycle/lifecycle'

// ECharts 用 canvas 渲染，解析不了 CSS 变量（写 var(--kms-*) 会渲染成黑色），
// 配色必须用字面量，取值与 design-tokens/tokens.scss 保持一致。
const CHART_COLORS = {
  brand: '#1677ff',
  warning: '#ff7d00',
  border: '#e5e7eb',
  textSecondary: '#646a73',
  surfaceOverlay: '#ffffff',
  textPrimary: '#1f2329'
}

const STATUS_TAG = { ACTIVE: 'success', REVOKED: 'danger', EXPIRED: 'warning' }

const loading = ref(false)
const keys = ref([])
const summary = ref({})

const chartRef = ref(null)
const chart = markRaw({ instance: null })

const STATUS_LABELS = { ACTIVE: 'ACTIVE（有效）', REVOKED: 'REVOKED（已回收）' }

const keyTotal = computed(() => keys.value.length)

function statusCount(status) {
  return keys.value.filter((k) => String(k.status || '').toUpperCase() === status).length
}

const statusTagType = (status) => STATUS_TAG[String(status || '').toUpperCase()] || 'info'

function toRows(map, keyName, labelFn = (v) => v) {
  const entries = [...map.entries()].filter(([, v]) => v > 0)
  const total = entries.reduce((sum, [, v]) => sum + v, 0)
  if (!total) return []
  return entries
    .map(([k, v]) => ({ [keyName]: labelFn(k), count: v, percent: Math.round((v / total) * 100) }))
    .sort((a, b) => b.count - a.count)
}

const byAlgorithm = computed(() => {
  const map = new Map()
  keys.value.forEach((k) => {
    const label = k.encrytName || k.encrytType || '未知'
    map.set(label, (map.get(label) || 0) + 1)
  })
  return toRows(map, 'label')
})

const byStatus = computed(() => {
  const map = new Map()
  keys.value.forEach((k) => {
    const label = String(k.status || '').toUpperCase() || '未知'
    map.set(label, (map.get(label) || 0) + 1)
  })
  return toRows(map, 'status', (v) => STATUS_LABELS[v] || v)
})

function renderChart() {
  if (!chartRef.value) return
  if (!chart.instance) chart.instance = echarts.init(chartRef.value)

  const recent = summary.value.recent7Days || {}
  chart.instance.setOption({
    tooltip: {
      trigger: 'axis',
      backgroundColor: CHART_COLORS.surfaceOverlay,
      borderColor: CHART_COLORS.brand,
      textStyle: { color: CHART_COLORS.textPrimary }
    },
    legend: { data: ['手动更新', '自动更新', '密钥回收'], textStyle: { color: CHART_COLORS.textSecondary } },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: recent.labels || [],
      axisLabel: { color: CHART_COLORS.textSecondary }
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: CHART_COLORS.textSecondary },
      splitLine: { lineStyle: { color: CHART_COLORS.border } }
    },
    series: [
      { name: '手动更新', type: 'line', smooth: true, itemStyle: { color: CHART_COLORS.brand }, data: recent.manualUpdate || [] },
      { name: '自动更新', type: 'line', smooth: true, itemStyle: { color: CHART_COLORS.brand }, data: recent.autoUpdate || [] },
      { name: '密钥回收', type: 'line', smooth: true, itemStyle: { color: CHART_COLORS.warning }, data: recent.revoke || [] }
    ]
  })
}

async function load() {
  loading.value = true
  try {
    const [listRes, summaryRes] = await Promise.allSettled([
      listKeymanage({ pageNum: 1, pageSize: 1000 }),
      getDashboardSummary()
    ])

    keys.value = listRes.status === 'fulfilled'
      ? (Array.isArray(listRes.value?.rows) ? listRes.value.rows : [])
      : []
    summary.value = summaryRes.status === 'fulfilled' ? summaryRes.value || {} : {}

    if (listRes.status === 'rejected' && summaryRes.status === 'rejected') {
      ElMessage.error(listRes.reason?.message || '加载生成统计失败')
    }
    renderChart()
  } finally {
    loading.value = false
  }
}

const resizeHandler = () => chart.instance && chart.instance.resize()

onMounted(() => {
  load()
  window.addEventListener('resize', resizeHandler)
})

onUnmounted(() => {
  if (chart.instance) {
    chart.instance.dispose()
    chart.instance = null
  }
  window.removeEventListener('resize', resizeHandler)
})
</script>

<style scoped>
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.mb16 { margin-bottom: 16px; }
.section-title {
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 600;
  color: var(--kms-text-primary);
}
.stat-row .stat {
  border: 1px solid var(--kms-border);
  border-radius: 8px;
  padding: 12px 16px;
  background: var(--kms-surface-2, #fafafa);
}
.stat .k {
  font-size: 13px;
  color: var(--kms-text-secondary);
  margin-bottom: 6px;
}
.stat .v {
  font-size: 22px;
  font-weight: 600;
  color: var(--kms-text-primary);
}
.stat .v.ok { color: var(--kms-success-strong, #00b42a); }
.stat .v.warn { color: var(--kms-warning-strong, #ff7d00); }
.stat .n {
  margin-top: 6px;
  font-size: 12px;
  color: var(--kms-text-secondary);
}
.chart-container {
  height: 300px;
  width: 100%;
}
</style>
