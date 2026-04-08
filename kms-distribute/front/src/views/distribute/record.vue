<template>
  <div class="app-container">
    <el-form :model="queryParams" ref="queryForm" :inline="true" v-show="showSearch" label-width="80px">
      <el-form-item label="用户名" prop="userName">
        <el-input v-model="queryParams.userName" placeholder="请输入用户名" clearable style="width: 200px" @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="密钥名称" prop="keyName">
        <el-input v-model="queryParams.keyName" placeholder="请输入密钥名称" clearable style="width: 200px" @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="分发类型" prop="distributeType">
        <el-select v-model="queryParams.distributeType" placeholder="请选择分发类型" clearable style="width: 150px">
          <el-option label="初始分发" value="1" />
          <el-option label="更新分发" value="2" />
          <el-option label="回收后补发" value="3" />
        </el-select>
      </el-form-item>
      <el-form-item label="分发状态" prop="distributeStatus">
        <el-select v-model="queryParams.distributeStatus" placeholder="请选择分发状态" clearable style="width: 150px">
          <el-option label="待分发" value="0" />
          <el-option label="分发中" value="1" />
          <el-option label="分发成功" value="2" />
          <el-option label="分发失败" value="3" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row :gutter="10" class="mb8">
      <right-toolbar :showSearch.sync="showSearch" @queryTable="getList"></right-toolbar>
    </el-row>

    <el-table v-loading="loading" :data="recordList">
      <el-table-column label="记录ID" align="center" prop="recordId" width="80" />
      <el-table-column label="用户名" align="center" prop="userName" width="120" />
      <el-table-column label="密钥名称" align="center" prop="keyName" width="150" />
      <el-table-column label="加密算法" align="center" prop="encrytName" width="120" />
      <el-table-column label="分发类型" align="center" prop="distributeType" width="100">
        <template #default="scope">
          <el-tag v-if="scope.row.distributeType === '1'" type="success">初始分发</el-tag>
          <el-tag v-else-if="scope.row.distributeType === '2'" type="warning">更新分发</el-tag>
          <el-tag v-else type="info">回收后补发</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="分发状态" align="center" prop="distributeStatus" width="100">
        <template #default="scope">
          <el-tag v-if="scope.row.distributeStatus === '0'" type="info">待分发</el-tag>
          <el-tag v-else-if="scope.row.distributeStatus === '1'" type="primary">分发中</el-tag>
          <el-tag v-else-if="scope.row.distributeStatus === '2'" type="success">成功</el-tag>
          <el-tag v-else type="danger">失败</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="分发时间" align="center" prop="distributeTime" width="180" />
      <el-table-column label="区块链Hash" align="center" prop="chainHash" width="200" show-overflow-tooltip />
      <el-table-column label="备注" align="center" prop="remark" show-overflow-tooltip />
      <el-table-column label="操作" align="center" class-name="small-padding fixed-width" width="120">
        <template #default="scope">
          <el-button link type="primary" @click="handleDetail(scope.row)">详情</el-button>
        </template>
      </el-table-column>
    </el-table>

    <pagination v-show="total > 0" :total="total" v-model:page="queryParams.pageNum" v-model:limit="queryParams.pageSize" @pagination="getList" />

    <!-- 详情弹窗 -->
    <el-dialog title="分发记录详情" v-model="detailVisible" width="600px" append-to-body>
      <el-descriptions :column="2" border v-if="currentRecord">
        <el-descriptions-item label="记录ID">{{ currentRecord.recordId }}</el-descriptions-item>
        <el-descriptions-item label="密钥ID">{{ currentRecord.keyId }}</el-descriptions-item>
        <el-descriptions-item label="用户名">{{ currentRecord.userName }}</el-descriptions-item>
        <el-descriptions-item label="密钥名称">{{ currentRecord.keyName }}</el-descriptions-item>
        <el-descriptions-item label="加密算法">{{ currentRecord.encrytName }}</el-descriptions-item>
        <el-descriptions-item label="分发类型">
          <el-tag v-if="currentRecord.distributeType === '1'" type="success">初始分发</el-tag>
          <el-tag v-else-if="currentRecord.distributeType === '2'" type="warning">更新分发</el-tag>
          <el-tag v-else type="info">回收后补发</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="分发状态">
          <el-tag v-if="currentRecord.distributeStatus === '2'" type="success">分发成功</el-tag>
          <el-tag v-else type="danger">分发失败</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="分发时间">{{ currentRecord.distributeTime }}</el-descriptions-item>
        <el-descriptions-item label="区块链Hash" :span="2">{{ currentRecord.chainHash }}</el-descriptions-item>
        <el-descriptions-item label="区块高度">{{ currentRecord.blockHeight }}</el-descriptions-item>
        <el-descriptions-item label="备注" :span="2">{{ currentRecord.remark }}</el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { listKeyDistributeRecord, getKeyDistributeRecord } from '@/api/distribute/record'

const loading = ref(true)
const showSearch = ref(true)
const total = ref(0)
const recordList = ref([])
const detailVisible = ref(false)
const currentRecord = ref(null)

const queryParams = reactive({
  pageNum: 1,
  pageSize: 10,
  userName: null,
  keyName: null,
  distributeType: null,
  distributeStatus: null
})

function getList() {
  loading.value = true
  listKeyDistributeRecord(queryParams).then(res => {
    recordList.value = res.data || []
    total.value = res.total || 0
    loading.value = false
  })
}

function handleQuery() {
  queryParams.pageNum = 1
  getList()
}

function resetQuery() {
  queryParams.userName = null
  queryParams.keyName = null
  queryParams.distributeType = null
  queryParams.distributeStatus = null
  handleQuery()
}

function handleDetail(row) {
  getKeyDistributeRecord(row.recordId).then(res => {
    currentRecord.value = res.data
    detailVisible.value = true
  })
}

getList()
</script>
