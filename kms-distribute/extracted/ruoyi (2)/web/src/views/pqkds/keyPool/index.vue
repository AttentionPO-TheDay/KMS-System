<template>
  <div class="app-container">
    <div class="page-header">
      <h2>🔐 密钥预分配</h2>
      <p>系统通过 Kyber KEM 为指定方向（发送方→接收方）批量生成 AES-256 对称密钥，用发送方的 Kyber 公钥加密后下发到发送方节点本地。发起会话时可直接从本地密钥池取用，无需实时协商。密钥池是单向的，双向通信需分别建立两个方向的密钥池。</p>
    </div>
    <el-row :gutter="16" class="stats-row">
      <el-col :span="6"><el-card shadow="hover"><el-statistic title="总密钥数" :value="poolStats.total || 0" /></el-card></el-col>
      <el-col :span="6"><el-card shadow="hover"><el-statistic title="可用密钥" :value="poolStats.unused || 0" /></el-card></el-col>
      <el-col :span="6"><el-card shadow="hover"><el-statistic title="已使用" :value="poolStats.used || 0" /></el-card></el-col>
      <el-col :span="6"><el-card shadow="hover"><el-statistic title="已过期" :value="poolStats.expired || 0" /></el-card></el-col>
    </el-row>
    <el-card class="action-card">
      <el-row :gutter="20">
        <el-col :span="18">
          <el-form :model="searchForm" inline>
            <el-form-item label="节点1">
              <el-select v-model="searchForm.node1_id" placeholder="选择节点" clearable filterable>
                <el-option v-for="n in nodeList" :key="n.node_id" :label="`${n.name} (${n.node_id})`" :value="n.node_id" />
              </el-select>
            </el-form-item>
            <el-form-item label="节点2">
              <el-select v-model="searchForm.node2_id" placeholder="选择节点" clearable filterable>
                <el-option v-for="n in nodeList" :key="n.node_id" :label="`${n.name} (${n.node_id})`" :value="n.node_id" />
              </el-select>
            </el-form-item>
            <el-form-item label="状态">
              <el-select v-model="searchForm.status" placeholder="全部" clearable>
                <el-option label="未使用" value="unused" />
                <el-option label="已使用" value="used" />
                <el-option label="已过期" value="expired" />
              </el-select>
            </el-form-item>
            <el-form-item><el-button type="primary" @click="loadList">查询</el-button></el-form-item>
          </el-form>
        </el-col>
        <el-col :span="6" style="text-align: right">
          <el-button type="danger" :disabled="selectedKeys.length === 0" @click="handleBatchDelete">批量删除 <span v-if="selectedKeys.length > 0">({{ selectedKeys.length }})</span></el-button>
          <el-button type="success" @click="showGenerateDialog = true">线上预分配</el-button>
          <el-button type="warning" @click="handleCleanup">清理过期</el-button>
        </el-col>
      </el-row>
    </el-card>
    <el-card v-if="mergedNodePairs.length > 0" class="pairs-card">
      <template #header><span>节点对密钥池余量</span></template>
      <el-table :data="mergedNodePairs" size="small" stripe>
        <el-table-column prop="node1_name" label="节点1" />
        <el-table-column prop="node2_name" label="节点2" />
        <el-table-column prop="available" label="可用数量" />
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="handleReplenish(row)">补充</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
    <el-card>
      <el-table :data="keyList" v-loading="loading" stripe border style="width: 100%" @selection-change="handleSelectionChange">
        <el-table-column type="selection" width="50" />
        <el-table-column prop="pool_id" label="批次ID" width="180" show-overflow-tooltip />
        <el-table-column prop="key_index" label="序号" width="70" />
        <el-table-column label="节点对" width="200">
          <template #default="{ row }">{{ row.node1_name }} ↔ {{ row.node2_name }}</template>
        </el-table-column>
        <el-table-column prop="status_display" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'unused' ? 'success' : row.status === 'used' ? 'info' : 'danger'" size="small">{{ row.status_display }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="key_hash" label="密钥哈希" width="160" show-overflow-tooltip />
        <el-table-column prop="generation_time_ms" label="生成耗时" width="100">
          <template #default="{ row }">{{ row.generation_time_ms ? row.generation_time_ms.toFixed(2) + ' ms' : '-' }}</template>
        </el-table-column>
        <el-table-column prop="expires_at" label="过期时间" width="170" />
        <el-table-column prop="used_at" label="使用时间" width="170">
          <template #default="{ row }">{{ row.used_at || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="handleDeleteOne(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-wrap">
        <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="total" :page-sizes="[20, 50, 100]" layout="total, sizes, prev, pager, next" @change="loadList" />
      </div>
    </el-card>
    <el-dialog v-model="showGenerateDialog" title="线上预分配密钥（单向）" width="500px">
      <el-alert
        title="密钥池是单向的：发送方节点持有密钥，用于向接收方发送消息。如需双向通信，请分别为两个方向各建一个密钥池。"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 16px"
      />
      <el-form :model="generateForm" label-width="120px">
        <el-form-item label="发送方节点" required>
          <el-select v-model="generateForm.node1_id" placeholder="选择发送方（密钥持有者）" filterable style="width: 100%">
            <el-option v-for="n in nodeList" :key="n.node_id" :label="`${n.name} (${n.node_id})`" :value="n.node_id" />
          </el-select>
        </el-form-item>
        <el-form-item label="接收方节点" required>
          <el-select v-model="generateForm.node2_id" placeholder="选择接收方（通信目标）" filterable style="width: 100%">
            <el-option v-for="n in nodeList" :key="n.node_id" :label="`${n.name} (${n.node_id})`" :value="n.node_id" />
          </el-select>
        </el-form-item>
        <el-form-item label="数量">
          <el-input-number v-model="generateForm.count" :min="1" :max="1000" :step="10" />
        </el-form-item>
        <el-form-item label="有效期(时)">
          <el-input-number v-model="generateForm.expiry_hours" :min="1" :max="720" :step="1" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showGenerateDialog = false">取消</el-button>
        <el-button type="primary" :loading="generating" @click="handleGenerate">开始预分配</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { keyPoolApi } from '@/api/pqkds/keyPool'
import request from '@/utils/request'

const loading = ref(false)
const generating = ref(false)
const showGenerateDialog = ref(false)
const keyList = ref<any[]>([])
const nodeList = ref<any[]>([])
const selectedKeys = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const poolStats = ref<any>({})

const searchForm = reactive({ node1_id: '', node2_id: '', status: '' })
const generateForm = reactive({
  node1_id: '', node2_id: '', count: 50, expiry_hours: 24
})

// 合并同一节点对不同算法的余量
const mergedNodePairs = computed(() => {
  const pairs = poolStats.value?.node_pairs || []
  const map = new Map<string, any>()
  for (const p of pairs) {
    const key = `${p.node1_id}_${p.node2_id}`
    const rkey = `${p.node2_id}_${p.node1_id}`
    const existing = map.get(key) || map.get(rkey)
    if (existing) {
      existing.available += p.available
    } else {
      map.set(key, { ...p, available: p.available })
    }
  }
  return Array.from(map.values())
})

const loadNodes = async () => {
  try {
    // res = { code: 2000, data: [...], total: N } (已被 axios 拦截器解包)
    const res: any = await request({ url: '/api/pqkds/nodes/', method: 'get', params: { limit: 999 } })
    console.log('[KeyPool] nodes response:', res)
    if (Array.isArray(res.data)) {
      nodeList.value = res.data
    } else if (res.data?.data && Array.isArray(res.data.data)) {
      nodeList.value = res.data.data
    } else if (res.data?.results && Array.isArray(res.data.results)) {
      nodeList.value = res.data.results
    } else {
      nodeList.value = []
    }
    console.log('[KeyPool] loaded nodes:', nodeList.value.length)
  } catch (e) { console.error('[KeyPool] loadNodes error:', e) }
}

const loadStats = async () => {
  try {
    const res: any = await keyPoolApi.getStats()
    poolStats.value = res.data || {}
  } catch (e) { console.error(e) }
}

const loadList = async () => {
  loading.value = true
  try {
    const params: any = { page: page.value, limit: pageSize.value }
    if (searchForm.node1_id) params.node1_id = searchForm.node1_id
    if (searchForm.node2_id) params.node2_id = searchForm.node2_id
    if (searchForm.status) params.status = searchForm.status
    const res: any = await keyPoolApi.getList(params)
    if (Array.isArray(res.data)) {
      keyList.value = res.data
      total.value = res.total || res.data.length
    } else if (res.data?.data && Array.isArray(res.data.data)) {
      keyList.value = res.data.data
      total.value = res.data.total || res.data.data.length
    } else {
      keyList.value = []
      total.value = 0
    }
  } catch (e) { console.error(e) }
  loading.value = false
}

const handleGenerate = async () => {
  if (!generateForm.node1_id || !generateForm.node2_id) {
    return ElMessage.warning('请选择两个节点')
  }
  if (generateForm.node1_id === generateForm.node2_id) {
    return ElMessage.warning('发送方和接收方不能是同一个节点')
  }
  generating.value = true
  try {
    // Step 1: 调用 distribute 生成加密密钥池
    const res: any = await keyPoolApi.distribute({
      sender_node_id: generateForm.node1_id,
      receiver_node_id: generateForm.node2_id,
      count: generateForm.count,
      expiry_hours: generateForm.expiry_hours
    })
    const d = res.data
    if (d?.success === false || !d?.encrypted_package) {
      ElMessage.error(d?.message || '密钥池生成失败')
      generating.value = false
      return
    }

    // Step 2: 自动调用 receive，将加密包下发给发送方节点（Kyber 解密 + 保存本地文件）
    const recvRes: any = await keyPoolApi.receive({
      node_id: generateForm.node1_id,
      encrypted_package: d.encrypted_package
    })
    const rd = recvRes.data
    if (rd?.pool_id) {
      ElMessage.success(
        `预分配完成: ${d.generated} 条密钥已生成并下发到节点 ${generateForm.node1_id} 本地` +
        `（${generateForm.node1_id} → ${generateForm.node2_id} 方向）`
      )
    } else {
      ElMessage.warning(`密钥池已生成 ${d.generated} 条，但节点接收失败: ${rd?.message || '未知错误'}`)
    }

    showGenerateDialog.value = false
    loadList()
    loadStats()
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || '预分配失败')
  }
  generating.value = false
}

const handleCleanup = async () => {
  try {
    await ElMessageBox.confirm('确认清理所有过期的预分配密钥？', '提示', { type: 'warning' })
    const res: any = await keyPoolApi.cleanup()
    const d = res.data
    ElMessage.success(`清理完成: ${d?.cleaned || 0} 条`)
    loadList()
    loadStats()
  } catch (e) { /* cancelled */ }
}

const handleReplenish = async (row: any) => {
  try {
    await ElMessageBox.confirm(
      `为 ${row.node1_name} ↔ ${row.node2_name} 补充密钥？`, '补充密钥池', { type: 'info' }
    )
    const res: any = await keyPoolApi.replenish({
      node1_id: row.node1_id, node2_id: row.node2_id
    })
    const d = res.data
    if (d?.replenished === false) {
      ElMessage.info('密钥池余量充足，无需补充')
    } else {
      ElMessage.success(`补充完成: ${d?.generated || 0} 条`)
    }
    loadList()
    loadStats()
  } catch (e) { /* cancelled */ }
}

onMounted(() => { loadNodes(); loadStats(); loadList() })

const handleSelectionChange = (rows: any[]) => {
  selectedKeys.value = rows
}

const handleBatchDelete = async () => {
  if (selectedKeys.value.length === 0) return
  const usedCount = selectedKeys.value.filter((k: any) => k.status === 'used').length
  let msg = `确认删除选中的 ${selectedKeys.value.length} 条预分配密钥？`
  if (usedCount > 0) {
    msg += `\n\n其中 ${usedCount} 条已被会话使用，删除后对应会话将被撤销。`
  }
  try {
    await ElMessageBox.confirm(msg, '批量删除', { type: 'warning' })
    const ids = selectedKeys.value.map((k: any) => k.id)
    const res: any = await keyPoolApi.batchDelete(ids)
    const d = res.data
    let tip = `已删除 ${d?.deleted || 0} 条密钥`
    if (d?.revoked_sessions > 0) {
      tip += `，撤销 ${d.revoked_sessions} 个关联会话`
    }
    ElMessage.success(tip)
    selectedKeys.value = []
    loadList()
    loadStats()
  } catch (e) { /* cancelled */ }
}

const handleDeleteOne = async (row: any) => {
  let msg = `确认删除密钥 ${row.pool_id}#${row.key_index}？`
  if (row.status === 'used') {
    msg += '\n\n该密钥已被会话使用，删除后对应会话将被撤销。'
  }
  try {
    await ElMessageBox.confirm(msg, '删除密钥', { type: 'warning' })
    const res: any = await keyPoolApi.batchDelete([row.id])
    const d = res.data
    let tip = '删除成功'
    if (d?.revoked_sessions > 0) {
      tip += `，已撤销 ${d.revoked_sessions} 个关联会话`
    }
    ElMessage.success(tip)
    loadList()
    loadStats()
  } catch (e) { /* cancelled */ }
}
</script>

<style scoped>
.page-header { margin-bottom: 16px; }
.page-header h2 { margin: 0 0 4px 0; }
.page-header p { margin: 0; color: #909399; font-size: 14px; }
.stats-row { margin-bottom: 16px; }
.action-card { margin-bottom: 16px; }
.pairs-card { margin-bottom: 16px; }
.pagination-wrap { margin-top: 16px; display: flex; justify-content: flex-end; }
</style>
