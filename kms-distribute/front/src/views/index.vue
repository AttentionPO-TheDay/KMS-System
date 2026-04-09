<template>
  <div class="dashboard-container">
    <div class="page-title">
      <h1>密钥分发系统仪表盘</h1>
      <p class="subtitle">实时监控密钥下发网络状态与数据</p>
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
            <div class="stat-trend" :class="stat.trend > 0 ? 'up' : 'down'">
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
          <div class="card-header">近7天密钥分发趋势</div>
          <div class="chart-container" ref="lineChartRef"></div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="glass-card">
          <div class="card-header">分发状态统计</div>
          <div class="chart-container" ref="pieChartRef"></div>
        </div>
      </el-col>
    </el-row>

    <!-- 底部区域 -->
    <el-row :gutter="20" class="action-section" style="margin-top: 20px;">
      <el-col :span="24">
        <div class="glass-card">
          <div class="card-header">快捷操作入口</div>
          <div class="action-grid">
            <div class="action-btn primary" @click="$router.push('/distribute/record')">
              <el-icon><List /></el-icon>
              <div class="btn-text">分发记录查询</div>
            </div>
            <div class="action-btn success">
              <el-icon><RefreshRight /></el-icon>
              <div class="btn-text">失败重试</div>
            </div>
            <div class="action-btn warning">
              <el-icon><DataAnalysis /></el-icon>
              <div class="btn-text">吞吐量监控</div>
            </div>
            <div class="action-btn info">
              <el-icon><Setting /></el-icon>
              <div class="btn-text">分发节点配置</div>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, markRaw } from 'vue'
import { Promotion, DataLine, Odometer, CircleCheck, Top, Bottom, List, RefreshRight, DataAnalysis, Setting } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { listKeyDistributeRecord } from '@/api/distribute/record'

const lineChartRef = ref(null)
const pieChartRef = ref(null)
let lineChart = null
let pieChart = null

const statsList = reactive([
  { title: '累计下发密钥', value: 0, trend: 15.2, icon: markRaw(Promotion), colorClass: 'blue' },
  { title: '今日分发总数', value: 342, trend: 12.3, icon: markRaw(DataLine), colorClass: 'green' },
  { title: '正在分发队列', value: 12, trend: -5.1, icon: markRaw(Odometer), colorClass: 'orange' },
  { title: '分发成功率', value: 99.8, trend: 0.1, icon: markRaw(CircleCheck), colorClass: 'purple', unit: '%' }
])

const initData = async () => {
  try {
    const res = await listKeyDistributeRecord()
    if (res && res.total !== undefined) {
      statsList[0].value = res.total
    }
  } catch (error) {
    console.error('获取统计数据失败', error)
  }
}

const initCharts = () => {
  const textColor = 'rgba(255, 255, 255, 0.7)'
  const splitLineColor = 'rgba(255, 255, 255, 0.1)'

  lineChart = echarts.init(lineChartRef.value)
  lineChart.setOption({
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(15,23,30,0.9)', borderColor: '#00e5ff', textStyle: { color: '#fff' } },
    legend: { data: ['成功分发', '失败重试'], textStyle: { color: textColor } },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { 
      type: 'category', 
      boundaryGap: false, 
      data: ['周一', '周二', '周三', '周四', '周五', '周六', '周日'],
      axisLabel: { color: textColor }
    },
    yAxis: { 
      type: 'value',
      axisLabel: { color: textColor },
      splitLine: { lineStyle: { color: splitLineColor } }
    },
    series: [
      {
        name: '成功分发', type: 'line', smooth: true,
        itemStyle: { color: '#00e5ff' },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(0,229,255,0.3)' },
            { offset: 1, color: 'rgba(0,229,255,0)' }
          ])
        },
        data: [150, 232, 201, 154, 190, 330, 210]
      },
      {
        name: '失败重试', type: 'line', smooth: true,
        itemStyle: { color: '#f56c6c' },
        data: [5, 12, 11, 4, 9, 3, 10]
      }
    ]
  })

  pieChart = echarts.init(pieChartRef.value)
  pieChart.setOption({
    tooltip: { trigger: 'item', backgroundColor: 'rgba(15,23,30,0.9)', borderColor: '#0099ff', textStyle: { color: '#fff' } },
    legend: { bottom: '0%', left: 'center', textStyle: { color: textColor } },
    series: [
      {
        name: '分发状态',
        type: 'pie',
        radius: ['45%', '70%'],
        avoidLabelOverlap: false,
        itemStyle: { borderRadius: 10, borderColor: 'rgba(0,0,0,0.5)', borderWidth: 2 },
        label: { show: false, position: 'center' },
        emphasis: { label: { show: true, fontSize: 20, fontWeight: 'bold' } },
        labelLine: { show: false },
        data: [
          { value: 890, name: '已分发', itemStyle: { color: '#00e5ff' } },
          { value: 92, name: '分发中', itemStyle: { color: '#0099ff' } },
          { value: 18, name: '响应超时', itemStyle: { color: '#e6a23c' } },
          { value: 3, name: '分发失败', itemStyle: { color: '#f56c6c' } }
        ]
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
  initCharts()
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
.stat-trend {
  display: flex;
  align-items: center;
  font-size: 13px;
  margin-top: 8px;
  gap: 4px;
}
.stat-trend.up { color: #67c23a; }
.stat-trend.down { color: #f56c6c; }

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
</style>
