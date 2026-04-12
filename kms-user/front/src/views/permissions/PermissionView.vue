<template>
  <section class="page">

    <div class="permission-dashboard">
      <aside class="apply-side">
        <article class="panel glass-panel profile-panel">
          <h3>👤 申请人信息</h3>
          <el-form label-position="top" class="mt16">
            <el-form-item label="用户 ID">
              <el-input :value="profile.userId" disabled />
            </el-form-item>
            <el-form-item label="用户名">
              <el-input :value="profile.userName" disabled />
            </el-form-item>
            <el-form-item label="当前内置等级">
              <el-input :value="levelText(profile.originalLevel)" disabled />
            </el-form-item>
          </el-form>
          <p class="muted small mt10" style="font-size: 12px; opacity: 0.7;">
            <template v-if="isAuthenticated">会话自动透传各业务节点</template>
            <template v-else>未登录</template>
          </p>
        </article>

        <article class="panel glass-panel action-card">
          <h3>🌐 生成域：公共密钥</h3>
          <p class="muted">提供临时查看公共库的权限 (目标：中级用户)</p>
          <el-input type="textarea" v-model="reasons.PUBLIC_KEY_LIST" :rows="3" placeholder="请简述申请该数据权限的合理性..." class="mt10" />
          <el-button type="primary" class="full-width mt10" @click="submit('PUBLIC_KEY_LIST')" :disabled="loading.PUBLIC_KEY_LIST || hasFeatureAccess('PUBLIC_KEY_LIST')">
            {{ hasFeatureAccess('PUBLIC_KEY_LIST') ? '✔️ 当前已具备该权限' : (loading.PUBLIC_KEY_LIST ? '提交中...' : '提交审批申请') }}
          </el-button>
        </article>

        <article class="panel glass-panel action-card">
          <h3>⚡ 状态域：自动更新</h3>
          <p class="muted">提供一键开启密钥托管更新的能力 (目标：管理员)</p>
          <el-input type="textarea" v-model="reasons.AUTO_UPDATE" :rows="3" placeholder="请简述开启安全托管的原因..." class="mt10" />
          <el-button type="primary" class="full-width mt10" @click="submit('AUTO_UPDATE')" :disabled="loading.AUTO_UPDATE || hasFeatureAccess('AUTO_UPDATE')">
            {{ hasFeatureAccess('AUTO_UPDATE') ? '✔️ 当前已具备该权限' : (loading.AUTO_UPDATE ? '提交中...' : '提交审批申请') }}
          </el-button>
        </article>
      </aside>

      <main class="history-main">
        <article class="panel glass-panel full-height">
          <div class="panel-head flex-between">
            <h3>📜 审批时间轴记录</h3>
            <el-button plain size="small" @click="loadRecords">↻ 刷新记录</el-button>
          </div>
          
          <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>
          
          <div v-if="records.length === 0" class="empty-state">
            暂无历史申请记录
          </div>
          
          <el-timeline v-else class="mt16 custom-timeline">
            <el-timeline-item
              v-for="record in records"
              :key="`${record.systemCode}-${record.requestId}`"
              :type="timelineItemType(record.status)"
              :timestamp="getTimelineDate(record)"
              placement="top"
            >
              <div class="timeline-card">
                <div class="timeline-head">
                  <strong>{{ record.featureName }}</strong>
                  <div style="display: flex; gap: 8px; align-items: center;">
                    <span class="style-badge" :class="`status-${record.status}`">{{ statusText(record.status) }}</span>
                    <el-button
                      v-if="record.status === '1' && Number(record.isTemp) === 1"
                      type="danger" size="small"
                      @click="rollback(record)"
                    >
                      安全回退
                    </el-button>
                  </div>
                </div>
                <div class="timeline-body">
                  <div class="info-row"><span>目标能力组：</span>{{ levelText(record.requestLevel) }}</div>
                  <div class="info-row"><span>申请理由：</span>{{ record.requestReason }}</div>
                  <div v-if="record.approveBy" class="info-row"><span>审批回执 ({{ record.approveBy }})：</span>{{ record.approveNote || '已受理' }}</div>
                </div>
              </div>
            </el-timeline-item>
          </el-timeline>
        </article>
      </main>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { listPermissionRequests, rollbackPermission, submitPermissionRequest } from '@/services/permission-api'
import useUserStore from '@/store/modules/user'

const userStore = useUserStore()

const profile = reactive({
  userId: '',
  userName: '',
  originalLevel: 2
})

const reasons = reactive({
  PUBLIC_KEY_LIST: '',
  AUTO_UPDATE: ''
})

const loading = reactive({
  PUBLIC_KEY_LIST: false,
  AUTO_UPDATE: false
})

const records = ref([])
const activeFeatureAccess = reactive({
  PUBLIC_KEY_LIST: false,
  AUTO_UPDATE: false
})
const errorMessage = ref('')
const isAuthenticated = computed(() => Boolean(userStore.token))

watch(
  () => ({
    userId: userStore.id,
    userName: userStore.name,
    roleLevel: userStore.roleLevel,
    token: userStore.token
  }),
  (value) => {
    profile.userId = value.userId || ''
    profile.userName = value.userName || ''
    profile.originalLevel = value.roleLevel ?? 2

    if (!value.token) {
      records.value = []
    }
  },
  { immediate: true }
)

onMounted(() => {
  loadRecords()
})

async function submit(featureCode) {
  errorMessage.value = ''
  if (!isAuthenticated.value) {
    errorMessage.value = '请先在左侧登录，再提交权限申请。'
    return
  }

  const reason = reasons[featureCode]?.trim()
  if (hasFeatureAccess(featureCode)) {
    errorMessage.value = '当前账号已具备该权限，无需重复申请。'
    return
  }
  if (!profile.userId || !profile.userName.trim()) {
    errorMessage.value = '当前登录用户信息不完整，请刷新资料后重试。'
    return
  }
  if (!reason || reason.length < 4) {
    errorMessage.value = '申请理由至少 4 个字符。'
    return
  }

  loading[featureCode] = true
  try {
    await submitPermissionRequest(featureCode, {
      userId: Number(profile.userId),
      userName: profile.userName.trim(),
      originalLevel: Number(profile.originalLevel),
      requestReason: reason
    })
    reasons[featureCode] = ''
    await loadRecords()
  } catch (error) {
    errorMessage.value = error.message
  } finally {
    loading[featureCode] = false
  }
}

async function loadRecords() {
  errorMessage.value = ''
  if (!isAuthenticated.value) {
    records.value = []
    return
  }

  if (!profile.userId) {
    try {
      await userStore.getInfo()
    } catch (error) {
      errorMessage.value = error.message
      records.value = []
      return
    }
  }

  if (!profile.userId) {
    records.value = []
    return
  }

  try {
    const [generateData, lifecycleData] = await Promise.all([
      listPermissionRequests('PUBLIC_KEY_LIST', Number(profile.userId)),
      listPermissionRequests('AUTO_UPDATE', Number(profile.userId))
    ])
    records.value = [...generateData.rows, ...lifecycleData.rows].sort((a, b) => {
      return getRecordTime(b) - getRecordTime(a)
    })
    activeFeatureAccess.PUBLIC_KEY_LIST = hasApprovedTemporaryRequest(generateData.rows)
    activeFeatureAccess.AUTO_UPDATE = hasApprovedTemporaryRequest(lifecycleData.rows)
  } catch (error) {
    errorMessage.value = error.message
  }
}

async function rollback(record) {
  errorMessage.value = ''
  try {
    await rollbackPermission(record.featureCode, record.requestId)
    await loadRecords()
  } catch (error) {
    errorMessage.value = error.message
  }
}

function levelText(level) {
  return { 0: '管理员', 1: '中级用户', 2: '普通用户' }[level] || '未知'
}

function hasFeatureAccess(featureCode) {
  const roleLevel = Number(profile.originalLevel)
  if (featureCode === 'PUBLIC_KEY_LIST') {
    return roleLevel <= 1 || activeFeatureAccess.PUBLIC_KEY_LIST
  }
  if (featureCode === 'AUTO_UPDATE') {
    return roleLevel <= 0 || activeFeatureAccess.AUTO_UPDATE
  }
  return false
}

function hasApprovedTemporaryRequest(rows = []) {
  return rows.some((item) => String(item?.status) === '1' && Number(item?.isTemp) === 1)
}

function getRecordTime(record) {
  const value = record?.approveTime || record?.requestTime
  const parsed = value ? new Date(value).getTime() : NaN
  if (!Number.isNaN(parsed)) {
    return parsed
  }
  return Number(record?.requestId) || 0
}

function systemText(systemCode) {
    return { generate: '密钥生成系统', lifecycle: '密钥动态更新与回收系统' }[systemCode] || systemCode
}

function statusText(status) {
  return { 0: '待审批', 1: '已通过', 2: '已拒绝', 3: '已回退' }[status] || '未知'
}

function timelineItemType(status) {
  return { '0': 'primary', '1': 'success', '2': 'danger', '3': 'warning' }[String(status)] || 'info'
}

function getTimelineDate(record) {
  const value = record?.requestTime
  return value ? new Date(value).toLocaleString() : '-'
}
</script>

<style scoped>
.permission-dashboard {
  display: flex;
  gap: 24px;
  align-items: flex-start;
  margin-top: 24px;
}

.apply-side {
  width: 32%;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.history-main {
  flex-grow: 1;
  min-width: 0;
}

.full-height {
  min-height: 700px;
}

.full-width {
  width: 100%;
}

.mt10 {
  margin-top: 10px;
}

.mt16 {
  margin-top: 16px;
}

.flex-between {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.custom-timeline {
  padding-left: 2px;
}

.custom-timeline :deep(.el-timeline-item__timestamp) {
  color: rgba(255, 255, 255, 0.5);
}

.timeline-card {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  padding: 16px;
  margin-top: 8px;
}

.timeline-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  padding-bottom: 8px;
}

.timeline-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.info-row {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.8);
}

.info-row span {
  color: rgba(255, 255, 255, 0.5);
}

.style-badge {
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
}
.status-0 { background: rgba(0, 153, 255, 0.15); color: #4db8ff; border: 1px solid rgba(0, 153, 255, 0.3); }
.status-1 { background: rgba(103, 194, 58, 0.15); color: #85ce61; border: 1px solid rgba(103, 194, 58, 0.3); }
.status-2 { background: rgba(245, 108, 108, 0.15); color: #f56c6c; border: 1px solid rgba(245, 108, 108, 0.3); }
.status-3 { background: rgba(144, 147, 153, 0.15); color: #a6a9ad; border: 1px solid rgba(144, 147, 153, 0.3); }

@media (max-width: 960px) {
  .permission-dashboard {
    flex-direction: column;
  }
  .apply-side {
    width: 100%;
  }
}
</style>
