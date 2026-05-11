<template>
  <div class="app-container">
    <!-- 页面标题 -->
    <div class="page-header">
      <h2>📝 操作日志</h2>
      <p>查看系统操作日志，监控系统活动</p>
    </div>

    <!-- 搜索和操作区域 -->
    <el-card class="search-card">
      <el-row :gutter="20">
        <el-col :span="20">
          <el-form :model="searchForm" inline>
            <el-form-item label="操作模块">
              <el-select v-model="searchForm.request_modular" placeholder="请选择模块" clearable>
                <el-option label="节点" value="节点" />
                <el-option label="节点管理" value="节点管理" />
                <el-option label="会话密钥" value="会话密钥" />
                <el-option label="会话管理" value="会话管理" />
                <el-option label="区块链配置" value="区块链配置" />
                <el-option label="区块链管理" value="区块链管理" />
                <el-option label="密钥管理" value="密钥管理" />
                <el-option label="系统参数" value="系统参数" />
                <el-option label="KGC密钥生成" value="KGC密钥生成" />
                <el-option label="消息管理" value="消息管理" />
                <el-option label="登录模块" value="登录模块" />
              </el-select>
            </el-form-item>
            <el-form-item label="请求路径">
              <el-input v-model="searchForm.request_path" placeholder="请输入请求路径" clearable />
            </el-form-item>
            <el-form-item label="请求方法">
              <el-select v-model="searchForm.request_method" placeholder="请选择请求方法" clearable>
                <el-option label="GET" value="GET" />
                <el-option label="POST" value="POST" />
                <el-option label="PUT" value="PUT" />
                <el-option label="DELETE" value="DELETE" />
                <el-option label="PATCH" value="PATCH" />
              </el-select>
            </el-form-item>
            <el-form-item label="状态">
              <el-select v-model="searchForm.status" placeholder="请选择状态" clearable>
                <el-option label="成功" :value="true" />
                <el-option label="失败" :value="false" />
              </el-select>
            </el-form-item>
            <el-form-item label="时间范围">
              <el-date-picker
                v-model="searchForm.dateRange"
                type="datetimerange"
                range-separator="至"
                start-placeholder="开始时间"
                end-placeholder="结束时间"
                format="YYYY-MM-DD HH:mm:ss"
                value-format="YYYY-MM-DD HH:mm:ss"
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="loadLogList">
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
        <el-col :span="4" style="text-align: right;">
          <el-button type="success" @click="loadLogList">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
          <el-button type="info" @click="exportLogs">
            <el-icon><Download /></el-icon>
            导出
          </el-button>
        </el-col>
      </el-row>
    </el-card>

    <!-- 统计卡片 -->
    <el-row :gutter="20" class="stats-cards">
      <el-col :span="6">
        <el-card class="stat-card">
          <div class="stat-item">
            <div class="stat-icon total">
              <el-icon><Document /></el-icon>
            </div>
            <div class="stat-content">
              <div class="stat-value">{{ logStats.total_logs }}</div>
              <div class="stat-label">总日志数</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <div class="stat-item">
            <div class="stat-icon success">
              <el-icon><CircleCheck /></el-icon>
            </div>
            <div class="stat-content">
              <div class="stat-value">{{ logStats.success_logs }}</div>
              <div class="stat-label">成功操作</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <div class="stat-item">
            <div class="stat-icon error">
              <el-icon><CircleClose /></el-icon>
            </div>
            <div class="stat-content">
              <div class="stat-value">{{ logStats.error_logs }}</div>
              <div class="stat-label">失败操作</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <div class="stat-item">
            <div class="stat-icon today">
              <el-icon><Calendar /></el-icon>
            </div>
            <div class="stat-content">
              <div class="stat-value">{{ logStats.today_logs }}</div>
              <div class="stat-label">今日日志</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 日志列表 -->
    <el-card>
      <el-table :data="logList" v-loading="loading" style="width: 100%">
        <el-table-column label="序号" width="80" align="center">
          <template #default="scope">
            {{ pagination.total - (pagination.page - 1) * pagination.size - scope.$index }}
          </template>
        </el-table-column>
        <el-table-column prop="request_path" label="请求路径" min-width="180" show-overflow-tooltip />
        <el-table-column prop="request_method" label="请求方法" width="100">
          <template #default="scope">
            <el-tag :type="getMethodType(scope.row.request_method)">
              {{ scope.row.request_method }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="request_modular" label="操作模块" width="120" />
        <el-table-column prop="request_msg" label="操作说明" min-width="200" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="scope">
            <el-tag :type="scope.row.status ? 'success' : 'danger'">
              {{ scope.row.status ? '成功' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="request_ip" label="请求IP" width="150" />
        <el-table-column prop="create_datetime" label="时间" width="180">
          <template #default="scope">
            {{ formatDateTime(scope.row.create_datetime) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="scope">
            <el-button size="small" @click="viewDetails(scope.row)">详情</el-button>
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
          @size-change="loadLogList"
          @current-change="loadLogList"
        />
      </div>
    </el-card>

    <!-- 日志详情对话框 -->
    <el-dialog v-model="detailsDialogVisible" title="日志详情" width="800px">
      <el-descriptions :column="1" border v-if="selectedLog">
        <el-descriptions-item label="日志ID">{{ selectedLog.id }}</el-descriptions-item>
        <el-descriptions-item label="请求路径">{{ selectedLog.request_path }}</el-descriptions-item>
        <el-descriptions-item label="请求方法">
          <el-tag :type="getMethodType(selectedLog.request_method)">
            {{ selectedLog.request_method }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="操作模块">{{ selectedLog.request_modular }}</el-descriptions-item>
        <el-descriptions-item label="操作说明">{{ selectedLog.request_msg }}</el-descriptions-item>
        <el-descriptions-item label="操作状态">
          <el-tag :type="selectedLog.status ? 'success' : 'danger'">
            {{ selectedLog.status ? '成功' : '失败' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="请求IP">{{ selectedLog.request_ip }}</el-descriptions-item>
        <el-descriptions-item label="浏览器">{{ selectedLog.request_browser }}</el-descriptions-item>
        <el-descriptions-item label="操作系统">{{ selectedLog.request_os }}</el-descriptions-item>
        <el-descriptions-item label="操作时间">{{ formatDateTime(selectedLog.create_datetime) }}</el-descriptions-item>
        <el-descriptions-item label="请求参数">
          <div class="details-content">{{ JSON.stringify(selectedLog.request_body, null, 2) }}</div>
        </el-descriptions-item>
        <el-descriptions-item label="返回信息">
          <div class="details-content">{{ JSON.stringify(selectedLog.json_result, null, 2) }}</div>
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { 
  Search, Refresh, Download, Document, CircleCheck, 
  CircleClose, Calendar 
} from '@element-plus/icons-vue'
import { logsApi } from '@/api/pqkds/logs'

// 响应式数据
const loading = ref(false)
const logList = ref([])
const detailsDialogVisible = ref(false)
const selectedLog = ref(null)

const logStats = ref({
  total_logs: 0,
  success_logs: 0,
  error_logs: 0,
  today_logs: 0
})

const searchForm = reactive({
  request_modular: '',
  request_path: '',
  request_method: '',
  status: true,  // 默认只显示成功的日志
  dateRange: null
})

const pagination = reactive({
  page: 1,
  size: 20,
  total: 0
})

// 方法
const loadLogList = async () => {
  try {
    loading.value = true
    const params = {
      page: pagination.page,
      limit: pagination.size,
      ordering: '-create_datetime'  // 按时间从大到小排序（最新的在前）
    }

    if (searchForm.request_modular) {
      params.request_modular = searchForm.request_modular
    }
    if (searchForm.request_path) {
      params.request_path__icontains = searchForm.request_path
    }
    if (searchForm.request_method) {
      params.request_method = searchForm.request_method
    }
    if (searchForm.status !== null) {
      // 确保布尔值正确转换，不要转换为字符串
      params.status = searchForm.status === true ? 1 : 0
    }

    if (searchForm.dateRange && searchForm.dateRange.length === 2) {
      params.create_datetime__gte = searchForm.dateRange[0]
      params.create_datetime__lte = searchForm.dateRange[1]
    }

    const response = await logsApi.getList(params)
    if (response.code === 2000) {
      logList.value = response.data || []
      // 后端返回的分页信息在顶层，不在 data 内
      pagination.total = response.total || 0
      pagination.page = response.page || 1
      pagination.size = response.limit || 20
    }
  } catch (error) {
    ElMessage.error('获取日志列表失败')
  } finally {
    loading.value = false
  }
}

const loadLogStats = async () => {
  try {
    const response = await logsApi.getStats()
    if (response.code === 2000) {
      const logs = response.data.results || response.data || []

      const successLogs = logs.filter(l => l.status === true)
      const total = successLogs.length
      const today = new Date().toDateString()

      logStats.value = {
        total_logs: total,
        success_logs: total,
        error_logs: 0,
        today_logs: successLogs.filter(l => new Date(l.create_datetime).toDateString() === today).length
      }
    }
  } catch (error) {
    console.error('获取日志统计失败:', error)
  }
}

const resetSearch = () => {
  Object.assign(searchForm, {
    request_modular: '',
    request_path: '',
    request_method: '',
    status: true,  // 重置后仍默认只显示成功日志
    dateRange: null
  })
  pagination.page = 1
  loadLogList()
}

const viewDetails = async (log) => {
  try {
    const response = await logsApi.getDetail(log.id)
    if (response.code === 2000) {
      selectedLog.value = response.data
      detailsDialogVisible.value = true
    }
  } catch (error) {
    ElMessage.error('获取日志详情失败')
  }
}

const exportLogs = () => {
  ElMessage.info('导出功能开发中...')
}

const getMethodType = (method) => {
  const typeMap = {
    'GET': 'info',
    'POST': 'success',
    'PUT': 'warning',
    'DELETE': 'danger',
    'PATCH': 'warning'
  }
  return typeMap[method] || 'info'
}

const formatDateTime = (dateTime) => {
  if (!dateTime) return '-'
  return new Date(dateTime).toLocaleString('zh-CN')
}

// 生命周期
onMounted(() => {
  loadLogList()
  loadLogStats()
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

.stats-cards {
  margin-bottom: 20px;
}

.stat-card {
  height: 100px;
}

.stat-item {
  display: flex;
  align-items: center;
  height: 100%;
}

.stat-icon {
  width: 50px;
  height: 50px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 16px;
  font-size: 20px;
  color: white;
}

.stat-icon.total {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.stat-icon.success {
  background: linear-gradient(135deg, #67c23a 0%, #85ce61 100%);
}

.stat-icon.error {
  background: linear-gradient(135deg, #f56c6c 0%, #f78989 100%);
}

.stat-icon.today {
  background: linear-gradient(135deg, #e6a23c 0%, #ebb563 100%);
}

.stat-content {
  flex: 1;
}

.stat-value {
  font-size: 24px;
  font-weight: bold;
  color: #303133;
  line-height: 1;
}

.stat-label {
  font-size: 14px;
  color: #909399;
  margin-top: 8px;
}

.pagination-container {
  margin-top: 20px;
  text-align: right;
}

.details-text {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.details-content {
  white-space: pre-wrap;
  word-break: break-all;
}

.error-content {
  color: #f56c6c;
  white-space: pre-wrap;
  word-break: break-all;
}

.hash-text {
  font-family: monospace;
  font-size: 12px;
  word-break: break-all;
  background: #f5f5f5;
  padding: 4px 8px;
  border-radius: 4px;
}
</style>
