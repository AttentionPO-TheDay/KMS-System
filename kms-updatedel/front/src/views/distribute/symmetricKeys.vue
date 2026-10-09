<template>
  <section class="page">
    <header class="page-head">
      <div>
        <h2>对称密钥查看</h2>
        <p class="page-desc">
          这里是分发给你本人的对称密钥信封。信封只能在<strong>本机</strong>用你的密钥文件解开 ——
          服务端不保存明文对称密钥，也不持有你的私钥。有效期 24 小时。
        </p>
      </div>
      <key-file-import @imported="handleImported" />
    </header>

    <el-alert
      v-if="keyring.size === 0"
      title="本机还没有导入任何密钥文件。请先在「密钥生成」页下载密钥文件，再用右上角「导入密钥文件」导入，之后才能解开下面的信封。"
      type="info"
      :closable="false"
      show-icon
      class="mb16"
    />

    <el-card class="panel" shadow="never">
      <template #header>
        <div class="panel-head">
          <span>我的对称密钥（{{ items.length }}）</span>
          <div class="panel-actions">
            <el-checkbox v-model="includeExpired" @change="load">显示已过期</el-checkbox>
            <el-button link type="primary" @click="load">刷新</el-button>
          </div>
        </div>
      </template>

      <el-table :data="items" size="small" v-loading="loading" empty-text="还没有分发给你本人的对称密钥">
        <el-table-column label="信封ID" prop="id" width="80" />
        <el-table-column label="批次号" prop="batchId" min-width="180" show-overflow-tooltip />
        <el-table-column label="封装算法" prop="wrappingAlgorithm" width="90" />
        <el-table-column label="来源密钥" prop="sourceKeyId" width="90" />
        <el-table-column label="剩余有效期" width="120">
          <template #default="scope">
            <el-tag size="small" :type="remainingType(scope.row)">{{ remainingText(scope.row) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="本机密钥" width="100">
          <template #default="scope">
            <el-tag v-if="keyring.has(scope.row.sourceKeyId)" size="small" type="success" effect="plain">已导入</el-tag>
            <el-tag v-else size="small" type="info" effect="plain">缺失</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="scope">
            <el-button link type="primary" @click="openDetail(scope.row)">查看</el-button>
            <el-button
              link
              type="success"
              :disabled="!keyring.has(scope.row.sourceKeyId)"
              @click="decryptEnvelope(scope.row)"
            >
              解开
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ------------------------------------------------------------------
         详情 / 解密结果
         ------------------------------------------------------------------ -->
    <el-dialog v-model="detailOpen" title="对称密钥信封" width="720px" append-to-body destroy-on-close>
      <el-descriptions v-if="current" :column="2" border size="small">
        <el-descriptions-item label="信封ID">{{ current.id }}</el-descriptions-item>
        <el-descriptions-item label="批次号">{{ current.batchId }}</el-descriptions-item>
        <el-descriptions-item label="封装算法">{{ current.wrappingAlgorithm }}</el-descriptions-item>
        <el-descriptions-item label="来源密钥">{{ current.sourceKeyId }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ formatTime(current.createdAt) }}</el-descriptions-item>
        <el-descriptions-item label="过期时间">{{ formatTime(current.expiresAt) }}</el-descriptions-item>
        <el-descriptions-item label="密钥指纹" :span="2">
          <code class="fingerprint">{{ current.keyHash }}</code>
        </el-descriptions-item>
      </el-descriptions>

      <!--
        解开结果：**只在本机**算出来，不外发、不落任何持久存储。
        解出来的密钥会与库中记录的 keyHash 比对 —— 只显示"解出了 32 位十六进制"
        没有意义，任何 32 位十六进制都满足；必须证明解出的**正是那把**密钥。
      -->
      <div v-if="decryptedHex" class="decrypted-box mt16">
        <p class="decrypted-title">已用本机密钥解开</p>
        <p class="decrypted-line">
          <span>SM4 密钥（十六进制）</span>
          <code class="secret">{{ decryptedHex }}</code>
        </p>
        <p class="decrypted-line">
          <span>与库中记录比对</span>
          <el-tag size="small" :type="decryptedMatches ? 'success' : 'danger'">
            {{ decryptedMatches ? '指纹一致' : '不一致！' }}
          </el-tag>
        </p>
        <p class="muted">
          这个值只在本机算出，没有发给服务端。对称密钥 24 小时后失效，届时信封无法再解开。
        </p>
      </div>

      <el-alert v-if="decryptError" type="error" :closable="false" show-icon class="mt16">
        {{ decryptError }}
      </el-alert>

      <el-alert v-if="detailError" type="error" :closable="false" show-icon class="mt16">
        {{ detailError }}
      </el-alert>

      <template #footer>
        <el-button @click="detailOpen = false">关 闭</el-button>
        <el-button
          v-if="current && keyring.has(current.sourceKeyId)"
          type="primary"
          :loading="decrypting"
          @click="decryptEnvelope(current)"
        >
          用本机密钥解开
        </el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup>
/**
 * 对称密钥查看页（P3 步骤 9）。
 *
 * 本页承担两件事：
 *   1. 列出分发给我本人的信封（服务端只存密文，**不存明文对称密钥**）；
 *   2. 显示本机密钥环里有没有对应的密钥文件（决定这份信封当前能否被解开）。
 *
 * 本机解密已经接入 `sm2-envelope.js`：浏览器本地执行 SM3、KDF、C3 校验，
 * 并把解出的密钥与服务端保存的 keyHash 比对。`d_A` 和明文只在本机短暂存在，
 * 不发送给服务端，也不写入持久存储。
 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import KeyFileImport from '@/components/KeyFileImport/index.vue'
import useKeyringStore from '@/store/modules/keyring'
import { getMySymmetricKey, listMySymmetricKeys } from '@/services/user-distribution-api'
import { decryptToHex } from '@/utils/sm2-envelope.js'

const keyring = useKeyringStore()

const items = ref([])
const loading = ref(false)
const includeExpired = ref(false)

const detailOpen = ref(false)
const current = ref(null)
const detailError = ref('')

// 解开结果：只在本机存在，页面关闭即丢，不写任何持久存储
const decrypting = ref(false)
const decryptedHex = ref('')
const decryptedMatches = ref(false)
const decryptError = ref('')

async function load() {
  loading.value = true
  try {
    const data = await listMySymmetricKeys({
      limit: 200,
      includeExpired: includeExpired.value ? '1' : ''
    })
    items.value = data?.items || []
  } catch (error) {
    ElMessage.error(`加载对称密钥失败：${error.message}`)
  } finally {
    loading.value = false
  }
}

/** 导入密钥文件后只需重渲染 —— "本机密钥"那一列依赖密钥环状态 */
function handleImported() {
  ElMessage.success('密钥已导入；对应的信封现在可以解开了')
}

async function openDetail(row) {
  current.value = row
  detailError.value = ''
  decryptedHex.value = ''
  decryptedMatches.value = false
  decryptError.value = ''
  detailOpen.value = true
  try {
    // 列表只含摘要，这里补取密文与指纹等完整字段
    const detail = await getMySymmetricKey(row.id)
    current.value = { ...row, ...detail }
  } catch (error) {
    detailError.value = `取详情失败：${error.message}`
  }
}

/**
 * 用本机密钥信封里的 `d_A` 解开这个信封。
 *
 * 密码学全部发生在**本机**：`sm2-envelope.js` 自带 SM3（浏览器不提供）与椭圆曲线运算，
 * 两者都已用国标向量验证过。`d_A` 与解出的明文**都不会离开浏览器** ——
 * 这正是"服务端也解不开"这条保证的落地方式。
 */
async function decryptEnvelope(row) {
  decryptError.value = ''
  decryptedHex.value = ''
  decryptedMatches.value = false

  const keyFile = keyring.get(row.sourceKeyId)
  if (!keyFile) {
    decryptError.value = `本机没有密钥 ${row.sourceKeyId} 的密钥文件，无法解开。请先导入。`
    return
  }

  // 结果展示在详情弹窗里，所以从列表行点「解开」时**必须把弹窗打开** ——
  // 否则值算出来了却没有地方显示，现象是"点了没反应、也没有报错"，很难查。
  current.value = row
  detailOpen.value = true

  decrypting.value = true
  try {
    const detail = await getMySymmetricKey(row.id)
    const envelope = typeof detail?.encryptedKeyData === 'string'
      ? JSON.parse(detail.encryptedKeyData)
      : detail?.encryptedKeyData
    if (!envelope) {
      throw new Error('信封内容为空')
    }

    const hex = decryptToHex(envelope, keyFile.private_share)
    decryptedHex.value = hex
    // 只显示"解出了 32 位十六进制"没有意义 —— 任何 32 位十六进制都满足。
    // 必须与库中记录的指纹比对，才能证明解出的**正是那把**密钥。
    decryptedMatches.value = await matchesRecordedHash(hex, detail?.keyHash)
    if (!decryptedMatches.value) {
      decryptError.value = '解出的密钥指纹与库中记录不一致，这份信封可能已被篡改。'
    }
  } catch (error) {
    decryptError.value = `${error.name === 'Sm2IntegrityError' ? '完整性校验失败' : '解封失败'}：${error.message}`
  } finally {
    decrypting.value = false
  }
}

async function matchesRecordedHash(keyHex, recorded) {
  if (!recorded) {
    return false
  }
  const bytes = new Uint8Array(keyHex.match(/.{2}/g).map((b) => parseInt(b, 16)))
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  const hex = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')
  return hex === String(recorded).toLowerCase()
}

function remainingText(row) {
  if (row.expired || row.remainingSeconds <= 0) {
    return '已过期'
  }
  const seconds = row.remainingSeconds
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  return hours > 0 ? `${hours} 小时 ${minutes} 分` : `${minutes} 分`
}

function remainingType(row) {
  if (row.expired || row.remainingSeconds <= 0) {
    return 'info'
  }
  return row.remainingSeconds < 3600 ? 'warning' : 'success'
}

function formatTime(value) {
  if (!value) {
    return '-'
  }
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN', { hour12: false })
}

onMounted(load)
</script>

<style scoped>
.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.page-head h2 {
  margin: 0 0 4px;
  font-size: 18px;
}

.page-desc {
  margin: 0 0 16px;
  color: var(--kms-text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.panel {
  border-radius: 10px;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.panel-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* 解密结果框：只在本机显示，页面关闭即丢 */
.decrypted-box {
  padding: 12px;
  border: 1px solid var(--el-color-success-light-5);
  border-radius: 8px;
  background: var(--el-color-success-light-9);
}

.decrypted-title {
  margin: 0 0 8px;
  font-weight: 600;
}

.decrypted-line {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 4px 0;
  font-size: 13px;
}

.secret {
  font-family: var(--el-font-family-mono, monospace);
  word-break: break-all;
}

.muted {
  margin: 8px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.fingerprint {
  font-family: var(--kms-font-mono, monospace);
  font-size: 12px;
  word-break: break-all;
}

.decrypted-box {
  padding: 12px 14px;
  border: 1px solid var(--kms-success-border, #b7ebc6);
  border-radius: 8px;
  background: var(--kms-success-bg, #f2fbf5);
}

.decrypted-title {
  margin: 0 0 8px;
  font-weight: 600;
}

.decrypted-line {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 4px 0;
  font-size: 13px;
}

.secret {
  font-family: var(--kms-font-mono, monospace);
  word-break: break-all;
}

.muted {
  margin: 8px 0 0;
  color: var(--kms-text-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.mb16 {
  margin-bottom: 16px;
}

.mt16 {
  margin-top: 16px;
}
</style>
