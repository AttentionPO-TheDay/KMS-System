<template>
  <div class="app-container">
    <el-tabs v-model="activeTab">
      <!-- ================= 单钥检查（阶段 7 原样保留） ================= -->
      <el-tab-pane label="单钥检查" name="single">
        <el-card shadow="never">
          <template #header>
            <div class="kh-header">
              <h2>一致性与异常分析</h2>
              <div class="kh-query">
                <el-input
                  v-model="keyId"
                  placeholder="输入密钥ID"
                  clearable
                  style="width: 180px"
                  @keyup.enter="load"
                />
                <el-button type="primary" icon="Search" :loading="loading" @click="load">检查</el-button>
              </div>
            </div>
          </template>

          <el-alert v-if="checkError" :title="checkError" type="error" :closable="false" show-icon />
          <el-empty v-else-if="!result && !loading" description="输入密钥ID后点击检查" :image-size="64" />
          <template v-if="result">
            <div v-if="result" class="kh-summary">
              <el-tag :type="healthTagType" size="large">{{ healthText }}</el-tag>
              <span class="kh-meta">
                密钥 {{ result.keyId }}（{{ result.keyName || '-' }}）· 版本 v{{ result.version }} · 状态 {{ result.status }}
              </span>
            </div>

            <el-table :data="result?.findings || []" size="small" border
                      empty-text="全部检查通过，未发现一致性问题或异常">
              <el-table-column label="级别" width="90">
                <template #default="{ row }">
                  <el-tag :type="row.severity === 'ERROR' ? 'danger' : 'warning'" size="small">
                    {{ row.severity === 'ERROR' ? '严重' : '警告' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="规则" prop="rule" width="170" />
              <el-table-column label="说明" prop="message" min-width="240" />
              <el-table-column label="建议" prop="advice" min-width="260" />
            </el-table>

            <!-- 观测值：给出判定的原始依据，便于人工复核。
                 健康检查若只给结论不给依据，运维无法判断该不该信。 -->
            <el-collapse v-if="result?.observations?.length" class="kh-obs">
              <el-collapse-item :title="`检查明细（${result.observations.length} 条）`">
                <ul>
                  <li v-for="(o, i) in result.observations" :key="i">{{ o }}</li>
                </ul>
              </el-collapse-item>
            </el-collapse>
          </template>
        </el-card>
      </el-tab-pane>

      <!-- ================= 批量扫描（KMS-022） ================= -->
      <el-tab-pane label="批量扫描" name="batch">
        <el-card shadow="never">
          <template #header>
            <div class="kh-summary">
              <h2>批量一致性检查</h2>
              <el-radio-group v-model="source" size="small">
                <el-radio-button value="user">用户密钥</el-radio-button>
                <el-radio-button value="node">节点长期密钥</el-radio-button>
              </el-radio-group>
            </div>
          </template>

          <!-- ---------- 用户密钥：Java 扫描批次（可回看） ---------- -->
          <template v-if="source === 'user'">
            <div class="kh-toolbar">
              <el-button type="primary" icon="Search" :loading="scanning" @click="runScan">触发扫描</el-button>
            </div>

            <el-table v-loading="runsLoading" :data="runs" size="small" border>
              <el-table-column label="批次" align="center" width="150">
                <template #default="{ row }">
                  <el-tooltip :content="row.runId" placement="top"><span class="kh-mono">{{ shortRunId(row.runId) }}</span></el-tooltip>
                </template>
              </el-table-column>
              <el-table-column label="范围" align="center" width="110">
                <template #default="{ row }">{{ row.scope === 'OWNER' ? `用户 ${row.userId}` : '全量' }}</template>
              </el-table-column>
              <el-table-column label="开始时间" align="center" prop="startedAt" width="165" />
              <el-table-column label="结束" align="center" width="90">
                <template #default="{ row }">
                  <el-tag v-if="!row.finishedAt" type="danger" size="small">未完成</el-tag>
                  <span v-else class="kh-muted">完成</span>
                </template>
              </el-table-column>
              <el-table-column label="扫描数" align="center" prop="total" width="80" />
              <el-table-column label="正常" align="center" width="70">
                <template #default="{ row }"><span class="kh-ok">{{ row.okCount }}</span></template>
              </el-table-column>
              <el-table-column label="警告" align="center" width="70">
                <template #default="{ row }"><span :class="{ 'kh-warn': row.warnCount > 0 }">{{ row.warnCount }}</span></template>
              </el-table-column>
              <el-table-column label="异常" align="center" width="70">
                <template #default="{ row }"><span :class="{ 'kh-danger': row.errorCount > 0 }">{{ row.errorCount }}</span></template>
              </el-table-column>
              <el-table-column label="备注" align="center" min-width="200" show-overflow-tooltip>
                <template #default="{ row }">
                  <span v-if="row.note" class="kh-warn">{{ row.note }}</span>
                  <span v-else class="kh-muted">-</span>
                </template>
              </el-table-column>
              <el-table-column label="操作" align="center" width="90" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" @click="openRun(row)">明细</el-button>
                </template>
              </el-table-column>
            </el-table>

            <pagination
              v-show="runsTotal > 0"
              :total="runsTotal"
              v-model:page="runsQuery.pageNum"
              v-model:limit="runsQuery.pageSize"
              @pagination="loadRuns"
            />
          </template>

          <!-- ---------- 节点长期密钥：只读展示 Python 侧巡检现状（E4） ---------- -->
          <template v-else>
            <div v-if="nodeLatestBatch" class="kh-grid">
              <div class="kh-card"><span>最近自动回收批次</span><strong class="kh-mono">{{ nodeLatestBatch.batchId }}</strong></div>
              <div class="kh-card"><span>回收密钥数</span><strong>{{ nodeLatestBatch.keys }}</strong></div>
              <div class="kh-card"><span>失效池项</span><strong>{{ nodeLatestBatch.poolItems }}</strong></div>
              <div class="kh-card"><span>失效会话</span><strong>{{ nodeLatestBatch.sessions }}</strong></div>
            </div>

            <div class="kh-toolbar">
              <el-radio-group v-model="nodeMode" size="small" @change="loadNodeRecords">
                <el-radio-button value="review">待复核（巡检异常）</el-radio-button>
                <el-radio-button value="revoked">已回收</el-radio-button>
              </el-radio-group>
              <el-input v-model="nodeQuery.keyword" placeholder="按密钥ID筛选" clearable style="width: 200px" @keyup.enter="loadNodeRecords" />
              <el-button icon="Search" @click="loadNodeRecords">查询</el-button>
            </div>

            <el-table v-loading="nodeLoading" :data="nodeRows" size="small" border
                      empty-text="没有符合条件的记录">
              <el-table-column label="密钥ID" align="center" prop="keyId" min-width="160" show-overflow-tooltip />
              <el-table-column label="节点" align="center" prop="nodeId" width="140" />
              <el-table-column label="算法" align="center" prop="algorithm" width="90" />
              <el-table-column label="版本" align="center" prop="keyVersion" width="70" />
              <el-table-column label="状态" align="center" width="100">
                <template #default="{ row }">
                  <el-tag :type="row.status === 'REVOKED' ? 'danger' : 'info'" size="small">{{ row.status || '-' }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="巡检动作" align="center" width="130">
                <template #default="{ row }">
                  <el-tag v-if="row.action === 'PENDING_REVIEW'" type="warning" size="small">待复核</el-tag>
                  <span v-else>{{ row.action || '-' }}</span>
                </template>
              </el-table-column>
              <el-table-column label="规则 / 严重级" align="center" min-width="150">
                <template #default="{ row }">
                  <span>{{ row.rule || '-' }}</span>
                  <el-tag v-if="row.severity" :type="row.severity === 'ERROR' ? 'danger' : 'warning'" size="small" class="kh-sev">{{ row.severity }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="检测 / 回收时间" align="center" min-width="160">
                <template #default="{ row }">{{ row.detectedAt || row.revokedAt || '-' }}</template>
              </el-table-column>
              <el-table-column label="原因" align="center" min-width="180" show-overflow-tooltip>
                <template #default="{ row }">{{ row.revokedReason || '-' }}</template>
              </el-table-column>
            </el-table>

            <pagination
              v-show="nodeTotal > 0"
              :total="nodeTotal"
              v-model:page="nodeQuery.page"
              v-model:limit="nodeQuery.pageSize"
              @pagination="loadNodeRecords"
            />
          </template>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <!-- 批次明细抽屉 -->
    <el-drawer v-model="runDrawer.open" size="70%" :title="runDrawerTitle" append-to-body>
      <div v-if="runDrawer.run" class="kh-grid">
        <div class="kh-card"><span>扫描数</span><strong>{{ runDrawer.run.total }}</strong></div>
        <div class="kh-card"><span>正常</span><strong class="kh-ok">{{ runDrawer.run.okCount }}</strong></div>
        <div class="kh-card"><span>警告</span><strong class="kh-warn">{{ runDrawer.run.warnCount }}</strong></div>
        <div class="kh-card"><span>异常</span><strong class="kh-danger">{{ runDrawer.run.errorCount }}</strong></div>
      </div>
      <el-alert v-if="runDrawer.run?.note" type="warning" :closable="false" show-icon class="kh-alert" :title="runDrawer.run.note" />

      <el-form :model="runDrawer.query" inline label-width="60px" class="kh-detail-filter">
        <el-form-item label="结论">
          <el-select v-model="runDrawer.query.verdict" placeholder="全部" clearable style="width: 120px">
            <el-option label="正常" value="OK" />
            <el-option label="警告" value="WARN" />
            <el-option label="异常" value="ERROR" />
          </el-select>
        </el-form-item>
        <el-form-item label="密钥ID">
          <el-input v-model="runDrawer.query.keyId" placeholder="密钥ID" clearable style="width: 140px" @keyup.enter="loadRunItems" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" icon="Search" @click="loadRunItems">查询</el-button>
        </el-form-item>
      </el-form>

      <el-table v-loading="runDrawer.loading" :data="runDrawer.items" size="small" border>
        <el-table-column label="密钥ID" align="center" prop="keyId" width="80" />
        <el-table-column label="密钥名称" align="center" prop="keyName" min-width="130" show-overflow-tooltip />
        <el-table-column label="算法" align="center" prop="encrytName" width="100" />
        <el-table-column label="版本" align="center" width="70">
          <template #default="{ row }">v{{ row.keyVersion }}</template>
        </el-table-column>
        <el-table-column label="结论" align="center" width="90">
          <template #default="{ row }">
            <el-tag :type="verdictTag(row.verdict)" size="small">{{ verdictText(row.verdict) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="规则" align="center" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.rule || '-' }}</template>
        </el-table-column>
        <el-table-column label="说明" align="center" min-width="260" show-overflow-tooltip>
          <template #default="{ row }">{{ row.summary || '-' }}</template>
        </el-table-column>
      </el-table>

      <pagination
        v-show="runDrawer.total > 0"
        :total="runDrawer.total"
        v-model:page="runDrawer.query.pageNum"
        v-model:limit="runDrawer.query.pageSize"
        @pagination="loadRunItems"
      />
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  getKeyHealth,
  triggerKeyHealthScan,
  listKeyHealthScans,
  listKeyHealthScanItems
} from '@/api/lifecycle/lifecycle'
import { listNodeKeyReviews } from '@/api/pqkds/node-self'
import { getOwnNodeKeyHealth } from '@/api/pqkds/key-diagnostics'
import useUserStore from '@/store/modules/user'

const route = useRoute()
const userStore = useUserStore()

// ---------------------------------------------------------------------------
// 单钥检查（原样保留；?keyId= 直达是 legacy.vue「一致性检查」跳转的落点）
// ---------------------------------------------------------------------------
const keyId = ref('')
const loading = ref(false)
const result = ref(null)
const checkError = ref('')
let checkRequest = 0
watch(keyId, () => { checkRequest++; result.value = null; checkError.value = ''; loading.value = false }, { flush: 'sync' })

const healthText = computed(() => ({
  OK: '一致，未发现异常',
  SUSPICIOUS: '发现可疑项',
  REVOKED: '已回收 / 材料不可用'
}[result.value?.health] || result.value?.health || '-'))

const healthTagType = computed(() => ({
  OK: 'success', SUSPICIOUS: 'warning', REVOKED: 'danger'
}[result.value?.health] || 'info'))

async function load() {
  const id = String(keyId.value || '').trim()
  if (!id || loading.value) return
  const requestId = ++checkRequest
  loading.value = true
  result.value = null
  checkError.value = ''
  try {
    const res = userStore.principalType !== 'NODE' && /^\d+$/.test(id) ? await getKeyHealth(id) : await getOwnNodeKeyHealth(id)
    if (requestId !== checkRequest) return
    if (res?.code && res.code !== 200) {
      checkError.value = res.msg || '检查失败'
      return
    }
    result.value = res?.data || res
  } catch (error) {
    if (requestId === checkRequest) checkError.value = `检查失败：${error.message || '请稍后重试'}`
  } finally {
    if (requestId === checkRequest) loading.value = false
  }
}

// ---------------------------------------------------------------------------
// 批量扫描（KMS-022）
// ---------------------------------------------------------------------------
const activeTab = ref('single')
/** user = 用户密钥（Java 扫描批次）；node = 节点长期密钥（Python 巡检只读展示）。 */
const source = ref('user')

// ---- 用户密钥侧 ----
const scanning = ref(false)
const runsLoading = ref(false)
const runs = ref([])
const runsTotal = ref(0)
const runsQuery = ref({ pageNum: 1, pageSize: 10 })

const runDrawer = ref({
  open: false,
  loading: false,
  run: null,
  items: [],
  total: 0,
  query: { pageNum: 1, pageSize: 20, verdict: null, keyId: null }
})

const runDrawerTitle = computed(() =>
  runDrawer.value.run ? `扫描明细 · ${shortRunId(runDrawer.value.run.runId)}` : '扫描明细')

function shortRunId(runId) {
  if (!runId) return '-'
  return runId.length > 12 ? runId.slice(0, 8) + '…' + runId.slice(-3) : runId
}

function verdictTag(verdict) {
  if (verdict === 'ERROR') return 'danger'
  if (verdict === 'WARN') return 'warning'
  return 'success'
}

function verdictText(verdict) {
  if (verdict === 'ERROR') return '异常'
  if (verdict === 'WARN') return '警告'
  return '正常'
}

function loadRuns() {
  runsLoading.value = true
  listKeyHealthScans(runsQuery.value).then(response => {
    runs.value = response.rows || []
    runsTotal.value = response.total || 0
  }).catch(error => {
    ElMessage.error(`加载扫描批次失败：${error?.message || error}`)
  }).finally(() => {
    runsLoading.value = false
  })
}

function runScan() {
  scanning.value = true
  triggerKeyHealthScan().then(response => {
    const run = response?.data
    if (run) {
      let text = `扫描完成：共 ${run.total} 把，正常 ${run.okCount}，警告 ${run.warnCount}，异常 ${run.errorCount}`
      if (run.note) text += `（${run.note}）`
      ElMessage({ message: text, type: run.errorCount > 0 ? 'warning' : 'success', duration: 6000 })
    } else {
      ElMessage.success('扫描完成')
    }
    loadRuns()
  }).catch(error => {
    // 后端对"扫描他人密钥"等有明确拒绝文案，必须展示出来而不是吞掉。
    ElMessage.error(`扫描失败：${error?.message || error}`)
  }).finally(() => {
    scanning.value = false
  })
}

function openRun(row) {
  runDrawer.value.run = row
  runDrawer.value.items = []
  runDrawer.value.total = 0
  runDrawer.value.query = { pageNum: 1, pageSize: 20, verdict: null, keyId: null }
  runDrawer.value.open = true
  loadRunItems()
}

function loadRunItems() {
  const run = runDrawer.value.run
  if (!run?.runId) return
  runDrawer.value.loading = true
  listKeyHealthScanItems(run.runId, runDrawer.value.query).then(response => {
    runDrawer.value.items = response.rows || []
    runDrawer.value.total = response.total || 0
  }).catch(error => {
    ElMessage.error(`加载明细失败：${error?.message || error}`)
  }).finally(() => {
    runDrawer.value.loading = false
  })
}

// ---- 节点长期密钥侧（只读展示既有巡检，E4：不重复实现） ----
const nodeLoading = ref(false)
const nodeRows = ref([])
const nodeTotal = ref(0)
const nodeLatestBatch = ref(null)
const nodeMode = ref('review')
const nodeQuery = ref({ page: 1, pageSize: 20, keyword: '' })

function loadNodeRecords() {
  nodeLoading.value = true
  listNodeKeyReviews({
    mode: nodeMode.value,
    page: nodeQuery.value.page,
    pageSize: nodeQuery.value.pageSize,
    keyword: nodeQuery.value.keyword || ''
  }).then(data => {
    nodeRows.value = data?.rows || []
    nodeTotal.value = data?.total || 0
    // latestBatch 只有管理员会拿到（后端口径）；拿不到就整块不显示 ——
    // 显示一张空卡片会被读成"批次数为 0"，那是编造。
    nodeLatestBatch.value = data?.latestBatch || null
  }).catch(error => {
    ElMessage.error(`加载节点密钥记录失败：${error?.message || error}`)
  }).finally(() => {
    nodeLoading.value = false
  })
}

onMounted(() => {
  const q = route.query.keyId
  if (q) {
    keyId.value = String(q)
  }
  // 批量扫描的数据按需加载：打开页签时才发第一批请求，
  // 避免单钥用户（多数场景）为一个不看的页签付两份查询。
  if (route.query.tab === 'batch') {
    activeTab.value = 'batch'
  }
})

// 页签/来源切换时按需拉取（懒加载，理由同上）
watch([activeTab, source], ([tab, src]) => {
  if (tab !== 'batch') return
  if (src === 'user' && runs.value.length === 0) loadRuns()
  if (src === 'node' && nodeRows.value.length === 0) loadNodeRecords()
})
</script>

<style scoped>
.kh-header { display: flex; align-items: center; justify-content: space-between; }
.kh-header h2 { margin: 0; font-size: 18px; }
.kh-query { display: flex; gap: 8px; }
@media (max-width: 700px) { .kh-header { align-items: flex-start; flex-direction: column; gap: 12px; } .kh-query { width: 100%; } .kh-query .el-input { flex: 1; } }
.kh-summary { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.kh-summary h2 { margin: 0; font-size: 18px; }
.kh-meta { color: var(--kms-text-secondary, #606266); font-size: 13px; }
.kh-obs { margin-top: 16px; }
.kh-obs ul { margin: 0; padding-left: 18px; }
.kh-obs li { font-size: 12px; line-height: 1.9; color: var(--kms-text-secondary, #606266); }

.kh-alert { margin-bottom: 12px; }
.kh-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.kh-note { font-size: 12px; color: var(--kms-text-secondary, #909399); }
.kh-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; margin-bottom: 12px; }
.kh-card {
  border: 1px solid var(--el-border-color, #e4e7ed); border-radius: 6px;
  padding: 10px 14px; display: flex; flex-direction: column; gap: 4px;
}
.kh-card span { font-size: 12px; color: var(--kms-text-secondary, #909399); }
.kh-card strong { font-size: 18px; }
.kh-ok { color: var(--el-color-success, #67c23a); }
.kh-warn { color: var(--el-color-warning, #e6a23c); }
.kh-danger { color: var(--el-color-danger, #f56c6c); }
.kh-muted { color: var(--kms-text-secondary, #909399); }
.kh-mono { font-family: Consolas, Monaco, monospace; font-size: 12px; }
.kh-detail-filter { margin-bottom: 8px; }
.kh-sev { margin-left: 6px; }
</style>
