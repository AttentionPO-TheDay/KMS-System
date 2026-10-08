<template>
  <div class="app-container">
    <el-card class="panel" shadow="never">
      <template #header>
        <div class="panel-head">
          <span>节点授权</span>
          <el-button size="small" :loading="loading" @click="load">刷 新</el-button>
        </div>
      </template>

      <!--
        任务书「节点多级授权」：**节点侧**的入口。

        在此之前，节点侧连"有哪些节点"都看不到 —— `/user-nodes/` 只回
        **已被授权**的节点，所以"没授权"与"不存在"在界面上无法区分，
        节点也无法表达"我想和谁建会话"。

        本页把那条链路摆出来：**看到全网名录 → 选对端 → 发起申请 →
        管理员在管理端「节点分发授权」页审批 → 双向放行**。

        ⚠️ 申请单只是**流程记录**。真正的权限写在 `UserNodeAuthorization` 里，
        批准的那一刻才产生。所以"待审批"时候的界面上不能有任何"已经能用了"
        的暗示 —— 关系列的文案按 granted/待审批/未授权三态如实区分。
      -->

      <el-alert
        v-if="!loading && !mapped"
        type="info"
        :closable="false"
        show-icon
        title="当前账号没有对应的 KMS 节点"
        description="本页只对「区块链节点」账号有意义 —— 授权是节点与节点之间的通信权限。管理员账号不映射到节点。"
      />

      <template v-else>
        <div class="section-title">全网节点名录</div>
        <p class="note">
          这里是平台上的全部节点（不含自己）。<b>勾选多个对端可以一次提交申请</b>，
          管理员批准后两个方向同时放行 —— 你<b>和</b>对方都能看到对方的密钥版本并建立会话。
          也可以在「发起分发」页选好接收节点后直接提交（那是同一个接口）。
        </p>

        <el-form :inline="true" class="filter-bar">
          <el-form-item label="搜索">
            <el-input
              v-model="keyword"
              clearable
              placeholder="节点名称或编号"
              style="width: 220px"
            />
          </el-form-item>
          <el-form-item label="只看">
            <el-select v-model="onlyFilter" clearable placeholder="全部" style="width: 150px">
              <el-option label="未授权" value="none" />
              <el-option label="待审批" value="pending" />
              <el-option label="已授权" value="granted" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button
              type="primary"
              :disabled="!selectedNodes.length"
              @click="openBatchRequest"
            >
              提交授权申请（{{ selectedNodes.length }}）
            </el-button>
          </el-form-item>
        </el-form>

        <el-table
          :data="filteredNodes"
          size="small"
          v-loading="loading"
          empty-text="没有匹配的节点"
          @selection-change="(rows) => { selectedNodes = rows }"
        >
          <el-table-column
            type="selection"
            width="42"
            :selectable="(row) => canRequest(row)"
          />
          <el-table-column label="节点" min-width="200">
            <template #default="{ row }">
              <div class="node-cell">
                <span class="node-name">{{ row.name || row.nodeCode }}</span>
                <span class="mono">{{ row.nodeCode }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="类型" width="90" prop="nodeType" />
          <el-table-column label="所属域" width="140">
            <template #default="{ row }">{{ row.domainId || '-' }}</template>
          </el-table-column>
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <el-tag size="small" :type="statusTagType(row.status)" effect="plain">
                {{ statusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="与我的关系" min-width="230">
            <template #default="{ row }">
              <!--
                四态如实区分。**不合并成一个布尔**：管理员可以手工只授单向
                （管理端「新增授权」做得到），那时"我能发给它、它回不了"是真实状态，
                合成一个"已授权"会让这种不对称在界面上消失。
              -->
              <el-tag size="small" :type="relationTagType(row)" effect="plain">
                {{ relationLabel(row) }}
              </el-tag>
              <span v-if="row.relationship.pendingRequestId" class="hint">
                申请 #{{ row.relationship.pendingRequestId }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" align="center">
            <template #default="{ row }">
              <el-button
                link
                type="primary"
                size="small"
                :disabled="!canRequest(row)"
                :title="requestBlockedReason(row)"
                @click="openRequest(row)"
              >
                申请授权
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="section-title">我的申请</div>
        <p class="note">
          「我发起」的是我在等的；「对方发起」的是别人想与我建立会话 ——
          后者决定权在管理员，这里只让你看得见（否则对方显示"待审批"、你这边一片空白）。
        </p>
        <el-table :data="requests" size="small" v-loading="loading" empty-text="还没有授权申请">
          <el-table-column label="方向" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="row.__direction === 'outgoing' ? 'primary' : 'info'" effect="plain">
                {{ row.__direction === 'outgoing' ? '我发起' : '对方发起' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="对端" min-width="170">
            <template #default="{ row }">
              <span class="mono">{{ row.__direction === 'outgoing' ? row.targetNodeId : row.requesterNodeId }}</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="requestStatusTagType(row.status)">
                {{ row.statusLabel }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="理由" min-width="180" prop="reason" show-overflow-tooltip />
          <el-table-column label="提交时间" width="170">
            <template #default="{ row }">{{ formatTime(row.createdAt) }}</template>
          </el-table-column>
          <el-table-column label="审批意见" min-width="150">
            <template #default="{ row }">
              <span v-if="row.status === 'pending'" class="muted">等待管理员审批</span>
              <span v-else>
                {{ row.decisionRemark || '-' }}
                <span v-if="row.decidedBy" class="hint">（{{ row.decidedBy }}）</span>
              </span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="90" align="center">
            <template #default="{ row }">
              <el-button
                v-if="row.__direction === 'outgoing' && row.status === 'pending'"
                link
                type="danger"
                size="small"
                @click="handleCancel(row)"
              >
                撤回
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </template>
    </el-card>

    <!-- 发起申请（单个 / 一次多个共用同一个对话框：目标是**列表**，单条时只有一个元素） -->
    <el-dialog v-model="requestOpen" title="发起授权申请" width="520px" :close-on-click-modal="false">
      <el-descriptions :column="1" border class="mb16">
        <el-descriptions-item label="目标节点">
          <span class="mono">{{ requestTargets.join('、') || '-' }}</span>
          <span class="hint">（共 {{ requestTargets.length }} 个）</span>
        </el-descriptions-item>
        <el-descriptions-item label="批准后">
          两个方向同时放行：你可以看到它的密钥版本并向它分发，它也可以向你分发。
          <!--
            ⚠️ 一次提交的 N 条申请**各自独立处置**：管理员可以只批其中几条
               （部分批准是真实需求）。所以这里说的是"每一条都会…"，
               而不是"这一批会…" —— 后者会让用户以为必须整批通过。
          -->
          <b>每一条</b>批准后都按双向放行；管理员也可以只批其中几条。
        </el-descriptions-item>
      </el-descriptions>
      <el-form label-width="80px">
        <el-form-item label="申请理由" required>
          <el-input
            v-model="requestReason"
            type="textarea"
            :rows="3"
            maxlength="200"
            show-word-limit
            placeholder="说明用途，管理员据此审批（例如：与 X 节点同步业务密钥）"
          />
        </el-form-item>
      </el-form>
      <el-alert
        v-if="requestFeedback"
        :type="requestFeedback.ok ? 'success' : 'warning'"
        :closable="false"
        show-icon
      >
        <template #title>{{ requestFeedback.title }}</template>
        <div v-if="requestFeedback.detail" class="feedback-detail">{{ requestFeedback.detail }}</div>
      </el-alert>
      <template #footer>
        <el-button @click="requestOpen = false">取 消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitRequest">
          提交申请（{{ requestTargets.length }}）
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/**
 * 任务书「节点多级授权」→ 节点侧「节点授权」页。
 *
 * 数据来自两个接口（都在 `/node-self/*`，HTTP 恒 200、成败看 `code`）：
 *   * `GET /node-self/directory/`                —— 全网名录 + 与我的关系
 *   * `GET /node-self/authorization-requests/`   —— 我发起的 + 对方发起的
 *
 * ⚠️ 权限判据在服务端（`UserNodeAuthorization`），本页**不自己判**：
 *    「能不能发」由名录下发的 `relationship.outgoing` 决定；按钮的禁用理由
 *    也取自服务端字段（`canRequest`），而不是前端再推一遍 —— 两份判断必然漂移，
 *    而漂移的表现是"界面能点、后端拒绝"。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  cancelNodeAuthorizationRequest,
  listNodeDirectory,
  listSelfAuthorizationRequests,
  requestNodeAuthorization,
  requestNodeAuthorizations
} from '@/api/pqkds/node-self'
import { getSelfNode } from '@/api/pqkds/node-self'

const loading = ref(false)
const mapped = ref(false)
const nodes = ref([])
const requests = ref([])
const keyword = ref('')
const onlyFilter = ref('')

const requestOpen = ref(false)
/** 本次要申请的对端编号列表（单个 = 一个元素，多个 = 勾选的那批）。 */
const requestTargets = ref([])
const requestReason = ref('')
const requestFeedback = ref(null)
const submitting = ref(false)
/** 名录表格里勾中的行（批量提交用）。 */
const selectedNodes = ref([])

const NODE_STATUS_LABELS = {
  ACTIVE: '已激活',
  DISABLED: '已停用',
  PENDING_INIT: '待初始化'
}

function statusLabel(status) {
  return NODE_STATUS_LABELS[status] || status || '-'
}

function statusTagType(status) {
  if (status === 'ACTIVE') return 'success'
  if (status === 'DISABLED') return 'danger'
  return 'warning'
}

/**
 * 关系文案。**四态**，不是"授权/未授权"两态：
 *   * 双向已通 —— 谁都能发；
 *   * 仅我可发起 —— 我能发给它，它回不了（管理员手工只授了单向）；
 *   * 仅对方可发起 —— 反过来；
 *   * 待审批（两个方向各判）／未授权。
 */
function relationLabel(row) {
  const r = row.relationship || {}
  if (r.granted) return '已授权（双向）'
  if (r.outgoing === 'granted' && r.incoming !== 'granted') return '仅我可发起'
  if (r.incoming === 'granted' && r.outgoing !== 'granted') return '仅对方可发起'
  if (r.outgoing === 'pending') return '我申请中'
  if (r.incoming === 'pending') return '对方申请中'
  return '未授权'
}

function relationTagType(row) {
  const r = row.relationship || {}
  if (r.granted) return 'success'
  if (r.outgoing === 'granted' || r.incoming === 'granted') return 'warning'
  if (r.outgoing === 'pending' || r.incoming === 'pending') return 'info'
  return 'danger'
}

function requestStatusTagType(status) {
  if (status === 'approved') return 'success'
  if (status === 'rejected') return 'danger'
  if (status === 'cancelled') return 'info'
  return 'warning'
}

function formatTime(value) {
  if (!value) return '-'
  const d = new Date(String(value))
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString('zh-CN', { hour12: false })
}

/** 能不能点「申请授权」。服务端的 `canRequest` + 关系状态，前端不另推一套。 */
function canRequest(row) {
  if (row.canRequest === false) return false
  const r = row.relationship || {}
  if (r.granted) return false
  // 这一对已有未决申请就不必再发（服务端也是幂等的，这里只是别让用户白点）。
  return !r.pendingRequestId
}

function requestBlockedReason(row) {
  if (row.canRequest === false) return '该节点已停用，无法建立会话'
  const r = row.relationship || {}
  if (r.granted) return '已双向授权，无需申请'
  if (r.pendingRequestId) return `已有待审批的申请（#${r.pendingRequestId}）`
  return '发起与该节点建立会话的申请'
}

const filteredNodes = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return nodes.value.filter((n) => {
    if (kw && !(`${n.nodeCode} ${n.name}`.toLowerCase().includes(kw))) return false
    const r = n.relationship || {}
    if (onlyFilter.value === 'granted' && !r.granted) return false
    if (onlyFilter.value === 'pending'
      && r.outgoing !== 'pending' && r.incoming !== 'pending') return false
    if (onlyFilter.value === 'none'
      && (r.granted || r.outgoing !== 'none' || r.incoming !== 'none')) return false
    return true
  })
})

async function load() {
  loading.value = true
  try {
    const self = await getSelfNode()
    mapped.value = Boolean(self?.mapped)
    if (!mapped.value) {
      nodes.value = []
      requests.value = []
      return
    }
    const [dir, reqs] = await Promise.all([
      listNodeDirectory(),
      listSelfAuthorizationRequests()
    ])
    nodes.value = dir?.nodes || []
    // 两个方向拼成一张表，用 `__direction` 标明来源 —— 服务端刻意分成两组，
    // 页面合并展示时**必须带上方向**，否则"我申请 A"与"A 申请我"长得一模一样。
    requests.value = [
      ...(reqs?.outgoing || []).map((r) => ({ ...r, __direction: 'outgoing' })),
      ...(reqs?.incoming || []).map((r) => ({ ...r, __direction: 'incoming' }))
    ].sort((a, b) => String(b.createdAt || '').localeCompare(String(a.createdAt || '')))
  } catch (error) {
    ElMessage.error(error?.message || '读取节点授权信息失败')
  } finally {
    loading.value = false
  }
}

function openRequest(row) {
  requestTargets.value = [row.nodeCode]
  requestReason.value = ''
  requestFeedback.value = null
  requestOpen.value = true
}

/** 批量入口：把表格里勾中的行一起提交（与单个走**同一个对话框、同一个提交函数**）。 */
function openBatchRequest() {
  requestTargets.value = selectedNodes.value.map((row) => row.nodeCode)
  requestReason.value = ''
  requestFeedback.value = null
  requestOpen.value = true
}

async function submitRequest() {
  const reason = requestReason.value.trim()
  if (!reason) {
    ElMessage.warning('请填写申请理由（审批人据此判断）')
    return
  }
  const targets = [...requestTargets.value]
  if (!targets.length) {
    return
  }
  submitting.value = true
  requestFeedback.value = null
  try {
    if (targets.length === 1) {
      // 单个仍走**原路径**（响应形状与既有页面/脚本一致）。
      const data = await requestNodeAuthorization(targets[0], reason)
      if (data?.alreadyGranted) {
        requestFeedback.value = { ok: true, title: '已与对方双向授权，无需申请', detail: '' }
      } else {
        requestFeedback.value = {
          ok: true,
          title: data?.created === false ? '已有待审批的申请（未重复创建）' : '申请已提交，等待管理员审批',
          detail: ''
        }
      }
    } else {
      // 多个走批量端点：**逐条**回报，跳过/失败的原因如实列出。
      const data = await requestNodeAuthorizations(targets, reason)
      const skipped = data?.skipped || []
      requestFeedback.value = {
        ok: true,
        title: `已提交 ${data?.created?.length || 0} 条申请，等待管理员审批`
          + (skipped.length ? `（${skipped.length} 条未新建）` : ''),
        detail: skipped.map((s) => {
          const label = s.reason === 'ALREADY_PENDING' ? '已有待审批的申请'
            : s.reason === 'ALREADY_GRANTED' ? '两个方向都已授权'
              : (s.message || s.reason)
          return `${s.nodeId}：${label}`
        }).join('；')
      }
    }
    ElMessage.success('申请已提交')
    selectedNodes.value = []
    await load()
  } catch (error) {
    // 按错误码分支而不是匹配文案（文案随时会改）。`@/api/pqkds/http` 已把
    // `data.error_code` 提到 `error.errorCode` 上。
    const code = error?.errorCode
    if (code === 'ALREADY_AUTHORIZED' || code === 'AUTH_REQUEST_PENDING'
      || code === 'NOT_AUTHORIZED' || code === 'INVALID_PARAMETER') {
      ElMessage.warning(error.message)
    } else {
      ElMessage.error(error?.message || '提交申请失败')
    }
    await load()
  } finally {
    submitting.value = false
  }
}

async function handleCancel(row) {
  try {
    await ElMessageBox.confirm(
      `撤回对 ${row.targetNodeId} 的授权申请？撤回后可以重新申请。`,
      '撤回授权申请',
      { confirmButtonText: '撤 回', cancelButtonText: '取 消', type: 'warning' }
    )
  } catch {
    return
  }
  try {
    await cancelNodeAuthorizationRequest(row.id)
    ElMessage.success('申请已撤回')
    await load()
  } catch (error) {
    ElMessage.error(error?.message || '撤回失败')
    await load()
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
/* 批量提交的逐条反馈：可能有好几行，允许换行、不与标题挤在一行 */
.feedback-detail {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.6;
  word-break: break-all;
}
.mono {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 13px;
}
.hint {
  margin-left: 8px;
  color: var(--kms-text-secondary);
  font-size: 12px;
}
.muted {
  color: var(--kms-text-secondary);
  font-size: 12px;
}
.note {
  margin: 0 0 12px;
  color: var(--kms-text-secondary);
  font-size: 13px;
  line-height: 1.7;
}
.section-title {
  margin: 20px 0 10px;
  font-size: 14px;
  font-weight: 600;
  color: var(--kms-text-primary);
}
.node-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.node-name { font-weight: 600; }
</style>