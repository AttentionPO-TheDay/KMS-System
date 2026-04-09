<template>
  <div class="app-container">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="68px">
      <el-form-item label="用户账号" prop="userName">
        <el-input v-model="queryParams.userName" placeholder="请输入用户账号" clearable @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-table v-loading="loading" :data="filteredUsers">
      <el-table-column label="用户ID" align="center" prop="userId" width="100" />
      <el-table-column label="用户账号" align="center" prop="userName" min-width="160" />
      <el-table-column label="用户等级" align="center" prop="roleLevel" width="120">
        <template #default="scope">
          <el-tag :type="roleTagType(scope.row.roleLevel)">{{ roleText(scope.row.roleLevel) }}</el-tag>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup name="BusinessUsers">
import { listBusinessUsers } from '@/api/query/keyQuery'

const { proxy } = getCurrentInstance()
const loading = ref(true)
const showSearch = ref(true)
const users = ref([])
const queryParams = ref({ userName: '' })

const filteredUsers = computed(() => {
  const keyword = (queryParams.value.userName || '').trim().toLowerCase()
  if (!keyword) {
    return users.value
  }
  return users.value.filter(item => (item.userName || '').toLowerCase().includes(keyword))
})

function getList() {
  loading.value = true
  listBusinessUsers().then(list => {
    users.value = list
    loading.value = false
  }).catch(() => {
    loading.value = false
  })
}

function handleQuery() {}

function resetQuery() {
  proxy.resetForm('queryRef')
}

function roleText(roleLevel) {
  return ({ 0: '管理员', 1: '中级用户', 2: '普通用户' })[roleLevel] || '普通用户'
}

function roleTagType(roleLevel) {
  return ({ 0: 'danger', 1: 'warning', 2: 'info' })[roleLevel] || 'info'
}

getList()
</script>
