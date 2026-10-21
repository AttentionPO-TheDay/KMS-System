<template>
  <section class="key-did" aria-label="本次密钥的 DID 上链记录" :aria-busy="busy">
    <div class="key-did__heading">
      <strong>DID 上链</strong>
      <el-tag size="small" :type="confirmed ? 'success' : (record?.status === 'FAILED' ? 'danger' : 'info')">
        {{ didStatusText(record) }}
      </el-tag>
    </div>
    <p v-if="!record" class="key-did__hint">尚未关联 SysPid</p>
    <template v-else>
      <ol class="key-did__steps" aria-label="上链过程">
        <li>公钥已登记</li>
        <li>{{ record.sysPid ? 'SysPid 已保存' : 'SysPid 待分配' }}</li>
        <li>{{ confirmed ? '链上核验通过' : '链上尚未确认' }}</li>
      </ol>
      <label v-if="record.sysPid" class="key-did__identifier">
        <span>本次 SysPid</span>
        <textarea :value="record.sysPid" readonly rows="5" aria-label="本次完整 SysPid" spellcheck="false" />
      </label>
      <div class="key-did__actions">
        <el-button v-if="record.sysPid" size="small" @click="copy(record.sysPid)">复制 SysPid</el-button>
        <el-button v-if="record.sysPid" size="small" :loading="busy" @click="check">查询上链结果</el-button>
        <el-button v-if="['PREPARING', 'PREPARE_FAILED', 'PREPARED'].includes(record.status)" size="small" :loading="busy" @click="resume">继续上链</el-button>
      </div>
      <p class="key-did__verdict" role="status">
        交易有效：{{ verdict(record.transactionValid) }} · 文档一致：{{ verdict(record.metadataMatches) }}
      </p>
      <p v-if="record.errorCode" class="key-did__error">核验提示：{{ record.errorCode }}。请保留本次 SysPid 查询。</p>
      <details class="key-did__details">
        <summary>交易详情</summary>
        <dl>
          <dt>交易号</dt><dd>{{ record.txId || '尚未分配' }}</dd>
          <dt>DID</dt><dd>{{ record.did || '尚未分配' }}</dd>
          <dt>请求编号</dt><dd>{{ record.requestId }}</dd>
          <dt>链标识</dt><dd>{{ record.chainId || '尚未分配' }}</dd>
        </dl>
      </details>
    </template>
    <p v-if="error" class="key-did__error" role="alert">{{ error }}</p>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { querySelfKeyDid, continueSelfKeyDid } from '@/api/pqkds/node-self'
import { didConfirmed, didStatusText } from '@/utils/key-did-evidence'

const props = defineProps({ record: { type: Object, default: null }, keyIdentity: { type: Object, required: true } })
const emit = defineEmits(['updated'])
const busy = ref(false)
const error = ref('')
const confirmed = computed(() => didConfirmed(props.record))
const verdict = value => value === true ? '通过' : value === false ? '未通过' : '待核验'

async function run(operation) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    const result = await operation()
    emit('updated', result)
    ElMessage[didConfirmed(result) ? 'success' : 'info'](didStatusText(result))
  } catch (failure) {
    error.value = `查询或提交未完成：${failure.message || failure}。原密钥和 SysPid 保留，请稍后重试。`
  } finally {
    busy.value = false
  }
}
const check = () => run(() => querySelfKeyDid(props.record.sysPid))
const resume = () => run(() => continueSelfKeyDid(props.keyIdentity))

async function copy(value) {
  try {
    await navigator.clipboard.writeText(value)
    ElMessage.success('完整 SysPid 已复制')
  } catch {
    error.value = '浏览器未允许自动复制，请选中上方完整 SysPid 手动复制。'
  }
}
</script>

<style scoped>
.key-did { margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--el-border-color-lighter); min-width: 0; }
.key-did__heading { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
.key-did__hint, .key-did__verdict, .key-did__details { font-size: 13px; color: var(--el-text-color-secondary); line-height: 1.65; }
.key-did__steps { display: flex; flex-wrap: wrap; gap: 6px 20px; padding-left: 18px; font-size: 12px; color: var(--el-text-color-secondary); }
.key-did__identifier { display: grid; gap: 6px; font-size: 13px; color: var(--el-text-color-regular); }
.key-did__identifier textarea { width: 100%; box-sizing: border-box; resize: vertical; padding: 8px 10px; border: 1px solid var(--el-border-color); border-radius: 6px; background: var(--el-fill-color-light); color: var(--el-text-color-primary); font: 12px/1.6 ui-monospace, monospace; overflow-wrap: anywhere; }
.key-did__identifier textarea:focus-visible, summary:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: 2px; }
.key-did__actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
.key-did__actions :deep(.el-button + .el-button) { margin-left: 0; }
.key-did__error { font-size: 13px; line-height: 1.6; color: var(--el-color-danger); overflow-wrap: anywhere; }
.key-did__details summary { cursor: pointer; width: fit-content; }
.key-did__details dl { display: grid; grid-template-columns: 65px minmax(0, 1fr); gap: 5px 10px; }
.key-did__details dd { margin: 0; overflow-wrap: anywhere; font: 12px/1.65 ui-monospace, monospace; }
</style>
