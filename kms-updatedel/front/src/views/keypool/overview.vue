<template>
  <div class="app-container">
    <el-card shadow="never">
      <template #header>
        <div class="panel-head">
          <span>预分配密钥池（监管视图）</span>
          <el-button size="small" :loading="loading" @click="load">刷 新</el-button>
        </div>
      </template>

      <!--
        §9.8 预分配密钥池管理（管理员视角）。

        与节点端「密钥池」的分工：
          本页   —— 全系统视角：池容量、按算法/按状态的分布、过期清理情况
          节点端 —— 本节点自己的池资源及其增删

        两侧用**同一批接口**（`/pqkds-api/key-pool/`）。管理员这一侧只读，
        不发这些接口里带副作用的那些（生成/补充/清理/删除）——
        §9.8 要求的是"查看容量与速度、批量预分配、过期清理"，
        但真正消耗密钥资源的是**节点**自己的分发行为，
        管理员替他生成一批没有接收方语义的池没有意义。
      -->

      <el-row :gutter="12" class="stat-row mb16">
        <el-col :span="6">
          <div class="stat"><div class="k">池总量</div><div class="v">{{ stats.total ?? '-' }}</div></div>
        </el-col>
        <el-col :span="6">
          <div class="stat"><div class="k">READY（未用）</div><div class="v ok">{{ stats.unused ?? '-' }}</div></div>
        </el-col>
        <el-col :span="6">
          <div class="stat"><div class="k">已使用</div><div class="v">{{ stats.used ?? '-' }}</div></div>
        </el-col>
        <el-col :span="6">
          <div class="stat"><div class="k">已过期</div><div class="v warn">{{ stats.expired ?? '-' }}</div></div>
        </el-col>
      </el-row>

      <el-row :gutter="20">
        <el-col :span="12">
          <div class="section-title">按算法分布</div>
          <el-table :data="byAlgorithm" border empty-text="暂无数据">
            <el-table-column label="保护算法" prop="label" min-width="160" />
            <el-table-column label="数量" width="110" align="center" prop="count" />
            <el-table-column label="占比" min-width="180">
              <template #default="{ row }">
                <el-progress :percentage="row.percent" :stroke-width="12" />
              </template>
            </el-table-column>
          </el-table>
        </el-col>
        <el-col :span="12">
          <div class="section-title">按状态分布</div>
          <el-table :data="byStatus" border empty-text="暂无数据">
            <el-table-column label="状态" width="140">
              <template #default="{ row }">
                <el-tag size="small" :type="statusTagType(row.status)">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="数量" width="110" align="center" prop="count" />
            <el-table-column label="占比" min-width="180">
              <template #default="{ row }">
                <el-progress :percentage="row.percent" :stroke-width="12" />
              </template>
            </el-table-column>
          </el-table>
        </el-col>
      </el-row>

      <div class="section-title" style="margin-top: 24px;">密钥池明细</div>
      <el-table v-loading="loading" :data="items" border max-height="420" empty-text="密钥池为空">
        <el-table-column label="批次号" prop="pool_id" min-width="190" show-overflow-tooltip />
        <el-table-column label="序号" prop="key_index" width="70" align="center" />
        <el-table-column label="归属节点" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.key_id || '-' }}</template>
        </el-table-column>
        <el-table-column label="算法" width="130">
          <template #default="{ row }">{{ algorithmLabel(row.algorithm) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="110" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="statusTagType(row.status)">{{ row.status || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="过期时间" width="170">
          <template #default="{ row }">{{ formatTime(row.expires_at) }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
/**
 * §11.1 密钥分发监管 → 预分配密钥池。
 *
 * 与节点端 9472「密钥池」共用 `@/api/pqkds/distribution`，但只读。
 *
 * ⚠️ path 必须与节点端那个区分开：后端路由名 = capitalize(path)，
 *    两边都叫 `keypool` 会让 vue-router 顶掉其中一个（本仓库踩过）。
 *    这里用 `poolgov`，见 41_*.sql 里的说明。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getKeyPoolStats, listKeyPool } from '@/api/pqkds/distribution'

const ALGORITHM_LABELS = {
  kyber_kem: 'Kyber KEM',
  falcon_lattice: 'Falcon 格密码',
  gm_sm2: 'SM2',
  gm_sscl: 'SSCL',
  aes_falcon: 'AES + Falcon'
}

/** 状态按文档 §10.9 的五态；未知状态原样显示，v-for 不隐藏信息 */
const STATUS_TAG = {
  READY: 'success',
  RESERVED: 'warning',
  CONSUMED: 'info',
  EXPIRED: 'danger',
  REVOKED: 'danger'
}

const loading = ref(false)
const stats = ref({})
const items = ref([])

const algorithmLabel = (code) => ALGORITHM_LABELS[code] || code || '-'
const statusTagType = (status) => STATUS_TAG[String(status || '').toUpperCase()] || 'info'

/** 把 {key: count} 形式的分布摊成表格行，并算占比 */
function toRows(source, keyName = 'key') {
  const entries = Object.entries(source || {}).filter(([, v]) => Number(v) > 0)
  const total = entries.reduce((sum, [, v]) => sum + Number(v), 0)
  if (!total) return []
  return entries
    .map(([k, v]) => ({
      [keyName]: k,
      count: Number(v),
      percent: Math.round((Number(v) / total) * 100)
    }))
    .sort((a, b) => b.count - a.count)
}

const byAlgorithm = computed(() =>
  toRows(stats.value.byAlgorithm || stats.value.algorithmDistribution, 'label')
    .map((r) => ({ ...r, label: algorithmLabel(r.label) }))
)

const byStatus = computed(() => toRows(stats.value.byStatus || stats.value.statusDistribution, 'status'))

function formatTime(value) {
  if (!value) return '-'
  const d = new Date(String(value).replace(' ', 'T'))
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString('zh-CN', { hour12: false })
}

async function load() {
  loading.value = true
  try {
    // 统计与明细分开取：统计接口轻，明细可能上千条。
    // 任一个失败都不应让整页空白，故各自 catch。
    const [statsRes, listRes] = await Promise.allSettled([getKeyPoolStats(), listKeyPool()])
    stats.value = statsRes.status === 'fulfilled' ? statsRes.value || {} : {}
    items.value = listRes.status === 'fulfilled' && Array.isArray(listRes.value) ? listRes.value : []

    if (statsRes.status === 'rejected' && listRes.status === 'rejected') {
      ElMessage.error(statsRes.reason?.message || '加载密钥池失败')
    }
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
.mb16 { margin-bottom: 16px; }
.section-title {
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 600;
  color: var(--kms-text-primary);
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
.stat .v.ok { color: var(--kms-success-strong, #00b42a); }
.stat .v.warn { color: var(--kms-warning-strong, #ff7d00); }
</style>
