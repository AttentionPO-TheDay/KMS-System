<template>
  <div class="app-container">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="68px">
      <el-form-item label="用户ID" prop="userId">
        <el-input v-model="queryParams.userId" placeholder="请输入用户ID" clearable @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="用户名" prop="userName">
        <el-input v-model="queryParams.userName" placeholder="请输入用户名" clearable @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="密钥名称" prop="keyName">
        <el-input v-model="queryParams.keyName" placeholder="请输入密钥名称" clearable @keyup.enter="handleQuery" />
      </el-form-item>
        <el-form-item label="状态" prop="status">
          <el-select v-model="queryParams.status" placeholder="请选择状态" clearable style="width: 140px">
          <el-option label="有效" value="0" />
          <el-option label="已冻结" value="1" />
          <el-option label="已更新" value="2" />
          <el-option label="已回收" value="3" />
          </el-select>
        </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button
          type="danger"
          plain
           icon="Delete"
          :disabled="multiple"
          @click="handleDelete()"
          v-hasPermi="['lifecycle:keymanage:remove']"
          style="padding: 6px 12px; margin-top: 15px"
        >密钥回收</el-button>
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
      <el-table-column label="版本" align="center" prop="version" width="80" />
      <el-table-column label="状态" align="center" width="100">
        <template #default="scope">
          <el-tag :type="statusTagType(scope.row.status)">{{ statusText(scope.row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="更新时间" align="center" prop="updTime" width="170" />
      <el-table-column label="操作" align="center" width="120">
        <template #default="scope">
          <el-button
            link
            type="danger"
            icon="Delete"
            :disabled="isRevoked(scope.row.status)"
            @click="handleDelete(scope.row)"
            v-hasPermi="['lifecycle:keymanage:remove']"
          >回收</el-button>
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
  </div>
</template>

<script setup name="KeyDelete">
import { listKeymanage, delKeymanage } from "@/api/lifecycle/lifecycle"

const { proxy } = getCurrentInstance()

const keymanageList = ref([])
const loading = ref(true)
const showSearch = ref(true)
const ids = ref([])
const multiple = ref(true)
const total = ref(0)

const queryParams = ref({
  pageNum: 1,
  pageSize: 10,
  userId: null,
  userName: null,
  keyName: null,
  status: null
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
  multiple.value = !selection.length
}

function handleDelete(row) {
  const keyIds = row?.keyId ? [row.keyId] : ids.value
  if (!keyIds.length) {
    proxy.$modal.msgWarning("请先选择需要回收的密钥")
    return
  }
  const revokedIds = keyIds.filter(keyId => {
    const current = keymanageList.value.find(item => item.keyId === keyId)
    return current && isRevoked(current.status)
  })
  if (revokedIds.length) {
    proxy.$modal.msgWarning(`密钥 ${revokedIds.join(', ')} 已回收，无需重复操作`)
    return
  }
    proxy.$modal.confirm(`是否确认回收密钥编号为 "${keyIds.join(', ')}" 的记录？`).then(async () => {
      for (const keyId of keyIds) {
        await delKeymanage(keyId)
      }
      proxy.$modal.msgSuccess("回收成功，结果已推送到用户端")
      getList()
    }).catch(() => {})
}

function isRevoked(status) {
  return status === '3' || status === 'Revoked' || status === 'REVOKED'
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

getList()
</script>
