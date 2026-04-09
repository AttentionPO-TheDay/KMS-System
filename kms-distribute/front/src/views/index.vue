<template>
  <div v-loading="loading" class="dashboard-container">
    <div class="page-title">
      <h1>抗量子密钥分发系统仪表盘</h1>
      <p class="subtitle">展示分发记录、链上回填结果与近 7 天事件趋势，全部来自当前真实分发数据链。</p>
    </div>

    <el-alert
      v-if="errorMessage"
      :title="errorMessage"
      type="error"
      show-icon
      :closable="false"
      class="error-alert"
    />

    <el-row :gutter="20" class="stat-cards">
      <el-col :span="6" v-for="stat in statsList" :key="stat.title">
        <div class="stat-card">
          <div class="stat-icon-wrapper" :class="stat.colorClass">
            <el-icon><component :is="stat.icon" /></el-icon>
            <div class="glow" :class="stat.colorClass"></div>
          </div>
          <div class="stat-content">
            <div class="stat-title">{{ stat.title }}</div>
            <div class="stat-value">
              <span class="num">{{ stat.value }}</span>
              <span v-if="stat.unit" class="unit">{{ stat.unit }}</span>
            </div>
            <div class="stat-desc">{{ stat.description }}</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="chart-section">
      <el-col :span="16">
        <div class="glass-card">
          <div class="card-header">近 7 天分发与链上回填趋势</div>
          <div ref="trendChartRef" class="chart-container"></div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="glass-card">
          <div class="card-header">近 7 天分发类型分布</div>
          <div ref="typeChartRef" class="chart-container"></div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="chart-section">
      <el-col :span="24">
        <div class="glass-card">
          <div class="card-header">近 7 天算法分布</div>
          <div ref="algorithmChartRef" class="chart-container algorithm-chart"></div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="table-section">
      <el-col :span="12">
        <div class="glass-card table-card">
          <div class="card-header">最近链上失败记录</div>
          <el-table :data="recentFailures" empty-text="暂无失败记录">
            <el-table-column label="记录ID" prop="recordId" width="90" />
            <el-table-column label="密钥名称" prop="keyName" min-width="140" show-overflow-tooltip />
            <el-table-column label="分发类型" width="110">
              <template #default="scope">{{ formatType(scope.row.distributeType) }}</template>
            </el-table-column>
            <el-table-column label="分发时间" prop="distributeTime" width="170" />
            <el-table-column label="失败原因" prop="remark" min-width="180" show-overflow-tooltip />
          </el-table>
        </div>
      </el-col>
      <el-col :span="12">
        <div class="glass-card table-card">
          <div class="card-header">最近链上回填记录</div>
          <el-table :data="recentChainResults" empty-text="暂无链上回填记录">
            <el-table-column label="记录ID" prop="recordId" width="90" />
            <el-table-column label="密钥名称" prop="keyName" min-width="140" show-overflow-tooltip />
            <el-table-column label="区块高度" prop="blockHeight" width="110" />
            <el-table-column label="分发时间" prop="distributeTime" width="170" />
            <el-table-column label="链上Hash" prop="chainHash" min-width="180" show-overflow-tooltip />
          </el-table>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="action-section">
      <el-col :span="24">
        <div class="glass-card">
          <div class="card-header">快捷操作入口</div>
          <div class="action-grid">
            <div class="action-btn primary" @click="router.push('/distribute/record')">
              <el-icon><List /></el-icon>
              <div class="btn-text">分发记录查询</div>
            </div>
            <div class="action-btn success" @click="router.push('/distribute/record')">
              <el-icon><CircleCheck /></el-icon>
              <div class="btn-text">链上结果追踪</div>
            </div>
            <div class="action-btn warning" @click="router.push('/distribute/record')">
              <el-icon><Warning /></el-icon>
              <div class="btn-text">查看失败记录</div>
            </div>
            <div class="action-btn info" @click="router.push('/distribute/record')">
              <el-icon><DataAnalysis /></el-icon>
              <div class="btn-text">全量分发分析</div>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, markRaw, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Promotion, DataLine, CircleCheck, Warning, List, DataAnalysis } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { getDashboardOverview } from '@/api/distribute/dashboard'

const router = useRouter()
const loading = ref(false)
const errorMessage = ref('')
const overview = ref({})
const trendChartRef = ref(null)
const typeChartRef = ref(null)
const algorithmChartRef = ref(null)

let trendChart = null
let typeChart = null
let algorithmChart = null

const summary = computed(() => overview.value.summary || {})
const recentFailures = computed(() => overview.value.recentFailures || [])
const recentChainResults = computed(() => overview.value.recentChainResults || [])

const trendData = computed(() => fillTrendPoints(overview.value.trend || []))
const typeDistribution = computed(() => overview.value.typeDistribution || [])
const algorithmDistribution = computed(() => overview.value.algorithmDistribution || [])

const completionRate = computed(() => {
  const total = trendData.value.reduce((sum, item) => sum + item.totalCount, 0)
  if (!total) {
    return 0
  }
  const completed = trendData.value.reduce((sum, item) => sum + item.chainCompletedCount, 0)
  return Number(((completed / total) * 100).toFixed(1))
})

const weeklyFailures = computed(() => trendData.value.reduce((sum, item) => sum + item.chainFailedCount, 0))

const statsList = computed(() => ([
  {
    title: '累计分发事件',
    value: summary.value.totalRecords || 0,
    description: '来自生成、更新、回收三类事件落表总量',
    icon: markRaw(Promotion),
    colorClass: 'blue'
  },
  {
    title: '今日新增分发',
    value: summary.value.todayRecords || 0,
    description: '按 distribute_time 统计今天新增记录',
    icon: markRaw(DataLine),
    colorClass: 'green'
  },
  {
    title: '近7日链上完成率',
    value: completionRate.value,
    unit: '%',
    description: '按链上回填 hash 或区块高度计算',
    icon: markRaw(CircleCheck),
    colorClass: 'purple'
  },
  {
    title: '近7日链上失败数',
    value: weeklyFailures.value,
    description: '按 remark 中的上链失败记录汇总',
    icon: markRaw(Warning),
    colorClass: 'orange'
  }
]))

async function loadOverview() {
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await getDashboardOverview()
    overview.value = response.data || {}
    await nextTick()
    initCharts()
  } catch (error) {
    errorMessage.value = error?.message || '仪表盘数据加载失败'
  } finally {
    loading.value = false
  }
}

function initCharts() {
  initTrendChart()
  initTypeChart()
  initAlgorithmChart()
}

function initTrendChart() {
  if (!trendChartRef.value) {
    return
  }
  if (!trendChart) {
    trendChart = echarts.init(trendChartRef.value)
  }

  const points = trendData.value
  trendChart.setOption({
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(15,23,30,0.92)', borderColor: '#00e5ff', textStyle: { color: '#fff' } },
    legend: { data: ['分发事件', '链上完成', '链上失败'], textStyle: { color: 'rgba(255,255,255,0.72)' } },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: {
      type: 'category',
      data: points.map((item) => item.label),
      axisLabel: { color: 'rgba(255,255,255,0.72)' },
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.16)' } }
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: 'rgba(255,255,255,0.72)' },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } }
    },
    series: [
      {
        name: '分发事件',
        type: 'line',
        smooth: true,
        itemStyle: { color: '#00e5ff' },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(0,229,255,0.28)' },
            { offset: 1, color: 'rgba(0,229,255,0)' }
          ])
        },
        data: points.map((item) => item.totalCount)
      },
      {
        name: '链上完成',
        type: 'line',
        smooth: true,
        itemStyle: { color: '#67c23a' },
        data: points.map((item) => item.chainCompletedCount)
      },
      {
        name: '链上失败',
        type: 'line',
        smooth: true,
        itemStyle: { color: '#f56c6c' },
        data: points.map((item) => item.chainFailedCount)
      }
    ]
  })
}

function initTypeChart() {
  if (!typeChartRef.value) {
    return
  }
  if (!typeChart) {
    typeChart = echarts.init(typeChartRef.value)
  }

  const data = typeDistribution.value.length
    ? typeDistribution.value.map((item, index) => ({
        value: item.value,
        name: item.label,
        itemStyle: { color: ['#00e5ff', '#0099ff', '#9c27b0', '#e6a23c'][index % 4] }
      }))
    : [{ value: 1, name: '暂无数据', itemStyle: { color: 'rgba(255,255,255,0.16)' } }]

  typeChart.setOption({
    tooltip: { trigger: 'item', backgroundColor: 'rgba(15,23,30,0.92)', borderColor: '#00e5ff', textStyle: { color: '#fff' } },
    legend: { bottom: '0%', left: 'center', textStyle: { color: 'rgba(255,255,255,0.72)' } },
    series: [{
      type: 'pie',
      radius: ['42%', '70%'],
      itemStyle: { borderRadius: 12, borderColor: 'rgba(0,0,0,0.4)', borderWidth: 2 },
      label: { color: '#fff', formatter: '{b}\n{d}%' },
      data
    }]
  })
}

function initAlgorithmChart() {
  if (!algorithmChartRef.value) {
    return
  }
  if (!algorithmChart) {
    algorithmChart = echarts.init(algorithmChartRef.value)
  }

  const data = algorithmDistribution.value
  algorithmChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, backgroundColor: 'rgba(15,23,30,0.92)', borderColor: '#00e5ff', textStyle: { color: '#fff' } },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: {
      type: 'category',
      data: data.map((item) => item.label),
      axisLabel: { color: 'rgba(255,255,255,0.72)', interval: 0, rotate: 18 },
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.16)' } }
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: 'rgba(255,255,255,0.72)' },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } }
    },
    series: [{
      name: '事件数',
      type: 'bar',
      barWidth: 32,
      itemStyle: {
        borderRadius: [8, 8, 0, 0],
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: '#00e5ff' },
          { offset: 1, color: '#0099ff' }
        ])
      },
      data: data.map((item) => item.value)
    }]
  })
}

function fillTrendPoints(points) {
  const pointMap = new Map((points || []).map((item) => [item.statDate, item]))
  const result = []
  for (let offset = 6; offset >= 0; offset -= 1) {
    const date = new Date()
    date.setDate(date.getDate() - offset)
    const statDate = formatDate(date)
    const source = pointMap.get(statDate) || {}
    result.push({
      statDate,
      label: `${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`,
      totalCount: Number(source.totalCount || 0),
      chainCompletedCount: Number(source.chainCompletedCount || 0),
      chainFailedCount: Number(source.chainFailedCount || 0)
    })
  }
  return result
}

function formatDate(date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function formatType(type) {
  return { '1': '生成分发', '2': '更新分发', '3': '回收后补发' }[String(type)] || '未知类型'
}

function resizeHandler() {
  if (trendChart) trendChart.resize()
  if (typeChart) typeChart.resize()
  if (algorithmChart) algorithmChart.resize()
}

onMounted(() => {
  loadOverview()
  window.addEventListener('resize', resizeHandler)
})

onUnmounted(() => {
  if (trendChart) trendChart.dispose()
  if (typeChart) typeChart.dispose()
  if (algorithmChart) algorithmChart.dispose()
  window.removeEventListener('resize', resizeHandler)
})
</script>

<style scoped>
.dashboard-container { padding: 24px; }

.error-alert { margin-bottom: 20px; }

.page-title { margin-bottom: 30px; }
.page-title h1 {
  font-size: 28px;
  color: #fff;
  margin: 0 0 8px 0;
  font-weight: 600;
  letter-spacing: 1px;
}
.page-title .subtitle {
  color: rgba(255, 255, 255, 0.5);
  margin: 0;
  font-size: 14px;
}

/* 统计卡片样式 */
.stat-card {
  background: rgba(255, 255, 255, 0.02);
  backdrop-filter: blur(24px);
  border: 1px solid rgba(255, 255, 255, 0.05);
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
  border-color: rgba(255, 255, 255, 0.1);
  box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.5);
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

.stat-icon-wrapper.blue { color: #0099ff; background: rgba(0, 153, 255, 0.1); }
.stat-icon-wrapper.blue .glow { background: #0099ff; }

.stat-icon-wrapper.green { color: #00e5ff; background: rgba(0, 229, 255, 0.1); }
.stat-icon-wrapper.green .glow { background: #00e5ff; }

.stat-icon-wrapper.orange { color: #e6a23c; background: rgba(230, 162, 60, 0.1); }
.stat-icon-wrapper.orange .glow { background: #e6a23c; }

.stat-icon-wrapper.purple { color: #9c27b0; background: rgba(156, 39, 176, 0.1); }
.stat-icon-wrapper.purple .glow { background: #9c27b0; }

.stat-content { flex: 1; }
.stat-title {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.6);
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
  color: #fff;
  font-family: 'Inter', sans-serif;
}
.stat-value .unit {
  font-size: 16px;
  color: rgba(255, 255, 255, 0.6);
}
.stat-desc {
  margin-top: 10px;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.54);
  line-height: 1.5;
}

/* 玻璃面板通用样式 */
.glass-card {
  background: rgba(255, 255, 255, 0.02);
  backdrop-filter: blur(24px);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  padding: 20px;
  height: 100%;
}
.card-header {
  font-size: 16px;
  font-weight: 600;
  color: #fff;
  margin-bottom: 20px;
  display: flex;
  align-items: center;
}
.card-header::before {
  content: '';
  display: inline-block;
  width: 4px;
  height: 16px;
  background: #00e5ff;
  border-radius: 2px;
  margin-right: 10px;
}

.chart-container {
  height: 320px;
  width: 100%;
}

.algorithm-chart {
  height: 280px;
}

.chart-section,
.table-section,
.action-section {
  margin-top: 20px;
}

.table-card :deep(.el-table),
.table-card :deep(.el-table__inner-wrapper::before) {
  background: transparent;
}

.table-card :deep(.el-table th.el-table__cell),
.table-card :deep(.el-table tr),
.table-card :deep(.el-table td.el-table__cell) {
  background: transparent;
  color: rgba(255, 255, 255, 0.82);
  border-bottom-color: rgba(255, 255, 255, 0.08);
}

.table-card :deep(.el-table th.el-table__cell) {
  color: rgba(255, 255, 255, 0.58);
}

.table-card :deep(.el-table__empty-text) {
  color: rgba(255, 255, 255, 0.5);
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
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.05);
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
  color: rgba(255, 255, 255, 0.8);
}
.action-btn:hover {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.1);
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
}
.action-btn:hover .el-icon {
  transform: scale(1.1);
}

.action-btn.primary:hover { border-color: rgba(0, 153, 255, 0.5); }
.action-btn.primary .el-icon { color: #0099ff; }

.action-btn.success:hover { border-color: rgba(0, 229, 255, 0.5); }
.action-btn.success .el-icon { color: #00e5ff; }

.action-btn.warning:hover { border-color: rgba(230, 162, 60, 0.5); }
.action-btn.warning .el-icon { color: #e6a23c; }

.action-btn.info:hover { border-color: rgba(156, 39, 176, 0.5); }
.action-btn.info .el-icon { color: #9c27b0; }

@media (max-width: 1200px) {
  .action-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .dashboard-container {
    padding: 16px;
  }

  .action-grid {
    grid-template-columns: 1fr;
  }
}
</style>
