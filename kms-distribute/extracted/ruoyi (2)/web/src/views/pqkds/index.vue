<template>
  <div class="pqkds-container">
    <div class="system-header">
      <h1>后量子密钥分发系统 (PQKDS)</h1>
      <p>基于Falcon签名和Kyber加密的无证书密钥分发系统</p>
    </div>

    <!-- 系统状态面板 -->
    <el-card class="status-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <span>系统状态</span>
          <el-button type="primary" @click="refreshSystemStatus">刷新</el-button>
        </div>
      </template>

      <div v-if="systemStatus.initialized" class="status-grid">
        <div class="status-item">
          <div class="status-label">系统参数</div>
          <div class="status-value">{{ systemStatus.system_params?.name || 'N/A' }}</div>
        </div>
        <div class="status-item">
          <div class="status-label">总节点数</div>
          <div class="status-value">{{ systemStatus.total_nodes || 0 }}</div>
        </div>
        <div class="status-item">
          <div class="status-label">总交易数</div>
          <div class="status-value">{{ systemStatus.total_transactions || 0 }}</div>
        </div>
        <div class="status-item">
          <div class="status-label">总区块数</div>
          <div class="status-value">{{ systemStatus.total_blocks || 0 }}</div>
        </div>
      </div>

      <div v-else class="not-initialized">
        <el-alert
          title="系统未初始化"
          type="warning"
          description="请先初始化系统参数"
          show-icon
        />
        <el-button type="primary" @click="initializeSystem" style="margin-top: 10px;">
          初始化系统
        </el-button>
      </div>
    </el-card>

    <!-- 操作面板 -->
    <div class="operation-panels">
      <!-- 节点注册 -->
      <el-card class="operation-card" shadow="hover">
        <template #header>
          <span>节点注册</span>
        </template>

        <el-form :model="nodeForm" label-width="100px">
          <el-form-item label="节点ID">
            <el-input v-model="nodeForm.node_id" placeholder="输入节点ID" />
          </el-form-item>
          <el-form-item label="节点名称">
            <el-input v-model="nodeForm.name" placeholder="输入节点名称" />
          </el-form-item>
          <el-form-item label="IP地址">
            <el-input v-model="nodeForm.ip_address" placeholder="输入IP地址" />
          </el-form-item>
          <el-form-item label="端口">
            <el-input-number v-model="nodeForm.port" :min="1" :max="65535" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="registerNode" :loading="loading.register">
              注册节点
            </el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- KGC操作 -->
      <el-card class="operation-card" shadow="hover">
        <template #header>
          <span>KGC操作</span>
        </template>

        <el-form :model="kgcForm" label-width="100px">
          <el-form-item label="目标节点ID">
            <el-input v-model="kgcForm.node_id" placeholder="输入节点ID" />
          </el-form-item>
          <el-form-item>
            <el-button type="success" @click="generatePartialKey" :loading="loading.partialKey">
              生成部分私钥
            </el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- Falcon密钥生成 -->
      <el-card class="operation-card" shadow="hover">
        <template #header>
          <span>Falcon密钥生成</span>
        </template>

        <el-form :model="falconForm" label-width="120px">
          <el-form-item label="节点ID">
            <el-input v-model="falconForm.node_id" placeholder="输入节点ID" />
          </el-form-item>
          <el-form-item label="生成方案">
            <el-select v-model="falconForm.scheme" placeholder="选择Falcon密钥生成方案">
              <el-option
                label="V1 - 原始无证书方案"
                value="v1"
                :disabled="false"
              >
                <span>V1 - 原始无证书方案</span>
                <span style="float: right; color: #8492a6; font-size: 13px">基于椭圆曲线</span>
              </el-option>
              <el-option
                label="V2 - 基于陷门函数方案"
                value="v2"
                :disabled="false"
              >
                <span>V2 - 基于陷门函数方案</span>
                <span style="float: right; color: #8492a6; font-size: 13px">更高安全性</span>
              </el-option>
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button type="warning" @click="generateFalconKeypair" :loading="loading.falcon">
              生成Falcon密钥对
            </el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- 会话密钥交换 -->
      <el-card class="operation-card" shadow="hover">
        <template #header>
          <span>会话密钥交换</span>
        </template>

        <el-form :model="sessionForm" label-width="100px">
          <el-form-item label="发送节点ID">
            <el-input v-model="sessionForm.sender_node_id" placeholder="输入发送节点ID" />
          </el-form-item>
          <el-form-item label="目标节点ID">
            <el-input v-model="sessionForm.target_node_id" placeholder="输入目标节点ID" />
          </el-form-item>
          <el-form-item>
            <el-button type="danger" @click="initiateSessionKeyExchange" :loading="loading.session">
              发起会话密钥交换
            </el-button>
          </el-form-item>
        </el-form>
      </el-card>
    </div>

    <!-- 操作日志 -->
    <el-card class="log-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <span>操作日志</span>
          <el-button @click="clearLogs">清空日志</el-button>
        </div>
      </template>

      <div class="log-container">
        <div v-for="(log, index) in logs" :key="index" class="log-item" :class="log.type">
          <span class="log-time">{{ log.time }}</span>
          <span class="log-message">{{ log.message }}</span>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'

// 响应式数据
const systemStatus = ref({
  initialized: false,
  system_params: null,
  total_nodes: 0,
  total_transactions: 0,
  total_blocks: 0
})

const nodeForm = reactive({
  node_id: '',
  name: '',
  ip_address: '127.0.0.1',
  port: 8000
})

const kgcForm = reactive({
  node_id: ''
})

const falconForm = reactive({
  node_id: '',
  scheme: 'v1'  // 默认使用V1方案
})

const sessionForm = reactive({
  sender_node_id: '',
  target_node_id: ''
})

const loading = reactive({
  register: false,
  partialKey: false,
  falcon: false,
  session: false
})

const logs = ref<Array<{time: string, message: string, type: string}>>([])

// API基础URL
const API_BASE = '/api/pqkds'

// 工具函数
const addLog = (message: string, type: 'success' | 'error' | 'info' = 'info') => {
  logs.value.unshift({
    time: new Date().toLocaleTimeString(),
    message,
    type
  })
  if (logs.value.length > 50) {
    logs.value = logs.value.slice(0, 50)
  }
}

// API调用函数
const initializeSystem = async () => {
  try {
    const response = await axios.post(`${API_BASE}/system/initialize/`, {
      name: 'default'
    })

    if (response.data.success) {
      ElMessage.success('系统初始化成功')
      addLog('系统初始化成功', 'success')
      await refreshSystemStatus()
    } else {
      ElMessage.error(response.data.message)
      addLog(`系统初始化失败: ${response.data.message}`, 'error')
    }
  } catch (error: any) {
    ElMessage.error('系统初始化失败')
    addLog(`系统初始化失败: ${error.message}`, 'error')
  }
}

const refreshSystemStatus = async () => {
  try {
    const response = await axios.get(`${API_BASE}/system/status/`)

    if (response.data.success) {
      systemStatus.value = response.data.data
      addLog('系统状态刷新成功', 'info')
    } else {
      addLog(`获取系统状态失败: ${response.data.message}`, 'error')
    }
  } catch (error: any) {
    addLog(`获取系统状态失败: ${error.message}`, 'error')
  }
}

const registerNode = async () => {
  if (!nodeForm.node_id || !nodeForm.name) {
    ElMessage.warning('请填写完整的节点信息')
    return
  }

  loading.register = true
  try {
    const response = await axios.post(`${API_BASE}/node/register/`, nodeForm)

    if (response.data.success) {
      ElMessage.success('节点注册成功')
      addLog(`节点 ${nodeForm.node_id} 注册成功`, 'success')

      // 清空表单
      Object.assign(nodeForm, {
        node_id: '',
        name: '',
        ip_address: '127.0.0.1',
        port: 8000
      })

      await refreshSystemStatus()
    } else {
      ElMessage.error(response.data.message)
      addLog(`节点注册失败: ${response.data.message}`, 'error')
    }
  } catch (error: any) {
    ElMessage.error('节点注册失败')
    addLog(`节点注册失败: ${error.message}`, 'error')
  } finally {
    loading.register = false
  }
}

const generatePartialKey = async () => {
  if (!kgcForm.node_id) {
    ElMessage.warning('请输入节点ID')
    return
  }

  loading.partialKey = true
  try {
    const response = await axios.post(`${API_BASE}/kgc/generate-partial-key/`, {
      node_id: kgcForm.node_id
    })

    if (response.data.success) {
      ElMessage.success('部分私钥生成成功')
      addLog(`为节点 ${kgcForm.node_id} 生成部分私钥成功`, 'success')
      kgcForm.node_id = ''
      await refreshSystemStatus()
    } else {
      ElMessage.error(response.data.message)
      addLog(`部分私钥生成失败: ${response.data.message}`, 'error')
    }
  } catch (error: any) {
    ElMessage.error('部分私钥生成失败')
    addLog(`部分私钥生成失败: ${error.message}`, 'error')
  } finally {
    loading.partialKey = false
  }
}

const generateFalconKeypair = async () => {
  if (!falconForm.node_id) {
    ElMessage.warning('请输入节点ID')
    return
  }

  if (!falconForm.scheme) {
    ElMessage.warning('请选择Falcon密钥生成方案')
    return
  }

  loading.falcon = true
  try {
    const response = await axios.post(`${API_BASE}/node/generate-falcon-keypair/`, {
      node_id: falconForm.node_id,
      scheme: falconForm.scheme
    })

    if (response.data.success) {
      const schemeName = falconForm.scheme === 'v1' ? 'V1(原始方案)' : 'V2(陷门函数方案)'
      ElMessage.success(`Falcon密钥对生成成功 - ${schemeName}`)
      addLog(`节点 ${falconForm.node_id} 使用${schemeName}生成Falcon密钥对成功`, 'success')
      falconForm.node_id = ''
      await refreshSystemStatus()
    } else {
      ElMessage.error(response.data.message)
      addLog(`Falcon密钥对生成失败: ${response.data.message}`, 'error')
    }
  } catch (error: any) {
    ElMessage.error('Falcon密钥对生成失败')
    addLog(`Falcon密钥对生成失败: ${error.message}`, 'error')
  } finally {
    loading.falcon = false
  }
}

const initiateSessionKeyExchange = async () => {
  if (!sessionForm.sender_node_id || !sessionForm.target_node_id) {
    ElMessage.warning('请输入发送节点ID和目标节点ID')
    return
  }

  loading.session = true
  try {
    const response = await axios.post(`${API_BASE}/session/initiate/`, sessionForm)

    if (response.data.success) {
      ElMessage.success('会话密钥分发发起成功')
      addLog(`节点 ${sessionForm.sender_node_id} 向 ${sessionForm.target_node_id} 发起会话密钥分发成功`, 'success')

      Object.assign(sessionForm, {
        sender_node_id: '',
        target_node_id: ''
      })

      await refreshSystemStatus()
    } else {
      ElMessage.error(response.data.message)
      addLog(`会话密钥分发失败: ${response.data.message}`, 'error')
    }
  } catch (error: any) {
    ElMessage.error('会话密钥分发失败')
    addLog(`会话密钥分发失败: ${error.message}`, 'error')
  } finally {
    loading.session = false
  }
}

const clearLogs = () => {
  logs.value = []
  ElMessage.info('日志已清空')
}

// 生命周期
onMounted(() => {
  refreshSystemStatus()
  addLog('PQKDS系统界面加载完成', 'info')
})
</script>

<style scoped lang="scss">
.pqkds-container {
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
}

.system-header {
  text-align: center;
  margin-bottom: 30px;

  h1 {
    color: #409eff;
    margin-bottom: 10px;
    font-size: 2.5em;
  }

  p {
    color: #666;
    font-size: 1.1em;
  }
}

.status-card {
  margin-bottom: 30px;

  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .status-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 20px;

    .status-item {
      text-align: center;
      padding: 20px;
      background: #f8f9fa;
      border-radius: 8px;

      .status-label {
        font-size: 14px;
        color: #666;
        margin-bottom: 8px;
      }

      .status-value {
        font-size: 24px;
        font-weight: bold;
        color: #409eff;
      }
    }
  }

  .not-initialized {
    text-align: center;
    padding: 20px;
  }
}

.operation-panels {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
  gap: 20px;
  margin-bottom: 30px;

  .operation-card {
    .el-form {
      .el-form-item {
        margin-bottom: 18px;
      }
    }
  }
}

.log-card {
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .log-container {
    max-height: 400px;
    overflow-y: auto;

    .log-item {
      display: flex;
      padding: 8px 12px;
      border-bottom: 1px solid #eee;

      &.success {
        background-color: #f0f9ff;
        border-left: 4px solid #67c23a;
      }

      &.error {
        background-color: #fef0f0;
        border-left: 4px solid #f56c6c;
      }

      &.info {
        background-color: #f4f4f5;
        border-left: 4px solid #909399;
      }

      .log-time {
        min-width: 100px;
        color: #666;
        font-size: 12px;
        margin-right: 12px;
      }

      .log-message {
        flex: 1;
        font-size: 14px;
      }
    }
  }
}

// 响应式设计
@media (max-width: 768px) {
  .operation-panels {
    grid-template-columns: 1fr;
  }

  .status-grid {
    grid-template-columns: repeat(2, 1fr) !important;
  }
}

@media (max-width: 480px) {
  .pqkds-container {
    padding: 10px;
  }

  .system-header h1 {
    font-size: 1.8em;
  }

  .status-grid {
    grid-template-columns: 1fr !important;
  }
}
</style>