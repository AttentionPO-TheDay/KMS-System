<template>
  <section class="page">

    <article class="panel">
      <div class="panel-head">
        <div>
          <h3>当前查询范围</h3>
          <p class="muted">普通用户仅可查看自己的分发记录，用户名条件不会跨用户生效。</p>
        </div>
      </div>
      <div class="detail-grid scope-grid">
        <p><strong>用户 ID：</strong>{{ profile.userId || '-' }}</p>
        <p><strong>用户名：</strong>{{ profile.userName || '-' }}</p>
      </div>
    </article>

    <div class="metric-grid mb16">
      <div class="metric-card glass-panel">
        <span class="metric-icon">📑</span>
        <div class="metric-info">
          <span class="label">符合当前筛选的总记录</span>
          <strong class="value">{{ total }}</strong>
        </div>
      </div>
      <div class="metric-card glass-panel">
        <span class="metric-icon">🔍</span>
        <div class="metric-info">
          <span class="label">本页加载记录数</span>
          <strong class="value">{{ records.length }}</strong>
        </div>
      </div>
    </div>

    <article class="panel glass-panel">
      <el-form :model="filters" inline class="query-form mb16">
        <el-form-item label="密钥名称">
          <el-input v-model="filters.keyName" @keyup.enter="handleSearch" placeholder="按密钥名称筛选" clearable />
        </el-form-item>
        <el-form-item label="分发类型">
          <el-select v-model="filters.distributeType" @change="handleSearch" clearable placeholder="全部">
            <el-option label="初始分发" value="1" />
            <el-option label="更新分发" value="2" />
            <el-option label="回收后补发" value="3" />
          </el-select>
        </el-form-item>
        <el-form-item label="分发状态">
          <el-select v-model="filters.distributeStatus" @change="handleSearch" clearable placeholder="全部">
            <el-option label="待分发" value="0" />
            <el-option label="分发中" value="1" />
            <el-option label="分发成功" value="2" />
            <el-option label="分发失败" value="3" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">搜索</el-button>
          <el-button @click="resetFilters">重置</el-button>
          <el-button type="primary" plain @click="loadRecords">立即刷新</el-button>
          <el-button :type="autoRefreshEnabled ? 'warning' : 'info'" plain @click="toggleAutoRefresh">
            {{ autoRefreshEnabled ? '关闭自动刷新（10秒）' : '开启自动刷新（10秒）' }}
          </el-button>
          <el-button type="success" plain @click="handleExport">导出结果</el-button>
        </el-form-item>
      </el-form>
      <p class="muted">导出文件：<code>key-distribute-record-时间戳.xlsx</code></p>
      <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>
      
      <el-table :data="records" class="mt16" empty-text="暂无分发记录">
        <el-table-column label="记录 ID" prop="recordId" width="90" />
        <el-table-column label="密钥名称" prop="keyName" min-width="160" />
        <el-table-column label="用户名" prop="userName" width="120" />
        <el-table-column label="加密算法" prop="encrytName" width="120" />
        <el-table-column label="分发类型" width="120">
          <template #default="scope">{{ typeText(scope.row.distributeType) }}</template>
        </el-table-column>
        <el-table-column label="分发状态" width="120">
          <template #default="scope">
            <span class="style-badge" :class="`status-${scope.row.distributeStatus || '0'}`">
              {{ statusText(scope.row.distributeStatus) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="分发时间" prop="distributeTime" width="180" />
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="scope">
            <el-button link type="primary" @click="showDetail(scope.row.recordId)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-show="total > 0" class="pagination">
        <el-pagination
          background
          layout="total, prev, pager, next"
          :total="total"
          v-model:current-page="filters.pageNum"
          :page-size="filters.pageSize"
          @current-change="changePage"
        />
      </div>
    </article>

    <el-dialog :model-value="!!selectedRecord" title="记录详情" width="600px" append-to-body @update:model-value="(val) => { if(!val) selectedRecord = null }" destroy-on-close>
      <div v-if="selectedRecord" class="detail-grid">
        <p><strong>记录 ID：</strong>{{ selectedRecord.recordId }}</p>
        <p><strong>密钥 ID：</strong>{{ selectedRecord.keyId }}</p>
        <p><strong>用户名：</strong>{{ selectedRecord.userName || '-' }}</p>
        <p><strong>密钥名称：</strong>{{ selectedRecord.keyName || '-' }}</p>
        <p><strong>加密算法：</strong>{{ selectedRecord.encrytName || '-' }}</p>
        <p><strong>分发类型：</strong>{{ typeText(selectedRecord.distributeType) }}</p>
        <p><strong>分发状态：</strong>
          <span class="style-badge" :class="`status-${selectedRecord.distributeStatus || '0'}`">
            {{ statusText(selectedRecord.distributeStatus) }}
          </span>
        </p>
        <p><strong>分发时间：</strong>{{ selectedRecord.distributeTime || '-' }}</p>
        <p><strong>区块高度：</strong>{{ selectedRecord.blockHeight ?? '-' }}</p>
        <p><strong>区块链 Hash：</strong>{{ selectedRecord.chainHash || '-' }}</p>
        <p class="detail-span"><strong>备注：</strong>{{ selectedRecord.remark || '-' }}</p>
      </div>
      <template #footer>
        <el-button @click="selectedRecord = null">关闭</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup>
import { computed, getCurrentInstance, onMounted, onUnmounted, reactive, ref } from 'vue'
import { apiBases } from '@/config/api-bases'
import { getDistributeRecord, listDistributeRecords } from '@/services/distribute-api'
import useUserStore from '@/store/modules/user'

const { proxy } = getCurrentInstance()
const userStore = useUserStore()
const apiBase = apiBases.distributeApi
const profile = reactive({
  userId: '',
  userName: ''
})
const filters = reactive({
  pageNum: 1,
  pageSize: 10,
  keyName: '',
  distributeType: '',
  distributeStatus: ''
})
const records = ref([])
const selectedRecord = ref(null)
const errorMessage = ref('')
const total = ref(0)
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / filters.pageSize)))
const autoRefreshEnabled = ref(false)
const AUTO_REFRESH_INTERVAL = 10000
let autoRefreshTimer = null

onMounted(async () => {
  if (userStore.token && (!userStore.id || !userStore.name)) {
    try {
      await userStore.getInfo()
    } catch (error) {
      errorMessage.value = error.message
    }
  }
  profile.userId = userStore.id || ''
  profile.userName = userStore.name || ''
  loadRecords()
})

onUnmounted(() => {
  stopAutoRefresh()
})

async function loadRecords() {
  errorMessage.value = ''
  selectedRecord.value = null
  try {
    const data = await listDistributeRecords(filters)
    records.value = data.rows || []
    total.value = data.total || 0
  } catch (error) {
    records.value = []
    total.value = 0
    errorMessage.value = error.message
  }
}

function handleSearch() {
  filters.pageNum = 1
  loadRecords()
}

function resetFilters() {
  filters.pageNum = 1
  filters.pageSize = 10
  filters.keyName = ''
  filters.distributeType = ''
  filters.distributeStatus = ''
  loadRecords()
}

function handleExport() {
  errorMessage.value = ''
  try {
    proxy.download('/distribute/record/export', buildExportParams(), `key-distribute-record-${Date.now()}.xlsx`, {
      baseURL: apiBases.distributeApi
    })
  } catch (error) {
    errorMessage.value = error.message || '导出失败'
  }
}

function changePage(pageNum) {
  filters.pageNum = pageNum
  loadRecords()
}

function toggleAutoRefresh() {
  autoRefreshEnabled.value = !autoRefreshEnabled.value
  if (autoRefreshEnabled.value) {
    startAutoRefresh()
    loadRecords()
    return
  }
  stopAutoRefresh()
}

function startAutoRefresh() {
  stopAutoRefresh()
  autoRefreshTimer = window.setInterval(() => {
    loadRecords()
  }, AUTO_REFRESH_INTERVAL)
}

function stopAutoRefresh() {
  if (autoRefreshTimer !== null) {
    window.clearInterval(autoRefreshTimer)
    autoRefreshTimer = null
  }
}

async function showDetail(recordId) {
  errorMessage.value = ''
  try {
    const data = await getDistributeRecord(recordId)
    selectedRecord.value = data.data || null
  } catch (error) {
    errorMessage.value = error.message
  }
}

function typeText(type) {
  return { 1: '初始分发', 2: '更新分发', 3: '回收后补发', '1': '初始分发', '2': '更新分发', '3': '回收后补发' }[type] || '未知'
}

function statusText(status) {
  return { 0: '待分发', 1: '分发中', 2: '分发成功', 3: '分发失败', '0': '待分发', '1': '分发中', '2': '分发成功', '3': '分发失败' }[status] || '未知'
}

function buildExportParams() {
  return {
    keyName: normalizeFilter(filters.keyName),
    distributeType: normalizeFilter(filters.distributeType),
    distributeStatus: normalizeFilter(filters.distributeStatus)
  }
}

function normalizeFilter(value) {
  const text = value == null ? '' : String(value).trim()
  return text === '' ? undefined : text
}
</script>

<style scoped>
.metric-grid {
  display: flex;
  gap: 20px;
  margin-bottom: 24px;
}

.metric-card {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 24px;
  background: rgba(255, 255, 255, 0.02);
  backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
}

.metric-icon {
  font-size: 32px;
  background: linear-gradient(135deg, rgba(0, 229, 255, 0.3), rgba(0, 153, 255, 0.5));
  width: 60px;
  height: 60px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 0 15px rgba(0, 229, 255, 0.4);
}

.metric-info {
  display: flex;
  flex-direction: column;
}

.metric-info .label {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.6);
  margin-bottom: 6px;
}

.metric-info .value {
  font-size: 28px;
  font-weight: 600;
  color: #00e5ff;
}

.toolbar {
  align-items: end;
}

.toolbar-actions {
  display: flex;
  gap: 8px;
}

.pagination {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 12px;
  margin-top: 24px;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 16px 24px;
}

.style-badge {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
}
.status-0 { background: rgba(255, 255, 255, 0.1); color: #fff; }
.status-1 { background: rgba(0, 153, 255, 0.2); color: #00e5ff; }
.status-2 { background: rgba(0, 255, 128, 0.2); color: #00ff80; }
.status-3 { background: rgba(255, 80, 80, 0.2); color: #ff5050; }

.detail-span {
  grid-column: 1 / -1;
}

@media (max-width: 768px) {
  .metric-grid {
    flex-direction: column;
  }
}
</style>
