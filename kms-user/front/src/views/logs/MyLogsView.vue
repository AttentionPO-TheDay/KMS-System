<template>
  <section class="page my-logs-page">
    <article class="panel">
      <div class="panel-head header-actions">
        <div class="identity-line">
          <strong>{{ userStore.name || '未登录' }}</strong>
          <el-tag size="small" type="info">{{ roleText(userStore.roleLevel) }}</el-tag>
        </div>
        <div class="header-buttons">
          <span class="muted">仅显示当前账号本人的记录</span>
          <el-button @click="reloadCurrentTab">刷新当前页</el-button>
        </div>
      </div>
    </article>

    <div class="logs-dashboard">
      <nav class="inner-sidenav">
        <div
          v-for="tab in TABS"
          :key="tab.key"
          class="nav-item"
          :class="{ active: activeTab === tab.key }"
          @click="activeTab = tab.key"
        >
          <el-icon class="icon"><component :is="tab.icon" /></el-icon> {{ tab.label }}
        </div>
      </nav>

      <main class="inner-main-content">
        <!-- 1. 密钥操作记录 -->
        <div v-show="activeTab === 'keys'" class="tab-pane">
          <article class="panel">
            <el-form :model="keyQuery" inline label-width="88px" class="query-form">
              <el-form-item label="操作类型">
                <el-select v-model="keyQuery.actionType" placeholder="全部" clearable>
                  <el-option label="密钥更新" value="UPDATE" />
                  <el-option label="KMS引用回收" value="REVOKE" />
                </el-select>
              </el-form-item>
              <el-form-item label="处理结果">
                <el-select v-model="keyQuery.resultStatus" placeholder="全部" clearable>
                  <el-option label="处理中" value="0" />
                  <el-option label="成功" value="1" />
                  <el-option label="失败" value="2" />
                </el-select>
              </el-form-item>
              <el-form-item>
                <el-button type="primary" @click="searchKeys">搜索</el-button>
                <el-button @click="resetKeys">重置</el-button>
              </el-form-item>
            </el-form>

            <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>

            <el-table v-loading="keyLoading" :data="keyRecords">
              <el-table-column label="记录ID" prop="recordId" width="90" />
              <el-table-column label="密钥名称" prop="keyName" min-width="150" show-overflow-tooltip />
              <el-table-column label="算法" prop="encrytName" width="110" />
              <el-table-column label="操作类型" width="120">
                <template #default="scope">{{ actionTypeText(scope.row.actionType) }}</template>
              </el-table-column>
              <el-table-column label="来源" width="90">
                <template #default="scope">{{ actionSourceText(scope.row.actionSource) }}</template>
              </el-table-column>
              <el-table-column label="结果" width="100">
                <template #default="scope">
                  <el-tag :type="resultStatusType(scope.row.resultStatus)">
                    {{ resultStatusText(scope.row.resultStatus) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="上链状态" width="110">
                <template #default="scope">
                  <el-tag :type="chainStatusType(scope.row.chainStatus)" effect="plain">
                    {{ chainStatusText(scope.row.chainStatus) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="交易哈希" prop="chainHash" min-width="180" show-overflow-tooltip />
              <el-table-column label="区块高度" prop="blockHeight" width="110" />
              <el-table-column label="操作时间" width="170">
                <template #default="scope">{{ formatDateTime(scope.row.actionTime) }}</template>
              </el-table-column>
              <template #empty>暂无密钥操作记录</template>
            </el-table>

            <pagination
              v-show="keyTotal > 0"
              :total="keyTotal"
              v-model:page="keyQuery.pageNum"
              v-model:limit="keyQuery.pageSize"
              @pagination="loadKeyRecords"
            />
          </article>
        </div>

        <!-- 2. 系统操作日志 -->
        <div v-show="activeTab === 'operations'" class="tab-pane">
          <article class="panel">
            <el-form :model="operQuery" inline label-width="88px" class="query-form">
              <el-form-item label="系统模块">
                <el-input v-model="operQuery.title" placeholder="请输入模块名" clearable />
              </el-form-item>
              <el-form-item label="操作状态">
                <el-select v-model="operQuery.status" placeholder="全部" clearable>
                  <el-option label="成功" value="0" />
                  <el-option label="失败" value="1" />
                </el-select>
              </el-form-item>
              <el-form-item label="操作时间">
                <el-date-picker
                  v-model="operDateRange"
                  type="daterange"
                  value-format="YYYY-MM-DD"
                  range-separator="至"
                  start-placeholder="开始日期"
                  end-placeholder="结束日期"
                  :teleported="false"
                />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" @click="searchOperations">搜索</el-button>
                <el-button @click="resetOperations">重置</el-button>
              </el-form-item>
            </el-form>

            <el-table v-loading="operLoading" :data="operRecords">
              <el-table-column label="编号" prop="operId" width="90" />
              <el-table-column label="系统模块" prop="title" min-width="140" show-overflow-tooltip />
              <el-table-column label="操作类型" width="110">
                <template #default="scope">{{ businessTypeText(scope.row.businessType) }}</template>
              </el-table-column>
              <el-table-column label="请求方式" prop="requestMethod" width="100" />
              <el-table-column label="操作地址" prop="operUrl" min-width="180" show-overflow-tooltip />
              <el-table-column label="主机" prop="operIp" width="140" />
              <el-table-column label="操作地点" prop="operLocation" min-width="130" show-overflow-tooltip />
              <el-table-column label="状态" width="90">
                <template #default="scope">
                  <el-tag :type="String(scope.row.status) === '0' ? 'success' : 'danger'">
                    {{ String(scope.row.status) === '0' ? '成功' : '失败' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作时间" width="170">
                <template #default="scope">{{ formatDateTime(scope.row.operTime) }}</template>
              </el-table-column>
              <el-table-column label="耗时" width="100">
                <template #default="scope">{{ scope.row.costTime != null ? scope.row.costTime + ' ms' : '-' }}</template>
              </el-table-column>
              <template #empty>暂无系统操作日志</template>
            </el-table>

            <pagination
              v-show="operTotal > 0"
              :total="operTotal"
              v-model:page="operQuery.pageNum"
              v-model:limit="operQuery.pageSize"
              @pagination="loadOperations"
            />
          </article>
        </div>

        <!-- 3. 登录日志 -->
        <div v-show="activeTab === 'logins'" class="tab-pane">
          <article class="panel">
            <el-form :model="loginQuery" inline label-width="88px" class="query-form">
              <el-form-item label="登录状态">
                <el-select v-model="loginQuery.status" placeholder="全部" clearable>
                  <el-option label="成功" value="0" />
                  <el-option label="失败" value="1" />
                </el-select>
              </el-form-item>
              <el-form-item label="登录时间">
                <el-date-picker
                  v-model="loginDateRange"
                  type="daterange"
                  value-format="YYYY-MM-DD"
                  range-separator="至"
                  start-placeholder="开始日期"
                  end-placeholder="结束日期"
                  :teleported="false"
                />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" @click="searchLogins">搜索</el-button>
                <el-button @click="resetLogins">重置</el-button>
              </el-form-item>
            </el-form>

            <el-table v-loading="loginLoading" :data="loginRecords">
              <el-table-column label="编号" prop="infoId" width="90" />
              <el-table-column label="登录名" prop="userName" width="130" />
              <el-table-column label="登录地址" prop="ipaddr" width="150" />
              <el-table-column label="登录地点" prop="loginLocation" min-width="140" show-overflow-tooltip />
              <el-table-column label="浏览器" prop="browser" min-width="130" show-overflow-tooltip />
              <el-table-column label="操作系统" prop="os" min-width="130" show-overflow-tooltip />
              <el-table-column label="状态" width="90">
                <template #default="scope">
                  <el-tag :type="String(scope.row.status) === '0' ? 'success' : 'danger'">
                    {{ String(scope.row.status) === '0' ? '成功' : '失败' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="描述" prop="msg" min-width="150" show-overflow-tooltip />
              <el-table-column label="访问时间" width="170">
                <template #default="scope">{{ formatDateTime(scope.row.loginTime) }}</template>
              </el-table-column>
              <template #empty>暂无登录日志</template>
            </el-table>

            <pagination
              v-show="loginTotal > 0"
              :total="loginTotal"
              v-model:page="loginQuery.pageNum"
              v-model:limit="loginQuery.pageSize"
              @pagination="loadLogins"
            />
          </article>
        </div>
      </main>
    </div>
  </section>
</template>

<script setup>
import { reactive, ref, watch } from 'vue'
import { Download, Key, User } from '@element-plus/icons-vue'
import { listMyKeyOperations, listMyLogins, listMyOperations } from '@/services/logs-api'
import useUserStore from '@/store/modules/user'
import { roleLevelText } from '@/utils/role'

const userStore = useUserStore()

const TABS = [
  { key: 'keys', label: '密钥操作', icon: Key },
  { key: 'operations', label: '操作日志', icon: Download },
  { key: 'logins', label: '登录日志', icon: User }
]

const activeTab = ref('keys')
const errorMessage = ref('')

const keyRecords = ref([])
const keyLoading = ref(false)
const keyTotal = ref(0)
const keyQuery = reactive({
  pageNum: 1,
  pageSize: 10,
  actionType: '',
  resultStatus: ''
})

const operRecords = ref([])
const operLoading = ref(false)
const operTotal = ref(0)
const operQuery = reactive({
  pageNum: 1,
  pageSize: 10,
  title: '',
  status: ''
})
const operDateRange = ref([])

const loginRecords = ref([])
const loginLoading = ref(false)
const loginTotal = ref(0)
const loginQuery = reactive({
  pageNum: 1,
  pageSize: 10,
  status: ''
})
const loginDateRange = ref([])

// 未登录时不发请求：这三个接口都要令牌，空跑只会刷出一片 401。
watch(
  () => userStore.token,
  (token) => {
    if (token) {
      reloadCurrentTab()
    } else {
      keyRecords.value = []
      operRecords.value = []
      loginRecords.value = []
    }
  },
  { immediate: true }
)

// 有令牌时 watch(immediate) 已完成首次加载，无需再在 onMounted 里重复拉取。

/**
 * RuoYi 的日期区间参数以 `params[beginTime]` / `params[endTime]` 形式提交，
 * 由 BaseEntity.params 接收。空区间直接不传，避免出现恒假的过滤条件。
 */
function withDateRange(query, range) {
  const payload = { ...query }
  if (Array.isArray(range) && range.length === 2 && range[0] && range[1]) {
    payload['params[beginTime]'] = `${range[0]} 00:00:00`
    payload['params[endTime]'] = `${range[1]} 23:59:59`
  }
  return payload
}

async function loadKeyRecords() {
  errorMessage.value = ''
  keyLoading.value = true
  try {
    const data = await listMyKeyOperations(keyQuery)
    keyRecords.value = data.rows || []
    keyTotal.value = data.total ?? keyRecords.value.length
  } catch (error) {
    keyRecords.value = []
    keyTotal.value = 0
    errorMessage.value = error.message
  } finally {
    keyLoading.value = false
  }
}

async function loadOperations() {
  errorMessage.value = ''
  operLoading.value = true
  try {
    const data = await listMyOperations(withDateRange(operQuery, operDateRange.value))
    operRecords.value = data.rows || []
    operTotal.value = data.total ?? operRecords.value.length
  } catch (error) {
    operRecords.value = []
    operTotal.value = 0
    errorMessage.value = error.message
  } finally {
    operLoading.value = false
  }
}

async function loadLogins() {
  errorMessage.value = ''
  loginLoading.value = true
  try {
    const data = await listMyLogins(withDateRange(loginQuery, loginDateRange.value))
    loginRecords.value = data.rows || []
    loginTotal.value = data.total ?? loginRecords.value.length
  } catch (error) {
    loginRecords.value = []
    loginTotal.value = 0
    errorMessage.value = error.message
  } finally {
    loginLoading.value = false
  }
}

function reloadCurrentTab() {
  if (activeTab.value === 'keys') {
    return loadKeyRecords()
  }
  if (activeTab.value === 'operations') {
    return loadOperations()
  }
  return loadLogins()
}

function searchKeys() {
  keyQuery.pageNum = 1
  loadKeyRecords()
}

function resetKeys() {
  keyQuery.pageNum = 1
  keyQuery.pageSize = 10
  keyQuery.actionType = ''
  keyQuery.resultStatus = ''
  loadKeyRecords()
}

function searchOperations() {
  operQuery.pageNum = 1
  loadOperations()
}

function resetOperations() {
  operQuery.pageNum = 1
  operQuery.pageSize = 10
  operQuery.title = ''
  operQuery.status = ''
  operDateRange.value = []
  loadOperations()
}

function searchLogins() {
  loginQuery.pageNum = 1
  loadLogins()
}

function resetLogins() {
  loginQuery.pageNum = 1
  loginQuery.pageSize = 10
  loginQuery.status = ''
  loginDateRange.value = []
  loadLogins()
}

function roleText(level) {
  return roleLevelText(level)
}

function actionTypeText(value) {
  return { UPDATE: '密钥更新', REVOKE: 'KMS引用回收' }[value] || '-'
}

function actionSourceText(value) {
  return { MANUAL: '手动', AUTO: '自动' }[value] || '-'
}

function resultStatusText(value) {
  return { '0': '处理中', '1': '成功', '2': '失败' }[String(value)] || '-'
}

function resultStatusType(value) {
  return { '0': 'warning', '1': 'success', '2': 'danger' }[String(value)] || 'info'
}

function chainStatusText(status) {
  return { '0': '未上链', '1': '已上链', '2': '上链失败' }[String(status)] || '未知'
}

function chainStatusType(status) {
  return { '0': 'info', '1': 'success', '2': 'danger' }[String(status)] || 'info'
}

/** RuoYi 操作类型字典 sys_oper_type */
function businessTypeText(value) {
  return {
    0: '其它',
    1: '新增',
    2: '修改',
    3: '删除',
    4: '授权',
    5: '导出',
    6: '导入',
    7: '强退',
    8: '生成代码',
    9: '清空数据'
  }[Number(value)] || '其它'
}

function formatDateTime(value) {
  if (!value) {
    return '-'
  }
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return String(value)
  }
  return parsed.toLocaleString('zh-CN', { hour12: false })
}
</script>

<style scoped>
.header-actions {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.header-buttons {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.logs-dashboard {
  display: flex;
  gap: 20px;
  align-items: flex-start;
  margin-top: 16px;
}

.inner-sidenav {
  width: 190px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: var(--kms-surface-1);
  border: 1px solid var(--kms-border);
  border-radius: var(--kms-radius-md, 8px);
  padding: 10px;
}

.inner-sidenav .nav-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: var(--kms-radius-sm);
  color: var(--kms-text-secondary);
  cursor: pointer;
  transition: background 0.2s, color 0.2s;
}

.inner-sidenav .nav-item:hover {
  background: var(--kms-surface-2);
  color: var(--kms-text-primary);
}

.inner-sidenav .nav-item.active {
  background: var(--kms-brand-subtle, #e6f4ff);
  color: var(--kms-brand-text);
  font-weight: var(--kms-font-weight-medium, 500);
}

.inner-main-content {
  flex-grow: 1;
  min-width: 0;
}

.query-form {
  margin-bottom: 8px;
}

.error-text {
  color: var(--kms-danger-strong);
  font-size: var(--kms-font-size-sm, 13px);
  margin: 0 0 8px;
}

@media (max-width: 960px) {
  .logs-dashboard {
    flex-direction: column;
  }

  .inner-sidenav {
    width: 100%;
    flex-direction: row;
    flex-wrap: wrap;
  }
}
</style>
