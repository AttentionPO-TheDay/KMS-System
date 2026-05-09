<template>
  <div class="app-container">
    <!-- 页面标题 -->
    <div class="page-header">
      <h2>🔑 会话管理</h2>
      <p>管理节点间的会话密钥交换，监控会话状态</p>
      <!-- 当前区块链配置信息 -->
      <div v-if="currentBlockchainConfig" class="blockchain-info">
        <el-tag type="info" size="small">
          当前区块链: {{ currentBlockchainConfig.name }}
          ({{ currentBlockchainConfig.network_id ? `网络ID: ${currentBlockchainConfig.network_id}` : currentBlockchainConfig.provider_url }})
        </el-tag>
      </div>
    </div>

    <!-- 搜索和操作区域 -->
    <el-card class="search-card">
      <el-row :gutter="20">
        <el-col :span="16">
          <el-form :model="searchForm" inline>
            <el-form-item label="发起节点">
              <el-input v-model="searchForm.initiator_node" placeholder="请输入节点ID" clearable />
            </el-form-item>
            <el-form-item label="目标节点">
              <el-input v-model="searchForm.target_node" placeholder="请输入节点ID" clearable />
            </el-form-item>
            <el-form-item label="状态">
              <el-select v-model="searchForm.status" placeholder="请选择状态" clearable>
                <el-option label="已发起" value="initiated" />
                <el-option label="已建立" value="established" />
                <el-option label="已记录到区块链" value="blockchain_recorded" />
                <el-option label="已过期" value="expired" />
                <el-option label="已撤销" value="revoked" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="loadSessionList">
                <el-icon><Search /></el-icon>
                搜索
              </el-button>
              <el-button @click="resetSearch">
                <el-icon><Refresh /></el-icon>
                重置
              </el-button>
            </el-form-item>
          </el-form>
        </el-col>
        <el-col :span="8" style="text-align: right;">
          <el-button type="primary" @click="showInitiateDialog">
            <el-icon><Plus /></el-icon>
            发起会话
          </el-button>
          <el-button type="success" @click="loadSessionList">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </el-col>
      </el-row>
    </el-card>

    <!-- 会话列表 -->
    <el-card>
      <el-table :data="sessionList" v-loading="loading" style="width: 100%">
        <el-table-column prop="id" label="会话ID" width="80" />
        <el-table-column prop="initiator_node" label="发起节点" width="120" />
        <el-table-column prop="target_node" label="目标节点" width="120" />
        <el-table-column prop="session_type" label="会话类型" width="140">
          <template #default="scope">
            <el-tag :type="getSessionTypeColor(scope.row.session_type)" size="small">
              {{ getSessionTypeText(scope.row.session_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="scope">
            <el-tag :type="getStatusType(scope.row.status)" size="small">
              {{ getStatusText(scope.row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="密钥来源" width="120">
          <template #default="scope">
            <el-tag v-if="isFromPool(scope.row)" type="success" size="small">预分配池</el-tag>
            <el-tag v-else type="info" size="small">实时协商</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="160">
          <template #default="scope">
            {{ formatDateTime(scope.row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column prop="expires_at" label="过期时间" width="160">
          <template #default="scope">
            {{ formatDateTime(scope.row.expires_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="320">
          <template #default="scope">
            <el-button size="small" @click="viewDetails(scope.row)">详情</el-button>
            <el-button size="small" type="primary" @click="openChat(scope.row)">对话</el-button>
            <el-button 
              size="small" 
              type="danger" 
              @click="deleteSession(scope.row)"
              :disabled="scope.row.status === 'established'"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-container">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.size"
          :total="pagination.total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="loadSessionList"
          @current-change="loadSessionList"
        />
      </div>
    </el-card>

    <!-- 发起会话对话框 -->
    <el-dialog v-model="initiateDialogVisible" title="🔐 发起会话密钥分发" width="700px">
      <el-form :model="initiateForm" :rules="initiateRules" ref="initiateFormRef" label-width="120px">
        <el-form-item label="发起节点" prop="initiator_node">
          <el-select v-model="initiateForm.initiator_node" placeholder="请选择发起节点" style="width: 100%">
            <el-option
              v-for="node in availableNodes"
              :key="node.node_id"
              :value="node.node_id">
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <span>{{ node.name }} ({{ node.node_id }})</span>
                <el-tag size="small" type="success">Kyber-{{ node.kyber_security_level || '未知' }}</el-tag>
              </div>
            </el-option>
          </el-select>
        </el-form-item>

        <el-form-item label="目标节点" prop="target_node">
          <el-select v-model="initiateForm.target_node" placeholder="请选择目标节点" style="width: 100%">
            <el-option
              v-for="node in availableNodes"
              :key="node.node_id"
              :value="node.node_id">
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <span>{{ node.name }} ({{ node.node_id }})</span>
                <el-tag size="small" type="success">Kyber-{{ node.kyber_security_level || '未知' }}</el-tag>
              </div>
            </el-option>
          </el-select>
        </el-form-item>

        <el-form-item label="会话类型" prop="session_type">
          <el-radio-group v-model="initiateForm.session_type">
            <el-radio label="aes_falcon">
              Falcon加密AES实现密钥分发
            </el-radio>
            <el-radio label="kyber_kem">
              Kyber加密AES实现密钥分发
            </el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="密钥来源">
          <el-switch
            v-model="initiateForm.use_predistributed"
            active-text="从预分配密钥池取用"
            inactive-text="实时协商生成"
            :active-value="true"
            :inactive-value="false"
          />
          <div v-if="initiateForm.use_predistributed" style="margin-top: 6px;">
            <el-alert
              title="将从发起方节点的本地密钥池中取用已生成的密钥，速度更快。如果该方向的密钥池中无可用密钥则会失败。请先在「密钥预分配」页面为该方向生成密钥池。"
              type="info"
              :closable="false"
              show-icon
            />
          </div>
        </el-form-item>

        <!-- Kyber安全级别匹配提示 -->
        <el-form-item v-if="initiateForm.session_type === 'kyber_kem' && showKyberLevelWarning" label="">
          <el-alert
            :title="kyberLevelWarningMessage"
            type="warning"
            :closable="false"
            show-icon
          />
        </el-form-item>

        <el-form-item label="过期时间">
          <el-date-picker
            v-model="initiateForm.expires_at"
            type="datetime"
            placeholder="选择过期时间（可选）"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="initiateDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="initiateSession" :loading="initiateLoading">发起</el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 会话详情对话框 -->
    <el-dialog v-model="detailsDialogVisible" title="🔍 会话详情" width="900px">
      <div v-if="selectedSession">
        <!-- 基本信息 -->
        <el-descriptions :column="2" border>
          <el-descriptions-item label="会话ID">
            <el-tag type="primary">{{ selectedSession.id }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="会话类型">
            <el-tag :type="getSessionTypeColor(selectedSession.session_type)" size="small">
              {{ getSessionTypeText(selectedSession.session_type) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="getStatusType(selectedSession.status)">
              {{ getStatusText(selectedSession.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="密码学算法">
            <el-text type="info" size="small">
              {{ getAlgorithmInfo(selectedSession.session_type) }}
            </el-text>
          </el-descriptions-item>
          <el-descriptions-item label="发起节点">
            <el-text type="success">{{ selectedSession.initiator_node }}</el-text>
          </el-descriptions-item>
          <el-descriptions-item label="目标节点">
            <el-text type="warning">{{ selectedSession.target_node }}</el-text>
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatDateTime(selectedSession.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="过期时间">{{ formatDateTime(selectedSession.expires_at) }}</el-descriptions-item>
        </el-descriptions>

        <!-- 密钥信息 -->
        <el-divider content-position="left">
          <el-icon><Key /></el-icon>
          <span style="margin-left: 8px">密钥信息</span>
        </el-divider>

        <el-descriptions :column="1" border>
          <el-descriptions-item label="会话密钥">
            <div v-if="selectedSession.session_key" style="font-family: monospace; font-size: 12px; word-break: break-all;">
              {{ selectedSession.session_key.substring(0, 64) }}...
              <el-button size="small" text @click="copyToClipboard(selectedSession.session_key)">
                <el-icon><CopyDocument /></el-icon>
                复制
              </el-button>
            </div>
            <el-text v-else type="info">未生成</el-text>
          </el-descriptions-item>

          <el-descriptions-item label="Kyber密文">
            <div v-if="selectedSession.kyber_ciphertext" style="font-family: monospace; font-size: 12px; word-break: break-all;">
              {{ selectedSession.kyber_ciphertext.substring(0, 64) }}...
              <el-tag size="small" type="info" style="margin-left: 8px;">
                长度: {{ selectedSession.kyber_ciphertext.length }} bytes
              </el-tag>
            </div>
            <el-text v-else type="info">未生成</el-text>
          </el-descriptions-item>

          <el-descriptions-item label="Falcon签名" v-if="selectedSession.session_type === 'aes_falcon'">
            <div v-if="selectedSession.falcon_signature" style="font-family: monospace; font-size: 12px; word-break: break-all;">
              {{ selectedSession.falcon_signature.substring(0, 64) }}...
              <el-tag size="small" type="success" style="margin-left: 8px;">
                已验证
              </el-tag>
            </div>
            <el-text v-else type="info">未生成</el-text>
          </el-descriptions-item>
        </el-descriptions>

      </div>
    </el-dialog>

    <!-- 会话通信测试 - 微信风格聊天界面 -->
    <el-dialog
      v-model="chatDialogVisible"
      :title="`💬 ${currentChat?.initiator_node} ⇄ ${currentChat?.target_node}`"
      width="900px"
      :close-on-click-modal="false"
      class="chat-dialog"
    >
      <div class="wechat-chat-container">
        <!-- 聊天头部信息 -->
        <div class="chat-info-bar">
          <div class="chat-info-item">
            <span class="info-label">会话ID:</span>
            <span class="info-value">{{ currentChat?.id }}</span>
          </div>
          <div class="chat-info-item">
            <span class="info-label">当前发送方:</span>
            <el-select v-model="chatForm.sender" size="small" style="width: 150px;">
              <el-option :label="currentChat?.initiator_node" :value="currentChat?.initiator_node" />
              <el-option :label="currentChat?.target_node" :value="currentChat?.target_node" />
            </el-select>
          </div>
          <div class="chat-info-item">
            <el-tag type="success" size="small">端到端加密</el-tag>
          </div>
        </div>

        <!-- 消息显示区域 -->
        <div class="messages-area" ref="messagesArea">
          <div v-if="chatMessages.length === 0" class="empty-messages">
            <div class="empty-icon">💬</div>
            <div class="empty-text">暂无消息，开始聊天吧</div>
          </div>
          <div
            v-for="(msg, index) in chatMessages"
            :key="index"
            :class="['message-item', msg.sender === chatForm.sender ? 'sent' : 'received']"
          >
            <div class="message-avatar">
              {{ msg.sender.charAt(msg.sender.length - 1) }}
            </div>
            <div class="message-content">
              <div class="message-sender">{{ msg.sender }}</div>
              <div class="message-bubble">{{ msg.content }}</div>
              <div class="message-time">{{ msg.time }}</div>
            </div>
          </div>
        </div>

        <!-- 消息输入区域 -->
        <div class="input-area">
          <div class="input-wrapper">
            <el-input
              v-model="chatForm.content"
              type="textarea"
              :rows="3"
              placeholder="输入消息内容... (按 Ctrl+Enter 发送)"
              @keydown.ctrl.enter="sendChatMessage"
              class="message-input"
            />
            <el-button
              type="primary"
              @click="sendChatMessage"
              :loading="chatLoading"
              class="send-button"
            >
              发送
            </el-button>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Refresh, Plus } from '@element-plus/icons-vue'
import { sessionKeysApi } from '@/api/pqkds/sessionKeys'
import { nodesApi } from '@/api/pqkds/nodes'
import { blockchainApi } from '@/api/pqkds/blockchain'

// 响应式数据
const loading = ref(false)
const sessionList = ref([])
const availableNodes = ref([])
const initiateDialogVisible = ref(false)
const detailsDialogVisible = ref(false)
const initiateLoading = ref(false)
const selectedSession = ref(null)
const chatDialogVisible = ref(false)
const currentChat = ref<any>(null)
const chatForm = reactive({ sender: '', content: '' })
const chatLoading = ref(false)
const chatResult = ref('')
const currentBlockchainConfig = ref<any>(null)

const searchForm = reactive({
  initiator_node: '',
  target_node: '',
  status: ''
})

const pagination = reactive({
  page: 1,
  size: 20,
  total: 0
})

const initiateForm = reactive({
  initiator_node: '',
  target_node: '',
  session_type: 'aes_falcon',
  use_predistributed: true,  // 默认优先从预分配密钥池取用
  expires_at: null
})

const initiateFormRef = ref()

const initiateRules = {
  initiator_node: [{ required: true, message: '请选择发起节点', trigger: 'change' }],
  target_node: [{ required: true, message: '请选择目标节点', trigger: 'change' }],
  session_type: [{ required: true, message: '请选择会话类型', trigger: 'change' }]
}

// Kyber安全级别匹配检查
const showKyberLevelWarning = computed(() => {
  if (initiateForm.session_type !== 'kyber_kem') return false
  if (!initiateForm.initiator_node || !initiateForm.target_node) return false
  
  const initiatorNode = availableNodes.value.find(n => n.node_id === initiateForm.initiator_node)
  const targetNode = availableNodes.value.find(n => n.node_id === initiateForm.target_node)
  
  if (!initiatorNode || !targetNode) return false
  
  return initiatorNode.kyber_security_level !== targetNode.kyber_security_level
})

const kyberLevelWarningMessage = computed(() => {
  if (!showKyberLevelWarning.value) return ''
  
  const initiatorNode = availableNodes.value.find(n => n.node_id === initiateForm.initiator_node)
  const targetNode = availableNodes.value.find(n => n.node_id === initiateForm.target_node)
  
  if (!initiatorNode || !targetNode) return ''
  
  return `⚠️ Kyber安全级别不匹配：发起节点使用 Kyber-${initiatorNode.kyber_security_level}，目标节点使用 Kyber-${targetNode.kyber_security_level}。Kyber密钥分发要求双方使用相同的安全级别。`
})

// 方法
const loadSessionList = async () => {
  try {
    loading.value = true
    const params: any = {
      page: pagination.page,
      limit: pagination.size
    }
    // 仅在有值时才附加过滤参数，避免传空字段导致后端过滤
    if (searchForm.initiator_node) params.initiator_node = searchForm.initiator_node
    if (searchForm.target_node) params.target_node = searchForm.target_node
    if (searchForm.status) params.status = searchForm.status

    const response = await sessionKeysApi.getList(params)
    if (response.code === 2000) {
      let list = []
      let total = 0
      if (response.data && Array.isArray(response.data)) {
        list = response.data
        total = response.total || response.data.length
      } else if (response.data) {
        list = response.data.results || []
        total = response.data.count || 0
      }
      // 规范化字段，适配后端返回
      sessionList.value = list.map((it: any) => ({
        id: it.id,
        session_id: it.session_id || '',
        initiator_node: it.node1_name || it.node1 || it.node1_id || '',
        target_node: it.node2_name || it.node2 || it.node2_id || '',
        session_type: it.session_type || 'aes_falcon',
        status: it.status,
        key_exchange_data: it.key_exchange_data || '',
        created_at: it.create_datetime || it.created_at,
        expires_at: it.expires_at
      }))
      pagination.total = total
    }
  } catch (error) {
    ElMessage.error('获取会话列表失败')
  } finally {
    loading.value = false
  }
}

const loadAvailableNodes = async () => {
  try {
    const response = await nodesApi.getList()
    if (response.code === 2000) {
      availableNodes.value = response.data.results || response.data
    }
  } catch (error) {
    ElMessage.error('获取节点列表失败')
  }
}

const resetSearch = () => {
  Object.assign(searchForm, {
    initiator_node: '',
    target_node: '',
    status: ''
  })
  pagination.page = 1
  loadSessionList()
}

const showInitiateDialog = () => {
  Object.assign(initiateForm, {
    initiator_node: '',
    target_node: '',
    session_type: 'aes_falcon',
    use_predistributed: true,
    expires_at: null
  })
  initiateDialogVisible.value = true
}

const initiateSession = async () => {
  try {
    await initiateFormRef.value.validate()

    if (initiateForm.initiator_node === initiateForm.target_node) {
      ElMessage.error('发起节点和目标节点不能相同')
      return
    }

    initiateLoading.value = true
    const payload: any = {
      node1_id: initiateForm.initiator_node,
      node2_id: initiateForm.target_node,
      session_type: initiateForm.session_type
    }

    // 使用预分配密钥池（池中统一为 Kyber KEM 加密的 AES 密钥，会话类型由用户选择决定）
    if (initiateForm.use_predistributed) {
      payload.use_predistributed = true
    }

    // 如果用户选择了过期时间，则传递给后端
    if (initiateForm.expires_at) {
      payload.expires_at = new Date(initiateForm.expires_at).toISOString()
    }

    const response = await sessionKeysApi.initiate(payload)
    
    if (response.code === 2000) {
      ElMessage.success('会话发起成功')
      initiateDialogVisible.value = false
      loadSessionList()
    } else {
      // 显示详细的错误信息
      const errorMsg = response.msg || response.message || '会话发起失败'
      console.error('会话发起失败详情 - else块:', response)
      console.log('else块错误消息内容:', errorMsg)
      
      // 强制显示错误信息
      ElMessage({
        message: errorMsg,
        type: 'error',
        duration: 15000, // 延长显示时间到15秒
        dangerouslyUseHTMLString: false,
        showClose: true
      })
      
      // 同时使用alert确保用户能看到
      alert(`会话发起失败(else块): ${errorMsg}`)
    }
  } catch (error) {
    console.error('会话发起失败 - 完整错误对象:', error)
    console.error('错误对象类型:', typeof error)
    console.error('错误对象键:', Object.keys(error))
    
    // 提取详细的错误信息
    let errorMsg = '会话发起失败'
    
    // 尝试多种方式获取错误信息
    if (error && typeof error === 'object') {
      console.log('error.msg:', error.msg)
      console.log('error.message:', error.message)
      console.log('error.response:', error.response)
      console.log('error.data:', error.data)
      
      if (error.msg) {
        errorMsg = error.msg
        console.log('使用 error.msg:', errorMsg)
      } else if (error.message) {
        errorMsg = error.message
        console.log('使用 error.message:', errorMsg)
      } else if (error.response?.data?.msg) {
        errorMsg = error.response.data.msg
        console.log('使用 error.response.data.msg:', errorMsg)
      } else if (error.data?.msg) {
        errorMsg = error.data.msg
        console.log('使用 error.data.msg:', errorMsg)
      }
    }
    
    console.log('最终错误消息:', errorMsg)
    
    // 强制显示错误信息
    ElMessage({
      message: errorMsg,
      type: 'error',
      duration: 15000, // 延长显示时间到15秒
      dangerouslyUseHTMLString: false,
      showClose: true
    })
    
    // 同时使用alert确保用户能看到
    alert(`会话发起失败: ${errorMsg}`)
  } finally {
    initiateLoading.value = false
  }
}

const viewDetails = async (session) => {
  try {
    const response = await sessionKeysApi.getDetail(session.id)
    if (response.code === 2000) {
      const data: any = response.data || {}
      // 解析密钥交换数据，提取展示字段
      try {
        const pkg = data.key_exchange_data ? JSON.parse(data.key_exchange_data) : {}
        data.kyber_ciphertext = pkg.kyber_ciphertext || ''
        data.falcon_signature = pkg.falcon_signature || ''
      } catch (_) {}
      data.created_at = data.create_datetime || data.created_at
      data.initiator_node = data.node1_name || data.node1 || data.node1_id
      data.target_node = data.node2_name || data.node2 || data.node2_id
      selectedSession.value = data
      detailsDialogVisible.value = true
    }
  } catch (error) {
    ElMessage.error('获取会话详情失败')
  }
}

// 复制到剪贴板
const copyToClipboard = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch (error) {
    ElMessage.error('复制失败')
  }
}

// 聊天消息列表
const chatMessages = ref([])
const messagesArea = ref(null)

const openChat = async (session) => {
  currentChat.value = session
  chatForm.sender = session.initiator_node
  chatForm.content = ''
  chatResult.value = ''
  chatMessages.value = []
  chatDialogVisible.value = true

  // 加载历史消息
  await loadChatHistory(session.id)
}

const loadChatHistory = async (sessionId) => {
  try {
    const response = await sessionKeysApi.getMessages(sessionId)
    if (response.code === 2000 && response.data.messages) {
      // 将历史消息转换为聊天消息格式
      chatMessages.value = response.data.messages.map(msg => ({
        sender: msg.sender,
        content: msg.content,
        time: new Date(msg.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
        type: msg.sender === chatForm.sender ? 'sent' : 'received'
      }))

      // 滚动到底部
      setTimeout(() => {
        if (messagesArea.value) {
          messagesArea.value.scrollTop = messagesArea.value.scrollHeight
        }
      }, 100)
    }
  } catch (error) {
    console.error('加载历史消息失败:', error)
  }
}

const sendChatMessage = async () => {
  if (!currentChat.value || !chatForm.sender || !chatForm.content) {
    ElMessage.warning('请选择发送方并输入消息内容')
    return
  }

  const messageContent = chatForm.content.trim()
  if (!messageContent) return

  try {
    chatLoading.value = true

    // 发送消息
    const sendRes = await sessionKeysApi.sendMessage(currentChat.value.id, {
      sender_node_id: chatForm.sender,
      content: messageContent
    })

    if (sendRes.code !== 2000) {
      ElMessage.error(sendRes.msg || '发送失败')
      return
    }

    // 添加发送的消息到列表
    chatMessages.value.push({
      sender: chatForm.sender,
      content: messageContent,
      time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
      type: 'sent'
    })

    // 清空输入框
    chatForm.content = ''

    // 滚动到底部
    setTimeout(() => {
      if (messagesArea.value) {
        messagesArea.value.scrollTop = messagesArea.value.scrollHeight
      }
    }, 100)

    // 自动解密并显示接收方收到的消息
    const receiver = chatForm.sender === currentChat.value.initiator_node
      ? currentChat.value.target_node
      : currentChat.value.initiator_node

    const decryptRes = await sessionKeysApi.decryptMessage(currentChat.value.id, {
      message_id: sendRes.data.message_id,
      receiver_node_id: receiver
    })

    if (decryptRes.code === 2000) {
      // 添加接收方收到的消息
      chatMessages.value.push({
        sender: receiver,
        content: decryptRes.data.plaintext || messageContent,
        time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
        type: 'received'
      })

      // 再次滚动到底部
      setTimeout(() => {
        if (messagesArea.value) {
          messagesArea.value.scrollTop = messagesArea.value.scrollHeight
        }
      }, 100)
    }

  } catch (e) {
    console.error('发送失败:', e)
    ElMessage.error('发送失败')
  } finally {
    chatLoading.value = false
  }
}

const deleteSession = async (session) => {
  try {
    await ElMessageBox.confirm('确定要删除这个会话吗？', '确认删除', {
      type: 'warning'
    })
    
    const response = await sessionKeysApi.delete(session.id)
    if (response.code === 2000) {
      ElMessage.success('会话删除成功')
      loadSessionList()
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除会话失败')
    }
  }
}

const getStatusType = (status) => {
  const typeMap = {
    'initiated': 'warning',
    'established': 'success',
    'blockchain_recorded': 'primary',
    'expired': 'info',
    'revoked': 'danger',
    'failed': 'danger'
  }
  return typeMap[status] || 'info'
}

const getStatusText = (status) => {
  const textMap = {
    'initiated': '已发起',
    'established': '已建立',
    'blockchain_recorded': '已记录',
    'expired': '已过期',
    'revoked': '已撤销',
    'failed': '失败'
  }
  return textMap[status] || status
}

const getSessionTypeColor = (sessionType) => {
  const colorMap = {
    'aes_falcon': 'primary',
    'kyber_kem': 'success'
  }
  return colorMap[sessionType] || 'info'
}

const getSessionTypeText = (sessionType) => {
  const textMap = {
    'aes_falcon': 'Falcon加密AES实现密钥分发',
    'kyber_kem': 'Kyber加密AES实现密钥分发'
  }
  return textMap[sessionType] || sessionType
}

const getAlgorithmInfo = (sessionType) => {
  const infoMap = {
    'aes_falcon': 'Falcon加密 + AES-256-GCM',
    'kyber_kem': 'Kyber KEM + AES-256-GCM'
  }
  return infoMap[sessionType] || '未知算法'
}

const isFromPool = (row: any) => {
  if (row.session_id && row.session_id.startsWith('predist_')) return true
  try {
    const kd = typeof row.key_exchange_data === 'string' ? JSON.parse(row.key_exchange_data) : row.key_exchange_data
    return kd?.source === 'predistributed'
  } catch { return false }
}

const formatDateTime = (dateTime) => {
  if (!dateTime) return '-'
  return new Date(dateTime).toLocaleString('zh-CN')
}

// 获取当前活跃的区块链配置
const loadCurrentBlockchainConfig = async () => {
  try {
    const response = await blockchainApi.getActiveConfig()
    if (response.code === 2000) {
      currentBlockchainConfig.value = response.data
    } else {
      console.warn('获取当前区块链配置失败:', response.msg)
    }
  } catch (error) {
    console.error('获取当前区块链配置出错:', error)
  }
}

// 生命周期
onMounted(() => {
  loadCurrentBlockchainConfig()
  loadSessionList()
  loadAvailableNodes()
})
</script>

<style scoped>
.page-header {
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0 0 8px 0;
  color: #303133;
}

.page-header p {
  margin: 0;
  color: #909399;
  font-size: 14px;
}

.search-card {
  margin-bottom: 20px;
}

.pagination-container {
  margin-top: 20px;
  text-align: right;
}

.key-text {
  font-family: monospace;
  font-size: 12px;
  word-break: break-all;
  background: #f5f5f5;
  padding: 4px 8px;
  border-radius: 4px;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.blockchain-info {
  margin-top: 8px;
}

.blockchain-info .el-tag {
  font-size: 12px;
}

/* 微信风格聊天界面样式 */
.wechat-chat-container {
  display: flex;
  flex-direction: column;
  height: 600px;
  background: #f5f5f5;
}

.chat-info-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: #409eff;
  color: white;
  border-radius: 8px 8px 0 0;
}

.chat-info-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.info-label {
  font-size: 12px;
  opacity: 0.9;
}

.info-value {
  font-size: 13px;
  font-weight: 500;
}

.messages-area {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  background: #f9f9f9;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.empty-messages {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #999;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 12px;
  opacity: 0.3;
}

.empty-text {
  font-size: 14px;
}

.message-item {
  display: flex;
  gap: 10px;
  animation: slideIn 0.3s ease;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.message-item.sent {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: #409eff;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-weight: 600;
  font-size: 16px;
  flex-shrink: 0;
}

.message-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-width: 60%;
}

.message-item.sent .message-content {
  align-items: flex-end;
}

.message-sender {
  font-size: 12px;
  color: #999;
  padding: 0 4px;
}

.message-bubble {
  padding: 10px 14px;
  border-radius: 12px;
  word-wrap: break-word;
  font-size: 14px;
  line-height: 1.5;
}

.message-item.received .message-bubble {
  background: #fff;
  color: #333;
  border-bottom-left-radius: 4px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.1);
}

.message-item.sent .message-bubble {
  background: #409eff;
  color: white;
  border-bottom-right-radius: 4px;
}

.message-time {
  font-size: 11px;
  color: #999;
  padding: 0 4px;
}

.input-area {
  background: #fff;
  border-top: 1px solid #e0e0e0;
  padding: 12px 16px;
}

.input-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.input-wrapper {
  display: flex;
  gap: 12px;
  align-items: flex-end;
}

.message-input {
  flex: 1;
}

.message-input :deep(.el-textarea__inner) {
  border-radius: 8px;
  resize: none;
}

.send-button {
  height: 40px;
  border-radius: 8px;
}

.send-button:hover {
  opacity: 0.8;
}

</style>
