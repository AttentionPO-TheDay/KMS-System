<template>
  <div class="app-container node-init">
    <el-card shadow="never" class="node-init__card">
      <template #header>
        <div class="node-init__header">
          <h2>节点首次初始化</h2>
          <el-tag :type="statusTagType" size="large">{{ statusText }}</el-tag>
        </div>
      </template>

      <!-- 账号没关联节点：这是管理员账号，或数据异常 -->
      <el-alert
        v-if="!loading && !mapped"
        type="warning"
        :closable="false"
        show-icon
        title="当前账号未关联任何节点"
        description="本页面只对「区块链节点」账号有意义。平台管理员不执行节点密钥初始化 —— 请在「节点管理」里创建节点，再由节点自行登录初始化。"
      />

      <template v-else>
        <p class="node-init__lead">
          节点
          <strong>{{ node.nodeId }}</strong>
          <span v-if="node.name">（{{ node.name }}）</span>
          由管理员创建后获得登录资格。首次登录需要完成四套基础密钥的初始化，
          之后才能进行密钥生成、更新与分发。
        </p>

        <el-descriptions :column="2" border class="node-init__meta">
          <el-descriptions-item label="节点ID">{{ node.nodeId || '-' }}</el-descriptions-item>
          <el-descriptions-item label="节点名称">{{ node.name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="权限等级">{{ node.permissionLevel || '-' }}</el-descriptions-item>
          <el-descriptions-item label="所属域">{{ node.domainId || '-' }}</el-descriptions-item>
          <el-descriptions-item label="节点状态">{{ statusText }}</el-descriptions-item>
          <el-descriptions-item label="初始化时间">{{ node.initializedAt || '-' }}</el-descriptions-item>
        </el-descriptions>

        <!-- 四套密钥就绪情况。这是本页的核心信息：
             只有四套都齐，节点才算可用（文档 §3.1）。 -->
        <h3 class="node-init__section-title">基础密钥</h3>
        <div class="node-init__keys">
          <div
            v-for="k in keyCards"
            :key="k.key"
            class="node-init__key"
            :class="{ 'is-ready': k.ready }"
          >
            <div class="node-init__key-name">{{ k.label }}</div>
            <div class="node-init__key-role">{{ k.role }}</div>
            <el-tag :type="k.ready ? 'success' : 'info'" size="small">
              {{ k.ready ? '已就绪' : '未生成' }}
            </el-tag>
          </div>
        </div>

        <el-alert
          v-if="isActive"
          class="node-init__done"
          type="success"
          :closable="false"
          show-icon
          title="初始化已完成"
          description="四套基础密钥均已就绪。你可以前往「密钥生成」创建业务密钥，或在「密钥分发」中与其它节点建立会话。"
        />

        <div class="node-init__actions">
          <el-button
            v-if="!isActive"
            type="primary"
            size="large"
            :loading="initializing"
            :disabled="loading || !mapped"
            @click="handleInit"
          >
            {{ initializing ? '正在生成四套密钥…' : '开始初始化' }}
          </el-button>
          <el-button v-if="isActive" type="primary" size="large" @click="goWorkbench">
            进入工作台
          </el-button>
          <el-button :disabled="initializing" @click="load">刷新状态</el-button>
        </div>

        <!-- 时间预期：Falcon 占大头，不告知的话用户会以为卡死 -->
        <p v-if="!isActive" class="node-init__hint">
          初始化会依次生成 Kyber、SSCL、SM2、Falcon 四套密钥，整体约 15~25 秒
          （Falcon 的计算与写入占大头）。期间请勿关闭页面或重复点击。
        </p>
      </template>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getSelfNode, initSelfNodeKeys } from '@/api/pqkds/node-self'
import { markNodeInitialized } from '@/utils/node-init-status'

const router = useRouter()

const loading = ref(true)
const initializing = ref(false)
const mapped = ref(false)
const node = ref({})

const KEY_META = [
  { key: 'kyber', label: 'Kyber', role: '后量子密钥封装 / 建立共享秘密' },
  { key: 'sscl', label: 'SSCL', role: '保护 / 封装 SM4 会话密钥' },
  { key: 'sm2', label: 'SM2', role: '保护 / 封装 SM4 会话密钥' },
  { key: 'falcon', label: 'Falcon', role: '对分发消息签名与验签' }
]

const keyCards = computed(() => {
  const keys = node.value.keys || {}
  return KEY_META.map((m) => ({ ...m, ready: Boolean(keys[m.key]) }))
})

const statusText = computed(() => {
  const s = node.value.status
  if (s === 'ACTIVE') return '已激活'
  if (s === 'DISABLED') return '已停用'
  return '待初始化'
})

const statusTagType = computed(() => {
  const s = node.value.status
  if (s === 'ACTIVE') return 'success'
  if (s === 'DISABLED') return 'danger'
  return 'warning'
})

const isActive = computed(() => node.value.status === 'ACTIVE')

async function load() {
  loading.value = true
  try {
    const data = await getSelfNode()
    mapped.value = Boolean(data?.mapped)
    node.value = data?.node || {}
    // 已激活的节点若手工进到本页（书签/后退），顺手把守卫缓存同步成 ACTIVE，
    // 免得它仍按 PENDING_INIT 把用户弹回来。
    if (node.value.status === 'ACTIVE') {
      markNodeInitialized()
    }
  } catch (error) {
    ElMessage.error(`读取节点状态失败：${error.message}`)
  } finally {
    loading.value = false
  }
}

async function handleInit() {
  if (initializing.value) return
  initializing.value = true
  try {
    const data = await initSelfNodeKeys()
    node.value = data?.node || node.value
    // 主动失效守卫里的状态缓存：不清的话它还是 PENDING_INIT，
    // 用户一点别的页面就会被弹回引导页 —— "初始化完了还进不去"。
    markNodeInitialized()
    if (data?.alreadyInitialized) {
      ElMessage.info('该节点此前已完成初始化')
    } else {
      ElMessage.success('四套基础密钥初始化完成')
    }
  } catch (error) {
    // 失败时保持 PENDING_INIT，允许重试 —— 明确告知可以再来一次，
    // 而不是让用户以为节点坏了。
    ElMessage.error(`初始化失败：${error.message}（可稍后重试）`)
    await load()
  } finally {
    initializing.value = false
  }
}

function goWorkbench() {
  router.push('/workbench')
}

onMounted(load)
</script>

<style scoped>
.node-init__card { max-width: 980px; margin: 24px auto; }
.node-init__header { display: flex; align-items: center; justify-content: space-between; }
.node-init__header h2 { margin: 0; font-size: 18px; }
.node-init__lead { margin: 0 0 16px; color: var(--kms-text-secondary, #606266); line-height: 1.7; }
.node-init__meta { margin-bottom: 24px; }
.node-init__section-title { margin: 0 0 12px; font-size: 15px; }
.node-init__keys {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px; margin-bottom: 20px;
}
.node-init__key {
  border: 1px solid var(--el-border-color, #dcdfe6); border-radius: 6px;
  padding: 12px 14px; display: flex; flex-direction: column; gap: 6px;
}
.node-init__key.is-ready { border-color: var(--el-color-success, #67c23a); }
.node-init__key-name { font-weight: 600; }
.node-init__key-role { font-size: 12px; color: var(--kms-text-secondary, #909399); line-height: 1.5; }
.node-init__done { margin-bottom: 20px; }
.node-init__actions { display: flex; gap: 12px; }
.node-init__hint { margin: 16px 0 0; font-size: 12px; color: var(--kms-text-secondary, #909399); line-height: 1.6; }
</style>