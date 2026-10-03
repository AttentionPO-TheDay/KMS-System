<template>
  <div class="app-container">
    <el-card class="panel" shadow="never">
      <template #header>
        <div class="panel-head">
          <div>
            <span>会话密钥</span>
</div>
          <el-button size="small" :loading="loading" @click="load">刷 新</el-button>
        </div>
      </template>

<el-form :inline="true" class="filter-bar">
        <el-form-item label="关键字">
          <el-input v-model="filter.keyword" clearable placeholder="会话ID / 节点ID" style="width: 240px" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filter.status" clearable placeholder="全部" style="width: 170px">
            <el-option v-for="s in statusOptions" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button @click="resetFilter">重 置</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="rows" size="small" v-loading="loading" empty-text="当前没有会话（节点之间还没协商过）">
        <el-table-column label="会话ID" min-width="200" prop="session_id" show-overflow-tooltip />
        <el-table-column label="发起节点" min-width="150">
          <template #default="scope">{{ scope.row.node1_name || scope.row.node1 }}</template>
        </el-table-column>
        <el-table-column label="接收节点" min-width="150">
          <template #default="scope">{{ scope.row.node2_name || scope.row.node2 }}</template>
        </el-table-column>
        <el-table-column label="类型" width="150">
          <template #default="scope">{{ typeLabel(scope.row.session_type) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="140">
          <template #default="scope">
            <el-tag size="small" :type="statusTag(scope.row.status)">{{ statusLabel(scope.row.status) }}</el-tag>
          </template>
        </el-table-column>
        <!-- KMS-014（计划 §7 阶段 6）：监管页区分五态。
             数据源是会话的 `evidence_state`（服务端从 `lifecycle_evidence` 轨迹算），
             **不**从 status 反推 —— 会话关闭/撤销后 status 只剩一个终态标记，
             "它曾经走到过哪一步"会静默丢失，而监管要看的恰恰是完整轨迹。
             悬停能看到每一步的时间与链上哈希（tx 为空即该步无链上事件）。 -->
        <el-table-column label="证据（五态）" min-width="260">
          <template #default="scope">
            <el-tooltip placement="top" :content="evidenceTooltip(scope.row)">
              <span class="evidence-row">
                <el-tag
                  v-for="step in EVIDENCE_STEPS"
                  :key="step.key"
                  size="small"
                  :type="scope.row.evidence_state?.[step.key] ? 'success' : 'info'"
                  :effect="scope.row.evidence_state?.[step.key] ? 'light' : 'plain'"
                  class="evidence-tag"
                >{{ step.label }}</el-tag>
              </span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="过期时间" width="180">
          <template #default="scope">{{ formatTime(scope.row.expires_at) }}</template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="scope">{{ formatTime(scope.row.create_datetime) }}</template>
        </el-table-column>
      </el-table>

      <div class="table-foot">共 {{ rows.length }} 条</div>
    </el-card>
  </div>
</template>

<script setup>
/**
 * 「会话密钥」——从分发模块复用的分发功能页（原生实现，只读）。
 *
 * 只读是刻意的：建立会话需要节点侧参与（密钥协商），管理端替节点发起没有意义。
 * 这里给出的是"系统里现在有哪些会话、和谁、什么状态"。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listSessions } from '@/api/pqkds/distribution'

const SESSION_TYPES = { aes_falcon: 'AES+Falcon 会话', kyber_kem: 'Kyber 密钥协商' }
const SESSION_STATUS = {
  initiated: '已发起',
  established: '已建立',
  blockchain_recorded: '已记录到区块链',
  expired: '已过期',
  revoked: '已撤销'
}

/**
 * KMS-014 五态（计划 §7 阶段 6）。key 与服务端 `evidence_state()` 的字段名
 * **逐字对应**：名字对不上时这一列会恒显示灰色（"看起来正常"），
 * 所以这里不另起中文名当 key。
 */
const EVIDENCE_STEPS = [
  { key: 'registered', label: '已登记' },
  { key: 'verified', label: '已验签' },
  { key: 'recovered', label: '已解封' },
  { key: 'established', label: '已建立' },
  { key: 'onChain', label: '已上链' }
]

/** 悬停详情：每一步的时间与链上哈希（从 `lifecycle_evidence` 轨迹解析）。 */
function evidenceTooltip(row) {
  let data = {}
  try {
    data = JSON.parse(row.lifecycle_evidence || '{}') || {}
  } catch {
    return '证据轨迹不是合法 JSON（库内值异常，请让维护者查看该会话行）'
  }
  const at = (k) => (data[k] && data[k].at) || ''
  const tx = (k) => (data[k] && data[k].tx) || ''
  return [
    '已登记：会话行建立（信封登记那一刻）',
    `已验签：${at('verified') || '—'}${tx('verified') ? `  tx=${tx('verified')}` : ''}`,
    `已解封：${at('recovered') || '—'}（节点单方声明，无链上事件）`,
    `已建立：${at('established') || '—'}${tx('established') ? `  tx=${tx('established')}` : ''}`,
    `已关闭：${at('closed') || '—'}${tx('closed') ? `  tx=${tx('closed')}` : ''}`
  ].join('\n')
}

const all = ref([])
const rows = ref([])
const loading = ref(false)
const filter = reactive({ keyword: '', status: '' })

const statusOptions = computed(() => {
  const seen = new Map()
  all.value.forEach((s) => {
    if (s.status) seen.set(s.status, SESSION_STATUS[s.status] || s.status)
  })
  return [...seen].map(([value, label]) => ({ value, label }))
})

const typeLabel = (v) => SESSION_TYPES[v] || v || '-'
const statusLabel = (v) => SESSION_STATUS[v] || v || '-'

function statusTag(status) {
  if (status === 'established' || status === 'blockchain_recorded') return 'success'
  if (status === 'expired' || status === 'revoked') return 'danger'
  return 'warning'
}

function formatTime(value) {
  if (!value) return '-'
  const d = new Date(String(value).replace(' ', 'T'))
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString('zh-CN', { hour12: false })
}

function applyFilter() {
  const kw = filter.keyword.trim().toLowerCase()
  rows.value = all.value.filter((s) => {
    if (filter.status && s.status !== filter.status) return false
    if (!kw) return true
    return [s.session_id, s.node1_name, s.node2_name].filter(Boolean).some((v) => String(v).toLowerCase().includes(kw))
  })
}

function resetFilter() {
  filter.keyword = ''
  filter.status = ''
  applyFilter()
}

async function load() {
  loading.value = true
  try {
    all.value = (await listSessions()) || []
    applyFilter()
  } catch (error) {
    ElMessage.error(`加载会话密钥失败：${error.message}`)
    all.value = []
    rows.value = []
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.panel { border-radius: 10px; }
.panel-head { display: flex; align-items: center; justify-content: space-between; }
.panel-head .sub { margin-left: 10px; color: var(--el-text-color-secondary); font-size: 12px; }
.filter-bar { margin-bottom: 4px; }
.table-foot { margin-top: 10px; color: var(--el-text-color-secondary); font-size: 12px; }
.mb16 { margin-bottom: 16px; }
.evidence-row { display: inline-flex; gap: 4px; flex-wrap: wrap; }
.evidence-tag { font-size: 11px; }
</style>