<template>
  <section class="page generate-page">
    <div class="generate-dashboard">
      <nav class="inner-sidenav">
        <div class="nav-item" :class="{ active: activeTab === 'generate' }" @click="activeTab = 'generate'">
          <el-icon class="icon"><MagicStick /></el-icon> 密钥生成
        </div>
        <div class="nav-item" :class="{ active: activeTab === 'records' }" @click="activeTab = 'records'">
          <el-icon class="icon"><TrendCharts /></el-icon> 历史记录
        </div>
        <div class="nav-item" :class="{ active: activeTab === 'params' }" @click="activeTab = 'params'">
          <el-icon class="icon"><Setting /></el-icon> 参数查询
        </div>
      </nav>

      <main class="inner-main-content">
        <div v-show="activeTab === 'generate'" class="tab-pane">
          <div class="summary-grid">
      <article class="summary-card">
        <span class="summary-label">当前用户</span>
        <strong>{{ profile.userName || '未登录' }}</strong>
        <small>{{ roleLevelText(profile.roleLevel) }}</small>
      </article>
      <article class="summary-card">
        <span class="summary-label">生成能力</span>
        <strong>证书无关 / 抗量子密钥</strong>
        <small>支持 SM2 / SSCL / 抗量子签名密钥 / 抗量子封装密钥</small>
      </article>
      <article class="summary-card">
        <span class="summary-label">本地私钥份额</span>
        <strong>{{ localMaterial.privateKey ? '已生成' : '未生成' }}</strong>
        <small>只在浏览器内保存，不会上传服务端</small>
      </article>
      <article class="summary-card">
        <!--
          P3 步骤 0b：把"密钥凭据"这件事显式呈现出来。
          生成密钥后必须下载密钥文件并自行保存 —— 服务端只有 KGC 分片，
          没有它就解不开分发过来的信封。
        -->
        <span class="summary-label">密钥凭据</span>
        <strong>{{ keyring.size > 0 ? `已导入 ${keyring.size} 把` : '未导入' }}</strong>
        <small class="keyring-line">
          <key-file-import ref="keyFileImportRef" @imported="handleKeyFileImported" />
        </small>
      </article>
    </div>

    <el-card class="panel" shadow="never">
      <template #header>
        <div class="panel-head">
          <div>
            <h3>密钥生成</h3>
</div>
        </div>
      </template>

      <div class="generate-layout">
        <div class="generate-main generation-box">
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
                <el-select v-model="generateForm.keyUse" placeholder="请选择密钥用途">
                  <el-option v-for="option in keyUseOptions" :key="option.value" :label="option.label" :value="option.value" />
                </el-select>
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
            <el-tag :type="pqAlgorithms.includes(generateForm.encrytName) ? 'info' : 'success'">{{ pqAlgorithms.includes(generateForm.encrytName) ? 'PQ demo_generated' : '浏览器侧' }}</el-tag>
          </div>
<div v-if="pqAlgorithms.includes(generateForm.encrytName)" class="pq-mode-note">
            <strong>当前 PQ 模式：demo_generated</strong>
          </div>
          <div v-else-if="!localMaterial.publicKey" style="display: flex; justify-content: center; padding: 40px 0;">
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
              <code class="danger-text" style="color: var(--kms-danger-strong);">{{ maskedPrivateKey }}</code>
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
</div>
        </div>
      </template>

      <el-form :model="filters" inline label-width="88px" class="query-form" @submit.prevent>
        <el-form-item label="用户 ID">
          <el-input v-model="filters.userId" type="number" min="1" placeholder="按用户 ID 筛选" clearable @keyup.enter="handleSearchKeys" />
        </el-form-item>
        <el-form-item label="用户名">
          <el-input v-model="filters.userName" placeholder="按用户名筛选" clearable @keyup.enter="handleSearchKeys" />
        </el-form-item>
        <el-form-item label="算法名称">
          <el-input v-model="filters.encrytName" placeholder="SM2 / SSCL" clearable @keyup.enter="handleSearchKeys" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearchKeys">查询</el-button>
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

        <div v-show="activeTab === 'params'" class="tab-pane">
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
      <!--
        这里的提示语已按 P3 步骤 0b 更新：
        原来只说"刷新后无法恢复"，把保存私钥的责任全推给用户手抄。
        现在有一个正式的**密钥文件**出口 —— 用户下载它，日后解密时再导入回来。
      -->
      <el-alert
        v-if="canExportKeyFile"
        title="请下载密钥文件并妥善保存。这是日后解开分发信封的唯一凭据，刷新页面后无法再次生成。"
        type="warning"
        :closable="false"
        show-icon
        class="mb16"
      />
      <el-alert
        v-else
        title="请立即保存用户侧私钥材料。刷新页面后将无法再次恢复。"
        type="warning"
        :closable="false"
        show-icon
        class="mb16"
      />
      <div class="detail-grid">
        <p><strong>算法类型：</strong>{{ localResult.encrytType || '-' }}</p>
        <p><strong>算法名称：</strong>{{ localResult.encrytName || '-' }}</p>
        <p><strong>密钥名称：</strong>{{ localResult.keyName || '-' }}</p>
        <p><strong>所属域：</strong>{{ localResult.keyDomain || '-' }}</p>
        <p v-if="pqAlgorithms.includes(localResult.encrytName)" class="detail-span"><strong>PQ 模式：</strong>{{ localResult.pqMode || localResult.pq_mode || 'demo_generated' }}</p>
        
        <p v-if="!pqAlgorithms.includes(localResult.encrytName)" class="detail-span"><strong>用户公钥份额 uA：</strong>{{ localResult.uA || '-' }}</p>
        <p v-if="!pqAlgorithms.includes(localResult.encrytName)" class="detail-span"><strong>用户私钥份额：</strong>{{ localResult.clientPrivateKey || '-' }}</p>
        <p class="detail-span"><strong>服务端返回值：</strong>{{ localResult.keyValue || '-' }}</p>
        <p v-if="localResult.partialKey" class="detail-span"><strong>部分私钥：</strong>{{ localResult.partialKey }}</p>
        <p v-if="localResult.finalPublicKey" class="detail-span"><strong>最终公钥：</strong>{{ localResult.finalPublicKey }}</p>
        <p v-if="localResult.finalPrivateKey" class="detail-span"><strong>最终私钥：</strong>{{ localResult.finalPrivateKey }}</p>
        <p v-if="localResult.domainDa" class="detail-span"><strong>SSCL DA：</strong>{{ localResult.domainDa }}</p>
      </div>
      <template #footer>
        <el-button @click="copyResultSummary">复制结果</el-button>
        <el-button v-if="canExportKeyFile" type="warning" plain @click="exportKeyFile">
          下载密钥文件
        </el-button>
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
        <p><strong>交易哈希：</strong>{{ selectedKey.chainHash || '-' }}</p>
        <p><strong>区块高度：</strong>{{ selectedKey.blockHeight ?? '-' }}</p>
        <p><strong>创建时间：</strong>{{ selectedKey.creTime || '-' }}</p>
        <p><strong>更新时间：</strong>{{ selectedKey.updTime || '-' }}</p>
        <p v-if="pqAlgorithms.includes(selectedKey.encrytName)" class="detail-span"><strong>PQ 模式：</strong>{{ selectedPqMode }}</p>
        
        <p class="detail-span"><strong>密钥值：</strong>{{ selectedKey.keyValue || '-' }}</p>
      </div>
    </el-dialog>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
// 统一使用 Element 图标，替代此前的 emoji（emoji 字形与配色随系统变化，观感不统一）
import { MagicStick, TrendCharts, Setting } from '@element-plus/icons-vue'
import { SM2 } from 'gm-crypto'
import { BigInteger } from 'jsbn'
import { weierstrass } from '@noble/curves/abstract/weierstrass.js'
import { apiBases } from '@/config/api-bases'
import { batchGetGenerateChainStatus, createGenerateKey, getCommonParams, getGenerateKey, listGenerateKeys } from '@/services/generate-api'
import useUserStore from '@/store/modules/user'
import { roleLevelText } from '@/utils/role'
import { buildKeyFile, serializeKeyFile, suggestFileName } from '@/utils/key-file'
import useKeyringStore from '@/store/modules/keyring'
import KeyFileImport from '@/components/KeyFileImport/index.vue'

const userStore = useUserStore()
const keyring = useKeyringStore()
const keyFileImportRef = ref(null)

/** 导入成功后给一条反馈 —— 用户需要确认"哪把密钥现在能解开了" */
function handleKeyFileImported(keyFile) {
  ElMessage.success(`密钥 ${keyFile.key_id} 已可用于解密`)
}
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
// 密钥文件导出中的状态（P3 步骤 0b）
const exporting = ref(false)
const detailOpen = ref(false)
const resultOpen = ref(false)
const generateFormRef = ref(null)
const selectedKey = ref(null)
const localResult = ref({})
const keys = ref([])
const commonParams = ref(null)
const errorMessage = ref('')
const activeTab = ref('generate')
const encrytNameOptions = ref([])
const pqAlgorithms = ['PQ_FALCON', 'PQ_KYBER', 'PQ_CERTIFICATELESS', 'PQ_CL_KYBER', 'PQ_CL_FALCON', 'CL-Kyber', 'CL-Falcon']
const keyUseOptions = [
  { label: '签名 / 验签', value: '签名 / 验签' },
  { label: '密钥封装 / 解封装', value: '密钥封装 / 解封装' },
  { label: '加密 / 解密', value: '加密 / 解密' },
  { label: '密钥协商', value: '密钥协商' }
]

const profile = reactive({
  userId: '',
  userName: '',
  roleLevel: null
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

const maskedPrivateKey = computed(() => maskText(localMaterial.privateKey, 20))
const selectedPqMode = computed(() => parsePqMode(selectedKey.value?.keyValue) || selectedKey.value?.pqMode || selectedKey.value?.pq_mode || 'demo_generated')

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
    profile.roleLevel = value.roleLevel
    if (!value.token) {
      keys.value = []
      selectedKey.value = null
      return
    }
  },
  { immediate: true }
)

onMounted(async () => {
  handleEncrytTypeChange(generateForm.encrytType)
  await ensureProfile()
  fillDefaultFilters()
  await loadKeys()
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
      { label: 'SSCL', value: 'SSCL' },
      { label: 'CL-Falcon', value: 'CL-Falcon' },
      { label: 'CL-Kyber', value: 'CL-Kyber' }
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
  if (!pqAlgorithms.includes(generateForm.encrytName) && (!localMaterial.publicKey || !localMaterial.privateKey)) {
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
      pqMode: pqAlgorithms.includes(generateForm.encrytName) ? 'demo_generated' : undefined,
      uA: pqAlgorithms.includes(generateForm.encrytName) ? '' : localMaterial.publicKey,
      ua: pqAlgorithms.includes(generateForm.encrytName) ? '' : localMaterial.publicKey,
      operatorMetadata: {
        user_id: Number(profile.userId),
        user_name: profile.userName
      }
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
    pqMode: pqAlgorithms.includes(generateForm.encrytName) ? (parsePqMode(snapshot?.keyValue) || snapshot?.pqMode || snapshot?.pq_mode || 'demo_generated') : undefined,
    uA: pqAlgorithms.includes(generateForm.encrytName) ? '' : localMaterial.publicKey,
    clientPrivateKey: pqAlgorithms.includes(generateForm.encrytName) ? '' : localMaterial.privateKey
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

// ---------------------------------------------------------------------------
// 密钥文件导出（P3 步骤 0b）
// ---------------------------------------------------------------------------
/**
 * 是否具备导出密钥文件的条件。
 *
 * 需要三样东西同时具备：算出了最终私钥 `d_a`、是 SM2/SSCL（格算法不走这条路，
 * 它们的私钥在服务端）、以及登录用户已知（文件里要写 user_id）。
 */
const canExportKeyFile = computed(() => {
  const result = localResult.value || {}
  if (pqAlgorithms.includes(result.encrytName)) {
    return false
  }
  return Boolean(result.finalPrivateKey && userStore.id)
})

/**
 * 解析这份结果对应的 `key_id`。
 *
 * 创建接口是"提交后异步入库"（经 Kafka），响应里拿不到 keyId，
 * 所以这里回查列表、按「密钥名称 + 算法」取**最新的一条**。
 * 带重试是因为 Kafka 落库与列表刷新之间有个时间窗。
 */
async function resolveKeyIdFor(result) {
  if (result?.keyId) {
    return String(result.keyId)
  }
  const wantedName = normalizeText(result?.keyName)
  for (let attempt = 0; attempt < 8; attempt++) {
    try {
      const data = await listGenerateKeys({ pageNum: 1, pageSize: 50 })
      const rows = data?.rows || []
      const hit = rows.find((row) => row.keyName === wantedName && row.encrytName === result.encrytName)
      if (hit?.keyId) {
        return String(hit.keyId)
      }
    } catch {
      // 列表暂时查不到就继续重试；真正的失败在下面统一报出来
    }
    await new Promise((resolve) => setTimeout(resolve, 600))
  }
  return null
}

/**
 * 生成并下载密钥文件，同时把它存进本机密钥环。
 *
 * 为什么要"同时存进密钥环"：下载是**持久凭据**（换浏览器也能恢复），
 * 而写入密钥环让当前浏览器立刻就能解密，不必马上走一次导入。
 * 两者不冲突 —— 密钥环丢了还能用文件恢复。
 */
async function exportKeyFile() {
  const result = localResult.value || {}
  if (!canExportKeyFile.value) {
    ElMessage.warning('当前结果没有可导出的用户私钥')
    return
  }
  exporting.value = true
  try {
    const keyId = await resolveKeyIdFor(result)
    if (!keyId) {
      ElMessage.error('还没能在密钥列表里找到这条记录（入库可能仍在进行），请稍后重试')
      return
    }
    const keyFile = await buildKeyFile({
      keyId,
      userId: userStore.id,
      algorithm: result.encrytName,
      privateShare: result.finalPrivateKey,
      // P_A 不是秘密；带上它，导入时就能核对"这份私钥确实对应那把公钥"
      publicKey: result.finalPublicKey || ''
    })
    downloadText(serializeKeyFile(keyFile), suggestFileName(keyFile))
    await keyring.importKeyFile(keyFile)
    ElMessage.success(`密钥文件已下载，并已存入本机密钥环（密钥 ${keyId}）`)
  } catch (error) {
    ElMessage.error(`导出密钥文件失败：${error.message}`)
  } finally {
    exporting.value = false
  }
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
    const rows = data.rows || []
    const chainStatusMap = await batchGetGenerateChainStatus(rows.map((item) => item.keyId))
    keys.value = rows.map((item) => {
      const latestChainStatus = chainStatusMap?.[item.keyId]
      if (!latestChainStatus || typeof latestChainStatus !== 'object') {
        return item
      }
      return {
        ...item,
        chainStatus: latestChainStatus.chainStatus ?? item.chainStatus,
        chainHash: latestChainStatus.chainHash ?? item.chainHash,
        blockHeight: latestChainStatus.blockHeight ?? item.blockHeight,
        status: latestChainStatus.status ?? item.status
      }
    })
  } catch (error) {
    keys.value = []
    errorMessage.value = error.message
  } finally {
    listLoading.value = false
  }
}

/**
 * 执行筛选查询。
 * 此前该按钮标签为「刷新」，与其它页面的「查询」不一致，容易被误解为仅重新加载；
 * 现统一为「查询」，并支持在输入框内回车触发。
 */
function handleSearchKeys() {
  errorMessage.value = ''
  loadKeys()
}

function resetFilters() {
  filters.userId = profile.userId ? String(profile.userId) : ''
  filters.userName = profile.userName || ''
  filters.encrytName = ''
  loadKeys()
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
    `pq_mode: ${result.pqMode || result.pq_mode || ''}`,
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

function parsePqMode(keyValue) {
  const parsed = safeJsonParse(keyValue)
  return parsed?.pq_mode || parsed?.pqMode || parsed?.display?.pq_mode || ''
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
/* 密钥环那一行里嵌着按钮，需要覆盖 summary-card 的 default 小字样式 */
.keyring-line {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
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
  border: 1px solid var(--kms-border);
  border-radius: var(--kms-radius);
  background: var(--kms-surface-1);
  box-shadow: var(--kms-shadow-sm);
  transition: box-shadow var(--kms-transition), border-color var(--kms-transition);
}

.summary-card:hover, .material-card:hover {
  border-color: var(--kms-brand-border);
  box-shadow: var(--kms-shadow-md);
}

.summary-card strong,
.material-item strong {
  display: block;
  margin-top: 8px;
  font-size: 20px;
  color: var(--kms-text-primary);
  font-weight: 600;
}

.summary-card small,
.muted {
  color: var(--kms-text-secondary);
}

.summary-label,
.material-item span {
  font-size: 14px;
  color: var(--kms-text-secondary);
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
  /* 320px 是按「108px 标签 + 控件最小宽度」定的下限，不是随手写的数：
     原来写 220px，格子只有 220~240px 时控件（el-select 的 min-width 是 120px）
     会被挤到标签下面一行；再叠加下面那条 margin-bottom:0，两行就直接压字
     （用户截图里"算法类型"上压着"所属域"）。
     显式给 row-gap 是第二道保险：万一将来某格内容变高，行与行也不会互相叠。 */
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  row-gap: 16px;
}

/* 控件宁可收缩，也不折到标签下面 —— 折行才是"塌陷"的起点 */
.generate-form :deep(.el-form-item__content) {
  flex-wrap: nowrap;
  min-width: 0;
}

.profile-grid label {
  display: grid;
  gap: 6px;
}

.profile-grid input {
  width: 100%;
  padding: 12px 14px;
  border: 1px solid var(--kms-border-strong);
  border-radius: var(--kms-radius);
  background: var(--kms-surface-1);
  color: var(--kms-text-primary);
  transition: all var(--kms-transition);
}

.profile-grid input:focus {
  outline: none;
  border-color: var(--kms-brand);
  box-shadow: 0 0 0 2px var(--kms-brand-subtle);
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
  border-top: 1px solid var(--kms-border);
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

.pq-mode-note {
  display: grid;
  gap: 10px;
  padding: 16px;
  border: 1px solid var(--kms-info-border);
  border-radius: var(--kms-radius);
  background: var(--kms-info-subtle);
  color: var(--kms-text-secondary);
}

.material-item code {
  margin-top: 8px;
  padding: 12px 14px;
  border-radius: var(--kms-radius-sm);
  background: var(--kms-surface-2);
  border: 1px solid var(--kms-border);
  color: var(--kms-text-primary);
  font-family: var(--kms-font-mono);
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
  border: 1px dashed var(--kms-border-strong);
  border-radius: var(--kms-radius);
  background: var(--kms-surface-2);
}

.json-block {
  margin: 0;
  padding: 20px;
  border-radius: var(--kms-radius);
  background: var(--kms-surface-2);
  border: 1px solid var(--kms-border);
  color: var(--kms-text-primary);
  overflow-y: auto;
  max-height: 400px;
  white-space: pre-wrap;
  word-wrap: break-word;
  word-break: break-all;
  font-family: var(--kms-font-mono);
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
  background: var(--kms-surface-1);
  border: 1px solid var(--kms-border);
  border-radius: var(--kms-radius);
  padding: 12px;
}

.inner-sidenav .nav-item {
  padding: 12px 16px;
  border-radius: var(--kms-radius-sm);
  cursor: pointer;
  color: var(--kms-text-secondary);
  transition: all var(--kms-transition);
  display: flex;
  align-items: center;
  gap: 12px;
  font-weight: 500;
}

.inner-sidenav .nav-item:hover {
  background: var(--kms-surface-3);
  color: var(--kms-text-primary);
}

.inner-sidenav .nav-item.active {
  background: var(--kms-brand-subtle);
  color: var(--kms-brand-text);
  border: 1px solid var(--kms-brand-border);
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

/* 两列布局（左表单 + 右「本地材料」）在中等宽度会互相挤：
 * 侧栏最小 320px，留给表单的不到 400px，而表单每格本身最少也要 320px，
 * 于是侧栏文字直接压到表单控件上（1024px 实测）。
 * 1200px 以下改为上下堆叠 —— 原来的断点是 960px，够不着这个区间。
 */
@media (max-width: 1200px) {
  .generate-layout {
    grid-template-columns: 1fr;
  }
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
