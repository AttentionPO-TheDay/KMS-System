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
</style>