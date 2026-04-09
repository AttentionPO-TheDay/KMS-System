<template>
  <div class="app-container">
    <el-alert v-if="pageMode === 'mine'" title="当前页面默认聚焦当前登录用户的密钥记录，用于统一查看个人密钥。" type="info" :closable="false" class="mb16" />
    <el-alert v-else-if="pageMode === 'chain'" title="当前页面聚焦链上状态与凭证查看，适合作为统一的区块链查看入口。" type="success" :closable="false" class="mb16" />

    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="68px">
      <el-form-item label="用户名" prop="userName">
        <el-input v-model="queryParams.userName" placeholder="请输入用户名" clearable @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="算法" prop="encrytName">
        <el-input v-model="queryParams.encrytName" placeholder="请输入算法名称" clearable @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="密钥名称" prop="keyName">
        <el-input v-model="queryParams.keyName" placeholder="请输入密钥名称" clearable @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="用途" prop="keyUse">
        <el-input v-model="queryParams.keyUse" placeholder="请输入密钥用途" clearable @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-table v-loading="loading" :data="keyList">
      <el-table-column label="密钥ID" align="center" prop="keyId" width="90" />
      <el-table-column label="用户名" align="center" prop="userName" width="120" />
      <el-table-column label="加密类型" align="center" prop="encrytType" width="140" />
      <el-table-column label="算法" align="center" prop="encrytName" width="120" />
      <el-table-column label="密钥名称" align="center" prop="keyName" min-width="150" />
      <el-table-column v-if="pageMode !== 'chain'" label="用途" align="center" prop="keyUse" min-width="140" />
      <el-table-column label="更新时间" align="center" prop="updTime" width="170">
        <template #default="scope">
          <span>{{ parseTime(scope.row.updTime || scope.row.creTime) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="工作状态" align="center" prop="status" width="110">
        <template #default="scope">
          <el-tag :type="statusType(scope.row.status)">{{ statusText(scope.row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="链上状态" align="center" prop="chainStatus" width="110">
        <template #default="scope">
          <el-tag :type="chainType(scope.row.chainStatus)">{{ chainText(scope.row.chainStatus) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" align="center" width="170">
        <template #default="scope">
          <el-button link type="info" @click="handleViewEvidence(scope.row)">存证详情</el-button>
          <el-button link type="primary" @click="handleViewChain(scope.row)">链上凭证</el-button>
        </template>
      </el-table-column>
    </el-table>

    <pagination v-show="total > 0" :total="total" v-model:page="queryParams.pageNum" v-model:limit="queryParams.pageSize" @pagination="getList" />

    <el-dialog title="存证详情" v-model="evidenceOpen" width="720px" append-to-body>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="密钥ID">{{ evidenceData.keyId || '-' }}</el-descriptions-item>
        <el-descriptions-item label="用户名">{{ evidenceData.userName || '-' }}</el-descriptions-item>
        <el-descriptions-item label="算法类型">{{ evidenceData.encrytType || '-' }}</el-descriptions-item>
        <el-descriptions-item label="算法名称">{{ evidenceData.encrytName || '-' }}</el-descriptions-item>
        <el-descriptions-item label="密钥名称">{{ evidenceData.keyName || '-' }}</el-descriptions-item>
        <el-descriptions-item label="密钥用途">{{ evidenceData.keyUse || '-' }}</el-descriptions-item>
        <el-descriptions-item label="工作状态">
          <el-tag :type="statusType(evidenceData.status)">{{ statusText(evidenceData.status) }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="存证状态">
          <el-tag :type="chainType(evidenceData.chainStatus)">{{ chainText(evidenceData.chainStatus) }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="上链版本">v{{ evidenceData.version || 1 }}</el-descriptions-item>
        <el-descriptions-item label="区块高度">{{ evidenceData.blockHeight || '-' }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ evidenceData.creTime || '-' }}</el-descriptions-item>
        <el-descriptions-item label="更新时间">{{ evidenceData.updTime || '-' }}</el-descriptions-item>
        <el-descriptions-item label="交易哈希" :span="2">
          <div class="hash-row">
            <span class="hash-text">{{ evidenceData.chainHash || '-' }}</span>
            <el-button
              v-if="evidenceData.chainHash"
              link
              type="primary"
              @click="copyChainHash(evidenceData.chainHash)"
            >复制</el-button>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="存证说明" :span="2">
          <el-alert
            title="该记录已纳入公共查询总表的存证详情视图，可直接查看业务字段与链上凭证的对应关系。"
            type="success"
            :closable="false"
            show-icon
          />
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="evidenceOpen = false">关 闭</el-button>
      </template>
    </el-dialog>

    <el-dialog title="链上凭证" v-model="chainOpen" width="620px" append-to-body>
      <el-descriptions :column="1" border>
        <el-descriptions-item label="交易哈希">
          <span style="word-break: break-all;">{{ chainData.chainHash || '-' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="区块高度">{{ chainData.blockHeight || '-' }}</el-descriptions-item>
        <el-descriptions-item label="上链版本">v{{ chainData.version || 1 }}</el-descriptions-item>
        <el-descriptions-item label="上链状态">{{ chainText(chainData.chainStatus) }}</el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="chainOpen = false">关 闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="QueryKeyList">
import { listQueryKeys, getKeyChainStatus } from '@/api/query/keyQuery'
import useUserStore from '@/store/modules/user'

const route = useRoute()
const { proxy } = getCurrentInstance()
const userStore = useUserStore()

const loading = ref(true)
const showSearch = ref(true)
const total = ref(0)
const keyList = ref([])
const chainOpen = ref(false)
const chainData = ref({})
const evidenceOpen = ref(false)
const evidenceData = ref({})

const pageMode = computed(() => {
  if (route.name === 'BlockchainView') return 'chain'
  if (route.name === 'UserKeysPage') return 'mine'
  return 'query'
})

const queryParams = ref({
  pageNum: 1,
  pageSize: 10,
  userName: '',
  encrytName: '',
  keyName: '',
  keyUse: ''
})

function getList() {
  loading.value = true
  listQueryKeys(queryParams.value).then(response => {
    keyList.value = response.rows || []
    total.value = response.total || 0
    loading.value = false
  }).catch(() => {
    loading.value = false
  })
}

function handleQuery() {
  queryParams.value.pageNum = 1
  getList()
}

function resetQuery() {
  proxy.resetForm('queryRef')
  if (pageMode.value === 'mine') {
    queryParams.value.userName = userStore.name || ''
  }
  handleQuery()
}

function handleViewChain(row) {
  getKeyChainStatus(row.keyId).then(data => {
    chainData.value = { ...data, chainStatus: row.chainStatus }
    chainOpen.value = true
  })
}

function handleViewEvidence(row) {
  getKeyChainStatus(row.keyId).then(data => {
    evidenceData.value = {
      ...row,
      ...data,
      chainStatus: row.chainStatus,
      version: data?.version ?? row.version,
      blockHeight: data?.blockHeight ?? row.blockHeight,
      chainHash: data?.chainHash ?? row.chainHash
    }
    evidenceOpen.value = true
  })
}

function copyChainHash(value) {
  navigator.clipboard.writeText(value).then(() => {
    proxy.$modal.msgSuccess('交易哈希已复制')
  }).catch(() => {
    proxy.$modal.msgError('复制失败，请手动复制')
  })
}

function statusText(status) {
  return ({ '0': '正常', '1': '冻结', '2': '轮换', '3': '回收' })[status] || (status || '-')
}

function statusType(status) {
  return ({ '0': 'success', '1': 'warning', '2': 'info', '3': 'danger' })[status] || 'info'
}

function chainText(status) {
  return ({ '1': '已上链', '2': '失败' })[status] || '排队中'
}

function chainType(status) {
  return ({ '1': 'success', '2': 'danger' })[status] || 'info'
}

if (pageMode.value === 'mine') {
  queryParams.value.userName = userStore.name || ''
}

getList()
</script>

<style scoped>
.mb16 {
  margin-bottom: 16px;
}

.hash-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.hash-text {
  word-break: break-all;
}
</style>
