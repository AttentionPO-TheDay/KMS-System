<template>
  <div class="app-container">
    <div class="filter-container">
      <el-card class="box-card">
        <template #header>
          <div class="card-header">
            <span>🔗 区块链管理</span>
          </div>
        </template>
        
        <!-- 区块链状态 -->
        <el-row :gutter="20" class="status-row">
          <el-col :span="6">
            <el-statistic title="网络ID" :value="blockchainStatus.network_id || 0" />
          </el-col>
          <el-col :span="6">
            <el-statistic title="最新区块" :value="blockchainStatus.latest_block_number || 0" />
          </el-col>
          <el-col :span="6">
            <el-statistic title="节点数量" :value="blockchainStatus.node_count || 0" />
          </el-col>
          <el-col :span="6">
            <el-tag :type="blockchainStatus.is_connected ? 'success' : 'danger'">
              {{ blockchainStatus.is_connected ? '已连接' : '未连接' }}
            </el-tag>
          </el-col>
        </el-row>

        <!-- 操作按钮 -->
        <el-row :gutter="20" class="button-row">
          <el-col :span="6">
            <el-button
              type="primary"
              icon="Plus"
              @click="showConfigDialog"
              size="large"
            >
              添加配置
            </el-button>
          </el-col>
          <el-col :span="6">
            <el-button
              type="primary"
              icon="Upload"
              @click="deployContract"
              :loading="deployLoading"
              size="large"
            >
              部署合约
            </el-button>
          </el-col>
          <el-col :span="6">
            <el-button
              type="success"
              icon="Refresh"
              @click="refreshStatus"
              :loading="statusLoading"
              size="large"
            >
              刷新状态
            </el-button>
          </el-col>
          <el-col :span="6">
            <el-button
              type="info"
              icon="List"
              @click="getBlockchainNodes"
              :loading="nodesLoading"
              size="large"
            >
              获取节点
            </el-button>
          </el-col>
        </el-row>
      </el-card>
    </div>

    <!-- 区块链详细信息 -->
    <el-card class="box-card" style="margin-top: 20px;">
      <template #header>
        <div class="card-header">
          <span>📊 区块链详细信息</span>
        </div>
      </template>
      
      <el-descriptions :column="2" border>
        <el-descriptions-item label="合约地址">
          <el-tag v-if="blockchainStatus.contract_address" type="success">
            {{ blockchainStatus.contract_address }}
          </el-tag>
          <el-tag v-else type="warning">未部署</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="账户地址">
          {{ blockchainStatus.account_address || '未配置' }}
        </el-descriptions-item>
        <el-descriptions-item label="最新区块哈希">
          <el-text class="hash-text">{{ blockchainStatus.latest_block_hash || '无' }}</el-text>
        </el-descriptions-item>
        <el-descriptions-item label="连接状态">
          <el-tag :type="blockchainStatus.is_connected ? 'success' : 'danger'">
            {{ blockchainStatus.is_connected ? '正常连接' : '连接失败' }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- 区块链节点列表 -->
    <el-card class="box-card" style="margin-top: 20px;" v-if="blockchainNodes.length > 0">
      <template #header>
        <div class="card-header">
          <span>🌐 区块链节点列表</span>
        </div>
      </template>
      
      <el-table :data="blockchainNodes" style="width: 100%">
        <el-table-column prop="node_id" label="节点ID" width="120" />
        <el-table-column prop="name" label="节点名称" width="150" />
        <el-table-column prop="ip_address" label="IP地址" width="120" />
        <el-table-column prop="port" label="端口" width="80" />
        <el-table-column label="Kyber公钥" width="120">
          <template #default="scope">
            <el-tag v-if="scope.row.kyber_public_key && scope.row.kyber_public_key.length > 0" type="success">
              已上传
            </el-tag>
            <el-tag v-else type="warning">未上传</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Falcon公钥" width="120">
          <template #default="scope">
            <el-tag v-if="scope.row.falcon_public_key_hash && scope.row.falcon_public_key_hash.length > 0" type="success">
              已上传
            </el-tag>
            <el-tag v-else type="warning">未上传</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="scope">
            <el-tag :type="scope.row.is_active ? 'success' : 'danger'">
              {{ scope.row.is_active ? '活跃' : '非活跃' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="注册时间" width="180">
          <template #default="scope">
            {{ formatTimestamp(scope.row.registration_time) }}
          </template>
        </el-table-column>
        <el-table-column label="最后更新" width="180">
          <template #default="scope">
            {{ formatTimestamp(scope.row.last_update_time) }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 配置对话框 -->
    <el-dialog v-model="configDialogVisible" title="添加区块链配置" width="50%">
      <el-form ref="configFormRef" :model="configForm" :rules="configRules" label-width="120px">
        <el-form-item label="配置名称" prop="name">
          <el-input v-model="configForm.name" placeholder="例如: Ganache Local" />
        </el-form-item>
        <el-form-item label="Provider URL" prop="provider_url">
          <el-input v-model="configForm.provider_url" placeholder="http://127.0.0.1:7545" />
        </el-form-item>
        <el-form-item label="账户地址" prop="account_address">
          <el-input v-model="configForm.account_address" placeholder="0x..." />
        </el-form-item>
        <el-form-item label="私钥" prop="private_key">
          <el-input v-model="configForm.private_key" type="password" placeholder="0x..." show-password />
        </el-form-item>
        <el-form-item label="网络ID" prop="network_id">
          <el-input-number v-model="configForm.network_id" :min="1" />
        </el-form-item>
        <el-form-item label="是否激活" prop="is_active">
          <el-switch v-model="configForm.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="configDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveConfig">保存</el-button>
      </template>
    </el-dialog>

    <!-- 合约部署结果对话框 -->
    <el-dialog v-model="deployDialogVisible" title="智能合约部署结果" width="600px">
      <div v-if="deployResult">
        <el-result 
          :icon="deployResult.success ? 'success' : 'error'"
          :title="deployResult.success ? '部署成功' : '部署失败'"
          :sub-title="deployResult.message || deployResult.error"
        >
          <template #extra v-if="deployResult.success">
            <el-descriptions :column="1" border>
              <el-descriptions-item label="合约地址">
                <el-tag type="success">{{ deployResult.contract_address }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="交易哈希">
                <el-text class="hash-text">{{ deployResult.tx_hash }}</el-text>
              </el-descriptions-item>
              <el-descriptions-item label="Gas消耗">
                {{ deployResult.gas_used }}
              </el-descriptions-item>
              <el-descriptions-item v-if="deployResult.note" label="备注">
                <el-tag type="info">{{ deployResult.note }}</el-tag>
              </el-descriptions-item>
            </el-descriptions>
          </template>
        </el-result>
      </div>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="deployDialogVisible = false">关闭</el-button>
          <el-button v-if="deployResult && deployResult.success" type="primary" @click="refreshStatus">
            刷新状态
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { blockchainApi } from '@/api/pqkds/blockchain'

// 响应式数据
const blockchainStatus = ref({
  network_id: 0,
  latest_block_number: 0,
  latest_block_hash: '',
  contract_address: '',
  account_address: '',
  node_count: 0,
  is_connected: false
})

const blockchainNodes = ref([])
const deployLoading = ref(false)
const statusLoading = ref(false)
const nodesLoading = ref(false)
const deployDialogVisible = ref(false)
const deployResult = ref(null)

// 配置表单
const configDialogVisible = ref(false)
const configFormRef = ref(null)
const configForm = ref({
  name: 'Ganache Local',
  provider_url: 'http://127.0.0.1:7545',
  account_address: '',
  private_key: '',
  network_id: 5777,
  is_active: true
})

const configRules = {
  name: [{ required: true, message: '请输入配置名称', trigger: 'blur' }],
  provider_url: [{ required: true, message: '请输入Provider URL', trigger: 'blur' }],
  account_address: [{ required: true, message: '请输入账户地址', trigger: 'blur' }],
  private_key: [{ required: true, message: '请输入私钥', trigger: 'blur' }],
  network_id: [{ required: true, message: '请输入网络ID', trigger: 'blur' }]
}

// 方法
const showConfigDialog = () => {
  configForm.value = {
    name: 'Ganache Local',
    provider_url: 'http://127.0.0.1:7545',
    account_address: '',
    private_key: '',
    network_id: 5777,
    is_active: true
  }
  configDialogVisible.value = true
}

const saveConfig = async () => {
  if (!configFormRef.value) return
  await configFormRef.value.validate(async (valid) => {
    if (valid) {
      try {
        const response = await blockchainApi.createConfig(configForm.value)
        if (response.code === 2000) {
          ElMessage.success('区块链配置添加成功')
          configDialogVisible.value = false
          await refreshStatus()
        } else {
          ElMessage.error(response.msg || '配置添加失败')
        }
      } catch (error) {
        ElMessage.error('配置添加失败')
        console.error('Error saving config:', error)
      }
    }
  })
}

const refreshStatus = async (silent = false) => {
  statusLoading.value = true
  try {
    const response = await blockchainApi.getStatus()
    if (response.code === 2000) {
      blockchainStatus.value = response.data
      if (!silent) ElMessage.success('区块链状态刷新成功')
    } else {
      if (!silent) ElMessage.warning(response.msg || '获取区块链状态失败，请确认 Ganache 已启动')
    }
  } catch (error) {
    if (!silent) ElMessage.warning('无法连接区块链，请确认 Ganache 已启动 (npx ganache)')
    console.error('Error fetching blockchain status:', error)
  } finally {
    statusLoading.value = false
  }
}

const deployContract = async () => {
  try {
    await ElMessageBox.confirm(
      '确定要部署FalconKDS智能合约吗？这将消耗一定的Gas费用。部署完成后会自动同步数据库中的节点信息到区块链。',
      '确认部署',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )

    deployLoading.value = true
    const response = await blockchainApi.deployContract()

    // 处理部署结果数据
    if (response.code === 2000) {
      deployResult.value = {
        success: true,
        message: response.msg,
        contract_address: response.data?.contract_address,
        tx_hash: response.data?.tx_hash,
        gas_used: response.data?.gas_used,
        note: response.data?.note
      }
      ElMessage.success('智能合约部署成功')

      // 部署成功后立即进行自动同步
      await performAutoSync()

    } else {
      deployResult.value = {
        success: false,
        error: response.msg || '智能合约部署失败'
      }
      ElMessage.error(response.msg || '智能合约部署失败')
    }

    deployDialogVisible.value = true
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('智能合约部署失败')
      console.error('Error deploying contract:', error)
    }
  } finally {
    deployLoading.value = false
  }
}

const performAutoSync = async () => {
  try {
    ElMessage.info('🔄 正在自动同步数据库节点信息到区块链...')
    console.log('🔄 开始自动同步：数据库 → 区块链')

    const response = await blockchainApi.syncDatabaseToBlockchain()

    if (response.code === 2000) {
      const result = response.data
      ElMessage.success(
        `✅ 同步完成！成功 ${result.synced_count || 0} 个，失败 ${result.failed_count || 0} 个`
      )
      console.log('✅ 自动同步完成！', result)

      // 同步完成后刷新节点列表
      if (result.synced_count > 0) {
        await new Promise(resolve => setTimeout(resolve, 1000))
        await getBlockchainNodes()
      }
    } else {
      ElMessage.warning(`⚠️ 同步过程中发生错误: ${response.msg}`)
      console.warn('⚠️ 同步失败:', response)
    }
  } catch (error) {
    console.error('❌ 自动同步失败:', error)
    ElMessage.error('自动同步失败，请手动刷新')
  }
}

const getBlockchainNodes = async () => {
  nodesLoading.value = true
  try {
    // 获取当前区块链下的节点
    const response = await blockchainApi.getNodesFromBlockchain()
    if (response.code === 2000) {
      // 后端已经只返回当前连接的区块链节点，无需额外过滤
      blockchainNodes.value = response.data || []
      ElMessage.success(`获取到 ${blockchainNodes.value.length} 个当前区块链节点`)
      console.log(`✅ 显示当前活跃区块链下的节点: ${blockchainNodes.value.length}个`)
    } else {
      ElMessage.error(response.msg || '获取区块链节点失败')
    }
  } catch (error) {
    ElMessage.error('获取区块链节点失败')
    console.error('Error fetching blockchain nodes:', error)
  } finally {
    nodesLoading.value = false
  }
}

const formatTimestamp = (timestamp) => {
  if (!timestamp) return '无'
  return new Date(timestamp * 1000).toLocaleString()
}

// 生命周期
onMounted(() => {
  refreshStatus(true)  // 静默加载，不弹提示
})
</script>

<style scoped>
.status-row {
  margin-bottom: 20px;
}

.button-row {
  margin-top: 20px;
}

.hash-text {
  font-family: monospace;
  font-size: 12px;
  word-break: break-all;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: bold;
}
</style>
