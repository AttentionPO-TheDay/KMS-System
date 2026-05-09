<template>
  <div class="app-container">
    <el-card class="box-card">
      <div slot="header" class="clearfix">
        <span>Falcon无证书密钥分发系统</span>
        <el-button style="float: right; padding: 3px 0" type="text" @click="refreshStatus">刷新状态</el-button>
      </div>
      
      <!-- 系统状态 -->
      <el-row :gutter="20" class="mb20">
        <el-col :span="8">
          <el-card shadow="hover">
            <div slot="header">
              <i class="el-icon-cpu"></i> 系统状态
            </div>
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
            <div slot="header">
              <i class="el-icon-link"></i> 区块链信息
            </div>
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
            <div slot="header">
              <i class="el-icon-key"></i> 密钥统计
            </div>
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
      <el-row class="mb20">
        <el-button type="primary" @click="showSetupDialog" :disabled="systemStatus.initialized">
          <i class="el-icon-setting"></i> 初始化系统
        </el-button>
        <el-button type="success" @click="showRegisterDialog">
          <i class="el-icon-plus"></i> 注册节点
        </el-button>
        <el-button type="info" @click="refreshNodeList">
          <i class="el-icon-refresh"></i> 刷新节点列表
        </el-button>
      </el-row>

      <!-- 节点列表 -->
      <el-table :data="nodeList" style="width: 100%" v-loading="loading">
        <el-table-column prop="node_id" label="节点ID" width="150"></el-table-column>
        <el-table-column prop="node_name" label="节点名称" width="120"></el-table-column>
        <el-table-column prop="ip_address" label="IP地址" width="120"></el-table-column>
        <el-table-column prop="port" label="端口" width="80"></el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template slot-scope="scope">
            <el-tag :type="getStatusType(scope.row.status)">
              {{ getStatusText(scope.row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="blockchain_stored" label="区块链存储" width="100">
          <template slot-scope="scope">
            <el-tag :type="scope.row.blockchain_stored ? 'success' : 'warning'">
              {{ scope.row.blockchain_stored ? '已存储' : '未存储' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="160">
          <template slot-scope="scope">
            {{ formatTime(scope.row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template slot-scope="scope">
            <el-button size="mini" @click="viewNodeKeys(scope.row)">查看密钥</el-button>
            <el-button size="mini" type="warning" @click="verifyIntegrity(scope.row)">验证完整性</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 系统初始化对话框 -->
    <el-dialog title="初始化Falcon无证书密钥分发系统" :visible.sync="setupDialogVisible" width="600px">
      <el-form :model="setupForm" :rules="setupRules" ref="setupForm" label-width="120px">
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
      <div slot="footer" class="dialog-footer">
        <el-button @click="setupDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="setupSystem" :loading="setupLoading">确定</el-button>
      </div>
    </el-dialog>

    <!-- 节点注册对话框 -->
    <el-dialog title="注册新节点" :visible.sync="registerDialogVisible" width="500px">
      <el-form :model="registerForm" :rules="registerRules" ref="registerForm" label-width="100px">
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
      <div slot="footer" class="dialog-footer">
        <el-button @click="registerDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="registerNode" :loading="registerLoading">注册</el-button>
      </div>
    </el-dialog>

    <!-- 密钥详情对话框 -->
    <el-dialog title="节点密钥信息" :visible.sync="keyDialogVisible" width="800px">
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
          :value="JSON.stringify(selectedNodeKeys.public_key, null, 2)"
          readonly
        ></el-input>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import {
  setupBlockchainFalconSystem,
  registerNodeWithBlockchain,
  getNodeFalconKeys,
  verifyFalconKeyIntegrity,
  getBlockchainStatus,
  listFalconNodes
} from '@/api/pqkds/falcon'

export default {
  name: 'FalconKDS',
  data() {
    return {
      loading: false,
      setupLoading: false,
      registerLoading: false,
      
      // 系统状态
      systemStatus: {
        initialized: false
      },
      blockchainStatus: {
        connected: false
      },
      nodeStats: {
        total: 0,
        active: 0
      },
      
      // 节点列表
      nodeList: [],
      
      // 对话框状态
      setupDialogVisible: false,
      registerDialogVisible: false,
      keyDialogVisible: false,
      
      // 表单数据
      setupForm: {
        provider_url: 'http://localhost:8545',
        contract_address: '',
        private_key: ''
      },
      registerForm: {
        node_id: '',
        name: '',
        ip_address: '',
        port: 8080
      },
      
      // 选中的节点密钥信息
      selectedNodeKeys: null,
      
      // 表单验证规则
      setupRules: {
        provider_url: [
          { required: true, message: '请输入区块链节点URL', trigger: 'blur' }
        ],
        private_key: [
          { required: true, message: '请输入私钥', trigger: 'blur' }
        ]
      },
      registerRules: {
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
      }
    }
  },
  
  created() {
    this.refreshStatus()
    this.refreshNodeList()
  },
  
  methods: {
    // 刷新系统状态
    async refreshStatus() {
      try {
        // 获取区块链状态
        const blockchainRes = await getBlockchainStatus()
        if (blockchainRes.success) {
          this.blockchainStatus = blockchainRes.data.blockchain_status
          this.systemStatus.initialized = true
        }
      } catch (error) {
        console.error('获取状态失败:', error)
        this.systemStatus.initialized = false
        this.blockchainStatus.connected = false
      }
    },
    
    // 刷新节点列表
    async refreshNodeList() {
      this.loading = true
      try {
        const res = await listFalconNodes()
        if (res.success) {
          this.nodeList = res.data.nodes
          this.nodeStats.total = res.data.total_nodes
          this.nodeStats.active = res.data.nodes.filter(n => n.status === 'active').length
        }
      } catch (error) {
        this.$message.error('获取节点列表失败: ' + error.message)
      } finally {
        this.loading = false
      }
    },
    
    // 显示系统初始化对话框
    showSetupDialog() {
      this.setupDialogVisible = true
    },
    
    // 初始化系统
    setupSystem() {
      this.$refs.setupForm.validate(async (valid) => {
        if (valid) {
          this.setupLoading = true
          try {
            const res = await setupBlockchainFalconSystem(this.setupForm)
            if (res.success) {
              this.$message.success('系统初始化成功')
              this.setupDialogVisible = false
              this.refreshStatus()
            } else {
              this.$message.error('系统初始化失败: ' + res.message)
            }
          } catch (error) {
            this.$message.error('系统初始化失败: ' + error.message)
          } finally {
            this.setupLoading = false
          }
        }
      })
    },
    
    // 显示节点注册对话框
    showRegisterDialog() {
      if (!this.systemStatus.initialized) {
        this.$message.warning('请先初始化系统')
        return
      }
      this.registerDialogVisible = true
    },
    
    // 注册节点
    registerNode() {
      this.$refs.registerForm.validate(async (valid) => {
        if (valid) {
          this.registerLoading = true
          try {
            const res = await registerNodeWithBlockchain(this.registerForm)
            if (res.success) {
              this.$message.success('节点注册成功')
              this.registerDialogVisible = false
              this.refreshNodeList()
              // 重置表单
              this.$refs.registerForm.resetFields()
            } else {
              this.$message.error('节点注册失败: ' + res.message)
            }
          } catch (error) {
            this.$message.error('节点注册失败: ' + error.message)
          } finally {
            this.registerLoading = false
          }
        }
      })
    },
    
    // 查看节点密钥
    async viewNodeKeys(node) {
      try {
        const res = await getNodeFalconKeys(node.node_id)
        if (res.success) {
          this.selectedNodeKeys = res.data
          this.keyDialogVisible = true
        } else {
          this.$message.error('获取密钥信息失败: ' + res.message)
        }
      } catch (error) {
        this.$message.error('获取密钥信息失败: ' + error.message)
      }
    },
    
    // 验证密钥完整性
    async verifyIntegrity(node) {
      try {
        const res = await verifyFalconKeyIntegrity({ node_id: node.node_id })
        if (res.success) {
          const verified = res.data.integrity_verified
          this.$message({
            type: verified ? 'success' : 'warning',
            message: verified ? '密钥完整性验证通过' : '密钥完整性验证失败'
          })
          // 刷新节点列表
          this.refreshNodeList()
        } else {
          this.$message.error('验证失败: ' + res.message)
        }
      } catch (error) {
        this.$message.error('验证失败: ' + error.message)
      }
    },
    
    // 获取状态类型
    getStatusType(status) {
      const statusMap = {
        'active': 'success',
        'revoked': 'danger',
        'expired': 'warning'
      }
      return statusMap[status] || 'info'
    },
    
    // 获取状态文本
    getStatusText(status) {
      const statusMap = {
        'active': '活跃',
        'revoked': '已撤销',
        'expired': '已过期'
      }
      return statusMap[status] || status
    },
    
    // 格式化时间
    formatTime(timeStr) {
      if (!timeStr) return 'N/A'
      return new Date(timeStr).toLocaleString()
    }
  }
}
</script>

<style scoped>
.mb20 {
  margin-bottom: 20px;
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
