<template>
  <div class="app-container">
    <el-card class="panel" shadow="never">
      <template #header>
        <div class="panel-head">
          <div>
            <span>分发日志</span>
            <span class="sub">节点侧密钥分发与上链动作的流水</span>
          </div>
          <el-button size="small" :loading="loading" @click="load">刷 新</el-button>
        </div>
      </template>

<el-form :inline="true" class="filter-bar">
        <el-form-item label="关键字">
          <el-input v-model="filter.keyword" clearable placeholder="节点 / 详情 / tx 哈希" style="width: 260px" />
        </el-form-item>
        <el-form-item label="操作">
          <el-select v-model="filter.action" clearable placeholder="全部" style="width: 180px">
            <el-option v-for="a in actionOptions" :key="a.value" :label="a.label" :value="a.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="结果">
          <el-select v-model="filter.success" clearable placeholder="全部" style="width: 130px">
            <el-option label="成功" value="1" />
            <el-option label="失败" value="0" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button @click="resetFilter">重 置</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="rows" size="small" v-loading="loading" empty-text="暂无分发日志">
        <el-table-column label="时间" width="180">
          <template #default="scope">{{ formatTime(scope.row.timestamp) }}</template>
        </el-table-column>
        <el-table-column label="节点" min-width="150">
          <template #default="scope">{{ scope.row.node_name || scope.row.node }}</template>
        </el-table-column>
        <el-table-column label="操作" width="140">
          <template #default="scope">{{ actionLabel(scope.row.action) }}</template>
        </el-table-column>
        <el-table-column label="结果" width="90">
          <template #default="scope">
            <el-tag size="small" :type="scope.row.success ? 'success' : 'danger'">
              {{ scope.row.success ? '成功' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="区块链交易" min-width="170">
          <template #default="scope">
            <code v-if="scope.row.blockchain_tx_hash" class="hash">{{ shortHash(scope.row.blockchain_tx_hash) }}</code>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="详情" min-width="240" show-overflow-tooltip>
          <template #default="scope">{{ scope.row.error_message || scope.row.details || '-' }}</template>
        </el-table-column>
        <el-table-column label="来源 IP" width="140" prop="ip_address" />
      </el-table>

      <div class="table-foot">共 {{ rows.length }} 条</div>
    </el-card>
  </div>
</template>

<script setup>
/**
 * 「分发日志」——从分发模块复用的分发功能页（原生实现，只读）。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listDistributionLogs } from '@/api/pqkds/distribution'

const ACTION_LABELS = {
  system_setup: '系统初始化',
  partial_key_gen: '部分密钥生成',
  user_key_gen: '用户密钥生成',
  blockchain_store: '区块链存储',
  key_update: '密钥更新',
  key_revoke: '密钥撤销'
}

const all = ref([])
const rows = ref([])
const loading = ref(false)
const filter = reactive({ keyword: '', action: '', success: '' })

const actionOptions = computed(() => {
  const seen = new Map()
  all.value.forEach((l) => {
    if (l.action) seen.set(l.action, ACTION_LABELS[l.action] || l.action)
  })
  return [...seen].map(([value, label]) => ({ value, label }))
})

const actionLabel = (v) => ACTION_LABELS[v] || v || '-'

function shortHash(hash) {
  if (!hash) return '-'
  return hash.length > 20 ? `${hash.slice(0, 10)}…${hash.slice(-6)}` : hash
}

function formatTime(value) {
  if (!value) return '-'
  const d = new Date(String(value).replace(' ', 'T'))
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString('zh-CN', { hour12: false })
}

function applyFilter() {
  const kw = filter.keyword.trim().toLowerCase()
  rows.value = all.value.filter((l) => {
    if (filter.action && l.action !== filter.action) return false
    // success 是布尔，下拉里是字符串，这里显式对齐，避免"选了失败却仍显示成功"
    if (filter.success !== '' && String(l.success ? '1' : '0') !== filter.success) return false
    if (!kw) return true
    return [l.node_name, l.details, l.error_message, l.blockchain_tx_hash]
      .filter(Boolean)
      .some((v) => String(v).toLowerCase().includes(kw))
  })
}

function resetFilter() {
  filter.keyword = ''
  filter.action = ''
  filter.success = ''
  applyFilter()
}

async function load() {
  loading.value = true
  try {
    all.value = (await listDistributionLogs()) || []
    applyFilter()
  } catch (error) {
    ElMessage.error(`加载分发日志失败：${error.message}`)
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
.hash { font-size: 12px; }
.mb16 { margin-bottom: 16px; }
</style>