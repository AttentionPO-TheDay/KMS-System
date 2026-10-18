<template>
  <section class="group-agreement" aria-label="多方密钥协商">
    <div class="agreement-toolbar">
      <el-select v-model="targets" multiple collapse-tags collapse-tags-tooltip :multiple-limit="7"
                 placeholder="选择2至7个参与节点" aria-label="参与节点" :disabled="busy || loading">
        <el-option v-for="peer in peers" :key="peer.nodeId" :label="`${peer.name} (${peer.nodeId})`" :value="peer.nodeId" />
      </el-select>
      <el-button type="primary" :disabled="targets.length < 2 || loading || Boolean(busy)" :loading="busy === 'create'" @click="create">发起多方协商</el-button>
      <el-button :disabled="Boolean(busy)" :loading="loading" @click="load">刷新</el-button>
    </div>
    <p class="agreement-prerequisite">参与节点须先两两建立并确认会话；每个节点使用自己的浏览器提交随机贡献。</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="agreement-error" />
    <el-table v-loading="loading" :data="items" empty-text="暂无多方协商" @row-click="select">
      <el-table-column label="协商ID" prop="agreementId" min-width="210" show-overflow-tooltip />
      <el-table-column label="参与节点" min-width="180">
        <template #default="{ row }">{{ row.members.map(member => member.name).join('、') }}</template>
      </el-table-column>
      <el-table-column label="贡献承诺" width="100">
        <template #default="{ row }">{{ row.committedCount }}/{{ row.members.length }}</template>
      </el-table-column>
      <el-table-column label="密文交换" width="100">
        <template #default="{ row }">{{ row.exchangedCount }}/{{ row.members.length }}</template>
      </el-table-column>
      <el-table-column label="密钥确认" width="100">
        <template #default="{ row }">{{ row.confirmedCount }}/{{ row.members.length }}</template>
      </el-table-column>
      <el-table-column label="状态" width="130">
        <template #default="{ row }"><el-tag :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag></template>
      </el-table-column>
      <el-table-column label="操作" width="90">
        <template #default="{ row }"><el-button link type="primary" :disabled="Boolean(busy)" @click.stop="select(row)">查看</el-button></template>
      </el-table-column>
    </el-table>

    <section v-if="selected" class="agreement-detail" aria-label="协商执行结果">
      <div class="agreement-heading">
        <div><h3>协商 {{ selected.agreementId }}</h3><span class="agreement-muted">有效期至 {{ formatTime(selected.expiresAt) }}</span></div>
        <el-tag :type="statusType(selected.status)">{{ statusLabel(selected.status) }}</el-tag>
      </div>
      <el-steps :active="stageIndex(selected.status)" :process-status="isTerminal(selected) ? 'error' : 'process'" finish-status="success" simple>
        <el-step title="贡献承诺" /><el-step title="加密交换" /><el-step title="共同派生" /><el-step title="全员确认" />
      </el-steps>
      <el-table :data="selected.members" size="small" class="agreement-members">
        <el-table-column label="参与者" min-width="160">
          <template #default="{ row }">{{ row.name }}{{ row.nodeId === selected.selfNodeId ? '（本节点）' : '' }}</template>
        </el-table-column>
        <el-table-column label="贡献承诺" min-width="120">
          <template #default="{ row }"><el-tag :type="row.committedAt ? 'success' : 'info'" size="small">{{ row.committedAt ? '已提交' : '待提交' }}</el-tag></template>
        </el-table-column>
        <el-table-column label="加密交换" min-width="120">
          <template #default="{ row }"><el-tag :type="row.exchangedAt ? 'success' : 'info'" size="small">{{ row.exchangedAt ? '已发送' : '待发送' }}</el-tag></template>
        </el-table-column>
        <el-table-column label="密钥确认" min-width="120">
          <template #default="{ row }"><el-tag :type="row.confirmedAt ? 'success' : 'info'" size="small">{{ row.confirmedAt ? '已提交确认' : '待确认' }}</el-tag></template>
        </el-table-column>
      </el-table>
      <div class="agreement-actions">
        <el-button v-if="actionLabel" type="primary" :disabled="Boolean(busy) || loading" :loading="busy === selected.agreementId" @click="advance">{{ actionLabel }}</el-button>
        <span v-else class="agreement-muted">{{ waitingLabel }}</span>
        <el-button v-if="!isTerminal(selected)" type="danger" plain :disabled="Boolean(busy) || loading" @click="close">关闭协商</el-button>
      </div>
      <el-alert v-if="selected.failureReason" :title="selected.failureReason" type="error" :closable="false" show-icon />
      <el-alert v-else-if="selected.status === 'established'" title="全员确认一致，协商已建立" type="success" :closable="false" show-icon
                :description="localKey ? '共同派生的会话密钥已加密保存于本机。' : '本机没有该协商的密钥副本，请回参与协商的原设备查看。'" />
      <dl class="agreement-facts">
        <dt>协议</dt><dd>多方随机贡献 · SHA-256 承诺 · AES-GCM 加密交换 · HKDF 派生 · HMAC 全员确认</dd>
        <dt>协商记录摘要</dt><dd>{{ selected.transcriptHash || '等待全员贡献承诺' }}</dd>
      </dl>
      <ol class="agreement-events" aria-label="执行记录">
        <li v-for="(event, index) in selected.events" :key="index">
          <time>{{ formatTime(event.at) }}</time><span>{{ eventLabel(event.stage) }}{{ event.nodeId ? ` (${event.nodeId})` : '' }}</span>
        </li>
      </ol>
    </section>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import { actOnGroupAgreement, createGroupAgreement, getGroupAgreement, listGroupAgreements } from '@/api/pqkds/group-agreement'
import { advanceAgreement } from '@/utils/crypto/group-agreement-client.js'
import { validateSnapshot } from '@/utils/crypto/group-agreement.js'
import {
  hasSessionSecret, readAgreementState, removeAgreementState, removeSessionSecret,
  saveAgreementState, sealSessionSecret, unsealSessionSecret
} from '@/utils/crypto/node-key-store.js'

const items = ref([]), peers = ref([]), targets = ref([]), selected = ref(null)
const loading = ref(false), busy = ref(''), error = ref(''), localKey = ref(false)
const emit = defineEmits(['busy'])
watch(busy, value => emit('busy', Boolean(value)))
let alive = true, interval, selectionEpoch = 0
const statuses = { committing: '等待贡献承诺', exchanging: '加密交换中', confirming: '等待全员确认', established: '已建立', failed: '协商失败', expired: '已过期', closed: '已关闭' }
const statusLabel = status => statuses[status] || status
const statusType = status => status === 'established' ? 'success' : ['failed', 'expired', 'closed'].includes(status) ? 'danger' : 'info'
const isTerminal = group => ['failed', 'expired', 'closed'].includes(group.status)
const formatTime = value => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : ''
const stageIndex = status => ({ committing: 0, exchanging: 1, confirming: 2, established: 4 })[status] ?? 0
const ownMember = computed(() => selected.value?.members.find(member => member.nodeId === selected.value.selfNodeId))
const actionLabel = computed(() => {
  if (!selected.value || !ownMember.value) return ''
  const { status } = selected.value, member = ownMember.value
  if (status === 'committing' && !member.committedAt) return '生成随机贡献并提交承诺'
  if (status === 'exchanging' && !member.exchangedAt) return '加密发送本节点贡献'
  if (status === 'confirming' && !member.confirmedAt) return '校验贡献、派生密钥并确认'
  return ''
})
const waitingLabel = computed(() => selected.value?.status === 'established' ? '全员已确认' : isTerminal(selected.value || {}) ? '协商已结束' : '本节点已完成当前阶段，等待其他参与者')
const eventLabel = stage => ({ created: '协商创建', committed: '提交贡献承诺', exchanging: '全员承诺完成', exchanged: '发送加密贡献', confirming: '全员贡献交换完成', confirmed: '提交密钥确认', established: '全员确认一致', failed: '协商失败', closed: '协商关闭', expired: '协商过期' })[stage] || stage

async function cleanup(group) {
  if (isTerminal(group)) {
    await removeAgreementState(group.agreementId, group.selfNodeId)
    await removeSessionSecret(group.agreementId)
  } else if (group.status === 'established') {
    await removeAgreementState(group.agreementId, group.selfNodeId)
  }
}

async function load() {
  if (loading.value || busy.value) return
  const previousSelection = selected.value?.agreementId
  const epoch = selectionEpoch
  loading.value = true
  try {
    const data = await listGroupAgreements()
    if (!alive) return
    items.value = data.items || []; peers.value = data.peers || []
    // Poll status only. Never automatically submit a contribution or confirmation.
    for (const group of items.value) {
      await validateSnapshot(group)
      if (group.selfNodeId !== data.selfNodeId) throw new Error('协商记录不属于当前节点')
      await cleanup(group)
    }
    // A background refresh must not overwrite a newer row selection.
    if (previousSelection && epoch === selectionEpoch && selected.value?.agreementId === previousSelection) {
      await select({ agreementId: previousSelection }, false)
    }
  } catch (cause) { if (alive) error.value = cause.message || String(cause) }
  finally { if (alive) loading.value = false }
}

async function select(row, clearError = true) {
  if (busy.value) return
  const epoch = ++selectionEpoch
  try {
    const group = await getGroupAgreement(row.agreementId)
    await validateSnapshot(group)
    await cleanup(group)
    const available = await hasSessionSecret(group.agreementId)
    if (!alive || epoch !== selectionEpoch) return
    selected.value = group; localKey.value = available
    if (clearError) error.value = ''
  } catch (cause) { if (alive && epoch === selectionEpoch) error.value = cause.message || String(cause) }
}

async function run(name, operation) {
  if (busy.value || loading.value) return
  busy.value = name; error.value = ''; ++selectionEpoch
  try {
    const group = await operation()
    await validateSnapshot(group)
    await cleanup(group)
    if (!alive) return
    selected.value = group; localKey.value = await hasSessionSecret(group.agreementId)
    if (isTerminal(group)) error.value = group.failureReason || statusLabel(group.status)
  } catch (cause) { if (alive) error.value = cause.message || String(cause) }
  finally {
    if (alive) { busy.value = ''; await load() }
  }
}

async function create() {
  await run('create', () => createGroupAgreement([...targets.value]))
}

async function advance() {
  const current = selected.value
  if (!current) return
  await run(current.agreementId, async () => {
    const work = async () => {
      const group = await getGroupAgreement(current.agreementId)
      return advanceAgreement(group, {
        loadState: readAgreementState, saveState: saveAgreementState,
        loadSecret: unsealSessionSecret, saveKey: sealSessionSecret, post: actOnGroupAgreement
      })
    }
    // Prevent same-origin tabs from generating two different local contributions.
    if (!navigator.locks) throw new Error('当前浏览器不支持协商操作锁，请使用新版Chrome或Edge并通过HTTPS访问')
    return navigator.locks.request(`kms-group:${current.agreementId}:${current.selfNodeId}`, work)
  })
}

async function close() {
  const current = selected.value
  if (!current || busy.value || loading.value) return
  try { await ElMessageBox.confirm('关闭后所有参与者都不能继续本次协商。是否关闭？', '关闭协商', { type: 'warning' }) }
  catch { return }
  await run(current.agreementId, () => actOnGroupAgreement(current.agreementId, 'close'))
}

onMounted(() => { load(); interval = window.setInterval(() => { if (!document.hidden) load() }, 5000) })
onBeforeUnmount(() => { alive = false; ++selectionEpoch; window.clearInterval(interval); emit('busy', false) })
</script>

<style scoped>
.group-agreement { min-width: 0; width: 100%; }
.agreement-toolbar, .agreement-heading, .agreement-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.agreement-toolbar .el-select { width: min(440px, 100%); }
.agreement-prerequisite, .agreement-muted { color: var(--el-text-color-secondary); font-size: 13px; }
.agreement-prerequisite { margin: 12px 0 20px; }
.agreement-error { margin-bottom: 16px; }
.agreement-detail { margin-top: 28px; padding-top: 20px; border-top: 1px solid var(--el-border-color); }
.agreement-heading { justify-content: space-between; margin-bottom: 20px; }
.agreement-heading > div { flex: 1; min-width: 0; }
.agreement-heading h3 { margin: 0 0 6px; font-size: 16px; overflow-wrap: anywhere; }
.agreement-members { margin-top: 16px; }
.agreement-actions { margin: 20px 0; justify-content: space-between; }
.agreement-facts { display: grid; grid-template-columns: 110px minmax(0, 1fr); gap: 8px 16px; font-size: 13px; line-height: 1.6; }
.agreement-facts dt { color: var(--el-text-color-secondary); }
.agreement-facts dd { margin: 0; overflow-wrap: anywhere; }
.agreement-events { list-style: none; padding: 0; margin: 20px 0 0; font-size: 12px; }
.agreement-events li { display: flex; gap: 16px; padding: 6px 0; }
.agreement-events time { color: var(--el-text-color-secondary); font-variant-numeric: tabular-nums; }
@media (max-width: 600px) {
  .agreement-toolbar .el-select { width: 100%; }
  .agreement-facts { grid-template-columns: 1fr; gap: 4px; }
  .agreement-events li { flex-direction: column; gap: 2px; }
  :deep(.el-steps--simple) { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; padding: 12px; }
  :deep(.el-step.is-simple) { max-width: none !important; min-width: 0; }
  :deep(.el-step.is-simple .el-step__title) { font-size: 12px; max-width: none; white-space: nowrap; }
  :deep(.el-step.is-simple .el-step__head) { display: none; }
  :deep(.el-step.is-simple .el-step__arrow) { display: none; }
}
</style>
