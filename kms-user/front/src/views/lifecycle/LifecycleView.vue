<template>
  <section class="page lifecycle-page">

    <article class="panel">
      <div class="panel-head header-actions">
        <div>
          <h3>当前用户</h3>
        </div>
        <el-button @click="reloadCurrentTab">刷新当前页</el-button>
      </div>
      <div class="form-grid profile-grid">
        <label>
          <span>用户 ID</span>
          <input :value="profile.userId" type="text" disabled />
        </label>
        <label>
          <span>用户名</span>
          <input :value="profile.userName" type="text" disabled />
        </label>
        <label>
          <span>当前等级</span>
          <input :value="roleText(profile.roleLevel)" type="text" disabled />
        </label>
      </div>
    </article>

    <div class="lifecycle-dashboard">
      <nav class="inner-sidenav">
        <div class="nav-item" :class="{ active: activeTab === 'mykeys' }" @click="activeTab = 'mykeys'">
          <span class="icon">🔑</span> 我的密钥库
        </div>
        <div class="nav-item" :class="{ active: activeTab === 'autoupdate' }" @click="activeTab = 'autoupdate'">
          <span class="icon">⚡</span> 自动更新配置
        </div>
        <div class="nav-item" :class="{ active: activeTab === 'results' }" @click="activeTab = 'results'">
          <span class="icon">📥</span> 操作结果回执
        </div>
      </nav>

      <main class="inner-main-content">
        <!-- Floating Action Bar -->
        <transition name="fade-slide">
          <div v-if="activeTab === 'mykeys' && selectedIds.length > 0" class="floating-action-bar">
            <span class="selection-count">已选择 {{ selectedIds.length }} 项</span>
            <div class="fab-actions">
              <el-button type="success" :disabled="selectedIds.length !== 1" @click="openUpdateDialog()">操作更新</el-button>
              <el-button type="danger" @click="handleRevoke()">一键回收</el-button>
            </div>
          </div>
        </transition>

        <div v-show="activeTab === 'mykeys'" class="tab-pane relative-pane">
          <article class="panel glass-panel">
          <el-form :model="myKeyQuery" inline label-width="88px" class="query-form">
            <el-form-item label="密钥名称">
              <el-input v-model="myKeyQuery.keyName" placeholder="请输入密钥名称" clearable @keyup.enter="searchMyKeys" />
            </el-form-item>
            <el-form-item label="算法名称">
              <el-input v-model="myKeyQuery.encrytName" placeholder="请输入算法名称" clearable @keyup.enter="searchMyKeys" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="searchMyKeys">搜索</el-button>
              <el-button @click="resetMyKeys">重置</el-button>
            </el-form-item>
          </el-form>

          <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>

          <el-table v-loading="myKeysLoading" :data="myKeys" @selection-change="handleSelectionChange">
            <el-table-column type="selection" width="55" align="center" />
            <el-table-column label="密钥 ID" align="center" prop="keyId" width="90" />
            <el-table-column label="用户名" align="center" prop="userName" width="120" />
            <el-table-column label="算法类型" align="center" prop="encrytType" min-width="140" />
            <el-table-column label="算法名称" align="center" prop="encrytName" width="120" />
            <el-table-column label="密钥名称" align="center" prop="keyName" min-width="150" />
            <el-table-column label="密钥用途" align="center" prop="keyUse" min-width="150" show-overflow-tooltip />
            <el-table-column label="自动更新" align="center" width="110">
              <template #default="scope">
                <el-tag :type="isAutoUpdateEnabled(scope.row.autoUpdate) ? 'success' : 'info'">
                  {{ autoUpdateText(scope.row.autoUpdate) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" align="center" width="110">
              <template #default="scope">
                <el-tag :type="statusTagType(scope.row.status)">{{ statusText(scope.row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="上链状态" align="center" width="110">
              <template #default="scope">
                <el-tag :type="chainStatusType(scope.row.chainStatus)">{{ chainStatusText(scope.row.chainStatus) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="更新时间" align="center" prop="updTime" width="180" />
            <el-table-column label="操作" align="center" width="220" fixed="right">
              <template #default="scope">
                <el-button link type="primary" :disabled="isRevoked(scope.row.status)" @click="openUpdateDialog(scope.row)">
                  更新
                </el-button>
                <el-button link type="danger" :disabled="isRevoked(scope.row.status)" @click="handleRevoke(scope.row)">
                  回收
                </el-button>
                <el-button link type="warning" @click="openAnalysisDialog(scope.row)">安全分析</el-button>
                <el-button link @click="showDetail(scope.row.keyId)">详情</el-button>
              </template>
            </el-table-column>
          </el-table>

          <pagination
            v-show="myKeyTotal > 0"
            :total="myKeyTotal"
            v-model:page="myKeyQuery.pageNum"
            v-model:limit="myKeyQuery.pageSize"
            @pagination="loadMyKeys"
          />
        </article>
        </div>

        <div v-show="activeTab === 'autoupdate'" class="tab-pane relative-pane">
          <el-alert
            v-if="!canManageAutoUpdate"
            title="当前账号没有生命周期域自动更新配置的权限，请先到权限管理页申请临时权限。"
            type="warning"
            :closable="false"
            show-icon
            class="mb12"
          >
            <template #default>
              <el-button type="primary" link @click="router.push('/permissions/index')">前往申请权限</el-button>
            </template>
          </el-alert>

          <el-alert
            v-if="showAutoUpdateRollback"
            title="当前自动更新配置权限为临时权限，完成配置后建议立即回退。"
            type="info"
            :closable="false"
            show-icon
            class="mb12"
          >
            <template #default>
              <el-button type="primary" link @click="handleRollback">回退权限</el-button>
            </template>
          </el-alert>

          <article class="panel glass-panel">
          <el-form :model="autoUpdateQuery" inline label-width="88px" class="query-form">
            <el-form-item label="密钥名称">
              <el-input v-model="autoUpdateQuery.keyName" placeholder="请输入密钥名称" clearable @keyup.enter="searchAutoUpdate" />
            </el-form-item>
            <el-form-item label="自动更新">
              <el-select v-model="autoUpdateQuery.autoUpdate" placeholder="全部" clearable>
                <el-option label="已开启" value="1" />
                <el-option label="已关闭" value="0" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :disabled="!canManageAutoUpdate" @click="searchAutoUpdate">搜索</el-button>
              <el-button :disabled="!canManageAutoUpdate" @click="resetAutoUpdate">重置</el-button>
            </el-form-item>
          </el-form>

          <el-table v-loading="autoUpdateLoading" :data="autoUpdateKeys">
            <el-table-column label="密钥 ID" align="center" prop="keyId" width="90" />
            <el-table-column label="用户名" align="center" prop="userName" width="120" />
            <el-table-column label="算法类型" align="center" prop="encrytType" min-width="140" />
            <el-table-column label="密钥名称" align="center" prop="keyName" min-width="150" />
            <el-table-column label="状态" align="center" width="110">
              <template #default="scope">
                <el-tag :type="statusTagType(scope.row.status)">{{ statusText(scope.row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="自动更新状态" align="center" width="120">
              <template #default="scope">
                <el-tag :type="isAutoUpdateEnabled(scope.row.autoUpdate) ? 'success' : 'info'">
                  {{ autoUpdateText(scope.row.autoUpdate) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="更新时间" align="center" prop="updTime" width="180" />
            <el-table-column label="操作" align="center" width="160" fixed="right">
              <template #default="scope">
                <el-button
                  link
                  type="primary"
                  :disabled="isRevoked(scope.row.status)"
                  @click="toggleAutoUpdate(scope.row)"
                >
                  {{ isAutoUpdateEnabled(scope.row.autoUpdate) ? '关闭' : '开启' }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <pagination
            v-show="autoUpdateTotal > 0"
            :total="autoUpdateTotal"
            v-model:page="autoUpdateQuery.pageNum"
            v-model:limit="autoUpdateQuery.pageSize"
            @pagination="loadAutoUpdateKeys"
          />
        </article>
        </div>

        <div v-show="activeTab === 'results'" class="tab-pane relative-pane">
          <article class="panel glass-panel">
          <el-form :model="resultQuery" inline label-width="88px" class="query-form">
            <el-form-item label="操作类型">
              <el-select v-model="resultQuery.actionType" placeholder="全部" clearable>
                <el-option label="密钥更新" value="UPDATE" />
                <el-option label="密钥回收" value="REVOKE" />
              </el-select>
            </el-form-item>
            <el-form-item label="接收状态">
              <el-select v-model="resultQuery.receiveStatus" placeholder="全部" clearable>
                <el-option label="待接收" value="0" />
                <el-option label="已接收" value="1" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="searchResults">搜索</el-button>
              <el-button @click="resetResults">重置</el-button>
            </el-form-item>
          </el-form>

          <el-table v-loading="resultLoading" :data="resultList">
            <el-table-column label="记录ID" prop="recordId" width="90" />
            <el-table-column label="密钥ID" prop="keyId" width="90" />
            <el-table-column label="密钥名称" prop="keyName" min-width="140" />
            <el-table-column label="操作类型" width="110">
              <template #default="scope">{{ actionTypeText(scope.row.actionType) }}</template>
            </el-table-column>
            <el-table-column label="来源" width="110">
              <template #default="scope">{{ actionSourceText(scope.row.actionSource) }}</template>
            </el-table-column>
            <el-table-column label="结果" width="100">
              <template #default="scope">
                <el-tag :type="resultStatusType(scope.row.resultStatus)">{{ resultStatusText(scope.row.resultStatus) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="接收状态" width="110">
              <template #default="scope">
                <el-tag :type="scope.row.receiveStatus === '1' ? 'success' : 'warning'">{{ scope.row.receiveStatus === '1' ? '已接收' : '待接收' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="结果说明" prop="resultMessage" min-width="160" show-overflow-tooltip />
            <el-table-column label="操作时间" width="180">
              <template #default="scope">{{ formatDateTime(scope.row.actionTime) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="150" fixed="right">
              <template #default="scope">
                <el-button link @click="showDetail(scope.row.keyId)">详情</el-button>
                <el-button
                  v-if="scope.row.receiveStatus !== '1' && scope.row.resultStatus !== '0'"
                  link
                  type="primary"
                  @click="receiveResult(scope.row)"
                >接收</el-button>
              </template>
            </el-table-column>
          </el-table>

          <pagination
            v-show="resultTotal > 0"
            :total="resultTotal"
            v-model:page="resultQuery.pageNum"
            v-model:limit="resultQuery.pageSize"
            @pagination="loadResultList"
          />
        </article>
        </div>
      </main>
    </div>

    <el-dialog v-model="updateDialogOpen" title="密钥更新" width="520px" append-to-body>
      <el-form ref="updateFormRef" :model="updateForm" :rules="updateRules" label-width="96px">
        <el-form-item label="密钥 ID">
          <el-input :model-value="String(updateForm.keyId || '')" disabled />
        </el-form-item>
        <el-form-item label="算法类型">
          <el-input v-model="updateForm.encrytType" disabled />
        </el-form-item>
        <el-form-item label="算法名称">
          <el-input v-model="updateForm.encrytName" disabled />
        </el-form-item>
        <el-form-item label="密钥名称" prop="keyName">
          <el-input v-model="updateForm.keyName" maxlength="64" show-word-limit />
        </el-form-item>
        <el-form-item label="密钥用途" prop="keyUse">
          <el-input v-model="updateForm.keyUse" maxlength="128" show-word-limit />
        </el-form-item>
        <el-form-item label="所属域" prop="keyDomain">
          <el-input v-model="updateForm.keyDomain" maxlength="64" clearable />
        </el-form-item>
        <el-form-item label="自动更新">
          <el-switch v-model="updateForm.autoUpdateEnabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="updateDialogOpen = false">取消</el-button>
        <el-button type="primary" :loading="updateSubmitting" @click="submitUpdate">确认更新</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="detailDialogOpen" title="密钥详情" width="720px" append-to-body>
      <div v-if="selectedKey" class="detail-grid">
        <p><strong>密钥 ID：</strong>{{ selectedKey.keyId }}</p>
        <p><strong>用户 ID：</strong>{{ selectedKey.userId }}</p>
        <p><strong>用户名：</strong>{{ selectedKey.userName || '-' }}</p>
        <p><strong>算法类型：</strong>{{ selectedKey.encrytType || '-' }}</p>
        <p><strong>算法名称：</strong>{{ selectedKey.encrytName || '-' }}</p>
        <p><strong>密钥名称：</strong>{{ selectedKey.keyName || '-' }}</p>
        <p><strong>密钥用途：</strong>{{ selectedKey.keyUse || '-' }}</p>
        <p><strong>所属域：</strong>{{ selectedKey.keyDomain || '-' }}</p>
        <p><strong>自动更新：</strong>{{ autoUpdateText(selectedKey.autoUpdate) }}</p>
        <p><strong>状态：</strong>{{ statusText(selectedKey.status) }}</p>
        <p><strong>版本：</strong>{{ selectedKey.version ?? '-' }}</p>
        <p><strong>上链状态：</strong>{{ chainStatusText(selectedKey.chainStatus) }}</p>
        <p><strong>交易哈希：</strong>{{ selectedKey.chainHash || '-' }}</p>
        <p><strong>创建时间：</strong>{{ selectedKey.creTime || '-' }}</p>
        <p><strong>更新时间：</strong>{{ selectedKey.updTime || '-' }}</p>
      </div>
    </el-dialog>

    <el-drawer v-model="analysisDrawerOpen" title="密钥防线全息扫描结果" size="65%">
      <div v-if="analysisLoading" class="analysis-loading" style="text-align: center; padding: 40px;">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <p>正在拉取源端底层数据，请稍候...</p>
      </div>
      <div v-else-if="analysisResult" class="analysis-content">
        <h3 style="margin-top:0;">1. 嫌疑面报表 (Base Info)</h3>
        <el-descriptions border :column="2" style="margin-bottom: 20px;">
          <el-descriptions-item label="密钥ID">{{ analysisResult.baseInfo?.keyId }}</el-descriptions-item>
          <el-descriptions-item label="密钥名称">{{ analysisResult.baseInfo?.keyName }}</el-descriptions-item>
          <el-descriptions-item label="算法">{{ analysisResult.baseInfo?.encrytName }}</el-descriptions-item>
          <el-descriptions-item label="使用域">{{ analysisResult.baseInfo?.keyDomain }}</el-descriptions-item>
          <el-descriptions-item label="版本号">{{ analysisResult.baseInfo?.version }}</el-descriptions-item>
          <el-descriptions-item label="安全状态">
            <el-tag :type="statusTagType(analysisResult.baseInfo?.status)">{{ statusText(analysisResult.baseInfo?.status) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="链上哈希证实" :span="2">{{ analysisResult.baseInfo?.chainHash || '尚未存证' }}</el-descriptions-item>
        </el-descriptions>

        <h3>2. 历史分发存留溯源 (Distribute Footprints)</h3>
        <el-table :data="analysisResult.distributeFootprints" border stripe style="width: 100%; margin-bottom: 20px;" max-height="250">
          <el-table-column prop="user_name" label="下发终端实体"></el-table-column>
          <el-table-column label="分发类型">
             <template #default="scope">
                <el-tag v-if="scope.row.distribute_type == '1'" type="info">初始分发</el-tag>
                <el-tag v-else-if="scope.row.distribute_type == '2'" type="warning">自动更新分发</el-tag>
                <el-tag v-else type="danger">补发</el-tag>
             </template>
          </el-table-column>
          <el-table-column prop="distribute_time" label="下达时间"></el-table-column>
          <el-table-column label="缓存状态" width="120">
             <template #default="scope">
                <el-tag v-if="scope.row.distribute_status == '2'" type="danger">该节点持有缓存!</el-tag>
                <el-tag v-else type="success">未接收成功</el-tag>
             </template>
          </el-table-column>
        </el-table>

        <h3>3. 异常操作轨迹盘点 (Timeline Trails)</h3>
        <el-timeline style="padding-left: 10px;">
          <el-timeline-item
            v-for="(op, index) in analysisResult.operationTrails"
            :key="index"
            :timestamp="op.action_time ? formatDateTime(op.action_time) : '-'"
            :type="op.action_type === 'REVOKE' ? 'danger' : 'primary'"
            :color="op.result_status == '1' ? '#0bbd87' : '#e4e7ed'"
          >
            <strong>{{ actionTypeText(op.action_type) }}</strong> 
            操作来源: [{{ op.action_source }}]
          </el-timeline-item>
          <el-timeline-item v-if="!analysisResult.operationTrails?.length" timestamp="暂无记录">
            该密钥暂无操作流转痕迹
          </el-timeline-item>
        </el-timeline>
      </div>
    </el-drawer>
  </section>
</template>

<script setup>
import { computed, getCurrentInstance, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { getLatestApprovedTemporaryRequest, rollbackPermission } from '@/services/permission-api'
import {
  getLifecycleKey,
  getLifecycleKeyAnalysis,
  listLifecycleKeys,
  listLifecycleOperationRecords,
  receiveLifecycleOperationRecord,
  revokeLifecycleKey,
  updateLifecycleAutoUpdate,
  updateLifecycleKey
} from '@/services/lifecycle-api'
import { apiBases } from '@/config/api-bases'
import useUserStore from '@/store/modules/user'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'

const { proxy } = getCurrentInstance()
const router = useRouter()
const userStore = useUserStore()

const apiBase = apiBases.lifecycleApi
const activeTab = ref('mykeys')
const errorMessage = ref('')

const analysisDrawerOpen = ref(false)
const analysisLoading = ref(false)
const analysisResult = ref(null)

async function openAnalysisDialog(row) {
  const keyId = row?.keyId || selectedIds.value[0]
  if (!keyId) {
    proxy.$modal.msgWarning('请先选择一条密钥记录')
    return
  }
  analysisDrawerOpen.value = true
  analysisLoading.value = true
  analysisResult.value = null
  try {
    const res = await getLifecycleKeyAnalysis(keyId)
    if (res.code === 200 || res.code === '200' || res.data) {
      analysisResult.value = res.data || res.baseInfo ? (res.data || res) : null
    } else {
      ElMessage.error(res.msg || '获取关联分析失败')
    }
  } catch (err) {
    ElMessage.error(err.message || '网络请求失败')
  } finally {
    analysisLoading.value = false
  }
}

const profile = reactive({
  userId: '',
  userName: '',
  roleLevel: 2
})

const myKeys = ref([])
const myKeysLoading = ref(false)
const myKeyTotal = ref(0)
const selectedIds = ref([])

const myKeyQuery = reactive({
  pageNum: 1,
  pageSize: 10,
  userId: '',
  keyName: '',
  encrytName: ''
})

const autoUpdateKeys = ref([])
const autoUpdateLoading = ref(false)
const autoUpdateTotal = ref(0)
const autoUpdateQuery = reactive({
  pageNum: 1,
  pageSize: 10,
  userId: '',
  keyName: '',
  autoUpdate: ''
})

const updateDialogOpen = ref(false)
const updateSubmitting = ref(false)
const updateFormRef = ref(null)
const updateForm = reactive({
  keyId: null,
  encrytType: '',
  encrytName: '',
  keyName: '',
  keyUse: '',
  keyDomain: '',
  autoUpdateEnabled: false
})
const updateRules = {
  keyName: [{ required: true, message: '请输入密钥名称', trigger: 'blur' }],
  keyUse: [{ required: true, message: '请输入密钥用途', trigger: 'blur' }]
}

const selectedKey = ref(null)
const detailDialogOpen = ref(false)
const approvedAutoUpdateRequestId = ref(null)
const resultList = ref([])
const resultLoading = ref(false)
const resultTotal = ref(0)

const resultQuery = reactive({
  pageNum: 1,
  pageSize: 10,
  actionType: '',
  receiveStatus: ''
})

const hasPermanentAutoUpdateAccess = computed(() => Number(profile.roleLevel) <= 0)
const hasTemporaryAutoUpdateAccess = computed(() => Boolean(approvedAutoUpdateRequestId.value))
const canManageAutoUpdate = computed(() => hasPermanentAutoUpdateAccess.value || hasTemporaryAutoUpdateAccess.value)
const showAutoUpdateRollback = computed(() => hasTemporaryAutoUpdateAccess.value)

watch(
  () => ({
    id: userStore.id,
    name: userStore.name,
    roleLevel: userStore.roleLevel,
    token: userStore.token
  }),
  (value) => {
    profile.userId = value.id || ''
    profile.userName = value.name || ''
    profile.roleLevel = value.roleLevel ?? 2
    myKeyQuery.userId = value.id || ''
    autoUpdateQuery.userId = value.id || ''

    if (!value.token) {
      approvedAutoUpdateRequestId.value = null
      myKeys.value = []
      autoUpdateKeys.value = []
      selectedIds.value = []
    }
  },
  { immediate: true }
)

watch(activeTab, async (tab) => {
  if (tab === 'autoupdate') {
    await loadAutoUpdateKeys()
    await loadAutoUpdatePermissionState()
  }
  if (tab === 'results') {
    await loadResultList()
  }
})

onMounted(async () => {
  await ensureProfile()
  await loadMyKeys()
  if (activeTab.value === 'autoupdate') {
    await loadAutoUpdateKeys()
  }
  if (activeTab.value === 'results') {
    await loadResultList()
  }
})

async function ensureProfile() {
  if (!userStore.token) {
    return
  }
  if (!profile.userId || !profile.userName) {
    try {
      await userStore.getInfo()
    } catch (error) {
      errorMessage.value = error.message
    }
  }
}

async function loadMyKeys() {
  errorMessage.value = ''
  if (!myKeyQuery.userId) {
    await ensureProfile()
  }
  if (!myKeyQuery.userId) {
    myKeys.value = []
    myKeyTotal.value = 0
    return
  }

  myKeysLoading.value = true
  try {
    const response = await listLifecycleKeys(myKeyQuery)
    myKeys.value = response.rows || []
    myKeyTotal.value = response.total ?? myKeys.value.length
    selectedIds.value = []
  } catch (error) {
    errorMessage.value = error.message
    myKeys.value = []
    myKeyTotal.value = 0
  } finally {
    myKeysLoading.value = false
  }
}

async function loadAutoUpdateKeys() {
  errorMessage.value = ''
  if (!autoUpdateQuery.userId) {
    await ensureProfile()
  }
  if (!autoUpdateQuery.userId) {
    autoUpdateKeys.value = []
    autoUpdateTotal.value = 0
    return
  }

  autoUpdateLoading.value = true
  try {
    const response = await listLifecycleKeys(autoUpdateQuery)
    autoUpdateKeys.value = response.rows || []
    autoUpdateTotal.value = response.total ?? autoUpdateKeys.value.length
  } catch (error) {
    errorMessage.value = error.message
    autoUpdateKeys.value = []
    autoUpdateTotal.value = 0
  } finally {
    autoUpdateLoading.value = false
  }
}

async function loadAutoUpdatePermissionState() {
  approvedAutoUpdateRequestId.value = null
  if (!profile.userId || !userStore.token) {
    return
  }

  try {
    const approved = await getLatestApprovedTemporaryRequest('AUTO_UPDATE', Number(profile.userId))
    approvedAutoUpdateRequestId.value = approved?.requestId || null
  } catch (error) {
    errorMessage.value = error.message
  }
}

function handleSelectionChange(selection) {
  selectedIds.value = selection.map((item) => item.keyId)
}

function searchMyKeys() {
  myKeyQuery.pageNum = 1
  loadMyKeys()
}

function resetMyKeys() {
  myKeyQuery.pageNum = 1
  myKeyQuery.pageSize = 10
  myKeyQuery.keyName = ''
  myKeyQuery.encrytName = ''
  loadMyKeys()
}

function searchAutoUpdate() {
  autoUpdateQuery.pageNum = 1
  loadAutoUpdateKeys()
}

function resetAutoUpdate() {
  autoUpdateQuery.pageNum = 1
  autoUpdateQuery.pageSize = 10
  autoUpdateQuery.keyName = ''
  autoUpdateQuery.autoUpdate = ''
  loadAutoUpdateKeys()
}

function reloadCurrentTab() {
  if (activeTab.value === 'results') {
    loadResultList()
    return
  }
  if (activeTab.value === 'autoupdate') {
    loadAutoUpdateKeys()
    loadAutoUpdatePermissionState()
    return
  }
  loadMyKeys()
}

async function loadResultList() {
  errorMessage.value = ''
  resultLoading.value = true
  try {
    const response = await listLifecycleOperationRecords(resultQuery)
    resultList.value = response.rows || []
    resultTotal.value = response.total ?? resultList.value.length
  } catch (error) {
    errorMessage.value = error.message
    resultList.value = []
    resultTotal.value = 0
  } finally {
    resultLoading.value = false
  }
}

function searchResults() {
  resultQuery.pageNum = 1
  loadResultList()
}

function resetResults() {
  resultQuery.pageNum = 1
  resultQuery.pageSize = 10
  resultQuery.actionType = ''
  resultQuery.receiveStatus = ''
  loadResultList()
}

async function openUpdateDialog(row) {
  errorMessage.value = ''
  const keyId = row?.keyId || selectedIds.value[0]
  if (!keyId) {
    proxy.$modal.msgWarning('请先选择一条密钥记录')
    return
  }

  try {
    const response = await getLifecycleKey(keyId)
    const record = response.data
    if (!record) {
      proxy.$modal.msgWarning('未找到对应密钥')
      return
    }
    if (isRevoked(record.status)) {
      proxy.$modal.msgWarning('已回收密钥不允许更新')
      return
    }

    updateForm.keyId = record.keyId
    updateForm.encrytType = record.encrytType || ''
    updateForm.encrytName = record.encrytName || ''
    updateForm.keyName = record.keyName || ''
    updateForm.keyUse = record.keyUse || ''
    updateForm.keyDomain = record.keyDomain || ''
    updateForm.autoUpdateEnabled = isAutoUpdateEnabled(record.autoUpdate)
    updateDialogOpen.value = true
  } catch (error) {
    errorMessage.value = error.message
  }
}

async function submitUpdate() {
  if (!updateFormRef.value) {
    return
  }

  try {
    await updateFormRef.value.validate()
  } catch {
    return
  }

  updateSubmitting.value = true
  errorMessage.value = ''
  try {
    await updateLifecycleKey({
      keyId: updateForm.keyId,
      keyName: normalizeText(updateForm.keyName),
      keyUse: normalizeText(updateForm.keyUse),
      keyDomain: normalizeText(updateForm.keyDomain),
      autoUpdate: updateForm.autoUpdateEnabled ? '1' : '0'
    })
    proxy.$modal.msgSuccess('密钥更新成功')
    updateDialogOpen.value = false
    await loadMyKeys()
    if (activeTab.value === 'autoupdate') {
      await loadAutoUpdateKeys()
    }
  } catch (error) {
    errorMessage.value = error.message
  } finally {
    updateSubmitting.value = false
  }
}

function handleRevoke(row) {
  const ids = row?.keyId ? [row.keyId] : [...selectedIds.value]
  if (!ids.length) {
    proxy.$modal.msgWarning('请先选择需要回收的密钥')
    return
  }

  const revokedIds = ids.filter((keyId) => {
    const record = myKeys.value.find((item) => item.keyId === keyId)
    return record && isRevoked(record.status)
  })
  if (revokedIds.length) {
    proxy.$modal.msgWarning(`密钥 ${revokedIds.join(', ')} 已回收，无需重复操作`)
    return
  }

  proxy.$modal.confirm(`是否确认回收密钥编号为 "${ids.join(', ')}" 的记录？`).then(async () => {
    errorMessage.value = ''
    try {
      for (const keyId of ids) {
        await revokeLifecycleKey(keyId)
      }
      proxy.$modal.msgSuccess('密钥回收成功')
      await loadMyKeys()
      await loadAutoUpdateKeys()
      await loadResultList()
    } catch (error) {
      errorMessage.value = error.message
    }
  }).catch(() => {})
}

function toggleAutoUpdate(row) {
  if (isRevoked(row.status)) {
    ElMessage.warning('该密钥已回收，不可开启自动更新')
    return
  }

  const nextValue = isAutoUpdateEnabled(row.autoUpdate) ? '0' : '1'
  const actionText = nextValue === '1' ? '启用' : '禁用'
  proxy.$modal.confirm(`确认${actionText}密钥 "${row.keyName}" 的自动更新功能？`).then(async () => {
    errorMessage.value = ''
    try {
      await updateLifecycleAutoUpdate({ keyId: row.keyId, autoUpdate: nextValue })
      proxy.$modal.msgSuccess(`已${actionText}自动更新`)
      await loadAutoUpdateKeys()
      await loadMyKeys()
    } catch (error) {
      errorMessage.value = error.message
    }
  }).catch(() => {})
}

async function showDetail(keyId) {
  errorMessage.value = ''
  try {
    const response = await getLifecycleKey(keyId)
    selectedKey.value = response.data || null
    detailDialogOpen.value = Boolean(selectedKey.value)
  } catch (error) {
    errorMessage.value = error.message
  }
}

function receiveResult(row) {
  proxy.$modal.confirm(`确认接收密钥 ${row.keyName || row.keyId} 的${actionTypeText(row.actionType)}结果？`).then(async () => {
    errorMessage.value = ''
    try {
      await receiveLifecycleOperationRecord(row.recordId)
      proxy.$modal.msgSuccess('结果已接收')
      await loadResultList()
      await loadMyKeys()
      await loadAutoUpdateKeys()
    } catch (error) {
      errorMessage.value = error.message
    }
  }).catch(() => {})
}

function handleRollback() {
  if (!approvedAutoUpdateRequestId.value) {
    proxy.$modal.msgWarning('没有可回退的临时权限')
    return
  }

  proxy.$modal.confirm('确认回退自动更新临时权限？').then(async () => {
    errorMessage.value = ''
    try {
      await rollbackPermission('AUTO_UPDATE', approvedAutoUpdateRequestId.value)
      proxy.$modal.msgSuccess('权限已回退成功')
      approvedAutoUpdateRequestId.value = null
      await userStore.getInfo()
      await loadAutoUpdatePermissionState()
    } catch (error) {
      errorMessage.value = error.message
    }
  }).catch(() => {})
}

function normalizeText(value) {
  const text = value == null ? '' : String(value).trim()
  return text === '' ? null : text
}

function isAutoUpdateEnabled(value) {
  return value === 1 || value === '1' || value === true || value === 'true'
}

function isRevoked(status) {
  return status === '3' || status === 3 || status === 'Revoked' || status === 'REVOKED'
}

function autoUpdateText(value) {
  return isAutoUpdateEnabled(value) ? '已开启' : '已关闭'
}

function chainStatusText(status) {
  return { '0': '待上链', '1': '已上链', '2': '上链失败' }[String(status)] || '-'
}

function chainStatusType(status) {
  return { '0': 'warning', '1': 'success', '2': 'danger' }[String(status)] || 'info'
}

function actionTypeText(value) {
  return { UPDATE: '密钥更新', REVOKE: '密钥回收' }[value] || '-'
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

function formatDateTime(value) {
  return value ? new Date(value).toLocaleString() : '-'
}

function statusText(status) {
  const normalized = status == null ? '' : String(status)
  return {
    '0': '有效',
    '1': '已冻结',
    '2': '已更新',
    '3': '已回收',
    Valid: '有效',
    Active: '有效',
    ACTIVE: '有效',
    Frozen: '已冻结',
    FROZEN: '已冻结',
    Replaced: '已更新',
    Rotated: '已更新',
    ROTATED: '已更新',
    Revoked: '已回收',
    REVOKED: '已回收'
  }[normalized] || (status == null ? '-' : String(status))
}

function statusTagType(status) {
  const normalized = status == null ? '' : String(status)
  if (isRevoked(normalized)) {
    return 'danger'
  }
  if (['1', '2', 'Frozen', 'FROZEN', 'Replaced', 'Rotated', 'ROTATED'].includes(normalized)) {
    return 'warning'
  }
  if (['0', 'Valid', 'Active', 'ACTIVE'].includes(normalized)) {
    return 'success'
  }
  return 'info'
}

function roleText(level) {
  return { 0: '管理员', 1: '中级用户', 2: '普通用户' }[level] || '未知'
}
</script>

<style scoped>
.lifecycle-page {
  animation: fade-in 0.5s ease;
}

.lifecycle-page .mb12 {
  margin-bottom: 12px;
}

.header-actions {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.profile-grid,
.quick-actions {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.quick-actions {
  align-items: center;
  padding: 8px 0;
}

.query-form {
  margin-bottom: 16px;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 16px 24px;
}

@media (max-width: 768px) {
  .profile-grid,
  .quick-actions {
    flex-direction: column;
    align-items: stretch;
  }
}

.lifecycle-dashboard {
  display: flex;
  gap: 24px;
  align-items: flex-start;
  margin-top: 20px;
}
.inner-sidenav {
  width: 220px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: rgba(255, 255, 255, 0.02);
  backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  padding: 12px;
}
.inner-sidenav .nav-item {
  padding: 12px 16px;
  border-radius: 10px;
  cursor: pointer;
  color: rgba(255, 255, 255, 0.7);
  transition: all 0.3s;
  display: flex;
  align-items: center;
  gap: 12px;
  font-weight: 500;
}
.inner-sidenav .nav-item:hover {
  background: rgba(255, 255, 255, 0.05);
  color: #fff;
}
.inner-sidenav .nav-item.active {
  background: rgba(0, 153, 255, 0.2);
  color: #00e5ff;
  border: 1px solid rgba(0, 153, 255, 0.3);
  box-shadow: 0 4px 12px rgba(0, 153, 255, 0.1);
}
.nav-link {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  text-align: center;
}
.inner-main-content {
  flex-grow: 1;
  min-width: 0;
  position: relative;
}
.tab-pane {
  animation: fade-in 0.3s ease-out;
}
.floating-action-bar {
  position: absolute;
  top: 10px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 100;
  background: rgba(20, 25, 35, 0.85);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(0, 229, 255, 0.3);
  padding: 12px 24px;
  border-radius: 30px;
  display: flex;
  align-items: center;
  gap: 20px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4), 0 0 16px rgba(0, 153, 255, 0.2);
}
.selection-count {
  color: #00e5ff;
  font-weight: bold;
}
.fab-actions {
  display: flex;
  gap: 8px;
}
.fade-slide-enter-active, .fade-slide-leave-active {
  transition: opacity 0.3s, transform 0.3s;
}
.fade-slide-enter-from, .fade-slide-leave-to {
  opacity: 0;
  transform: translate(-50%, -20px);
}
@media (max-width: 960px) {
  .lifecycle-dashboard {
    flex-direction: column;
  }
  .inner-sidenav {
    width: 100%;
    flex-direction: row;
    overflow-x: auto;
  }
}
</style>
