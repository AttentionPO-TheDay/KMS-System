<template>
  <div class="app-container">
    <el-card shadow="never">
      <template #header>
        <div class="panel-head">
          <span>节点初始化状态</span>
          <el-button size="small" :loading="loading" @click="load">刷 新</el-button>
        </div>
      </template>

      <!--
        §9.2 节点管理 → 查看节点初始化状态 / 查看公钥登记状态。

        ⚠️ 这里显示的是**服务端登记了什么**，不是"节点能不能用"。
        无证书体系下 Kyber/Falcon/SM2/SSCL 的**私钥在节点自己的浏览器里**
        （§7.2/§7.3/§3.1），服务端只有公钥。所以"四套公钥都登记了"
        不等于"那台机器上私钥还在" —— 后者只有节点侧的
        「本地密钥环境」页能回答。
        这两件事合在一起才是完整状态，本页只管服务端这一半。
      -->

      <el-row :gutter="12" class="stat-row mb16">
        <el-col :span="6">
          <div class="stat"><div class="k">节点总数</div><div class="v">{{ nodes.length }}</div></div>
        </el-col>
        <el-col :span="6">
          <div class="stat"><div class="k">ACTIVE</div><div class="v ok">{{ statusCount('active') }}</div></div>
        </el-col>
        <el-col :span="6">
          <div class="stat"><div class="k">PENDING_INIT</div><div class="v warn">{{ pendingCount }}</div></div>
        </el-col>
        <el-col :span="6">
          <div class="stat"><div class="k">DISABLED</div><div class="v danger">{{ statusCount('disabled') + statusCount('inactive') }}</div></div>
        </el-col>
      </el-row>

      <el-form :inline="true" class="filter-bar">
        <el-form-item label="状态">
          <el-select v-model="filter.status" clearable placeholder="全部" style="width: 170px">
            <el-option label="ACTIVE" value="active" />
            <el-option label="PENDING_INIT（待初始化）" value="pending" />
            <el-option label="DISABLED（已停用）" value="disabled" />
          </el-select>
        </el-form-item>
        <el-form-item label="关键字">
          <el-input v-model="filter.keyword" clearable placeholder="节点ID / 名称" style="width: 220px" />
        </el-form-item>
      </el-form>

      <el-table v-loading="loading" :data="rows" border empty-text="没有符合条件的节点">
        <el-table-column label="节点 ID" prop="node_id" min-width="150" show-overflow-tooltip />
        <el-table-column label="名称" prop="name" min-width="130" show-overflow-tooltip />
        <el-table-column label="所属域" width="130">
          <template #default="{ row }">
            <span class="mono">{{ row.domain_id || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="权限" width="80" align="center">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.permission_level || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="140" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="publicStatusTag(row.status)">{{ publicStatusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Kyber" width="80" align="center">
          <template #default="{ row }"><key-dot :ready="hasKey(row, 'kyber')" /></template>
        </el-table-column>
        <el-table-column label="Falcon" width="80" align="center">
          <template #default="{ row }"><key-dot :ready="hasKey(row, 'falcon')" /></template>
        </el-table-column>
        <el-table-column label="SM2" width="80" align="center">
          <template #default="{ row }"><key-dot :ready="hasKey(row, 'gm')" /></template>
        </el-table-column>
        <el-table-column label="SSCL" width="80" align="center">
          <template #default="{ row }"><key-dot :ready="hasKey(row, 'sscl')" /></template>
        </el-table-column>
        <el-table-column label="初始化时间" width="170">
          <template #default="{ row }">{{ formatTime(row.initialized_at) }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
/**
 * §11.1 密钥生成监管 → 节点初始化状态。
 *
 * 数据来自既有的 `GET /pqkds-api/nodes/`（NodeSerializer 含 status /
 * permission_level / domain_id，四套公钥字段在模型上）。不需要后端改动。
 */
import { computed, h, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElTag } from 'element-plus'
import { listNodes } from '@/api/nodes/nodes'

/** 公钥是否已登记的小圆点。用组件而不是内联模板，避免四列各写一遍 */
const KeyDot = {
  props: { ready: { type: Boolean, default: false } },
  setup(props) {
    return () =>
      h(ElTag, { size: 'small', type: props.ready ? 'success' : 'danger', effect: 'plain' },
        () => (props.ready ? '已登记' : '缺失'))
  }
}

const loading = ref(false)
const nodes = ref([])
const filter = reactive({ status: '', keyword: '' })

/** 服务端四套公钥字段名（models.py）：kyber/falcon_public_key、gm_public_key、sscl_public_key */
function hasKey(row, kind) {
  if (kind === 'kyber') return Boolean(row.kyber_public_key)
  if (kind === 'falcon') return Boolean(row.falcon_public_key)
  if (kind === 'gm') return Boolean(row.gm_public_key)
  if (kind === 'sscl') return Boolean(row.sscl_public_key)
  return false
}

function statusCount(status) {
  return nodes.value.filter((n) => String(n.status || '').toLowerCase() === status).length
}

/** 内部状态有 registered/kyber_uploaded/... 多个中间态，除 active/disabled 外都算待初始化 */
const pendingCount = computed(
  () => nodes.value.filter((n) => !['active', 'disabled', 'inactive'].includes(String(n.status || '').toLowerCase())).length
)

function publicStatusText(status) {
  const s = String(status || '').toLowerCase()
  if (s === 'active') return 'ACTIVE'
  if (s === 'disabled' || s === 'inactive') return 'DISABLED'
  return 'PENDING_INIT'
}

function publicStatusTag(status) {
  const s = String(status || '').toLowerCase()
  if (s === 'active') return 'success'
  if (s === 'disabled' || s === 'inactive') return 'danger'
  return 'warning'
}

const rows = computed(() => {
  const kw = filter.keyword.trim().toLowerCase()
  return nodes.value.filter((n) => {
    const s = String(n.status || '').toLowerCase()
    if (filter.status === 'active' && s !== 'active') return false
    if (filter.status === 'disabled' && !['disabled', 'inactive'].includes(s)) return false
    if (filter.status === 'pending' && ['active', 'disabled', 'inactive'].includes(s)) return false
    if (!kw) return true
    return [n.node_id, n.name].filter(Boolean).some((v) => String(v).toLowerCase().includes(kw))
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
    nodes.value = await listNodes()
  } catch (error) {
    ElMessage.error(error?.message || '加载节点列表失败')
    nodes.value = []
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
.stat .v.ok { color: var(--kms-success-strong, #00b42a); }
.stat .v.warn { color: var(--kms-warning-strong, #ff7d00); }
.stat .v.danger { color: var(--kms-danger-strong, #f53f3f); }
</style>
