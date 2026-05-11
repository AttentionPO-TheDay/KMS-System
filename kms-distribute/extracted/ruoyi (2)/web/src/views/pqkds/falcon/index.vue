<template>
  <div class="falcon-kds-container">
    <el-card class="box-card">
      <template #header>
        <div class="card-header">
          <span>Falcon无证书密钥分发系统</span>
          <el-button type="text" @click="refreshStatus">刷新状态</el-button>
        </div>
      </template>
      
      <!-- 系统状态 -->
      <el-row :gutter="20" class="mb-4">
        <el-col :span="8">
          <el-card shadow="hover">
            <template #header>
              <i class="iconfont icon-cpu"></i> 系统状态
            </template>
            <div class="status-item">
              <span>系统初始化:</span>
              <el-tag :type="systemStatus.initialized ? 'success' : 'danger'">
                {{ systemStatus.initialized ? '已初始化' : '未初始化' }}
              </el-tag>
            </div>
            <div class="status-item">
              <span>区块链连接:</span>
              <el-tag :type="blockchainStatus.connected ? 'success' : 'danger'">
                {{ blockchainStatus.connected ? '已连接' : '未连接' }}
              </el-tag>
            </div>
          </el-card>
        </el-col>
        
        <el-col :span="8">
          <el-card shadow="hover">
            <template #header>
              <i class="iconfont icon-link"></i> 区块链信息
            </template>
            <div class="status-item" v-if="blockchainStatus.connected">
              <span>最新区块:</span>
              <span>{{ blockchainStatus.latest_block || 'N/A' }}</span>
            </div>
            <div class="status-item" v-if="blockchainStatus.connected">
              <span>账户地址:</span>
              <span class="address">{{ blockchainStatus.account || 'N/A' }}</span>
            </div>
          </el-card>
        </el-col>
        
        <el-col :span="8">
          <el-card shadow="hover">
            <template #header>
              <i class="iconfont icon-key"></i> 密钥统计
            </template>
            <div class="status-item">
              <span>节点总数:</span>
              <span>{{ nodeStats.total || 0 }}</span>
            </div>
            <div class="status-item">
              <span>活跃节点:</span>
              <span>{{ nodeStats.active || 0 }}</span>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <!-- 操作按钮 -->
      <el-row class="mb-4">
        <el-button type="primary" @click="showSetupDialog" :disabled="systemStatus.initialized">
          <i class="iconfont icon-setting"></i> 初始化系统
        </el-button>
        <el-button type="success" @click="showRegisterDialog">
          <i class="iconfont icon-plus"></i> 注册节点
        </el-button>
        <el-button type="info" @click="refreshNodeList">
          <i class="iconfont icon-refresh"></i> 刷新节点列表
        </el-button>
      </el-row>

      <!-- 节点列表 -->
      <el-table :data="nodeList" style="width: 100%" v-loading="loading">
        <el-table-column prop="node_id" label="节点ID" width="150"></el-table-column>
        <el-table-column prop="node_name" label="节点名称" width="120"></el-table-column>
        <el-table-column prop="ip_address" label="IP地址" width="120"></el-table-column>
        <el-table-column prop="port" label="端口" width="80"></el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="scope">
            <el-tag :type="getStatusType(scope.row.status)">
              {{ getStatusText(scope.row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="blockchain_stored" label="区块链存储" width="100">
          <template #default="scope">
            <el-tag :type="scope.row.blockchain_stored ? 'success' : 'warning'">
              {{ scope.row.blockchain_stored ? '已存储' : '未存储' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="160">
          <template #default="scope">
            {{ formatTime(scope.row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="scope">
            <el-button size="small" @click="viewNodeKeys(scope.row)">查看密钥</el-button>
            <el-button size="small" type="warning" @click="verifyIntegrity(scope.row)">验证完整性</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 系统初始化对话框 -->
    <el-dialog v-model="setupDialogVisible" title="初始化Falcon无证书密钥分发系统" width="600px">
      <el-form :model="setupForm" :rules="setupRules" ref="setupFormRef" label-width="120px">
        <el-form-item label="区块链节点URL" prop="provider_url">
          <el-input v-model="setupForm.provider_url" placeholder="http://localhost:8545"></el-input>
        </el-form-item>
        <el-form-item label="合约地址" prop="contract_address">
          <el-input v-model="setupForm.contract_address" placeholder="0x...（可选）"></el-input>
        </el-form-item>
        <el-form-item label="私钥" prop="private_key">
          <el-input v-model="setupForm.private_key" type="password" placeholder="0x..."></el-input>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="setupDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="setupSystem" :loading="setupLoading">确定</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 节点注册对话框 -->
    <el-dialog v-model="registerDialogVisible" title="注册新节点" width="500px">
      <el-form :model="registerForm" :rules="registerRules" ref="registerFormRef" label-width="100px">
        <el-form-item label="节点ID" prop="node_id">
          <el-input v-model="registerForm.node_id" placeholder="唯一节点标识"></el-input>
        </el-form-item>
        <el-form-item label="节点名称" prop="name">
          <el-input v-model="registerForm.name" placeholder="节点显示名称"></el-input>
        </el-form-item>
        <el-form-item label="IP地址" prop="ip_address">
          <el-input v-model="registerForm.ip_address" placeholder="192.168.1.100"></el-input>
        </el-form-item>
        <el-form-item label="端口" prop="port">
          <el-input-number v-model="registerForm.port" :min="1" :max="65535" placeholder="8080"></el-input-number>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="registerDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="registerNode" :loading="registerLoading">注册</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 密钥详情对话框 -->
    <el-dialog v-model="keyDialogVisible" title="节点密钥信息" width="800px">
      <div v-if="selectedNodeKeys">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="节点ID">{{ selectedNodeKeys.node_id }}</el-descriptions-item>
          <el-descriptions-item label="节点名称">{{ selectedNodeKeys.node_name }}</el-descriptions-item>
          <el-descriptions-item label="密钥状态">
            <el-tag :type="getStatusType(selectedNodeKeys.status)">
              {{ getStatusText(selectedNodeKeys.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="区块链存储">
            <el-tag :type="selectedNodeKeys.blockchain_stored ? 'success' : 'warning'">
              {{ selectedNodeKeys.blockchain_stored ? '已存储' : '未存储' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="区块链交易哈希" :span="2">
            <span class="hash">{{ selectedNodeKeys.blockchain_tx_hash || 'N/A' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="密钥完整性验证" :span="2">
            <el-tag :type="selectedNodeKeys.key_integrity_verified ? 'success' : 'danger'">
              {{ selectedNodeKeys.key_integrity_verified ? '验证通过' : '验证失败' }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>
        
        <el-divider>公钥信息</el-divider>
        <el-input
          type="textarea"
          :rows="6"
          :model-value="JSON.stringify(selectedNodeKeys.public_key, null, 2)"
          readonly
        ></el-input>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts" name="FalconKDS">
import { ref, reactive, onMounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import type { FormInstance, FormRules } from 'element-plus';
import {
  setupBlockchainFalconSystem,
  registerNodeWithBlockchain,
  getNodeFalconKeys,
  verifyFalconKeyIntegrity,
  getBlockchainStatus,
  listFalconNodes
} from '/@/api/pqkds/falcon';

// 响应式数据
const loading = ref(false);
const setupLoading = ref(false);
const registerLoading = ref(false);

// 系统状态
const systemStatus = reactive({
  initialized: false
});

const blockchainStatus = reactive({
  connected: false,
  latest_block: null,
  account: null
});

const nodeStats = reactive({
  total: 0,
  active: 0
});

// 节点列表
const nodeList = ref([]);

// 对话框状态
const setupDialogVisible = ref(false);
const registerDialogVisible = ref(false);
const keyDialogVisible = ref(false);

// 表单引用
const setupFormRef = ref<FormInstance>();
const registerFormRef = ref<FormInstance>();

// 表单数据
const setupForm = reactive({
  provider_url: 'http://localhost:8545',
  contract_address: '',
  private_key: ''
});

const registerForm = reactive({
  node_id: '',
  name: '',
  ip_address: '',
  port: 8080
});

// 选中的节点密钥信息
const selectedNodeKeys = ref(null);

// 表单验证规则
const setupRules: FormRules = {
  provider_url: [
    { required: true, message: '请输入区块链节点URL', trigger: 'blur' }
  ],
  private_key: [
    { required: true, message: '请输入私钥', trigger: 'blur' }
  ]
};

const registerRules: FormRules = {
  node_id: [
    { required: true, message: '请输入节点ID', trigger: 'blur' }
  ],
  name: [
    { required: true, message: '请输入节点名称', trigger: 'blur' }
  ],
  ip_address: [
    { required: true, message: '请输入IP地址', trigger: 'blur' }
  ],
  port: [
    { required: true, message: '请输入端口', trigger: 'blur' }
  ]
};

// 生命周期
onMounted(() => {
  refreshStatus();
  refreshNodeList();
});

// 方法
const refreshStatus = async () => {
  try {
    const blockchainRes = await getBlockchainStatus();
    if (blockchainRes.success) {
      Object.assign(blockchainStatus, blockchainRes.data.blockchain_status);
      systemStatus.initialized = true;
    }
  } catch (error) {
    console.error('获取状态失败:', error);
    systemStatus.initialized = false;
    blockchainStatus.connected = false;
  }
};

const refreshNodeList = async () => {
  loading.value = true;
  try {
    const res = await listFalconNodes();
    if (res.success) {
      nodeList.value = res.data.nodes;
      nodeStats.total = res.data.total_nodes;
      nodeStats.active = res.data.nodes.filter((n: any) => n.status === 'active').length;
    }
  } catch (error: any) {
    ElMessage.error('获取节点列表失败: ' + error.message);
  } finally {
    loading.value = false;
  }
};

const showSetupDialog = () => {
  setupDialogVisible.value = true;
};

const setupSystem = async () => {
  if (!setupFormRef.value) return;
  
  const valid = await setupFormRef.value.validate();
  if (valid) {
    setupLoading.value = true;
    try {
      const res = await setupBlockchainFalconSystem(setupForm);
      if (res.success) {
        ElMessage.success('系统初始化成功');
        setupDialogVisible.value = false;
        refreshStatus();
      } else {
        ElMessage.error('系统初始化失败: ' + res.message);
      }
    } catch (error: any) {
      ElMessage.error('系统初始化失败: ' + error.message);
    } finally {
      setupLoading.value = false;
    }
  }
};

const showRegisterDialog = () => {
  if (!systemStatus.initialized) {
    ElMessage.warning('请先初始化系统');
    return;
  }
  registerDialogVisible.value = true;
};

const registerNode = async () => {
  if (!registerFormRef.value) return;
  
  const valid = await registerFormRef.value.validate();
  if (valid) {
    registerLoading.value = true;
    try {
      const res = await registerNodeWithBlockchain(registerForm);
      if (res.success) {
        ElMessage.success('节点注册成功');
        registerDialogVisible.value = false;
        refreshNodeList();
        registerFormRef.value.resetFields();
      } else {
        ElMessage.error('节点注册失败: ' + res.message);
      }
    } catch (error: any) {
      ElMessage.error('节点注册失败: ' + error.message);
    } finally {
      registerLoading.value = false;
    }
  }
};

const viewNodeKeys = async (node: any) => {
  try {
    const res = await getNodeFalconKeys(node.node_id);
    if (res.success) {
      selectedNodeKeys.value = res.data;
      keyDialogVisible.value = true;
    } else {
      ElMessage.error('获取密钥信息失败: ' + res.message);
    }
  } catch (error: any) {
    ElMessage.error('获取密钥信息失败: ' + error.message);
  }
};

const verifyIntegrity = async (node: any) => {
  try {
    const res = await verifyFalconKeyIntegrity({ node_id: node.node_id });
    if (res.success) {
      const verified = res.data.integrity_verified;
      ElMessage({
        type: verified ? 'success' : 'warning',
        message: verified ? '密钥完整性验证通过' : '密钥完整性验证失败'
      });
      refreshNodeList();
    } else {
      ElMessage.error('验证失败: ' + res.message);
    }
  } catch (error: any) {
    ElMessage.error('验证失败: ' + error.message);
  }
};

const getStatusType = (status: string) => {
  const statusMap: Record<string, string> = {
    'active': 'success',
    'revoked': 'danger',
    'expired': 'warning'
  };
  return statusMap[status] || 'info';
};

const getStatusText = (status: string) => {
  const statusMap: Record<string, string> = {
    'active': '活跃',
    'revoked': '已撤销',
    'expired': '已过期'
  };
  return statusMap[status] || status;
};

const formatTime = (timeStr: string) => {
  if (!timeStr) return 'N/A';
  return new Date(timeStr).toLocaleString();
};
</script>

<style scoped>
.falcon-kds-container {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.mb-4 {
  margin-bottom: 16px;
}

.status-item {
  margin-bottom: 10px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.address {
  font-family: monospace;
  font-size: 12px;
  word-break: break-all;
}

.hash {
  font-family: monospace;
  font-size: 12px;
  word-break: break-all;
  color: #409EFF;
}
</style>
