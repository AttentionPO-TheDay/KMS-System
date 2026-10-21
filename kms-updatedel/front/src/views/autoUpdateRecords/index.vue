<template>
  <div class="app-container">
    <!-- 口径说明：这一页回答的是「任务跑了没有、成功几条、失败几条、为什么」。
         必须把三项口径写在页面上，否则数字会被读成另一种意思：
         · 成功/失败 = 提交轮换的结果，不是"已上链"；
         · 「送达/确认」列 = 该密钥最近一条自动更新流水，不保证属于本轮的 run；
         · 跳过 = 开着开关、还没到间隔窗口的密钥数（不是错误）。 -->
    <h2>自动更新任务记录</h2>

    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="88px">
      <el-form-item label="触发方式" prop="triggerSource">
        <el-select v-model="queryParams.triggerSource" placeholder="全部" clearable style="width: 140px">
          <el-option label="定时" value="SCHEDULED" />
          <el-option label="手动补跑" value="MANUAL" />
        </el-select>
      </el-form-item>
      <el-form-item label="轮次ID" prop="runId">
        <el-input v-model="queryParams.runId" placeholder="完整 runId" clearable style="width: 260px" @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row :gutter="10" class="mb8">
      <el-col :span="3">
        <el-button
          type="primary"
          plain
          icon="VideoPlay"
          :loading="triggering"
          @click="handleRunOnce"
        >手动触发一轮</el-button>
      </el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList" />
    </el-row>

    <el-table v-loading="loading" :data="runList">
      <el-table-column label="轮次ID" align="center" width="150">
        <template #default="scope">
          <el-tooltip :content="scope.row.runId" placement="top">
            <span class="aur-mono">{{ shortRunId(scope.row.runId) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="触发方式" align="center" width="100">
        <template #default="scope">
          <el-tag :type="scope.row.triggerSource === 'MANUAL' ? 'warning' : 'info'" size="small">
            {{ scope.row.triggerSource === 'MANUAL' ? '手动补跑' : '定时' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="开始时间" align="center" prop="startedAt" width="170" />
      <el-table-column label="结束时间" align="center" width="180">
        <template #default="scope">
          <el-tag v-if="!scope.row.finishedAt" type="danger" size="small">未完成（进程中断）</el-tag>
          <span v-else>{{ scope.row.finishedAt }}</span>
        </template>
      </el-table-column>
      <el-table-column label="候选" align="center" prop="candidateCount" width="70" />
      <el-table-column label="轮换成功" align="center" width="90">
        <template #default="scope">
          <span :class="{ 'aur-ok': scope.row.successCount > 0 }">{{ scope.row.successCount }}</span>
        </template>
      </el-table-column>
      <el-table-column label="轮换失败" align="center" width="90">
        <template #default="scope">
          <span :class="{ 'aur-fail': scope.row.failCount > 0 }">{{ scope.row.failCount }}</span>
        </template>
      </el-table-column>
      <el-table-column label="跳过（未到期）" align="center" width="130">
        <template #default="scope">
          <span>{{ scope.row.skippedCount }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" align="center" width="100" fixed="right">
        <template #default="scope">
          <el-button link type="primary" icon="View" @click="openDetail(scope.row)">明细</el-button>
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

    <el-drawer v-model="detail.open" size="70%" :title="detailTitle" append-to-body>
      <div class="aur-detail-head">
        <el-tag size="small" type="info">轮次 {{ shortRunId(detail.run?.runId) }}</el-tag>
        <span v-if="detail.run">
          候选 {{ detail.run.candidateCount }} · 成功 {{ detail.run.successCount }} ·
          失败 {{ detail.run.failCount }} · 跳过 {{ detail.run.skippedCount }}
        </span>
      </div>

      <el-form :model="detail.query" inline label-width="70px">
        <el-form-item label="结果">
          <el-select v-model="detail.query.result" placeholder="全部" clearable style="width: 120px">
            <el-option label="成功" value="SUCCESS" />
            <el-option label="失败" value="FAILED" />
          </el-select>
        </el-form-item>
        <el-form-item label="密钥ID">
          <el-input v-model="detail.query.keyId" placeholder="密钥ID" clearable style="width: 140px" @keyup.enter="loadItems" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" icon="Search" @click="loadItems">查询</el-button>
        </el-form-item>
      </el-form>

      <el-table v-loading="detail.loading" :data="detail.items" size="small" border>
        <el-table-column label="密钥ID" align="center" prop="keyId" width="90" />
        <el-table-column label="密钥名称" align="center" prop="keyName" min-width="130" show-overflow-tooltip />
        <el-table-column label="算法" align="center" prop="encrytName" width="100" />
        <el-table-column label="结果" align="center" width="90">
          <template #default="scope">
            <el-tag :type="scope.row.result === 'SUCCESS' ? 'success' : 'danger'" size="small">
              {{ scope.row.result === 'SUCCESS' ? '成功' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="版本" align="center" width="100">
          <template #default="scope">
            <span v-if="scope.row.result === 'SUCCESS'">v{{ scope.row.fromVersion }} → v{{ scope.row.toVersion }}</span>
            <span v-else class="aur-muted">v{{ scope.row.fromVersion }}（未变）</span>
          </template>
        </el-table-column>
        <el-table-column label="失败原因" align="center" min-width="220" show-overflow-tooltip>
          <template #default="scope">
            <span v-if="scope.row.reason" class="aur-fail">{{ scope.row.reason }}</span>
            <span v-else class="aur-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="最近送达/确认" align="center" width="130">
          <template #default="scope">
            <el-tag v-if="scope.row.chainResultStatus === '1'" type="success" size="small">已成功</el-tag>
            <el-tag v-else-if="scope.row.chainResultStatus === '2'" type="danger" size="small">失败</el-tag>
            <el-tag v-else-if="scope.row.chainResultStatus === '0'" type="warning" size="small">处理中</el-tag>
            <span v-else class="aur-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="交易哈希" align="center" min-width="150" show-overflow-tooltip>
          <template #default="scope">
            <span class="aur-mono">{{ scope.row.chainHash || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="执行时间" align="center" prop="updatedAt" width="160" />
      </el-table>

      <pagination
        v-show="detail.total > 0"
        :total="detail.total"
        v-model:page="detail.query.pageNum"
        v-model:limit="detail.query.pageSize"
        @pagination="loadItems"
      />

      <el-alert
        v-if="!detail.loading && detail.items.length === 0"
        type="info"
        :closable="false"
        show-icon
        title="本轮没有逐密钥明细"
      />
    </el-drawer>
  </div>
</template>

<script setup name="AutoUpdateRecords">
import {
  listAutoUpdateRuns,
  listAutoUpdateRunItems,
  triggerAutoUpdateRunOnce
} from "@/api/lifecycle/lifecycle"

const { proxy } = getCurrentInstance()

const loading = ref(true)
const triggering = ref(false)
const showSearch = ref(true)
const runList = ref([])
const total = ref(0)

const queryParams = ref({
  pageNum: 1,
  pageSize: 10,
  triggerSource: null,
  runId: null
})

const detail = ref({
  open: false,
  loading: false,
  run: null,
  items: [],
  total: 0,
  query: { pageNum: 1, pageSize: 20, result: null, keyId: null }
})

const detailTitle = computed(() => {
  const run = detail.value.run
  return run ? `执行明细 · ${shortRunId(run.runId)}` : '执行明细'
})

function shortRunId(runId) {
  if (!runId) return '-'
  return runId.length > 12 ? runId.slice(0, 8) + '…' + runId.slice(-3) : runId
}

function getList() {
  loading.value = true
  listAutoUpdateRuns(queryParams.value).then(response => {
    runList.value = response.rows || []
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

function handleRunOnce() {
  proxy.$modal.confirm('将立即扫描并轮换到期的自动更新密钥（与定时任务是同一段逻辑）。确定执行一轮？').then(() => {
    triggering.value = true
    return triggerAutoUpdateRunOnce()
  }).then(response => {
    const run = response?.data
    if (run) {
      proxy.$modal.msgSuccess(
        `本轮完成：候选 ${run.candidateCount}，成功 ${run.successCount}，失败 ${run.failCount}，跳过 ${run.skippedCount}`
      )
    } else {
      proxy.$modal.msgSuccess('本轮已执行')
    }
    getList()
  }).catch(() => {}).finally(() => {
    triggering.value = false
  })
}

function openDetail(row) {
  detail.value.run = row
  detail.value.items = []
  detail.value.total = 0
  detail.value.query = { pageNum: 1, pageSize: 20, result: null, keyId: null }
  detail.value.open = true
  loadItems()
}

function loadItems() {
  const run = detail.value.run
  if (!run?.runId) return
  detail.value.loading = true
  listAutoUpdateRunItems(run.runId, detail.value.query).then(response => {
    detail.value.items = response.rows || []
    detail.value.total = response.total || 0
  }).finally(() => {
    detail.value.loading = false
  })
}

getList()
</script>

<style scoped>
.aur-intro { margin-bottom: 12px; }
.aur-mono { font-family: Consolas, Monaco, monospace; font-size: 12px; }
.aur-muted { color: var(--kms-text-secondary, #909399); }
.aur-ok { color: #67c23a; font-weight: 600; }
.aur-fail { color: #f56c6c; }
.aur-detail-head { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
</style>
