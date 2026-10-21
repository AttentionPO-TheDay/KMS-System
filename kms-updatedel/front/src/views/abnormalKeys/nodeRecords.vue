<template>
  <el-card shadow="never">
    <template #header>
      <div class="records-head">
        <h2>节点异常密钥</h2>
        <el-button size="small" :loading="loading" @click="load">刷新</el-button>
      </div>
    </template>

    <el-alert v-if="latestBatch" type="info" :closable="false" class="records-batch">
      <template #title>
        最近自动回收批次：{{ latestBatch.keys }} 把密钥，{{ latestBatch.poolItems }} 条池项，{{ latestBatch.sessions }} 个会话，耗时 {{ latestBatch.elapsedMs }} ms，完成速率 {{ latestBatch.keysPerSecond }} 条/秒（目标 ≥ 5000 条/秒）
      </template>
    </el-alert>

    <el-form inline @submit.prevent="search">
      <el-form-item label="记录类型">
        <el-select v-model="mode" style="width: 150px" @change="search">
          <el-option label="回收记录" value="revoked" />
          <el-option label="待复核" value="review" />
          <el-option label="已处置" value="handled" />
        </el-select>
      </el-form-item>
      <el-form-item label="节点 ID">
        <el-input v-model="nodeId" clearable placeholder="全部节点" @keyup.enter="search" />
      </el-form-item>
      <el-form-item label="算法">
        <el-select v-model="algorithm" clearable placeholder="全部" style="width: 130px" @change="search">
          <el-option v-for="name in ['KYBER', 'SSCL', 'SM2', 'FALCON']" :key="name" :label="name" :value="name" />
        </el-select>
      </el-form-item>
      <el-form-item label="keyId">
        <el-input v-model="keyword" clearable placeholder="包含匹配" @keyup.enter="search" />
      </el-form-item>
      <el-form-item><el-button type="primary" @click="search">查询</el-button></el-form-item>
    </el-form>

    <el-table v-loading="loading" :data="rows" border size="small" empty-text="没有符合条件的记录">
      <el-table-column label="节点" prop="nodeId" width="150" show-overflow-tooltip />
      <el-table-column label="算法" prop="algorithm" width="90" />
      <el-table-column label="keyId" prop="keyId" min-width="180" show-overflow-tooltip />
      <el-table-column label="版本" width="68"><template #default="{ row }">v{{ row.keyVersion }}</template></el-table-column>
      <el-table-column label="状态" width="95">
        <template #default="{ row }">
          <el-tag size="small" :type="statusTagType(row.status)">{{ row.status || '—' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="处理" width="110">
        <template #default="{ row }">
          <el-tag size="small" :type="actionTagType(row.action)">{{ actionText(row.action) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="判据／处置说明" min-width="230" show-overflow-tooltip>
        <template #default="{ row }">{{ row.revokedReason || row.dispositionNote || ruleText(row.rule) }}</template>
      </el-table-column>
      <el-table-column :label="mode === 'revoked' ? '回收时间' : '发现时间'" width="170">
        <template #default="{ row }">{{ formatTime(mode === 'revoked' ? row.revokedAt : row.detectedAt) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="310" fixed="right">
        <template #default="{ row }">
          <el-button v-if="isAdmin" link type="primary" size="small" @click="openDetail(row)">详情</el-button>
          <el-button v-if="canConfirm(row)" link type="primary" size="small"
            :loading="actingRowId === row.rowId" @click="confirmReview(row)">确认</el-button>
          <el-button v-if="canManualRevoke(row)" link type="danger" size="small"
            :loading="actingRowId === row.rowId" @click="revokeReview(row)">{{ row.status === 'REVOKED' ? '重试人工回收' : '人工回收' }}</el-button>
          <el-button v-if="canDismiss(row)" link type="warning" size="small"
            :loading="actingRowId === row.rowId" @click="dismissReview(row)">忽略误报</el-button>
          <el-button v-if="canRetry(row)" link type="primary" size="small"
            :loading="actingRowId === row.rowId" @click="retryReview(row)">重试</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination v-if="total > 0" v-model:current-page="page" :page-size="30" :total="total"
      layout="total, prev, pager, next" class="records-pagination" @current-change="load" />
  </el-card>

  <el-drawer v-model="detail.open" :title="detailTitle" size="680px" append-to-body destroy-on-close>
    <div v-loading="detail.loading">
      <template v-if="detail.data">
        <el-descriptions title="密钥记录" :column="1" border size="small">
          <el-descriptions-item label="节点">{{ detail.data.key?.nodeId || '—' }}</el-descriptions-item>
          <el-descriptions-item label="算法">{{ detail.data.key?.algorithm || '—' }}</el-descriptions-item>
          <el-descriptions-item label="keyId">{{ detail.data.key?.keyId || '—' }}</el-descriptions-item>
          <el-descriptions-item label="版本">v{{ detail.data.key?.keyVersion ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ detail.data.key?.status || '—' }}</el-descriptions-item>
          <el-descriptions-item label="公钥摘要">{{ detail.data.key?.publicKeyHash || '—' }}</el-descriptions-item>
          <el-descriptions-item label="回收原因">{{ detail.data.key?.revokedReason || '—' }}</el-descriptions-item>
        </el-descriptions>

        <el-descriptions v-if="detail.data.inspection" title="巡检与处置" :column="1" border size="small" class="detail-section">
          <el-descriptions-item label="规则">{{ ruleText(detail.data.inspection.rule) }}</el-descriptions-item>
          <el-descriptions-item label="严重级">{{ detail.data.inspection.severity || '—' }}</el-descriptions-item>
          <el-descriptions-item label="巡检动作">{{ actionText(detail.data.inspection.action) }}</el-descriptions-item>
          <el-descriptions-item label="发现时间">{{ formatTime(detail.data.inspection.detectedAt) }}</el-descriptions-item>
          <el-descriptions-item label="动作时间">{{ formatTime(detail.data.inspection.actionAt) }}</el-descriptions-item>
          <el-descriptions-item label="处置">{{ dispositionText(detail.data.inspection.disposition) }}</el-descriptions-item>
          <el-descriptions-item label="处置说明">{{ detail.data.inspection.dispositionNote || '—' }}</el-descriptions-item>
          <el-descriptions-item label="处置人">{{ detail.data.inspection.handledBy || '—' }}</el-descriptions-item>
          <el-descriptions-item label="处置时间">{{ formatTime(detail.data.inspection.handledAt) }}</el-descriptions-item>
          <el-descriptions-item label="自动批次">{{ detail.data.inspection.batchId || '—' }}</el-descriptions-item>
        </el-descriptions>

        <div class="impact-section">
          <h3>影响面预览</h3>
          <div class="impact-grid">
            <div class="impact-item"><span>关联池项</span><strong>{{ impactCount(detail.data.impact?.poolItems) }}</strong></div>
            <div class="impact-item"><span>关联会话</span><strong>{{ impactCount(detail.data.impact?.sessions) }}</strong></div>
            <div class="impact-item"><span>会话失效状态</span><strong>{{ sessionImpactStatus(detail.data.impact) }}</strong></div>
          </div>
          <el-alert v-if="!hasImpact(detail.data.impact)" type="warning" :closable="false" show-icon
            title="服务端未返回完整影响面，不能把缺失数据当作 0。" />
          <el-alert v-else-if="detail.data.impact.sessionsOk === false" type="error" :closable="false" show-icon
            title="会话失效未完成；人工回收需要重试，不能把当前会话数当作 0。" />
          <el-table v-if="detail.data.impact?.sessionItems?.length" :data="detail.data.impact.sessionItems" border size="small" class="impact-table">
            <el-table-column label="会话" prop="sessionId" min-width="190" show-overflow-tooltip />
            <el-table-column label="状态" prop="status" width="120" />
            <el-table-column label="命中依据" prop="match" min-width="180" show-overflow-tooltip />
          </el-table>
        </div>
      </template>
    </div>
  </el-drawer>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { actOnNodeKeyReview, getNodeKeyReviewImpact, listNodeKeyReviews } from '@/api/pqkds/node-self'
import useUserStore from '@/store/modules/user'

const userStore = useUserStore()
const isAdmin = computed(() => userStore.roleLevel !== null && userStore.roleLevel !== undefined
  && userStore.roleLevel !== '' && Number(userStore.roleLevel) <= 0)
const rows = ref([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const mode = ref('revoked')
const nodeId = ref('')
const algorithm = ref('')
const keyword = ref('')
const latestBatch = ref(null)
const actingRowId = ref(null)
const detail = reactive({ open: false, loading: false, row: null, data: null })
const detailTitle = computed(() => detail.row ? `节点密钥详情 · ${detail.row.keyId || ''}` : '节点密钥详情')

const RULES = {
  PUBLIC_KEY_MISSING: '公钥材料缺失',
  PUBLIC_KEY_HASH_MISSING: '公钥摘要缺失',
  PUBLIC_KEY_HASH_MISMATCH: '公钥摘要与材料不一致',
  MATERIALIZED_PUBLIC_KEY_MISMATCH: '节点公钥视图与密钥记录不一致'
}
const ACTIONS = {
  PENDING_REVIEW: '待复核',
  RESOLVED: '已解决',
  AUTO_REVOKED: '自动回收',
  MANUAL_REVOKED: '人工回收'
}
const DISPOSITIONS = {
  confirmed: '已确认',
  dismissed: '已忽略（不等于修复）',
  manual_revoked: '已人工回收',
  rechecked: '已重试复核'
}

function ruleText(rule) { return RULES[rule] || rule || '—' }
function actionText(action) { return ACTIONS[action] || action || '—' }
function dispositionText(disposition) { return DISPOSITIONS[disposition] || disposition || '未处置' }
function actionTagType(action) {
  if (action === 'AUTO_REVOKED' || action === 'MANUAL_REVOKED') return 'danger'
  if (action === 'PENDING_REVIEW') return 'warning'
  if (action === 'RESOLVED') return 'success'
  return 'info'
}
function statusTagType(status) {
  if (status === 'REVOKED') return 'danger'
  if (status === 'ACTIVE') return 'success'
  return 'info'
}
function formatTime(value) {
  if (!value) return '—'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString('zh-CN', { hour12: false })
}
function impactCount(value) {
  return typeof value === 'number' ? String(value) : '未返回'
}
function hasImpact(impact) {
  return Boolean(impact) && typeof impact.poolItems === 'number' && typeof impact.sessions === 'number'
}
function sessionImpactStatus(impact) {
  if (!hasImpact(impact)) return '未返回'
  if (typeof impact.sessionsOk !== 'boolean') return '仅预览，未执行'
  return impact.sessionsOk ? '已完成' : '未完成'
}
function canConfirm(row) {
  return isAdmin.value && mode.value === 'review' && row.action === 'PENDING_REVIEW'
    && !['confirmed', 'dismissed', 'manual_revoked'].includes(row.disposition)
}
function canDismiss(row) {
  return isAdmin.value && mode.value === 'review' && row.action === 'PENDING_REVIEW'
    && !['confirmed', 'dismissed', 'manual_revoked'].includes(row.disposition)
}
function canManualRevoke(row) {
  if (!isAdmin.value || row.severity !== 'WARNING'
    || ['confirmed', 'dismissed', 'manual_revoked'].includes(row.disposition)) return false
  if (row.status === 'REVOKED') return ['PENDING_REVIEW', 'RESOLVED'].includes(row.action)
  return mode.value === 'review' && row.action === 'PENDING_REVIEW'
}
function canRetry(row) {
  return isAdmin.value && (mode.value === 'review' || mode.value === 'handled') && Boolean(row.rowId)
}
function search() { page.value = 1; load() }

async function load() {
  loading.value = true
  try {
    const data = await listNodeKeyReviews({ mode: mode.value, page: page.value, pageSize: 30,
      nodeId: nodeId.value, algorithm: algorithm.value, keyword: keyword.value })
    rows.value = data?.rows || []
    total.value = data?.total || 0
    latestBatch.value = data?.latestBatch || null
  } catch (error) {
    ElMessage.error(`读取节点密钥记录失败：${error?.message || error}`)
  } finally {
    loading.value = false
  }
}

async function loadDetail(row, open = true) {
  if (open) {
    detail.row = row
    detail.data = null
    detail.open = true
  }
  detail.loading = true
  try {
    detail.data = await getNodeKeyReviewImpact(row.rowId)
  } catch (error) {
    ElMessage.error(`读取密钥详情失败：${error?.message || error}`)
  } finally {
    detail.loading = false
  }
}
function openDetail(row) { loadDetail(row) }

async function submitAction(row, operation, note, successText) {
  if (actingRowId.value !== null) return
  actingRowId.value = row.rowId
  try {
    await actOnNodeKeyReview(row.rowId, operation, note)
    ElMessage.success(successText)
    await load()
    if (detail.open && detail.row?.rowId === row.rowId) await loadDetail(row, false)
  } catch (error) {
    ElMessage.error(`操作未完成：${error?.message || error}`)
    // A failed response can follow a committed key revocation. Reload the fact
    // before offering recovery; "重试巡检" must never substitute for revoke.
    await load()
    if (detail.open && detail.row?.rowId === row.rowId) await loadDetail(row, false)
  } finally {
    actingRowId.value = null
  }
}

async function confirmReview(row) {
  try {
    await ElMessageBox.confirm(
      `已核对 ${row.algorithm} ${row.keyId} v${row.keyVersion} 的异常记录？确认只记录人工核对结论，不会回收密钥。`,
      '确认异常记录',
      { confirmButtonText: '确认已核对', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  await submitAction(row, 'confirm', '', '已记录确认')
}

async function dismissReview(row) {
  let note
  try {
    const result = await ElMessageBox.prompt(
      '忽略不等于修复；被忽略的漂移仍会在安全监控里可见。请填写为什么判定为误报。',
      '忽略误报',
      {
        confirmButtonText: '忽略并记录', cancelButtonText: '取消', type: 'warning',
        inputPlaceholder: '必填：误报依据或核对结果',
        inputValidator: (value) => String(value || '').trim() ? true : '忽略原因不能为空'
      },
    )
    note = String(result.value).trim()
  } catch {
    return
  }
  await submitAction(row, 'dismiss', note, '已记录忽略')
}

async function revokeReview(row) {
  let reason
  try {
    const result = await ElMessageBox.prompt(
      row.status === 'REVOKED'
        ? `密钥 ${row.keyId} v${row.keyVersion} 已回收。本次只补做未完成的池项和会话失效，不会恢复密钥或重试链上存证；请填写原因。`
        : `人工回收 ${row.algorithm} ${row.keyId} v${row.keyVersion} 是终态操作，会清空当前公钥并失效关联池项与会话；请确认影响面后填写回收原因。`,
      '人工回收密钥',
      {
        confirmButtonText: '确认回收', cancelButtonText: '取消', type: 'error',
        inputPlaceholder: '必填：人工回收原因',
        inputValidator: (value) => String(value || '').trim() ? true : '回收原因不能为空'
      },
    )
    reason = String(result.value).trim()
  } catch {
    return
  }
  await submitAction(row, 'revoke', reason, '已完成人工回收')
}

async function retryReview(row) {
  try {
    await ElMessageBox.confirm(
      '重试只会重跑这一行的巡检判定；已有人工终态与首次审计保持不变，不会自动回收密钥、补做会话失效或重试链上存证。',
      '重试巡检',
      { confirmButtonText: '重试', cancelButtonText: '取消', type: 'info' },
    )
  } catch {
    return
  }
  await submitAction(row, 'retry', '', '已完成巡检重试')
}

onMounted(load)
</script>

<style scoped>
.records-head { display: flex; align-items: center; justify-content: space-between; }
.records-head h2 { margin: 0; font-size: 18px; }
.records-lead { margin: 0 0 14px; color: var(--kms-text-secondary); line-height: 1.7; }
.records-batch { margin-bottom: 14px; }
.records-pagination { margin-top: 14px; justify-content: flex-end; }
.detail-section { margin-top: 18px; }
.impact-section { margin-top: 22px; }
.impact-section h3 { margin: 0 0 12px; font-size: 15px; }
.impact-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-bottom: 12px; }
.impact-item { padding: 12px; border: 1px solid var(--el-border-color-light); border-radius: 4px; }
.impact-item span { display: block; color: var(--kms-text-secondary); font-size: 12px; margin-bottom: 6px; }
.impact-item strong { font-size: 18px; }
.impact-table { margin-top: 12px; }
@media (max-width: 720px) {
  .impact-grid { grid-template-columns: 1fr; }
}
</style>
