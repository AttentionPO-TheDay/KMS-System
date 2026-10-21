<template>
  <!-- 独立页面（路由不经 `Layout`，与 `/login` 同级）：没有侧边栏/顶部菜单。
       这页是**闸门**不是系统内页 —— 挂上完整导航会让人误以为已经进系统。
       页面自带退出登录，避免"没有导航、也走不掉"的死角。 -->
  <div class="node-init-page">
    <div class="node-init-page__bar">
      <span class="node-init-page__brand">KMS · {{ pageTitle }}</span>
      <div>
        <el-button v-if="IS_DEMO" link size="small" :disabled="initializing" @click="openAdmin">管理控制台</el-button>
        <el-button link size="small" :disabled="initializing" @click="handleLogout">退出登录</el-button>
      </div>
    </div>
    <div class="node-init-page__inner">
      <el-card shadow="never" class="node-init__card">
        <template #header>
          <div class="node-init__header">
            <h2>{{ pageTitle }}</h2>
            <el-tag :type="statusTagType" size="large">{{ statusText }}</el-tag>
          </div>
        </template>

      <!-- 账号没关联节点：这是管理员账号，或数据异常 -->
      <el-alert
        v-if="!loading && !mapped"
        type="warning"
        :closable="false"
        show-icon
        title="当前账号未关联任何节点"
      />

      <template v-else>
        <p v-if="isActive && blocked" class="node-init__lead">
          节点已激活，当前浏览器缺少匹配的本机密钥材料。
        </p>

        <el-descriptions :column="2" border class="node-init__meta">
          <el-descriptions-item label="节点ID">{{ node.nodeId || '-' }}</el-descriptions-item>
          <el-descriptions-item label="节点名称">{{ node.name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="权限等级">{{ node.permissionLevel || '-' }}</el-descriptions-item>
          <el-descriptions-item label="所属域">{{ node.domainId || '-' }}</el-descriptions-item>
          <el-descriptions-item label="节点状态">{{ statusText }}</el-descriptions-item>
          <el-descriptions-item label="初始化时间">{{ node.initializedAt || '-' }}</el-descriptions-item>
        </el-descriptions>

        <!-- 四套密钥就绪情况。首次初始化仍要求四套齐备；节点激活后，某套密钥
             进入已回收等生命周期终态时只影响对应业务，不再阻断整个工作台。 -->
        <h3 class="node-init__section-title">基础密钥</h3>
        <div class="node-init__keys">
          <div
            v-for="k in keyCards"
            :key="k.key"
            class="node-init__key"
            :class="{ 'is-ready': k.ready }"
          >
            <div class="node-init__key-name">{{ k.label }}</div>
            <el-tag :type="k.tagType" size="small">
              {{ k.ready ? '登记一致 · 本机可读' : k.text }}
            </el-tag>
          </div>
        </div>

        <h3 v-if="isActive" class="node-init__section-title">改进型无证书格加密（实验版 v1）</h3>
        <p>{{ encryptionStatus }}</p>
        <el-button v-if="isActive" :disabled="!node.falconClCapability?.enabled || encryptionRegistered || encryptionBusy || blocked" :loading="encryptionBusy" @click="handleEncryptionInit">初始化加密密钥</el-button>
        <el-button v-if="encryptionBusy" @click="encryptionController?.abort()">取消矩阵运算</el-button>
        <el-alert
          v-if="ready"
          class="node-init__done"
          type="success"
          :closable="false"
          show-icon
          title="初始化已完成"
        />
        <el-alert
          v-else-if="workspaceReady && lifecycleUnavailableCount"
          class="node-init__done"
          type="warning"
          :closable="false"
          show-icon
          title="节点可继续使用，部分算法暂无可用密钥"
        />

        <!-- §4.4 设备绑定：本机不是当初生成密钥的那台设备。
             必须显式说明"不是你坏了"，否则用户只会看到"解不开信封"而无从判断。 -->
        <el-alert
          v-if="deviceMismatch"
          class="node-init__device"
          type="error"
          :closable="false"
          show-icon
          title="本机没有该节点的私钥"
        >
          <template #default>
            <ul class="node-init__device-options">
              <li><strong>续用原设备</strong>：改回原设备登录，本机不做任何改动。</li>
              <li>
                <strong>改用本机</strong>：恢复原本机材料，或通过密钥更新与回收流程换钥。
              </li>
            </ul>
          </template>
        </el-alert>

        <el-alert v-if="blocked" class="node-init__device" type="error" :closable="false" show-icon
          :title="isActive ? '节点已激活，但当前入口缺少密钥材料' : '密钥材料需恢复，已禁止自动初始化或覆盖'">
          <p v-for="reason in inspection.reasons" :key="reason">{{ reason }}</p>
          <p>请返回原浏览器或恢复本机材料；换钥请使用密钥更新与回收。</p>
        </el-alert>
        <el-alert v-if="!locksAvailable" class="node-init__device" type="warning" :closable="false" show-icon
          title="浏览器不支持 Web Locks，初始化已关闭；请使用支持安全锁的浏览器和可信入口" />

        <div class="node-init__actions">
          <el-button
            v-if="!isActive"
            type="primary"
            size="large"
            :loading="initializing"
            :disabled="loading || !mapped || blocked || deviceMismatch || !locksAvailable"
            @click="handleInit"
          >
            {{ initializing ? '正在初始化…' : hasPartialMaterials ? '继续初始化（复用已有材料）' : '开始初始化' }}
          </el-button>
          <el-button v-if="workspaceReady" type="primary" size="large" :disabled="loading || initializing" @click="goWorkbench">
            进入工作台
          </el-button>
          <el-button :disabled="initializing" @click="load">刷新状态</el-button>
        </div>

        <!-- 逐套的进展。四套是串行生成的，用户需要看到"卡在哪一步" ——
             否则界面上只有一个转圈的按钮，卡住时完全无从判断。 -->
        <div v-if="progress.length" class="node-init__progress">
          <p v-for="line in progress" :key="line.algorithm" class="node-init__progress-line">
            <el-icon v-if="initializing && line.status !== 'complete' && line.status !== 'failed'" class="is-loading"><Loading /></el-icon>
            <el-tag v-else :type="line.status === 'complete' ? 'success' : 'danger'" size="small">{{ line.status === 'complete' ? '完成' : '失败' }}</el-tag>
            <span>{{ line.message }}</span>
          </p>
        </div>

        <!-- 时间预期。⚠️ §4.4 起密钥在**本机**生成，不再有服务端那 15~25 秒，
             但 Falcon 的 keygen 仍是最慢的一步，所以仍要告知。
             文案改过：原文写的是"初始化会依次生成…"，
             现在准确的说法是"在本机依次生成并登记公钥"。
             ⚠️ 模板里**不能写 Markdown**（`**粗体**` 会原样显示成星号），
                强调要用 <strong>。 -->
        <p v-if="!isActive" class="node-init__hint">
          初始化期间请勿关闭页面或重复点击。
        </p>
      </template>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { markNodeInitialized, resetNodeInitStatusCache } from '@/utils/node-init-status'
import { inspectInitialization, initializeNode, generateAndRegisterNodeKey } from '@/utils/node-initialization'
import { listSelfNodeKeys } from '@/api/pqkds/node-self'
import { cryptoProvider } from '@/utils/crypto/browser-provider.js'
import { buildKeyRef } from '@/utils/crypto/key-ref.js'
import { hasDeviceKey } from '@/utils/crypto/device-credential.js'
import { IS_DEMO, entryPath } from '@/utils/entry-mode'
import { switchDemo } from '@/utils/demo-context'
import { formatGenerationName, coreDetail, GENERATION_SCHEMES } from '@/utils/crypto/generation-scheme.js'
import { canEnterNodeWorkspace } from '@/utils/node-workspace-access'
import useUserStore from '@/store/modules/user'

const router = useRouter()
const userStore = useUserStore()

const loading = ref(true)
const initializing = ref(false)
const mapped = ref(false)
const node = ref({})
const progress = ref([])
const encryptionBusy = ref(false)
const encryptionRegistered = ref(false)
const encryptionStatus = ref('尚未检查独立加密能力。')
let encryptionController
onBeforeUnmount(() => encryptionController?.abort())
async function handleEncryptionInit() {
  if (encryptionBusy.value || encryptionRegistered.value || !node.value.falconClCapability?.enabled) return
  encryptionBusy.value = true
  encryptionController = new AbortController()
  try {
    await generateAndRegisterNodeKey({ algorithm: 'FALCON_CL_V1', nodeId: node.value.nodeId, variant: 512, signal: encryptionController.signal,
      confirmUnusedIssuance: async record => { await ElMessageBox.confirm(record.message, '明确弃用未完成部分签发', { type: 'warning' }); return true }
    })
    ElMessage.success('独立 ENCRYPT 公钥已登记，完整私钥只保留在本机')
  } catch (error) { ElMessage.error(error.message) }
  finally { encryptionBusy.value = false; encryptionController = null; await load() }
}
const inspection = ref({ ready: false, blocked: false, algorithms: [], reasons: [] })
const ready = computed(() => inspection.value.ready)
const blocked = computed(() => inspection.value.blocked)
const workspaceReady = computed(() => canEnterNodeWorkspace(inspection.value))
const lifecycleUnavailableCount = computed(() => inspection.value.algorithms.filter(step => step.lifecycleUnavailable).length)
const hasPartialMaterials = computed(() => inspection.value.algorithms.some(step => step.local || step.complete))
const locksAvailable = Boolean(globalThis.navigator?.locks?.request)

const KEY_META = [
  { key: 'kyber', label: 'Kyber', role: '后量子密钥封装 / 建立共享秘密' },
  { key: 'sscl', label: 'SSCL', role: '保护 / 封装 SM4 会话密钥' },
  { key: 'sm2', label: 'SM2', role: '保护 / 封装 SM4 会话密钥' },
  { key: 'falcon', label: 'Falcon', role: '对分发消息签名与验签' },
  { key: 'falcon_cl_v1', label: '改进型无证书格加密（实验版 v1）', role: '保护 / 封装 SM4 会话密钥' }
]

const keyCards = computed(() => KEY_META.filter(meta => inspection.value.algorithms.some(row => row.algorithm === meta.key.toUpperCase())).map(meta => {
  const step = inspection.value.algorithms.find(row => row.algorithm === meta.key.toUpperCase())
  const algorithm = meta.key.toUpperCase()
  const source = step?.server || step?.latestServer || step?.local
  const lifecycleText = step?.state === 'REVOKED'
    ? '已回收 · 暂无可用版本'
    : step?.lifecycleUnavailable ? '暂无当前可用版本' : ''
  return { ...meta, label: formatGenerationName(algorithm, source ? source.generation : GENERATION_SCHEMES[algorithm]),
    core: coreDetail(algorithm, source?.variant || source?.securityLevel),
    ready: Boolean(step?.complete), tagType: step?.complete ? 'success' : step?.lifecycleUnavailable ? 'warning' : 'info',
    text: lifecycleText || (step?.blocked ? '需恢复材料' : step?.local ? '本机已封存 · 待登记' : '尚未生成') }
}))

const statusText = computed(() => {
  const s = node.value.status
  if (s === 'ACTIVE') return '已激活'
  if (s === 'DISABLED') return '已停用'
  return '待初始化'
})

const statusTagType = computed(() => {
  const s = node.value.status
  if (s === 'ACTIVE') return 'success'
  if (s === 'DISABLED') return 'danger'
  return 'warning'
})

const isActive = computed(() => node.value.status === 'ACTIVE')
const pageTitle = computed(() => isActive.value ? (blocked.value ? '节点密钥材料恢复' : '节点密钥状态') : '节点首次初始化')

// ---------------------------------------------------------------------------
// §4.4 设备绑定
// ---------------------------------------------------------------------------
// 判据是「**本机有没有该节点的设备私钥**」，不是比对某个字符串。
//
// 改造前这里比的是 `node.keyDeviceId`（服务端记的）与本机 `getDeviceId()`
// （浏览器级随机串、明文存在 IndexedDB）。那套是**自报身份**：任何脚本都能改
// 本机那个值，服务端也验证不了 —— `Node.key_device_id` 的模型注释自己就写明
// "不是密码学证明"。
//
// 现在用设备凭据（§3.1）：本机私钥**不可导出**，签得出名就证明是那台设备。
// 所以"本机不是当初那台"的正确判据是：**服务端登记了设备公钥，而本机没有对应私钥**。
// 既更准，也把"换台机器"从不置可否变成可验证。
//
// 不做这件事的后果是静默的：界面一切正常，直到某天某个信封解不开，
// 而那时已经很难追到"是因为换了设备"。
const hasDeviceCredential = ref(false)

const deviceMismatch = computed(() => {
  if (IS_DEMO) return false
  // 服务端还没登记设备公钥 → 该节点还没在**任何**设备上激活过，
  // 谈不上"换设备"（真走那条路会先被登录页的激活流程拦住）。
  const boundOnServer = Boolean(String(node.value.keyDeviceId || '').trim())
  if (!boundOnServer) return false
  // 服务端已绑定 + 本机签不出名 → 本机不是那台设备。
  // 本机有私钥说明就是当初那台（或至少能继续做下去），不该拦。
  return !hasDeviceCredential.value
})

function acceptInspection(data) {
  inspection.value = data
  mapped.value = data.mapped
  node.value = data.node
  if (canEnterNodeWorkspace(data)) markNodeInitialized()
  else resetNodeInitStatusCache()
}

async function load() {
  loading.value = true
  try {
    acceptInspection(await inspectInitialization())
    if (mapped.value) {
      const keys = (await listSelfNodeKeys()).keys || []
      const row = keys.find(k => k.algorithm === 'FALCON_CL_V1' && k.allowsNewWork)
      encryptionRegistered.value = keys.some(k => k.algorithm === 'FALCON_CL_V1')
      const locals = await cryptoProvider.listLocalKeys()
      const ref = row && buildKeyRef({ nodeId: node.value.nodeId, algorithm: row.algorithm, keyId: row.keyId, version: row.keyVersion })
      const local = ref && locals.find(k => k.keyRef === ref)
      encryptionStatus.value = !node.value.falconClCapability?.enabled ? '独立审查开关尚未启用。' : row && local?.publicKey === row.publicKey && await cryptoProvider.hasKey(ref) ? '独立 ENCRYPT v1 已就绪，登记与本机材料匹配。' : encryptionRegistered.value ? '已有加密登记，但本机缺失/版本不可用：请恢复原材料，不自动重置。' : '尚无独立加密材料，请主动补充初始化。'
    }
    // Demo never reads or creates device credentials/fingerprints.
    if (!IS_DEMO && mapped.value) hasDeviceCredential.value = await hasDeviceKey(node.value.nodeId)
  } catch (error) {
    inspection.value = { ready: false, blocked: true, algorithms: [], reasons: [`无法安全读取节点材料：${error.message}`] }
    resetNodeInitStatusCache()
    ElMessage.error(`读取节点状态失败：${error.message}`)
  } finally {
    loading.value = false
  }
}

function updateProgress(step) {
  const index = progress.value.findIndex(row => row.algorithm === step.algorithm)
  if (index < 0) progress.value.push(step)
  else progress.value[index] = step
}

async function handleInit() {
  if (initializing.value || loading.value || blocked.value || deviceMismatch.value || isActive.value || !locksAvailable) return
  initializing.value = true
  progress.value = []
  try {
    acceptInspection(await initializeNode({ onProgress: updateProgress,
      confirmUnusedIssuance: async record => {
        await ElMessageBox.confirm(record.message, '确认恢复未完成签发', { type: 'warning', confirmButtonText: '弃用未使用签发并重试', cancelButtonText: '取消，不换钥' })
        return true
      }
    }))
    ElMessage.success('四套基础公钥与本机材料一致，节点已激活')
  } catch (error) {
    const at = [...progress.value].reverse().find(row => row.status !== 'complete') || { algorithm: 'CHECK', message: '初始化检查' }
    updateProgress({ ...at, status: 'failed', message: `${at.message} 失败：${error.message}` })
    ElMessage.error(`${error.message}（已封存材料与已登记公钥会保留，重试不会重新生成）`)
    await load()
  } finally {
    initializing.value = false
  }
}

function goWorkbench() {
  if (workspaceReady.value) router.push(entryPath('/workbench', 'NODE'))
}

async function openAdmin() {
  try { await switchDemo('ADMIN') } catch (error) { ElMessage.error(error.message) }
}

/**
 * 退出登录（独立页面自带，见模板顶栏）。
 *
 * 为什么这页必须有自己的出口：路由不再经 `Layout`，顶栏那套「注销」
 * 就不存在了 —— 若这里不给出口，一个登错账号的人（或节点还没想好要不要
 * 初始化的用户）会停在一个"没有导航、也走不掉"的页面上。
 * 与 Navbar 的注销同一套动作（`userStore.logOut()`），失败也放行跳转：
 * 令牌清了、服务端没清掉是不一致，但**不让用户卡死在这页**更重要。
 */
async function handleLogout() {
  try {
    await userStore.logOut()
  } catch (error) {
    if (IS_DEMO) {
      ElMessage.error(`退出演示失败：${error.message}`)
      return
    }
  }
  // Demo logout owns its full-document boundary; do not override it with the old login route.
  if (!IS_DEMO) router.push('/login')
}

onMounted(load)
</script>

<style scoped>
/* 独立页外壳：与 /login 同级、不套 Layout —— 全高背景 + 居中内容。
   没有侧边栏与顶部菜单是**刻意的**（这页是闸门不是系统内页），
   顶栏只留品牌名与「退出登录」。 */
.node-init-page {
  min-height: 100vh;
  background: var(--el-bg-color-page, #f5f7fa);
  padding: 0 16px 32px;
}
.node-init-page__bar {
  max-width: 980px;
  margin: 0 auto;
  padding: 14px 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.node-init-page__brand { font-weight: 600; color: var(--el-text-color-primary, #303133); }
.node-init-page__inner { max-width: 980px; margin: 8px auto 0; }
.node-init__card { border-radius: 10px; }
.node-init__header { display: flex; align-items: center; justify-content: space-between; }
.node-init__header h2 { margin: 0; font-size: 18px; }
.node-init__lead { margin: 0 0 16px; color: var(--kms-text-secondary, #606266); line-height: 1.7; }
.node-init__meta { margin-bottom: 24px; }
.node-init__section-title { margin: 0 0 12px; font-size: 15px; }
.node-init__keys {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px; margin-bottom: 20px;
}
.node-init__key {
  border: 1px solid var(--el-border-color, #dcdfe6); border-radius: 6px;
  padding: 12px 14px; display: flex; flex-direction: column; gap: 6px;
}
.node-init__key.is-ready { border-color: var(--el-color-success, #67c23a); }
.node-init__key-name { font-weight: 600; }
.node-init__key-role { font-size: 12px; color: var(--kms-text-secondary, #909399); line-height: 1.5; }
.node-init__done { margin-bottom: 20px; }
.node-init__actions { display: flex; gap: 12px; }
.node-init__hint {
  margin: 16px 0 0; color: var(--kms-text-secondary, #909399);
  font-size: 13px; line-height: 1.7;
}
.node-init__progress { margin-top: 16px; padding: 12px 14px; border-radius: 6px;
  background: var(--el-fill-color-light, #f5f7fa); }
.node-init__progress-line { display: flex; align-items: center; gap: 8px;
  margin: 4px 0; font-size: 13px; color: var(--kms-text-secondary, #606266); }
.node-init__device { margin-bottom: 16px; }
.node-init__device p { margin: 6px 0; line-height: 1.7; }
.node-init__device-options { margin: 6px 0 0; padding-left: 20px; line-height: 1.9; }
</style>
