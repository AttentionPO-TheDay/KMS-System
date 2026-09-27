<template>
  <div class="app-container">
    <el-card class="panel" shadow="never">
      <template #header>
        <div class="panel-head">
          <span>节点分发授权</span>
          <div class="panel-actions">
            <el-button size="small" @click="$router.push('/audit/permission/request')">
              去「权限申请」
            </el-button>
            <el-button type="primary" size="small" @click="openGrant">新增授权</el-button>
          </div>
        </div>
      </template>

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
  grantNodeAuthorization,
  listAdminUsers,
  listNodeAuthorizations,
  revokeNodeAuthorization
} from '@/api/nodeauth/nodeauth'
import { listDistributionNodes } from '@/api/nodeauth/nodeauth'

const items = ref([])
const users = ref([])
const nodes = ref([])
const loading = ref(false)

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

onMounted(async () => {
  await Promise.all([loadUsers(), loadNodes()])
  await load()
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
</style>
