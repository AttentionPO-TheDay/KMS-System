<template>
  <div class="app-container">
    <!-- 系统状态卡片 -->
    <el-row :gutter="20" class="status-cards">
      <el-col :span="6">
        <el-card class="status-card">
          <div class="status-item">
            <div class="status-icon nodes">
              <el-icon><Connection /></el-icon>
            </div>
            <div class="status-content">
              <div class="status-value">{{ systemStats.total_nodes }}</div>
              <div class="status-label">总节点数</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="status-card">
          <div class="status-item">
            <div class="status-icon active">
              <el-icon><CircleCheck /></el-icon>
            </div>
            <div class="status-content">
              <div class="status-value">{{ systemStats.active_nodes }}</div>
              <div class="status-label">活跃节点</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="status-card">
          <div class="status-item">
            <div class="status-icon sessions">
              <el-icon><Key /></el-icon>
            </div>
            <div class="status-content">
              <div class="status-value">{{ systemStats.total_sessions }}</div>
              <div class="status-label">会话密钥</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="status-card">
          <div class="status-item">
            <div class="status-icon messages">
              <el-icon><ChatDotRound /></el-icon>
            </div>
            <div class="status-content">
              <div class="status-value">{{ systemStats.total_messages }}</div>
              <div class="status-label">消息数量</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 区块链状态 -->
    <el-row :gutter="20" style="margin-top: 20px;">
      <el-col :span="12">
        <el-card class="box-card">
          <template #header>
            <div class="card-header">
              <span>🔗 区块链状态</span>
              <el-button type="text" @click="refreshBlockchainStatus">
                <el-icon><Refresh /></el-icon>
              </el-button>
            </div>
          </template>
          
          <el-descriptions :column="1" border>
            <el-descriptions-item label="连接状态">
              <el-tag :type="blockchainStatus.is_connected ? 'success' : 'danger'">
                {{ blockchainStatus.is_connected ? '已连接' : '未连接' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="网络ID">
              {{ blockchainStatus.network_id || '未知' }}
            </el-descriptions-item>
            <el-descriptions-item label="最新区块">
              {{ blockchainStatus.latest_block_number || 0 }}
            </el-descriptions-item>
            <el-descriptions-item label="合约地址">
              <el-text v-if="blockchainStatus.contract_address" class="address-text">
                {{ blockchainStatus.contract_address }}
              </el-text>
              <el-tag v-else type="warning">未部署</el-tag>
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
      
      <el-col :span="12">
        <el-card class="box-card">
          <template #header>
            <div class="card-header">
              <span>📊 系统统计</span>
              <el-button type="text" @click="refreshSystemStats">
                <el-icon><Refresh /></el-icon>
              </el-button>
            </div>
          </template>
          
          <el-descriptions :column="1" border>
            <el-descriptions-item label="总交易数">
              {{ systemStats.total_transactions }}
            </el-descriptions-item>
            <el-descriptions-item label="最新区块">
              {{ systemStats.latest_block }}
            </el-descriptions-item>
            <el-descriptions-item label="Kyber密钥上传">
              {{ blockchainStats.kyber_uploads || 0 }}
            </el-descriptions-item>
            <el-descriptions-item label="Falcon密钥上传">
              {{ blockchainStats.falcon_uploads || 0 }}
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
    </el-row>

    <!-- 最近活动 -->
    <el-row :gutter="20" style="margin-top: 20px;">
      <el-col :span="24">
        <el-card class="box-card">
          <template #header>
            <div class="card-header">
              <span>📝 最近活动</span>
              <el-button type="text" @click="refreshRecentActivity">
                <el-icon><Refresh /></el-icon>
              </el-button>
            </div>
          </template>
          
          <el-timeline>
            <el-timeline-item
              v-for="activity in recentActivities"
              :key="activity.id"
              :timestamp="activity.timestamp"
              :type="getActivityType(activity.action)"
            >
              <div class="activity-content">
                <div class="activity-title">{{ getActivityTitle(activity.action) }}</div>
                <div class="activity-details">
                  节点: {{ activity.node_name }} | 
                  状态: <el-tag :type="activity.success ? 'success' : 'danger'" size="small">
                    {{ activity.success ? '成功' : '失败' }}
                  </el-tag>
                </div>
                <div class="activity-description">{{ activity.details }}</div>
              </div>
            </el-timeline-item>
          </el-timeline>
          
          <div v-if="recentActivities.length === 0" class="empty-state">
            <el-empty description="暂无活动记录" />
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 快速操作 -->
    <el-row :gutter="20" style="margin-top: 20px;">
      <el-col :span="24">
        <el-card class="box-card">
          <template #header>
            <div class="card-header">
              <span>⚡ 快速操作</span>
            </div>
          </template>
          
          <el-row :gutter="20">
            <el-col :span="6">
              <el-button type="primary" size="large" style="width: 100%;" @click="goToNodes">
                <el-icon><Plus /></el-icon>
                注册新节点
              </el-button>
            </el-col>
            <el-col :span="6">
              <el-button type="success" size="large" style="width: 100%;" @click="goToBlockchain">
                <el-icon><Upload /></el-icon>
                部署合约
              </el-button>
            </el-col>
            <el-col :span="6">
              <el-button type="info" size="large" style="width: 100%;" @click="goToSessions">
                <el-icon><Key /></el-icon>
                创建会话
              </el-button>
            </el-col>
            <el-col :span="6">
              <el-button type="warning" size="large" style="width: 100%;" @click="goToLogs">
                <el-icon><Document /></el-icon>
                查看日志
              </el-button>
            </el-col>
          </el-row>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { 
  Connection, CircleCheck, Key, ChatDotRound, 
  Refresh, Plus, Upload, Document 
} from '@element-plus/icons-vue'
import { blockchainApi } from '@/api/pqkds/blockchain'
import { statsApi } from '@/api/pqkds/stats'
import { logsApi } from '@/api/pqkds/logs'

const router = useRouter()

// 响应式数据
const systemStats = ref({
  total_nodes: 0,
  active_nodes: 0,
  total_transactions: 0,
  total_sessions: 0,
  total_messages: 0,
  latest_block: 0
})

const blockchainStatus = ref({
  network_id: 0,
  latest_block_number: 0,
  latest_block_hash: '',
  contract_address: '',
  account_address: '',
  node_count: 0,
  is_connected: false
})

const blockchainStats = ref({
  kyber_uploads: 0,
  falcon_uploads: 0,
  session_exchanges: 0
})

const recentActivities = ref([])

// 方法
const refreshSystemStats = async () => {
  try {
    const response = await statsApi.getOverview()
    if (response.code === 2000) {
      systemStats.value = response.data
    }
  } catch (error) {
    console.error('Error fetching system stats:', error)
  }
}

const refreshBlockchainStatus = async () => {
  try {
    const response = await blockchainApi.getStatus()
    if (response.code === 2000) {
      blockchainStatus.value = response.data
    }
  } catch (error) {
    console.error('Error fetching blockchain status:', error)
  }
}

const refreshBlockchainStats = async () => {
  try {
    const response = await statsApi.getBlockchain()
    if (response.code === 2000) {
      blockchainStats.value = response.data
    }
  } catch (error) {
    console.error('Error fetching blockchain stats:', error)
  }
}

const refreshRecentActivity = async () => {
  try {
    const response = await logsApi.getList({ page: 1, size: 10 })
    if (response.code === 2000) {
      recentActivities.value = response.data.results || []
    }
  } catch (error) {
    console.error('Error fetching recent activities:', error)
  }
}

const getActivityType = (action) => {
  const typeMap = {
    'node_register': 'primary',
    'kyber_generate': 'success',
    'falcon_generate': 'success',
    'session_create': 'warning',
    'message_send': 'info'
  }
  return typeMap[action] || 'primary'
}

const getActivityTitle = (action) => {
  const titleMap = {
    'node_register': '节点注册',
    'kyber_generate': 'Kyber密钥生成',
    'falcon_generate': 'Falcon密钥生成',
    'session_create': '会话密钥创建',
    'message_send': '消息发送'
  }
  return titleMap[action] || action
}

// 导航方法
const goToNodes = () => {
  router.push('/nodes')
}

const goToBlockchain = () => {
  router.push('/blockchain')
}

const goToSessions = () => {
  router.push('/sessions')
}

const goToLogs = () => {
  router.push('/operation-logs')
}

// 生命周期
onMounted(() => {
  refreshSystemStats()
  refreshBlockchainStatus()
  refreshBlockchainStats()
  refreshRecentActivity()
})
</script>

<style scoped>
.status-cards {
  margin-bottom: 20px;
}

.status-card {
  height: 120px;
}

.status-item {
  display: flex;
  align-items: center;
  height: 100%;
}

.status-icon {
  width: 60px;
  height: 60px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 20px;
  font-size: 24px;
  color: white;
}

.status-icon.nodes {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.status-icon.active {
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
}

.status-icon.sessions {
  background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
}

.status-icon.messages {
  background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
}

.status-content {
  flex: 1;
}

.status-value {
  font-size: 32px;
  font-weight: bold;
  color: #303133;
  line-height: 1;
}

.status-label {
  font-size: 14px;
  color: #909399;
  margin-top: 8px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: bold;
}

.address-text {
  font-family: monospace;
  font-size: 12px;
  word-break: break-all;
}

.activity-content {
  padding: 10px 0;
}

.activity-title {
  font-weight: bold;
  margin-bottom: 5px;
}

.activity-details {
  font-size: 12px;
  color: #909399;
  margin-bottom: 5px;
}

.activity-description {
  font-size: 14px;
  color: #606266;
}

.empty-state {
  text-align: center;
  padding: 40px 0;
}
</style>
