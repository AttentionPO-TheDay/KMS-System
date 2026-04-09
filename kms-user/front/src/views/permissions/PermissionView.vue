<template>
  <section class="page">
    <div class="page-header">
      <p class="eyebrow">Permission</p>
      <h2>权限申请与回退</h2>
      <p>第一阶段仅开放“查看公共密钥列表”和“密钥自动更新”两类临时权限申请。</p>
    </div>

    <article class="panel">
      <h3>申请人信息</h3>
      <div class="form-grid">
        <label>
          <span>用户 ID</span>
          <input :value="profile.userId" type="number" min="1" disabled />
        </label>
        <label>
          <span>用户名</span>
          <input :value="profile.userName" type="text" disabled />
        </label>
        <label>
          <span>当前等级</span>
          <select :value="profile.originalLevel" disabled>
            <option :value="2">普通用户</option>
            <option :value="1">中级用户</option>
            <option :value="0">管理员</option>
          </select>
        </label>
      </div>
      <p class="muted">
        <template v-if="isAuthenticated">申请人信息来自统一登录态，并随请求透传到各业务系统。</template>
        <template v-else>请先在左侧完成登录，权限申请会复用同一份用户会话。</template>
      </p>
    </article>

    <div class="card-grid two-col">
      <article class="card action-card">
        <h3>查看公共密钥列表</h3>
        <p>生成域权限。普通用户申请通过后可临时查看公共密钥列表，目标等级为中级用户。</p>
        <textarea v-model="reasons.PUBLIC_KEY_LIST" rows="4" placeholder="请填写申请理由"></textarea>
        <button @click="submit('PUBLIC_KEY_LIST')" :disabled="loading.PUBLIC_KEY_LIST">
          {{ loading.PUBLIC_KEY_LIST ? '提交中...' : '提交生成域申请' }}
        </button>
      </article>

      <article class="card action-card">
        <h3>密钥自动更新</h3>
        <p>更新与回收域权限。普通用户申请通过后可临时操作自动更新，目标等级为管理员。</p>
        <textarea v-model="reasons.AUTO_UPDATE" rows="4" placeholder="请填写申请理由"></textarea>
        <button @click="submit('AUTO_UPDATE')" :disabled="loading.AUTO_UPDATE">
          {{ loading.AUTO_UPDATE ? '提交中...' : '提交更新与回收申请' }}
        </button>
      </article>
    </div>

    <article class="panel">
      <div class="panel-head">
        <h3>我的申请记录</h3>
        <button class="ghost-button" @click="loadRecords">刷新</button>
      </div>
      <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>
      <div v-if="records.length === 0" class="empty-state">暂无申请记录</div>
      <div v-else class="record-list">
        <article v-for="record in records" :key="`${record.systemCode}-${record.requestId}`" class="record-card">
          <div class="record-head">
            <strong>{{ record.featureName }}</strong>
            <span class="badge" :class="`status-${record.status}`">{{ statusText(record.status) }}</span>
          </div>
          <p>系统：{{ systemText(record.systemCode) }}</p>
          <p>申请等级：{{ levelText(record.requestLevel) }}</p>
          <p>申请理由：{{ record.requestReason }}</p>
          <p v-if="record.approveBy">审批人：{{ record.approveBy }}</p>
          <p v-if="record.approveNote">审批备注：{{ record.approveNote }}</p>
          <button
            v-if="record.status === '1'"
            class="danger-button"
            @click="rollback(record)"
          >
            回退权限
          </button>
        </article>
      </div>
    </article>
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
      return new Date(b.requestTime || 0).getTime() - new Date(a.requestTime || 0).getTime()
    })
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

function systemText(systemCode) {
    return { generate: '密钥生成系统', lifecycle: '密钥动态更新与回收系统' }[systemCode] || systemCode
}

function statusText(status) {
  return { 0: '待审批', 1: '已通过', 2: '已拒绝', 3: '已回退' }[status] || '未知'
}
</script>
