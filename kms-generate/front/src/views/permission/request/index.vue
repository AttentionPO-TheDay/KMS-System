<template>
  <div class="app-container">
    <el-card shadow="never">
      <template #header>
        <div class="header-row">
          <span>生成域权限审批</span>
          <el-button type="primary" link @click="getList">刷新</el-button>
        </div>
      </template>

      <el-table v-loading="loading" :data="requestList">
        <el-table-column label="申请 ID" prop="requestId" width="90" />
        <el-table-column label="用户" prop="userName" width="140" />
        <el-table-column label="功能" prop="featureName" min-width="180" />
        <el-table-column label="当前等级" prop="originalLevel" width="110">
          <template #default="scope">{{ levelText(scope.row.originalLevel) }}</template>
        </el-table-column>
        <el-table-column label="申请等级" prop="requestLevel" width="110">
          <template #default="scope">{{ levelText(scope.row.requestLevel) }}</template>
        </el-table-column>
        <el-table-column label="申请理由" prop="requestReason" min-width="240" show-overflow-tooltip />
        <el-table-column label="状态" prop="status" width="100">
          <template #default="scope">
            <el-tag :type="statusType(scope.row.status)">{{ statusText(scope.row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="审批人" prop="approveBy" width="120" />
        <el-table-column label="操作" width="180">
          <template #default="scope">
            <el-button v-if="scope.row.status === '0'" link type="primary" @click="openDialog(scope.row, 'approve')">通过</el-button>
            <el-button v-if="scope.row.status === '0'" link type="danger" @click="openDialog(scope.row, 'reject')">拒绝</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogOpen" :title="dialogMode === 'approve' ? '审批通过' : '审批拒绝'" width="520px">
      <el-form label-width="90px">
        <el-form-item label="申请用户">
          <el-input :model-value="currentRow.userName" disabled />
        </el-form-item>
        <el-form-item label="申请功能">
          <el-input :model-value="currentRow.featureName" disabled />
        </el-form-item>
        <el-form-item label="审批备注">
          <el-input v-model="approveNote" type="textarea" :rows="4" placeholder="请输入审批备注" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogOpen = false">取消</el-button>
        <el-button :type="dialogMode === 'approve' ? 'primary' : 'danger'" @click="submitDialog">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { approveRequest, listPermissionRequests, rejectRequest } from '@/api/permission/permission'

const loading = ref(false)
const requestList = ref([])
const dialogOpen = ref(false)
const dialogMode = ref('approve')
const approveNote = ref('')
const currentRow = reactive({})

onMounted(() => {
  getList()
})

function getList() {
  loading.value = true
  listPermissionRequests().then(response => {
    requestList.value = response.rows
  }).catch(error => {
    ElMessage.error(error.message || '加载失败')
  }).finally(() => {
    loading.value = false
  })
}

function openDialog(row, mode) {
  Object.assign(currentRow, row)
  dialogMode.value = mode
  approveNote.value = ''
  dialogOpen.value = true
}

function submitDialog() {
  const payload = {
    approveBy: 'generate-admin',
    approveNote: approveNote.value
  }
  const action = dialogMode.value === 'approve'
    ? approveRequest(currentRow.requestId, payload)
    : rejectRequest(currentRow.requestId, payload)

  action.then(() => {
    ElMessage.success(dialogMode.value === 'approve' ? '审批通过成功' : '审批拒绝成功')
    dialogOpen.value = false
    getList()
  }).catch(error => {
    ElMessage.error(error.message || '审批失败')
  })
}

function levelText(level) {
  return { 0: '管理员', 1: '中级用户', 2: '普通用户' }[level] || '未知'
}

function statusText(status) {
  return { 0: '待审批', 1: '已通过', 2: '已拒绝', 3: '已回退' }[status] || '未知'
}

function statusType(status) {
  return { 0: 'warning', 1: 'success', 2: 'danger', 3: 'info' }[status] || 'info'
}
</script>

<style scoped>
.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
</style>
