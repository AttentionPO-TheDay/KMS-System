<template>
  <div class="app-container">
    <el-alert
      title="自动更新配置"
      type="info"
      :closable="false"
      style="margin-bottom: 16px"
    >
      <template #default>
        当前页面只调用后端 `PUT /lifecycle/keymanage/auto-update` 修改自动更新开关，不再编辑整条密钥记录。
      </template>
    </el-alert>

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
        >修改自动更新</el-button>
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
      <el-table-column label="自动更新" align="center" width="100">
        <template #default="scope">
          <el-tag :type="isAutoUpdateEnabled(scope.row.autoUpdate) ? 'success' : 'info'">
            {{ isAutoUpdateEnabled(scope.row.autoUpdate) ? '启用' : '关闭' }}
          </el-tag>
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

    <el-dialog title="修改自动更新状态" v-model="open" width="420px" append-to-body>
      <el-form ref="keymanageRef" :model="form" label-width="90px">
        <el-form-item label="密钥ID">
          <el-input :model-value="form.keyId" disabled />
        </el-form-item>
        <el-form-item label="密钥名称">
          <el-input :model-value="form.keyName" disabled />
        </el-form-item>
        <el-form-item label="自动更新">
          <el-switch v-model="form.autoUpdateEnabled" inline-prompt active-text="开" inactive-text="关" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button type="primary" @click="submitForm">确 定</el-button>
          <el-button @click="cancel">取 消</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="KeyAutoUpdate">
import { listKeymanage, getKeymanage, updateKeyAutoUpdate } from "@/api/lifecycle/lifecycle"

const { proxy } = getCurrentInstance()

const keymanageList = ref([])
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
  autoUpdateEnabled: false,
  status: ''
})

function getList() {
  loading.value = true
  listKeymanage(queryParams.value).then(response => {
    keymanageList.value = response.rows || []
    total.value = response.total || 0
  }).finally(() => {
    loading.value = false
  })
}

function reset() {
  form.value = { keyId: null, keyName: '', autoUpdateEnabled: false, status: '' }
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
    form.value = {
      keyId: current.keyId,
      keyName: current.keyName,
      autoUpdateEnabled: isAutoUpdateEnabled(current.autoUpdate),
      status: current.status
    }
    open.value = true
  })
}

function submitForm() {
  updateKeyAutoUpdate({
    keyId: form.value.keyId,
    autoUpdate: form.value.autoUpdateEnabled ? '1' : '0'
  }).then(() => {
    proxy.$modal.msgSuccess("自动更新状态修改成功")
    open.value = false
    getList()
  })
}

function isAutoUpdateEnabled(value) {
  return value === 1 || value === '1' || value === true || value === 'true'
}

function isRevoked(status) {
  return status === '3' || status === 'Revoked' || status === 'REVOKED'
}

getList()
</script>
