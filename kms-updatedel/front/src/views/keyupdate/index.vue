<template>
  <div class="app-container">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="68px">
      <el-form-item label="用户ID" prop="userId">
        <el-input v-model="queryParams.userId" placeholder="请输入用户ID" clearable @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="用户名" prop="userName">
        <el-input v-model="queryParams.userName" placeholder="请输入用户名" clearable @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="算法名称" prop="encrytName">
        <el-input v-model="queryParams.encrytName" placeholder="请输入算法名称" clearable @keyup.enter="handleQuery" />
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
          type="success"
          plain
          icon="Refresh"
          :disabled="single"
           @click="openUpdateDialog()"
           v-hasPermi="['lifecycle:keymanage:edit']"
           style="padding: 6px 12px; margin-top: 15px"
        >密钥更新</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="primary"
          plain
          icon="Refresh"
          :disabled="multiple"
          @click="handleBatchUpdate"
          v-hasPermi="['lifecycle:keymanage:edit']"
          style="padding: 6px 12px; margin-top: 15px"
        >批量更新</el-button>
      </el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList" />
    </el-row>

    <el-table v-loading="loading" :data="keymanageList" @selection-change="handleSelectionChange">
      <el-table-column type="selection" width="55" align="center" />
      <el-table-column label="密钥ID" align="center" prop="keyId" width="90" />
      <el-table-column label="用户ID" align="center" prop="userId" width="90" />
      <el-table-column label="用户名" align="center" prop="userName" width="120" />
      <el-table-column label="算法类型" align="center" prop="encrytType" min-width="130" />
      <el-table-column label="算法名称" align="center" prop="encrytName" width="120" />
      <el-table-column label="密钥名称" align="center" prop="keyName" min-width="140" />
      <el-table-column label="用途" align="center" prop="keyUse" min-width="140" />
      <el-table-column label="版本" align="center" prop="version" width="80" />
      <el-table-column label="自动更新" align="center" width="100">
        <template #default="scope">
          <el-tag :type="isAutoUpdateEnabled(scope.row.autoUpdate) ? 'success' : 'info'">
            {{ isAutoUpdateEnabled(scope.row.autoUpdate) ? '启用' : '关闭' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" align="center" width="100">
        <template #default="scope">
          <el-tag :type="statusTagType(scope.row.status)">{{ statusText(scope.row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="上链状态" align="center" width="100">
        <template #default="scope">
          <el-tag :type="chainStatusType(scope.row.chainStatus)">{{ chainStatusText(scope.row.chainStatus) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="更新时间" align="center" prop="updTime" width="170" />
      <el-table-column label="操作" align="center" width="120">
        <template #default="scope">
          <el-button
            link
            type="primary"
            icon="Refresh"
            :disabled="isRevoked(scope.row.status)"
            @click="openUpdateDialog(scope.row)"
            v-hasPermi="['lifecycle:keymanage:edit']"
          >更新</el-button>
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

    <el-dialog :title="dialogTitle" v-model="open" width="560px" append-to-body>
      <el-form ref="keymanageRef" :model="form" :rules="rules" label-width="96px">
        <el-form-item label="密钥ID">
          <el-input :model-value="form.keyId" disabled />
        </el-form-item>
        <el-form-item label="用户名">
          <el-input :model-value="form.userName" disabled />
        </el-form-item>
        <el-form-item label="算法类型">
          <el-input :model-value="form.encrytType" disabled />
        </el-form-item>
        <el-form-item label="算法名称">
          <el-input :model-value="form.encrytName" disabled />
        </el-form-item>
        <el-form-item label="密钥名称" prop="keyName">
          <el-input v-model="form.keyName" placeholder="可选，不填则沿用当前值" />
        </el-form-item>
        <el-form-item label="密钥用途" prop="keyUse">
          <el-input v-model="form.keyUse" placeholder="可选，不填则沿用当前值" />
        </el-form-item>
        <el-form-item label="所属域" prop="keyDomain" v-if="isSsclKey(form)">
          <el-input v-model="form.keyDomain" placeholder="SSCL 更新时可调整所属域" />
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

<script setup name="KeyUpdate">
import { listKeymanage, getKeymanage, updateKeymanage } from "@/api/lifecycle/lifecycle"

const { proxy } = getCurrentInstance()

const keymanageList = ref([])
const open = ref(false)
const loading = ref(true)
const showSearch = ref(true)
const ids = ref([])
const single = ref(true)
const multiple = ref(true)
const total = ref(0)
const dialogTitle = ref('密钥更新')

const data = reactive({
  form: {},
  queryParams: {
    pageNum: 1,
    pageSize: 10,
    userId: null,
    userName: null,
    encrytName: null,
    keyName: null
  },
  rules: {
    keyName: [{ max: 64, message: "密钥名称长度不能超过64个字符", trigger: "blur" }],
    keyUse: [{ max: 128, message: "密钥用途长度不能超过128个字符", trigger: "blur" }],
    keyDomain: [{ max: 64, message: "所属域长度不能超过64个字符", trigger: "blur" }]
  }
})

const { queryParams, form, rules } = toRefs(data)

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
  form.value = {
    keyId: null,
    userName: '',
    encrytType: '',
    encrytName: '',
    keyName: '',
    keyUse: '',
    keyDomain: '',
    autoUpdateEnabled: false,
    batchMode: false,
    status: ''
  }
  proxy.resetForm("keymanageRef")
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
  multiple.value = !selection.length
}

function openUpdateDialog(row) {
  reset()
  const keyId = row?.keyId || ids.value[0]
  if (!keyId) {
    proxy.$modal.msgWarning("请先选择一条密钥记录")
    return
  }
  getKeymanage(keyId).then(response => {
    const current = response.data
    form.value = {
      keyId: current.keyId,
      userName: current.userName,
      encrytType: current.encrytType,
      encrytName: current.encrytName,
      keyName: current.keyName,
      keyUse: current.keyUse,
      keyDomain: current.keyDomain,
      autoUpdateEnabled: isAutoUpdateEnabled(current.autoUpdate),
      batchMode: false,
      status: current.status
    }
    if (isRevoked(current.status)) {
      proxy.$modal.msgWarning("该密钥已回收，无法更新")
      return
    }
    dialogTitle.value = '密钥更新'
    open.value = true
  })
}

async function handleBatchUpdate() {
  if (!ids.value.length) {
    proxy.$modal.msgWarning('请先选择需要更新的密钥')
    return
  }
  proxy.$modal.confirm(`是否确认批量更新选中的 ${ids.value.length} 条密钥记录？`).then(async () => {
    for (const keyId of ids.value) {
      const response = await getKeymanage(keyId)
      const current = response.data
      if (!current || isRevoked(current.status)) {
        continue
      }
      await updateKeymanage({
        keyId: current.keyId,
        keyName: current.keyName,
        keyUse: current.keyUse,
        keyDomain: isSsclKey(current) ? blankToNull(current.keyDomain) : null,
        autoUpdate: isAutoUpdateEnabled(current.autoUpdate) ? '1' : '0'
      })
    }
    proxy.$modal.msgSuccess('批量更新已提交，结果将推送给用户端接收')
    getList()
  }).catch(() => {})
}

function submitForm() {
  proxy.$refs["keymanageRef"].validate(valid => {
    if (!valid) {
      return
    }
    updateKeymanage({
      keyId: form.value.keyId,
      keyName: blankToNull(form.value.keyName),
      keyUse: blankToNull(form.value.keyUse),
      keyDomain: isSsclKey(form.value) ? blankToNull(form.value.keyDomain) : null,
      autoUpdate: form.value.autoUpdateEnabled ? '1' : '0'
      }).then(() => {
        proxy.$modal.msgSuccess("更新成功，结果已推送到用户端")
        open.value = false
        getList()
      })
  })
}

function blankToNull(value) {
  return value == null || String(value).trim() === '' ? null : String(value).trim()
}

function isSsclKey(row) {
  return row.encrytType === '无证书非对称加密' && row.encrytName === 'SSCL'
}

function isAutoUpdateEnabled(value) {
  return value === 1 || value === '1' || value === true || value === 'true'
}

function isRevoked(status) {
  return status === '3' || status === 'REVOKED'
}

function statusText(status) {
  return {
    Valid: '有效',
    Active: '有效',
    Frozen: '已冻结',
    Replaced: '已更新',
    Rotated: '已更新',
    Revoked: '已回收',
    '0': '有效',
    '1': '已冻结',
    '2': '已更新',
    '3': '已回收'
  }[status] || (status || '-')
}

function statusTagType(status) {
  if (isRevoked(status)) {
    return 'danger'
  }
  if (status === 'Frozen' || status === '1') {
    return 'info'
  }
  if (status === 'Replaced' || status === '2') {
    return 'warning'
  }
  return 'success'
}

function chainStatusText(status) {
  return { '0': '待上链', '1': '已上链', '2': '失败' }[status] || '-'
}

function chainStatusType(status) {
  return { '0': 'warning', '1': 'success', '2': 'danger' }[status] || 'info'
}

getList()
</script>
