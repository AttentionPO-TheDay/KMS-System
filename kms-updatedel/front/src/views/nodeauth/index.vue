<template>
  <div class="app-container">
    <el-card class="panel" shadow="never">
      <template #header>
        <div class="panel-head">
          <span>节点分发授权</span>
          <div class="panel-actions">
            <!--
              这里原来有一个「去「权限申请」」按钮，指向 `/audit/permission/request`。
              阶段 8 已整体删除那套审批流与其页面（理由见 35_remove_permission_request_menu.sql：
              那套审批**不承担真实授权作用**，留着只会形成第二套权限语义），当时漏了这个按钮。

              ⚠️ 但"申请-审批"这条路径**现在又有了**，只是换了个主体与落点：
                 节点侧「节点授权」页发起、**在本页上方的待审批区审批**，
                 批准即真的写授权行。所以上面那句"不存在申请-审批路径"已经不成立，
                 这里按现状改写 —— 注释与代码相反比没有注释更危险。
            -->
            <el-button type="primary" size="small" @click="openGrant">新增授权</el-button>
          </div>
        </div>
      </template>

      <!--
        待审批的节点授权申请（任务书「节点多级授权」）。
        节点在「节点授权」页发起，这里批准/驳回。
        ⚠️ 批准 = 真的写授权行（默认双向各一行），不是改一个状态字。
      -->
      <div v-if="pendingRequests.length" class="pending-block">
        <div class="pending-head">
          <span class="pending-title">待审批的授权申请</span>
          <el-tag size="small" type="warning">{{ pendingRequests.length }} 条待处理</el-tag>
        </div>
        <el-table :data="pendingRequests" size="small" v-loading="pendingLoading">
          <el-table-column label="申请节点" min-width="160">
            <template #default="{ row }">
              <span class="mono">{{ row.requesterNodeCode }}</span>
            </template>
          </el-table-column>
          <el-table-column label="希望通信的节点" min-width="160">
            <template #default="{ row }">
              <span class="mono">{{ row.targetNodeCode }}</span>
            </template>
          </el-table-column>
          <el-table-column label="申请理由" min-width="200" prop="reason" show-overflow-tooltip />
          <el-table-column label="提交时间" width="170">
            <template #default="{ row }">{{ formatTime(row.createdAt) }}</template>
          </el-table-column>
          <el-table-column label="审批说明" min-width="190">
            <template #default="{ row }">
              <!-- 批准时会「重新激活」而不是新建 —— 审批人该在点之前就知道 -->
              <span v-if="row.existingForward?.status === 'revoked' || row.existingBackward?.status === 'revoked'" class="warn">
                该对节点此前有授权被撤销过，批准将重新激活
              </span>
              <span v-else-if="row.requesterUserMissing || row.targetUserMissing" class="warn">
                有节点未关联登录账号，无法批准
              </span>
              <span v-else class="muted">批准后双向放行</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150" align="center">
            <template #default="{ row }">
              <el-button
                link
                type="primary"
                size="small"
                :disabled="row.requesterUserMissing || row.targetUserMissing"
                @click="handleApprove(row)"
              >
                批准
              </el-button>
              <el-button link type="danger" size="small" @click="handleReject(row)">驳回</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

<el-form :inline="true" class="filter-bar">
        <el-form-item label="用户">
          <el-select
            v-model="filter.userId"
            clearable
            filterable
            placeholder="全部用户"
            style="width: 200px"
            @change="load"
          >
            <el-option
              v-for="u in users"
              :key="u.userId"
              :label="`${u.userName}（#${u.userId}）`"
              :value="u.userId"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filter.status" clearable placeholder="全部" style="width: 140px" @change="load">
            <el-option label="有效" value="active" />
            <el-option label="已撤销" value="revoked" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="load">查询</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="items" size="small" v-loading="loading" empty-text="还没有授权记录">
        <el-table-column label="用户" width="160">
          <template #default="scope">{{ userNameOf(scope.row.userId) }}（#{{ scope.row.userId }}）</template>
        </el-table-column>
        <el-table-column label="节点" min-width="180">
          <template #default="scope">{{ scope.row.nodeName }}（{{ scope.row.nodeCode }}）</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="scope">
            <el-tag size="small" :type="scope.row.status === 'active' ? 'success' : 'info'">
              {{ scope.row.status === 'active' ? '有效' : '已撤销' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="授权人" prop="grantedBy" width="110" />
        <el-table-column label="授权时间" width="170">
          <template #default="scope">{{ formatTime(scope.row.grantedAt) }}</template>
        </el-table-column>
        <el-table-column label="撤销时间" width="170">
          <template #default="scope">{{ formatTime(scope.row.revokedAt) }}</template>
        </el-table-column>
        <el-table-column label="备注" prop="remark" min-width="140" show-overflow-tooltip />
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="scope">
            <el-button
              link
              type="danger"
              :disabled="scope.row.status !== 'active'"
              @click="handleRevoke(scope.row)"
            >
              撤销
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ------------------------------------------------------------------
         新增授权
         ------------------------------------------------------------------ -->
    <el-dialog v-model="grantOpen" title="新增节点授权" width="560px" append-to-body destroy-on-close>
      <el-form label-width="90px">
        <el-form-item label="用户">
          <el-select v-model="grantForm.userId" filterable placeholder="选择用户" class="full-width">
            <el-option
              v-for="u in users"
              :key="u.userId"
              :label="`${u.userName}（#${u.userId}）`"
              :value="u.userId"
            />
          </el-select>
          <div class="form-hint">
            列表来自主 KMS 的账号表（`kms.sys_user`），由服务端代理转发，内部令牌不下发浏览器。
          </div>
        </el-form-item>
        <el-form-item label="节点">
          <el-select v-model="grantForm.nodeId" filterable placeholder="选择节点" class="full-width">
            <el-option
              v-for="n in nodes"
              :key="n.id"
              :label="`${n.name}（${n.nodeId}）`"
              :value="n.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="grantForm.remark" placeholder="可选，例如申请单号" />
        </el-form-item>
      </el-form>

      <el-alert v-if="grantError" type="error" :closable="false" show-icon>{{ grantError }}</el-alert>

      <template #footer>
        <el-button @click="grantOpen = false">取 消</el-button>
        <el-button type="primary" :loading="granting" @click="handleGrant">授 权</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/**
 * 管理端「节点鉴权」页（P3 步骤 10 / D5）。
 *
 * 授权关系是分发模块（Django / falcon_kds）的数据，本页只是它的调用方 ——
 * 管理端 Java 不跨库去写它。角色判定（`roleLevel <= 0`）在服务端做，
 * 前端不做判断：被拒时如实显示 403 的说明，而不是自己藏起按钮假装安全。
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  decideAuthorizationRequest,
  grantNodeAuthorization,
  listAdminUsers,
  listAuthorizationRequests,
  listNodeAuthorizations,
  revokeNodeAuthorization
} from '@/api/nodeauth/nodeauth'
import { listDistributionNodes } from '@/api/nodeauth/nodeauth'

const items = ref([])
const users = ref([])
const nodes = ref([])
const loading = ref(false)

/**
 * 待审批的节点授权申请（任务书「节点多级授权」）。
 *
 * ⚠️ 与下面的授权列表**是两张不同的表**：这里是"申请"（流程记录），
 *    下面是"授权"（真正的权限）。批准会把前者变成后者 —— 但放行判据
 *    自始至终只读后者（服务端的 `authorized_node_ids`）。
 */
const pendingRequests = ref([])
const pendingLoading = ref(false)

const filter = reactive({ userId: null, status: null })

const grantOpen = ref(false)
const granting = ref(false)
const grantError = ref('')
const grantForm = reactive({ userId: null, nodeId: null, remark: '' })

async function load() {
  loading.value = true
  try {
    const params = {}
    if (filter.userId) params.userId = filter.userId
    if (filter.status) params.status = filter.status
    const data = await listNodeAuthorizations(params)
    items.value = data?.items || []
  } catch (error) {
    ElMessage.error(`加载授权列表失败：${error.message}`)
  } finally {
    loading.value = false
  }
}

async function loadUsers() {
  try {
    const data = await listAdminUsers()
    users.value = data?.items || []
  } catch (error) {
    // 这个失败要显式说出来：没有用户列表，整个页面就没法用，
    // 静默失败只会让人以为是"没有用户"。
    ElMessage.error(`加载账号列表失败：${error.message}`)
  }
}

async function loadNodes() {
  try {
    const data = await listDistributionNodes()
    nodes.value = data?.rows || data || []
  } catch (error) {
    ElMessage.error(`加载节点列表失败：${error.message}`)
  }
}

function userNameOf(userId) {
  const hit = users.value.find((u) => u.userId === userId)
  return hit ? hit.userName : `用户${userId}`
}

function openGrant() {
  grantForm.userId = null
  grantForm.nodeId = null
  grantForm.remark = ''
  grantError.value = ''
  grantOpen.value = true
}

async function handleGrant() {
  if (!grantForm.userId || !grantForm.nodeId) {
    grantError.value = '请选择用户与节点'
    return
  }
  granting.value = true
  grantError.value = ''
  try {
    const data = await grantNodeAuthorization({
      userId: grantForm.userId,
      nodeId: grantForm.nodeId,
      remark: grantForm.remark || null
    })
    // 服务端对已撤销的记录是"重新激活"而不是新增行 —— 如实告诉管理员，
    // 否则他会以为多了一条记录，而列表里只多了一行状态变化。
    ElMessage.success(data?.created ? '授权成功' : '该授权已存在，已置为有效')
    grantOpen.value = false
    await load()
  } catch (error) {
    grantError.value = error.message
  } finally {
    granting.value = false
  }
}

async function handleRevoke(row) {
  try {
    await ElMessageBox.confirm(
      `确定撤销「${userNameOf(row.userId)}」对节点「${row.nodeName}」的通信权限？` +
        '撤销后该用户将无法再向此节点分发密钥（记录会保留以备审计）。',
      '撤销授权',
      { type: 'warning', confirmButtonText: '撤 销', cancelButtonText: '取 消' }
    )
  } catch {
    return
  }
  try {
    await revokeNodeAuthorization(row.id)
    ElMessage.success('已撤销')
    await load()
  } catch (error) {
    ElMessage.error(`撤销失败：${error.message}`)
  }
}

function formatTime(value) {
  if (!value) {
    return '-'
  }
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN', { hour12: false })
}

// ---------------------------------------------------------------------------
// 授权申请：审批（任务书「节点多级授权」）
// ---------------------------------------------------------------------------

async function loadPendingRequests() {
  pendingLoading.value = true
  try {
    const data = await listAuthorizationRequests({ status: 'pending' })
    pendingRequests.value = data?.items || []
  } catch (error) {
    // 这个失败要显式说出来：静默失败会让人以为"没有待审批的申请"，
    // 而那正好是最坏的一种误解（节点在等，管理员以为没人等）。
    ElMessage.error(`加载待审批申请失败：${error.message}`)
  } finally {
    pendingLoading.value = false
  }
}

/** 批准。二次确认里说清"会写两个方向的授权"。 */
async function handleApprove(row) {
  const needReactivate = row.existingForward?.status === 'revoked'
    || row.existingBackward?.status === 'revoked'
  try {
    await ElMessageBox.confirm(
      `批准后 ${row.requesterNodeCode} 与 ${row.targetNodeCode} 将**双向**获得通信权限`
      + `（两个方向各一条授权记录）。`
      + (needReactivate ? '\n注意：该对节点此前有授权被撤销过，本次将重新激活它。' : ''),
      '批准授权申请',
      { confirmButtonText: '批 准', cancelButtonText: '取 消', type: 'warning', dangerouslyUseHTMLString: false }
    )
  } catch {
    return
  }
  try {
    const data = await decideAuthorizationRequest(row.id, { decision: 'approve' })
    // 如实回报"这次改变了什么"：新建与重新激活是两件事，别混成一句"成功"。
    const created = data?.granted?.created || []
    const reactivated = data?.granted?.reactivated || []
    const parts = []
    if (created.length) parts.push(`新建授权 ${created.length} 条`)
    if (reactivated.length) parts.push(`重新激活 ${reactivated.length} 条`)
    ElMessage.success(`已批准${parts.length ? '（' + parts.join('、') + '）' : '（授权此前已存在）'}`)
    if (data?.chainWarning) {
      // 存证失败与授权成功是两件事：不隐藏，但不阻断。
      ElMessage.warning(data.chainWarning)
    }
    await Promise.all([loadPendingRequests(), load()])
  } catch (error) {
    ElMessage.error(`批准失败：${error.message}`)
    await loadPendingRequests()
  }
}

/** 驳回。理由必填 —— 节点侧看到的只有这句话。 */
async function handleReject(row) {
  let remark = ''
  try {
    const result = await ElMessageBox.prompt(
      `驳回 ${row.requesterNodeCode} → ${row.targetNodeCode} 的申请。请写明理由（对方会看到）。`,
      '驳回授权申请',
      {
        confirmButtonText: '驳 回',
        cancelButtonText: '取 消',
        inputType: 'textarea',
        inputPlaceholder: '例如：业务上不需要与该节点通信',
        inputValidator: (value) => (String(value || '').trim() ? true : '必须填写驳回理由')
      }
    )
    remark = String(result?.value || '').trim()
  } catch {
    return
  }
  try {
    const data = await decideAuthorizationRequest(row.id, { decision: 'reject', remark })
    ElMessage.success('已驳回（未授予任何权限）')
    if (data?.chainWarning) {
      ElMessage.warning(data.chainWarning)
    }
    await loadPendingRequests()
  } catch (error) {
    ElMessage.error(`驳回失败：${error.message}`)
    await loadPendingRequests()
  }
}

onMounted(async () => {
  await Promise.all([loadUsers(), loadNodes()])
  await Promise.all([load(), loadPendingRequests()])
})
</script>

<style scoped>
.panel {
  border-radius: 10px;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.panel-actions {
  display: flex;
  gap: 8px;
}

/* 与主体说明分开一段，点明"这不是提权申请"，避免和权限申请混淆 */
.scope-note {
  margin-top: 6px;
  color: var(--el-text-color-secondary);
  line-height: 1.7;
}

.filter-bar {
  margin-bottom: 8px;
}

.full-width {
  width: 100%;
}

.form-hint {
  margin-top: 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.mb16 {
  margin-bottom: 16px;
}

/* 待审批区：与下方「授权列表」在视觉上分块 —— 两者是**不同的东西**
   （申请是流程记录，授权才是权限）。 */
.pending-block {
  margin-bottom: 20px;
  padding: 12px 14px;
  border: 1px solid var(--el-color-warning-light-5, #f3d19e);
  border-radius: 8px;
  background: var(--el-color-warning-light-9, #fdf6ec);
}
.pending-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.pending-title {
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.mono {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 13px;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.warn {
  color: var(--el-color-warning, #e6a23c);
  font-size: 12px;
}
</style>
