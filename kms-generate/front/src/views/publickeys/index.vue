<template>
  <div class="app-container">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="68px">
      <el-form-item label="用户名" prop="userName">
        <el-input v-model="queryParams.userName" placeholder="请输入用户名" clearable @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-table v-loading="loading" :data="publicKeysList">
      <el-table-column label="密钥ID" align="center" prop="keyId" width="80" />
      <el-table-column label="用户名" align="center" prop="userName" width="120" />
      <el-table-column label="加密类型" align="center" prop="encrytType" width="120" />
      <el-table-column label="加密算法" align="center" prop="encrytName" width="120" />
      <el-table-column label="密钥名称" align="center" prop="keyName" width="150" />
      <el-table-column label="公钥值" align="center" prop="keyValue" :show-overflow-tooltip="true" min-width="200" />
      <el-table-column label="创建时间" align="center" prop="creTime" width="160" />
    </el-table>

    <pagination v-show="total>0" :total="total" v-model:page="queryParams.pageNum" v-model:limit="queryParams.pageSize" @pagination="getList" />
  </div>
</template>

<script setup name="PublicKeys">
import { listPublicKeys } from "@/api/generate/keymanage"

const { proxy } = getCurrentInstance()
const publicKeysList = ref([])
const loading = ref(true)
const showSearch = ref(true)
const total = ref(0)

const data = reactive({
  queryParams: { pageNum: 1, pageSize: 10, userName: null }
})

const { queryParams } = toRefs(data)

function getList() {
  loading.value = true
  listPublicKeys(queryParams.value).then(response => {
    publicKeysList.value = response.rows
    total.value = response.total
    loading.value = false
  })
}

function handleQuery() { queryParams.value.pageNum = 1; getList() }
function resetQuery() { proxy.resetForm("queryRef"); handleQuery() }

getList()
</script>
