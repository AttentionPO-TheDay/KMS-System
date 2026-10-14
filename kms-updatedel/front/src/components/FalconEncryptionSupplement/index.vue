<template>
  <section class="falcon-supplement" aria-label="改进型无证书格加密密钥">
    <div class="falcon-supplement__heading">
      <strong>改进型无证书格加密密钥</strong>
      <el-tag v-if="state.ready" size="small" type="success">已就绪</el-tag>
      <el-button v-if="state.canAdd" size="small" type="primary" :loading="busy" :disabled="loading" @click="supplement">
        {{ state.pending ? '继续登记格加密密钥' : '补充格加密密钥' }}
      </el-button>
      <el-button size="small" :disabled="busy" :loading="loading" @click="load">检查状态</el-button>
    </div>
    <p>{{ error || state.message || '正在检查现有密钥…' }}</p>
    <p class="falcon-supplement__note">独立加密密钥用于保护 SM4 会话密钥，现有签名密钥继续用于签名。私钥保存在本机；该加密方案为实验性。</p>
  </section>
</template>

<script setup>
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getSelfNode, listSelfNodeKeys } from '@/api/pqkds/node-self'
import { cryptoProvider } from '@/utils/crypto/browser-provider.js'
import { generateAndRegisterNodeKey } from '@/utils/node-initialization'
import { inspectFalconEncryption } from '@/utils/falcon-encryption-state.js'

const emit = defineEmits(['registered'])
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const node = ref({})
const state = ref({ canAdd: false, ready: false })
let controller
onBeforeUnmount(() => controller?.abort())

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await getSelfNode()
    node.value = data.node || {}
    if (!data.mapped) throw new Error('当前账号未关联节点')
    const platform = await listSelfNodeKeys()
    if (platform.nodeId !== node.value.nodeId) throw new Error('密钥清单与当前节点不一致')
    const local = await cryptoProvider.inspectNodeKeys(node.value.nodeId)
    state.value = await inspectFalconEncryption({ node: node.value, keys: platform.keys || [],
      locals: local.keys || [], hasKey: ref => cryptoProvider.hasKey(ref) })
  } catch (exc) {
    state.value = { canAdd: false, ready: false }
    error.value = `无法检查格加密材料：${exc.message}`
  } finally { loading.value = false }
}

async function supplement() {
  if (busy.value || loading.value) return
  busy.value = true
  controller = new AbortController()
  try {
    await load()
    if (!state.value.canAdd) throw new Error(error.value || state.value.message)
    await generateAndRegisterNodeKey({ algorithm: 'FALCON_CL_V1', nodeId: node.value.nodeId,
      variant: 512, signal: controller.signal,
      confirmUnusedIssuance: async record => {
        await ElMessageBox.confirm(record.message, '恢复未完成加密签发', {
          type: 'warning', confirmButtonText: '弃用未使用签发并重试', cancelButtonText: '取消' })
        return true
      }
    })
    ElMessage.success('格加密密钥已补充，公钥已登记，私钥保存在本机')
    emit('registered')
  } catch (exc) {
    ElMessage.error(`补充未完成：${exc.message}；已封存材料会保留供重试`)
  } finally {
    busy.value = false
    controller = null
    await load()
  }
}

onMounted(load)
</script>

<style scoped>
.falcon-supplement { margin: 16px 0; padding: 12px 0; border-top: 1px solid var(--el-border-color); border-bottom: 1px solid var(--el-border-color); }
.falcon-supplement__heading { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.falcon-supplement p { margin: 8px 0 0; line-height: 1.6; font-size: 13px; }
.falcon-supplement__note { color: var(--el-text-color-secondary); }
</style>
