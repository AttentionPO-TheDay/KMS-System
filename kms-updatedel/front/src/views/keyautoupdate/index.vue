<template>
  <div class="app-container">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="88px">
      <el-form-item label="用户ID" prop="userId">
        <el-input v-model="queryParams.userId" placeholder="请输入用户ID" clearable @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="用户名" prop="userName">
        <el-input v-model="queryParams.userName" placeholder="请输入用户名" clearable @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="密钥名称" prop="keyName">
        <el-input v-model="queryParams.keyName" placeholder="请输入密钥名称" clearable @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button
          type="primary"
          plain
          icon="Edit"
          :disabled="single"
          @click="openDialog()"
          v-hasPermi="['lifecycle:keymanage:edit']"
          style="padding: 6px 12px; margin-top: 15px"
        >配置自动更新</el-button>
      </el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList" />
    </el-row>

    <el-table v-loading="loading" :data="keymanageList" @selection-change="handleSelectionChange">
      <el-table-column type="selection" width="55" align="center" />
      <el-table-column label="密钥ID" align="center" prop="keyId" width="90" />
      <el-table-column label="用户名" align="center" prop="userName" width="120" />
      <el-table-column label="算法类型" align="center" prop="encrytType" min-width="130" />
      <el-table-column label="算法名称" align="center" prop="encrytName" width="120" />
      <el-table-column label="密钥名称" align="center" prop="keyName" min-width="140" />
      <el-table-column label="用途" align="center" prop="keyUse" min-width="140" />
      <el-table-column label="自动更新" align="center" width="110">
        <template #default="scope">
          <!-- KYBER/FALCON 私钥不在服务端，托管轮换必然失败。历史遗留已开启的
               行如实显示为"已开启·不支持"，并提示去关掉，而不是假装开关没问题。 -->
          <el-tooltip v-if="isAutoUpdateEnabled(scope.row.autoUpdate) && isManagedRotationUnsupported(scope.row.encrytName)"
                      content="该算法私钥不在服务端（文档 §5.3），服务端造不出新版本，每轮托管轮换都会失败；请关闭开关" placement="top">
            <el-tag type="danger">已开启·不支持</el-tag>
          </el-tooltip>
          <el-tag v-else :type="isAutoUpdateEnabled(scope.row.autoUpdate) ? 'success' : 'info'">
            {{ isAutoUpdateEnabled(scope.row.autoUpdate) ? '启用' : '关闭' }}
          </el-tag>
        </template>
      </el-table-column>
      <!-- KMS-019：「上次执行」来自 kms_auto_update_item（每把密钥最近一条）。
           没有记录时显示 - —— 不显示"成功"，因为"没跑过"与"跑成功了"是两回事。 -->
      <el-table-column label="上次执行" align="center" width="160">
        <template #default="scope">
          <template v-if="latestByKey[scope.row.keyId]">
            <el-tooltip :content="latestTooltip(latestByKey[scope.row.keyId])" placement="top">
              <el-tag :type="latestByKey[scope.row.keyId].result === 'SUCCESS' ? 'success' : 'danger'" size="small">
                {{ latestByKey[scope.row.keyId].result === 'SUCCESS' ? '成功' : '失败' }}
              </el-tag>
            </el-tooltip>
            <div class="kau-time">{{ shortTime(latestByKey[scope.row.keyId].updatedAt) }}</div>
          </template>
          <span v-else class="kau-muted">-</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" align="center" width="100">
        <template #default="scope">
          <el-tag :type="isRevoked(scope.row.status) ? 'danger' : 'success'">
            {{ isRevoked(scope.row.status) ? '已回收' : '可配置' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" align="center" width="120">
        <template #default="scope">
          <el-button
            link
            type="primary"
            icon="Edit"
            :disabled="isRevoked(scope.row.status)"
            @click="openDialog(scope.row)"
            v-hasPermi="['lifecycle:keymanage:edit']"
          >配置</el-button>
        </template>
      </el-table-column>
    </el-table>

    <pagination
      v-show="total > 0"
      :total="total"
      v-model:page="queryParams.pageNum"
      v-model:limit="queryParams.pageSize"
      @pagination="getList"
    />

    <el-dialog title="配置自动更新" v-model="open" width="460px" append-to-body>
      <el-form ref="keymanageRef" :model="form" label-width="90px">
        <el-form-item label="密钥ID">
          <el-input :model-value="form.keyId" disabled />
        </el-form-item>
        <el-form-item label="密钥名称">
          <el-input :model-value="form.keyName" disabled />
        </el-form-item>
        <el-form-item label="算法">
          <el-input :model-value="form.encrytName" disabled />
        </el-form-item>
        <el-form-item label="自动更新">
          <el-switch
            v-model="form.autoUpdateEnabled"
            inline-prompt
            active-text="开"
            inactive-text="关"
            :disabled="form.unsupported && !form.autoUpdateEnabled"
          />
        </el-form-item>
        <el-alert
          v-if="form.unsupported"
          type="warning"
          :closable="false"
          show-icon
          title="该算法不支持服务端托管轮换"
          description="私钥不在服务端（文档 §5.3），开启后每轮都会失败。历史已开启的开关可关闭并保存，但不能重新开启；若需更新，请由节点侧重新 KeyGen 后登记新公钥，或改用支持托管轮换的算法。"
        />
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button type="primary" :disabled="form.unsupported && form.autoUpdateEnabled" @click="submitForm">确 定</el-button>
          <el-button @click="cancel">取 消</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="KeyAutoUpdate">
import { listKeymanage, getKeymanage, updateKeyAutoUpdate, listLatestAutoUpdateItems } from "@/api/lifecycle/lifecycle"

const { proxy } = getCurrentInstance()

const keymanageList = ref([])
const latestByKey = ref({})
const open = ref(false)
const loading = ref(true)
const showSearch = ref(true)
const ids = ref([])
const single = ref(true)
const total = ref(0)

const queryParams = ref({
  pageNum: 1,
  pageSize: 10,
  userId: null,
  userName: null,
  keyName: null
})

const form = ref({
  keyId: null,
  keyName: '',
  encrytName: '',
  unsupported: false,
  autoUpdateEnabled: false,
  status: ''
})

function getList() {
  loading.value = true
  listKeymanage(queryParams.value).then(response => {
    keymanageList.value = response.rows || []
    total.value = response.total || 0
    loadLatest()
  }).finally(() => {
    loading.value = false
  })
}

/**
 * 「上次执行」列：一次带当前页的 keyIds 取每把密钥的最近一条执行结果。
 * 失败不阻塞列表（拿不到就显示 -），但要留下可查的线索 ——
 * 静默吞掉会让"这一列怎么老是空的"变成无从下手的现象。
 */
function loadLatest() {
  const keyIds = keymanageList.value.map(item => item.keyId).filter(id => id != null)
  if (keyIds.length === 0) {
    latestByKey.value = {}
    return
  }
  listLatestAutoUpdateItems(keyIds).then(response => {
    const map = {}
    for (const item of (response.data || [])) {
      map[item.keyId] = item
    }
    latestByKey.value = map
  }).catch(error => {
    latestByKey.value = {}
    console.warn('加载「上次执行」失败：', error)
  })
}

function reset() {
  form.value = { keyId: null, keyName: '', encrytName: '', unsupported: false, autoUpdateEnabled: false, status: '' }
}

function cancel() {
  open.value = false
  reset()
}

function handleQuery() {
  queryParams.value.pageNum = 1
  getList()
}

function resetQuery() {
  proxy.resetForm("queryRef")
  handleQuery()
}

function handleSelectionChange(selection) {
  ids.value = selection.map(item => item.keyId)
  single.value = selection.length !== 1
}

function openDialog(row) {
  reset()
  const keyId = row?.keyId || ids.value[0]
  if (!keyId) {
    proxy.$modal.msgWarning("请先选择一条密钥记录")
    return
  }
  getKeymanage(keyId).then(response => {
    const current = response.data
    if (isRevoked(current.status)) {
      proxy.$modal.msgWarning("已回收密钥不允许再配置自动更新")
      return
    }
    const unsupported = isManagedRotationUnsupported(current.encrytName)
    form.value = {
      keyId: current.keyId,
      keyName: current.keyName,
      encrytName: current.encrytName,
      unsupported,
      autoUpdateEnabled: isAutoUpdateEnabled(current.autoUpdate),
      status: current.status
    }
    open.value = true
  })
}

function submitForm() {
  if (form.value.unsupported && form.value.autoUpdateEnabled) {
    proxy.$modal.msgWarning('该算法不支持服务端托管轮换，请关闭自动更新后保存')
    return
  }
  updateKeyAutoUpdate({
    keyId: form.value.keyId,
    autoUpdate: form.value.autoUpdateEnabled ? '1' : '0'
  }).then(() => {
    proxy.$modal.msgSuccess(form.value.autoUpdateEnabled ? '自动更新已启用，到时间会自动执行更新' : '自动更新已关闭')
    open.value = false
    getList()
  }).catch(error => {
    // 服务端对 KYBER/FALCON 的开启请求有明确拒绝文案（D3 守卫），
    // 这里兜底展示 —— 不能让拒绝被吞成"点了没反应"。
    proxy.$modal.msgError(error?.message || '自动更新配置失败')
  })
}

function isAutoUpdateEnabled(value) {
  return value === 1 || value === '1' || value === true || value === 'true'
}

function isRevoked(status) {
  return status === '3' || status === 'Revoked' || status === 'REVOKED'
}

/** 与后端 LifecycleService#assertAutoUpdateEnableAllowed 同一口径。 */
function isManagedRotationUnsupported(encrytName) {
  // 后端按 contains + 大写归一化识别算法；这里必须同口径，
  // 否则 KYBER-768/FALCON-512 会在页面显示为可托管，提交后才被拒。
  const name = String(encrytName || '').trim().toUpperCase()
  return name.includes('KYBER') || name.includes('FALCON')
}

function shortTime(value) {
  if (!value) return ''
  const text = String(value)
  // 后端返回 'yyyy-MM-dd HH:mm:ss'；只显示月-日 时:分，完整值在 tooltip 里。
  return text.length >= 16 ? text.slice(5, 16) : text
}

function latestTooltip(item) {
  if (!item) return ''
  const parts = [`上次执行：${item.updatedAt || '-'}`]
  if (item.result === 'SUCCESS') {
    parts.push(`成功：v${item.fromVersion} → v${item.toVersion}`)
  } else {
    parts.push(`失败：${item.reason || '（无原因记录）'}`)
  }
  if (item.chainResultStatus === '1') parts.push('链上/接收：成功')
  else if (item.chainResultStatus === '2') parts.push('链上/接收：失败')
  else if (item.chainResultStatus === '0') parts.push('链上/接收：处理中')
  return parts.join('\n')
}

getList()
</script>

<style scoped>
.kau-time { color: var(--kms-text-secondary, #909399); font-size: 12px; margin-top: 2px; }
.kau-muted { color: var(--kms-text-secondary, #909399); }
</style>