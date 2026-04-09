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
        <el-input v-model="queryParams.encrytName" placeholder="请输入加密算法名称" clearable @keyup.enter="handleQuery" />
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
        <el-button type="primary" plain icon="Plus" @click="handleAdd">新增</el-button>
      </el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
    </el-row>

    <el-table v-loading="loading" :data="keymanageList">
      <el-table-column label="密钥ID" align="center" prop="keyId" />
      <el-table-column label="用户ID" align="center" prop="userId" />
      <el-table-column label="用户名" align="center" prop="userName" />
      <el-table-column label="加密算法类型" align="center" prop="encrytType" min-width="150" />
      <el-table-column label="加密算法名称" align="center" prop="encrytName" width="120" />
      <el-table-column label="密钥名称" align="center" prop="keyName" min-width="160" />
      <el-table-column label="密钥用途" align="center" prop="keyUse" min-width="180" show-overflow-tooltip />
      <el-table-column label="所属域" align="center" prop="keyDomain" width="100" />
      <el-table-column label="更新时间" align="center" prop="updTime" width="160" />
      <el-table-column label="密钥状态" align="center" prop="status" width="100">
        <template #default="scope">
          <el-tag :type="statusTagType(scope.row.status)">{{ statusText(scope.row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="存证状态" align="center" prop="chainStatus" width="100">
        <template #default="scope">
          <el-tag :type="chainStatusTagType(scope.row.chainStatus)">{{ chainStatusText(scope.row.chainStatus) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" align="center" width="220">
        <template #default="scope">
          <el-button v-if="scope.row.chainStatus == '1'" link type="primary" icon="Link" @click="handleViewChain(scope.row)">凭证</el-button>
          <el-button link type="primary" icon="View" @click="handleViewDetails(scope.row)">详情</el-button>
        </template>
      </el-table-column>
    </el-table>

    <pagination v-show="total > 0" :total="total" v-model:page="queryParams.pageNum" v-model:limit="queryParams.pageSize" @pagination="getList" />

    <el-dialog title="新增生成历史" v-model="open" width="640px" append-to-body>
      <el-form ref="historyRef" :model="form" :rules="rules" label-width="110px">
        <el-form-item label="选择用户" prop="userId">
          <el-select v-model="form.userId" placeholder="请选择用户" filterable @change="handleUserChange">
            <el-option v-for="user in userList" :key="user.userId" :label="`${user.userName} (ID: ${user.userId})`" :value="user.userId" />
          </el-select>
        </el-form-item>
        <el-form-item label="加密算法类型" prop="encrytType">
          <el-select v-model="form.encrytType" placeholder="请选择加密算法类型" @change="handleEncrytTypeChange">
            <el-option label="无证书非对称加密" value="无证书非对称加密" />
          </el-select>
        </el-form-item>
        <el-form-item label="加密算法名称" prop="encrytName">
          <el-select v-model="form.encrytName" placeholder="请选择加密算法名称">
            <el-option v-for="option in encrytNameOptions" :key="option.value" :label="option.label" :value="option.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="密钥名称" prop="keyName">
          <el-input v-model="form.keyName" maxlength="64" />
        </el-form-item>
        <el-form-item label="密钥用途" prop="keyUse">
          <el-input v-model="form.keyUse" maxlength="128" />
        </el-form-item>
        <el-form-item label="所属域" prop="keyDomain">
          <el-input v-model="form.keyDomain" maxlength="32" />
        </el-form-item>
        <el-form-item label="密钥状态" prop="status">
          <el-select v-model="form.status" placeholder="请选择密钥状态">
            <el-option label="正常" value="0" />
            <el-option label="冻结" value="1" />
            <el-option label="轮换" value="2" />
            <el-option label="回收" value="3" />
          </el-select>
        </el-form-item>
        <el-form-item label="存证状态" prop="chainStatus">
          <el-select v-model="form.chainStatus" placeholder="请选择存证状态">
            <el-option label="排队中" value="0" />
            <el-option label="已上链" value="1" />
            <el-option label="失败" value="2" />
          </el-select>
        </el-form-item>
        <el-form-item label="交易哈希" prop="chainHash">
          <el-input v-model="form.chainHash" maxlength="128" placeholder="已上链时可填写" />
        </el-form-item>
        <el-form-item label="区块高度" prop="blockHeight">
          <el-input-number v-model="form.blockHeight" :min="1" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="密钥值" prop="keyValue">
          <el-input v-model="form.keyValue" type="textarea" :rows="4" placeholder="可选，不填则自动生成占位历史值" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button type="primary" @click="submitForm">确 定</el-button>
        <el-button @click="cancel">取 消</el-button>
      </template>
    </el-dialog>

    <el-dialog title="密钥详细信息" v-model="detailOpen" width="720px" append-to-body destroy-on-close>
      <div class="detail-container">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="密钥ID"><el-tag type="info">{{ detailInfo.keyId }}</el-tag></el-descriptions-item>
          <el-descriptions-item label="密钥名称">{{ detailInfo.keyName }}</el-descriptions-item>
          <el-descriptions-item label="用户ID">{{ detailInfo.userId }}</el-descriptions-item>
          <el-descriptions-item label="用户名">{{ detailInfo.userName }}</el-descriptions-item>
          <el-descriptions-item label="算法类型">{{ detailInfo.encrytType }}</el-descriptions-item>
          <el-descriptions-item label="算法名称">{{ detailInfo.encrytName }}</el-descriptions-item>
          <el-descriptions-item label="密钥用途">{{ detailInfo.keyUse }}</el-descriptions-item>
          <el-descriptions-item label="所属域">{{ detailInfo.keyDomain || '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ detailInfo.creTime }}</el-descriptions-item>
          <el-descriptions-item label="更新时间">{{ detailInfo.updTime }}</el-descriptions-item>
        </el-descriptions>
        <div class="key-content-box">
          <div class="key-item">
            <span class="key-label">密钥值:</span>
            <div class="key-value-block">{{ detailInfo.keyValue || '无数据' }}</div>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button type="primary" @click="detailOpen = false">关 闭</el-button>
      </template>
    </el-dialog>

    <el-dialog title="区块链存证详情" v-model="chainOpen" width="600px" append-to-body>
      <el-descriptions :column="1" border>
        <el-descriptions-item label="交易哈希 (TxHash)">
          <span style="word-break: break-all;">{{ chainData.chainHash || '-' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="区块高度 (Block)"><el-tag effect="dark">{{ chainData.blockHeight || '-' }}</el-tag></el-descriptions-item>
        <el-descriptions-item label="最新版本 (Version)"><el-tag type="info">v{{ chainData.version || 1 }}</el-tag></el-descriptions-item>
        <el-descriptions-item label="上链时间">{{ chainData.updTime || '刚刚' }}</el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button type="primary" @click="chainOpen = false">关 闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="KeyGenerateHistory">
import { addHistoryRecord, listKeymanage } from '@/api/generate/keymanage'
import { listNonAdminUsers } from '@/api/system/user'

const { proxy } = getCurrentInstance()
const keymanageList = ref([])
const userList = ref([])
const encrytNameOptions = ref([])
const open = ref(false)
const loading = ref(true)
const showSearch = ref(true)
const total = ref(0)
const detailOpen = ref(false)
const detailInfo = ref({})
const chainOpen = ref(false)
const chainData = ref({})

const data = reactive({
  queryParams: {
    pageNum: 1,
    pageSize: 10,
    userId: null,
    userName: null,
    encrytType: null,
    encrytName: null,
    keyName: null
  },
  form: {
    userId: null,
    userName: null,
    encrytType: '无证书非对称加密',
    encrytName: null,
    keyName: null,
    keyUse: null,
    keyDomain: 'A',
    status: '0',
    chainStatus: '0',
    chainHash: null,
    blockHeight: null,
    keyValue: null
  },
  rules: {
    userId: [{ required: true, message: '请选择用户', trigger: 'change' }],
    encrytType: [{ required: true, message: '请选择加密算法类型', trigger: 'change' }],
    encrytName: [{ required: true, message: '请选择加密算法名称', trigger: 'change' }],
    keyName: [{ required: true, message: '请输入密钥名称', trigger: 'blur' }],
    keyUse: [{ required: true, message: '请输入密钥用途', trigger: 'blur' }]
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

function handleQuery() {
  queryParams.value.pageNum = 1
  getList()
}

function resetQuery() {
  proxy.resetForm('queryRef')
  handleQuery()
}

function reset() {
  form.value = {
    userId: null,
    userName: null,
    encrytType: '无证书非对称加密',
    encrytName: null,
    keyName: null,
    keyUse: null,
    keyDomain: 'A',
    status: '0',
    chainStatus: '0',
    chainHash: null,
    blockHeight: null,
    keyValue: null
  }
  handleEncrytTypeChange(form.value.encrytType)
  proxy.resetForm('historyRef')
}

function handleAdd() {
  reset()
  listNonAdminUsers().then(response => {
    userList.value = response.data || []
    open.value = true
  })
}

function cancel() {
  open.value = false
  reset()
}

function handleUserChange(userId) {
  const matched = userList.value.find(item => item.userId === userId)
  form.value.userName = matched?.userName || null
}

function handleEncrytTypeChange(value) {
  if (value === '无证书非对称加密') {
    encrytNameOptions.value = [
      { label: 'SM2', value: 'SM2' },
      { label: 'SSCL', value: 'SSCL' }
    ]
  } else {
    encrytNameOptions.value = []
  }
  form.value.encrytName = null
}

function submitForm() {
  proxy.$refs.historyRef.validate(valid => {
    if (!valid) {
      return
    }

    const payload = {
      ...form.value,
      keyName: normalizeText(form.value.keyName),
      keyUse: normalizeText(form.value.keyUse),
      keyDomain: normalizeText(form.value.keyDomain) || 'A',
      chainHash: normalizeText(form.value.chainHash),
      keyValue: normalizeText(form.value.keyValue)
    }

    addHistoryRecord(payload).then(() => {
      proxy.$modal.msgSuccess('生成历史新增成功')
      open.value = false
      getList()
    })
  })
}

function handleViewDetails(row) {
  detailInfo.value = row
  detailOpen.value = true
}

function handleViewChain(row) {
  chainData.value = row
  chainOpen.value = true
}

function normalizeText(value) {
  const text = value == null ? '' : String(value).trim()
  return text === '' ? null : text
}

function statusText(status) {
  return { '0': '正常', '1': '冻结', '2': '轮换', '3': '回收' }[String(status)] || (status ?? '未知')
}

function statusTagType(status) {
  return { '0': 'success', '1': 'warning', '2': 'info', '3': 'danger' }[String(status)] || 'info'
}

function chainStatusText(status) {
  return { '0': '排队中', '1': '已上链', '2': '失败' }[String(status)] || (status ?? '未知')
}

function chainStatusTagType(status) {
  return { '0': 'info', '1': 'success', '2': 'danger' }[String(status)] || 'info'
}

reset()
getList()
</script>

<style scoped>
.detail-container { padding: 0 10px }
.key-content-box { background-color: #f8f9fa; border-radius: 4px; padding: 15px; margin-top: 10px; border: 1px solid #ebeef5 }
.key-item { margin-bottom: 15px }
.key-label { display: block; font-weight: bold; color: #606266; margin-bottom: 5px; font-size: 14px }
.key-value-block { background-color: #282c34; color: #abb2bf; padding: 10px; border-radius: 4px; font-family: Consolas, Monaco, monospace; font-size: 13px; word-break: break-all; white-space: pre-wrap }
</style>
