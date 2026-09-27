<template>
  <div class="dashboard-container">
    <div class="page-title">
      <h1>KMS 管理控制台</h1>
      <p class="subtitle">密钥生成、更新、回收与分发全流程运行概览</p>
    </div>

    <!-- 统计卡片区 -->
    <el-row :gutter="20" class="stat-cards">
      <el-col :span="6" v-for="(stat, index) in statsList" :key="index">
        <div class="stat-card">
          <div class="stat-icon-wrapper" :class="stat.colorClass">
            <el-icon><component :is="stat.icon" /></el-icon>
            <div class="glow" :class="stat.colorClass"></div>
          </div>
          <div class="stat-content">
            <div class="stat-title">{{ stat.title }}</div>
            <div class="stat-value">
              <span class="num">{{ stat.value }}</span>
              <span class="unit" v-if="stat.unit">{{ stat.unit }}</span>
            </div>
            <div class="stat-note">{{ stat.note }}</div>
            <div class="stat-trend" v-if="stat.trend !== null" :class="stat.trend > 0 ? 'up' : 'down'">
              <el-icon><Top v-if="stat.trend > 0"/><Bottom v-else/></el-icon>
              <span>{{ Math.abs(stat.trend) }}% 较昨日</span>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 图表区 -->
    <el-row :gutter="20" class="chart-section" style="margin-top: 20px;">
      <el-col :span="16">
        <div class="glass-card">
          <div class="card-header">近7天更新与回收活动趋势</div>
          <div class="chart-container" ref="lineChartRef"></div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="glass-card">
          <div class="card-header">操作类型分布</div>
          <div class="chart-container" ref="pieChartRef"></div>
        </div>
      </el-col>
    </el-row>

    <!-- 底部区域 -->
    <!--
      跳转路径一律写「路由内路径」，不要带 /updatedel 前缀。
      router 已用 createWebHistory(import.meta.env.BASE_URL) 把 /updatedel/ 作为 base，
      push 时会自动拼接；再手写前缀会变成 /updatedel/updatedel/xxx，
      命中 catch-all 落到 404 页。这些路径必须与 sys_menu 下发的 path 一致。
    -->
    <el-row :gutter="20" class="action-section" style="margin-top: 20px;">
      <el-col :span="24">
        <div class="glass-card">
          <div class="card-header">更新与回收管理操作</div>
          <div class="action-grid">
            <div class="action-btn primary" @click="$router.push('/key/keyupdate')">
              <el-icon><Refresh /></el-icon>
              <div class="btn-text">密钥更新</div>
            </div>
            <div class="action-btn success" @click="$router.push('/key/keyautoupdate')">
              <el-icon><Timer /></el-icon>
              <div class="btn-text">自动更新配置</div>
            </div>
            <div class="action-btn warning" @click="$router.push('/audit/permission/request')">
              <el-icon><Tickets /></el-icon>
              <div class="btn-text">系统权限审批</div>
            </div>
            <div class="action-btn danger" @click="$router.push('/key/keydelete')">
              <el-icon><Delete /></el-icon>
              <div class="btn-text">临时/永久回收</div>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, markRaw } from 'vue'
import { Refresh, Delete, Timer, Bell, Top, Bottom, Tickets } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { getDashboardSummary } from '@/api/lifecycle/lifecycle'

// ---------------------------------------------------------------------------
// ECharts 配色（必须使用字面量）
// ---------------------------------------------------------------------------
// ECharts 使用 canvas 渲染，无法解析 CSS 自定义属性（写 var(--kms-*) 会渲染为黑色），
// 因此图表配色在此显式声明，取值与 design-tokens/tokens.scss 保持一致，修改令牌时需同步。
// 注意：图表属非文字用途，故 brand 取 --kms-brand (#1677ff)，
//       而非承载白字的 --kms-brand-fill (#0e5fd8)。
// 此前本文件缺失该定义，导致看板初始化抛 ReferenceError: CHART_COLORS is not defined，
// 被 initData 的 catch 吞掉后仅打印「获取统计数据失败」，表现为所有图表空白。
const CHART_COLORS = {
  brand: '#1677ff',
  success: '#00b42a',
  warning: '#ff7d00',
  danger: '#f53f3f',
  neutral: '#8a919f',
  border: '#e5e7eb',
  borderSubtle: '#f0f2f5',
  surface: '#ffffff',
  surfaceOverlay: '#ffffff',
  textPrimary: '#1f2329',
  textSecondary: '#646a73'
}

const lineChartRef = ref(null)
const pieChartRef = ref(null)
let lineChart = null
let pieChart = null

const statsList = reactive([
  { title: '累计密钥更新', value: 0, note: '', trend: null, icon: markRaw(Refresh), colorClass: 'blue' },
  { title: '累计密钥回收', value: 0, note: '', trend: null, icon: markRaw(Delete), colorClass: 'orange' },
  { title: '自动更新已启用', value: 0, note: '', trend: null, icon: markRaw(Timer), colorClass: 'green' },
  { title: '用户待接收结果', value: 0, note: '', trend: null, icon: markRaw(Bell), colorClass: 'purple' }
])

const chartState = reactive({
  labels: [],
  manualUpdate: [],
  autoUpdate: [],
  revoke: [],
  distribution: []
})

const initData = async () => {
  try {
    const summary = await getDashboardSummary()
    statsList[0].value = summary.totalUpdates || 0
    statsList[0].note = `近 7 天共 ${((summary.recent7Days?.manualUpdate || []).reduce((a, b) => a + b, 0))} 次手动更新`
    statsList[1].value = summary.totalRevokes || 0
    statsList[1].note = `上链失败 ${summary.failedResults || 0} 条`
    statsList[2].value = summary.autoUpdateEnabled || 0
    statsList[2].note = '当前仍处于启用状态的密钥数'
    statsList[3].value = summary.pendingReceives || 0
    statsList[3].note = '用户端尚未确认接收的结果数'

    chartState.labels = summary.recent7Days?.labels || []
    chartState.manualUpdate = summary.recent7Days?.manualUpdate || []
    chartState.autoUpdate = summary.recent7Days?.autoUpdate || []
    chartState.revoke = summary.recent7Days?.revoke || []
    chartState.distribution = Object.entries(summary.operationDistribution || {}).map(([name, value], index) => ({
      name,
      value,
      itemStyle: { color: [CHART_COLORS.brand, CHART_COLORS.brand, CHART_COLORS.warning][index % 3] }
    }))

    initCharts()
  } catch (error) {
    console.error('获取统计数据失败', error)
  }
}

const initCharts = () => {
  const textColor = CHART_COLORS.textSecondary
  const splitLineColor = CHART_COLORS.border

  if (!lineChart && lineChartRef.value) {
    lineChart = echarts.init(lineChartRef.value)
  }
  lineChart.setOption({
    tooltip: { trigger: 'axis', backgroundColor: CHART_COLORS.surfaceOverlay, borderColor: CHART_COLORS.brand, textStyle: { color: CHART_COLORS.textPrimary } },
    legend: { data: ['手动更新', '自动更新', '密钥回收'], textStyle: { color: textColor } },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { 
      type: 'category', 
      boundaryGap: false, 
      data: chartState.labels,
      axisLabel: { color: textColor }
    },
    yAxis: { 
      type: 'value',
      axisLabel: { color: textColor },
      splitLine: { lineStyle: { color: splitLineColor } }
    },
    series: [
      {
        name: '手动更新', type: 'line', smooth: true,
        itemStyle: { color: CHART_COLORS.brand },
        data: chartState.manualUpdate
      },
      {
        name: '自动更新', type: 'line', smooth: true,
        itemStyle: { color: CHART_COLORS.brand },
        data: chartState.autoUpdate
      },
      {
        name: '密钥回收', type: 'line', smooth: true,
        itemStyle: { color: CHART_COLORS.warning },
        data: chartState.revoke
      }
    ]
  })

  if (!pieChart && pieChartRef.value) {
    pieChart = echarts.init(pieChartRef.value)
  }
  pieChart.setOption({
    tooltip: { trigger: 'item', backgroundColor: CHART_COLORS.surfaceOverlay, borderColor: CHART_COLORS.warning, textStyle: { color: CHART_COLORS.textPrimary } },
    legend: { bottom: '0%', left: 'center', textStyle: { color: textColor } },
    series: [
      {
        name: '操作类型',
        type: 'pie',
        radius: ['45%', '70%'],
        avoidLabelOverlap: false,
        itemStyle: { borderRadius: 10, borderColor: CHART_COLORS.border, borderWidth: 2 },
        label: { show: false, position: 'center' },
        emphasis: { label: { show: true, fontSize: 20, fontWeight: 'bold' } },
        labelLine: { show: false },
        data: chartState.distribution
      }
    ]
  })
}

const resizeHandler = () => {
  if (lineChart) lineChart.resize()
  if (pieChart) pieChart.resize()
}

onMounted(() => {
  initData()
  window.addEventListener('resize', resizeHandler)
})

onUnmounted(() => {
  if (lineChart) lineChart.dispose()
  if (pieChart) pieChart.dispose()
  window.removeEventListener('resize', resizeHandler)
})
</script>

<style scoped>
.dashboard-container { padding: 24px; }

.page-title { margin-bottom: 30px; }
.page-title h1 {
  font-size: 28px;
  color: var(--kms-text-primary);
  margin: 0 0 8px 0;
  font-weight: 600;
  letter-spacing: 1px;
}
.page-title .subtitle {
  color: var(--kms-text-secondary);
  margin: 0;
  font-size: 14px;
}

/* 统计卡片样式 */
.stat-card {
  background: var(--kms-surface-1);
  backdrop-filter: blur(24px);
  border: 1px solid var(--kms-border);
  border-radius: 12px;
  padding: 24px;
  display: flex;
  align-items: center;
  transition: all 0.3s ease;
  position: relative;
  overflow: hidden;
}
.stat-card:hover {
  transform: translateY(-5px);
  border-color: var(--kms-border);
  box-shadow: 0 10px 30px -10px var(--kms-border-strong);
}

.stat-icon-wrapper {
  width: 64px;
  height: 64px;
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 32px;
  margin-right: 20px;
  position: relative;
  z-index: 2;
}

.stat-icon-wrapper .glow {
  position: absolute;
  width: 100%;
  height: 100%;
  border-radius: 50%;
  filter: blur(20px);
  opacity: 0.5;
  z-index: -1;
}

.stat-icon-wrapper.blue { color: var(--kms-brand-text); background: var(--kms-brand-subtle); }
.stat-icon-wrapper.blue .glow { background: var(--kms-brand-fill); }

.stat-icon-wrapper.green { color: var(--kms-brand-text); background: var(--kms-brand-subtle); }
.stat-icon-wrapper.green .glow { background: var(--kms-brand-fill); }

.stat-icon-wrapper.orange { color: var(--kms-warning-strong); background: var(--kms-warning-subtle); }
.stat-icon-wrapper.orange .glow { background: var(--kms-warning); }

.stat-icon-wrapper.purple { color: var(--kms-brand-hover); background: var(--kms-brand-subtle); }
.stat-icon-wrapper.purple .glow { background: var(--kms-brand-hover); }

.stat-content { flex: 1; }
.stat-note {
  color: var(--kms-text-secondary);
  font-size: 12px;
  margin-top: 4px;
}
.stat-title {
  font-size: 14px;
  color: var(--kms-text-secondary);
  margin-bottom: 8px;
}
.stat-value {
  display: flex;
  align-items: baseline;
  gap: 4px;
}
.stat-value .num {
  font-size: 28px;
  font-weight: bold;
  color: var(--kms-text-primary);
  font-family: 'Inter', sans-serif;
}
.stat-value .unit {
  font-size: 16px;
  color: var(--kms-text-secondary);
}
.stat-trend {
  display: flex;
  align-items: center;
  font-size: 13px;
  margin-top: 8px;
  gap: 4px;
}
.stat-trend.up { color: var(--kms-success-strong); }
.stat-trend.down { color: var(--kms-danger-strong); }

/* 玻璃面板通用样式 */
.glass-card {
  background: var(--kms-surface-1);
  backdrop-filter: blur(24px);
  border: 1px solid var(--kms-border);
  border-radius: 12px;
  padding: 20px;
  height: 100%;
}
.card-header {
  font-size: 16px;
  font-weight: 600;
  color: var(--kms-text-primary);
  margin-bottom: 20px;
  display: flex;
  align-items: center;
}
.card-header::before {
  content: '';
  display: inline-block;
  width: 4px;
  height: 16px;
  background: var(--kms-warning);
  border-radius: 2px;
  margin-right: 10px;
}

.chart-container {
  height: 320px;
  width: 100%;
}

.action-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}
.action-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: var(--kms-surface-1);
  border: 1px solid var(--kms-border);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s;
}
.action-btn .el-icon {
  font-size: 32px;
  margin-bottom: 12px;
  transition: transform 0.3s;
}
.action-btn .btn-text {
  font-size: 14px;
  font-weight: 500;
  color: var(--kms-text-primary);
}
.action-btn:hover {
  background: var(--kms-surface-3);
  border-color: var(--kms-border);
  box-shadow: 0 4px 15px var(--kms-shadow);
}
.action-btn:hover .el-icon {
  transform: scale(1.1);
}

.action-btn.primary:hover { border-color: var(--kms-brand-border); }
.action-btn.primary .el-icon { color: var(--kms-brand-text); }

.action-btn.success:hover { border-color: var(--kms-brand-border); }
.action-btn.success .el-icon { color: var(--kms-brand-text); }

.action-btn.warning:hover { border-color: var(--kms-warning-border); }
.action-btn.warning .el-icon { color: var(--kms-warning-strong); }

.action-btn.danger:hover { border-color: var(--kms-danger-border); }
.action-btn.danger .el-icon { color: var(--kms-danger-strong); }
</style>
