<template>
  <div class="app-container">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="68px">
      <el-form-item label="用户ID" prop="userId">
        <el-input v-model="queryParams.userId" placeholder="请输入用户ID" clearable @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="用户名" prop="userName">
        <el-input v-model="queryParams.userName" placeholder="请输入用户名" clearable @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="加密算法名称" prop="encrytName">
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
        <el-button type="primary" plain icon="Plus" @click="handleAdd" v-hasPermi="['keymanage:keymanage:add']">新增</el-button>
      </el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
    </el-row>

    <el-table v-loading="loading" :data="keymanageList" @selection-change="handleSelectionChange">
      <el-table-column type="selection" width="55" align="center" />
      <el-table-column label="密钥ID" align="center" prop="keyId" />
      <el-table-column label="用户ID" align="center" prop="userId" />
      <el-table-column label="用户名" align="center" prop="userName" />
      <el-table-column label="加密算法类型" align="center" prop="encrytType" />
      <el-table-column label="加密算法名称" align="center" prop="encrytName" />
      <el-table-column label="密钥名称" align="center" prop="keyName" />
      <el-table-column label="密钥用途" align="center" prop="keyUse" />
      <el-table-column label="更新时间" align="center" prop="updTime" width="160" />
      <el-table-column label="密钥状态" align="center" prop="status" width="100">
        <template #default="scope">
          <el-tag v-if="scope.row.status == '0'" type="success">正常</el-tag>
          <el-tag v-else-if="scope.row.status == '1'" type="warning">冻结</el-tag>
          <el-tag v-else-if="scope.row.status == '2'" type="info">轮换</el-tag>
          <el-tag v-else-if="scope.row.status == '3'" type="danger">回收</el-tag>
          <el-tag v-else>{{ scope.row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="存证状态" align="center" prop="chainStatus" width="100">
        <template #default="scope">
          <el-tag v-if="scope.row.chainStatus == '1'" type="success" effect="dark">已上链</el-tag>
          <el-tag v-else-if="scope.row.chainStatus == '2'" type="danger" effect="dark">失败</el-tag>
          <el-tag v-else type="info" effect="plain">排队中</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" align="center" class-name="small-padding fixed-width" width="220">
        <template #default="scope">
          <el-button v-if="scope.row.chainStatus == '1'" link type="primary" icon="Link" @click="handleViewChain(scope.row)">凭证</el-button>
          <el-button link type="primary" icon="View" @click="handleViewDetails(scope.row)">详情</el-button>
        </template>
      </el-table-column>
    </el-table>

    <pagination v-show="total>0" :total="total" v-model:page="queryParams.pageNum" v-model:limit="queryParams.pageSize" @pagination="getList" />

    <el-dialog title="密钥详细信息" v-model="detailOpen" width="700px" append-to-body destroy-on-close>
      <div class="detail-container">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="密钥ID"><el-tag type="info">{{ detailInfo.keyId }}</el-tag></el-descriptions-item>
          <el-descriptions-item label="密钥名称">{{ detailInfo.keyName }}</el-descriptions-item>
          <el-descriptions-item label="用户ID">{{ detailInfo.userId }}</el-descriptions-item>
          <el-descriptions-item label="加密类型"><el-tag effect="dark">{{ detailInfo.encrytName }}</el-tag></el-descriptions-item>
          <el-descriptions-item label="密钥用途">{{ detailInfo.keyUse }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ detailInfo.creTime }}</el-descriptions-item>
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
          <span style="word-break: break-all;">{{ chainData.chainHash }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="区块高度 (Block)"><el-tag effect="dark">{{ chainData.blockHeight }}</el-tag></el-descriptions-item>
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
import { listKeymanage } from "@/api/generate/keymanage"

const { proxy } = getCurrentInstance()
const keymanageList = ref([])
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
    pageNum: 1, pageSize: 10, userId: null, userName: null, encrytType: null,
    encrytName: null, keyName: null, keyUse: null, keyValue: null,
    creTime: null, updTime: null, autoUpdate: null, status: null
  }
})

const { queryParams } = toRefs(data)

function getList() {
  loading.value = true
  listKeymanage(queryParams.value).then(response => {
    keymanageList.value = response.rows
    total.value = response.total
    loading.value = false
  })
}

function handleQuery() { queryParams.value.pageNum = 1; getList() }
function resetQuery() { proxy.resetForm("queryRef"); handleQuery() }
function handleSelectionChange(selection) {}

function handleAdd() { open.value = true }

function handleViewDetails(row) {
  detailInfo.value = row
  detailOpen.value = true
}

function handleViewChain(row) {
  chainData.value = row
  chainOpen.value = true
}

getList()
</script>

<style scoped>
.detail-container { padding: 0 10px }
.key-content-box { background-color: #f8f9fa; border-radius: 4px; padding: 15px; margin-top: 10px; border: 1px solid #ebeef5 }
.key-item { margin-bottom: 15px }
.key-label { display: block; font-weight: bold; color: #606266; margin-bottom: 5px; font-size: 14px }
.key-value-block { background-color: #282c34; color: #abb2bf; padding: 10px; border-radius: 4px; font-family: Consolas, Monaco, monospace; font-size: 13px; word-break: break-all; white-space: pre-wrap }
</style>
