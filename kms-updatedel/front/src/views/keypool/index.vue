<template>
  <div class="app-container">
    <el-card class="panel" shadow="never">
      <template #header>
        <div class="panel-head">
          <div>
            <span>密钥池</span>
</div>
          <div class="panel-actions">
            <el-button size="small" :loading="loading" @click="loadAll">刷 新</el-button>
            <el-button size="small" @click="handleCleanup">清理过期</el-button>
            <el-button size="small" type="danger" :disabled="!selected.length" @click="handleBatchDelete">
              批量删除{{ selected.length ? `（${selected.length}）` : '' }}
            </el-button>
            <el-button size="small" type="primary" @click="openDistribute">生成并分发</el-button>
          </div>
        </div>
      </template>

<el-row :gutter="12" class="stat-row">
        <el-col :span="6"><div class="stat"><div class="k">总数</div><div class="v">{{ stats.total ?? '-' }}</div></div></el-col>
        <el-col :span="6"><div class="stat"><div class="k">未使用</div><div class="v">{{ stats.unused ?? '-' }}</div></div></el-col>
        <el-col :span="6"><div class="stat"><div class="k">已使用</div><div class="v">{{ stats.used ?? '-' }}</div></div></el-col>
        <el-col :span="6"><div class="stat"><div class="k">已过期</div><div class="v">{{ stats.expired ?? '-' }}</div></div></el-col>
      </el-row>

      <el-form :inline="true" class="filter-bar">
        <el-form-item label="关键字">
          <el-input v-model="filter.keyword" clearable placeholder="批次号 / 节点ID / 密钥哈希" style="width: 260px" />
        </el-form-item>
        <el-form-item label="算法">
          <el-select v-model="filter.algorithm" clearable placeholder="全部" style="width: 170px">
            <el-option v-for="a in algorithmOptions" :key="a.value" :label="a.label" :value="a.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filter.status" clearable placeholder="全部" style="width: 150px">
            <el-option v-for="st in statusOptions" :key="st.value" :label="st.label" :value="st.value" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button @click="resetFilter">重 置</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="rows" size="small" v-loading="loading" row-key="id" empty-text="密钥池还是空的，点右上角「生成并分发」建一批"
                @selection-change="(v) => (selected = v)">
        <el-table-column type="selection" width="42" />
        <el-table-column label="批次号" min-width="200" prop="pool_id" show-overflow-tooltip />
        <el-table-column label="序号" width="70" prop="key_index" />
        <el-table-column label="归属节点" min-width="150">
          <template #default="scope">{{ scope.row.node1_name || scope.row.node1_id }}</template>
        </el-table-column>
        <el-table-column label="算法" width="120">
          <template #default="scope">{{ scope.row.algorithm_display || scope.row.algorithm }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="scope">
            <el-tag size="small" :type="statusTag(scope.row.status)">{{ scope.row.status_display || scope.row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="密钥哈希" min-width="150">
          <template #default="scope"><code class="hash">{{ shortHash(scope.row.key_hash) }}</code></template>
        </el-table-column>
        <el-table-column label="过期时间" width="170">
          <template #default="scope">{{ formatTime(scope.row.expires_at) }}</template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="scope">{{ formatTime(scope.row.create_datetime) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="scope">
            <el-button link type="danger" size="small" @click="handleDelete(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="table-foot">
        共 {{ rows.length }} 条{{ rows.length !== allRows.length ? `（已按筛选显示，总 ${allRows.length} 条）` : '' }}
      </div>
    </el-card>

    <!-- 生成并分发 -->
    <el-dialog v-model="distOpen" title="生成并分发密钥池" width="560px">
      <el-form :model="distForm" label-width="110px">
        <!--
          封装算法（2026-09-26 新增）。
          此前这个对话框只调 `/key-pool/distribute/`，而那条路在服务端**写死 Kyber**，
          于是密钥池的算法列永远只有 Kyber KEM —— 抗量子只剩一半，
          想看 Falcon 得直接调接口，界面上无路可走。
          两条路的语义不同，所以选项标签里写清楚"谁封装、池子归谁"：
            * Kyber KEM     → /key-pool/distribute/：用**发送方**公钥封装，单向池
            * Falcon 格密码 → /key-pool/generate/  ：用**接收方**公钥封装，节点间池
        -->
        <!-- 阶段 5（文档 §6.2）：**移除 Falcon 选项**。
             理由是职责错配 —— SM4 的机密性必须由加密/封装算法提供，
             而 Falcon 是**签名**算法，签名不保密。原先这里能选它，
             意味着允许用签名算法"封装"会话密钥，概念上用错了。

             正确分工：SM2 / SSCL / Kyber 保护 SM4；Falcon 用于签名验签。

             保留 Kyber 一条：它是当前唯一被支持的抗量子封装算法。
             历史 falcon_lattice 池项仍可读（列表按记录自身的 algorithm 渲染），
             只是不再能新建。 -->
        <el-form-item label="封装算法">
          <el-select v-model="distForm.algorithm" style="width: 100%">
            <el-option label="Kyber KEM（抗量子封装）" value="kyber_kem" />
          </el-select>
        </el-form-item>
        <el-form-item label="发送方节点">
          <el-select v-model="distForm.sender_node_id" filterable placeholder="选择发送方节点" style="width: 100%">
            <el-option v-for="n in nodes" :key="n.node_id" :label="`${n.name}（${n.node_id}）`" :value="n.node_id" />
          </el-select>
          <div class="form-hint">
            用该节点的 Kyber 公钥封装，只有它能解开。
          </div>
        </el-form-item>
        <el-form-item label="接收方节点">
          <el-select v-model="distForm.receiver_node_id" filterable placeholder="选择接收方节点" style="width: 100%">
            <el-option v-for="n in nodes" :key="n.node_id" :label="`${n.name}（${n.node_id}）`" :value="n.node_id" />
          </el-select>
        </el-form-item>
        <el-form-item label="数量">
          <el-input-number v-model="distForm.count" :min="1" :max="500" controls-position="right" />
        </el-form-item>
        <el-form-item label="有效期(小时)">
          <el-input-number v-model="distForm.expiry_hours" :min="1" :max="720" controls-position="right" />
        </el-form-item>
      </el-form>
      <div v-if="distError" class="dialog-error">{{ distError }}</div>
      <div v-if="distResult" class="dialog-ok">{{ distResult }}</div>
      <template #footer>
        <el-button @click="distOpen = false">关 闭</el-button>
        <el-button type="primary" :loading="distributing" @click="submitDistribute">生成并分发</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/**
 * 「密钥池」——从分发模块复用过来的**分发功能**页（原生实现）。
 *
 * 为什么不 iframe 嵌它原来的页面：那个子应用有自己的登录态，嵌进来只会显示它的登录页；
 * 而它的接口本来就是开放的、可被管理端直接调用。所以这里只复用**功能**，
 * 页面用管理端自己的组件与登录态重写。
 *
 * 服务端：`/pqkds-api/key-pool/*`（预分配密钥住在 falcon_kds）。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  batchDeleteKeyPool,
  cleanupKeyPool,
  deleteKeyPoolItem,
  distributeKeyPool,
  getKeyPoolStats,
  listKeyPool
} from '@/api/pqkds/distribution'
import { listNodes } from '@/api/nodes/nodes'

const allRows = ref([])
const rows = ref([])
const selected = ref([])
const nodes = ref([])
const stats = ref({})
const loading = ref(false)
const filter = reactive({ keyword: '', algorithm: '', status: '' })

const distOpen = ref(false)
const distributing = ref(false)
const distError = ref('')
const distResult = ref('')
const distForm = reactive({ algorithm: 'kyber_kem', sender_node_id: '', receiver_node_id: '', count: 10, expiry_hours: 24 })

const algorithmOptions = computed(() => {
  const seen = new Map()
  allRows.value.forEach((r) => {
    if (r.algorithm) seen.set(r.algorithm, r.algorithm_display || r.algorithm)
  })
  return [...seen].map(([value, label]) => ({ value, label }))
})

const statusOptions = computed(() => {
  const seen = new Map()
  allRows.value.forEach((r) => {
    if (r.status) seen.set(r.status, r.status_display || r.status)
  })
  return [...seen].map(([value, label]) => ({ value, label }))
})

function statusTag(status) {
  if (status === 'unused') return 'success'
  if (status === 'used') return 'info'
  if (status === 'expired') return 'danger'
  return 'warning'
}

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
  rows.value = allRows.value.filter((r) => {
    if (filter.algorithm && r.algorithm !== filter.algorithm) return false
    if (filter.status && r.status !== filter.status) return false
    if (!kw) return true
    return [r.pool_id, r.node1_id, r.node1_name, r.key_hash]
      .filter(Boolean)
      .some((v) => String(v).toLowerCase().includes(kw))
  })
}

function resetFilter() {
  filter.keyword = ''
  filter.algorithm = ''
  filter.status = ''
  applyFilter()
}

async function loadAll() {
  loading.value = true
  try {
    const [list, poolStats, nodeList] = await Promise.all([
      listKeyPool(),
      getKeyPoolStats().catch(() => ({})),
      listNodes().catch(() => [])
    ])
    allRows.value = list || []
    stats.value = poolStats || {}
    nodes.value = nodeList || []
    applyFilter()
  } catch (error) {
    ElMessage.error(`加载密钥池失败：${error.message}`)
    allRows.value = []
    rows.value = []
  } finally {
    loading.value = false
  }
}

function openDistribute() {
  distError.value = ''
  distResult.value = ''
  distOpen.value = true
}

async function submitDistribute() {
  distError.value = ''
  distResult.value = ''
  if (!distForm.sender_node_id || !distForm.receiver_node_id) {
    distError.value = '请先选择发送方与接收方节点'
    return
  }
  if (distForm.sender_node_id === distForm.receiver_node_id) {
    distError.value = '发送方与接收方不能是同一个节点'
    return
  }
  distributing.value = true
  try {
    // 阶段 5（文档 §6.2）后只剩 Kyber 一条路：单向池，封给**发送方**的 Kyber 公钥。
    //
    // 原此处按算法分流到 generateNodePool（Falcon 节点间池）。UI 移除 Falcon 选项后
    // 该分支恒不走，属死代码，已删除 —— 留着会让人以为系统仍支持 Falcon 封装。
    // 历史 falcon_lattice 池项仍可读（列表与筛选项按记录自身的 algorithm 渲染）。
    const res = await distributeKeyPool({ ...distForm })
    // 服务端实际返回 {success, pool_id, sender_node_id, receiver_node_id, generated, expires_at}。
    // 先按真实字段名读，再留几个兜底 —— 之前只猜了 count/keys/total，
    // 结果把一整串 JSON 当提示显示给用户了（能跑但难看，也算一种"没验证到位"）。
    const count = res?.generated ?? res?.count ?? res?.keys?.length ?? res?.total ?? null
    distResult.value = count
      ? `已生成并分发 ${count} 条（Kyber KEM，批次 ${res?.pool_id || '-'}）`
      : `服务端已受理：${JSON.stringify(res)?.slice(0, 160)}`
    ElMessage.success('生成并分发完成')
    await loadAll()
  } catch (error) {
    distError.value = error.message
  } finally {
    distributing.value = false
  }
}

async function handleCleanup() {
  try {
    await ElMessageBox.confirm('清理所有已过期的预分配密钥？该操作不可撤销。', '清理过期', {
      type: 'warning', confirmButtonText: '清 理', cancelButtonText: '取 消'
    })
  } catch {
    return
  }
  try {
    const res = await cleanupKeyPool()
    const n = res?.deleted ?? res?.count ?? ''
    ElMessage.success(`已清理${n === '' ? '' : ` ${n} 条`}`)
    await loadAll()
  } catch (error) {
    ElMessage.error(`清理失败：${error.message}`)
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`删除批次 ${row.pool_id} 的第 ${row.key_index} 条？`, '删除', {
      type: 'warning', confirmButtonText: '删 除', cancelButtonText: '取 消'
    })
  } catch {
    return
  }
  try {
    await deleteKeyPoolItem(row.id)
    ElMessage.success('已删除')
    await loadAll()
  } catch (error) {
    ElMessage.error(`删除失败：${error.message}`)
  }
}

async function handleBatchDelete() {
  const ids = selected.value.map((r) => r.id)
  if (!ids.length) return
  try {
    await ElMessageBox.confirm(`删除选中的 ${ids.length} 条？该操作不可撤销。`, '批量删除', {
      type: 'warning', confirmButtonText: '删 除', cancelButtonText: '取 消'
    })
  } catch {
    return
  }
  try {
    await batchDeleteKeyPool(ids)
    ElMessage.success('已删除')
    selected.value = []
    await loadAll()
  } catch (error) {
    ElMessage.error(`批量删除失败：${error.message}`)
  }
}

onMounted(loadAll)
</script>

<style scoped>
.panel { border-radius: 10px; }
.panel-head { display: flex; align-items: center; justify-content: space-between; }
.panel-head .sub { margin-left: 10px; color: var(--el-text-color-secondary); font-size: 12px; }
.panel-actions { display: flex; gap: 8px; }
.stat-row { margin-bottom: 12px; }
.stat { background: var(--el-fill-color-light); border-radius: 8px; padding: 10px 14px; }
.stat .k { color: var(--el-text-color-secondary); font-size: 12px; }
.stat .v { font-size: 20px; font-weight: 600; margin-top: 2px; }
.filter-bar { margin-bottom: 4px; }
.table-foot { margin-top: 10px; color: var(--el-text-color-secondary); font-size: 12px; }
.hash { font-size: 12px; }
.form-hint { margin-top: 4px; color: var(--el-text-color-secondary); font-size: 12px; }
.dialog-error { margin-top: 8px; color: var(--el-color-danger); font-size: 12px; word-break: break-all; }
.dialog-ok { margin-top: 8px; color: var(--el-color-success); font-size: 12px; }
.mb16 { margin-bottom: 16px; }
</style>