<template>
  <section class="app-container workbench-page">
    <el-card shadow="never" class="hero-card">
      <div class="hero-layout">
        <div>
          <p class="hero-eyebrow">KMS User</p>
          <h2>统一用户工作台</h2>
          <p class="hero-desc">用户侧入口已经收敛到生成、生命周期、分发与权限四个页面。工作台只负责概览和快捷跳转，不再承载旧版密钥前端计算逻辑。</p>
        </div>
        <div class="hero-user">
          <el-avatar :src="userStore.avatar" :size="64" />
          <div>
            <div class="hero-name">{{ userStore.name || '未登录用户' }}</div>
            <div class="hero-meta">用户 ID：{{ userStore.id || '-' }}</div>
            <div class="hero-meta">当前等级：{{ roleText(userStore.roleLevel) }}</div>
          </div>
        </div>
      </div>
    </el-card>

    <el-row :gutter="16" class="summary-row">
      <el-col :xs="24" :sm="12" :lg="6" v-for="item in summaryCards" :key="item.title">
        <el-card shadow="hover" class="summary-card">
          <div class="summary-title">{{ item.title }}</div>
          <div class="summary-value">{{ item.value }}</div>
          <div class="summary-desc">{{ item.desc }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :span="24">
        <el-card shadow="never" class="section-card">
          <template #header>
            <div class="section-head">
              <span>功能入口</span>
            </div>
          </template>

          <div class="feature-grid">
            <article v-for="item in featureCards" :key="item.path" class="feature-card">
              <div>
                <h3>{{ item.title }}</h3>
                <p>{{ item.desc }}</p>
                <el-tag size="small" :type="item.tagType">{{ item.tag }}</el-tag>
              </div>
              <el-button type="primary" plain @click="router.push(item.path)">进入</el-button>
            </article>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive } from 'vue'
import { useRouter } from 'vue-router'
import useUserStore from '@/store/modules/user'
import { listPermissionRequests } from '@/services/permission-api'

const router = useRouter()
const userStore = useUserStore()
const featureAccess = reactive({
  PUBLIC_KEY_LIST: false,
  AUTO_UPDATE: false
})

const summaryCards = computed(() => [
  {
    title: '统一身份',
    value: userStore.name || '-',
    desc: '三套业务系统共用同一登录身份'
  },
  {
    title: '当前等级',
    value: roleText(userStore.roleLevel),
    desc: '临时授权后刷新即可获得目标能力'
  },
  {
    title: '公共密钥权限',
    value: Number(userStore.roleLevel) <= 1 || featureAccess.PUBLIC_KEY_LIST ? '已具备' : '待申请',
    desc: '用于查看生成域公共密钥列表'
  },
  {
    title: '自动更新权限',
    value: Number(userStore.roleLevel) <= 0 || featureAccess.AUTO_UPDATE ? '已具备' : '待申请',
    desc: '用于生命周期域自动更新配置'
  }
])

const featureCards = [
  {
    path: '/user_actions/generate',
    title: '密钥生成',
    desc: '发起生成请求，查看生成记录、详情、公共参数和公共密钥列表。',
    tag: '生成域',
    tagType: 'success'
  },
  {
    path: '/user_actions/updatedel',
    title: '更新与回收',
    desc: '管理我的密钥，执行更新、回收以及自动更新开关。',
    tag: '生命周期域',
    tagType: 'warning'
  },
  {
    path: '/user_actions/distribute',
    title: '分发记录',
    desc: '查询分发流水、状态与链上记录，定位分发执行结果。',
    tag: '分发域',
    tagType: 'info'
  },
  {
    path: '/user_actions/permissions',
    title: '权限申请',
    desc: '提交临时权限申请，查看审批状态并在完成操作后主动回退。',
    tag: '统一前台',
    tagType: 'primary'
  }
]

function roleText(level) {
  return { 0: '管理员', 1: '中级用户', 2: '普通用户' }[level] || '普通用户'
}

onMounted(async () => {
  if (!userStore.token) {
    return
  }
  if (!userStore.id) {
    await userStore.getInfo()
  }
  if (!userStore.id) {
    return
  }
  const [generateData, lifecycleData] = await Promise.all([
    listPermissionRequests('PUBLIC_KEY_LIST', Number(userStore.id)),
    listPermissionRequests('AUTO_UPDATE', Number(userStore.id))
  ])
  featureAccess.PUBLIC_KEY_LIST = hasApprovedTemporaryRequest(generateData.rows)
  featureAccess.AUTO_UPDATE = hasApprovedTemporaryRequest(lifecycleData.rows)
})

function hasApprovedTemporaryRequest(rows = []) {
  return rows.some((item) => String(item?.status) === '1' && Number(item?.isTemp) === 1)
}
</script>

<style scoped>
.workbench-page {
  display: grid;
  gap: 16px;
}

.hero-card,
.section-card,
.summary-card {
  border-radius: 16px;
}

.hero-layout {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: center;
  flex-wrap: wrap;
}

.hero-eyebrow {
  margin: 0 0 8px;
  color: var(--el-color-primary);
  font-weight: 600;
}

.hero-layout h2 {
  margin: 0 0 8px;
}

.hero-desc {
  margin: 0;
  max-width: 760px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}

.hero-user {
  display: flex;
  align-items: center;
  gap: 16px;
}

.hero-name {
  font-size: 18px;
  font-weight: 600;
}

.hero-meta {
  margin-top: 4px;
  color: var(--el-text-color-secondary);
}

.summary-row {
  margin: 0;
}

.summary-card {
  min-height: 136px;
}

.summary-title {
  color: var(--el-text-color-secondary);
}

.summary-value {
  margin-top: 12px;
  font-size: 28px;
  font-weight: 700;
}

.summary-desc {
  margin-top: 8px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}

.section-head {
  font-weight: 600;
}

.feature-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 16px;
}

.feature-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 16px;
  padding: 18px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 16px;
  min-height: 190px;
}

.feature-card h3 {
  margin: 0 0 8px;
}

.feature-card p {
  margin: 0 0 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}

.tips-list {
  display: grid;
  gap: 12px;
}

.quick-links {
  margin-top: 16px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
}
</style>
