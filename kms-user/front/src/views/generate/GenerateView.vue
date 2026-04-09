<template>
  <section class="page">
    <div class="page-header">
      <p class="eyebrow">Generate</p>
      <h2>密钥生成与记录查询</h2>
      <p>保留用户侧生成入口，同时继续支持生成记录、详情和公共参数查询。</p>
    </div>

    <el-card class="panel" shadow="never">
      <template #header>
        <div class="panel-head">
          <div>
            <h3>发起生成</h3>
            <p class="muted">当前用户将自动绑定为申请人，无需手动选择用户。</p>
          </div>
          <RouterLink class="inline-link" to="/permissions">查看权限申请</RouterLink>
        </div>
      </template>

      <div class="profile-grid">
        <label>
          <span>用户 ID</span>
          <input :value="profile.userId || '-'" type="text" disabled />
        </label>
        <label>
          <span>用户名</span>
          <input :value="profile.userName || '-'" type="text" disabled />
        </label>
        <label>
          <span>API 前缀</span>
          <input :value="apiBase" type="text" disabled />
        </label>
      </div>

      <el-alert
        v-if="generateForm.encrytType === '无证书非对称加密'"
        title="当前统一生成页暂不直接处理无证书非对称密钥的浏览器端私钥拼装，请优先使用对称/非对称/单向算法。"
        type="warning"
        :closable="false"
        show-icon
        class="mb12"
      />

      <el-form ref="generateFormRef" :model="generateForm" :rules="generateRules" label-width="108px" class="generate-form">
        <div class="form-grid three-col">
          <el-form-item label="算法类型" prop="encrytType">
            <el-select v-model="generateForm.encrytType" placeholder="请选择算法类型" @change="handleEncrytTypeChange">
              <el-option label="无证书非对称加密" value="无证书非对称加密" />
              <el-option label="对称加密" value="对称加密" />
              <el-option label="非对称加密" value="非对称加密" />
              <el-option label="单向加密" value="单向加密" />
            </el-select>
          </el-form-item>
          <el-form-item label="算法名称" prop="encrytName">
            <el-select v-model="generateForm.encrytName" placeholder="请选择算法名称">
              <el-option
                v-for="option in encrytNameOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="密钥名称" prop="keyName">
            <el-input v-model="generateForm.keyName" maxlength="64" show-word-limit />
          </el-form-item>
          <el-form-item label="密钥用途" prop="keyUse">
            <el-input v-model="generateForm.keyUse" maxlength="128" show-word-limit />
          </el-form-item>
          <el-form-item label="所属域" prop="keyDomain">
            <el-input v-model="generateForm.keyDomain" maxlength="64" placeholder="默认 A，可按需填写" />
          </el-form-item>
          <el-form-item label="自动更新">
            <el-switch v-model="generateForm.autoUpdateEnabled" />
          </el-form-item>
        </div>
      </el-form>

      <div class="action-row">
        <el-button type="primary" :loading="submitting" @click="submitGenerate">提交生成</el-button>
        <el-button @click="resetGenerateForm">重置</el-button>
      </div>
    </el-card>

    <el-card class="panel" shadow="never">
      <template #header>
        <div class="panel-head">
          <div>
            <h3>生成记录</h3>
            <p class="muted">统一前端直接读取生成系统记录，并支持查看单条详情。</p>
          </div>
        </div>
      </template>

      <el-form :model="filters" inline label-width="88px" class="query-form">
        <el-form-item label="用户 ID">
          <el-input v-model="filters.userId" type="number" min="1" placeholder="按用户 ID 筛选" />
        </el-form-item>
        <el-form-item label="用户名">
          <el-input v-model="filters.userName" placeholder="按用户名筛选" />
        </el-form-item>
        <el-form-item label="算法名称">
          <el-input v-model="filters.encrytName" placeholder="如 AES / RSA / SHA-256" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadKeys">刷新</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>

      <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>

      <el-table v-loading="listLoading" :data="keys">
        <el-table-column label="密钥 ID" prop="keyId" width="90" />
        <el-table-column label="用户名" prop="userName" width="120" />
        <el-table-column label="算法类型" prop="encrytType" min-width="140" />
        <el-table-column label="算法名称" prop="encrytName" width="120" />
        <el-table-column label="密钥名称" prop="keyName" min-width="160" />
        <el-table-column label="密钥用途" prop="keyUse" min-width="160" show-overflow-tooltip />
        <el-table-column label="链上状态" width="120">
          <template #default="scope">
            <el-tag :type="chainStatusType(scope.row.chainStatus)">{{ chainStatusText(scope.row.chainStatus) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" prop="creTime" width="180" />
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="scope">
            <el-button link type="primary" @click="showDetail(scope.row.keyId)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="panel" shadow="never">
      <template #header>
        <div class="panel-head">
          <div>
            <h3>公共密钥列表</h3>
            <p class="muted">该能力属于生成域临时权限，审批通过后可查看公共密钥。</p>
          </div>
          <RouterLink class="inline-link" to="/permissions">去申请权限</RouterLink>
        </div>
      </template>

      <el-alert
        v-if="!canViewPublicKeys"
        title="当前账号没有查看公共密钥列表的权限，请先到权限管理页申请临时权限。"
        type="warning"
        :closable="false"
        show-icon
        class="mb12"
      />

      <el-alert
        v-if="showPublicKeysRollback"
        title="当前公共密钥访问权限为临时权限，完成查看后建议立即回退。"
        type="info"
        :closable="false"
        show-icon
        class="mb12"
      >
        <template #default>
          <el-button type="primary" link @click="handleRollbackPublicKeys">回退权限</el-button>
        </template>
      </el-alert>

      <el-form :model="publicKeyQuery" inline label-width="88px" class="query-form">
        <el-form-item label="用户名">
          <el-input v-model="publicKeyQuery.userName" placeholder="请输入用户名" clearable />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :disabled="!canViewPublicKeys" @click="loadPublicKeys">搜索</el-button>
          <el-button :disabled="!canViewPublicKeys" @click="resetPublicKeys">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table v-loading="publicListLoading" :data="publicKeys">
        <el-table-column label="密钥 ID" prop="keyId" width="90" />
        <el-table-column label="用户名" prop="userName" width="120" />
        <el-table-column label="算法类型" prop="encrytType" min-width="140" />
        <el-table-column label="算法名称" prop="encrytName" width="120" />
        <el-table-column label="密钥名称" prop="keyName" min-width="160" />
        <el-table-column label="公钥值" prop="keyValue" min-width="260" show-overflow-tooltip />
        <el-table-column label="创建时间" prop="creTime" width="180" />
      </el-table>
    </el-card>

    <el-card class="panel" shadow="never">
      <template #header>
        <div class="panel-head">
          <div>
            <h3>公共参数查询</h3>
          </div>
        </div>
      </template>

      <el-form :model="paramForm" inline label-width="88px" class="query-form">
        <el-form-item label="算法类型">
          <el-select v-model="paramForm.encrytType" placeholder="请选择">
            <el-option label="无证书非对称加密" value="无证书非对称加密" />
            <el-option label="对称加密" value="对称加密" />
            <el-option label="非对称加密" value="非对称加密" />
            <el-option label="单向加密" value="单向加密" />
          </el-select>
        </el-form-item>
        <el-form-item label="算法名称">
          <el-input v-model="paramForm.encrytName" placeholder="例如 SSCL / SM2 / AES" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadParams">查询公共参数</el-button>
        </el-form-item>
      </el-form>
      <pre v-if="commonParams" class="json-block">{{ JSON.stringify(commonParams, null, 2) }}</pre>
    </el-card>

    <el-dialog v-model="detailOpen" title="生成详情" width="720px" append-to-body>
      <div v-if="selectedKey" class="detail-grid">
        <p><strong>密钥 ID：</strong>{{ selectedKey.keyId }}</p>
        <p><strong>用户 ID：</strong>{{ selectedKey.userId }}</p>
        <p><strong>用户名：</strong>{{ selectedKey.userName || '-' }}</p>
        <p><strong>算法类型：</strong>{{ selectedKey.encrytType || '-' }}</p>
        <p><strong>算法名称：</strong>{{ selectedKey.encrytName || '-' }}</p>
        <p><strong>密钥名称：</strong>{{ selectedKey.keyName || '-' }}</p>
        <p><strong>密钥用途：</strong>{{ selectedKey.keyUse || '-' }}</p>
        <p><strong>所属域：</strong>{{ selectedKey.keyDomain || '-' }}</p>
        <p><strong>链上状态：</strong>{{ chainStatusText(selectedKey.chainStatus) }}</p>
        <p><strong>创建时间：</strong>{{ selectedKey.creTime || '-' }}</p>
        <p><strong>更新时间：</strong>{{ selectedKey.updTime || '-' }}</p>
        <p class="detail-span"><strong>密钥值：</strong>{{ selectedKey.keyValue || '-' }}</p>
      </div>
    </el-dialog>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { apiBases } from '@/config/api-bases'
import { createGenerateKey, getCommonParams, getGenerateKey, listGenerateKeys, listPublicGenerateKeys } from '@/services/generate-api'
import { getLatestApprovedTemporaryRequest, rollbackPermission } from '@/services/permission-api'
import useUserStore from '@/store/modules/user'
const userStore = useUserStore()

const apiBase = apiBases.generateApi
const listLoading = ref(false)
const submitting = ref(false)
const detailOpen = ref(false)
const generateFormRef = ref(null)
const selectedKey = ref(null)
const keys = ref([])
const publicKeys = ref([])
const commonParams = ref(null)
const errorMessage = ref('')
const publicListLoading = ref(false)
const approvedPublicRequestId = ref(null)

const profile = reactive({
  userId: '',
  userName: ''
})

const filters = reactive({
  userId: '',
  userName: '',
  encrytName: ''
})

const paramForm = reactive({
  encrytType: '',
  encrytName: ''
})

const publicKeyQuery = reactive({
  pageNum: 1,
  pageSize: 10,
  userName: ''
})

const generateForm = reactive({
  encrytType: '',
  encrytName: '',
  keyName: '',
  keyUse: '',
  keyDomain: 'A',
  autoUpdateEnabled: false
})

const encrytNameOptions = ref([])
const generateRules = {
  encrytType: [{ required: true, message: '请选择算法类型', trigger: 'change' }],
  encrytName: [{ required: true, message: '请选择算法名称', trigger: 'change' }],
  keyName: [{ required: true, message: '请输入密钥名称', trigger: 'blur' }],
  keyUse: [{ required: true, message: '请输入密钥用途', trigger: 'blur' }]
}

const canViewPublicKeys = computed(() => Number(userStore.roleLevel) <= 1)
const showPublicKeysRollback = computed(() => canViewPublicKeys.value && Boolean(approvedPublicRequestId.value))

watch(
  () => ({
    id: userStore.id,
    name: userStore.name,
    roleLevel: userStore.roleLevel,
    token: userStore.token
  }),
  async (value) => {
    profile.userId = value.id || ''
    profile.userName = value.name || ''
    if (!value.token) {
      keys.value = []
      publicKeys.value = []
      selectedKey.value = null
      approvedPublicRequestId.value = null
      return
    }

    await loadPublicKeyPermissionState()
    if (Number(value.roleLevel) <= 1) {
      await loadPublicKeys()
    }
  },
  { immediate: true }
)

onMounted(async () => {
  await ensureProfile()
  fillDefaultFilters()
  await loadKeys()
  await loadPublicKeyPermissionState()
  if (canViewPublicKeys.value) {
    await loadPublicKeys()
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

function fillDefaultFilters() {
  if (!filters.userId && profile.userId) {
    filters.userId = String(profile.userId)
  }
  if (!filters.userName && profile.userName) {
    filters.userName = profile.userName
  }
}

function resetGenerateForm() {
  generateForm.encrytType = ''
  generateForm.encrytName = ''
  generateForm.keyName = ''
  generateForm.keyUse = ''
  generateForm.keyDomain = 'A'
  generateForm.autoUpdateEnabled = false
  encrytNameOptions.value = []
  generateFormRef.value?.clearValidate()
}

function handleEncrytTypeChange(value) {
  if (value === '无证书非对称加密') {
    encrytNameOptions.value = [
      { label: 'SM2', value: 'SM2' },
      { label: 'SSCL', value: 'SSCL' }
    ]
  } else if (value === '对称加密') {
    encrytNameOptions.value = [{ label: 'AES', value: 'AES' }]
  } else if (value === '非对称加密') {
    encrytNameOptions.value = [
      { label: 'RSA', value: 'RSA' },
      { label: 'ECC', value: 'ECC' }
    ]
  } else if (value === '单向加密') {
    encrytNameOptions.value = [
      { label: 'MD5', value: 'MD5' },
      { label: 'BLAKE2', value: 'BLAKE2' },
      { label: 'SHA-256', value: 'SHA-256' },
      { label: 'SHA-512', value: 'SHA-512' },
      { label: 'SHA-3', value: 'SHA-3' }
    ]
  } else {
    encrytNameOptions.value = []
  }
  generateForm.encrytName = ''
}

async function submitGenerate() {
  errorMessage.value = ''
  if (!generateFormRef.value) {
    return
  }

  try {
    await generateFormRef.value.validate()
  } catch {
    return
  }

  if (!profile.userId || !profile.userName) {
    await ensureProfile()
  }
  if (!profile.userId || !profile.userName) {
    errorMessage.value = '当前登录用户信息不完整，请刷新后重试。'
    return
  }
  if (generateForm.encrytType === '无证书非对称加密') {
    errorMessage.value = '当前生成页暂不直接处理无证书非对称密钥，请先选择其他算法类型。'
    return
  }

  submitting.value = true
  try {
    await createGenerateKey({
      userId: Number(profile.userId),
      userName: profile.userName,
      encrytType: generateForm.encrytType,
      encrytName: generateForm.encrytName,
      keyName: normalizeText(generateForm.keyName),
      keyUse: normalizeText(generateForm.keyUse),
      keyDomain: normalizeText(generateForm.keyDomain) || 'A',
      autoUpdate: generateForm.autoUpdateEnabled ? 'true' : 'false'
    })
    ElMessage.success('生成请求已提交，正在后台处理')
    resetGenerateForm()
    fillDefaultFilters()
    await loadKeys()
  } catch (error) {
    errorMessage.value = error.message
  } finally {
    submitting.value = false
  }
}

async function loadKeys() {
  errorMessage.value = ''
  listLoading.value = true
  try {
    const data = await listGenerateKeys(filters)
    keys.value = data.rows || []
  } catch (error) {
    keys.value = []
    errorMessage.value = error.message
  } finally {
    listLoading.value = false
  }
}

async function loadPublicKeys() {
  errorMessage.value = ''
  if (!canViewPublicKeys.value) {
    publicKeys.value = []
    return
  }

  publicListLoading.value = true
  try {
    const data = await listPublicGenerateKeys(publicKeyQuery)
    publicKeys.value = data.rows || data.data || []
  } catch (error) {
    publicKeys.value = []
    errorMessage.value = error.message
  } finally {
    publicListLoading.value = false
  }
}

function resetFilters() {
  filters.userId = profile.userId ? String(profile.userId) : ''
  filters.userName = profile.userName || ''
  filters.encrytName = ''
  loadKeys()
}

function resetPublicKeys() {
  publicKeyQuery.pageNum = 1
  publicKeyQuery.pageSize = 10
  publicKeyQuery.userName = ''
  loadPublicKeys()
}

async function showDetail(keyId) {
  errorMessage.value = ''
  try {
    const data = await getGenerateKey(keyId)
    selectedKey.value = data.data || null
    detailOpen.value = Boolean(selectedKey.value)
  } catch (error) {
    errorMessage.value = error.message
  }
}

async function loadParams() {
  errorMessage.value = ''
  if (!paramForm.encrytType || !paramForm.encrytName.trim()) {
    errorMessage.value = '请先填写算法类型和算法名称。'
    return
  }
  try {
    commonParams.value = await getCommonParams(paramForm)
  } catch (error) {
    commonParams.value = null
    errorMessage.value = error.message
  }
}

async function loadPublicKeyPermissionState() {
  approvedPublicRequestId.value = null
  if (!profile.userId || !userStore.token) {
    return
  }

  try {
    const approved = await getLatestApprovedTemporaryRequest('PUBLIC_KEY_LIST', Number(profile.userId))
    approvedPublicRequestId.value = approved?.requestId || null
  } catch (error) {
    errorMessage.value = error.message
  }
}

async function handleRollbackPublicKeys() {
  if (!approvedPublicRequestId.value) {
    ElMessage.warning('没有可回退的临时权限')
    return
  }

  try {
    await rollbackPermission('PUBLIC_KEY_LIST', approvedPublicRequestId.value)
    ElMessage.success('权限已回退成功')
    approvedPublicRequestId.value = null
    publicKeys.value = []
    await userStore.getInfo()
    await loadPublicKeyPermissionState()
  } catch (error) {
    errorMessage.value = error.message
  }
}

function normalizeText(value) {
  const text = value == null ? '' : String(value).trim()
  return text === '' ? null : text
}

function chainStatusText(status) {
  return {
    0: '待上链',
    1: '已上链',
    2: '上链失败',
    '0': '待上链',
    '1': '已上链',
    '2': '上链失败'
  }[status] || (status ?? '未知')
}

function chainStatusType(status) {
  return {
    0: 'info',
    1: 'success',
    2: 'danger',
    '0': 'info',
    '1': 'success',
    '2': 'danger'
  }[status] || 'info'
}
</script>

<style scoped>
.panel + .panel {
  margin-top: 16px;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.profile-grid,
.form-grid.three-col,
.detail-grid {
  display: grid;
  gap: 12px 16px;
}

.profile-grid,
.form-grid.three-col {
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.profile-grid label {
  display: grid;
  gap: 6px;
}

.generate-form {
  margin-top: 16px;
}

.generate-form :deep(.el-form-item) {
  margin-bottom: 0;
}

.action-row {
  display: flex;
  gap: 12px;
  margin-top: 16px;
}

.query-form {
  margin-bottom: 12px;
}

.json-block {
  margin: 0;
  padding: 16px;
  border-radius: 16px;
  background: #0f172a;
  color: #e2e8f0;
  overflow: auto;
}

.detail-grid {
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.detail-span {
  grid-column: 1 / -1;
}

.mb12 {
  margin-top: 12px;
}
</style>
