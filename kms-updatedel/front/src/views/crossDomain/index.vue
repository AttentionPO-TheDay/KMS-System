<template>
  <div class="app-container">
    <el-card shadow="never">
      <template #header>
        <div class="panel-head">
          <span>跨域分发</span>
          <el-button size="small" :loading="loading" @click="load">刷 新</el-button>
        </div>
      </template>

      <!--
        §9.10 跨域分发。

        判定完全依据后端下发的两个快照字段（models.py:735-739）：
          source_domain_id    发起方所属域，**分发发起时**的快照
          target_domain_ids   接收方所属域列表
        快照而非实时回查是后端刻意的设计：节点事后改域，不应改写历史分发记录的
        跨域属性。所以本页也不拿节点当前域去重算 —— 那会与后端口径不一致。
      -->

      <el-form :inline="true" class="filter-bar">
        <el-form-item label="视图">
          <el-radio-group v-model="filter.view">
            <el-radio-button label="cross">仅跨域</el-radio-button>
            <el-radio-button label="same">仅同域</el-radio-button>
            <el-radio-button label="all">全部</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="关键字">
          <el-input v-model="filter.keyword" clearable placeholder="批次号 / 发起方 / 接收方" style="width: 240px" />
        </el-form-item>
      </el-form>

      <el-row :gutter="12" class="stat-row mb16">
        <el-col :xs="12" :sm="6">
          <div class="stat"><div class="k">分发批次</div><div class="v">{{ stats.total }}</div></div>
        </el-col>
        <el-col :xs="12" :sm="6">
          <div class="stat"><div class="k">跨域</div><div class="v warn">{{ stats.cross }}</div></div>
        </el-col>
        <el-col :xs="12" :sm="6">
          <div class="stat"><div class="k">同域</div><div class="v">{{ stats.same }}</div></div>
        </el-col>
        <el-col :xs="12" :sm="6">
          <div class="stat"><div class="k">涉及域</div><div class="v">{{ stats.domains }}</div></div>
        </el-col>
      </el-row>

      <p class="security-note">批次状态沿用节点级汇总，逐载荷失败见安全明细；用户信封生成不等于验签通过。未知域 {{ stats.unknown }} 批，不计入同域。</p>
      <el-table v-loading="loading" :data="rows" border empty-text="没有符合条件的分发记录">
        <el-table-column label="批次号" prop="batchId" min-width="170" show-overflow-tooltip />
        <el-table-column label="发起方" prop="senderName" min-width="140" show-overflow-tooltip />
        <el-table-column label="发起方所属域" min-width="150">
          <template #default="{ row }">
            <span class="mono">{{ row.sourceDomainId || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="接收方所属域" min-width="200">
          <template #default="{ row }">
            <span class="mono">{{ row.targetDomainIds.length ? row.targetDomainIds.join('、') : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="域类型" width="100" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="domainTagType(row.distributionType)" effect="plain">
              {{ domainLabel(row.distributionType) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="批次封装算法" width="125" align="center">
          <template #default="{ row }"><el-tag size="small" effect="plain">{{ algorithmLabel(row.wrappingAlgorithm) }}</el-tag></template>
        </el-table-column>
        <el-table-column label="状态" width="105" align="center">
          <template #default="{ row }"><el-tag size="small" :type="batchStatusType(row.status)">{{ batchStatusLabel(row.status) }}</el-tag></template>
        </el-table-column>
        <el-table-column label="节点成功" width="100" align="center">
          <template #default="{ row }">{{ row.nodeSuccessCount ?? '-' }} / {{ row.nodeCount ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="会话数" width="85" align="center">
          <template #default="{ row }">{{ row.sessionCount ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="用户信封生成" width="125" align="center">
          <template #default="{ row }">{{ userEnvelopeLabel(row.userEnvelopeOk) }}</template>
        </el-table-column>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ formatTime(row.createdAt) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="95" fixed="right" align="center">
          <template #default="{ row }"><el-button link type="primary" @click="openDetail(row)">安全明细</el-button></template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-drawer v-model="detailVisible" :title="'分发安全明细 · ' + selectedBatchId" size="min(1180px, 100vw)" append-to-body destroy-on-close>
      <div v-loading="detailLoading" class="batch-detail">
        <el-alert v-if="detailError" :title="detailError" type="error" show-icon :closable="false" />
        <template v-if="detail">
          <el-descriptions :column="1" border class="mb16">
            <el-descriptions-item label="批次号"><span class="mono detail-wrap">{{ detail.batch.batchId }}</span></el-descriptions-item>
            <el-descriptions-item label="批次状态">{{ batchStatusLabel(detail.batch.status) }}</el-descriptions-item>
            <el-descriptions-item label="批次封装算法">{{ algorithmLabel(detail.batch.wrappingAlgorithm) }}（各腿实际算法见下表）</el-descriptions-item>
            <el-descriptions-item label="发起域 / 目标域">{{ detail.batch.sourceDomainId || '未记录' }} / {{ detail.batch.targetDomainIds?.join('、') || '未记录' }}</el-descriptions-item>
            <el-descriptions-item label="节点成功 / 目标数">{{ detail.batch.nodeSuccessCount ?? '-' }} / {{ detail.batch.nodeCount ?? '-' }}</el-descriptions-item>
            <el-descriptions-item label="载荷数 / 失败尝试">{{ detail.batch.payloadCount ?? '-' }} / {{ detail.batch.failedAttemptCount ?? '-' }}</el-descriptions-item>
            <el-descriptions-item label="用户信封生成">{{ userEnvelopeLabel(detail.batch.userEnvelopeOk) }}（不是验签结果）</el-descriptions-item>
            <el-descriptions-item label="真实会话数">{{ detail.batch.sessionCount ?? '-' }}</el-descriptions-item>
          </el-descriptions>
          <el-alert v-if="detail.legacy" :title="detail.legacyReason || '历史批次没有逐信封明细，不按当前公钥回填。'" type="warning" show-icon :closable="false" class="mb16" />
          <el-alert :title="detail.sessionScopeNote" type="info" show-icon :closable="false" class="mb16" />
          <h3 class="detail-heading">逐信封 / 失败尝试</h3>
          <p class="security-note">签名有效若标注“登记时”，只代表服务端入库校验；接收方验签、解封及确认请查看真实会话证据。版本未记录保持未知。</p>
          <el-table :data="detail.items || []" border empty-text="没有持久化的逐信封明细">
            <el-table-column type="expand">
              <template #default="{ row }">
                <div class="item-audit">
                  <p>载荷 SHA256：<span class="mono detail-wrap">{{ row.keyHash || '未记录' }}</span></p>
                  <p>信封密文摘要：<span class="mono detail-wrap">{{ row.ciphertextDigest || '未记录' }}</span></p>
                  <p>验签说明：{{ row.signatureMessage || '未记录' }}</p>
                  <p>生成时间：{{ formatTime(row.createdAt) }}</p>
                  <template v-if="row.session">
                    <p>关联会话范围：{{ row.sessionScope }}（不是逐载荷确认）</p>
                    <p v-for="entry in evidenceEntries(row.session)" :key="entry.label" class="detail-wrap">
                      {{ entry.label }}：{{ formatTime(entry.at) }}；链交易：<span class="mono">{{ entry.tx || '未记录' }}</span>
                    </p>
                    <p v-if="!evidenceEntries(row.session).length">未记录验签、解封或确认轨迹。</p>
                  </template>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="载荷 / 明细" width="100" align="center">
              <template #default="{ row }">{{ row.payloadIndex + 1 }} / {{ row.itemIndex + 1 }}</template>
            </el-table-column>
            <el-table-column label="收件人" min-width="170">
              <template #default="{ row }">
                <template v-if="row.recipientType === 'user'">用户 #{{ row.recipientUserId ?? '未记录' }}</template>
                <template v-else>
                  <div class="mono">{{ row.recipientNodeCode || '节点编号未记录' }}</div>
                  <div class="cell-note">{{ row.recipientNodeName || '-' }}（#{{ row.recipientNodeId ?? '已不可用' }}）</div>
                </template>
              </template>
            </el-table-column>
            <el-table-column label="实际封装 / 载荷" width="145">
              <template #default="{ row }"><el-tag size="small" effect="plain">{{ algorithmLabel(row.wrappingAlgorithm) }}</el-tag><div class="cell-note">{{ row.payloadAlgorithm?.toUpperCase() || '未记录' }}</div></template>
            </el-table-column>
            <el-table-column label="接收密钥 / 版本" min-width="180">
              <template #default="{ row }"><div class="mono detail-wrap">{{ row.recipientKeyId ?? '未记录' }}</div><div class="cell-note">{{ versionLabel(row.recipientKeyVersion) }}</div></template>
            </el-table-column>
            <el-table-column label="信封登记" width="120">
              <template #default="{ row }"><el-tag size="small" :type="row.deliveryStatus === 'success' ? 'success' : 'danger'">{{ row.deliveryStatus === 'success' ? '信封已登记' : '封装失败' }}</el-tag></template>
            </el-table-column>
            <el-table-column label="验签四态" width="130">
              <template #default="{ row }">
                <el-tooltip :content="row.signatureMessage || '未记录'" placement="top"><el-tag size="small" :type="signatureType(row.signatureState)">{{ signatureLabel(row.signatureState) }}</el-tag></el-tooltip>
                <div class="cell-note">{{ row.signatureScope === 'ingest' ? '登记时校验' : row.signatureScope === 'read' ? '读时验签' : '信封状态' }}</div>
              </template>
            </el-table-column>
            <el-table-column label="信封引用 / 状态" min-width="135">
              <template #default="{ row }"><div>{{ row.envelopeId == null ? '无信封引用' : row.envelopeType + ' #' + row.envelopeId }}</div><div class="cell-note">{{ row.envelopeStatus || '-' }}</div></template>
            </el-table-column>
            <el-table-column label="真实会话关联" min-width="230">
              <template #default="{ row }">
                <template v-if="row.session"><div class="mono detail-wrap">{{ row.session.sessionId }}</div><div class="cell-note">{{ sessionStatusLabel(row.session.status) }} · batch-node</div></template>
                <span v-else class="cell-note">未逐项关联；见批次会话摘要</span>
              </template>
            </el-table-column>
            <el-table-column label="失败原因" prop="failureReason" min-width="210" show-overflow-tooltip />
            <el-table-column label="到期时间" width="175"><template #default="{ row }">{{ formatTime(row.expiresAt) }}</template></el-table-column>
          </el-table>
          <h3 class="detail-heading">批次级会话摘要（batch-node）</h3>
          <el-table :data="detail.sessions || []" border empty-text="没有匹配的真实会话行">
            <el-table-column label="会话号" prop="sessionId" min-width="240" show-overflow-tooltip />
            <el-table-column label="接收节点" prop="recipientNodeId" width="95" />
            <el-table-column label="当前状态" width="135"><template #default="{ row }">{{ sessionStatusLabel(row.status) }}</template></el-table-column>
            <el-table-column label="接收密钥 / 版本" min-width="170"><template #default="{ row }"><div class="mono detail-wrap">{{ row.recipientKeyId ?? '未记录' }}</div><div class="cell-note">{{ versionLabel(row.recipientKeyVersion) }}</div></template></el-table-column>
            <el-table-column label="Falcon 密钥 / 版本" min-width="170"><template #default="{ row }"><div class="mono detail-wrap">{{ row.falconKeyId ?? '未记录' }}</div><div class="cell-note">{{ versionLabel(row.falconKeyVersion) }}</div></template></el-table-column>
            <el-table-column label="真实生命周期证据" min-width="320">
              <template #default="{ row }">
                <div v-for="entry in evidenceEntries(row)" :key="entry.label" class="evidence-entry">
                  <div>{{ entry.label }}：{{ formatTime(entry.at) }}</div><div class="mono cell-note detail-wrap">链交易：{{ entry.tx || '未记录' }}</div>
                </div>
                <span v-if="!evidenceEntries(row).length" class="cell-note">未记录验签、解封或确认轨迹；不由当前状态反推。</span>
              </template>
            </el-table-column>
          </el-table>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
/**
 * §11.1 密钥分发监管 → 跨域分发。
 *
 * 批次列表保持 KMS-017 的 items unwrap；安全明细由 owner-scoped 详情端点提供。
 * 域信息是分发时快照，未知域不能当作同域。会话证据保持 batch-node 粒度。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getDistributionBatch, listDistributionBatches } from '@/services/user-distribution-api'

const loading = ref(false)
const all = ref([])
const filter = reactive({ view: 'cross', keyword: '' })
const detailVisible = ref(false)
const detailLoading = ref(false)
const selectedBatchId = ref('')
const detail = ref(null)
const detailError = ref('')

function normalize(batch) {
  const sourceDomainId = String(batch.sourceDomainId || batch.source_domain_id || '').trim()
  const rawTargets = batch.targetDomainIds || batch.target_domain_ids || []
  const targetDomainIds = (Array.isArray(rawTargets) ? rawTargets : [])
    .map((d) => String(d || '').trim())
    .filter(Boolean)

  // 没有域快照就保持未知；不能因为 cross=false 把历史批次显示成同域。
  const declaredType = batch.distributionType || batch.distribution_type
  const hasCross = targetDomainIds.some((d) => d !== sourceDomainId)
  const hasSame = targetDomainIds.includes(sourceDomainId)
  const distributionType = !sourceDomainId || !targetDomainIds.length
    ? 'unknown'
    : ['same', 'cross', 'mixed'].includes(declaredType)
      ? declaredType
      : hasCross ? (hasSame ? 'mixed' : 'cross') : 'same'

  return {
    batchId: batch.batchId || batch.batch_id || batch.id || '-',
    senderName: batch.senderName || batch.sender_name || batch.userName || '-',
    sourceDomainId,
    targetDomainIds,
    distributionType,
    cross: distributionType === 'cross' || distributionType === 'mixed',
    wrappingAlgorithm: batch.wrappingAlgorithm ?? batch.wrapping_algorithm ?? null,
    status: batch.status ?? null,
    nodeCount: batch.nodeCount ?? batch.node_count ?? null,
    nodeSuccessCount: batch.nodeSuccessCount ?? batch.node_success_count ?? null,
    sessionCount: batch.sessionCount ?? batch.session_count ?? null,
    userEnvelopeOk: batch.userEnvelopeOk ?? batch.user_envelope_ok ?? null,
    createdAt: batch.createdAt || batch.created_at || batch.creTime || ''
  }
}

const normalized = computed(() => all.value.map(normalize))

const stats = computed(() => {
  const cross = normalized.value.filter((r) => r.cross).length
  const domainSet = new Set()
  normalized.value.forEach((r) => {
    if (r.sourceDomainId) domainSet.add(r.sourceDomainId)
    r.targetDomainIds.forEach((d) => domainSet.add(d))
  })
  return {
    total: normalized.value.length,
    cross,
    same: normalized.value.filter((r) => r.distributionType === 'same').length,
    unknown: normalized.value.filter((r) => r.distributionType === 'unknown').length,
    domains: domainSet.size
  }
})

const rows = computed(() => {
  const kw = filter.keyword.trim().toLowerCase()
  return normalized.value.filter((r) => {
    if (filter.view === 'cross' && !r.cross) return false
    if (filter.view === 'same' && r.distributionType !== 'same') return false
    if (!kw) return true
    return [r.batchId, r.senderName, r.sourceDomainId, ...r.targetDomainIds]
      .filter(Boolean)
      .some((v) => String(v).toLowerCase().includes(kw))
  })
})

function formatTime(value) {
  if (!value) return '-'
  const d = new Date(String(value).replace(' ', 'T'))
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString('zh-CN', { hour12: false })
}

function algorithmLabel(value) {
  return { kyber_kem: 'Kyber', KYBER: 'Kyber', gm_sm2: 'SM2', SM2: 'SM2', sm2: 'SM2', gm_sscl: 'SSCL', SSCL: 'SSCL', sscl: 'SSCL' }[value] || value || '未记录'
}

function domainLabel(value) {
  return { same: '同域', cross: '跨域', mixed: '混合', unknown: '未知域' }[value] || '未知域'
}

function domainTagType(value) {
  return value === 'same' ? 'success' : value === 'unknown' ? 'info' : 'warning'
}

function batchStatusLabel(value) {
  return { pending: '进行中', partial: '部分成功', success: '全部成功', failed: '失败' }[value] || value || '未记录'
}

function batchStatusType(value) {
  return { pending: 'info', partial: 'warning', success: 'success', failed: 'danger' }[value] || 'info'
}

function userEnvelopeLabel(value) {
  return value == null ? '未记录' : value ? '已生成' : '未生成 / 无用户腿'
}

function versionLabel(value) {
  return value == null ? '版本未记录' : `v${value}`
}

function signatureLabel(value) {
  return { valid: '签名有效', invalid: '签名无效', missing: '无签名', unverifiable: '无法验证' }[value] || '无法验证'
}

function signatureType(value) {
  return { valid: 'success', invalid: 'danger', missing: 'warning', unverifiable: 'info' }[value] || 'info'
}

function sessionStatusLabel(value) {
  return { initiated: '已发起', recipient_verified: '接收方已验签', key_recovered: '已报告解封', established: '已建立', blockchain_recorded: '已上链', closed: '已关闭', expired: '已过期', revoked: '已撤销' }[value] || value || '未记录'
}

function evidenceEntries(session) {
  const labels = { verified: '接收方验签', recovered: '解封声明（服务端不代解）', established: '双方确认建立', closed: '关闭' }
  return Object.entries(labels).flatMap(([step, label]) => {
    const entry = session?.lifecycleEvidence?.[step]
    return entry && (entry.at || entry.tx) ? [{ label, at: entry.at, tx: entry.tx }] : []
  })
}

async function openDetail(row) {
  const batchId = row.batchId
  selectedBatchId.value = batchId
  detail.value = null
  detailError.value = ''
  detailVisible.value = true
  detailLoading.value = true
  try {
    const result = await getDistributionBatch(batchId)
    if (!result?.batch || !Array.isArray(result.items)) throw new Error('批次详情响应缺少明细字段')
    if (selectedBatchId.value === batchId) detail.value = result
  } catch (error) {
    if (selectedBatchId.value === batchId) detailError.value = error?.message || '加载分发安全明细失败'
  } finally {
    if (selectedBatchId.value === batchId) detailLoading.value = false
  }
}

async function load() {
  loading.value = true
  try {
    const res = await listDistributionBatches()
    // KMS-017：本接口经 service 层 unwrap 后是 `{ items, total }` —— 既不是裸数组，
    // 也不是 DRF 分页的 `results`。此前两个判据都不认它，表格恒空且**不报错**
    // （失败形态是"成功"：页面空着、控制台干净）。读法与 distribute/index.vue:702、
    // workbench/index.vue:848 两处既有正例对齐。
    all.value = Array.isArray(res) ? res : (res?.items || res?.results || [])
  } catch (error) {
    ElMessage.error(error?.message || '加载分发批次失败')
    all.value = []
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}
.filter-bar { margin-bottom: 8px; }
.mb16 { margin-bottom: 16px; }
.mono {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 13px;
}
.stat-row .stat {
  border: 1px solid var(--kms-border);
  border-radius: 8px;
  padding: 12px 16px;
  background: var(--kms-surface-2, #fafafa);
}
.stat .k {
  font-size: 13px;
  color: var(--kms-text-secondary);
  margin-bottom: 6px;
}
.stat .v {
  font-size: 22px;
  font-weight: 600;
  color: var(--kms-text-primary);
}
.stat .v.warn { color: var(--kms-warning-strong, #ff7d00); }
.security-note, .cell-note { color: var(--kms-text-secondary); font-size: 13px; }
.security-note { line-height: 1.6; margin: 0 0 12px; }
.cell-note { margin-top: 4px; font-size: 12px; }
.batch-detail { min-height: 160px; min-width: 0; }
.detail-heading { margin: 22px 0 12px; font-size: 15px; color: var(--kms-text-primary); }
.detail-wrap { overflow-wrap: anywhere; word-break: break-word; }
.item-audit { padding: 8px 16px; line-height: 1.6; }
.item-audit p { margin: 6px 0; }
.evidence-entry + .evidence-entry { margin-top: 8px; }
:deep(.el-descriptions__content) { overflow-wrap: anywhere; }
@media (max-width: 640px) {
  .stat-row .el-col { margin-bottom: 12px; }
  .filter-bar :deep(.el-form-item) { margin-right: 0; max-width: 100%; }
  .filter-bar :deep(.el-input) { max-width: 100%; }
  :deep(.el-descriptions__label) { width: 112px; }
  .item-audit { padding-inline: 12px; }
}
</style>
