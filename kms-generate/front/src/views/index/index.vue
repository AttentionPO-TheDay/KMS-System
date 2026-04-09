<template>
  <div class="dashboard-container">
    <div class="page-title">
      <h1>密钥生成系统仪表盘</h1>
      <p class="subtitle">实时监控生成记录、算法分布与上链状态</p>
    </div>

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
            </div>
            <div class="stat-note">{{ stat.note }}</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="chart-section" style="margin-top: 20px;">
      <el-col :span="16">
        <div class="glass-card">
          <div class="card-header">近7天密钥生成趋势</div>
          <div class="chart-container" ref="lineChartRef"></div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="glass-card">
          <div class="card-header">加密算法分布</div>
          <div class="chart-container" ref="pieChartRef"></div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="action-section" style="margin-top: 20px;">
      <el-col :span="12">
        <div class="glass-card">
          <div class="card-header">系统公告</div>
          <div class="notice-list">
            <div class="notice-item">
              <span class="notice-tag new">简介</span>
              <span class="notice-text">生成系统负责 SM2、SSCL 两类无证书算法的生成接入、记录落库与链上同步。</span>
            </div>
            <div class="notice-item">
              <span class="notice-tag">边界</span>
              <span class="notice-text">普通用户从统一用户端发起权限申请与查询，管理员在本系统完成审批与历史维护。</span>
            </div>
            <div class="notice-item">
              <span class="notice-tag">说明</span>
              <span class="notice-text">公共参数、生成历史和系统权限审批均已与当前真实业务数据联动展示。</span>
            </div>
          </div>
        </div>
      </el-col>
      <el-col :span="12">
        <div class="glass-card">
          <div class="card-header">快捷操作</div>
          <div class="action-grid">
            <div class="action-btn primary" @click="$router.push('/generate/keygenerate/index')">
              <el-icon><Lock /></el-icon>
              <div class="btn-text">生成信息</div>
            </div>
            <div class="action-btn success" @click="$router.push('/generate/history/index')">
              <el-icon><Calendar /></el-icon>
              <div class="btn-text">生成历史</div>
            </div>
            <div class="action-btn warning" @click="$router.push('/generate/commonparam/index')">
              <el-icon><Setting /></el-icon>
              <div class="btn-text">公共参数</div>
            </div>
            <div class="action-btn info" @click="$router.push('/permission/request/index')">
              <el-icon><Stamp /></el-icon>
              <div class="btn-text">系统权限审批</div>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, markRaw } from 'vue'
import { Key, User, TrendCharts, Link, Lock, Calendar, Setting, Stamp } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { getDashboardSummary } from '@/api/generate/keymanage'

const lineChartRef = ref(null)
const pieChartRef = ref(null)
let lineChart = null
let pieChart = null

const statsList = reactive([
  { title: '平台总密钥数', value: 0, note: '根据真实生成记录统计', icon: markRaw(Key), colorClass: 'blue' },
  { title: '系统用户总数', value: 0, note: '根据当前有效账号统计', icon: markRaw(User), colorClass: 'green' },
  { title: '今日生成密钥', value: 0, note: '今日新增生成记录', icon: markRaw(TrendCharts), colorClass: 'orange' },
  { title: '已同步上链数', value: 0, note: 'chainStatus = 1 的记录总数', icon: markRaw(Link), colorClass: 'purple' }
])

const chartState = reactive({
  labels: [],
  sm2: [],
  sscl: [],
  distribution: []
})

async function initData() {
  try {
    const summary = await getDashboardSummary()
    statsList[0].value = summary.totalKeys || 0
    statsList[0].note = `今日新增 ${summary.todayGenerated || 0} 条`
    statsList[1].value = summary.totalUsers || 0
    statsList[1].note = `今日新增 ${summary.todayUsers || 0} 个`
    statsList[2].value = summary.todayGenerated || 0
    statsList[2].note = '按创建时间统计今日生成量'
    statsList[3].value = summary.totalSynced || 0
    statsList[3].note = `今日上链 ${summary.todaySynced || 0} 条`

    chartState.labels = summary.recent7Days?.labels || []
    chartState.sm2 = summary.recent7Days?.sm2 || []
    chartState.sscl = summary.recent7Days?.sscl || []
    chartState.distribution = Object.entries(summary.algorithmDistribution || {}).map(([name, value], index) => ({
      name,
      value,
      itemStyle: { color: ['#0099ff', '#9c27b0', '#00e5ff', '#e6a23c'][index % 4] }
    }))

    initCharts()
  } catch (error) {
    console.error('获取仪表盘数据失败', error)
  }
}

function initCharts() {
  const textColor = 'rgba(255, 255, 255, 0.7)'
  const splitLineColor = 'rgba(255, 255, 255, 0.1)'

  if (!lineChart && lineChartRef.value) {
    lineChart = echarts.init(lineChartRef.value)
  }
  if (!pieChart && pieChartRef.value) {
    pieChart = echarts.init(pieChartRef.value)
  }

  lineChart?.setOption({
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(15,23,30,0.9)', borderColor: '#0099ff', textStyle: { color: '#fff' } },
    legend: { data: ['SM2生成量', 'SSCL生成量'], textStyle: { color: textColor } },
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
        name: 'SM2生成量', type: 'line', smooth: true,
        itemStyle: { color: '#0099ff' },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(0,153,255,0.3)' },
            { offset: 1, color: 'rgba(0,153,255,0)' }
          ])
        },
        data: chartState.sm2
      },
      {
        name: 'SSCL生成量', type: 'line', smooth: true,
        itemStyle: { color: '#00e5ff' },
        data: chartState.sscl
      }
    ]
  })

  pieChart?.setOption({
    tooltip: { trigger: 'item', backgroundColor: 'rgba(15,23,30,0.9)', borderColor: '#5e4d9a', textStyle: { color: '#fff' } },
    legend: { bottom: '0%', left: 'center', textStyle: { color: textColor } },
    series: [
      {
        name: '算法分布',
        type: 'pie',
        radius: ['40%', '70%'],
        avoidLabelOverlap: false,
        itemStyle: { borderRadius: 10, borderColor: 'rgba(0,0,0,0.5)', borderWidth: 2 },
        label: { show: false, position: 'center' },
        emphasis: { label: { show: true, fontSize: 20, fontWeight: 'bold' } },
        labelLine: { show: false },
        data: chartState.distribution
      }
    ]
  })
}

function resizeHandler() {
  lineChart?.resize()
  pieChart?.resize()
}

onMounted(() => {
  initData()
  window.addEventListener('resize', resizeHandler)
})

onUnmounted(() => {
  lineChart?.dispose()
  pieChart?.dispose()
  window.removeEventListener('resize', resizeHandler)
})
</script>

<style scoped>
.dashboard-container {
  padding: 24px;
}

.page-title {
  margin-bottom: 30px;
}

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

.stat-content {
  flex: 1;
}

.stat-title {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.6);
  margin-bottom: 8px;
}

.stat-value .num {
  font-size: 28px;
  font-weight: bold;
  color: #fff;
  font-family: 'Inter', sans-serif;
}

.stat-note {
  margin-top: 8px;
  color: rgba(255, 255, 255, 0.55);
  font-size: 13px;
}

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
  background: #0099ff;
  border-radius: 2px;
  margin-right: 10px;
}

.chart-container {
  height: 320px;
  width: 100%;
}

.notice-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.notice-item {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 8px;
  border-left: 2px solid transparent;
  transition: all 0.2s;
}

.notice-item:hover {
  background: rgba(255, 255, 255, 0.06);
  border-left-color: #0099ff;
}

.notice-tag {
  min-width: 44px;
  padding: 4px 8px;
  margin-right: 12px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.08);
  color: #d9ecff;
  text-align: center;
  font-size: 12px;
}

.notice-tag.new {
  background: rgba(0, 153, 255, 0.18);
  color: #8fd2ff;
}

.notice-text {
  flex: 1;
  color: rgba(255, 255, 255, 0.78);
  line-height: 1.6;
}

.action-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.action-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-height: 116px;
  border-radius: 12px;
  color: #fff;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.action-btn:hover {
  transform: translateY(-4px);
}

.action-btn.primary { background: linear-gradient(135deg, rgba(0, 153, 255, 0.24), rgba(0, 153, 255, 0.08)); }
.action-btn.success { background: linear-gradient(135deg, rgba(103, 194, 58, 0.24), rgba(103, 194, 58, 0.08)); }
.action-btn.warning { background: linear-gradient(135deg, rgba(230, 162, 60, 0.24), rgba(230, 162, 60, 0.08)); }
.action-btn.info { background: linear-gradient(135deg, rgba(144, 147, 153, 0.24), rgba(144, 147, 153, 0.08)); }

.action-btn .el-icon {
  font-size: 28px;
}

.btn-text {
  font-size: 14px;
}
</style>
