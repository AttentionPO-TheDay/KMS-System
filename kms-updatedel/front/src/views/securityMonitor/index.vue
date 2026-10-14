<template>
  <AdminDataPanel v-if="['keys', 'pool', 'sessions', 'distribution'].includes(props.section)" :section="props.section" />
  <div v-else class="app-container">
    <h1>{{ pageTitle }}</h1>
    <p class="sm-note">管理员只读查看数据，不执行节点侧生成、更新、回收或分发操作。</p>
    <div class="sm-actions">
      <el-button icon="Refresh" :loading="loading" @click="load">刷新</el-button>
      <span v-if="loadedAt" class="sm-time">更新于 {{ loadedAt }}</span>
    </div>

    <!-- 节点 -->
    <template v-if="show('nodes')">
    <h3 class="sm-title">节点</h3>
    <div class="sm-grid">
      <div class="sm-card"><span>节点总数</span><strong>{{ val('nodes.total') }}</strong></div>
      <div class="sm-card"><span>已激活</span><strong class="ok">{{ val('nodes.active') }}</strong></div>
      <div class="sm-card"><span>待初始化</span><strong class="warn">{{ val('nodes.pendingInit') }}</strong></div>
      <div class="sm-card"><span>已停用</span><strong>{{ val('nodes.disabled') }}</strong></div>
    </div>

    <h3 class="sm-title">节点权限等级分布</h3>
    <div class="sm-grid">
      <div v-for="(label, lvl) in LEVEL_LABELS" :key="lvl" class="sm-card">
        <span>{{ lvl }} · {{ label }}</span>
        <strong>{{ val(`nodes.byLevel.${lvl}`) }}</strong>
      </div>
    </div>
    </template>

    <!-- 密钥 -->
    <template v-if="show('keys')">
    <h3 class="sm-title">节点长期密钥</h3>
    <div class="sm-grid">
      <div class="sm-card"><span>密钥总数</span><strong>{{ val('keys.total') }}</strong></div>
      <div class="sm-card"><span>生产中 ACTIVE</span><strong class="ok">{{ val('keys.active') }}</strong></div>
      <div class="sm-card"><span>待启用 PENDING</span><strong>{{ val('keys.pending') }}</strong></div>
      <div class="sm-card"><span>已被取代 RETIRED</span><strong>{{ val('keys.retired') }}</strong></div>
      <div class="sm-card"><span>已回收 REVOKED</span><strong class="warn">{{ val('keys.revoked') }}</strong></div>
      <div class="sm-card"><span>已过期 EXPIRED</span><strong>{{ val('keys.expired') }}</strong></div>
    </div>
    <p class="sm-note">{{ data.keys?.note || '密钥统计源不可用' }}</p>
    <h3 class="sm-title">密钥类型分布</h3>
    <p v-if="!data.keys" class="sm-note">不可用</p>
    <el-table v-else :data="keyTypes" empty-text="暂无密钥（0）" aria-label="节点长期密钥算法计数">
      <el-table-column prop="type" label="算法" />
      <el-table-column prop="count" label="密钥数量" />
    </el-table>
    <p v-if="unknownStatuses.length" class="sm-note">其它状态：{{ unknownStatuses.join('；') }}</p>

    <h3 class="sm-title">密钥条目</h3>
    <el-table class="sm-table" :data="pagedKeyItems" size="small" empty-text="暂无密钥条目（0）" aria-label="逻辑密钥只读列表">
      <el-table-column prop="keyId" label="密钥 ID" min-width="210" show-overflow-tooltip />
      <el-table-column prop="nodeId" label="所属节点" min-width="120" show-overflow-tooltip />
      <el-table-column prop="algorithm" label="算法" width="110" />
      <el-table-column label="状态" width="100">
        <template #default="scope">{{ keyStatusText(scope.row.status) }}</template>
      </el-table-column>
      <el-table-column prop="version" label="版本" width="80" />
      <el-table-column prop="securityLevel" label="安全级别" width="95">
        <template #default="scope">{{ scope.row.securityLevel || '-' }}</template>
      </el-table-column>
      <el-table-column prop="generationScheme" label="生成方案" min-width="170" show-overflow-tooltip>
        <template #default="scope">{{ scope.row.generationScheme || '-' }}</template>
      </el-table-column>
      <el-table-column label="生效时间" min-width="170">
        <template #default="scope">{{ formatTime(scope.row.effectiveAt || scope.row.createdAt) }}</template>
      </el-table-column>
    </el-table>
    <el-pagination
      class="sm-pagination"
      :current-page="keyPage"
      :page-size="PAGE_SIZE"
      :total="keyItems.length"
      layout="total, prev, pager, next"
      @current-change="keyPage = $event"
    />

    </template>

    <!-- 预分配池 -->
    <template v-if="show('pool')">
    <h3 class="sm-title">预分配保护包（池项，不等于唯一密钥）</h3>
    <div class="sm-grid">
      <div class="sm-card"><span>池项总数</span><strong>{{ val('pool.total') }}</strong></div>
      <div class="sm-card"><span>可取用 READY</span><strong class="ok">{{ val('pool.ready') }}</strong></div>
      <div class="sm-card"><span>占用中 RESERVED</span><strong>{{ val('pool.reserved') }}</strong></div>
      <div class="sm-card"><span>已消费 CONSUMED</span><strong>{{ val('pool.consumed') }}</strong></div>
      <div class="sm-card"><span>已失效 REVOKED</span><strong class="warn">{{ val('pool.revoked') }}</strong></div>
      <div class="sm-card"><span>已过期 EXPIRED</span><strong>{{ val('pool.expired') }}</strong></div>
    </div>
    <h3 class="sm-title">预分配密钥条目</h3>
    <p class="sm-note sm-note--compact">仅展示标识、归属、算法、状态和时间，不返回密文、哈希或解封材料。</p>
    <el-table class="sm-table" :data="pagedPoolItems" size="small" empty-text="暂无预分配密钥条目（0）" aria-label="预分配密钥只读列表">
      <el-table-column prop="poolId" label="池批次" min-width="210" show-overflow-tooltip />
      <el-table-column prop="keyIndex" label="序号" width="75" />
      <el-table-column prop="sourceNode" label="来源节点" min-width="115" show-overflow-tooltip />
      <el-table-column prop="targetNode" label="目标节点" min-width="115" show-overflow-tooltip>
        <template #default="scope">{{ scope.row.targetNode || '-' }}</template>
      </el-table-column>
      <el-table-column label="封装算法" width="115">
        <template #default="scope">{{ algorithmText(scope.row.wrappingAlgorithm) }}</template>
      </el-table-column>
      <el-table-column label="载荷算法" width="105">
        <template #default="scope">{{ algorithmText(scope.row.payloadAlgorithm) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="105">
        <template #default="scope">{{ poolStatusText(scope.row.status) }}</template>
      </el-table-column>
      <el-table-column prop="longTermKeyId" label="保护密钥" min-width="190" show-overflow-tooltip>
        <template #default="scope">
          {{ scope.row.longTermKeyId ? `${scope.row.longTermKeyId} · v${scope.row.longTermKeyVersion || '-'}` : '-' }}
        </template>
      </el-table-column>
      <el-table-column label="过期时间" min-width="170">
        <template #default="scope">{{ formatTime(scope.row.expiresAt) }}</template>
      </el-table-column>
    </el-table>
    <el-pagination
      class="sm-pagination"
      :current-page="poolPage"
      :page-size="PAGE_SIZE"
      :total="data.pool?.total || 0"
      layout="total, prev, pager, next"
      @current-change="loadPoolPage"
    />
    </template>

    <!-- 会话 -->
    <template v-if="show('sessions')">
    <h3 class="sm-title">会话</h3>
    <div class="sm-grid">
      <div class="sm-card"><span>会话总数</span><strong>{{ val('sessions.total') }}</strong></div>
      <div class="sm-card"><span>已建立</span><strong class="ok">{{ val('sessions.established') }}</strong></div>
      <div class="sm-card"><span>已过期</span><strong>{{ val('sessions.expired') }}</strong></div>
      <div class="sm-card"><span>已撤销</span><strong>{{ val('sessions.revoked') }}</strong></div>
    </div>
    <el-table class="sm-table" :data="pagedSessionItems" size="small" empty-text="暂无会话记录（0）" aria-label="全部会话只读列表">
      <el-table-column prop="sessionId" label="会话 ID" min-width="190" show-overflow-tooltip />
      <el-table-column prop="sourceNode" label="发起节点" min-width="130" show-overflow-tooltip />
      <el-table-column prop="targetNode" label="接收节点" min-width="130" show-overflow-tooltip />
      <el-table-column prop="sessionType" label="保护方式" width="130" />
      <el-table-column label="状态" width="110">
        <template #default="scope">{{ statusText(scope.row.status) }}</template>
      </el-table-column>
      <el-table-column label="创建时间" min-width="170">
        <template #default="scope">{{ formatTime(scope.row.createdAt) }}</template>
      </el-table-column>
      <el-table-column label="过期时间" min-width="170">
        <template #default="scope">{{ formatTime(scope.row.expiresAt) }}</template>
      </el-table-column>
    </el-table>
    <el-pagination
      class="sm-pagination"
      :current-page="sessionPage"
      :page-size="PAGE_SIZE"
      :total="sessionItems.length"
      layout="total, prev, pager, next"
      @current-change="sessionPage = $event"
    />
    </template>

    <!-- 分发 -->
    <template v-if="show('distribution')">
    <h3 class="sm-title">分发</h3>
    <div class="sm-grid">
      <div class="sm-card"><span>分发批次总数</span><strong>{{ val('distribution.total') }}</strong></div>
      <div class="sm-card">
        <span>成功率</span>
        <strong class="ok">{{ rateText }}</strong>
      </div>
      <div class="sm-card"><span>成功</span><strong class="ok">{{ val('distribution.byStatus.success') }}</strong></div>
      <div class="sm-card"><span>部分成功</span><strong class="warn">{{ val('distribution.byStatus.partial') }}</strong></div>
      <div class="sm-card"><span>失败</span><strong class="danger">{{ val('distribution.byStatus.failed') }}</strong></div>
    </div>

    <h3 class="sm-title">跨域分发（§8.5）</h3>
    <div class="sm-grid">
      <div class="sm-card"><span>同域</span><strong>{{ val('distribution.crossDomain.same') }}</strong></div>
      <div class="sm-card"><span>跨域</span><strong class="warn">{{ val('distribution.crossDomain.cross') }}</strong></div>
      <div class="sm-card"><span>混合</span><strong>{{ val('distribution.crossDomain.mixed') }}</strong></div>
    </div>
    <el-table class="sm-table" :data="pagedDistributionItems" size="small" empty-text="暂无分发批次（0）" aria-label="分发结果只读列表">
      <el-table-column prop="batchId" label="批次 ID" min-width="190" show-overflow-tooltip />
      <el-table-column label="范围" width="90">
        <template #default="scope">{{ distributionTypeText(scope.row.distributionType) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="scope">{{ statusText(scope.row.status) }}</template>
      </el-table-column>
      <el-table-column prop="sourceNode" label="发起节点" min-width="115" show-overflow-tooltip>
        <template #default="scope">{{ scope.row.sourceNode || '-' }}</template>
      </el-table-column>
      <el-table-column prop="receiverNode" label="接收节点" min-width="140" show-overflow-tooltip>
        <template #default="scope">{{ scope.row.receiverNode || '-' }}</template>
      </el-table-column>
      <el-table-column label="保护算法" width="110">
        <template #default="scope">{{ algorithmText(scope.row.wrappingAlgorithm) }}</template>
      </el-table-column>
      <el-table-column label="会话状态" width="105">
        <template #default="scope">{{ scope.row.sessionStatus ? statusText(scope.row.sessionStatus) : '-' }}</template>
      </el-table-column>
      <el-table-column prop="sourceDomain" label="发起域" width="120" />
      <el-table-column label="目标域" min-width="160" show-overflow-tooltip>
        <template #default="scope">{{ (scope.row.targetDomains || []).join('、') || '-' }}</template>
      </el-table-column>
      <el-table-column prop="nodeSuccessCount" label="成功节点" width="100" />
      <el-table-column label="创建时间" min-width="170">
        <template #default="scope">{{ formatTime(scope.row.createdAt) }}</template>
      </el-table-column>
    </el-table>
    <el-pagination
      class="sm-pagination"
      :current-page="distributionPage"
      :page-size="PAGE_SIZE"
      :total="distributionItems.length"
      layout="total, prev, pager, next"
      @current-change="distributionPage = $event"
    />
    </template>

    <p v-if="props.section === 'all'" class="sm-note">
      统计失败项显示「不可用」而非 0 —— 0 是有效值，会被误读成"确实没有"。
      密钥统计与明细取自当前节点长期密钥模型，不包含旧用户腿验收数据。
    </p>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import http, { unwrap } from '@/api/pqkds/http'
import AdminDataPanel from './AdminDataPanel.vue'

const props = defineProps({ section: { type: String, default: 'all' } })
const show = (name) => props.section === 'all' || props.section === name
const pageTitle = computed(() => ({
  all: '密钥全生命周期',
  keys: '密钥总览',
  nodes: '节点数据',
  pool: '预分配池数据',
  sessions: '会话数据',
  distribution: '分发批次数据'
}[props.section] || '数据总览'))

const LEVEL_LABELS = { L1: '查询', L2: '查询+生成+分发', L3: '查询+生成+分发+更新+回收' }

const loading = ref(false)
const loadedAt = ref('')
const data = ref({})
const PAGE_SIZE = 10
const keyPage = ref(1)
const poolPage = ref(1)
const sessionPage = ref(1)
const distributionPage = ref(1)
const keyItems = computed(() => data.value.keys?.items || [])
const poolItems = computed(() => data.value.pool?.items || [])
const sessionItems = computed(() => data.value.sessions?.items || [])
const distributionItems = computed(() => data.value.distribution?.items || [])
const pageItems = (items, page) => items.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
const pagedKeyItems = computed(() => pageItems(keyItems.value, keyPage.value))
const pagedPoolItems = poolItems
const pagedSessionItems = computed(() => pageItems(sessionItems.value, sessionPage.value))
const pagedDistributionItems = computed(() => pageItems(distributionItems.value, distributionPage.value))
const keyTypes = computed(() => Object.entries(data.value.keys?.byType || {})
  .map(([type, count]) => ({ type, count })))
const unknownStatuses = computed(() => Object.entries(data.value.keys?.byStatus || {})
  .filter(([status]) => !['0', '1', '2', '3'].includes(status))
  .map(([status, count]) => `${status}: ${count}`))

/**
 * 取值并按点路径展开。
 *
 * 关键：**缺失项返回「不可用」而不是 0**。监控面板上 0 是有效值，
 * 会被读成"确实没有"；而"这个数据源挂了"和"数量为零"是完全不同的事。
 * 混在一起会让一次统计故障看起来像一片健康。
 */
const val = (path) => {
  const v = path.split('.').reduce((o, k) => (o == null ? undefined : o[k]), data.value)
  if (v === null || v === undefined) return '不可用'
  return v
}

/** 成功率：后端在分母为 0 时返回 null（无定义），需与"0%"区分开 */
const rateText = computed(() => {
  const r = data.value?.distribution?.successRate
  if (r === null || r === undefined) return '不可用'
  return `${(Number(r) * 100).toFixed(1)}%`
})

const formatTime = (value) => {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN', { hour12: false })
}

const statusText = (status) => ({
  success: '全部成功',
  partial: '部分成功',
  pending: '进行中',
  initiated: '已发起',
  established: '已建立',
  blockchain_recorded: '已上链',
  expired: '已过期',
  revoked: '已撤销',
  failed: '失败'
}[status] || status || '未知')

const keyStatusText = (status) => ({
  ACTIVE: '生产中',
  PENDING: '待启用',
  RETIRED: '已被取代',
  REVOKED: '已回收',
  EXPIRED: '已过期',
  LEGACY: '历史记录'
}[String(status)] || status || '未知')

const poolStatusText = (status) => ({
  READY: '可取用',
  unused: '可取用（历史）',
  RESERVED: '占用中',
  CONSUMED: '已消费',
  used: '已消费（历史）',
  distributed: '已分发（历史）',
  REVOKED: '已失效',
  EXPIRED: '已过期',
  expired: '已过期（历史）'
}[status] || status || '未知')

const algorithmText = (algorithm) => ({
  kyber_kem: 'Kyber',
  falcon_lattice: 'Falcon',
  gm_sm2: 'SM2',
  sm2: 'SM2',
  gm_sscl: 'SSCL',
  sscl: 'SSCL',
  sm4: 'SM4-GCM',
  aes_256: 'AES-256-GCM'
}[algorithm] || algorithm || '-')

const distributionTypeText = (type) => ({
  same: '同域',
  cross: '跨域',
  mixed: '混合'
}[type] || type || '-')

let loadRevision = 0

function loadPoolPage(page) {
  return load(page)
}

async function load(page = 1) {
  // A refresh click passes its MouseEvent; only pagination supplies a page number.
  const requestedPage = Number.isInteger(page) && page > 0 ? page : 1
  const revision = ++loadRevision
  loading.value = true
  try {
    const result = await http.get('/security-monitor/summary/', {
      params: { poolPage: requestedPage, poolPageSize: PAGE_SIZE }
    }).then(unwrap)
    if (revision !== loadRevision) return
    data.value = result
    keyPage.value = 1
    poolPage.value = result.pool?.page || 1
    sessionPage.value = 1
    distributionPage.value = 1
    loadedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  } catch (error) {
    if (revision !== loadRevision) return
    data.value = {}
    poolPage.value = 1
    loadedAt.value = ''
    ElMessage.error(`读取监控数据失败：${error.message}`)
  } finally {
    if (revision === loadRevision) loading.value = false
  }
}

onMounted(() => { if (!['keys', 'pool', 'sessions', 'distribution'].includes(props.section)) load() })
</script>

<style scoped>
.sm-actions { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.sm-time { font-size: 12px; color: var(--kms-text-secondary, #909399); }
.sm-title { margin: 20px 0 10px; font-size: 14px; font-weight: 600; }
.sm-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; }
.sm-card {
  border: 1px solid var(--el-border-color, #e4e7ed); border-radius: 6px;
  padding: 10px 14px; display: flex; flex-direction: column; gap: 4px;
}
.sm-card span { font-size: 12px; color: var(--kms-text-secondary, #909399); }
.sm-card strong { font-size: 20px; }
.sm-card strong, .sm-card .ok, .sm-card .warn, .sm-card .danger { color: var(--kms-text-primary, var(--el-text-color-primary)); }
h1 { font-size: 24px; color: var(--kms-text-primary, var(--el-text-color-primary)); }
@media (max-width: 480px) { .sm-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
.sm-card { background: var(--kms-surface-1, var(--el-bg-color)); min-width: 0; }
.sm-actions { flex-wrap: wrap; margin-top: 16px; }
.sm-note { margin: 20px 0 0; font-size: 12px; color: var(--kms-text-secondary, #909399); line-height: 1.7; }
.sm-note--compact { margin-top: -2px; }
.sm-table { margin-top: 10px; }
.sm-pagination { margin-top: 14px; justify-content: flex-end; }
</style>
