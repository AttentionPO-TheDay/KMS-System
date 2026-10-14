<template>
  <section class="page">
    <header class="page-head">
      <div>
        <h2>已分发对称密钥</h2>
        <p class="page-desc">
          这里显示当前节点收到的节点间分发信封。服务端只保存密文，SM4 明文只在本机解封后进入本机会话密钥库。
        </p>
      </div>
      <el-button :loading="loading" @click="load">刷新</el-button>
    </header>

    <el-alert
      v-if="!loading && !mapped"
      title="当前账号没有关联节点"
      description="管理员账号不能查看节点收件箱，请从节点入口进入。"
      type="info"
      :closable="false"
      show-icon
      class="mb16"
    />

    <el-alert
      v-if="mapped && !loading && !items.length"
      title="暂未收到节点分发信封"
      description="如果刚刚完成分发，请点击刷新。分发记录以节点收件箱为准，不再读取旧的“分发给本人”接口。"
      type="info"
      :closable="false"
      show-icon
      class="mb16"
    />

    <el-card v-if="mapped" class="panel" shadow="never">
      <template #header>
        <div class="panel-head">
          <span>节点收件箱（{{ items.length }}）</span>
          <el-checkbox v-model="includeExpired" @change="load">显示已过期</el-checkbox>
        </div>
      </template>

      <el-table :data="items" size="small" v-loading="loading" empty-text="暂无节点分发记录">
        <el-table-column label="信封 ID" prop="envelopeId" width="90" />
        <el-table-column label="批次号" prop="poolId" min-width="180" show-overflow-tooltip />
        <el-table-column label="会话 ID" prop="sessionId" min-width="190" show-overflow-tooltip />
        <el-table-column label="方向" width="90">
          <template #default="scope">{{ scope.row.isSender ? '我发起' : '我接收' }}</template>
        </el-table-column>
        <el-table-column label="来源节点" prop="senderNode" min-width="130" show-overflow-tooltip />
        <el-table-column label="封装算法" prop="wrappingAlgorithm" width="110" />
        <el-table-column label="状态" width="110">
          <template #default="scope">
            <el-tag size="small" :type="statusType(scope.row)">{{ statusLabel(scope.row) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="本机副本" width="110">
          <template #default="scope">
            <el-tag v-if="scope.row.hasLocalSecret" size="small" type="success" effect="plain">已保存</el-tag>
            <el-tag v-else size="small" type="info" effect="plain">待解封</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="过期时间" min-width="170">
          <template #default="scope">{{ formatTime(scope.row.expiresAt) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="scope">
            <el-button link type="primary" @click="openDetail(scope.row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="detailOpen" title="节点分发信封" width="680px" append-to-body destroy-on-close @closed="localSecretHex = ''">
      <el-descriptions v-if="current" :column="2" border size="small">
        <el-descriptions-item label="信封 ID">{{ current.envelopeId || '发送方本地会话' }}</el-descriptions-item>
        <el-descriptions-item label="批次号">{{ current.poolId || '-' }}</el-descriptions-item>
        <el-descriptions-item label="会话 ID" :span="2">{{ current.sessionId || '暂无关联会话' }}</el-descriptions-item>
        <el-descriptions-item label="来源节点">{{ current.senderNode || '-' }}</el-descriptions-item>
        <el-descriptions-item label="封装算法">{{ current.wrappingAlgorithm || '-' }}</el-descriptions-item>
        <el-descriptions-item label="密钥摘要" :span="2"><code>{{ current.keyHash || '-' }}</code></el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ formatTime(current.createdAt) }}</el-descriptions-item>
        <el-descriptions-item label="过期时间">{{ formatTime(current.expiresAt) }}</el-descriptions-item>
      </el-descriptions>
      <el-alert
        v-if="current && !current.hasLocalSecret"
        class="mt16"
        type="warning"
        :closable="false"
        show-icon
        title="这条信封还没有本机密钥副本"
        description="请到“会话管理”执行验签和解封。解封成功后，本机副本会出现在这里。"
      />
      <el-alert
        v-else-if="current"
        class="mt16"
        type="success"
        :closable="false"
        show-icon
        title="对称密钥已保存在本机"
        description="页面只展示本机副本状态，不把 SM4 明文回传或写入服务端。"
      />
      <div v-if="localSecretHex" class="secret-box mt16">
        <span>本机解封出的 SM4 密钥</span>
        <code>{{ localSecretHex }}</code>
        <small>仅当前页面临时显示，刷新或关闭详情后清除。</small>
      </div>
      <template #footer>
        <el-button @click="detailOpen = false">关闭</el-button>
        <el-button
          v-if="current?.hasLocalSecret"
          type="primary"
          :loading="revealing"
          @click="revealLocalSecret"
        >显示本机密钥</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getSelfNode, listSelfEnvelopes, listSelfSessions } from '@/api/pqkds/node-self'
import { hasSessionSecret, unsealSessionSecret } from '@/utils/crypto/node-key-store.js'

const loading = ref(false)
const mapped = ref(false)
const includeExpired = ref(false)
const items = ref([])
const detailOpen = ref(false)
const current = ref(null)
const revealing = ref(false)
const localSecretHex = ref('')

async function load() {
  loading.value = true
  try {
    const node = await getSelfNode()
    mapped.value = node?.mapped === true
    if (!mapped.value) {
      items.value = []
      return
    }
    const [envelopeData, sessionData] = await Promise.all([
      listSelfEnvelopes({ includeExpired: includeExpired.value, limit: 500 }),
      listSelfSessions({ includeExpired: includeExpired.value, limit: 500 })
    ])
    const sessions = new Map((sessionData?.items || []).map((session) => [session.sessionId, session]))
    const rows = []
    for (const envelope of envelopeData?.items || []) {
      const session = sessions.get(envelope.sessionId)
      rows.push({
        ...envelope,
        senderNode: session?.senderNode || '-',
        recipientNode: session?.recipientNode || '-',
        isSender: session?.isSender === true,
        hasLocalSecret: Boolean(envelope.sessionId && await hasSessionSecret(envelope.sessionId))
      })
    }
    // 发送方的信封存储在接收节点收件箱，但发送方同样持有本地会话密钥。
    // 把没有对应收件信封的会话补进来，避免“我刚分发成功，页面却是 0”。
    const seenSessions = new Set(rows.map((row) => row.sessionId).filter(Boolean))
    for (const session of sessions.values()) {
      if (seenSessions.has(session.sessionId)) continue
      rows.push({
        envelopeId: null,
        poolId: session.sessionId,
        sessionId: session.sessionId,
        senderNode: session.senderNode || '-',
        recipientNode: session.recipientNode || '-',
        isSender: session.isSender === true,
        wrappingAlgorithm: session.protectionAlgorithm || '-',
        sessionStatus: session.status,
        keyHash: '',
        expiresAt: session.expiresAt,
        createdAt: session.createdAt,
        hasLocalSecret: Boolean(await hasSessionSecret(session.sessionId))
      })
    }
    items.value = rows
  } catch (error) {
    items.value = []
    ElMessage.error(`加载节点分发密钥失败：${error.message}`)
  } finally {
    loading.value = false
  }
}

function openDetail(row) {
  current.value = row
  localSecretHex.value = ''
  detailOpen.value = true
}

async function revealLocalSecret() {
  if (!current.value?.sessionId) return
  revealing.value = true
  localSecretHex.value = ''
  try {
    const bytes = await unsealSessionSecret(current.value.sessionId)
    localSecretHex.value = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
    bytes.fill(0)
  } catch (error) {
    ElMessage.error(`读取本机密钥失败：${error.message}`)
  } finally {
    revealing.value = false
  }
}

function statusLabel(row) {
  if (row.hasLocalSecret) return '已解封'
  if (row.sessionStatus === 'established') return '已建立'
  if (row.sessionStatus) return row.sessionStatus
  return row.status || '待处理'
}

function statusType(row) {
  if (row.hasLocalSecret || row.sessionStatus === 'established') return 'success'
  if (row.expired) return 'info'
  return 'warning'
}

function formatTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN', { hour12: false })
}

onMounted(load)
</script>

<style scoped>
.page-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.page-head h2 { margin: 0 0 4px; font-size: 18px; }
.page-desc { margin: 0 0 16px; color: var(--kms-text-secondary); font-size: 13px; line-height: 1.6; }
.panel { border-radius: 10px; }
.panel-head { display: flex; align-items: center; justify-content: space-between; }
.mt16 { margin-top: 16px; }
.mb16 { margin-bottom: 16px; }
code { word-break: break-all; }
.secret-box { display: grid; gap: 6px; padding: 12px; border: 1px solid var(--el-color-success-light-5); border-radius: 8px; background: var(--el-color-success-light-9); }
.secret-box code { font-size: 16px; letter-spacing: 1px; }
.secret-box small { color: var(--kms-text-secondary); }
</style>
