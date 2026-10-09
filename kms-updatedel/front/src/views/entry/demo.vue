<template>
  <main class="entry-page">
    <el-card class="entry-card" shadow="never" v-loading="loading">
      <h1>密钥管理系统 · 受控演示</h1>
      <p>此入口只在已启用的受控本机网关可用。无需账号、密码或激活凭证；身份由服务端演示会话确认。</p>
      <el-alert v-if="error" :title="error" type="warning" :closable="false" show-icon />
      <el-form @submit.prevent="resolveNode" label-position="top">
        <el-form-item label="已有节点 ID">
          <el-input v-model="nodeId" placeholder="例如 DEMO-NODE-01" maxlength="64" :disabled="!enabled || loading" />
        </el-form-item>
        <el-button type="primary" :loading="loading" :disabled="!enabled" @click="resolveNode">进入节点</el-button>
        <el-button :disabled="!enabled || loading" @click="openAdmin">管理控制台</el-button>
      </el-form>
      <p class="hint">节点不存在时不会自动创建。请进入管理控制台显式登记，再用节点 ID 进入；停用节点不能进入。</p>
      <p class="hint">演示私钥只在当前浏览器的独立密钥库内。不会复制独立运行材料，缺失或不匹配时不会覆盖已登记公钥。</p>
      <a href="/updatedel/standalone">返回独立运行入口</a>
    </el-card>
  </main>
</template>

<script setup>
import { loadDemoContext, enterDemo, switchDemo } from '@/utils/demo-context'

const route = useRoute()
const nodeId = ref(typeof route.query.nodeId === 'string' ? route.query.nodeId : '')
const loading = ref(false)
const enabled = ref(false)
const error = ref('')

async function resolveNode() {
  error.value = ''
  if (!nodeId.value) {
    error.value = '缺少节点 ID。请输入已有节点，或进入管理控制台登记。'
    return
  }
  loading.value = true
  try {
    await enterDemo(nodeId.value)
  } catch (err) {
    error.value = err?.response?.data?.msg || err.message || '节点入口解析失败'
  } finally {
    loading.value = false
  }
}

async function openAdmin() {
  loading.value = true
  error.value = ''
  try { await switchDemo('ADMIN') }
  catch (err) { error.value = err?.response?.data?.msg || err.message || '管理控制台不可用' }
  finally { loading.value = false }
}

onMounted(async () => {
  loading.value = true
  try {
    await loadDemoContext()
    enabled.value = true
  } catch (err) {
    error.value = err?.response?.data?.msg || err.message || '受控演示未启用'
  } finally { loading.value = false }
  if (enabled.value && nodeId.value) await resolveNode()
  else if (enabled.value) error.value = String(route.query.reason || '缺少节点 ID。请输入已有节点，或进入管理控制台登记。')
})
</script>

<style scoped>
.entry-page { min-height: 100vh; display: grid; place-items: center; padding: 24px; background: var(--kms-surface-2); }
.entry-card { max-width: 640px; width: 100%; }
h1 { font-size: 22px; }
p { line-height: 1.8; }
.el-form { margin-top: 24px; }
.hint { color: var(--el-text-color-secondary); font-size: 13px; }
</style>
