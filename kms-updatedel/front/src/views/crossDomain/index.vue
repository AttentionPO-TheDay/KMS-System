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
        <el-col :span="6">
          <div class="stat"><div class="k">分发批次</div><div class="v">{{ stats.total }}</div></div>
        </el-col>
        <el-col :span="6">
          <div class="stat"><div class="k">跨域</div><div class="v warn">{{ stats.cross }}</div></div>
        </el-col>
        <el-col :span="6">
          <div class="stat"><div class="k">同域</div><div class="v">{{ stats.same }}</div></div>
        </el-col>
        <el-col :span="6">
          <div class="stat"><div class="k">涉及域</div><div class="v">{{ stats.domains }}</div></div>
        </el-col>
      </el-row>

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
        <el-table-column label="跨域" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.cross ? 'warning' : 'success'" effect="plain">
              {{ row.cross ? '跨域' : '同域' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="数量" width="90" align="center">
          <template #default="{ row }">{{ row.count ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ formatTime(row.createdAt) }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
/**
 * §11.1 密钥分发监管 → 跨域分发。
 *
 * 数据来自既有的 `GET /pqkds-api/distribution-batches/`
 * （user_distribution_views.py 已回 sourceDomainId / targetDomainIds，
 * 见该文件约 484-486 行），**不需要后端改动**。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listDistributionBatches } from '@/services/user-distribution-api'

const loading = ref(false)
const all = ref([])
const filter = reactive({ view: 'cross', keyword: '' })

function normalize(batch) {
  const sourceDomainId = String(batch.sourceDomainId || batch.source_domain_id || '').trim()
  const rawTargets = batch.targetDomainIds || batch.target_domain_ids || []
  const targetDomainIds = (Array.isArray(rawTargets) ? rawTargets : [])
    .map((d) => String(d || '').trim())
    .filter(Boolean)

  // 跨域的判据：任一接收方域与发起方域不同。
  // 接收方域缺失时**不**当作跨域 —— 那是数据不全，不是跨域，
  // 混为一谈会让"跨域"这个数字失去意义。
  const cross = Boolean(sourceDomainId) && targetDomainIds.some((d) => d !== sourceDomainId)

  const receivers = batch.nodes || batch.receivers || []
  return {
    batchId: batch.batchId || batch.batch_id || batch.id || '-',
    senderName: batch.senderName || batch.sender_name || batch.userName || '-',
    sourceDomainId,
    targetDomainIds,
    cross,
    count: batch.number ?? batch.count ?? (Array.isArray(receivers) ? receivers.length : null),
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
    same: normalized.value.length - cross,
    domains: domainSet.size
  }
})

const rows = computed(() => {
  const kw = filter.keyword.trim().toLowerCase()
  return normalized.value.filter((r) => {
    if (filter.view === 'cross' && !r.cross) return false
    if (filter.view === 'same' && r.cross) return false
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

async function load() {
  loading.value = true
  try {
    const res = await listDistributionBatches()
    all.value = Array.isArray(res) ? res : Array.isArray(res?.results) ? res.results : []
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
</style>
