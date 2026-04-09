<template>
  <section class="page lifecycle-page">
    <div class="page-header">
      <p class="eyebrow">Updatedel</p>
      <h2>动态更新与回收</h2>
      <p>恢复更新与回收主工作流，集中处理我的密钥、密钥轮换、逻辑回收与自动更新配置。</p>
    </div>

    <article class="panel">
      <div class="panel-head header-actions">
        <div>
          <h3>当前用户</h3>
          <p class="muted">API 前缀：<code>{{ apiBase }}</code></p>
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

    <article class="panel">
      <div class="quick-actions">
        <el-button type="success" :disabled="selectedIds.length !== 1" @click="openUpdateDialog()">密钥更新</el-button>
        <el-button type="danger" :disabled="selectedIds.length === 0" @click="handleRevoke()">密钥回收</el-button>
        <el-button type="warning" plain @click="activeTab = 'autoupdate'">密钥自动更新</el-button>
        <RouterLink class="inline-link" to="/permissions">进入权限申请</RouterLink>
      </div>
    </article>

    <el-tabs v-model="activeTab" class="user-tabs">
      <el-tab-pane label="我的密钥" name="mykeys">
        <article class="panel">
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
            <el-table-column label="更新时间" align="center" prop="updTime" width="180" />
            <el-table-column label="操作" align="center" width="220" fixed="right">
              <template #default="scope">
                <el-button link type="primary" :disabled="isRevoked(scope.row.status)" @click="openUpdateDialog(scope.row)">
                  更新
                </el-button>
                <el-button link type="danger" :disabled="isRevoked(scope.row.status)" @click="handleRevoke(scope.row)">
                  回收
                </el-button>
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
      </el-tab-pane>

      <el-tab-pane label="密钥自动更新" name="autoupdate">
        <article class="panel">
          <el-alert
            v-if="!canManageAutoUpdate"
            title="当前账号没有自动更新操作权限，可前往权限管理页申请临时权限。"
            type="warning"
            :closable="false"
            show-icon
            class="mb12"
          >
            <template #default>
              <RouterLink class="inline-link" to="/permissions">去申请权限</RouterLink>
            </template>
          </el-alert>

          <el-alert
            v-if="showAutoUpdateRollback && canManageAutoUpdate"
            title="当前自动更新权限为临时权限，完成操作后建议立即回退。"
            type="info"
            :closable="false"
            show-icon
            class="mb12"
          >
            <template #default>
              <el-button type="primary" link @click="handleRollback">回退权限</el-button>
            </template>
          </el-alert>

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
              <el-button type="primary" @click="searchAutoUpdate">搜索</el-button>
              <el-button @click="resetAutoUpdate">重置</el-button>
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
                  :disabled="!canManageAutoUpdate || isRevoked(scope.row.status)"
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
      </el-tab-pane>
    </el-tabs>

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
        <p><strong>创建时间：</strong>{{ selectedKey.creTime || '-' }}</p>
        <p><strong>更新时间：</strong>{{ selectedKey.updTime || '-' }}</p>
      </div>
    </el-dialog>
  </section>
</template>

<script setup>
import { computed, getCurrentInstance, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { getLatestApprovedTemporaryRequest, rollbackPermission } from '@/services/permission-api'
import {
  getLifecycleKey,
  listLifecycleKeys,
  revokeLifecycleKey,
  updateLifecycleAutoUpdate,
  updateLifecycleKey
} from '@/services/lifecycle-api'
import { apiBases } from '@/config/api-bases'
import useUserStore from '@/store/modules/user'

const { proxy } = getCurrentInstance()
const router = useRouter()
const userStore = useUserStore()

const apiBase = apiBases.lifecycleApi
const activeTab = ref('mykeys')
const errorMessage = ref('')

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

const canManageAutoUpdate = computed(() => Number(profile.roleLevel) <= 0)
const showAutoUpdateRollback = computed(() => canManageAutoUpdate.value && Boolean(approvedAutoUpdateRequestId.value))

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
})

onMounted(async () => {
  await ensureProfile()
  await loadMyKeys()
  if (activeTab.value === 'autoupdate') {
    await loadAutoUpdateKeys()
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
  if (activeTab.value === 'autoupdate') {
    loadAutoUpdateKeys()
    loadAutoUpdatePermissionState()
    return
  }
  loadMyKeys()
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
    } catch (error) {
      errorMessage.value = error.message
    }
  }).catch(() => {})
}

function toggleAutoUpdate(row) {
  if (!canManageAutoUpdate.value) {
    proxy.$modal.msgWarning('当前没有自动更新操作权限，请先申请临时权限')
    router.push('/permissions')
    return
  }
  if (isRevoked(row.status)) {
    proxy.$modal.msgWarning('已回收密钥不允许配置自动更新')
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

function statusText(status) {
  return {
    1: '有效',
    2: '已轮换',
    3: '已回收',
    Valid: '有效',
    Replaced: '已轮换',
    Revoked: '已回收',
    REVOKED: '已回收'
  }[status] || (status == null ? '-' : String(status))
}

function statusTagType(status) {
  if (isRevoked(status)) {
    return 'danger'
  }
  if (status === '2' || status === 2 || status === 'Replaced') {
    return 'warning'
  }
  return 'success'
}

function roleText(level) {
  return { 0: '管理员', 1: '中级用户', 2: '普通用户' }[level] || '未知'
}
</script>

<style scoped>
.lifecycle-page .mb12 {
  margin-bottom: 12px;
}

.header-actions {
  align-items: flex-start;
  gap: 16px;
}

.profile-grid,
.quick-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.quick-actions {
  align-items: center;
}

.query-form {
  margin-bottom: 16px;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px 16px;
}

@media (max-width: 768px) {
  .profile-grid,
  .quick-actions {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
