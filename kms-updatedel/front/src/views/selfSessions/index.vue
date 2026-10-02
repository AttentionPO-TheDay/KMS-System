<template>
  <div class="app-container">
    <el-card shadow="never">
      <template #header>
        <div class="panel-head">
          <span>会话管理</span>
          <el-button size="small" :loading="loading" @click="load">刷 新</el-button>
        </div>
      </template>

      <!--
        §10.10 会话管理（节点视角）。

        ⚠️ 只显示**元数据**，不显示 SM4 明文会话密钥。
        这不是界面取舍：服务端根本没有明文（§12「不能上传：SM4 明文会话密钥」），
        密钥只存在于会话双方各自的内存里。所以本页即使想显示也无从显示。

        隔离在**服务端**完成（`GET /pqkds-api/node-self/sessions/`）：
        按 node1/node2 外键主键过滤，不是按名字。前端不再做二次过滤 ——
        见 `@/api/pqkds/node-self` 里 listSelfSessions 的说明。
      -->

      <el-alert
        v-if="!loading && !mapped"
        type="info"
        :closable="false"
        show-icon
        class="mb16"
        title="当前账号没有对应的 KMS 节点"
        description="管理员账号不映射到节点，因此没有自己的会话。全系统的会话请见「密钥分发监管 → 会话监控」。"
      />

      <template v-if="mapped">
        <el-row :gutter="12" class="stat-row mb16">
          <el-col :span="6">
            <div class="stat"><div class="k">会话总数</div><div class="v">{{ all.length }}</div></div>
          </el-col>
          <el-col :span="6">
            <div class="stat"><div class="k">已建立</div><div class="v ok">{{ countBy('established') + countBy('blockchain_recorded') }}</div></div>
          </el-col>
          <el-col :span="6">
            <div class="stat"><div class="k">进行中</div><div class="v warn">{{ inProgress }}</div></div>
          </el-col>
          <el-col :span="6">
            <div class="stat"><div class="k">已过期 / 已撤销</div><div class="v danger">{{ countBy('expired') + countBy('revoked') }}</div></div>
          </el-col>
        </el-row>

        <el-form :inline="true" class="filter-bar">
          <el-form-item label="角色">
            <el-select v-model="filter.role" style="width: 160px">
              <el-option label="全部会话" value="all" />
              <el-option label="我发起的" value="sender" />
              <el-option label="我接收的" value="recipient" />
            </el-select>
          </el-form-item>
          <el-form-item label="状态">
            <el-select v-model="filter.status" clearable placeholder="全部" style="width: 170px">
              <el-option v-for="s in statusOptions" :key="s.value" :label="s.label" :value="s.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="关键字">
            <el-input v-model="filter.keyword" clearable placeholder="会话ID / 对端节点" style="width: 220px" />
          </el-form-item>
          <el-form-item>
            <el-checkbox v-model="filter.includeExpired" @change="load">含已过期/已撤销</el-checkbox>
          </el-form-item>
        </el-form>

        <el-table v-loading="loading" :data="rows" border empty-text="没有符合条件的会话">
          <el-table-column label="会话 ID" prop="sessionId" min-width="190" show-overflow-tooltip />
          <el-table-column label="方向" width="100" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="row.isSender ? 'primary' : 'success'" effect="plain">
                {{ row.isSender ? '我发起' : '我接收' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="发送方" prop="senderNode" min-width="130" show-overflow-tooltip />
          <el-table-column label="接收方" prop="recipientNode" min-width="130" show-overflow-tooltip />
          <el-table-column label="保护算法" width="140">
            <template #default="{ row }">{{ typeLabel(row.protectionAlgorithm) }}</template>
          </el-table-column>
          <el-table-column label="签名算法" width="100" align="center">
            <!-- §7.3 Falcon 负责业务签名，不承担 SM4 加密 -->
            <span class="muted">Falcon</span>
          </el-table-column>
          <el-table-column label="状态" width="140" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="statusTag(row.status)">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="创建时间" width="170">
            <template #default="{ row }">{{ formatTime(row.createdAt) }}</template>
          </el-table-column>
          <el-table-column label="过期时间" width="170">
            <template #default="{ row }">{{ formatTime(row.expiresAt) }}</template>
          </el-table-column>
        </el-table>
      </template>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getSelfNode, listSelfSessions } from '@/api/pqkds/node-self'

const SESSION_TYPES = {
  aes_falcon: 'AES + Falcon',
  kyber_kem: 'Kyber 密钥协商',
  falcon_lattice: 'Falcon 格密码'
}
const SESSION_STATUS = {
  initiated: '已发起',
  established: '已建立',
  blockchain_recorded: '已记录上链',
  expired: '已过期',
  revoked: '已撤销'
}

const loading = ref(false)
const mapped = ref(false)
const all = ref([])
const filter = reactive({ role: 'all', status: '', keyword: '', includeExpired: false })

const typeLabel = (v) => SESSION_TYPES[v] || v || '-'
const statusLabel = (v) => SESSION_STATUS[v] || v || '-'

function statusTag(status) {
  if (status === 'established' || status === 'blockchain_recorded') return 'success'
  if (status === 'expired' || status === 'revoked') return 'danger'
  return 'warning'
}

function countBy(status) {
  return all.value.filter((s) => s.status === status).length
}

const inProgress = computed(
  () => all.value.filter((s) => !['established', 'blockchain_recorded', 'expired', 'revoked'].includes(s.status)).length
)

const statusOptions = computed(() => {
  const seen = new Map()
  all.value.forEach((s) => {
    if (s.status) seen.set(s.status, SESSION_STATUS[s.status] || s.status)
  })
  return [...seen].map(([value, label]) => ({ value, label }))
})

const rows = computed(() => {
  const kw = filter.keyword.trim().toLowerCase()
  return all.value.filter((s) => {
    if (filter.role === 'sender' && !s.isSender) return false
    if (filter.role === 'recipient' && s.isSender) return false
    if (filter.status && s.status !== filter.status) return false
    if (!kw) return true
    return [s.sessionId, s.senderNode, s.recipientNode]
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
    // 先确认这个账号是不是节点。管理员账号会得到 mapped=false ——
    // 那不是错误，是"这个账号不是节点"，不该报红。
    const self = await getSelfNode()
    mapped.value = Boolean(self?.mapped)

    if (!mapped.value) {
      all.value = []
      return
    }

    const res = await listSelfSessions({ includeExpired: filter.includeExpired })
    all.value = Array.isArray(res?.items) ? res.items : []
  } catch (error) {
    ElMessage.error(error?.message || '加载会话失败')
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
.muted { color: var(--kms-text-secondary); font-size: 13px; }
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