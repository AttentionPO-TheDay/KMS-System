<template>
  <section class="page generate-page">
    <div class="generate-dashboard">
      <nav class="inner-sidenav">
        <div class="nav-item" :class="{ active: activeTab === 'generate' }" @click="activeTab = 'generate'">
          <span class="icon">🚀</span> 密钥生成
        </div>
        <div class="nav-item" :class="{ active: activeTab === 'records' }" @click="activeTab = 'records'">
          <span class="icon">📊</span> 历史记录
        </div>
        <div class="nav-item" :class="{ active: activeTab === 'public' }" @click="activeTab = 'public'">
          <span class="icon">🌐</span> 公共库
        </div>
        <div class="nav-item" :class="{ active: activeTab === 'params' }" @click="activeTab = 'params'">
          <span class="icon">⚙️</span> 参数查询
        </div>
      </nav>

      <main class="inner-main-content">
        <div v-show="activeTab === 'generate'" class="tab-pane">
          <div class="summary-grid">
      <article class="summary-card">
        <span class="summary-label">当前用户</span>
        <strong>{{ profile.userName || '未登录' }}</strong>
        <small>ID: {{ profile.userId || '-' }}</small>
      </article>
      <article class="summary-card">
        <span class="summary-label">生成能力</span>
        <strong>证书无关密钥</strong>
        <small>支持 SM2 / SSCL</small>
      </article>
      <article class="summary-card">
        <span class="summary-label">公共密钥权限</span>
        <strong>{{ canViewPublicKeys ? '已具备' : '需申请' }}</strong>
        <small>{{ canViewPublicKeys ? '可直接查询公共密钥' : '去权限页申请临时权限' }}</small>
      </article>
    </div>

    <el-card class="panel glass-panel" shadow="never">
      <template #header>
        <div class="panel-head">
          <div>
            <h3>密钥生成</h3>
            <p class="muted">提交前会先在当前浏览器生成一份用户侧密钥材料，并把公钥份额 `uA` 发送到后端。</p>
          </div>
          <RouterLink class="inline-link" to="/user_actions/permissions">查看权限申请</RouterLink>
        </div>
      </template>

      <div class="generate-layout">
        <div class="generate-main generation-box">
          <div class="profile-grid">
            <label>
              <span>用户 ID</span>
              <input :value="profile.userId || '-'" type="text" disabled />
            </label>
            <label>
              <span>用户名</span>
              <input :value="profile.userName || '-'" type="text" disabled />
            </label>
          </div>

          <el-form ref="generateFormRef" :model="generateForm" :rules="generateRules" label-width="108px" class="generate-form">
            <div class="form-grid two-col">
              <el-form-item label="算法类型" prop="encrytType">
                <el-select v-model="generateForm.encrytType" @change="handleEncrytTypeChange">
                  <el-option label="无证书非对称加密" value="无证书非对称加密" />
                </el-select>
              </el-form-item>
              <el-form-item label="算法名称" prop="encrytName">
                <el-select v-model="generateForm.encrytName" placeholder="请选择算法名称">
                  <el-option v-for="option in encrytNameOptions" :key="option.value" :label="option.label" :value="option.value" />
                </el-select>
              </el-form-item>
              <el-form-item label="密钥名称" prop="keyName">
                <el-input v-model="generateForm.keyName" maxlength="64" show-word-limit />
              </el-form-item>
              <el-form-item label="密钥用途" prop="keyUse">
                <el-input v-model="generateForm.keyUse" maxlength="128" show-word-limit />
              </el-form-item>
              <el-form-item label="所属域" prop="keyDomain">
                <el-input v-model="generateForm.keyDomain" maxlength="64" placeholder="SSCL 默认 A" />
              </el-form-item>
              <el-form-item label="自动更新">
                <el-switch v-model="generateForm.autoUpdateEnabled" />
              </el-form-item>
            </div>
          </el-form>

          <div class="action-row">
            <el-button type="primary" :loading="submitting" @click="submitGenerate">提交生成</el-button>
            <el-button @click="regenerateLocalMaterial">重新生成本地材料</el-button>
            <el-button @click="resetGenerateForm">重置表单</el-button>
          </div>
        </div>

        <aside class="material-card">
          <div class="material-head">
            <h3>本地材料</h3>
            <el-tag type="success">浏览器侧</el-tag>
          </div>
          <p class="muted">本地部分私钥只保留在当前页面中，不会提交到后端。提交时仅发送 `uA`。</p>

          <div v-if="!localMaterial.publicKey" style="display: flex; justify-content: center; padding: 40px 0;">
            <el-button type="primary" plain @click="regenerateLocalMaterial">点击生成本地公私钥</el-button>
          </div>
          <template v-else>
            <div class="material-item">
              <span>生成时间</span>
              <strong>{{ localMaterial.generatedAt || '-' }}</strong>
            </div>
            <div class="material-item full">
              <span>本地部分公钥 uA</span>
              <code>{{ localMaterial.publicKey || '-' }}</code>
            </div>
            <div class="material-item full">
              <span>本地部分私钥 (浏览器侧生成且不在网络中传输)</span>
              <code class="danger-text" style="color: #ff4d4f;">{{ maskedPrivateKey }}</code>
            </div>
            <div class="action-row compact">
              <el-button text type="primary" @click="copyLocalMaterial">复制材料摘要</el-button>
              <el-button text type="primary" @click="downloadLocalMaterial">下载材料</el-button>
            </div>
          </template>
        </aside>
      </div>

      <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>
    </el-card>
        </div>

        <div v-show="activeTab === 'records'" class="tab-pane">
    <el-card class="panel" shadow="never">
      <template #header>
        <div class="panel-head">
          <div>
            <h3>生成记录</h3>
            <p class="muted">默认聚焦当前登录用户的生成记录，可查看链上状态与单条详情。</p>
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
          <el-input v-model="filters.encrytName" placeholder="SM2 / SSCL" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadKeys">刷新</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table v-loading="listLoading" :data="keys">
        <el-table-column label="密钥 ID" prop="keyId" width="90" />
        <el-table-column label="用户名" prop="userName" width="120" />
        <el-table-column label="算法类型" prop="encrytType" min-width="140" />
        <el-table-column label="算法名称" prop="encrytName" width="120" />
        <el-table-column label="密钥名称" prop="keyName" min-width="160" />
        <el-table-column label="密钥用途" prop="keyUse" min-width="160" show-overflow-tooltip />
        <el-table-column label="自动更新" width="110">
          <template #default="scope">
            <el-tag :type="scope.row.autoUpdate === 'true' || scope.row.autoUpdate === '1' ? 'success' : 'info'">
              {{ scope.row.autoUpdate === 'true' || scope.row.autoUpdate === '1' ? '已开启' : '未开启' }}
            </el-tag>
          </template>
        </el-table-column>
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
        </div>

        <div v-show="activeTab === 'public'" class="tab-pane">
    <el-card class="panel" shadow="never">
      <template #header>
        <div class="panel-head">
          <div>
            <h3>公共密钥列表</h3>
            <p class="muted">该能力需要生成域临时权限，审批通过后只展示脱敏后的公共值。</p>
          </div>
          <RouterLink class="inline-link" to="/user_actions/permissions">去申请权限</RouterLink>
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
        </div>

        <div v-show="activeTab === 'params'" class="tab-pane">
    <el-card class="panel" shadow="never">
      <template #header>
        <div class="panel-head">
          <div>
            <h3>公共参数查询</h3>
            <p class="muted">用于核对 SSCL 公共参数，便于和 legacy 结果做比对。</p>
          </div>
        </div>
      </template>

      <el-form :model="paramForm" inline label-width="88px" class="query-form">
        <el-form-item label="算法类型">
          <el-select v-model="paramForm.encrytType" placeholder="请选择">
            <el-option label="无证书非对称加密" value="无证书非对称加密" />
          </el-select>
        </el-form-item>
        <el-form-item label="算法名称">
          <el-select v-model="paramForm.encrytName" placeholder="请选择算法名称">
            <el-option label="SM2" value="SM2" />
            <el-option label="SSCL" value="SSCL" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadParams">查询公共参数</el-button>
        </el-form-item>
      </el-form>
      <pre v-if="commonParams" class="json-block">{{ JSON.stringify(commonParams, null, 2) }}</pre>
    </el-card>
        </div>
      </main>
    </div>

    <el-dialog v-model="resultOpen" title="本地最终结果" width="760px" append-to-body destroy-on-close>
      <el-alert title="请立即保存用户侧私钥材料。刷新页面后将无法再次恢复。" type="warning" :closable="false" show-icon class="mb16" />
      <div class="detail-grid">
        <p><strong>算法类型：</strong>{{ localResult.encrytType || '-' }}</p>
        <p><strong>算法名称：</strong>{{ localResult.encrytName || '-' }}</p>
        <p><strong>密钥名称：</strong>{{ localResult.keyName || '-' }}</p>
        <p><strong>所属域：</strong>{{ localResult.keyDomain || '-' }}</p>
        <p class="detail-span"><strong>用户公钥份额 uA：</strong>{{ localResult.uA || '-' }}</p>
        <p class="detail-span"><strong>用户私钥份额：</strong>{{ localResult.clientPrivateKey || '-' }}</p>
        <p class="detail-span"><strong>服务端返回值：</strong>{{ localResult.keyValue || '-' }}</p>
        <p v-if="localResult.partialKey" class="detail-span"><strong>部分私钥：</strong>{{ localResult.partialKey }}</p>
        <p v-if="localResult.finalPublicKey" class="detail-span"><strong>最终公钥：</strong>{{ localResult.finalPublicKey }}</p>
        <p v-if="localResult.finalPrivateKey" class="detail-span"><strong>最终私钥：</strong>{{ localResult.finalPrivateKey }}</p>
        <p v-if="localResult.domainDa" class="detail-span"><strong>SSCL DA：</strong>{{ localResult.domainDa }}</p>
      </div>
      <template #footer>
        <el-button @click="copyResultSummary">复制结果</el-button>
        <el-button type="primary" @click="downloadResultSummary">下载结果</el-button>
      </template>
    </el-dialog>

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
import { SM2 } from 'gm-crypto'
import { BigInteger } from 'jsbn'
import { weierstrass } from '@noble/curves/abstract/weierstrass.js'
import { apiBases } from '@/config/api-bases'
import { createGenerateKey, getCommonParams, getGenerateKey, listGenerateKeys, listPublicGenerateKeys } from '@/services/generate-api'
import { getLatestApprovedTemporaryRequest, rollbackPermission } from '@/services/permission-api'
import useUserStore from '@/store/modules/user'

const userStore = useUserStore()
const apiBase = apiBases.generateApi
const curveOrder = new BigInteger('FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123', 16)
const sm2Curve = weierstrass({
  p: BigInt('0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFF'),
  n: BigInt('0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123'),
  h: 1n,
  a: BigInt('0xFFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFC'),
  b: BigInt('0x28E9FA9E9D9F5E344D5A9E4BCF6509A7F39789F515AB8F92DDBCBD414D940E93'),
  Gx: BigInt('0x32C4AE2C1F1981195F9904466A39C9948FE30BBFF2660BE1715A4589334C74C7'),
  Gy: BigInt('0xBC3736A2F4F6779C59BDCEE36B692153D0A9877CC62A474002DF32E52139F0A0')
})

const listLoading = ref(false)
const submitting = ref(false)
const detailOpen = ref(false)
const resultOpen = ref(false)
const generateFormRef = ref(null)
const selectedKey = ref(null)
const localResult = ref({})
const keys = ref([])
const publicKeys = ref([])
const commonParams = ref(null)
const errorMessage = ref('')
const publicListLoading = ref(false)
const activeTab = ref('generate')
const approvedPublicRequestId = ref(null)
const encrytNameOptions = ref([])

const profile = reactive({
  userId: '',
  userName: ''
})

const localMaterial = reactive({
  publicKey: '',
  privateKey: '',
  generatedAt: ''
})

const filters = reactive({
  userId: '',
  userName: '',
  encrytName: ''
})

const paramForm = reactive({
  encrytType: '无证书非对称加密',
  encrytName: 'SSCL'
})

const publicKeyQuery = reactive({
  pageNum: 1,
  pageSize: 10,
  userName: ''
})

const generateForm = reactive({
  encrytType: '无证书非对称加密',
  encrytName: 'SM2',
  keyName: '',
  keyUse: '',
  keyDomain: 'A',
  autoUpdateEnabled: false
})

const generateRules = {
  encrytType: [{ required: true, message: '请选择算法类型', trigger: 'change' }],
  encrytName: [{ required: true, message: '请选择算法名称', trigger: 'change' }],
  keyName: [{ required: true, message: '请输入密钥名称', trigger: 'blur' }],
  keyUse: [{ required: true, message: '请输入密钥用途', trigger: 'blur' }]
}

const hasPermanentPublicKeysAccess = computed(() => Number(userStore.roleLevel) <= 1)
const hasTemporaryPublicKeysAccess = computed(() => Boolean(approvedPublicRequestId.value))
const canViewPublicKeys = computed(() => hasPermanentPublicKeysAccess.value || hasTemporaryPublicKeysAccess.value)
const showPublicKeysRollback = computed(() => hasTemporaryPublicKeysAccess.value)
const maskedPrivateKey = computed(() => maskText(localMaterial.privateKey, 20))

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
  handleEncrytTypeChange(generateForm.encrytType)
  // [NEW] Default do not auto generate local materials
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
  generateForm.encrytType = '无证书非对称加密'
  generateForm.encrytName = 'SM2'
  generateForm.keyName = ''
  generateForm.keyUse = ''
  generateForm.keyDomain = 'A'
  generateForm.autoUpdateEnabled = false
  handleEncrytTypeChange(generateForm.encrytType)
  generateFormRef.value?.clearValidate()
}

function handleEncrytTypeChange(value) {
  if (value === '无证书非对称加密') {
    encrytNameOptions.value = [
      { label: 'SM2', value: 'SM2' },
      { label: 'SSCL', value: 'SSCL' }
    ]
  } else {
    encrytNameOptions.value = []
  }
  if (!encrytNameOptions.value.some((item) => item.value === generateForm.encrytName)) {
    generateForm.encrytName = encrytNameOptions.value[0]?.value || ''
  }
}

function regenerateLocalMaterial() {
  const { publicKey, privateKey } = SM2.generateKeyPair()
  localMaterial.publicKey = publicKey
  localMaterial.privateKey = privateKey
  localMaterial.generatedAt = new Date().toLocaleString('zh-CN', { hour12: false })
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
  if (!localMaterial.publicKey || !localMaterial.privateKey) {
    regenerateLocalMaterial()
  }

  submitting.value = true
  try {
    const response = await createGenerateKey({
      userId: Number(profile.userId),
      userName: profile.userName,
      encrytType: generateForm.encrytType,
      encrytName: generateForm.encrytName,
      keyName: normalizeText(generateForm.keyName),
      keyUse: normalizeText(generateForm.keyUse),
      keyDomain: normalizeText(generateForm.keyDomain) || 'A',
      autoUpdate: generateForm.autoUpdateEnabled ? 'true' : 'false',
      uA: localMaterial.publicKey,
      ua: localMaterial.publicKey
    })

    const snapshot = response?.data || response
    await handleSubmittedSnapshot(snapshot)
    ElMessage.success('生成请求已提交，已同步展示本地结果摘要')
    fillDefaultFilters()
    await loadKeys()
  } catch (error) {
    errorMessage.value = error.message
  } finally {
    submitting.value = false
  }
}

async function handleSubmittedSnapshot(snapshot) {
  const result = {
    ...snapshot,
    keyDomain: snapshot?.keyDomain || generateForm.keyDomain,
    uA: localMaterial.publicKey,
    clientPrivateKey: localMaterial.privateKey
  }

  if (result?.keyValue && result?.encrytType === '无证书非对称加密') {
    if (result.encrytName === 'SM2') {
      enrichSm2Result(result)
    } else if (result.encrytName === 'SSCL') {
      await enrichSsclResult(result)
    }
  }

  localResult.value = result
  resultOpen.value = true
}

function enrichSm2Result(result) {
  const keyValue = safeJsonParse(result.keyValue)
  if (!keyValue?.partialKey) {
    return
  }
  const partialKey = new BigInteger(keyValue.partialKey, 16)
  const clientPrivateKey = new BigInteger(localMaterial.privateKey, 16)
  const finalPrivateKey = partialKey.add(clientPrivateKey).mod(curveOrder)

  result.partialKey = keyValue.partialKey
  result.finalPublicKey = keyValue.finalPublicKey || ''
  if (isValidPrivateKey(finalPrivateKey)) {
    result.finalPrivateKey = leftPad(finalPrivateKey.toString(16), 64)
  }
}

async function enrichSsclResult(result) {
  const keyValue = safeJsonParse(result.keyValue)
  if (!keyValue?.SSCLKey) {
    return
  }

  const params = await getCommonParams({
    encrytType: result.encrytType,
    encrytName: result.encrytName
  })
  const xIndex = parseIndexArray(params?.xIndex)
  const yIndex = parseIndexArray(params?.yIndex)
  const publicPoint = params?.PPub
  if (!xIndex || !yIndex || !publicPoint) {
    return
  }

  const share = keyValue.SSCLKey
  const xHex = share.slice(2, 66)
  const yHex = share.slice(66, 130)
  const secret = getSecret(xIndex, yIndex, xHex, yHex, curveOrder)
  const domainPrivate = secret.multiply(new BigInteger(xHex, 16)).mod(curveOrder)
  const clientPrivate = new BigInteger(localMaterial.privateKey, 16)
  const finalPrivate = clientPrivate.add(domainPrivate).mod(curveOrder)

  result.partialKey = keyValue.SSCLKey
  result.domainDa = sm2PointMultiply(publicPoint, leftPad(domainPrivate.toString(16), 64))
  result.finalPublicKey = sm2PointMultiply(publicPoint, leftPad(finalPrivate.toString(16), 64))
  result.finalPrivateKey = leftPad(finalPrivate.toString(16), 64)
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

function copyLocalMaterial() {
  copyText(`uA: ${localMaterial.publicKey}\nprivate_share: ${localMaterial.privateKey}`)
}

function downloadLocalMaterial() {
  downloadText(`generated_at: ${localMaterial.generatedAt}\nuA: ${localMaterial.publicKey}\nprivate_share: ${localMaterial.privateKey}\n`, 'kms-user-local-material.txt')
}

function copyResultSummary() {
  copyText(buildResultSummary())
}

function downloadResultSummary() {
  downloadText(buildResultSummary(), 'kms-user-generate-result.txt')
}

function buildResultSummary() {
  const result = localResult.value || {}
  return [
    `algorithm_type: ${result.encrytType || ''}`,
    `algorithm_name: ${result.encrytName || ''}`,
    `key_name: ${result.keyName || ''}`,
    `key_domain: ${result.keyDomain || ''}`,
    `uA: ${result.uA || ''}`,
    `client_private_key: ${result.clientPrivateKey || ''}`,
    `partial_key: ${result.partialKey || ''}`,
    `final_public_key: ${result.finalPublicKey || ''}`,
    `final_private_key: ${result.finalPrivateKey || ''}`,
    `domain_da: ${result.domainDa || ''}`,
    `server_key_value: ${result.keyValue || ''}`
  ].join('\n')
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

function getSecret(xIndex, yIndex, xHex, yHex, n) {
  const xPoints = xIndex.map((value) => new BigInteger(value, 16))
  xPoints.push(new BigInteger(xHex, 16))
  const yPoints = yIndex.map((value) => new BigInteger(value, 16))
  yPoints.push(new BigInteger(yHex, 16))

  let secret = new BigInteger('0')
  for (let i = 0; i < xPoints.length; i += 1) {
    let numerator = new BigInteger('1')
    let denominator = new BigInteger('1')
    for (let j = 0; j < xPoints.length; j += 1) {
      if (i !== j) {
        numerator = numerator.multiply(xPoints[j].negate()).mod(n)
        denominator = denominator.multiply(xPoints[i].subtract(xPoints[j]).mod(n)).mod(n)
      }
    }
    secret = secret.add(yPoints[i].multiply(numerator).multiply(denominator.modInverse(n)).mod(n)).mod(n)
  }
  return secret.compareTo(new BigInteger('0')) < 0 ? secret.add(n) : secret
}

function sm2PointMultiply(hexPoint, hexScalar) {
  if (!hexPoint || !hexPoint.startsWith('04')) {
    throw new Error('点格式错误，必须以04开头')
  }
  const point = sm2Curve.fromHex(hexPoint)
  point.assertValidity()
  const result = point.multiply(BigInt(`0x${hexScalar}`))
  result.assertValidity()
  return result.toHex(false)
}

function isValidPrivateKey(value) {
  return value.compareTo(new BigInteger('1')) > 0 && value.compareTo(curveOrder.subtract(new BigInteger('1'))) < 0
}

function parseIndexArray(value) {
  if (!value) {
    return null
  }
  if (Array.isArray(value)) {
    return value
  }
  try {
    return JSON.parse(value)
  } catch {
    return null
  }
}

function safeJsonParse(value) {
  try {
    return JSON.parse(value)
  } catch {
    return null
  }
}

function leftPad(value, length) {
  return String(value || '').padStart(length, '0')
}

function normalizeText(value) {
  const text = value == null ? '' : String(value).trim()
  return text === '' ? null : text
}

function maskText(value, keep) {
  const text = value || ''
  if (!text) {
    return '-'
  }
  if (text.length <= keep * 2) {
    return text
  }
  return `${text.slice(0, keep)}...${text.slice(-keep)}`
}

function copyText(text) {
  navigator.clipboard.writeText(text).then(() => {
    ElMessage.success('复制成功')
  }).catch(() => {
    ElMessage.error('复制失败，请手动复制')
  })
}

function downloadText(text, filename) {
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.generate-page {
  display: grid;
  gap: 16px;
}

.summary-grid,
.profile-grid,
.form-grid.two-col,
.detail-grid,
.generate-layout {
  display: grid;
  gap: 16px;
}

.summary-grid {
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
}

.summary-card,
.material-card {
  padding: 24px;
  border: 1px solid rgba(255, 255, 255, 0.05); /* Global card style will handle standard, but we override here if needed */
  border-radius: 20px;
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.03), rgba(255, 255, 255, 0.01));
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
  transition: transform 0.3s ease, border-color 0.3s ease, box-shadow 0.3s ease;
}

.summary-card:hover, .material-card:hover {
  transform: translateY(-2px);
  border-color: rgba(0, 229, 255, 0.2);
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.3), 0 0 20px rgba(0, 153, 255, 0.1);
}

.summary-card strong,
.material-item strong {
  display: block;
  margin-top: 8px;
  font-size: 20px;
  color: #fff;
  font-weight: 500;
  text-shadow: 0 0 10px rgba(0, 229, 255, 0.3);
}

.summary-card small,
.muted {
  color: #94a3b8;
}

.summary-label,
.material-item span {
  font-size: 14px;
  color: #bae6fd;
}

.generate-layout {
  grid-template-columns: minmax(0, 2fr) minmax(320px, 1fr);
  align-items: start;
}

.generate-main {
  min-width: 0;
}

.profile-grid,
.form-grid.two-col,
.detail-grid {
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.profile-grid label {
  display: grid;
  gap: 6px;
}

.profile-grid input {
  width: 100%;
  padding: 12px 14px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  background: rgba(0, 0, 0, 0.3);
  color: #fff;
  transition: all 0.3s;
}

.profile-grid input:focus {
  outline: none;
  border-color: #00e5ff;
  box-shadow: 0 0 0 3px rgba(0, 229, 255, 0.15);
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}

.generate-form {
  margin-top: 16px;
}

.generate-form :deep(.el-form-item) {
  margin-bottom: 0;
}

.material-head,
.material-item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.material-head {
  align-items: center;
  margin-bottom: 12px;
}

.material-item {
  padding: 16px 0;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  align-items: flex-start;
  animation: fade-in 0.5s ease forwards;
}

.material-item.full {
  display: grid;
}

.material-item code,
.detail-span,
.json-block {
  word-break: break-all;
}

.material-item code {
  margin-top: 8px;
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(0, 153, 255, 0.05);
  border: 1px solid rgba(0, 153, 255, 0.2);
  color: #00e5ff;
  box-shadow: inset 0 0 10px rgba(0, 153, 255, 0.1);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
}

.action-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 16px;
}

.action-row.compact {
  margin-top: 12px;
}

.mb16 {
  margin-top: 16px;
}

.generation-box {
  padding: 24px;
  border: 1px dashed rgba(0, 229, 255, 0.3);
  border-radius: 16px;
  background: rgba(0, 153, 255, 0.02);
}

.json-block {
  margin: 0;
  padding: 20px;
  border-radius: 16px;
  background: rgba(0, 0, 0, 0.4);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #bae6fd;
  overflow-y: auto;
  max-height: 400px;
  white-space: pre-wrap;
  word-wrap: break-word;
  word-break: break-all;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
}

.generate-dashboard {
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

.inner-sidenav .icon {
  font-size: 18px;
}

.inner-main-content {
  flex-grow: 1;
  min-width: 0;
}

.tab-pane {
  animation: fade-in 0.3s ease-out;
}

@keyframes fade-in {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

@media (max-width: 960px) {
  .generate-dashboard {
    flex-direction: column;
  }
  .inner-sidenav {
    width: 100%;
    flex-direction: row;
    overflow-x: auto;
  }
  .generate-layout {
    grid-template-columns: 1fr;
  }
}
</style>
